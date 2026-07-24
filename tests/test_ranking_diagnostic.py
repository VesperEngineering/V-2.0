import importlib.util
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTIC_PATH = ROOT / "scripts" / "ranking_diagnostic.py"


def _load_diagnostic_module():
    spec = importlib.util.spec_from_file_location("ranking_diagnostic", DIAGNOSTIC_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
