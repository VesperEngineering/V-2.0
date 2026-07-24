#!/usr/bin/env python3
"""Research-only low-volatility evaluator; it does not produce trading signals or files."""

import argparse
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

FEATURE_SESSIONS = 60
LIQUIDITY_SESSIONS = 20
DISCONTINUITY_THRESHOLD = 0.20
HOLDING_SESSIONS = 21
LABELS = ["fixed-502-universe", "raw-price", "survivorship-limited"]
LIMITATION = "Holding-window discontinuity exclusion is post-outcome censoring, not deployable proof."
WINDOWS = {
    "development": ("2003-01-01", "2014-12-31"),
    "validation": ("2015-01-01", "2020-12-31"),
    "final_oos": ("2021-01-01", "2026-07-21"),
}


def _prepared(bars: pd.DataFrame) -> pd.DataFrame:
    if bars.attrs.get("low_vol_prepared"):
        return bars
    out = bars.copy()
    out["date"] = pd.to_datetime(out["date"])
    out = out.sort_values(["ticker", "date"])
    out.attrs["low_vol_prepared"] = True
    return out


def formation_features(bars: pd.DataFrame, formation_date) -> pd.DataFrame:
    """Compute no-lookahead raw-price features from observations through formation_date."""
    date = pd.Timestamp(formation_date)
    rows = []
    for ticker, group in _prepared(bars).groupby("ticker", sort=True):
        history = group[group["date"] <= date].tail(FEATURE_SESSIONS)
        if len(history) != FEATURE_SESSIONS:
            continue
        close_returns = history["close"].pct_change().dropna()
        if (close_returns.abs() >= DISCONTINUITY_THRESHOLD).any():
            continue
        dollar_volume = (history["close"] * history["volume"]).tail(LIQUIDITY_SESSIONS)
        if len(dollar_volume) != LIQUIDITY_SESSIONS:
            continue
        rows.append(
            {
                "ticker": ticker,
                "realized_volatility": float(close_returns.std()),
                "range_risk": float(((history["high"] - history["low"]) / history["close"]).mean()),
                "median_dollar_volume": float(dollar_volume.median()),
            }
        )
    return pd.DataFrame(rows).set_index("ticker") if rows else pd.DataFrame(
        columns=["realized_volatility", "range_risk", "median_dollar_volume"]
    )


def _liquid_universe(features: pd.DataFrame) -> pd.DataFrame:
    if features.empty:
        return features
    liquid_count = max(1, int(np.ceil(len(features) * 0.80)))
    return features.sort_values("median_dollar_volume", ascending=False).head(liquid_count).copy()


def select_low_volatility(features: pd.DataFrame) -> pd.DataFrame:
    """Remove the least-liquid fifth, then equally rank the lowest-volatility fifth."""
    liquid = _liquid_universe(features)
    if liquid.empty:
        return liquid
    if "range_risk" in liquid:
        liquid["risk_score"] = liquid[["realized_volatility", "range_risk"]].rank(pct=True).mean(axis=1)
    else:
        liquid["risk_score"] = liquid["realized_volatility"]
    basket_count = max(1, int(np.ceil(len(liquid) / 5)))
    return liquid.sort_values("risk_score").head(basket_count)


def holding_returns(bars: pd.DataFrame, formation_date) -> pd.Series:
    """Raw open-to-open labels, excluding future windows with a large raw-price jump."""
    date = pd.Timestamp(formation_date)
    labels = {}
    for ticker, group in _prepared(bars).groupby("ticker", sort=True):
        matching = group.index[group["date"] == date]
        if len(matching) != 1:
            continue
        position = group.index.get_loc(matching[0])
        entry = position + 1
        exit_ = position + HOLDING_SESSIONS
        if exit_ >= len(group):
            continue
        future_returns = group["close"].pct_change().iloc[entry:exit_ + 1]
        if (future_returns.abs() >= DISCONTINUITY_THRESHOLD).any():
            continue
        entry_open = group["open"].iloc[entry]
        exit_open = group["open"].iloc[exit_]
        if entry_open > 0 and exit_open > 0:
            labels[ticker] = float(exit_open / entry_open - 1)
    return pd.Series(labels, dtype=float)


def monthly_formation_dates(bars: pd.DataFrame) -> list[pd.Timestamp]:
    dates = pd.DatetimeIndex(_prepared(bars)["date"].unique())
    return [pd.Timestamp(date) for date in dates.to_series().groupby(dates.to_period("M")).max()]


def _period_rows(bars: pd.DataFrame, formation_dates) -> list[dict]:
    rows = []
    for date in formation_dates:
        features = formation_features(bars, date)
        selected = select_low_volatility(features)
        labels = holding_returns(bars, date)
        eligible = selected.index.intersection(labels.index)
        if not len(eligible):
            continue
        control_eligible = _liquid_universe(features).index.intersection(labels.index)
        rows.append(
            {
                "date": pd.Timestamp(date),
                "return": float(labels.loc[eligible].mean()),
                "names": list(eligible),
                "average_names": int(len(eligible)),
                "control_return": float(labels.loc[control_eligible].mean()),
                "control_names": list(control_eligible),
                "control_average_names": int(len(control_eligible)),
            }
        )
    return rows


def _turnover(rows: list[dict]) -> list[float]:
    previous = {}
    values = []
    for row in rows:
        current = {name: 1 / len(row["names"]) for name in row["names"]}
        values.append(sum(max(current.get(name, 0) - previous.get(name, 0), 0) for name in set(current) | set(previous)))
        previous = current
    return values


def _summary(rows: list[dict]) -> dict:
    if not rows:
        zero_returns = {f"{bps}bps": 0.0 for bps in (5, 10, 25, 50)}
        return {"gross_return": 0.0, "average_period_return": 0.0, "periods": 0, "average_names": 0.0, "turnover_proxy": 0.0, "net_returns": zero_returns, "turnover_cost_returns": zero_returns.copy()}
    returns = np.array([row["return"] for row in rows])
    turnover = _turnover(rows)
    net_returns = {}
    turnover_cost_returns = {}
    for bps in (5, 10, 25, 50):
        # Conservative independent-holding approximation: full entry and exit each label period.
        net_returns[f"{bps}bps"] = float(np.prod(1 + returns - 2 * bps / 10_000) - 1)
        per_side_cost = bps / 10_000
        costs = [per_side_cost * value * (1 if index == 0 else 2) for index, value in enumerate(turnover)]
        costs[-1] += per_side_cost  # Liquidate the final long-only basket once.
        turnover_cost_returns[f"{bps}bps"] = float(np.prod(1 + returns - np.array(costs)) - 1)
    return {
        "gross_return": float(np.prod(1 + returns) - 1),
        "average_period_return": float(returns.mean()),
        "periods": len(rows),
        "average_names": float(np.mean([row["average_names"] for row in rows])),
        "turnover_proxy": float(np.mean(turnover)),
        "net_returns": net_returns,
        "turnover_cost_returns": turnover_cost_returns,
    }


def evaluate_low_volatility(bars: pd.DataFrame, formation_dates=None) -> dict:
    """Return a research report only; no files, orders, strategy, or model state are touched."""
    prepared = _prepared(bars)
    dates = formation_dates if formation_dates is not None else monthly_formation_dates(prepared)
    rows = _period_rows(prepared, dates)
    control_rows = [
        {"date": row["date"], "return": row["control_return"], "names": row["control_names"], "average_names": row["control_average_names"]}
        for row in rows
    ]
    windows = {}
    control_windows = {}
    for name, (start, end) in WINDOWS.items():
        windows[name] = _summary([row for row in rows if pd.Timestamp(start) <= row["date"] <= pd.Timestamp(end)])
        control_windows[name] = _summary([row for row in control_rows if pd.Timestamp(start) <= row["date"] <= pd.Timestamp(end)])
    return {
        "research_only": True,
        "outcome": "RESEARCH_ONLY_NO_GO: not a paid-GPU approval; cannot override raw-price/survivorship limitations.",
        "labels": LABELS,
        "limitations": LIMITATION,
        "method": "60-session raw close-to-close volatility; 60-session mean high-low range risk diagnostic; next-open to 21-session-ahead-open labels",
        "cost_method": "net_returns retain the conservative two-side cost on every independent label. turnover_cost_returns charge bps per traded side: initial basket entry, both sides of each actual one-way equal-weight rebalance, and final basket exit.",
        "summary": _summary(rows),
        "windows": windows,
        "matched_equal_weight_control": {"summary": _summary(control_rows), "windows": control_windows},
    }


def load_bars(database: Path) -> pd.DataFrame:
    """Read the fixed raw OHLCV universe without modifying the SQLite source."""
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        return pd.read_sql_query(
            "SELECT ticker, date, close, volume, open, high, low FROM sp500_ohlcv", connection
        )


def main():
    parser = argparse.ArgumentParser(description="Run the research-only raw-price low-volatility evaluator")
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("vesper/data/massive/sp500/sp500_ohlcv.sqlite"),
    )
    args = parser.parse_args()
    print(json.dumps(evaluate_low_volatility(load_bars(args.database)), indent=2))


if __name__ == "__main__":
    main()
