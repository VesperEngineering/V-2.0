import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTIC_PATH = ROOT / "scripts" / "ranking_diagnostic.py"


def _load_diagnostic_module():
    spec = importlib.util.spec_from_file_location("ranking_diagnostic", DIAGNOSTIC_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_diagnostic_stops_before_data_when_split_adjustments_are_missing(
    monkeypatch, tmp_path
):
    diagnostic = _load_diagnostic_module()
    monkeypatch.setattr(
        diagnostic,
        "SPLIT_ADJUSTMENTS_PATH",
        tmp_path / "missing-split-adjustments.json",
    )
    monkeypatch.setattr(
        diagnostic,
        "create_feed",
        lambda config: pytest.fail("data must not load without split adjustments"),
    )
    monkeypatch.setattr(sys, "argv", ["ranking_diagnostic.py"])

    with pytest.raises(FileNotFoundError, match="Split adjustments not found"):
        diagnostic.main()


def test_diagnostic_applies_split_adjustments_before_evaluation(monkeypatch, tmp_path):
    diagnostic = _load_diagnostic_module()
    index = pd.to_datetime(["2024-01-02"])
    bars = {
        "AAA": pd.DataFrame(
            {
                "open": [100.0],
                "high": [110.0],
                "low": [90.0],
                "close": [105.0],
                "volume": [1000],
            },
            index=index,
        )
    }
    captured = {}

    class FakeModel:
        def load_model(self, path):
            pass

    class FakeFeed:
        def get_bars(self, universe, start, end):
            return bars

    monkeypatch.setattr(diagnostic.xgb, "XGBRegressor", FakeModel)
    monkeypatch.setattr(diagnostic, "create_feed", lambda config: FakeFeed())
    monkeypatch.setattr(
        diagnostic,
        "load_split_adjustments",
        lambda *args, **kwargs: {"AAA": {"2024-01-02": 0.5}},
    )

    def capture_run(*, data, model, basket_size):
        captured["close"] = data["AAA"]["close"].iloc[0]
        return {"ml_model": {}, "momentum": {}}

    monkeypatch.setattr(diagnostic, "run_diagnostic", capture_run)
    monkeypatch.setattr(
        sys,
        "argv",
        ["ranking_diagnostic.py", "--report-path", str(tmp_path / "report.json")],
    )

    diagnostic.main()

    assert captured["close"] == 52.5


def test_rank_metrics_reports_positive_spread_and_perfect_rank_ic():
    diagnostic = _load_diagnostic_module()
    scores = pd.Series({"A": 3.0, "B": 2.0, "C": 1.0, "D": 0.0})
    forward_returns = pd.Series({"A": 0.04, "B": 0.02, "C": -0.01, "D": -0.03})

    metrics = diagnostic.rank_metrics(scores, forward_returns, basket_size=2)

    assert metrics["coverage"] == 4
    assert metrics["top_mean_return"] == 0.03
    assert metrics["bottom_mean_return"] == -0.02
    assert metrics["top_bottom_spread"] == 0.05
    assert metrics["rank_ic"] == 1.0
