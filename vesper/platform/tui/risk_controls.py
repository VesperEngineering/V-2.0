"""Pure, fail-closed semantics for an already-approved maximum risk limit."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Literal, Self

from pydantic import TypeAdapter, model_validator

from .views import DecimalString, SafeId, StrictModel


_DECIMAL_STRING = TypeAdapter(DecimalString)
_SAFE_ID = TypeAdapter(SafeId)


class RiskLimitDecision(StrictModel):
    """Effect plan only; it never applies a setting or sends an order."""

    limit_id: SafeId
    change: Literal["tighter", "higher", "unchanged"]
    previous_limit: DecimalString
    effective_limit: DecimalString
    observed_value: DecimalString
    new_risk_blocked: bool
    corrective_plan_required: bool
    broker_orders_authorized: Literal[False] = False
    order_approval_required: bool

    @model_validator(mode="after")
    def require_safe_effect_shape(self) -> Self:
        if self.corrective_plan_required and (
            self.change != "tighter" or not self.new_risk_blocked
        ):
            raise ValueError("only a violated tighter limit creates a corrective plan")
        if self.order_approval_required is not self.corrective_plan_required:
            raise ValueError("corrective plan orders require separate approval")
        return self


def _non_negative_decimal(value: object) -> tuple[DecimalString, Decimal]:
    try:
        validated = _DECIMAL_STRING.validate_python(value, strict=True)
        parsed = Decimal(validated)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("value must be a finite non-negative decimal") from error
    if not parsed.is_finite() or parsed < 0:
        raise ValueError("value must be a finite non-negative decimal")
    return validated, parsed


def evaluate_approved_maximum(
    *,
    limit_id: SafeId,
    current_limit: DecimalString,
    approved_limit: DecimalString,
    observed_value: DecimalString,
) -> RiskLimitDecision:
    """Plan the effect of one approved upper bound without applying any effect."""

    validated_id = _SAFE_ID.validate_python(limit_id, strict=True)
    previous_text, previous = _non_negative_decimal(current_limit)
    approved_text, approved = _non_negative_decimal(approved_limit)
    observed_text, observed = _non_negative_decimal(observed_value)
    change: Literal["tighter", "higher", "unchanged"]
    if approved < previous:
        change = "tighter"
    elif approved > previous:
        change = "higher"
    else:
        change = "unchanged"
    violated = observed > approved
    corrective = change == "tighter" and violated
    return RiskLimitDecision(
        limit_id=validated_id,
        change=change,
        previous_limit=previous_text,
        effective_limit=approved_text,
        observed_value=observed_text,
        new_risk_blocked=violated,
        corrective_plan_required=corrective,
        broker_orders_authorized=False,
        order_approval_required=corrective,
    )
