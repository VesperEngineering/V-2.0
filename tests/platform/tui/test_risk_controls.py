from __future__ import annotations

import pytest

from vesper.platform.tui.risk_controls import evaluate_approved_maximum


def test_tighter_approved_limit_activates_and_blocks_new_risk_when_violated() -> None:
    decision = evaluate_approved_maximum(
        limit_id="limit:concentration",
        current_limit="0.12",
        approved_limit="0.10",
        observed_value="0.11",
    )

    assert decision.change == "tighter"
    assert decision.effective_limit == "0.10"
    assert decision.new_risk_blocked is True
    assert decision.corrective_plan_required is True
    assert decision.broker_orders_authorized is False
    assert decision.order_approval_required is True


def test_tighter_approved_limit_does_not_create_plan_when_already_within_limit() -> None:
    decision = evaluate_approved_maximum(
        limit_id="limit:concentration",
        current_limit="0.12",
        approved_limit="0.10",
        observed_value="0.09",
    )

    assert decision.change == "tighter"
    assert decision.new_risk_blocked is False
    assert decision.corrective_plan_required is False
    assert decision.order_approval_required is False


def test_higher_approved_limit_changes_permission_without_forcing_trade() -> None:
    decision = evaluate_approved_maximum(
        limit_id="limit:concentration",
        current_limit="0.10",
        approved_limit="0.12",
        observed_value="0.11",
    )

    assert decision.change == "higher"
    assert decision.effective_limit == "0.12"
    assert decision.new_risk_blocked is False
    assert decision.corrective_plan_required is False
    assert decision.broker_orders_authorized is False
    assert decision.order_approval_required is False


def test_equal_limit_is_a_noop_and_never_authorizes_orders() -> None:
    decision = evaluate_approved_maximum(
        limit_id="limit:concentration",
        current_limit="0.10",
        approved_limit="0.10",
        observed_value="0.10",
    )

    assert decision.change == "unchanged"
    assert decision.corrective_plan_required is False
    assert decision.broker_orders_authorized is False


@pytest.mark.parametrize(
    ("current_limit", "approved_limit", "observed_value"),
    [
        ("nan", "0.10", "0.09"),
        ("0.10", "Infinity", "0.09"),
        ("0.10", "0.09", "-0.01"),
        ("-0.10", "0.09", "0.01"),
        ("0.10", "-0.09", "0.01"),
        ("", "0.09", "0.01"),
    ],
)
def test_invalid_or_negative_risk_values_fail_closed(
    current_limit: str,
    approved_limit: str,
    observed_value: str,
) -> None:
    with pytest.raises(ValueError, match="finite non-negative decimal"):
        evaluate_approved_maximum(
            limit_id="limit:concentration",
            current_limit=current_limit,
            approved_limit=approved_limit,
            observed_value=observed_value,
        )
