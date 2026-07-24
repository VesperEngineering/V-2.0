"""
XGBoost ranking strategy.
Loads the trained model, scores every stock, buys the top N.
"""

import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

from vesper.data.features import compute_features, FEATURE_COLS, zscore_features
from .base import Signal, SignalAction, Strategy

logger = logging.getLogger("vesper.strategy.ml_model")


class MLModelStrategy(Strategy):
    def __init__(self, params: dict):
        super().__init__("ml_model", params)

        model_path = params.get("model_path", "models/xgb_ranker.json")
        if not Path(model_path).exists():
            raise FileNotFoundError(
                f"Model not found at {model_path}. "
                f"Run: python scripts/train_model.py first."
            )

        self.model = xgb.XGBRegressor()
        self.model.load_model(model_path)
        logger.info("Loaded model from %s", model_path)

        self.top_n = params.get("top_n", 5)
        self.lookback = params.get("lookback", 50)
        self.entry_threshold = params.get("entry_threshold", 0.0)
        self.exit_rank = params.get("exit_rank", 10)
        self.rebalance_interval = params.get("rebalance_interval", 30)
        self._last_rebalance: datetime | None = None

    def generate_signals(self, data, current_positions, timestamp):
        signals: list[Signal] = []

        # Respect rebalance interval
        if self._last_rebalance is not None:
            elapsed = (timestamp - self._last_rebalance).total_seconds() / 60
            if elapsed < self.rebalance_interval:
                return signals
        self._last_rebalance = timestamp

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
            return signals

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