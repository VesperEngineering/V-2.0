import sys
from pathlib import Path

import pandas as pd
import pytest

from scripts import train_model


def test_split_adjustment_path_stays_inside_v20():
    assert train_model.SPLIT_ADJUSTMENTS_PATH == Path(
        "vesper/data/massive/split_adjustments.json"
    )


def test_training_stops_before_features_when_split_adjustments_are_missing(
    monkeypatch, tmp_path
):
    database_path = tmp_path / "sp500_ohlcv.sqlite"
    database_path.touch()
    monkeypatch.setattr(train_model, "SP500_DB", database_path)
    monkeypatch.setattr(train_model, "MODEL_PATH", tmp_path / "model.json")
    monkeypatch.setattr(
        train_model,
        "SPLIT_ADJUSTMENTS_PATH",
        tmp_path / "missing-split-adjustments.json",
    )
    monkeypatch.setattr(train_model, "load_bars", lambda connection: {"AAA": object()})
    monkeypatch.setattr(
        train_model,
        "build_training_set",
        lambda bars: pytest.fail("features must not run without split adjustments"),
    )
    monkeypatch.setattr(sys, "argv", ["train_model.py"])

    with pytest.raises(FileNotFoundError, match="Split adjustments not found"):
        train_model.main()


def test_training_applies_split_adjustments_before_features(monkeypatch, tmp_path):
    database_path = tmp_path / "sp500_ohlcv.sqlite"
    database_path.touch()
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

    monkeypatch.setattr(train_model, "SP500_DB", database_path)
    monkeypatch.setattr(train_model, "MODEL_PATH", tmp_path / "model.json")
    monkeypatch.setattr(train_model, "load_bars", lambda connection: bars)
    monkeypatch.setattr(
        train_model,
        "load_split_adjustments",
        lambda *args, **kwargs: {"AAA": {"2024-01-02": 0.5}},
    )

    def capture_features(data):
        captured["close"] = data["AAA"]["close"].iloc[0]
        raise RuntimeError("stop after adjustment")

    monkeypatch.setattr(train_model, "build_training_set", capture_features)
    monkeypatch.setattr(sys, "argv", ["train_model.py"])

    with pytest.raises(RuntimeError, match="stop after adjustment"):
        train_model.main()

    assert captured["close"] == 52.5


def test_metadata_serializes_active_model_parameters(tmp_path):
    model_path = tmp_path / "xgb_ranker.json"
    model_path.write_bytes(b"candidate")

    metadata_path = train_model.write_model_metadata(
        model_path,
        train_ic=0.01,
        test_ic=0.02,
        train_samples=10,
        test_samples=5,
    )

    metadata = __import__("json").loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["model_parameters"] == {
        "n_estimators": 50,
        "max_depth": 2,
        "learning_rate": 0.05,
        "subsample": 0.6,
        "colsample_bytree": 0.6,
        "reg_alpha": 5.0,
        "reg_lambda": 20.0,
        "objective": "reg:squarederror",
        "n_jobs": -1,
        "random_state": 42,
    }
