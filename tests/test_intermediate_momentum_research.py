import importlib.util
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "intermediate_momentum_research.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("intermediate_momentum_research", SCRIPT_PATH)
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


def test_formation_features_use_252_session_return_ending_21_sessions_before_formation():
    research = _load_module()
    dates = pd.bdate_range("2020-01-01", periods=274)
    closes = np.linspace(100, 200, 253).tolist() + [20] * 21

    features = research.formation_features(_bars("MOM", closes, dates), dates[-1])

    assert features.loc["MOM", "momentum_12_1"] == 1.0
    assert features.loc["MOM", "median_dollar_volume"] == 20_000.0


def test_select_top_momentum_quintile_applies_liquidity_screen_before_ranking():
    research = _load_module()
    features = pd.DataFrame(
        {
            "momentum_12_1": [0.99, 0.10, 0.20, 0.30, 0.40],
            "median_dollar_volume": [1, 100, 100, 100, 100],
        },
        index=["ILLQ", "A", "B", "C", "D"],
    )

    selected = research.select_intermediate_momentum(features)

    assert list(selected.index) == ["D"]


def test_holding_return_excludes_post_outcome_discontinuity_and_uses_opens():
    research = _load_module()
    dates = pd.bdate_range("2020-01-01", periods=24)
    clean = _bars("CLEAN", np.linspace(100, 123, len(dates)), dates)
    jumpy = _bars("JUMP", [100] * 3 + [130] + [131] * 20, dates)

    labels = research.holding_returns(pd.concat([clean, jumpy]), dates[0])

    expected = clean.loc[clean["date"] == dates[21], "open"].iloc[0] / clean.loc[
        clean["date"] == dates[1], "open"
    ].iloc[0] - 1
    assert labels.to_dict() == {"CLEAN": expected}


def test_evaluator_reports_required_windows_costs_control_and_no_paid_gpu_approval():
    research = _load_module()
    dates = pd.bdate_range("2020-01-01", periods=295)
    bars = pd.concat(
        [
            _bars(ticker, 100 * (1 + np.arange(len(dates)) * slope), dates, volume=100_000)
            for ticker, slope in zip("ABCDE", [0.0001, 0.0002, 0.0003, 0.0004, 0.0005])
        ]
    )

    report = research.evaluate_intermediate_momentum(bars, formation_dates=[dates[273]])

    assert report["research_only"] is True
    assert report["labels"] == ["fixed-502-universe", "raw-price", "survivorship-limited"]
    assert "post-outcome censoring" in report["limitations"]
    assert "META/FB" in report["limitations"]
    assert "no paid-GPU approval" in report["outcome"]
    assert "252-session close return ending 21 sessions before formation" in report["method"]
    assert set(report["windows"]) == {"development", "validation", "final_oos"}
    assert report["summary"]["periods"] == 1
    assert set(report["summary"]["net_returns"]) == {"5bps", "10bps", "25bps", "50bps"}
    assert set(report["summary"]["turnover_cost_returns"]) == {"5bps", "10bps", "25bps", "50bps"}
    assert report["matched_equal_weight_control"]["summary"]["average_names"] == 4


def test_load_bars_reads_total_return_adapter_and_attaches_validation_provenance(tmp_path):
    research = _load_module()
    database = tmp_path / "total_return_ohlcv_adapter_20260717T153500Z.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE ohlcv_data (ticker, timestamp, open, high, low, close, volume, timeframe)"
        )
        connection.execute(
            "INSERT INTO ohlcv_data VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("META", 1_704_067_200, 300.0, 303.0, 297.0, 301.0, 1_000, "1day"),
        )
        connection.execute(
            "INSERT INTO ohlcv_data VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("META", 1_704_153_600, 301.0, 304.0, 298.0, 302.0, 2_000, "1hour"),
        )

    bars = research.load_bars(database)
    report = research.evaluate_intermediate_momentum(bars, formation_dates=[])

    assert bars.to_dict("records") == [{
        "ticker": "META", "date": "2024-01-01", "close": 301.0, "volume": 1_000,
        "open": 300.0, "high": 303.0, "low": 297.0,
    }]
    assert report["provenance"] == {
        "price_basis": "total_return_adjusted",
        "universe": "31-name alias-normalized validation subset",
        "adapter_path": str(database),
        "snapshot_id": "20260717T153500Z",
        "snapshot_date": "2026-07-17",
    }
