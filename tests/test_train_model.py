from pathlib import Path

from scripts import train_model


def test_split_adjustment_paths_stay_inside_v20():
    assert train_model.SPLIT_ADJ_PATHS == [
        Path("vesper/data/massive/split_adjustments.json"),
    ]


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
