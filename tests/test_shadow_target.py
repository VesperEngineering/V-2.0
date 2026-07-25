from dataclasses import FrozenInstanceError, asdict, replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from vesper.portfolio.shadow_target import (
    ShadowTargetLine,
    build_shadow_portfolio_target,
)
from vesper.strategy.forecast import ForecastRecord


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
SHA_E = "e" * 64
SHA_F = "f" * 64
AS_OF = datetime(2026, 7, 24, 16, 0)
VALID_UNTIL = datetime(2026, 7, 31, 16, 0)


def _forecast(symbol, raw_score, standardized_score, rank, **overrides):
    values = {
        "symbol": symbol,
        "as_of_timestamp": AS_OF,
        "valid_until_timestamp": VALID_UNTIL,
        "horizon_sessions": 5,
        "raw_model_score": raw_score,
        "standardized_score": standardized_score,
        "rank": rank,
        "model_artifact_path": "models/xgb_ranker.json",
        "model_artifact_sha256": SHA_A,
        "dataset_identity_sha256": SHA_B,
        "adjustment_identity_sha256": SHA_C,
        "feature_identity_sha256": SHA_D,
        "universe_identity_sha256": SHA_F,
        "expert_version": "xgb-2026.07.24",
        "feature_version": "features-v1",
        "run_manifest_sha256": SHA_E,
    }
    values.update(overrides)
    return ForecastRecord(**values)


def _build(forecasts, **overrides):
    values = {
        "forecasts": forecasts,
        "as_of_timestamp": AS_OF,
        "valid_until_timestamp": VALID_UNTIL,
        "current_holdings_weights": {"A": 0.25},
        "portfolio_value": 1_000.0,
        "classification_identity_sha256": "1" * 64,
        "target_generation_version": "shadow-top-n-equal-weight-v1",
        "top_n": 2,
        "entry_threshold": 0.0,
        "transaction_cost_rate": None,
    }
    values.update(overrides)
    return build_shadow_portfolio_target(**values)


def _base_forecasts():
    return (
        _forecast("C", -0.1, -1.0, 4),
        _forecast("A", 0.8, 1.2, 1),
        _forecast("D", 0.2, 0.0, 3),
        _forecast("B", 0.5, 0.7, 2),
    )


def test_build_shadow_target_is_closed_inert_and_binds_authority_content():
    target = _build(_base_forecasts())

    assert [line.symbol for line in target.lines] == ["A", "B", "C", "D"]
    assert [line.target_weight for line in target.lines] == [0.5, 0.5, 0.0, 0.0]
    assert [line.target_notional for line in target.lines] == [500.0, 500.0, 0.0, 0.0]
    assert [line.reason for line in target.lines] == [
        "selected_top_n",
        "selected_top_n",
        "below_or_equal_entry_threshold",
        "outside_top_n",
    ]
    assert target.current_holdings_weights == (("A", 0.25),)
    assert target.current_cash_weight == 0.75
    assert len(target.holdings_snapshot_sha256) == 64
    assert len(target.cash_snapshot_sha256) == 64
    assert target.transaction_cost_rate is None
    assert target.transaction_cost_assumption == (("transaction_cost_rate", None),)
    assert len(target.transaction_cost_assumption_sha256) == 64
    assert target.universe_identity_sha256 == SHA_F
    assert target.long_only is True
    assert target.equal_weight is True
    assert len(target.constraint_identity_sha256) == 64
    assert target.turnover == pytest.approx(0.75)
    assert target.gross_exposure == 1.0
    assert target.net_exposure == 1.0
    assert target.concentration == 0.5
    assert target.selected_count == 2
    assert target.blocked is False
    assert target.infeasible is False
    assert target.diagnostic_reason is None
    assert target.research_only is True
    assert target.authority_state == "shadow"
    assert target.execution_authority is False
    assert target.risk_authority is False
    assert target.broker_authority is False
    assert target.persistence_authority is False
    assert not hasattr(target, "__dict__")
    assert all(not hasattr(line, "__dict__") for line in target.lines)
    for forbidden in ("action", "quantity", "order_id", "delta"):
        assert not hasattr(target, forbidden)
        assert all(not hasattr(line, forbidden) for line in target.lines)
    with pytest.raises(FrozenInstanceError):
        target.selected_count = 3
    with pytest.raises(TypeError):
        type(target)(**{**asdict(target), "unexpected": True})


def test_threshold_is_strict_and_ties_are_deterministic_by_symbol():
    target = _build(
        (
            _forecast("B", 0.5, 0.0, 1),
            _forecast("C", 0.5, 0.0, 2),
            _forecast("A", 0.25, -1.0, 3),
        ),
        entry_threshold=0.25,
        top_n=1,
    )

    assert [(line.symbol, line.target_weight, line.reason) for line in target.lines] == [
        ("A", 0.0, "below_or_equal_entry_threshold"),
        ("B", 1.0, "selected_top_n"),
        ("C", 0.0, "outside_top_n"),
    ]


def test_forecast_order_and_numeric_representation_do_not_change_canonical_hash():
    integer_values = (
        _forecast("A", 1, 1, 1),
        _forecast("B", 0, 0, 2),
    )
    float_values = tuple(
        _forecast(
            item.symbol,
            float(item.raw_model_score),
            float(item.standardized_score),
            item.rank,
        )
        for item in reversed(integer_values)
    )

    first = _build(integer_values)
    second = _build(float_values)

    assert first.eligible_forecast_set_sha256 == second.eligible_forecast_set_sha256


def test_common_forecast_universe_identity_is_required_and_not_caller_authorized():
    forecasts = (
        _forecast("A", 0.8, 1.0, 1),
        _forecast("B", 0.5, 0.0, 2, universe_identity_sha256="9" * 64),
    )
    with pytest.raises(ValueError, match="common provenance"):
        _build(forecasts)

    with pytest.raises(TypeError, match="approved_universe"):
        _build((_forecast("A", 0.8, 1.0, 1),), approved_universe=("A",))
    with pytest.raises(TypeError, match="universe_identity_sha256"):
        _build(
            (_forecast("A", 0.8, 1.0, 1),),
            universe_identity_sha256="9" * 64,
        )


def test_holdings_and_cash_are_normalized_bound_and_hashes_are_internal():
    forecasts = (_forecast("A", 0.8, 1.0, 1), _forecast("B", 0.5, 0.0, 2))
    first = _build(
        forecasts,
        current_holdings_weights={"B": 0.2, "A": 0.1},
    )
    second = _build(
        forecasts,
        current_holdings_weights={"A": 0.1, "B": 0.2},
    )
    changed = _build(forecasts, current_holdings_weights={"A": 0.3})

    assert first.current_holdings_weights == (("A", 0.1), ("B", 0.2))
    assert first.current_cash_weight == pytest.approx(0.7)
    assert first.holdings_snapshot_sha256 == second.holdings_snapshot_sha256
    assert first.holdings_snapshot_sha256 != changed.holdings_snapshot_sha256
    with pytest.raises(TypeError, match="holdings_snapshot_sha256"):
        _build(forecasts, holdings_snapshot_sha256=SHA_A)
    with pytest.raises(TypeError, match="cash_snapshot_sha256"):
        _build(forecasts, cash_snapshot_sha256=SHA_A)


def test_liquidation_line_cost_and_turnover_cover_holding_absent_from_forecasts():
    target = _build(
        (_forecast("A", 0.8, 1.0, 1), _forecast("B", 0.5, 0.0, 2)),
        current_holdings_weights={"A": 0.25, "C": 0.25},
        transaction_cost_rate=0.001,
    )

    assert [(line.symbol, line.reason) for line in target.lines] == [
        ("A", "selected_top_n"),
        ("B", "selected_top_n"),
        ("C", "liquidation_no_forecast"),
    ]
    liquidation = target.lines[-1]
    assert liquidation.target_weight == 0.0
    assert liquidation.target_notional == 0.0
    assert liquidation.raw_forecast_contribution is None
    assert liquidation.standardized_forecast_contribution is None
    assert liquidation.confidence is None
    assert liquidation.estimated_cost == pytest.approx(0.25)
    assert [line.estimated_cost for line in target.lines] == pytest.approx([0.25, 0.5, 0.25])
    assert target.turnover == pytest.approx(0.75)


def test_transaction_cost_assumption_is_content_bound_and_not_caller_minted():
    forecasts = (_forecast("A", 0.8, 1.0, 1),)
    first = _build(forecasts, transaction_cost_rate=0.001)
    changed = _build(forecasts, transaction_cost_rate=0.002)

    assert first.transaction_cost_assumption == (("transaction_cost_rate", 0.001),)
    assert first.transaction_cost_assumption_sha256 != changed.transaction_cost_assumption_sha256
    with pytest.raises(TypeError, match="transaction_cost_assumption"):
        _build(forecasts, transaction_cost_assumption_identity_sha256=SHA_A)


def test_fixed_constraints_are_content_bound_and_not_caller_minted():
    forecasts = (_forecast("A", 0.8, 1.0, 1),)
    first = _build(forecasts, top_n=1, entry_threshold=0.0)
    changed = _build(forecasts, top_n=2, entry_threshold=0.0)

    assert first.long_only is True
    assert first.equal_weight is True
    assert first.constraint_identity_sha256 != changed.constraint_identity_sha256
    with pytest.raises(TypeError, match="constraint_identity_sha256"):
        _build(forecasts, constraint_identity_sha256=SHA_A)


def test_constraint_identity_preserves_large_integer_identity():
    forecasts = (_forecast("A", 0.8, 1.0, 1),)

    first = _build(forecasts, top_n=2**53)
    changed = _build(forecasts, top_n=2**53 + 1)

    assert first.constraint_identity_sha256 != changed.constraint_identity_sha256


@pytest.mark.parametrize(
    "forecasts",
    [
        (
            _forecast("A", 0.8, 1.0, 2),
            _forecast("B", 0.5, 0.0, 1),
        ),
        (
            _forecast("A", 0.8, 1.0, 1),
            _forecast("B", 0.5, 0.0, 1),
        ),
        (
            _forecast("A", 0.8, 1.0, 1),
            _forecast("B", 0.5, 0.0, 3),
        ),
        (
            _forecast("B", 0.5, 0.0, 1),
            _forecast("A", 0.5, 0.0, 2),
        ),
    ],
)
def test_builder_rejects_noncontiguous_duplicate_or_score_incoherent_ranks(forecasts):
    with pytest.raises(ValueError, match="rank"):
        _build(forecasts)


@pytest.mark.parametrize(
    ("override", "match"),
    [
        ({"as_of_timestamp": AS_OF + timedelta(days=1)}, "as_of_timestamp"),
        ({"valid_until_timestamp": VALID_UNTIL + timedelta(days=1)}, "valid_until_timestamp"),
        ({"portfolio_value": 0.0}, "portfolio_value"),
        ({"portfolio_value": float("inf")}, "portfolio_value"),
        ({"current_holdings_weights": {"A": -0.1}}, "current_holdings_weights"),
        ({"current_holdings_weights": {"A": 1.1}}, "current_holdings_weights"),
        ({"current_holdings_weights": {"A": 0.6, "B": 0.5}}, "current_holdings_weights"),
        ({"top_n": 0}, "top_n"),
        ({"top_n": True}, "top_n"),
        ({"entry_threshold": float("nan")}, "entry_threshold"),
        ({"transaction_cost_rate": -0.01}, "transaction_cost_rate"),
        ({"transaction_cost_rate": float("inf")}, "transaction_cost_rate"),
        ({"target_generation_version": " "}, "target_generation_version"),
    ],
)
def test_builder_rejects_malformed_inputs(override, match):
    with pytest.raises(ValueError, match=match):
        _build((_forecast("A", 0.8, 1.0, 1),), **override)


def test_builder_rejects_empty_mixed_or_duplicate_forecast_provenance():
    with pytest.raises(ValueError, match="forecasts must not be empty"):
        _build(())

    mixed = (
        _forecast("A", 0.8, 1.0, 1),
        _forecast("B", 0.5, 0.0, 2, dataset_identity_sha256="9" * 64),
    )
    with pytest.raises(ValueError, match="common provenance"):
        _build(mixed)

    duplicate = (_forecast("A", 0.8, 1.0, 1), _forecast("A", 0.5, 0.0, 2))
    with pytest.raises(ValueError, match="duplicate forecast symbol"):
        _build(duplicate)


def test_builder_revalidates_forecasts_at_consumer_boundary():
    forecast = _forecast("A", 0.8, 1.0, 1)
    object.__setattr__(forecast, "raw_model_score", float("nan"))

    with pytest.raises(ValueError, match="raw_model_score"):
        _build((forecast,))


def test_public_line_rejects_substantive_contradictions():
    with pytest.raises(ValueError, match="target_weight"):
        ShadowTargetLine("A", -0.1, 0.0, "outside_top_n", 1.0, 1.0, None, None)
    with pytest.raises(ValueError, match="forecast contribution"):
        ShadowTargetLine("A", 0.0, 0.0, "liquidation_no_forecast", 1.0, None, None, None)
    with pytest.raises(ValueError, match="estimated_cost"):
        ShadowTargetLine("A", 0.0, 0.0, "outside_top_n", 1.0, 1.0, None, -1.0)


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"portfolio_value": -1.0}, "portfolio_value"),
        ({"transaction_cost_rate": -0.1}, "transaction_cost_rate"),
        ({"turnover": -0.1}, "turnover"),
        ({"gross_exposure": -0.1}, "gross_exposure"),
        ({"net_exposure": -0.1}, "net_exposure"),
        ({"concentration": -0.1}, "concentration"),
        ({"selected_count": -1}, "selected_count"),
        ({"top_n": True}, "top_n"),
        ({"blocked": True}, "diagnostic_reason"),
        ({"infeasible": True}, "diagnostic_reason"),
        ({"diagnostic_reason": "contradiction"}, "diagnostic_reason"),
        ({"long_only": False}, "long_only"),
        ({"equal_weight": False}, "equal_weight"),
        ({"current_cash_weight": 0.5}, "cash"),
        ({"holdings_snapshot_sha256": SHA_A}, "holdings_snapshot_sha256"),
        ({"transaction_cost_assumption_sha256": SHA_A}, "transaction_cost_assumption_sha256"),
        ({"constraint_identity_sha256": SHA_A}, "constraint_identity_sha256"),
    ],
)
def test_public_target_replace_rejects_substantive_contradictions(changes, match):
    target = _build(_base_forecasts())
    with pytest.raises(ValueError, match=match):
        replace(target, **changes)


def test_public_target_binds_embedded_forecast_set_digest():
    target = _build(_base_forecasts())

    assert target.forecasts == tuple(sorted(_base_forecasts(), key=lambda item: item.symbol))
    with pytest.raises(ValueError, match="eligible_forecast_set_sha256"):
        replace(target, eligible_forecast_set_sha256="9" * 64)


def test_public_target_binds_line_contributions_to_embedded_forecasts():
    target = _build(_base_forecasts())
    changed = replace(target.lines[0], raw_forecast_contribution=0.75)

    with pytest.raises(ValueError, match="forecast contribution"):
        replace(target, lines=(changed, *target.lines[1:]))


def test_public_target_rejects_no_forecast_reason_for_embedded_forecast():
    target = _build(_base_forecasts())
    changed = replace(
        target.lines[2],
        reason="liquidation_no_forecast",
        raw_forecast_contribution=None,
        standardized_forecast_contribution=None,
    )

    with pytest.raises(ValueError, match="liquidation_no_forecast"):
        replace(target, lines=(*target.lines[:2], changed, *target.lines[3:]))


def test_public_target_binds_altered_embedded_forecasts():
    target = _build(_base_forecasts())
    changed = replace(target.forecasts[0], standardized_score=-0.5)

    with pytest.raises(ValueError, match="eligible_forecast_set_sha256"):
        replace(target, forecasts=(changed, *target.forecasts[1:]))


def test_public_target_rejects_line_order_selection_weights_metrics_and_cost_contradictions():
    target = _build(_base_forecasts(), transaction_cost_rate=0.001)

    with pytest.raises(ValueError, match="symbol order"):
        replace(target, lines=tuple(reversed(target.lines)))
    with pytest.raises(ValueError, match="selected_count"):
        replace(target, selected_count=1)
    bad_weight = replace(target.lines[0], target_weight=0.4, target_notional=400.0)
    with pytest.raises(ValueError, match="equal weight"):
        replace(target, lines=(bad_weight, *target.lines[1:]))
    bad_notional = replace(target.lines[0], target_notional=499.0)
    with pytest.raises(ValueError, match="target_notional"):
        replace(target, lines=(bad_notional, *target.lines[1:]))
    bad_cost = replace(target.lines[0], estimated_cost=99.0)
    with pytest.raises(ValueError, match="estimated_cost"):
        replace(target, lines=(bad_cost, *target.lines[1:]))

    tampered_line = target.lines[2]
    object.__setattr__(tampered_line, "confidence", 0.5)
    with pytest.raises(ValueError, match="confidence"):
        replace(target, lines=target.lines)


def test_builder_normalizes_signed_zero_in_embedded_numeric_content():
    target = _build(
        (_forecast("A", 0.8, 1.0, 1),),
        current_holdings_weights={"A": -0.0},
        transaction_cost_rate=-0.0,
    )

    assert target.current_holdings_weights[0][1].hex() == float(0.0).hex()
    assert target.transaction_cost_rate.hex() == float(0.0).hex()


def test_builder_does_not_mutate_forecasts_or_write_files(tmp_path, monkeypatch):
    forecasts = [_forecast("A", 0.8, 1.0, 1), _forecast("B", 0.5, 0.0, 2)]
    before = tuple(asdict(forecast) for forecast in forecasts)
    monkeypatch.chdir(tmp_path)
    files_before = set(tmp_path.iterdir())

    _build(forecasts)

    assert tuple(asdict(forecast) for forecast in forecasts) == before
    assert set(tmp_path.iterdir()) == files_before


def test_shadow_target_module_has_no_operational_or_persistence_wiring():
    source = (
        Path(__file__).resolve().parents[1] / "vesper" / "portfolio" / "shadow_target.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "vesper.engine",
        "vesper.risk",
        "vesper.execution",
        "from vesper.execution",
        "Signal",
        "submit_order",
        "open(",
        "write_text",
        "write_bytes",
    ):
        assert forbidden not in source
