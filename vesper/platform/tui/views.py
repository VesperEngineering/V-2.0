"""Strict presentation models for the local V20 operations console."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal, Self, TypeAlias, get_args

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)


def _require_finite_float(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("floating-point values must be finite")
    return value


def _require_utc(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError("timestamps must be timezone-aware UTC")
    return value


_UTC_TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|\+00:00)$"
)


def _require_utc_timestamp_shape(value: object) -> object:
    if isinstance(value, str):
        if _UTC_TIMESTAMP_PATTERN.fullmatch(value) is None:
            raise ValueError("timestamps must use the shared zero-offset UTC format")
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def _serialize_utc(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


FiniteFloat = Annotated[float, AfterValidator(_require_finite_float)]
NonNegativeFiniteFloat = Annotated[FiniteFloat, Field(ge=0)]
ConfidenceFloat = Annotated[FiniteFloat, Field(ge=0, le=1)]
UtcDateTime = Annotated[
    datetime,
    BeforeValidator(_require_utc_timestamp_shape),
    AfterValidator(_require_utc),
    PlainSerializer(_serialize_utc, return_type=str, when_used="json"),
]
NonEmptyStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=512),
]
SafeId = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    ),
]
Sha256Hex = Annotated[
    str,
    StringConstraints(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"),
]
DecimalString = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$",
    ),
]
WireUInt = Annotated[int, Field(ge=0, le=2**64 - 1)]
Priority = Annotated[int, Field(ge=0, le=100)]


class StrictModel(BaseModel):
    """Reject coercion and undeclared input at every presentation boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Freshness(StrEnum):
    LOADING = "loading"
    FRESH = "fresh"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class OperatingMode(StrEnum):
    UNKNOWN = "unknown"
    STOPPED = "stopped"
    SHADOW = "shadow"
    PAPER = "paper"
    LIVE = "live"


class CapabilityState(StrEnum):
    ENABLED = "enabled"
    READ_ONLY = "read-only"
    DISABLED = "disabled"


class CapabilityView(StrictModel):
    capability_id: NonEmptyStr
    state: CapabilityState
    reason: NonEmptyStr | None = None


class AlertView(StrictModel):
    alert_id: SafeId
    severity: Literal["info", "active", "waiting", "urgent", "resolved"]
    summary: NonEmptyStr
    created_at_utc: UtcDateTime
    resolved_at_utc: UtcDateTime | None


class HeaderView(StrictModel):
    operating_mode: OperatingMode
    operating_mode_freshness: Freshness
    operating_mode_reason: NonEmptyStr | None
    data_freshness: Freshness
    data_age_seconds: NonNegativeFiniteFloat | None
    regime_label: str
    regime_confidence: ConfidenceFloat | None
    portfolio_value: FiniteFloat | None
    next_rebalance_at_utc: UtcDateTime | None
    rebalance_blockers: tuple[str, ...] | None
    active_agent: str | None
    agent_queue_length: WireUInt | None
    qwen_state: str
    qwen_context_percent: FiniteFloat | None
    current_time_utc: UtcDateTime
    market_session: str


class ShellSnapshot(StrictModel):
    state_version: WireUInt
    generated_at_utc: UtcDateTime
    header: HeaderView
    alerts: tuple[AlertView, ...] | None
    capabilities: tuple[CapabilityView, ...]


class ScreenView(StrictModel):
    freshness: Freshness
    as_of_utc: UtcDateTime | None
    source: NonEmptyStr
    error: str | None

    @model_validator(mode="after")
    def require_truthful_freshness(self) -> Self:
        if self.freshness in {Freshness.FRESH, Freshness.STALE} and self.as_of_utc is None:
            raise ValueError("fresh and stale views require as_of_utc")
        if self.freshness in {Freshness.STALE, Freshness.UNAVAILABLE} and not (
            self.error and self.error.strip()
        ):
            raise ValueError("stale and unavailable views require an error reason")
        if self.freshness is Freshness.FRESH and self.error is not None:
            raise ValueError("fresh views cannot report an error")
        return self


class PortfolioRow(StrictModel):
    symbol: SafeId
    description: str | None
    asset_type: Literal["stock", "etf", "cash"]
    quantity: DecimalString
    price: DecimalString | None
    market_value: DecimalString | None
    current_weight: FiniteFloat
    proposed_weight: FiniteFloat | None
    approved_weight: FiniteFloat | None
    change_state: Literal["unchanged", "proposed", "approved", "executing", "reconciling"]
    confirmed_rank: WireUInt | None
    reconciliation: Literal["not-required", "pending", "matched", "mismatch", "unavailable"]


class AgentCard(StrictModel):
    work_id: SafeId
    agent: NonEmptyStr
    title: NonEmptyStr
    stage: Literal["backlog", "queued", "running", "waiting", "done", "failed"]
    priority: Priority
    urgent: bool
    elapsed_seconds: NonNegativeFiniteFloat | None
    model: str | None
    affected_areas: tuple[str, ...]


class TimelineRow(StrictModel):
    event_id: SafeId
    occurred_at_utc: UtcDateTime
    impact: bool
    severity: Literal["info", "active", "waiting", "urgent", "resolved"]
    summary: NonEmptyStr
    agent_id: SafeId | None
    symbol: SafeId | None
    model_id: SafeId | None
    approval_id: SafeId | None
    order_id: SafeId | None
    evidence_ids: tuple[SafeId, ...]


class FillRow(StrictModel):
    fill_id: SafeId
    quantity: DecimalString
    price: DecimalString
    fee: DecimalString
    filled_at_utc: UtcDateTime


class OrderRow(StrictModel):
    order_id: SafeId
    symbol: SafeId
    side: Literal["buy", "sell"]
    quantity: DecimalString
    status: Literal["proposed", "approved", "submitted", "partial", "filled", "rejected", "cancelled"]
    submitted_at_utc: UtcDateTime | None
    broker_order_id: str | None
    fills: tuple[FillRow, ...]
    expected_price: DecimalString | None
    actual_price: DecimalString | None
    reconciliation: Literal["pending", "matched", "mismatch", "unavailable"]


class ModelOpinionRow(StrictModel):
    model_id: SafeId
    regime: NonEmptyStr
    confidence: ConfidenceFloat
    as_of_utc: UtcDateTime


class CandidateRow(StrictModel):
    candidate_id: SafeId
    family: NonEmptyStr
    strategy: Literal["ml_model", "momentum"]
    status: Literal["training", "evaluating", "passed", "failed", "rejected", "active", "rollback"]
    evidence_ids: tuple[SafeId, ...]
    created_at_utc: UtcDateTime


class RiskLimitRow(StrictModel):
    limit_id: SafeId
    current_value: DecimalString
    proposed_value: DecimalString | None
    status: Literal["within", "violated", "pending", "unavailable"]


class ApprovalRow(StrictModel):
    approval_id: SafeId
    state: Literal["pending", "approved", "held", "rejected", "rework", "stale"]
    reason: str | None
    evidence_ids: tuple[SafeId, ...]
    requested_at_utc: UtcDateTime


class SourceRow(StrictModel):
    source_id: SafeId
    freshness: Freshness
    as_of_utc: UtcDateTime | None
    age_seconds: NonNegativeFiniteFloat | None
    coverage: str | None
    error: str | None
    consumers: tuple[NonEmptyStr, ...]

    @model_validator(mode="after")
    def require_truthful_freshness(self) -> Self:
        if self.freshness in {Freshness.FRESH, Freshness.STALE} and self.as_of_utc is None:
            raise ValueError("fresh and stale sources require as_of_utc")
        if self.freshness in {Freshness.STALE, Freshness.UNAVAILABLE} and not (
            self.error and self.error.strip()
        ):
            raise ValueError("stale and unavailable sources require an error reason")
        if self.freshness is Freshness.FRESH and self.error is not None:
            raise ValueError("fresh sources cannot report an error")
        return self


class EvidenceRow(StrictModel):
    evidence_id: SafeId
    evidence_type: NonEmptyStr
    source: NonEmptyStr
    created_at_utc: UtcDateTime
    sha256: Sha256Hex


class MemoryRow(StrictModel):
    memory_id: SafeId
    status: Literal["core", "archived"]
    summary: NonEmptyStr
    evidence_ids: tuple[SafeId, ...]
    updated_at_utc: UtcDateTime


class ServiceRow(StrictModel):
    service_id: SafeId
    state: Literal["running", "paused", "stopped", "failed", "unavailable"]
    health_reason: str | None
    observed_at_utc: UtcDateTime


class RepositoryRow(StrictModel):
    repository_id: SafeId
    freshness: Freshness
    as_of_utc: UtcDateTime | None
    source: NonEmptyStr
    error: str | None
    branch: NonEmptyStr | None
    revision: NonEmptyStr | None
    clean: bool | None
    worktrees: tuple[NonEmptyStr, ...]
    unpushed_commit_count: WireUInt | None

    @model_validator(mode="after")
    def require_truthful_freshness(self) -> Self:
        if self.freshness in {Freshness.FRESH, Freshness.STALE} and self.as_of_utc is None:
            raise ValueError("fresh and stale repositories require as_of_utc")
        if self.freshness in {Freshness.STALE, Freshness.UNAVAILABLE} and not (
            self.error and self.error.strip()
        ):
            raise ValueError("stale and unavailable repositories require an error reason")
        if self.freshness is Freshness.FRESH and self.error is not None:
            raise ValueError("fresh repositories cannot report an error")
        return self


class MetricRow(StrictModel):
    metric_id: SafeId
    value: FiniteFloat | None
    unit: NonEmptyStr
    freshness: Freshness
    observed_at_utc: UtcDateTime | None
    error: str | None

    @model_validator(mode="after")
    def require_truthful_freshness(self) -> Self:
        has_reason = bool(self.error and self.error.strip())
        if self.freshness is Freshness.FRESH:
            if self.value is None or self.observed_at_utc is None or self.error is not None:
                raise ValueError("fresh metrics require a value and time without an error")
        elif self.freshness is Freshness.STALE:
            if self.value is None or self.observed_at_utc is None or not has_reason:
                raise ValueError("stale metrics require a value, time, and error reason")
        elif self.freshness is Freshness.UNAVAILABLE:
            if self.value is not None or not has_reason:
                raise ValueError("unavailable metrics require no value and an error reason")
        elif any(value is not None for value in (self.value, self.observed_at_utc, self.error)):
            raise ValueError("loading metrics cannot report value, time, or error")
        return self


class ReturnComponentRow(StrictModel):
    component: Literal["price", "dividends", "cash-interest", "fees", "sp500-total-return"]
    value: DecimalString


AlertRow = AlertView


class ImpactView(ScreenView):
    holdings: tuple[PortfolioRow, ...]
    events: tuple[TimelineRow, ...]
    agents: tuple[AgentCard, ...]


class PortfolioView(ScreenView):
    rows: tuple[PortfolioRow, ...]
    returns_today: tuple[ReturnComponentRow, ...]
    returns_since_rebalance: tuple[ReturnComponentRow, ...]
    returns_since_start: tuple[ReturnComponentRow, ...]
    metrics: tuple[MetricRow, ...]
    history: tuple[TimelineRow, ...]
    rank_source: NonEmptyStr | None


class OrdersView(ScreenView):
    rows: tuple[OrderRow, ...]
    reconciliation_agents: tuple[AgentCard, ...]
    history: tuple[TimelineRow, ...]


class AgentsView(ScreenView):
    rows: tuple[AgentCard, ...]
    history: tuple[TimelineRow, ...]


class ModelsView(ScreenView):
    opinions: tuple[ModelOpinionRow, ...]
    candidates: tuple[CandidateRow, ...]
    metrics: tuple[MetricRow, ...]
    evidence: tuple[EvidenceRow, ...]


class TimelineView(ScreenView):
    rows: tuple[TimelineRow, ...]
    hidden_event_count: WireUInt


class RiskView(ScreenView):
    limits: tuple[RiskLimitRow, ...]
    approvals: tuple[ApprovalRow, ...]
    alerts: tuple[AlertRow, ...]
    metrics: tuple[MetricRow, ...]


class DataView(ScreenView):
    sources: tuple[SourceRow, ...]
    evidence: tuple[EvidenceRow, ...]


class MemoryView(ScreenView):
    rows: tuple[MemoryRow, ...]
    history: tuple[TimelineRow, ...]


class SystemView(ScreenView):
    services: tuple[ServiceRow, ...]
    metrics: tuple[MetricRow, ...]
    repositories: tuple[RepositoryRow, ...]


EventTarget: TypeAlias = Literal[
    "shell.alerts",
    "impact.holdings",
    "impact.events",
    "impact.agents",
    "portfolio.rows",
    "portfolio.returns-today",
    "portfolio.returns-since-rebalance",
    "portfolio.returns-since-start",
    "portfolio.metrics",
    "portfolio.history",
    "orders.rows",
    "orders.reconciliation-agents",
    "orders.history",
    "agents.rows",
    "agents.history",
    "models.opinions",
    "models.candidates",
    "models.metrics",
    "models.evidence",
    "timeline.rows",
    "risk.limits",
    "risk.approvals",
    "risk.alerts",
    "risk.metrics",
    "data.sources",
    "data.evidence",
    "memory.rows",
    "memory.history",
    "system.services",
    "system.metrics",
    "system.repositories",
]
_EVENT_TARGET_ORDER = {target: index for index, target in enumerate(get_args(EventTarget))}


class WindowOmission(StrictModel):
    target: EventTarget
    omitted_count: Annotated[WireUInt, Field(gt=0)] | None


class ScreenMeta(StrictModel):
    freshness: Freshness
    as_of_utc: UtcDateTime | None
    source: NonEmptyStr
    error: str | None

    @model_validator(mode="after")
    def require_truthful_metadata(self) -> Self:
        if self.freshness in {Freshness.FRESH, Freshness.STALE} and self.as_of_utc is None:
            raise ValueError("fresh and stale screen metadata require as_of_utc")
        if self.freshness in {Freshness.STALE, Freshness.UNAVAILABLE} and not (
            self.error and self.error.strip()
        ):
            raise ValueError("stale and unavailable screen metadata require an error reason")
        if self.freshness is Freshness.FRESH and self.error is not None:
            raise ValueError("fresh screen metadata cannot report an error")
        return self


class EventPresentation(StrictModel):
    generated_at_utc: UtcDateTime
    header: HeaderView
    control_version: WireUInt
    control_hash: Sha256Hex
    window_omissions: tuple[WindowOmission, ...]
    impact: ScreenMeta
    portfolio: ScreenMeta
    orders: ScreenMeta
    agents: ScreenMeta
    models: ScreenMeta
    timeline: ScreenMeta
    risk: ScreenMeta
    data: ScreenMeta
    memory: ScreenMeta
    system: ScreenMeta
    portfolio_rank_source: NonEmptyStr | None
    timeline_hidden_event_count: WireUInt

    @model_validator(mode="after")
    def require_canonical_omissions(self) -> Self:
        targets = tuple(item.target for item in self.window_omissions)
        if len(set(targets)) != len(targets):
            raise ValueError("event presentation omission targets must be unique")
        if targets != tuple(sorted(targets, key=_EVENT_TARGET_ORDER.__getitem__)):
            raise ValueError("event presentation omission targets must use canonical order")
        return self


class CommandSpecView(StrictModel):
    command_type: NonEmptyStr
    payload_model: NonEmptyStr
    capability_id: SafeId
    reason_rule: Literal["forbidden", "optional", "required"]
    confirmation_level: Literal["none", "confirm", "double-confirm", "typed-live"]


class ConsoleSnapshot(StrictModel):
    shell: ShellSnapshot
    control_version: WireUInt
    control_hash: Sha256Hex
    command_specs: tuple[CommandSpecView, ...]
    window_omissions: tuple[WindowOmission, ...]
    impact: ImpactView
    portfolio: PortfolioView
    orders: OrdersView
    agents: AgentsView
    models: ModelsView
    timeline: TimelineView
    risk: RiskView
    data: DataView
    memory: MemoryView
    system: SystemView

    @model_validator(mode="after")
    def require_canonical_omissions(self) -> Self:
        targets = tuple(item.target for item in self.window_omissions)
        if len(set(targets)) != len(targets):
            raise ValueError("window omission targets must be unique")
        if targets != tuple(sorted(targets, key=_EVENT_TARGET_ORDER.__getitem__)):
            raise ValueError("window omission targets must use canonical order")
        return self


EventEntity: TypeAlias = (
    PortfolioRow
    | AgentCard
    | TimelineRow
    | OrderRow
    | ModelOpinionRow
    | CandidateRow
    | RiskLimitRow
    | ApprovalRow
    | SourceRow
    | EvidenceRow
    | MemoryRow
    | ServiceRow
    | RepositoryRow
    | MetricRow
    | ReturnComponentRow
    | AlertRow
)
EntityType: TypeAlias = Literal[
    "portfolio-row",
    "agent-card",
    "timeline-row",
    "order-row",
    "model-opinion-row",
    "candidate-row",
    "risk-limit-row",
    "approval-row",
    "source-row",
    "evidence-row",
    "memory-row",
    "service-row",
    "repository-row",
    "metric-row",
    "return-component-row",
    "alert-row",
]


_EVENT_TYPES: dict[str, tuple[type[StrictModel], str]] = {
    "portfolio-row": (PortfolioRow, "symbol"),
    "agent-card": (AgentCard, "work_id"),
    "timeline-row": (TimelineRow, "event_id"),
    "order-row": (OrderRow, "order_id"),
    "model-opinion-row": (ModelOpinionRow, "model_id"),
    "candidate-row": (CandidateRow, "candidate_id"),
    "risk-limit-row": (RiskLimitRow, "limit_id"),
    "approval-row": (ApprovalRow, "approval_id"),
    "source-row": (SourceRow, "source_id"),
    "evidence-row": (EvidenceRow, "evidence_id"),
    "memory-row": (MemoryRow, "memory_id"),
    "service-row": (ServiceRow, "service_id"),
    "repository-row": (RepositoryRow, "repository_id"),
    "metric-row": (MetricRow, "metric_id"),
    "return-component-row": (ReturnComponentRow, "component"),
    "alert-row": (AlertRow, "alert_id"),
}

_EVENT_TARGETS: dict[str, frozenset[str]] = {
    "portfolio-row": frozenset({"impact.holdings", "portfolio.rows"}),
    "agent-card": frozenset({"impact.agents", "orders.reconciliation-agents", "agents.rows"}),
    "timeline-row": frozenset(
        {
            "impact.events",
            "portfolio.history",
            "orders.history",
            "agents.history",
            "timeline.rows",
            "memory.history",
        }
    ),
    "order-row": frozenset({"orders.rows"}),
    "model-opinion-row": frozenset({"models.opinions"}),
    "candidate-row": frozenset({"models.candidates"}),
    "risk-limit-row": frozenset({"risk.limits"}),
    "approval-row": frozenset({"risk.approvals"}),
    "source-row": frozenset({"data.sources"}),
    "evidence-row": frozenset({"models.evidence", "data.evidence"}),
    "memory-row": frozenset({"memory.rows"}),
    "service-row": frozenset({"system.services"}),
    "repository-row": frozenset({"system.repositories"}),
    "metric-row": frozenset(
        {"portfolio.metrics", "models.metrics", "risk.metrics", "system.metrics"}
    ),
    "return-component-row": frozenset(
        {
            "portfolio.returns-today",
            "portfolio.returns-since-rebalance",
            "portfolio.returns-since-start",
        }
    ),
    "alert-row": frozenset({"shell.alerts", "risk.alerts"}),
}


class EventPayload(StrictModel):
    entity_type: EntityType
    entity_id: SafeId
    operation: Literal["upsert", "remove"]
    entity: EventEntity | None
    targets: Annotated[tuple[EventTarget, ...], Field(min_length=1, max_length=8)]
    presentation: EventPresentation

    @field_validator("entity", mode="before")
    @classmethod
    def parse_exact_entity_type(cls, entity: object, info: ValidationInfo) -> object:
        entity_type = info.data.get("entity_type")
        spec = _EVENT_TYPES.get(entity_type) if isinstance(entity_type, str) else None
        if spec is None or entity is None or isinstance(entity, spec[0]):
            return entity
        if isinstance(entity, dict):
            if info.mode == "json":
                return spec[0].model_validate_json(json.dumps(entity, separators=(",", ":")))
            return spec[0].model_validate(entity, strict=True)
        return entity

    @model_validator(mode="after")
    def require_matching_entity(self) -> Self:
        if len(set(self.targets)) != len(self.targets):
            raise ValueError("event targets must be unique")
        if self.targets != tuple(sorted(self.targets, key=_EVENT_TARGET_ORDER.__getitem__)):
            raise ValueError("event targets must use canonical order")
        if any(target not in _EVENT_TARGETS[self.entity_type] for target in self.targets):
            raise ValueError("event target is incompatible with entity_type")
        if self.operation == "remove":
            if self.entity is not None:
                raise ValueError("remove events require a null entity")
            return self
        if self.entity is None:
            raise ValueError("upsert events require a complete entity")
        expected_type, id_field = _EVENT_TYPES[self.entity_type]
        if not isinstance(self.entity, expected_type):
            raise ValueError("event entity_type does not match entity")
        if getattr(self.entity, id_field) != self.entity_id:
            raise ValueError("event entity_id does not match entity")
        return self


def event_model(entity_type: str) -> type[StrictModel] | None:
    """Return the exact event row model for strict diagnostic classification."""

    spec = _EVENT_TYPES.get(entity_type)
    return None if spec is None else spec[0]
