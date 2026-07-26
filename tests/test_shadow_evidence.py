from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from vesper.portfolio.shadow_delta import (
    PlannerConstraints,
    PositionObservation,
    PriceObservation,
    build_shadow_delta_plan,
)
from vesper.portfolio.shadow_evidence import (
    CurrentSignalObservation,
    CurrentSignalSnapshot,
    build_shadow_evidence,
    capture_shadow_replay,
    replay_shadow,
)
from vesper.portfolio.shadow_target import build_shadow_portfolio_target
from vesper.strategy.base import Signal, SignalAction
from vesper.strategy.forecast import ForecastRecord


AS_OF = datetime(2026, 7, 24, 16, 0)
VALID_UNTIL = datetime(2026, 7, 31, 16, 0)
SHA = tuple(character * 64 for character in "abcdef")


def _forecast(symbol, score, rank):
    return ForecastRecord(
        symbol=symbol,
        as_of_timestamp=AS_OF,
        valid_until_timestamp=VALID_UNTIL,
        horizon_sessions=5,
        raw_model_score=score,
        standardized_score=score,
        rank=rank,
        model_artifact_path="models/xgb_ranker.json",
        model_artifact_sha256=SHA[0],
        dataset_identity_sha256=SHA[1],
        adjustment_identity_sha256=SHA[2],
        feature_identity_sha256=SHA[3],
        universe_identity_sha256=SHA[4],
        expert_version="xgb-v1",
        feature_version="features-v1",
        run_manifest_sha256=SHA[5],
    )


def _plan(*, holdings=None, stale_prices=False):
    holdings = holdings or {}
    forecasts = tuple(
        _forecast(symbol, score, rank)
        for rank, (symbol, score) in enumerate(
            (("A", 0.9), ("B", 0.8), ("C", 0.1)), start=1
        )
    )
    target = build_shadow_portfolio_target(
        forecasts=forecasts,
        as_of_timestamp=AS_OF,
        valid_until_timestamp=VALID_UNTIL,
        current_holdings_weights=holdings,
        portfolio_value=1_000.0,
        classification_identity_sha256="1" * 64,
        target_generation_version="shadow-target-v1",
        top_n=2,
        entry_threshold=0.0,
        transaction_cost_rate=0.001,
    )
    return build_shadow_delta_plan(
        target=target,
        as_of_timestamp=AS_OF,
        current_positions=tuple(
            PositionObservation(symbol, int(weight * 10))
            for symbol, weight in sorted(holdings.items())
        ),
        prices=tuple(
            PriceObservation(
                symbol,
                100.0,
                AS_OF - timedelta(minutes=6) if stale_prices else AS_OF,
            )
            for symbol in "ABC"
        ),
        pending_orders=(),
        pending_order_completeness="complete",
        pending_orders_observed_at=AS_OF,
        pending_orders_account_identity_sha256="7" * 64,
        pending_orders_source_snapshot_identity_sha256="8" * 64,
        constraints=PlannerConstraints(
            stale_price_max_age=timedelta(minutes=5),
            minimum_trade_notional=25.0,
            lot_size=1,
            planner_version="shadow-delta-v1",
        ),
    )


def _signal(symbol, action):
    return Signal(symbol, action, 1.0, "current strategy", timestamp=AS_OF)


def test_builds_derivation_closed_evidence_from_existing_signal_contract():
    plan = _plan()
    evidence = build_shadow_evidence(
        plan,
        (_signal("B", SignalAction.BUY), _signal("A", SignalAction.SELL)),
    )

    assert evidence.plan_sha256 == plan.plan_sha256
    assert not hasattr(evidence, "plan")
    assert [item.symbol for item in evidence.signal_snapshot.observations] == ["A", "B"]
    assert [item.action for item in evidence.signal_snapshot.observations] == ["SELL", "BUY"]
    assert [(item.symbol, item.disposition) for item in evidence.attributions] == [
        ("A", "divergent_action"),
        ("B", "aligned"),
        ("C", "both_inactive"),
    ]
    assert evidence.research_only is True
    assert evidence.authority_state == "shadow"
    assert evidence.execution_authority is False
    assert evidence.broker_authority is False
    assert evidence.order_submission_authority is False
    assert evidence.persistence_authority is False

    with pytest.raises(ValueError, match="plan"):
        replace(evidence, attributions=())


def test_signal_adapter_rejects_duplicate_unknown_nonenum_or_mismatched_signals():
    plan = _plan()
    with pytest.raises(ValueError, match="duplicate"):
        build_shadow_evidence(
            plan,
            (_signal("A", SignalAction.BUY), _signal("A", SignalAction.BUY)),
        )
    with pytest.raises(ValueError, match="unknown"):
        build_shadow_evidence(plan, (_signal("X", SignalAction.BUY),))
    with pytest.raises(ValueError, match="SignalAction"):
        build_shadow_evidence(plan, (Signal("A", "BUY", 1.0, "bad", AS_OF),))
    with pytest.raises(ValueError, match="timestamp"):
        build_shadow_evidence(
            plan,
            (Signal("A", SignalAction.BUY, 1.0, "stale", AS_OF - timedelta(seconds=1)),),
        )
    with pytest.raises(ValueError, match="strength"):
        build_shadow_evidence(plan, (Signal("A", SignalAction.BUY, True, "bad", AS_OF),))
    with pytest.raises(ValueError, match="strength"):
        build_shadow_evidence(plan, (Signal("A", SignalAction.BUY, 1.1, "bad", AS_OF),))


def test_attribution_preserves_suppressed_blocked_and_close_context():
    suppressed = build_shadow_evidence(_plan(), (_signal("C", SignalAction.BUY),))
    suppressed_c = next(item for item in suppressed.attributions if item.symbol == "C")
    assert (
        suppressed_c.disposition,
        suppressed_c.shadow_constraint_outcome,
        suppressed_c.shadow_reason,
        suppressed_c.shadow_urgency,
    ) == ("current_signal_only", "suppressed", "no_delta", "none")

    blocked = build_shadow_evidence(_plan(stale_prices=True), (_signal("A", SignalAction.BUY),))
    blocked_a = next(item for item in blocked.attributions if item.symbol == "A")
    assert (
        blocked_a.disposition,
        blocked_a.shadow_constraint_outcome,
        blocked_a.shadow_reason,
        blocked_a.shadow_urgency,
    ) == ("current_signal_only", "blocked", "stale_price", "none")

    closing = build_shadow_evidence(_plan(holdings={"C": 0.2}), (_signal("C", SignalAction.CLOSE),))
    closing_c = next(item for item in closing.attributions if item.symbol == "C")
    assert (
        closing_c.disposition,
        closing_c.shadow_action,
        closing_c.shadow_constraint_outcome,
        closing_c.shadow_urgency,
    ) == ("aligned", "CLOSE", "actionable", "close")

    reducing = build_shadow_evidence(_plan(holdings={"A": 0.7}), (_signal("A", SignalAction.SELL),))
    reducing_a = next(item for item in reducing.attributions if item.symbol == "A")
    assert (
        reducing_a.disposition,
        reducing_a.shadow_action,
        reducing_a.shadow_constraint_outcome,
        reducing_a.shadow_urgency,
    ) == ("aligned", "SELL", "actionable", "reduce")

    shadow_only = build_shadow_evidence(_plan(), ())
    shadow_only_a = next(item for item in shadow_only.attributions if item.symbol == "A")
    assert (
        shadow_only_a.disposition,
        shadow_only_a.shadow_action,
        shadow_only_a.shadow_constraint_outcome,
        shadow_only_a.shadow_urgency,
    ) == ("shadow_delta_only", "BUY", "actionable", "increase")


def test_signal_snapshot_is_deterministic_and_rejects_mutated_plan_content():
    plan = _plan()
    left = CurrentSignalSnapshot.from_signals(
        as_of_timestamp=AS_OF,
        signals=(_signal("B", SignalAction.BUY), _signal("A", SignalAction.BUY)),
    )
    right = CurrentSignalSnapshot.from_signals(
        as_of_timestamp=AS_OF,
        signals=(_signal("A", SignalAction.BUY), _signal("B", SignalAction.BUY)),
    )
    assert left == right
    assert left.snapshot_sha256 == right.snapshot_sha256

    object.__setattr__(plan.target.forecasts[0], "standardized_score", 99.0)
    with pytest.raises(ValueError, match="plan"):
        build_shadow_evidence(plan, ())


def test_capture_and_replay_rebuilds_exact_plan_and_evidence_without_source_aliases():
    plan = _plan()
    signals = (_signal("B", SignalAction.BUY), _signal("A", SignalAction.SELL))

    envelope = capture_shadow_replay(plan, signals)
    assert not hasattr(envelope, "plan")
    assert not hasattr(envelope, "target")
    assert not hasattr(envelope, "lines")
    assert (
        envelope.research_only,
        envelope.authority_state,
        envelope.execution_authority,
        envelope.broker_authority,
        envelope.order_submission_authority,
        envelope.persistence_authority,
    ) == (True, "shadow", False, False, False, False)

    object.__setattr__(plan.target.forecasts[0], "standardized_score", 99.0)
    replayed = replay_shadow(envelope)
    assert replayed.plan is not plan
    assert replayed.plan.plan_sha256 == envelope.source_plan_sha256
    assert replayed.evidence.evidence_sha256 == envelope.source_evidence_sha256
    assert replayed.evidence.signal_snapshot.snapshot_sha256 == envelope.signal_snapshot.snapshot_sha256


def test_replay_rejects_mutated_envelope_semantic_input():
    envelope = capture_shadow_replay(_plan(), ())
    object.__setattr__(envelope.forecasts[0], "standardized_score", 99.0)
    with pytest.raises(ValueError, match="replayed plan"):
        replay_shadow(envelope)


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("research_only", False),
        ("authority_state", "live"),
        ("execution_authority", True),
        ("broker_authority", True),
        ("order_submission_authority", True),
        ("persistence_authority", True),
    ),
)
def test_replay_rejects_mutated_envelope_authority(field_name, value):
    envelope = capture_shadow_replay(_plan(), ())
    object.__setattr__(envelope, field_name, value)
    with pytest.raises(ValueError):
        replay_shadow(envelope)


def test_current_signal_observation_rejects_out_of_range_strength():
    with pytest.raises(ValueError, match="strength"):
        CurrentSignalObservation("A", "BUY", 1.1, "bad", AS_OF)


def test_evidence_module_is_pure_and_has_no_execution_wiring(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.iterdir())
    assert build_shadow_evidence(_plan(), ()).evidence_sha256
    assert set(tmp_path.iterdir()) == before

    source = (
        Path(__file__).resolve().parents[1]
        / "vesper"
        / "portfolio"
        / "shadow_evidence.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "vesper.engine",
        "vesper.risk",
        "vesper.execution",
        "vesper.broker",
        "submit_order",
        "sqlite",
        "requests",
        "open(",
        "write_",
    ):
        assert forbidden not in source
