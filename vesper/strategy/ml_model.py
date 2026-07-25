"""
XGBoost ranking strategy.
Loads the trained model, scores every stock, buys the top N.
"""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

from vesper.data.features import compute_features, FEATURE_COLS, zscore_features
from .base import Signal, SignalAction, Strategy
from .forecast import ForecastRecord

logger = logging.getLogger("vesper.strategy.ml_model")


def _canonical_sha256(value) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class MLModelStrategy(Strategy):
    def __init__(self, params: dict):
        super().__init__("ml_model", params)

        model_path = params.get("model_path", "models/xgb_ranker.json")
        self.model_path = Path(model_path)
        self.compatibility_path = self.model_path.with_suffix(".compatibility.json")
        self._shadow_compatibility = None
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Model not found at {model_path}. "
                f"Run: python scripts/train_model.py first."
            )
        self.model_artifact_sha256 = hashlib.sha256(self.model_path.read_bytes()).hexdigest()

        self.model = xgb.XGBRegressor()
        self.model.load_model(model_path)
        logger.info("Loaded model from %s", model_path)

        self.top_n = params.get("top_n", 5)
        self.lookback = params.get("lookback", 50)
        self.entry_threshold = params.get("entry_threshold", 0.0)
        self.exit_rank = params.get("exit_rank", 10)
        self.rebalance_interval = params.get("rebalance_interval", 30)
        self._last_rebalance: datetime | None = None

    def _load_shadow_compatibility(self):
        if self._shadow_compatibility is not None:
            return self._shadow_compatibility

        try:
            manifest = json.loads(self.compatibility_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"invalid compatibility manifest at {self.compatibility_path}: {exc}"
            ) from exc
        if not isinstance(manifest, dict):
            raise ValueError("compatibility manifest must be a JSON object")

        required = {
            "schema_version",
            "model_artifact_sha256",
            "label_horizon",
            "target_definition",
            "feature_cols",
            "feature_identity_sha256",
            "approved_universe",
            "universe_identity_sha256",
        }
        missing = sorted(required - set(manifest))
        if missing:
            raise ValueError(
                f"compatibility manifest missing required fields: {', '.join(missing)}"
            )
        if manifest["schema_version"] != "1":
            raise ValueError("compatibility manifest schema_version must be 1")
        if manifest["model_artifact_sha256"] != self.model_artifact_sha256:
            raise ValueError("compatibility manifest model_artifact_sha256 mismatch")
        if manifest["label_horizon"] != 5:
            raise ValueError("compatibility manifest label_horizon must be 5")
        if manifest["target_definition"] != (
            "cross_sectional_5_session_forward_return_rank"
        ):
            raise ValueError("compatibility manifest target_definition mismatch")
        if manifest["feature_cols"] != list(FEATURE_COLS):
            raise ValueError("compatibility manifest feature_cols mismatch")

        feature_identity = _canonical_sha256(list(FEATURE_COLS))
        if manifest["feature_identity_sha256"] != feature_identity:
            raise ValueError("compatibility manifest feature_identity_sha256 mismatch")

        approved_universe = manifest["approved_universe"]
        if (
            not isinstance(approved_universe, list)
            or not approved_universe
            or any(not isinstance(symbol, str) or not symbol.strip() for symbol in approved_universe)
            or len(set(approved_universe)) != len(approved_universe)
        ):
            raise ValueError("compatibility manifest approved_universe must be unique symbols")
        if manifest["universe_identity_sha256"] != _canonical_sha256(approved_universe):
            raise ValueError("compatibility manifest universe_identity_sha256 mismatch")

        self._shadow_compatibility = manifest
        return manifest

    def _score_universe(self, data) -> dict[str, float]:
        # Compute features for all stocks, then z-score cross-sectionally
        feat_rows: list[pd.DataFrame] = []
        for sym, df in data.items():
            try:
                feats = compute_features(df)
                if feats.empty or feats.iloc[-1].isna().any():
                    continue
                row = feats.iloc[[-1]].copy()
                row["symbol"] = sym
                feat_rows.append(row)
            except Exception as e:
                logger.warning("Feature error for %s: %s", sym, e)

        if not feat_rows:
            return {}

        panel = pd.concat(feat_rows, ignore_index=True)
        zscored = zscore_features(panel[FEATURE_COLS])

        # Predict using z-scored features
        scores: dict[str, float] = {}
        for i, sym in enumerate(panel["symbol"]):
            try:
                x = zscored.iloc[[i]].values
                pred = float(self.model.predict(x)[0])
                scores[sym] = pred
            except Exception as e:
                logger.warning("Predict error for %s: %s", sym, e)

        return scores

    def generate_shadow_forecasts(
        self,
        data,
        as_of_timestamp,
        *,
        valid_until_timestamp,
        dataset_identity_sha256,
        adjustment_identity_sha256,
        expert_version,
        feature_version,
        run_manifest_sha256,
    ) -> list[ForecastRecord]:
        if not isinstance(as_of_timestamp, datetime):
            raise ValueError("as_of_timestamp must be a datetime")
        if not isinstance(valid_until_timestamp, datetime):
            raise ValueError("valid_until_timestamp must be a datetime")
        if valid_until_timestamp < as_of_timestamp:
            raise ValueError("valid_until_timestamp must not be earlier than as_of_timestamp")
        compatibility = self._load_shadow_compatibility()
        unknown_symbols = sorted(set(data) - set(compatibility["approved_universe"]))
        if unknown_symbols:
            raise ValueError(
                f"symbols outside compatibility manifest universe: {', '.join(unknown_symbols)}"
            )

        as_of_date = pd.Timestamp(as_of_timestamp).date()
        for sym, df in data.items():
            if df.empty or pd.Timestamp(df.index[-1]).date() != as_of_date:
                raise ValueError(f"{sym} data does not match as-of {as_of_timestamp.isoformat()}")

        scores = self._score_universe(data)
        nonfinite = [sym for sym, score in scores.items() if not np.isfinite(score)]
        if nonfinite:
            raise ValueError(f"non-finite model score for {', '.join(sorted(nonfinite))}")

        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        values = pd.Series([score for _, score in ranked], dtype=float)
        score_std = values.std()
        if len(values) > 1 and score_std > 0:
            standardized = ((values - values.mean()) / score_std).tolist()
        else:
            standardized = [0.0] * len(ranked)

        return [
            ForecastRecord(
                symbol=sym,
                as_of_timestamp=as_of_timestamp,
                valid_until_timestamp=valid_until_timestamp,
                horizon_sessions=compatibility["label_horizon"],
                target_definition=compatibility["target_definition"],
                standardized_score=standardized[rank - 1],
                rank=rank,
                model_artifact_path=str(self.model_path),
                model_artifact_sha256=self.model_artifact_sha256,
                dataset_identity_sha256=dataset_identity_sha256,
                adjustment_identity_sha256=adjustment_identity_sha256,
                feature_identity_sha256=compatibility["feature_identity_sha256"],
                expert_version=expert_version,
                feature_version=feature_version,
                run_manifest_sha256=run_manifest_sha256,
            )
            for rank, (sym, _) in enumerate(ranked, start=1)
        ]

    def generate_signals(self, data, current_positions, timestamp):
        signals: list[Signal] = []

        # Respect rebalance interval
        if self._last_rebalance is not None:
            elapsed = (timestamp - self._last_rebalance).total_seconds() / 60
            if elapsed < self.rebalance_interval:
                return signals
        self._last_rebalance = timestamp

        scores = self._score_universe(data)
        if not scores:
            return signals

        # Rank by predicted return (descending)
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        logger.info("Model rankings: %s",
                     [(s, f"{v:.4f}") for s, v in ranked[:10]])

        # EXIT: close held positions that fell out of top N
        held = set(current_positions.keys())
        top_symbols = set(s for s, _ in ranked[: self.exit_rank])
        for sym in held:
            if sym not in top_symbols:
                rank = next((i for i, (s, _) in enumerate(ranked) if s == sym), len(ranked))
                signals.append(Signal(
                    sym, SignalAction.CLOSE, 1.0,
                    f"model rank #{rank + 1} fell outside top {self.exit_rank}",
                    timestamp,
                    {"predicted_return": scores.get(sym, 0), "rank": rank + 1},
                ))

        # ENTRY: buy top N not already held, above threshold
        candidates = [
            (sym, pred) for sym, pred in ranked
            if sym not in held and pred > self.entry_threshold
        ]

        for sym, pred in candidates[: self.top_n]:
            rank = next(i for i, (s, _) in enumerate(ranked) if s == sym)
            strength = max(0.1, 1.0 - rank / len(ranked))
            signals.append(Signal(
                sym, SignalAction.BUY, strength,
                f"model rank #{rank + 1}, predicted 5d return {pred:.4f}",
                timestamp,
                {"predicted_return": pred, "rank": rank + 1},
            ))

        return signals