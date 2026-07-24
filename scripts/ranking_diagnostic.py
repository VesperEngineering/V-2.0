#!/usr/bin/env python3
"""No-submit cross-sectional ranking diagnostic for the ML and momentum signals."""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import xgboost as xgb
import yaml

from vesper.data.features import FEATURE_COLS, compute_features, zscore_features
from vesper.data.feed import create_feed


LABEL_HORIZON = 5
MOMENTUM_LOOKBACK = 20
FEATURE_LOOKBACK = 50


def rank_metrics(
    scores: pd.Series,
    forward_returns: pd.Series,
    *,
    basket_size: int,
) -> dict[str, float | int]:
    """Return cross-sectional rank quality for one evaluation date."""
    panel = pd.concat([scores.rename("score"), forward_returns.rename("return")], axis=1).dropna()
    if len(panel) < basket_size * 2:
        raise ValueError("Insufficient cross-sectional coverage for top/bottom baskets")

    ranked = panel.sort_values("score", ascending=False)
    top_mean = float(ranked.head(basket_size)["return"].mean())
    bottom_mean = float(ranked.tail(basket_size)["return"].mean())
    return {
        "coverage": len(ranked),
        "top_mean_return": top_mean,
        "bottom_mean_return": bottom_mean,
        "top_bottom_spread": top_mean - bottom_mean,
        "rank_ic": float(ranked["score"].corr(ranked["return"], method="spearman")),
    }


def _ml_scores(model: xgb.XGBRegressor, bars: dict[str, pd.DataFrame]) -> pd.Series:
    rows = []
    for symbol, df in bars.items():
        features = compute_features(df)
        if features.empty or features.iloc[-1].isna().any():
            continue
        row = features.iloc[-1].copy()
        row["symbol"] = symbol
        rows.append(row)
    if not rows:
        return pd.Series(dtype=float)

    panel = pd.DataFrame(rows).set_index("symbol")
    values = model.predict(zscore_features(panel[FEATURE_COLS]).values)
    return pd.Series(values, index=panel.index, dtype=float)


def _momentum_scores(bars: dict[str, pd.DataFrame]) -> pd.Series:
    scores = {}
    for symbol, df in bars.items():
        if len(df) >= MOMENTUM_LOOKBACK + 1:
            close = df["close"]
            scores[symbol] = float(close.iloc[-1] / close.iloc[-MOMENTUM_LOOKBACK - 1] - 1)
    return pd.Series(scores, dtype=float)


def _forward_returns(bars: dict[str, pd.DataFrame], date: pd.Timestamp) -> pd.Series:
    values = {}
    for symbol, df in bars.items():
        if date not in df.index:
            continue
        index = df.index.get_loc(date)
        if isinstance(index, slice) or index + LABEL_HORIZON >= len(df):
            continue
        close = df["close"]
        values[symbol] = float(close.iloc[index + LABEL_HORIZON] / close.iloc[index] - 1)
    return pd.Series(values, dtype=float)


def _mean_metrics(rows: list[dict[str, float | int]]) -> dict[str, float | int]:
    return {
        "evaluation_dates": len(rows),
        "mean_coverage": float(np.mean([row["coverage"] for row in rows])),
        "mean_top_return": float(np.mean([row["top_mean_return"] for row in rows])),
        "mean_bottom_return": float(np.mean([row["bottom_mean_return"] for row in rows])),
        "mean_top_bottom_spread": float(np.mean([row["top_bottom_spread"] for row in rows])),
        "mean_rank_ic": float(np.mean([row["rank_ic"] for row in rows])),
    }


def run_diagnostic(
    *,
    data: dict[str, pd.DataFrame],
    model: xgb.XGBRegressor,
    basket_size: int,
) -> dict[str, dict[str, float | int]]:
    dates = sorted(set().union(*(df.index for df in data.values())))
    ml_rows = []
    momentum_rows = []
    for date in dates:
        bars = {symbol: df[df.index <= date] for symbol, df in data.items()}
        if max((len(df) for df in bars.values()), default=0) < FEATURE_LOOKBACK + 1:
            continue
        forward = _forward_returns(data, date)
        try:
            ml_rows.append(rank_metrics(_ml_scores(model, bars), forward, basket_size=basket_size))
            momentum_rows.append(rank_metrics(_momentum_scores(bars), forward, basket_size=basket_size))
        except ValueError:
            continue
    return {"ml_model": _mean_metrics(ml_rows), "momentum": _mean_metrics(momentum_rows)}


def main():
    parser = argparse.ArgumentParser(description="Run a no-submit ranking diagnostic")
    parser.add_argument("--history-days", type=int, default=200)
    parser.add_argument("--basket-size", type=int, default=10)
    parser.add_argument("--report-path", type=Path, default=Path("reports/ranking_diagnostic.json"))
    args = parser.parse_args()

    with open("config/settings.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    with open("config/universe.yaml", encoding="utf-8") as f:
        universe = yaml.safe_load(f)["universe"]

    model_path = Path(config["strategy"]["params"]["model_path"])
    model = xgb.XGBRegressor()
    model.load_model(model_path)

    end = datetime.now()
    data = create_feed(config).get_bars(universe, end - timedelta(days=args.history_days), end)
    results = run_diagnostic(data=data, model=model, basket_size=args.basket_size)
    report = {
        "model_path": str(model_path),
        "label_horizon": LABEL_HORIZON,
        "basket_size": args.basket_size,
        "history_days": args.history_days,
        "results": results,
    }
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
