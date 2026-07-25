from dataclasses import FrozenInstanceError, asdict
from datetime import datetime
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xgboost as xgb

from vesper.data.features import FEATURE_COLS
from vesper.strategy.base import SignalAction
from vesper.strategy.forecast import ForecastRecord
from vesper.strategy.ml_model import MLModelStrategy


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
TARGET_DEFINITION = "cross_sectional_5_session_forward_return_rank"


def test_forecast_record_is_a_frozen_closed_shadow_contract():
    as_of = datetime(2026, 7, 24, 16, 0)
    valid_until = datetime(2026, 7, 31, 16, 0)

    record = ForecastRecord(
        symbol="AAPL",
        as_of_timestamp=as_of,
        horizon_sessions=5,
        target_definition=TARGET_DEFINITION,
        standardized_score=1.25,
        rank=1,
        model_artifact_path="models/xgb_ranker.json",
        model_artifact_sha256=SHA_A,
        dataset_identity_sha256=SHA_B,
        adjustment_identity_sha256=SHA_C,
        feature_identity_sha256=SHA_D,
        expert_version="xgb-2026.07.24",
        feature_version="features-v1",
        run_manifest_sha256=SHA_E,
        valid_until_timestamp=valid_until,
        data_freshness_status="current",
    )

    assert record.symbol == "AAPL"
    assert record.as_of_timestamp == as_of
    assert record.horizon_sessions == 5
    assert record.target_definition == TARGET_DEFINITION
    assert record.standardized_score == 1.25
    assert record.rank == 1
    assert record.schema_version == "1"
    assert record.expert_id == "xgb_ranker"
    assert record.expert_version == "xgb-2026.07.24"
    assert record.feature_version == "features-v1"
    assert record.run_manifest_sha256 == SHA_E
    assert record.score_units == "cross_sectional_zscore"
    assert record.direction == "higher_is_better"
    assert record.valid_until_timestamp == valid_until
    assert record.data_freshness_status == "current"
    assert record.research_only is True
    assert record.execution_authority is False
    assert record.authority_state == "shadow"
    assert not hasattr(record, "__dict__")
    with pytest.raises(FrozenInstanceError):
        record.rank = 2
    with pytest.raises(TypeError):
        ForecastRecord(**{**asdict(record), "unexpected": True})


def _valid_record_kwargs():
    return {
        "symbol": "AAPL",
        "as_of_timestamp": datetime(2026, 7, 24, 16, 0),
        "horizon_sessions": 5,
        "target_definition": TARGET_DEFINITION,
        "standardized_score": 0.0,
        "rank": 1,
        "model_artifact_path": "models/xgb_ranker.json",
        "model_artifact_sha256": SHA_A,
        "dataset_identity_sha256": SHA_B,
        "adjustment_identity_sha256": SHA_C,
        "feature_identity_sha256": SHA_D,
        "expert_version": "xgb-2026.07.24",
        "feature_version": "features-v1",
        "run_manifest_sha256": SHA_E,
        "valid_until_timestamp": datetime(2026, 7, 31, 16, 0),
        "data_freshness_status": "current",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model_artifact_sha256", ""),
        ("dataset_identity_sha256", "a" * 63),
        ("adjustment_identity_sha256", "g" * 64),
        ("feature_identity_sha256", " " * 64),
        ("run_manifest_sha256", "e" * 63),
    ],
)
def test_forecast_record_rejects_invalid_provenance(field, value):
    kwargs = _valid_record_kwargs()
    kwargs[field] = value

    with pytest.raises(ValueError, match=field):
        ForecastRecord(**kwargs)


@pytest.mark.parametrize("score", [float("nan"), float("inf"), float("-inf")])
def test_forecast_record_rejects_nonfinite_scores(score):
    kwargs = _valid_record_kwargs()
    kwargs["standardized_score"] = score

    with pytest.raises(ValueError, match="standardized_score"):
        ForecastRecord(**kwargs)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("symbol", " "),
        ("model_artifact_path", ""),
        ("horizon_sessions", 4),
        ("rank", 0),
        ("schema_version", "2"),
        ("expert_id", "other_expert"),
        ("expert_version", " "),
        ("feature_version", ""),
        ("target_definition", "next_close_return"),
        ("score_units", "raw_return"),
        ("direction", "lower_is_better"),
        ("data_freshness_status", "stale"),
        ("research_only", False),
        ("execution_authority", True),
        ("authority_state", "active"),
    ],
)
def test_forecast_record_rejects_authority_or_schema_invariant_changes(field, value):
    kwargs = _valid_record_kwargs()
    kwargs[field] = value

    with pytest.raises(ValueError, match=field):
        ForecastRecord(**kwargs)


@pytest.mark.parametrize("field", ["as_of_timestamp", "valid_until_timestamp"])
def test_forecast_record_rejects_non_datetime_timestamps(field):
    kwargs = _valid_record_kwargs()
    kwargs[field] = "2026-07-24"

    with pytest.raises(ValueError, match=field):
        ForecastRecord(**kwargs)


def test_forecast_record_rejects_valid_until_before_as_of():
    kwargs = _valid_record_kwargs()
    kwargs["valid_until_timestamp"] = datetime(2026, 7, 23, 16, 0)

    with pytest.raises(ValueError, match="valid_until_timestamp"):
        ForecastRecord(**kwargs)


def test_forecast_record_requires_valid_until_timestamp():
    kwargs = _valid_record_kwargs()
    del kwargs["valid_until_timestamp"]

    with pytest.raises(TypeError, match="valid_until_timestamp"):
        ForecastRecord(**kwargs)


def _write_model(path: Path):
    model = xgb.XGBRegressor(n_estimators=1, max_depth=1)
    model.fit(np.zeros((2, len(FEATURE_COLS))), np.array([0.0, 1.0]))
    model.save_model(path)


def _canonical_sha256(value):
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_compatibility_manifest(
    model_path: Path,
    *,
    approved_universe=("A", "AAA", "AAPL", "B", "C", "MSFT", "ZZZ"),
    feature_cols=FEATURE_COLS,
    label_horizon=5,
    model_artifact_sha256=None,
):
    feature_cols = list(feature_cols)
    approved_universe = list(approved_universe)
    manifest = {
        "schema_version": "1",
        "model_artifact_sha256": model_artifact_sha256
        or hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "label_horizon": label_horizon,
        "target_definition": TARGET_DEFINITION,
        "feature_cols": feature_cols,
        "feature_identity_sha256": _canonical_sha256(feature_cols),
        "approved_universe": approved_universe,
        "universe_identity_sha256": _canonical_sha256(approved_universe),
    }
    compatibility_path = model_path.with_suffix(".compatibility.json")
    compatibility_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return compatibility_path


class _FirstFeatureModel:
    def predict(self, values):
        return np.array([float(values[0, 0])])


def _fake_compute_features(frame):
    value = frame.attrs["feature_value"]
    return pd.DataFrame(
        {column: [value] for column in FEATURE_COLS},
        index=[frame.index[-1]],
    )


def _market_data(as_of, values):
    data = {}
    for symbol, value in values:
        frame = pd.DataFrame({"close": [100.0]}, index=[pd.Timestamp(as_of.date())])
        frame.attrs["feature_value"] = value
        data[symbol] = frame
    return data


def _strategy(model_path):
    _write_model(model_path)
    _write_compatibility_manifest(model_path)
    strategy = MLModelStrategy(
        {
            "model_path": str(model_path),
            "top_n": 2,
            "exit_rank": 2,
            "entry_threshold": -10.0,
            "rebalance_interval": 0,
        }
    )
    strategy.model = _FirstFeatureModel()
    return strategy


def _forecast_kwargs():
    return {
        "valid_until_timestamp": datetime(2026, 7, 31, 16, 0),
        "dataset_identity_sha256": SHA_B,
        "adjustment_identity_sha256": SHA_C,
        "expert_version": "xgb-2026.07.24",
        "feature_version": "features-v1",
        "run_manifest_sha256": SHA_E,
    }


def test_generate_signals_exact_behavior_is_preserved_during_score_factorization(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("vesper.strategy.ml_model.compute_features", _fake_compute_features)
    as_of = datetime(2026, 7, 24, 16, 0)
    strategy = _strategy(tmp_path / "ranker.json")
    data = _market_data(as_of, [("B", 2.0), ("C", 1.0), ("A", 3.0)])

    signals = strategy.generate_signals(data, {"C": object()}, as_of)

    assert [
        (
            signal.symbol,
            signal.action,
            signal.strength,
            signal.reason,
            signal.timestamp,
            signal.metadata,
        )
        for signal in signals
    ] == [
        (
            "C",
            SignalAction.CLOSE,
            1.0,
            "model rank #3 fell outside top 2",
            as_of,
            {"predicted_return": -1.0, "rank": 3},
        ),
        (
            "A",
            SignalAction.BUY,
            1.0,
            "model rank #1, predicted 5d return 1.0000",
            as_of,
            {"predicted_return": 1.0, "rank": 1},
        ),
        (
            "B",
            SignalAction.BUY,
            1.0 - 1 / 3,
            "model rank #2, predicted 5d return 0.0000",
            as_of,
            {"predicted_return": 0.0, "rank": 2},
        ),
    ]


def test_generate_shadow_forecasts_returns_inert_provenance_complete_records(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("vesper.strategy.ml_model.compute_features", _fake_compute_features)
    as_of = datetime(2026, 7, 24, 16, 0)
    model_path = tmp_path / "ranker.json"
    strategy = _strategy(model_path)
    data = _market_data(as_of, [("ZZZ", 1.0), ("AAA", 1.0)])
    last_rebalance = datetime(2026, 7, 23, 16, 0)
    strategy._last_rebalance = last_rebalance
    monkeypatch.setattr(
        "vesper.strategy.ml_model.Signal",
        lambda *args, **kwargs: pytest.fail("shadow forecast constructed a signal"),
    )
    files_before = set(tmp_path.iterdir())

    records = strategy.generate_shadow_forecasts(
        data,
        as_of,
        valid_until_timestamp=datetime(2026, 7, 31, 16, 0),
        dataset_identity_sha256=SHA_B,
        adjustment_identity_sha256=SHA_C,
        expert_version="xgb-2026.07.24",
        feature_version="features-v1",
        run_manifest_sha256=SHA_E,
    )

    assert [(record.symbol, record.rank) for record in records] == [
        ("AAA", 1),
        ("ZZZ", 2),
    ]
    assert all(record.standardized_score == 0.0 for record in records)
    assert all(record.horizon_sessions == 5 for record in records)
    assert all(record.target_definition == TARGET_DEFINITION for record in records)
    assert all(record.as_of_timestamp == as_of for record in records)
    assert all(
        record.valid_until_timestamp == datetime(2026, 7, 31, 16, 0)
        for record in records
    )
    assert all(record.data_freshness_status == "current" for record in records)
    assert all(record.research_only is True for record in records)
    assert all(record.execution_authority is False for record in records)
    assert all(record.authority_state == "shadow" for record in records)
    assert all(record.model_artifact_path == str(model_path) for record in records)
    expected_model_sha = hashlib.sha256(model_path.read_bytes()).hexdigest()
    assert all(record.model_artifact_sha256 == expected_model_sha for record in records)
    assert all(record.dataset_identity_sha256 == SHA_B for record in records)
    assert all(record.adjustment_identity_sha256 == SHA_C for record in records)
    expected_feature_sha = _canonical_sha256(FEATURE_COLS)
    assert all(record.feature_identity_sha256 == expected_feature_sha for record in records)
    assert all(record.schema_version == "1" for record in records)
    assert all(record.expert_id == "xgb_ranker" for record in records)
    assert all(record.expert_version == "xgb-2026.07.24" for record in records)
    assert all(record.feature_version == "features-v1" for record in records)
    assert all(record.run_manifest_sha256 == SHA_E for record in records)
    assert all(record.score_units == "cross_sectional_zscore" for record in records)
    assert all(record.direction == "higher_is_better" for record in records)
    assert all(isinstance(record, ForecastRecord) for record in records)
    assert all(
        not hasattr(record, field)
        for record in records
        for field in ("action", "quantity", "order_id")
    )
    assert strategy._last_rebalance == last_rebalance
    assert set(tmp_path.iterdir()) == files_before


@pytest.mark.parametrize(
    "missing_field",
    [
        "valid_until_timestamp",
        "dataset_identity_sha256",
        "adjustment_identity_sha256",
        "expert_version",
        "feature_version",
        "run_manifest_sha256",
    ],
)
def test_generate_shadow_forecasts_requires_per_run_contract_bindings(
    missing_field, tmp_path, monkeypatch
):
    monkeypatch.setattr("vesper.strategy.ml_model.compute_features", _fake_compute_features)
    as_of = datetime(2026, 7, 24, 16, 0)
    strategy = _strategy(tmp_path / "ranker.json")
    kwargs = _forecast_kwargs()
    del kwargs[missing_field]

    with pytest.raises(TypeError, match=missing_field):
        strategy.generate_shadow_forecasts(
            _market_data(as_of, [("AAPL", 1.0)]),
            as_of,
            **kwargs,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("approved_universe", {"ARBITRARY_BUT_CALLER_APPROVED"}),
        ("expected_feature_identity_sha256", "9" * 64),
        ("feature_identity_sha256", "9" * 64),
    ],
)
def test_generate_shadow_forecasts_rejects_per_call_compatibility_overrides(
    field, value, tmp_path
):
    as_of = datetime(2026, 7, 24, 16, 0)
    strategy = _strategy(tmp_path / "ranker.json")

    with pytest.raises(TypeError, match=field):
        strategy.generate_shadow_forecasts(
            _market_data(as_of, [("AAPL", 1.0)]),
            as_of,
            **_forecast_kwargs(),
            **{field: value},
        )


def test_generate_shadow_forecasts_rejects_string_as_of_before_scoring(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("vesper.strategy.ml_model.compute_features", _fake_compute_features)
    market_as_of = datetime(2026, 7, 24, 16, 0)
    strategy = _strategy(tmp_path / "ranker.json")
    monkeypatch.setattr(
        strategy,
        "_score_universe",
        lambda data: pytest.fail("invalid timestamp reached model scoring"),
    )

    with pytest.raises(ValueError, match="as_of_timestamp"):
        strategy.generate_shadow_forecasts(
            _market_data(market_as_of, [("AAPL", 1.0)]),
            "2026-07-24",
            **_forecast_kwargs(),
        )


def test_generate_shadow_forecasts_rejects_symbols_outside_manifest_universe(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("vesper.strategy.ml_model.compute_features", _fake_compute_features)
    as_of = datetime(2026, 7, 24, 16, 0)
    strategy = _strategy(tmp_path / "ranker.json")
    monkeypatch.setattr(
        strategy,
        "_score_universe",
        lambda data: pytest.fail("unknown symbol reached model scoring"),
    )

    with pytest.raises(ValueError, match="NOT_IN_DECLARED_UNIVERSE"):
        strategy.generate_shadow_forecasts(
            _market_data(
                as_of,
                [("AAPL", 1.0), ("NOT_IN_DECLARED_UNIVERSE", 2.0)],
            ),
            as_of,
            **_forecast_kwargs(),
        )


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("model_artifact_sha256", SHA_A, "model_artifact_sha256"),
        ("feature_identity_sha256", SHA_A, "feature_identity_sha256"),
        ("feature_cols", [*FEATURE_COLS[:-1], "tampered"], "feature_cols"),
        ("label_horizon", 4, "label_horizon"),
        ("universe_identity_sha256", SHA_A, "universe_identity_sha256"),
    ],
)
def test_generate_shadow_forecasts_rejects_tampered_compatibility_manifest(
    field, value, error, tmp_path, monkeypatch
):
    monkeypatch.setattr("vesper.strategy.ml_model.compute_features", _fake_compute_features)
    as_of = datetime(2026, 7, 24, 16, 0)
    strategy = _strategy(tmp_path / "ranker.json")
    manifest = json.loads(strategy.compatibility_path.read_text(encoding="utf-8"))
    manifest[field] = value
    strategy.compatibility_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(
        strategy,
        "_score_universe",
        lambda data: pytest.fail("tampered manifest reached model scoring"),
    )

    with pytest.raises(ValueError, match=error):
        strategy.generate_shadow_forecasts(
            _market_data(as_of, [("AAPL", 1.0)]),
            as_of,
            **_forecast_kwargs(),
        )


def test_generate_shadow_forecasts_rejects_stale_or_mismatched_as_of_data(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("vesper.strategy.ml_model.compute_features", _fake_compute_features)
    as_of = datetime(2026, 7, 24, 16, 0)
    strategy = _strategy(tmp_path / "ranker.json")
    data = _market_data(as_of, [("AAPL", 1.0), ("MSFT", 2.0)])
    data["MSFT"].index = pd.DatetimeIndex([pd.Timestamp("2026-07-23")])

    with pytest.raises(ValueError, match="MSFT.*as-of"):
        strategy.generate_shadow_forecasts(
            data,
            as_of,
            **_forecast_kwargs(),
        )


def test_generate_shadow_forecasts_rejects_nonfinite_model_scores(tmp_path, monkeypatch):
    monkeypatch.setattr("vesper.strategy.ml_model.compute_features", _fake_compute_features)
    as_of = datetime(2026, 7, 24, 16, 0)
    strategy = _strategy(tmp_path / "ranker.json")
    strategy.model.predict = lambda values: np.array([float("inf")])

    with pytest.raises(ValueError, match="non-finite model score"):
        strategy.generate_shadow_forecasts(
            _market_data(as_of, [("AAPL", 1.0)]),
            as_of,
            **_forecast_kwargs(),
        )


def test_generate_shadow_forecasts_standardizes_cross_sectional_model_scores(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("vesper.strategy.ml_model.compute_features", _fake_compute_features)
    as_of = datetime(2026, 7, 24, 16, 0)
    strategy = _strategy(tmp_path / "ranker.json")

    records = strategy.generate_shadow_forecasts(
        _market_data(as_of, [("C", 1.0), ("A", 3.0), ("B", 2.0)]),
        as_of,
        **_forecast_kwargs(),
    )

    assert [record.symbol for record in records] == ["A", "B", "C"]
    assert [record.standardized_score for record in records] == pytest.approx(
        [1.0, 0.0, -1.0]
    )


def test_current_champion_compatibility_manifest_matches_reviewed_sources():
    root = Path(__file__).resolve().parents[1]
    model_path = root / "models" / "xgb_ranker.json"
    manifest = json.loads(
        (root / "models" / "xgb_ranker.compatibility.json").read_text(encoding="utf-8")
    )
    universe = [
        line.removeprefix("  - ").strip()
        for line in (root / "config" / "universe.yaml").read_text(encoding="utf-8").splitlines()
        if line.startswith("  - ")
    ]

    assert manifest["model_artifact_sha256"] == hashlib.sha256(
        model_path.read_bytes()
    ).hexdigest()
    assert manifest["feature_cols"] == FEATURE_COLS
    assert manifest["feature_identity_sha256"] == _canonical_sha256(FEATURE_COLS)
    assert manifest["approved_universe"] == universe
    assert manifest["universe_identity_sha256"] == _canonical_sha256(universe)
