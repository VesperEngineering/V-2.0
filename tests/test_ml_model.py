import importlib.util
import json
from pathlib import Path

import numpy as np
import xgboost as xgb

from types import SimpleNamespace

from vesper.strategy.ml_model import MLModelStrategy
from vesper.strategy.base import Signal, SignalAction
from vesper.execution.broker import OrderSide, PaperBroker


ROOT = Path(__file__).resolve().parents[1]
TRAIN_MODULE_PATH = ROOT / "scripts" / "train_model.py"
BACKTEST_MODULE_PATH = ROOT / "scripts" / "run_backtest.py"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_train_module():
    return _load_module("train_model", TRAIN_MODULE_PATH)


def _load_backtest_module():
    return _load_module("run_backtest", BACKTEST_MODULE_PATH)


def _write_model(path):
    model = xgb.XGBRegressor(n_estimators=1, max_depth=1)
    model.fit(np.zeros((2, 24)), np.array([0.0, 1.0]))
    model.save_model(path)


def test_ml_model_exposes_feature_lookback(tmp_path):
    model_path = tmp_path / "ranker.json"
    _write_model(model_path)

    strategy = MLModelStrategy({"model_path": str(model_path)})

    assert strategy.lookback == 50


def test_training_metadata_records_artifact_and_evaluation(tmp_path):
    train_model = _load_train_module()
    model_path = tmp_path / "xgb_ranker.json"
    model_path.write_bytes(b"model-bytes")

    metadata_path = train_model.write_model_metadata(
        model_path,
        train_ic=0.04,
        test_ic=0.03,
        train_samples=100,
        test_samples=50,
    )

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["model_path"] == str(model_path)
    assert metadata["label_horizon"] == train_model.LABEL_HORIZON
    assert metadata["train_ic"] == 0.04
    assert metadata["out_of_sample_ic"] == 0.03
    assert metadata["train_samples"] == 100
    assert metadata["test_samples"] == 50
    assert metadata["model_parameters"]["n_estimators"] == 50
    assert metadata["model_parameters"]["max_depth"] == 2
    assert len(metadata["sha256"]) == 64


def test_rebalance_interval_converts_sessions_to_minutes():
    run_backtest = _load_backtest_module()

    assert run_backtest.rebalance_interval_minutes(1) == 1_440
    assert run_backtest.rebalance_interval_minutes(5) == 7_200
    assert run_backtest.rebalance_interval_minutes(10) == 14_400


def test_strategy_override_beats_config_name_only_when_explicit():
    run_backtest = _load_backtest_module()

    assert run_backtest.resolve_strategy_name("ml_model", None) == "ml_model"
    assert run_backtest.resolve_strategy_name("ml_model", "momentum") == "momentum"


def test_portfolio_rule_overrides_copy_only_requested_values():
    run_backtest = _load_backtest_module()

    params = run_backtest.apply_portfolio_overrides({"top_n": 10, "exit_rank": 50}, 5, 10)

    assert params == {"top_n": 5, "exit_rank": 10}


def test_paper_broker_rejects_insufficient_cash_without_logging_error(caplog):
    broker = PaperBroker(initial_cash=100)
    broker.update_prices({"AAPL": 200})

    order = broker.submit_order("AAPL", 1, OrderSide.BUY)

    assert order.status.name == "REJECTED"
    assert "Insufficient cash" in caplog.text


def test_execute_signals_refreshes_positions_between_same_day_buys():
    run_backtest = _load_backtest_module()
    broker = PaperBroker(initial_cash=1_000)
    broker.update_prices({"A": 100, "B": 100})

    class RecordingRisk:
        def __init__(self):
            self.position_counts = []

        def check_signal(self, signal, account, positions, price, daily_pnl):
            self.position_counts.append(len(positions))
            return SimpleNamespace(approved=True, adjusted_qty=1)

    risk = RecordingRisk()
    signals = [
        Signal("A", SignalAction.BUY, 1.0, "test"),
        Signal("B", SignalAction.BUY, 1.0, "test"),
    ]

    run_backtest.execute_signals(broker, risk, signals, {"A": 100, "B": 100}, 0.0)

    assert risk.position_counts == [0, 1]
    assert len(broker.get_positions()) == 2
