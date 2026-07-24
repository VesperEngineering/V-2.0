import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "low_vol_research.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("low_vol_research", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bars(ticker, closes, dates, volume=1_000):
    close = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {
            "ticker": ticker,
            "date": dates,
            "close": close,
            "volume": volume,
            "open": close * 1.001,
            "high": close * 1.01,
            "low": close * 0.99,
        }
    )


def test_feature_window_excludes_large_raw_price_discontinuity():
    research = _load_module()
    dates = pd.bdate_range("2020-01-01", periods=61)
    clean = _bars("CLEAN", np.linspace(100, 106, len(dates)), dates)
    jumpy = _bars("JUMP", [100] * 30 + [130] + [131] * 30, dates)

    features = research.formation_features(pd.concat([clean, jumpy]), dates[-1])

    assert list(features.index) == ["CLEAN"]
    assert features.loc["CLEAN", "realized_volatility"] > 0
    assert "range_risk" in features.columns


def test_select_low_volatility_quintile_applies_liquidity_screen_before_ranking():
    research = _load_module()
    features = pd.DataFrame(
        {
            "realized_volatility": [0.001, 0.002, 0.003, 0.004, 0.005],
            "median_dollar_volume": [1, 100, 100, 100, 100],
        },
        index=["ILLQ", "A", "B", "C", "D"],
    )

    selected = research.select_low_volatility(features)

    assert list(selected.index) == ["A"]


def test_select_low_risk_quintile_combines_volatility_and_range_risk():
    research = _load_module()
    features = pd.DataFrame(
        {
            "realized_volatility": [0.001, 0.002, 0.003, 0.004, 0.005],
            "range_risk": [0.10, 0.001, 0.002, 0.003, 0.004],
            "median_dollar_volume": [100] * 5,
        },
        index=["LOW_VOL_WIDE_RANGE", "LOW_RANGE", "C", "D", "E"],
    )

    selected = research.select_low_volatility(features)

    assert list(selected.index) == ["LOW_RANGE"]


def test_holding_return_excludes_post_outcome_discontinuity_and_uses_opens():
    research = _load_module()
    dates = pd.bdate_range("2020-01-01", periods=24)
    clean = _bars("CLEAN", np.linspace(100, 123, len(dates)), dates)
    jumpy = _bars("JUMP", [100] * 3 + [130] + [131] * 20, dates)
    bars = pd.concat([clean, jumpy])

    labels = research.holding_returns(bars, dates[0])

    expected = clean.loc[clean["date"] == dates[21], "open"].iloc[0] / clean.loc[
        clean["date"] == dates[1], "open"
    ].iloc[0] - 1
    assert labels.to_dict() == {"CLEAN": expected}


def test_evaluator_reports_research_labels_costs_and_actual_turnover():
    research = _load_module()
    dates = pd.bdate_range("2020-01-01", periods=90)
    frames = []
    for ticker, scale in zip("ABCDE", [1.0, 1.01, 1.02, 1.03, 1.04]):
        closes = 100 * scale * (1 + np.arange(len(dates)) * 0.001)
        frames.append(_bars(ticker, closes, dates, volume=100_000))
    bars = pd.concat(frames)

    report = research.evaluate_low_volatility(bars, formation_dates=[dates[60], dates[65]])

    assert report["research_only"] is True
    assert report["labels"] == ["fixed-502-universe", "raw-price", "survivorship-limited"]
    assert "post-outcome censoring" in report["limitations"]
    assert report["summary"]["periods"] == 2
    assert report["summary"]["turnover_proxy"] == 0.5
    assert set(report["summary"]["net_returns"]) == {"5bps", "10bps", "25bps", "50bps"}


def test_summary_keeps_conservative_costs_and_adds_per_side_turnover_costs():
    research = _load_module()
    rows = [
        {"return": 0.10, "names": ["A", "B"], "average_names": 2},
        {"return": 0.10, "names": ["B", "C"], "average_names": 2},
    ]

    summary = research._summary(rows)

    assert summary["net_returns"]["5bps"] == (1.10 - 0.001) ** 2 - 1
    assert summary["turnover_proxy"] == 0.75
    assert summary["turnover_cost_returns"]["5bps"] == (1.10 - 0.0005) * (1.10 - 0.001) - 1


def test_evaluator_reports_matched_equal_weight_control_from_liquid_censored_universe():
    research = _load_module()
    dates = pd.bdate_range("2020-01-01", periods=90)
    frames = []
    for ticker, future_step in zip("ABCDE", [0.001, 0.002, 0.003, 0.004, 0.005]):
        closes = 100 * (1 + np.arange(len(dates)) * 0.001)
        closes[61:] *= 1 + np.arange(1, len(dates) - 60) * future_step
        frames.append(_bars(ticker, closes, dates, volume=100_000))
    bars = pd.concat(frames)

    report = research.evaluate_low_volatility(bars, formation_dates=[dates[60]])
    labels = research.holding_returns(bars, dates[60])
    features = research.formation_features(bars, dates[60])
    liquid = features.sort_values("median_dollar_volume", ascending=False).head(4)
    expected_control = labels.loc[liquid.index.intersection(labels.index)].mean()

    control = report["matched_equal_weight_control"]
    assert control["summary"]["periods"] == report["summary"]["periods"] == 1
    assert control["summary"]["average_names"] == 4
    assert np.isclose(control["summary"]["gross_return"], expected_control)


def test_evaluator_outcome_cannot_approve_paid_gpu_or_override_data_limitations():
    research = _load_module()
    dates = pd.bdate_range("2020-01-01", periods=90)
    bars = pd.concat([_bars(ticker, np.linspace(100, 110, len(dates)), dates) for ticker in "ABCDE"])

    report = research.evaluate_low_volatility(bars, formation_dates=[dates[60]])

    assert report["outcome"] == (
        "RESEARCH_ONLY_NO_GO: not a paid-GPU approval; cannot override raw-price/survivorship limitations."
    )
