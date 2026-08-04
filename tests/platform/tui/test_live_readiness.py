"""Fail-closed Live readiness and descriptive broker transition tests."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from vesper.platform.tui.gateway import Gateway
from vesper.platform.tui import live_readiness
from vesper.platform.tui.live_readiness import (
    BrokerPositionInput,
    BrokerTransitionInput,
    DesiredPositionInput,
    build_live_readiness,
    build_transition_plan,
    unavailable_live_readiness,
)
from vesper.platform.tui.views import (
    AccountSummaryView,
    LiveReadinessView,
    ReadinessGate,
    TransitionOrderView,
)


NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
GATE_NAMES = (
    "broker",
    "account",
    "data",
    "model",
    "strategy",
    "risk",
    "reconciliation",
    "incident",
    "authority",
)


def _gates(state: str = "ready") -> dict[str, ReadinessGate]:
    return {name: ReadinessGate(state=state, reason=f"{name} test evidence") for name in GATE_NAMES}


def test_live_is_enabled_if_and_only_if_all_nine_named_gates_are_ready() -> None:
    ready = build_live_readiness(**_gates())
    assert ready.enabled is True

    for state in ("blocked", "unavailable", "stale"):
        gates = _gates()
        gates["reconciliation"] = ReadinessGate(
            state=state,
            reason="Broker positions do not have a current match.",
        )
        assert build_live_readiness(**gates).enabled is False

    with pytest.raises(ValidationError, match="enabled"):
        LiveReadinessView(**_gates(), enabled=False)
    with pytest.raises(ValidationError, match="enabled"):
        LiveReadinessView(
            **{
                **_gates(),
                "authority": ReadinessGate(state="blocked", reason="No authority."),
            },
            enabled=True,
        )


def test_live_readiness_requires_each_exact_gate_once_and_defaults_unavailable() -> None:
    gates = _gates()
    gates.pop("authority")
    with pytest.raises(TypeError):
        build_live_readiness(**gates)

    default = unavailable_live_readiness()
    assert default.enabled is False
    assert all(getattr(default, name).state == "unavailable" for name in GATE_NAMES)


def test_default_gateway_snapshot_is_unavailable_null_and_never_touches_a_broker(
    tmp_path,
    monkeypatch,
) -> None:
    from vesper.execution import broker as broker_module

    def forbidden(*_args, **_kwargs):
        pytest.fail("default Live view must not touch a broker or account")

    monkeypatch.setattr(broker_module, "create_broker", forbidden)
    for broker_type in (
        broker_module.BrokerBase,
        broker_module.PaperBroker,
        broker_module.AlpacaBroker,
    ):
        monkeypatch.setattr(broker_type, "get_account", forbidden)
        monkeypatch.setattr(broker_type, "get_positions", forbidden)

    system = Gateway(tmp_path / "state", clock=lambda: NOW).snapshot().system

    assert system.live_readiness.enabled is False
    assert all(getattr(system.live_readiness, name).state == "unavailable" for name in GATE_NAMES)
    assert system.live_account is None
    assert system.live_transition_plan is None


def test_live_account_summary_contains_only_reviewed_display_fields() -> None:
    summary = AccountSummaryView(
        name="Primary brokerage",
        number="123456789",
        balance="10000.25",
        capital="9500",
    )
    assert summary.model_dump() == {
        "name": "Primary brokerage",
        "number": "123456789",
        "balance": "10000.25",
        "capital": "9500",
    }
    with pytest.raises(ValidationError):
        AccountSummaryView.model_validate(
            {**summary.model_dump(), "credential": "must-never-enter-the-view"}
        )


def test_transition_plan_uses_typed_broker_positions_and_keeps_orders_approval_required() -> None:
    inputs = BrokerTransitionInput(
        source="broker",
        broker_positions_as_of_utc=NOW,
        desired_portfolio_id="portfolio:live-candidate",
        broker_positions=(
            BrokerPositionInput(symbol="AAPL", quantity=Decimal("10")),
            BrokerPositionInput(symbol="MSFT", quantity=Decimal("2.5")),
            BrokerPositionInput(symbol="OLD", quantity=Decimal("1")),
        ),
        desired_positions=(
            DesiredPositionInput(symbol="AAPL", quantity=Decimal("10")),
            DesiredPositionInput(symbol="MSFT", quantity=Decimal("5")),
            DesiredPositionInput(symbol="NVDA", quantity=Decimal("3.2500")),
        ),
    )

    plan = build_transition_plan(inputs)

    assert plan is not None
    assert plan.broker_positions_as_of_utc == NOW
    assert plan.desired_portfolio_id == "portfolio:live-candidate"
    assert [order.model_dump() for order in plan.orders] == [
        {"symbol": "MSFT", "side": "buy", "quantity": "2.5", "approval_required": True},
        {"symbol": "NVDA", "side": "buy", "quantity": "3.25", "approval_required": True},
        {"symbol": "OLD", "side": "sell", "quantity": "1", "approval_required": True},
    ]
    assert all(order.approval_required is True for order in plan.orders)


def test_transition_input_rejects_paper_untyped_quantities_duplicates_and_zero_orders() -> None:
    valid = {
        "source": "broker",
        "broker_positions_as_of_utc": NOW,
        "desired_portfolio_id": "portfolio:candidate",
        "broker_positions": (),
        "desired_positions": (),
    }
    with pytest.raises(ValidationError):
        BrokerTransitionInput.model_validate({**valid, "source": "paper"})
    with pytest.raises(ValidationError):
        BrokerPositionInput(symbol="AAPL", quantity="1")
    with pytest.raises(ValidationError, match="duplicate"):
        BrokerTransitionInput(
            **{
                **valid,
                "broker_positions": (
                    BrokerPositionInput(symbol="AAPL", quantity=Decimal("1")),
                    BrokerPositionInput(symbol="AAPL", quantity=Decimal("2")),
                ),
            }
        )
    with pytest.raises(ValidationError, match="positive"):
        TransitionOrderView(
            symbol="AAPL",
            side="buy",
            quantity="0",
            approval_required=True,
        )
    with pytest.raises(ValidationError):
        TransitionOrderView(
            symbol="AAPL",
            side="buy",
            quantity="1",
            approval_required=False,
        )
    assert build_transition_plan(None) is None


@pytest.mark.parametrize(
    "quantity",
    (
        "12345678901234567890123456789",
        "1234567890123456789012345678901234567890",
    ),
)
def test_transition_subtraction_preserves_29_and_40_digit_quantities(quantity: str) -> None:
    inputs = BrokerTransitionInput(
        source="broker",
        broker_positions_as_of_utc=NOW,
        desired_portfolio_id="portfolio:candidate",
        broker_positions=(BrokerPositionInput(symbol="AAPL", quantity=Decimal(0)),),
        desired_positions=(DesiredPositionInput(symbol="AAPL", quantity=Decimal(quantity)),),
    )

    plan = build_transition_plan(inputs)

    assert plan is not None
    assert plan.orders[0].quantity == quantity
    assert plan.orders[0].approval_required is True


def test_transition_subtraction_preserves_mixed_integer_and_fractional_scales() -> None:
    inputs = BrokerTransitionInput(
        source="broker",
        broker_positions_as_of_utc=NOW,
        desired_portfolio_id="portfolio:candidate",
        broker_positions=(
            BrokerPositionInput(
                symbol="AAPL",
                quantity=Decimal("0.00000000000000000000000000001"),
            ),
        ),
        desired_positions=(
            DesiredPositionInput(
                symbol="AAPL",
                quantity=Decimal("12345678901234567890123456789.123456789"),
            ),
        ),
    )

    plan = build_transition_plan(inputs)

    assert plan is not None
    assert plan.orders[0].quantity == "12345678901234567890123456789.12345678899999999999999999999"


def test_position_input_accepts_128_canonical_characters_and_rejects_129_or_huge_exponents() -> (
    None
):
    assert BrokerPositionInput(symbol="AAPL", quantity=Decimal("9" * 128)).quantity == Decimal(
        "9" * 128
    )
    assert BrokerPositionInput(
        symbol="AAPL",
        quantity=Decimal("1E+127"),
    ).quantity == Decimal("1E+127")

    for quantity in (Decimal("9" * 129), Decimal("1E+128"), Decimal("1E+1000000")):
        with pytest.raises(ValidationError, match="128-character"):
            BrokerPositionInput(symbol="AAPL", quantity=quantity)


def test_oversized_transition_delta_is_rejected_before_fixed_point_formatting(
    monkeypatch,
) -> None:
    inputs = BrokerTransitionInput(
        source="broker",
        broker_positions_as_of_utc=NOW,
        desired_portfolio_id="portfolio:candidate",
        broker_positions=(BrokerPositionInput(symbol="AAPL", quantity=Decimal("-" + "9" * 127)),),
        desired_positions=(DesiredPositionInput(symbol="AAPL", quantity=Decimal("9" * 128)),),
    )

    def forbidden_format(*_args, **_kwargs):
        raise AssertionError("oversized decimal reached fixed-point formatting")

    monkeypatch.setattr(live_readiness, "format", forbidden_format, raising=False)

    with pytest.raises(ValueError, match="128-character"):
        build_transition_plan(inputs)
