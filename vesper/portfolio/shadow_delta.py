"""Deterministic, in-memory, authority-free proposed shadow deltas."""

import math
from dataclasses import dataclass, field, fields, is_dataclass, replace
from datetime import datetime, timedelta

from vesper.portfolio.shadow_target import (
    ShadowPortfolioTarget,
    _canonical_sha256,
    _close,
    _float_hex,
    _is_number,
    _require_sha256,
)


_MAX_EXACT_FLOAT_INTEGER = 2**53
_shared_require_sha256 = _require_sha256


def _require_sha256(name, value):
    if type(value) is not str:
        raise ValueError(f"{name} must be a 64-character hexadecimal SHA-256")
    _shared_require_sha256(name, value)


def _content(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {
            item.name: _content(getattr(value, item.name))
            for item in fields(value)
            if not item.metadata.get("computed_digest")
        }
    if isinstance(value, dict):
        return {key: _content(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return tuple(_content(item) for item in value)
    return value


def _digest(domain, value):
    return _canonical_sha256(domain, _content(value))


def _require_datetime(name, value):
    if type(value) is not datetime:
        raise ValueError(f"{name} must be a datetime")


def _require_symbol(symbol):
    if type(symbol) is not str or not symbol.strip():
        raise ValueError("symbol must not be blank")


def _require_nonnegative_number(name, value):
    if not _is_number(value) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")


def _time_difference(later, earlier, name):
    try:
        return later - earlier
    except TypeError as exc:
        raise ValueError(f"{name} timestamps must use compatible timezone semantics") from exc


def _same_number(left, right):
    return _float_hex(left) == _float_hex(right) or _close(left, right)


@dataclass(frozen=True, slots=True)
class PriceObservation:
    symbol: str
    price: float
    observed_at: datetime
    external_source_claim: str | None = None

    def __post_init__(self):
        _require_symbol(self.symbol)
        if not _is_number(self.price) or not math.isfinite(self.price) or self.price <= 0:
            raise ValueError("price must be finite and positive")
        object.__setattr__(self, "price", float(self.price))
        _require_datetime("observed_at", self.observed_at)
        if self.external_source_claim is not None and (
            not isinstance(self.external_source_claim, str)
            or not self.external_source_claim.strip()
        ):
            raise ValueError("external_source_claim must be None or nonblank")


@dataclass(frozen=True, slots=True)
class PositionObservation:
    symbol: str
    quantity: int

    def __post_init__(self):
        _require_symbol(self.symbol)
        if (
            type(self.quantity) is not int
            or self.quantity < 0
        ):
            raise ValueError("quantity must be a nonnegative integer share count")


@dataclass(frozen=True, slots=True)
class PendingOrderObservation:
    symbol: str
    state: str
    side: str
    remaining_quantity: int
    external_order_identity_claim: str
    observed_at: datetime

    def __post_init__(self):
        _require_symbol(self.symbol)
        if self.state not in {"open", "pending"}:
            raise ValueError("state must unambiguously be open or pending")
        if self.side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if (
            type(self.remaining_quantity) is not int
            or self.remaining_quantity <= 0
        ):
            raise ValueError("remaining_quantity must be a positive integer")
        if (
            not isinstance(self.external_order_identity_claim, str)
            or not self.external_order_identity_claim.strip()
        ):
            raise ValueError("external_order_identity_claim must not be blank")
        _require_datetime("observed_at", self.observed_at)


@dataclass(frozen=True, slots=True)
class PriceSnapshot:
    as_of_timestamp: datetime
    observations: tuple[PriceObservation, ...]
    snapshot_sha256: str = field(init=False, metadata={"computed_digest": True})

    def __post_init__(self):
        _require_datetime("as_of_timestamp", self.as_of_timestamp)
        if not isinstance(self.observations, tuple) or not self.observations:
            raise ValueError("price observations must be a nonempty immutable tuple")
        validated = []
        for observation in self.observations:
            if not isinstance(observation, PriceObservation):
                raise ValueError("price observations must contain PriceObservation values")
            validated.append(replace(observation))
            if _time_difference(
                observation.observed_at, self.as_of_timestamp, "price"
            ) > timedelta(0):
                raise ValueError("price observed_at must not follow as_of_timestamp")
        symbols = tuple(item.symbol for item in validated)
        if len(symbols) != len(set(symbols)):
            raise ValueError("duplicate price symbol")
        if symbols != tuple(sorted(symbols)):
            raise ValueError("price observations must be in symbol order")
        object.__setattr__(
            self,
            "snapshot_sha256",
            _digest(
                "vesper.shadow.price-snapshot.v1",
                {
                    "as_of_timestamp": self.as_of_timestamp,
                    "observations": self.observations,
                },
            ),
        )


@dataclass(frozen=True, slots=True)
class CurrentPortfolioSnapshot:
    as_of_timestamp: datetime
    portfolio_value: float
    positions: tuple[PositionObservation, ...]
    snapshot_sha256: str = field(init=False, metadata={"computed_digest": True})

    def __post_init__(self):
        _require_datetime("as_of_timestamp", self.as_of_timestamp)
        if not _is_number(self.portfolio_value) or not math.isfinite(
            self.portfolio_value
        ) or self.portfolio_value <= 0:
            raise ValueError("portfolio_value must be finite and positive")
        if not isinstance(self.positions, tuple):
            raise ValueError("positions must be an immutable tuple")
        validated = []
        for position in self.positions:
            if not isinstance(position, PositionObservation):
                raise ValueError("positions must contain PositionObservation values")
            validated.append(replace(position))
        symbols = tuple(item.symbol for item in validated)
        if len(symbols) != len(set(symbols)):
            raise ValueError("duplicate position symbol")
        if symbols != tuple(sorted(symbols)):
            raise ValueError("positions must be in symbol order")
        object.__setattr__(
            self,
            "snapshot_sha256",
            _digest(
                "vesper.shadow.current-portfolio-snapshot.v1",
                {
                    "as_of_timestamp": self.as_of_timestamp,
                    "portfolio_value": self.portfolio_value,
                    "positions": self.positions,
                },
            ),
        )


@dataclass(frozen=True, slots=True)
class PendingOrderSnapshot:
    as_of_timestamp: datetime
    observed_at: datetime
    completeness: str
    account_identity_sha256: str
    source_snapshot_identity_sha256: str
    observations: tuple[PendingOrderObservation, ...]
    snapshot_sha256: str = field(init=False, metadata={"computed_digest": True})

    def __post_init__(self):
        _require_datetime("as_of_timestamp", self.as_of_timestamp)
        _require_datetime("observed_at", self.observed_at)
        if _time_difference(
            self.observed_at, self.as_of_timestamp, "pending order snapshot"
        ) > timedelta(0):
            raise ValueError("observed_at must not follow as_of_timestamp")
        if type(self.completeness) is not str or self.completeness not in {
            "complete", "partial", "ambiguous",
        }:
            raise ValueError("completeness must be complete, partial, or ambiguous")
        _require_sha256("account_identity_sha256", self.account_identity_sha256)
        _require_sha256(
            "source_snapshot_identity_sha256",
            self.source_snapshot_identity_sha256,
        )
        if not isinstance(self.observations, tuple):
            raise ValueError("pending order observations must be an immutable tuple")
        validated = []
        for observation in self.observations:
            if not isinstance(observation, PendingOrderObservation):
                raise ValueError(
                    "pending order observations must contain PendingOrderObservation values"
                )
            validated.append(replace(observation))
            if _time_difference(
                observation.observed_at, self.as_of_timestamp, "pending order"
            ) > timedelta(0):
                raise ValueError("pending order observed_at must not follow as_of_timestamp")
        identities = tuple(
            item.external_order_identity_claim for item in validated
        )
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate external order identity claim")
        symbols = tuple(item.symbol for item in validated)
        if len(symbols) != len(set(symbols)):
            raise ValueError("ambiguous multiple pending orders for one symbol")
        expected = tuple(
            sorted(
                self.observations,
                key=lambda item: (item.symbol, item.external_order_identity_claim),
            )
        )
        if self.observations != expected:
            raise ValueError("pending order observations must be deterministic")
        object.__setattr__(
            self,
            "snapshot_sha256",
            _digest(
                "vesper.shadow.pending-order-snapshot.v1",
                {
                    "as_of_timestamp": self.as_of_timestamp,
                    "observed_at": self.observed_at,
                    "completeness": self.completeness,
                    # Externally carried provenance claims; not self-verification.
                    "account_identity_sha256": self.account_identity_sha256,
                    "source_snapshot_identity_sha256": self.source_snapshot_identity_sha256,
                    "observations": self.observations,
                },
            ),
        )


@dataclass(frozen=True, slots=True)
class PlannerConstraints:
    stale_price_max_age: timedelta
    minimum_trade_notional: float
    lot_size: int
    planner_version: str
    identity_sha256: str = field(init=False, metadata={"computed_digest": True})

    def __post_init__(self):
        if (
            not isinstance(self.stale_price_max_age, timedelta)
            or self.stale_price_max_age <= timedelta(0)
        ):
            raise ValueError("stale_price_max_age must be a positive timedelta")
        _require_nonnegative_number(
            "minimum_trade_notional", self.minimum_trade_notional
        )
        normalized_minimum = (
            0.0 if self.minimum_trade_notional == 0
            else float(self.minimum_trade_notional)
        )
        object.__setattr__(self, "minimum_trade_notional", normalized_minimum)
        if type(self.lot_size) is not int or self.lot_size != 1:
            raise ValueError("lot_size must be the integer-share lot size 1")
        if (
            not isinstance(self.planner_version, str)
            or not self.planner_version.strip()
        ):
            raise ValueError("planner_version must not be blank")
        object.__setattr__(
            self,
            "identity_sha256",
            _digest(
                "vesper.shadow.delta-constraints.v1",
                {
                    "stale_price_max_age_microseconds": (
                        self.stale_price_max_age.days * 86_400_000_000
                        + self.stale_price_max_age.seconds * 1_000_000
                        + self.stale_price_max_age.microseconds
                    ),
                    "minimum_trade_notional": self.minimum_trade_notional,
                    "lot_size": self.lot_size,
                    "planner_version": self.planner_version,
                },
            ),
        )


@dataclass(frozen=True, slots=True)
class ShadowDeltaLine:
    symbol: str
    target_identity_sha256: str
    current_snapshot_identity_sha256: str
    target_weight: float
    current_weight: float
    target_notional: float
    current_notional: float
    execution_price: float
    transaction_cost_rate: float | None
    minimum_trade_notional: float
    lot_size: int
    declared_blocker: str | None
    valid_until_timestamp: datetime
    delta_weight: float = field(init=False, metadata={"derived_claim": True})
    delta_notional: float = field(init=False, metadata={"derived_claim": True})
    raw_rounded_quantity: int = field(init=False, metadata={"derived_claim": True})
    rounded_proposed_quantity: int = field(init=False, metadata={"derived_claim": True})
    reason: str = field(init=False, metadata={"derived_claim": True})
    urgency: str = field(init=False, metadata={"derived_claim": True})
    estimated_cost: float | None = field(init=False, metadata={"derived_claim": True})
    constraint_outcome: str = field(init=False, metadata={"derived_claim": True})

    def __post_init__(self):
        _require_symbol(self.symbol)
        _require_sha256("target_identity_sha256", self.target_identity_sha256)
        _require_sha256(
            "current_snapshot_identity_sha256",
            self.current_snapshot_identity_sha256,
        )
        for name in (
            "target_weight", "current_weight", "target_notional", "current_notional",
        ):
            value = getattr(self, name)
            if type(value) is not float or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be a finite nonnegative float")
        if (
            type(self.execution_price) is not float
            or not math.isfinite(self.execution_price)
            or self.execution_price <= 0
        ):
            raise ValueError("execution_price must be a finite positive float")
        if self.transaction_cost_rate is not None and (
            type(self.transaction_cost_rate) is not float
            or not math.isfinite(self.transaction_cost_rate)
            or self.transaction_cost_rate < 0
        ):
            raise ValueError(
                "transaction_cost_rate must be None or a finite nonnegative float"
            )
        if (
            type(self.minimum_trade_notional) is not float
            or not math.isfinite(self.minimum_trade_notional)
            or self.minimum_trade_notional < 0
        ):
            raise ValueError(
                "minimum_trade_notional must be a finite nonnegative float"
            )
        if type(self.lot_size) is not int or self.lot_size != 1:
            raise ValueError("lot_size must be the integer-share lot size 1")
        blockers = {
            "stale_price", "pending_order", "incomplete_order_snapshot",
        }
        if self.declared_blocker is not None and (
            type(self.declared_blocker) is not str
            or self.declared_blocker not in blockers
        ):
            raise ValueError("declared_blocker is not declared")
        _require_datetime("valid_until_timestamp", self.valid_until_timestamp)

        delta_weight = self.target_weight - self.current_weight
        delta_notional = self.target_notional - self.current_notional
        raw_quantity = delta_notional / self.execution_price
        if not math.isfinite(raw_quantity) or abs(raw_quantity) > _MAX_EXACT_FLOAT_INTEGER:
            raise ValueError("impossible rounding for proposed quantity")
        raw_rounded = math.trunc(raw_quantity / self.lot_size) * self.lot_size

        if self.declared_blocker is not None:
            reason = self.declared_blocker
            outcome = "blocked"
            proposed = 0
        elif _close(delta_notional, 0.0):
            reason = "no_delta"
            outcome = "suppressed"
            proposed = 0
        elif abs(delta_notional) < self.minimum_trade_notional:
            reason = "below_minimum_trade_notional"
            outcome = "suppressed"
            proposed = 0
        elif raw_rounded == 0:
            reason = "zero_after_rounding"
            outcome = "suppressed"
            proposed = 0
        elif abs(raw_rounded * self.execution_price) < self.minimum_trade_notional:
            reason = "below_minimum_trade_notional"
            outcome = "suppressed"
            proposed = 0
        else:
            reason = "actionable_shadow"
            outcome = "actionable"
            proposed = raw_rounded

        if proposed > 0:
            urgency = "increase"
        elif proposed < 0 and self.target_notional == 0:
            urgency = "close"
        elif proposed < 0:
            urgency = "reduce"
        else:
            urgency = "none"
        estimated_cost = None
        if self.transaction_cost_rate is not None:
            estimated_cost = (
                abs(proposed) * self.execution_price * self.transaction_cost_rate
            )
            if not math.isfinite(estimated_cost):
                raise ValueError("impossible estimated cost")

        object.__setattr__(self, "delta_weight", delta_weight)
        object.__setattr__(self, "delta_notional", delta_notional)
        object.__setattr__(self, "raw_rounded_quantity", raw_rounded)
        object.__setattr__(self, "rounded_proposed_quantity", proposed)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "urgency", urgency)
        object.__setattr__(self, "estimated_cost", estimated_cost)
        object.__setattr__(self, "constraint_outcome", outcome)


@dataclass(frozen=True, slots=True)
class ShadowDeltaPlan:
    as_of_timestamp: datetime
    valid_until_timestamp: datetime
    target: ShadowPortfolioTarget
    target_identity_sha256: str
    current_snapshot: CurrentPortfolioSnapshot
    price_snapshot: PriceSnapshot
    order_snapshot: PendingOrderSnapshot
    constraints: PlannerConstraints
    external_provenance_claims: tuple[tuple[str, str], ...]
    lines: tuple[ShadowDeltaLine, ...]
    blocked: bool
    diagnostic_reason: str | None
    plan_sha256: str = field(init=False, metadata={"computed_digest": True})
    research_only: bool = True
    authority_state: str = "shadow"
    risk_approved: bool = False
    execution_authority: bool = False
    broker_authority: bool = False
    order_submission_authority: bool = False
    persistence_authority: bool = False

    def __post_init__(self):
        if type(self.blocked) is not bool:
            raise ValueError("blocked must be a bool")
        expected = _derive_plan(
            target=self.target,
            as_of_timestamp=self.as_of_timestamp,
            current_snapshot=self.current_snapshot,
            price_snapshot=self.price_snapshot,
            order_snapshot=self.order_snapshot,
            constraints=self.constraints,
        )
        for name in (
            "valid_until_timestamp", "target_identity_sha256",
            "external_provenance_claims", "lines", "blocked", "diagnostic_reason",
        ):
            if getattr(self, name) != expected[name]:
                raise ValueError(f"{name} does not match recomputed plan content")
        if self.research_only is not True:
            raise ValueError("research_only must be True")
        if self.authority_state != "shadow":
            raise ValueError("authority_state must be shadow")
        for name in (
            "risk_approved", "execution_authority", "broker_authority",
            "order_submission_authority", "persistence_authority",
        ):
            if getattr(self, name) is not False:
                raise ValueError(f"{name} must be False")
        object.__setattr__(self, "plan_sha256", expected["plan_sha256"])


def _validated_target(target):
    if not isinstance(target, ShadowPortfolioTarget):
        raise ValueError("target must be a ShadowPortfolioTarget")
    try:
        validated = replace(target)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid target: {exc}") from exc
    if validated.blocked or validated.infeasible:
        raise ValueError("target blocked or infeasible")
    return validated


def _revalidated_snapshot(snapshot, expected_type, name):
    if not isinstance(snapshot, expected_type):
        raise ValueError(f"{name} has the wrong type")
    rebuilt = replace(snapshot)
    if rebuilt.snapshot_sha256 != snapshot.snapshot_sha256:
        raise ValueError(f"{name} content does not match snapshot_sha256")
    return rebuilt


def _revalidated_constraints(constraints):
    if not isinstance(constraints, PlannerConstraints):
        raise ValueError("constraints must be PlannerConstraints")
    rebuilt = replace(constraints)
    if rebuilt.identity_sha256 != constraints.identity_sha256:
        raise ValueError("constraints content does not match identity_sha256")
    return rebuilt


def _target_identity(target):
    return _digest("vesper.shadow.portfolio-target.v1", target)


def _external_claims(target, prices, orders):
    claims = [
        ("external.target.adjustment_identity_sha256", target.forecasts[0].adjustment_identity_sha256),
        ("external.target.classification_identity_sha256", target.classification_identity_sha256),
        ("external.target.dataset_identity_sha256", target.forecasts[0].dataset_identity_sha256),
        ("external.target.feature_identity_sha256", target.forecasts[0].feature_identity_sha256),
        ("external.target.model_artifact_sha256", target.forecasts[0].model_artifact_sha256),
        ("external.target.run_manifest_sha256", target.forecasts[0].run_manifest_sha256),
        ("external.target.universe_identity_sha256", target.universe_identity_sha256),
    ]
    claims.extend(
        (f"external.price_source_claim.{item.symbol}", item.external_source_claim)
        for item in prices.observations
        if item.external_source_claim is not None
    )
    claims.extend(
        (f"external.order_identity_claim.{item.symbol}", item.external_order_identity_claim)
        for item in orders.observations
    )
    claims.extend((
        ("external.order_account_identity_sha256", orders.account_identity_sha256),
        (
            "external.order_source_snapshot_identity_sha256",
            orders.source_snapshot_identity_sha256,
        ),
    ))
    return tuple(sorted(claims))


def _derive_plan(*, target, as_of_timestamp, current_snapshot, price_snapshot,
                 order_snapshot, constraints):
    target = _validated_target(target)
    _require_datetime("as_of_timestamp", as_of_timestamp)
    current_snapshot = _revalidated_snapshot(
        current_snapshot, CurrentPortfolioSnapshot, "current snapshot"
    )
    price_snapshot = _revalidated_snapshot(price_snapshot, PriceSnapshot, "price snapshot")
    order_snapshot = _revalidated_snapshot(
        order_snapshot, PendingOrderSnapshot, "order snapshot"
    )
    constraints = _revalidated_constraints(constraints)
    if _time_difference(
        as_of_timestamp, target.valid_until_timestamp, "target validity"
    ) > timedelta(0):
        raise ValueError("target expired")
    if as_of_timestamp != target.as_of_timestamp:
        raise ValueError("as_of_timestamp must match target as_of_timestamp")
    for snapshot in (current_snapshot, price_snapshot, order_snapshot):
        if snapshot.as_of_timestamp != as_of_timestamp:
            raise ValueError("snapshot as_of_timestamp mismatch")
    if not _same_number(current_snapshot.portfolio_value, target.portfolio_value):
        raise ValueError("current snapshot portfolio_value mismatch")

    target_lines = {line.symbol: line for line in target.lines}
    required_symbols = set(target_lines)
    prices = {item.symbol: item for item in price_snapshot.observations}
    positions = {item.symbol: item.quantity for item in current_snapshot.positions}
    orders = {item.symbol: item for item in order_snapshot.observations}
    unknown_positions = set(positions) - required_symbols
    unknown_orders = set(orders) - required_symbols
    unknown_prices = set(prices) - required_symbols
    if unknown_positions or unknown_orders or unknown_prices:
        raise ValueError("unknown symbol in planner snapshots")
    if set(prices) != required_symbols:
        raise ValueError("price snapshot must completely cover target symbols")

    target_holdings = dict(target.current_holdings_weights)
    for symbol in required_symbols:
        observed_weight = positions.get(symbol, 0) * prices[symbol].price / target.portfolio_value
        expected_weight = target_holdings.get(symbol, 0.0)
        if not _same_number(observed_weight, expected_weight):
            raise ValueError("current snapshot does not match target holdings snapshot")

    identity = _target_identity(target)
    rank = {forecast.symbol: forecast.rank for forecast in target.forecasts}
    ordered_symbols = sorted(required_symbols, key=lambda symbol: (rank.get(symbol, math.inf), symbol))
    order_snapshot_block = None
    if order_snapshot.completeness != "complete":
        order_snapshot_block = f"pending order snapshot is {order_snapshot.completeness}"
    elif _time_difference(
        as_of_timestamp, order_snapshot.observed_at, "pending order snapshot freshness"
    ) > constraints.stale_price_max_age:
        order_snapshot_block = "pending order snapshot is stale"
    lines = []
    for symbol in ordered_symbols:
        target_line = target_lines[symbol]
        price_observation = prices[symbol]
        price = price_observation.price
        current_quantity = positions.get(symbol, 0)
        current_notional = current_quantity * price
        current_weight = current_notional / target.portfolio_value
        if order_snapshot_block is not None:
            declared_blocker = "incomplete_order_snapshot"
        elif _time_difference(
            as_of_timestamp, price_observation.observed_at, "price freshness"
        ) > constraints.stale_price_max_age:
            declared_blocker = "stale_price"
        elif symbol in orders:
            declared_blocker = "pending_order"
        else:
            declared_blocker = None

        lines.append(
            ShadowDeltaLine(
                symbol=symbol,
                target_identity_sha256=identity,
                current_snapshot_identity_sha256=current_snapshot.snapshot_sha256,
                target_weight=target_line.target_weight,
                current_weight=current_weight,
                target_notional=target_line.target_notional,
                current_notional=current_notional,
                execution_price=price,
                transaction_cost_rate=target.transaction_cost_rate,
                minimum_trade_notional=constraints.minimum_trade_notional,
                lot_size=constraints.lot_size,
                declared_blocker=declared_blocker,
                valid_until_timestamp=target.valid_until_timestamp,
            )
        )

    blocked = any(line.constraint_outcome == "blocked" for line in lines)
    diagnostic = order_snapshot_block or (
        "one or more symbols fail closed" if blocked else None
    )
    claims = _external_claims(target, price_snapshot, order_snapshot)
    plan_content = {
        "as_of_timestamp": as_of_timestamp,
        "valid_until_timestamp": target.valid_until_timestamp,
        "target_identity_sha256": identity,
        "current_snapshot_sha256": current_snapshot.snapshot_sha256,
        "price_snapshot_sha256": price_snapshot.snapshot_sha256,
        "order_snapshot_sha256": order_snapshot.snapshot_sha256,
        "constraint_identity_sha256": constraints.identity_sha256,
        "external_provenance_claims": claims,
        "lines": tuple(lines),
        "blocked": blocked,
        "diagnostic_reason": diagnostic,
        "research_only": True,
        "authority_state": "shadow",
        "risk_approved": False,
        "execution_authority": False,
        "broker_authority": False,
        "order_submission_authority": False,
        "persistence_authority": False,
    }
    return {
        "valid_until_timestamp": target.valid_until_timestamp,
        "target_identity_sha256": identity,
        "external_provenance_claims": claims,
        "lines": tuple(lines),
        "blocked": blocked,
        "diagnostic_reason": diagnostic,
        "plan_sha256": _digest("vesper.shadow.delta-plan.v1", plan_content),
    }


def build_shadow_delta_plan(*, target, as_of_timestamp, current_positions, prices,
                            pending_orders, pending_order_completeness,
                            pending_orders_observed_at,
                            pending_orders_account_identity_sha256,
                            pending_orders_source_snapshot_identity_sha256,
                            constraints):
    """Build a proposed shadow plan without effects, persistence, or authority."""
    target = _validated_target(target)
    _require_datetime("as_of_timestamp", as_of_timestamp)
    constraints = _revalidated_constraints(constraints)
    try:
        positions = tuple(sorted(tuple(current_positions), key=lambda item: item.symbol))
    except (AttributeError, TypeError) as exc:
        raise ValueError("current_positions must contain typed observations") from exc
    try:
        price_items = tuple(sorted(tuple(prices), key=lambda item: item.symbol))
    except (AttributeError, TypeError) as exc:
        raise ValueError("prices must contain typed observations") from exc
    try:
        order_items = tuple(
            sorted(
                tuple(pending_orders),
                key=lambda item: (item.symbol, item.external_order_identity_claim),
            )
        )
    except (AttributeError, TypeError) as exc:
        raise ValueError("pending_orders must contain typed observations") from exc

    current_snapshot = CurrentPortfolioSnapshot(
        as_of_timestamp, target.portfolio_value, positions
    )
    price_snapshot = PriceSnapshot(as_of_timestamp, price_items)
    if pending_order_completeness is None:
        raise ValueError("pending_order_completeness must be explicit")
    order_snapshot = PendingOrderSnapshot(
        as_of_timestamp,
        pending_orders_observed_at,
        pending_order_completeness,
        pending_orders_account_identity_sha256,
        pending_orders_source_snapshot_identity_sha256,
        order_items,
    )
    derived = _derive_plan(
        target=target,
        as_of_timestamp=as_of_timestamp,
        current_snapshot=current_snapshot,
        price_snapshot=price_snapshot,
        order_snapshot=order_snapshot,
        constraints=constraints,
    )
    return ShadowDeltaPlan(
        as_of_timestamp=as_of_timestamp,
        valid_until_timestamp=derived["valid_until_timestamp"],
        target=target,
        target_identity_sha256=derived["target_identity_sha256"],
        current_snapshot=current_snapshot,
        price_snapshot=price_snapshot,
        order_snapshot=order_snapshot,
        constraints=constraints,
        external_provenance_claims=derived["external_provenance_claims"],
        lines=derived["lines"],
        blocked=derived["blocked"],
        diagnostic_reason=derived["diagnostic_reason"],
    )
