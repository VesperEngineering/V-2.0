"""Pure Live readiness and transition views; no broker or command execution.

A future approved broker port may supply ``BrokerTransitionInput``. This module
only compares typed values and never reads an account, copies Paper positions,
submits an order, or changes the active portfolio.
"""

from __future__ import annotations

from decimal import Decimal, Inexact, Rounded, localcontext
from typing import Annotated, Literal, TypeAlias, cast

from pydantic import AfterValidator, model_validator

from vesper.platform.tui.views import (
    LiveReadinessView,
    ReadinessGate,
    SafeId,
    StrictModel,
    TransitionOrderView,
    TransitionPlanView,
    UtcDateTime,
)


ReadinessGateName: TypeAlias = Literal[
    "broker",
    "account",
    "data",
    "model",
    "strategy",
    "risk",
    "reconciliation",
    "incident",
    "authority",
]
_GATE_NAMES: tuple[ReadinessGateName, ...] = (
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
_MAX_FIXED_POINT_CHARS = 128
_EXACT_SUBTRACTION_PRECISION = 2 * _MAX_FIXED_POINT_CHARS + 1


def _require_representable_decimal(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise ValueError("position quantity must be finite")
    _require_fixed_point_size(value, "position quantity")
    return value


FiniteDecimal = Annotated[Decimal, AfterValidator(_require_representable_decimal)]


class BrokerPositionInput(StrictModel):
    symbol: SafeId
    quantity: FiniteDecimal


class DesiredPositionInput(StrictModel):
    symbol: SafeId
    quantity: FiniteDecimal


class BrokerTransitionInput(StrictModel):
    source: Literal["broker"]
    broker_positions_as_of_utc: UtcDateTime
    desired_portfolio_id: SafeId
    broker_positions: tuple[BrokerPositionInput, ...]
    desired_positions: tuple[DesiredPositionInput, ...]

    @model_validator(mode="after")
    def require_unique_symbols(self) -> BrokerTransitionInput:
        for label, rows in (
            ("broker positions", self.broker_positions),
            ("desired positions", self.desired_positions),
        ):
            symbols = tuple(row.symbol for row in rows)
            if len(set(symbols)) != len(symbols):
                raise ValueError(f"duplicate symbol in {label}")
        return self


def build_live_readiness(
    *,
    broker: ReadinessGate,
    account: ReadinessGate,
    data: ReadinessGate,
    model: ReadinessGate,
    strategy: ReadinessGate,
    risk: ReadinessGate,
    reconciliation: ReadinessGate,
    incident: ReadinessGate,
    authority: ReadinessGate,
) -> LiveReadinessView:
    """Index the exact nine named gates and derive the enabled value."""

    indexed = {
        "broker": broker,
        "account": account,
        "data": data,
        "model": model,
        "strategy": strategy,
        "risk": risk,
        "reconciliation": reconciliation,
        "incident": incident,
        "authority": authority,
    }
    return LiveReadinessView(
        **indexed,
        enabled=all(gate.state == "ready" for gate in indexed.values()),
    )


def unavailable_live_readiness() -> LiveReadinessView:
    """Return the truthful default before reviewed Live sources exist."""

    return build_live_readiness(
        **{
            name: ReadinessGate(
                state="unavailable",
                reason=f"No reviewed {name} readiness source is configured.",
            )
            for name in _GATE_NAMES
        },
    )


def build_transition_plan(
    inputs: BrokerTransitionInput | None,
) -> TransitionPlanView | None:
    """Describe broker-to-desired differences without submitting orders."""

    if inputs is None:
        return None
    current = {row.symbol: row.quantity for row in inputs.broker_positions}
    desired = {row.symbol: row.quantity for row in inputs.desired_positions}
    orders: list[TransitionOrderView] = []
    for symbol in sorted(current.keys() | desired.keys()):
        delta = _subtract_exact(
            desired.get(symbol, Decimal(0)),
            current.get(symbol, Decimal(0)),
        )
        if delta == 0:
            continue
        orders.append(
            TransitionOrderView(
                symbol=symbol,
                side="buy" if delta > 0 else "sell",
                quantity=_decimal_string(delta.copy_abs()),
                approval_required=True,
            )
        )
    return TransitionPlanView(
        broker_positions_as_of_utc=inputs.broker_positions_as_of_utc,
        desired_portfolio_id=inputs.desired_portfolio_id,
        orders=tuple(orders),
    )


def _subtract_exact(desired: Decimal, current: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = _EXACT_SUBTRACTION_PRECISION
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        context.clear_flags()
        try:
            return desired - current
        except (Inexact, Rounded) as error:
            raise ValueError("transition quantity subtraction must be exact") from error


def _decimal_string(value: Decimal) -> str:
    if value == 0:
        return "0"
    _require_fixed_point_size(value, "transition order quantity")
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _require_fixed_point_size(value: Decimal, label: str) -> None:
    if _canonical_fixed_point_length(value) > _MAX_FIXED_POINT_CHARS:
        raise ValueError(f"{label} exceeds the 128-character fixed-point limit")


def _canonical_fixed_point_length(value: Decimal) -> int:
    """Return the canonical fixed-point length without allocating its text."""

    if value.is_zero():
        return 1
    components = value.as_tuple()
    exponent = cast(int, components.exponent)
    digit_count = len(components.digits)
    if exponent < 0:
        trailing_zeros = 0
        for digit in reversed(components.digits):
            if digit != 0:
                break
            trailing_zeros += 1
        trimmed = min(trailing_zeros, -exponent)
        digit_count -= trimmed
        exponent += trimmed
    if exponent >= 0:
        body_length = digit_count + exponent
    elif digit_count + exponent > 0:
        body_length = digit_count + 1
    else:
        body_length = 2 - exponent
    return components.sign + body_length
