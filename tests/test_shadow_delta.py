from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from vesper.portfolio.shadow_delta import (
    PendingOrderObservation,
    PlannerConstraints,
    PositionObservation,
    PriceObservation,
    build_shadow_delta_plan,
)
from vesper.portfolio.shadow_target import build_shadow_portfolio_target
from vesper.strategy.base import SignalAction
from vesper.strategy.forecast import ForecastRecord
from vesper.strategy.ml_model import MLModelStrategy


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


def _target(*, holdings=None, portfolio_value=1_000.0, scores=None, top_n=2,
            cost_rate=0.001):
    scores = scores or (("A", 0.9), ("B", 0.8), ("C", 0.1))
    forecasts = tuple(
        _forecast(symbol, score, rank)
        for rank, (symbol, score) in enumerate(scores, start=1)
    )
    return build_shadow_portfolio_target(
        forecasts=forecasts,
        as_of_timestamp=AS_OF,
        valid_until_timestamp=VALID_UNTIL,
        current_holdings_weights=holdings or {},
        portfolio_value=portfolio_value,
        classification_identity_sha256="1" * 64,
        target_generation_version="shadow-target-v1",
        top_n=top_n,
        entry_threshold=0.0,
        transaction_cost_rate=cost_rate,
    )


def _constraints(**changes):
    values = {
        "stale_price_max_age": timedelta(minutes=5),
        "minimum_trade_notional": 25.0,
        "lot_size": 1,
        "planner_version": "shadow-delta-v1",
    }
    values.update(changes)
    return PlannerConstraints(**values)


def _build(*, target=None, positions=(), prices=None, orders=(), constraints=None,
           as_of=AS_OF, order_completeness="complete", orders_observed_at=AS_OF,
           account_identity_sha256="7" * 64,
           source_snapshot_identity_sha256="8" * 64):
    target = target or _target()
    prices = prices or tuple(
        PriceObservation(symbol, 100.0, AS_OF, "external.market-test")
        for symbol in ("A", "B", "C")
    )
    return build_shadow_delta_plan(
        target=target,
        as_of_timestamp=as_of,
        current_positions=positions,
        prices=prices,
        pending_orders=orders,
        pending_order_completeness=order_completeness,
        pending_orders_observed_at=orders_observed_at,
        pending_orders_account_identity_sha256=account_identity_sha256,
        pending_orders_source_snapshot_identity_sha256=source_snapshot_identity_sha256,
        constraints=constraints or _constraints(),
    )


def _strategy_signals(scores, holdings, *, top_n=2, exit_rank=4):
    strategy = object.__new__(MLModelStrategy)
    strategy._last_rebalance = None
    strategy.rebalance_interval = 30
    strategy.exit_rank = exit_rank
    strategy.entry_threshold = 0.0
    strategy.top_n = top_n
    strategy._score_universe = lambda data: dict(scores)
    return strategy.generate_signals({}, holdings, AS_OF)


def test_empty_holdings_actionable_buys_match_current_signal_top_n_order():
    target = _target()
    plan = _build(target=target)
    current_strategy = object.__new__(MLModelStrategy)
    current_strategy._last_rebalance = None
    current_strategy.rebalance_interval = 30
    current_strategy.exit_rank = 10
    current_strategy.entry_threshold = 0.0
    current_strategy.top_n = 2
    current_strategy._score_universe = lambda data: {"B": 0.8, "A": 0.9, "C": 0.1}
    current_signals = current_strategy.generate_signals({}, {}, AS_OF)
    actionable = [
        (line.symbol, SignalAction.BUY)
        for line in plan.lines
        if line.reason == "actionable_shadow" and line.rounded_proposed_quantity > 0
    ]

    assert actionable == [
        (signal.symbol, signal.action) for signal in current_signals
    ]
    assert [(line.symbol, line.rounded_proposed_quantity) for line in plan.lines] == [
        ("A", 5), ("B", 5), ("C", 0)
    ]
    assert plan.target == _target()
    assert plan.target_identity_sha256
    assert plan.current_snapshot.snapshot_sha256
    assert plan.price_snapshot.snapshot_sha256
    assert plan.order_snapshot.snapshot_sha256
    assert plan.constraints.identity_sha256
    assert plan.plan_sha256
    assert plan.external_provenance_claims
    assert plan.research_only is True
    assert plan.authority_state == "shadow"
    assert plan.risk_approved is False
    assert plan.execution_authority is False
    assert plan.broker_authority is False
    assert plan.order_submission_authority is False
    assert plan.persistence_authority is False
    assert not hasattr(plan, "__dict__")
    with pytest.raises(FrozenInstanceError):
        plan.blocked = True


def test_real_strategy_comparison_covers_held_entry_keep_and_exit_divergence():
    scores = (("A", 0.9), ("B", 0.8), ("C", 0.7), ("D", 0.6), ("E", 0.5))

    unheld = _build(
        target=_target(scores=scores),
        prices=tuple(PriceObservation(symbol, 100.0, AS_OF) for symbol, _ in scores),
    )
    unheld_signals = _strategy_signals(scores, {})
    assert [(signal.symbol, signal.action) for signal in unheld_signals] == [
        ("A", SignalAction.BUY), ("B", SignalAction.BUY)
    ]
    assert [
        (line.symbol, line.rounded_proposed_quantity > 0)
        for line in unheld.lines if line.constraint_outcome == "actionable"
    ] == [("A", True), ("B", True)]

    held_selected = _build(
        target=_target(scores=scores, holdings={"A": 0.2}),
        positions=(PositionObservation("A", 2),),
        prices=tuple(PriceObservation(symbol, 100.0, AS_OF) for symbol, _ in scores),
    )
    held_selected_signals = _strategy_signals(scores, {"A": object()})
    assert [(signal.symbol, signal.action) for signal in held_selected_signals] == [
        ("B", SignalAction.BUY), ("C", SignalAction.BUY)
    ]
    assert next(line for line in held_selected.lines if line.symbol == "A").rounded_proposed_quantity == 3
    # Intentional divergence: signals do not re-BUY holdings; targets may resize them.

    held_kept = _build(
        target=_target(scores=scores, holdings={"C": 0.2}),
        positions=(PositionObservation("C", 2),),
        prices=tuple(PriceObservation(symbol, 100.0, AS_OF) for symbol, _ in scores),
    )
    held_kept_signals = _strategy_signals(scores, {"C": object()})
    assert [(signal.symbol, signal.action) for signal in held_kept_signals] == [
        ("A", SignalAction.BUY), ("B", SignalAction.BUY)
    ]
    assert next(line for line in held_kept.lines if line.symbol == "C").rounded_proposed_quantity == -2
    # Intentional divergence: exit_rank keeps C in signals; top-N targets close it.

    held_exit = _build(
        target=_target(scores=scores, holdings={"E": 0.2}),
        positions=(PositionObservation("E", 2),),
        prices=tuple(PriceObservation(symbol, 100.0, AS_OF) for symbol, _ in scores),
    )
    held_exit_signals = _strategy_signals(scores, {"E": object()})
    assert [(signal.symbol, signal.action) for signal in held_exit_signals] == [
        ("E", SignalAction.CLOSE),
        ("A", SignalAction.BUY),
        ("B", SignalAction.BUY),
    ]
    exit_line = next(line for line in held_exit.lines if line.symbol == "E")
    assert exit_line.rounded_proposed_quantity < 0
    assert exit_line.urgency == "close"


def test_reductions_closures_rounding_threshold_and_zero_lines_are_truthful():
    target = _target(
        holdings={"A": 0.6, "B": 0.2, "D": 0.1},
        portfolio_value=1_000.0,
    )
    prices = tuple(
        PriceObservation(symbol, price, AS_OF)
        for symbol, price in (("A", 100.0), ("B", 100.0), ("C", 300.0), ("D", 50.0))
    )
    plan = _build(
        target=target,
        positions=(
            PositionObservation("A", 6),
            PositionObservation("B", 2),
            PositionObservation("D", 2),
        ),
        prices=prices,
    )

    by_symbol = {line.symbol: line for line in plan.lines}
    assert by_symbol["A"].rounded_proposed_quantity == -1
    assert by_symbol["A"].urgency == "reduce"
    assert by_symbol["D"].rounded_proposed_quantity == -2
    assert by_symbol["D"].urgency == "close"
    assert by_symbol["C"].reason == "no_delta"
    assert by_symbol["C"].rounded_proposed_quantity == 0
    assert by_symbol["B"].rounded_proposed_quantity == 3
    assert by_symbol["B"].estimated_cost == pytest.approx(0.3)

    rounded = _build(prices=(
        PriceObservation("A", 1_000.0, AS_OF),
        PriceObservation("B", 1_000.0, AS_OF),
        PriceObservation("C", 100.0, AS_OF),
    ))
    assert rounded.lines[0].reason == "zero_after_rounding"

    rounded_below_minimum = _build(
        target=_target(portfolio_value=60.0),
        prices=(
            PriceObservation("A", 29.0, AS_OF),
            PriceObservation("B", 30.0, AS_OF),
            PriceObservation("C", 1.0, AS_OF),
        ),
        constraints=_constraints(minimum_trade_notional=30.0),
    )
    assert rounded_below_minimum.lines[0].delta_notional == 30.0
    assert rounded_below_minimum.lines[0].reason == "below_minimum_trade_notional"
    assert rounded_below_minimum.lines[0].rounded_proposed_quantity == 0

    below = _build(constraints=_constraints(minimum_trade_notional=600.0))
    assert [line.reason for line in below.lines] == [
        "below_minimum_trade_notional",
        "below_minimum_trade_notional",
        "no_delta",
    ]


def test_stale_and_pending_symbols_are_explicitly_blocked_without_proposals():
    prices = (
        PriceObservation("A", 100.0, AS_OF - timedelta(minutes=6)),
        PriceObservation("B", 100.0, AS_OF),
        PriceObservation("C", 100.0, AS_OF),
    )
    orders = (
        PendingOrderObservation(
            symbol="B",
            state="pending",
            side="BUY",
            remaining_quantity=2,
            external_order_identity_claim="external.broker-order-17",
            observed_at=AS_OF,
        ),
    )
    plan = _build(prices=prices, orders=orders)
    by_symbol = {line.symbol: line for line in plan.lines}

    assert by_symbol["A"].reason == "stale_price"
    assert by_symbol["A"].constraint_outcome == "blocked"
    assert by_symbol["B"].reason == "pending_order"
    assert by_symbol["B"].constraint_outcome == "blocked"
    assert by_symbol["A"].rounded_proposed_quantity == 0
    assert by_symbol["B"].rounded_proposed_quantity == 0
    assert plan.blocked is True


def test_ambiguous_pending_order_state_fails_closed():
    with pytest.raises(ValueError, match="state"):
        PendingOrderObservation("A", "unknown", "BUY", 1, "external.1", AS_OF)

    orders = (
        PendingOrderObservation("A", "open", "BUY", 1, "external.1", AS_OF),
        PendingOrderObservation("A", "pending", "SELL", 1, "external.2", AS_OF),
    )
    with pytest.raises(ValueError, match="ambiguous"):
        _build(orders=orders)


@pytest.mark.parametrize("completeness", ["partial", "ambiguous"])
def test_incomplete_order_snapshot_blocks_every_proposal(completeness):
    plan = _build(order_completeness=completeness)

    assert plan.blocked is True
    assert plan.diagnostic_reason == f"pending order snapshot is {completeness}"
    assert all(line.rounded_proposed_quantity == 0 for line in plan.lines)
    assert all(line.reason == "incomplete_order_snapshot" for line in plan.lines)
    assert all(line.constraint_outcome == "blocked" for line in plan.lines)


def test_complete_known_empty_order_snapshot_is_actionable_and_content_bound():
    plan = _build()
    snapshot = plan.order_snapshot

    assert snapshot.completeness == "complete"
    assert snapshot.observations == ()
    assert snapshot.observed_at == AS_OF
    assert snapshot.account_identity_sha256 == "7" * 64
    assert snapshot.source_snapshot_identity_sha256 == "8" * 64
    assert any(line.constraint_outcome == "actionable" for line in plan.lines)
    assert snapshot.snapshot_sha256 != replace(
        snapshot, source_snapshot_identity_sha256="9" * 64
    ).snapshot_sha256
    assert snapshot.snapshot_sha256 != replace(
        snapshot, account_identity_sha256="9" * 64
    ).snapshot_sha256


def test_stale_complete_order_snapshot_blocks_every_proposal():
    plan = _build(orders_observed_at=AS_OF - timedelta(minutes=6))

    assert plan.blocked is True
    assert plan.diagnostic_reason == "pending order snapshot is stale"
    assert all(line.reason == "incomplete_order_snapshot" for line in plan.lines)
    assert all(line.rounded_proposed_quantity == 0 for line in plan.lines)


def test_pending_order_snapshot_strict_fields_and_replace_tampering_fail_closed():
    snapshot = _build().order_snapshot
    for changes, match in (
        ({"completeness": "unknown"}, "completeness"),
        ({"completeness": 1}, "completeness"),
        ({"observed_at": "not-a-time"}, "observed_at"),
        ({"observed_at": AS_OF + timedelta(seconds=1)}, "observed_at"),
        ({"account_identity_sha256": "external-account"}, "account_identity_sha256"),
        ({"source_snapshot_identity_sha256": "f" * 63}, "source_snapshot_identity_sha256"),
    ):
        with pytest.raises(ValueError, match=match):
            replace(snapshot, **changes)

    with pytest.raises(ValueError, match="pending_order_completeness"):
        build_shadow_delta_plan(
            target=_target(), as_of_timestamp=AS_OF, current_positions=(),
            prices=tuple(PriceObservation(symbol, 100.0, AS_OF) for symbol in "ABC"),
            pending_orders=(), pending_order_completeness=None,
            pending_orders_observed_at=AS_OF,
            pending_orders_account_identity_sha256="7" * 64,
            pending_orders_source_snapshot_identity_sha256="8" * 64,
            constraints=_constraints(),
        )


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"prices": (PriceObservation("A", 100.0, AS_OF),)}, "complete"),
        ({"prices": (
            PriceObservation("A", 100.0, AS_OF),
            PriceObservation("B", 100.0, AS_OF),
            PriceObservation("C", 100.0, AS_OF),
            PriceObservation("X", 100.0, AS_OF),
        )}, "unknown"),
        ({"prices": (
            PriceObservation("A", 100.0, AS_OF),
            PriceObservation("A", 100.0, AS_OF),
            PriceObservation("B", 100.0, AS_OF),
            PriceObservation("C", 100.0, AS_OF),
        )}, "duplicate"),
        ({"positions": (PositionObservation("X", 1),)}, "unknown"),
        ({"as_of": VALID_UNTIL + timedelta(seconds=1)}, "expired"),
    ],
)
def test_invalid_price_portfolio_symbol_and_expiry_inputs_fail_closed(change, match):
    with pytest.raises(ValueError, match=match):
        _build(**change)

    with pytest.raises(ValueError, match="price"):
        PriceObservation("A", float("nan"), AS_OF)
    with pytest.raises(ValueError, match="quantity"):
        PositionObservation("A", -1)


def test_mismatched_target_snapshot_and_time_fail_closed():
    target = _target(holdings={"A": 0.5})
    with pytest.raises(ValueError, match="current snapshot"):
        _build(target=target, positions=())
    with pytest.raises(ValueError, match="as_of_timestamp"):
        _build(as_of=AS_OF + timedelta(minutes=1))
    with pytest.raises(ValueError, match="timezone"):
        _build(as_of=AS_OF.replace(tzinfo=timezone.utc))


def test_blocked_or_infeasible_target_fails_closed():
    target = _target(scores=(("A", -0.1), ("B", -0.2)))
    blocked = replace(target, blocked=True, diagnostic_reason="upstream blocked")
    infeasible = replace(target, infeasible=True, diagnostic_reason="upstream infeasible")

    with pytest.raises(ValueError, match="blocked or infeasible"):
        _build(target=blocked, prices=(
            PriceObservation("A", 100.0, AS_OF),
            PriceObservation("B", 100.0, AS_OF),
        ))
    with pytest.raises(ValueError, match="blocked or infeasible"):
        _build(target=infeasible, prices=(
            PriceObservation("A", 100.0, AS_OF),
            PriceObservation("B", 100.0, AS_OF),
        ))


def test_content_hashes_are_internal_deterministic_and_sensitive_to_exact_content():
    first = _build()
    reordered = _build(prices=tuple(reversed(first.price_snapshot.observations)))
    changed = _build(prices=(
        PriceObservation("A", 100.0, AS_OF, "external.changed"),
        PriceObservation("B", 100.0, AS_OF, "external.market-test"),
        PriceObservation("C", 100.0, AS_OF, "external.market-test"),
    ))

    assert first.plan_sha256 == reordered.plan_sha256
    assert first.price_snapshot.snapshot_sha256 == reordered.price_snapshot.snapshot_sha256
    assert first.plan_sha256 != changed.plan_sha256
    changed_target = replace(first.target, classification_identity_sha256="2" * 64)
    changed_target_plan = _build(target=changed_target)
    assert first.target_identity_sha256 != changed_target_plan.target_identity_sha256
    assert _constraints(minimum_trade_notional=25).identity_sha256 == (
        _constraints(minimum_trade_notional=25.0).identity_sha256
    )
    assert replace(first) == first
    with pytest.raises(TypeError, match="snapshot_sha256"):
        type(first.price_snapshot)(
            as_of_timestamp=AS_OF,
            observations=first.price_snapshot.observations,
            snapshot_sha256="0" * 64,
        )
    with pytest.raises(TypeError, match="identity_sha256"):
        PlannerConstraints(
            timedelta(minutes=5), 25.0, 1, "v1", identity_sha256="0" * 64
        )


def test_replace_tampering_and_numeric_edges_fail_closed():
    plan = _build()
    with pytest.raises(ValueError, match="delta_notional"):
        replace(plan.lines[0], delta_notional=999.0)

    object.__setattr__(plan.price_snapshot.observations[0], "price", 0.0)
    with pytest.raises(ValueError, match="price"):
        replace(plan)

    with pytest.raises(ValueError, match="minimum_trade_notional"):
        _constraints(minimum_trade_notional=float("inf"))
    with pytest.raises(ValueError, match="lot_size"):
        _constraints(lot_size=True)
    with pytest.raises(ValueError, match="lot_size"):
        _constraints(lot_size=2)
    with pytest.raises(ValueError, match="planner_version"):
        _constraints(planner_version=" ")
    with pytest.raises(ValueError, match="observed_at"):
        PriceObservation("A", 1.0, "not-a-time")
    with pytest.raises(ValueError, match="quantity"):
        PositionObservation("A", 2**53 + 1.0)


def test_detached_delta_line_derived_claims_cannot_be_replaced():
    line = _build().lines[0]
    for changes in (
        {"estimated_cost": 123.5},
        {"rounded_proposed_quantity": line.rounded_proposed_quantity + 999},
        {
            "reason": "no_delta",
            "rounded_proposed_quantity": 0,
            "constraint_outcome": "suppressed",
            "urgency": "none",
        },
    ):
        with pytest.raises(ValueError, match="init=False"):
            replace(line, **changes)


def test_detached_delta_line_evidence_replacement_recomputes_truth():
    plan = _build()
    line = plan.lines[0]

    repriced = replace(line, execution_price=50.0)
    assert repriced.delta_notional == line.delta_notional
    assert repriced.raw_rounded_quantity == 10
    assert repriced.rounded_proposed_quantity == 10
    assert repriced.estimated_cost == 0.5

    no_delta = replace(line, target_notional=line.current_notional)
    assert no_delta.delta_notional == 0.0
    assert no_delta.raw_rounded_quantity == 0
    assert no_delta.rounded_proposed_quantity == 0
    assert no_delta.reason == "no_delta"
    assert no_delta.urgency == "none"
    assert no_delta.constraint_outcome == "suppressed"
    assert no_delta.estimated_cost == 0.0

    blocked = replace(line, declared_blocker="stale_price")
    assert blocked.raw_rounded_quantity == line.raw_rounded_quantity
    assert blocked.rounded_proposed_quantity == 0
    assert blocked.reason == "stale_price"
    assert blocked.urgency == "none"
    assert blocked.constraint_outcome == "blocked"
    with pytest.raises(ValueError, match="lines"):
        replace(plan, lines=(blocked,) + plan.lines[1:])


def test_detached_delta_line_strict_evidence_and_impossible_rounding_fail_closed():
    line = _build().lines[0]
    for changes, match in (
        ({"target_weight": 0}, "target_weight"),
        ({"current_weight": -0.1}, "current_weight"),
        ({"target_notional": float("inf")}, "target_notional"),
        ({"current_notional": -1.0}, "current_notional"),
        ({"execution_price": 100}, "execution_price"),
        ({"execution_price": float("nan")}, "execution_price"),
        ({"execution_price": 0.0}, "execution_price"),
        ({"transaction_cost_rate": 0}, "transaction_cost_rate"),
        ({"transaction_cost_rate": float("inf")}, "transaction_cost_rate"),
        ({"transaction_cost_rate": -0.1}, "transaction_cost_rate"),
        ({"minimum_trade_notional": 25}, "minimum_trade_notional"),
        ({"minimum_trade_notional": -1.0}, "minimum_trade_notional"),
        ({"lot_size": True}, "lot_size"),
        ({"lot_size": 2}, "lot_size"),
        ({"declared_blocker": "invented"}, "declared_blocker"),
        ({
            "declared_blocker": type("BlockerText", (str,), {})("stale_price")
        }, "declared_blocker"),
        ({"valid_until_timestamp": "not-a-time"}, "valid_until_timestamp"),
        ({"target_notional": 1e308, "execution_price": 1.0}, "impossible rounding"),
        ({
            "target_notional": 1e308,
            "execution_price": 1e308,
            "transaction_cost_rate": 2.0,
        }, "impossible estimated cost"),
    ):
        with pytest.raises(ValueError, match=match):
            replace(line, **changes)


def test_delta_line_field_metadata_closes_constructor_and_preserves_hash_content():
    line_fields = {item.name: item for item in fields(type(_build().lines[0]))}
    derived = {
        "delta_weight", "delta_notional", "raw_rounded_quantity",
        "rounded_proposed_quantity", "reason", "urgency", "estimated_cost",
        "constraint_outcome",
    }

    assert all(line_fields[name].init is False for name in derived)
    assert all(line_fields[name].metadata.get("derived_claim") is True for name in derived)
    assert all(
        line_fields[name].metadata.get("computed_digest") is not True
        for name in derived
    )
    assert all(
        line_fields[name].init is True
        for name in set(line_fields) - derived
    )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("blocked", 1),
        ("research_only", 1),
        ("risk_approved", 0),
        ("execution_authority", 0),
        ("broker_authority", 0),
        ("order_submission_authority", 0),
        ("persistence_authority", 0),
    ],
)
def test_plan_public_boolean_fields_require_exact_bool(field_name, value):
    with pytest.raises(ValueError, match=field_name):
        replace(_build(), **{field_name: value})


def test_schema_has_no_execution_semantics_and_builder_writes_nothing(tmp_path, monkeypatch):
    plan_fields = {item.name for item in fields(type(_build()))}
    line_fields = {item.name for item in fields(type(_build().lines[0]))}
    forbidden_fields = {
        "order_type", "time_in_force", "account", "broker", "client_order_id"
    }
    assert not (plan_fields | line_fields) & forbidden_fields

    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.iterdir())
    _build()
    assert set(tmp_path.iterdir()) == before

    source = (
        Path(__file__).resolve().parents[1] / "vesper" / "portfolio" / "shadow_delta.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "vesper.engine", "vesper.risk", "vesper.execution", "vesper.broker",
        "submit_order", "open(", "write_text", "write_bytes", "sqlite", "pickle",
    ):
        assert forbidden not in source
