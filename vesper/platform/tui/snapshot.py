"""Pure aggregation of immutable projection samples into console snapshots."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Final, TypeAlias, cast

from vesper.platform.tui.contracts import MessageType, SnapshotPayload, WireEnvelope
from vesper.platform.tui.live_readiness import unavailable_live_readiness
from vesper.platform.tui.ports import (
    AgentFacts,
    AttentionFacts,
    DataFacts,
    MemoryFacts,
    MEMORY_AGENT_USAGE_UNAVAILABLE,
    ModelFacts,
    OrderFacts,
    PlatformRuntimeFacts,
    PortfolioFacts,
    RiskFacts,
    SourceSample,
    SystemFacts,
    TimelineFacts,
)
from vesper.platform.tui.protocol import MAX_FRAME_BYTES
from vesper.platform.tui.views import (
    AgentCard,
    AgentsView,
    AlertView,
    BlockedActionRow,
    CapabilityState,
    CapabilityView,
    ConsoleSnapshot,
    CircuitBreakerView,
    DataView,
    EventPayload,
    EventPresentation,
    EventTarget,
    EvidenceRow,
    Freshness,
    HeaderView,
    ImpactView,
    MemoryRow,
    MemoryView,
    MetricRow,
    ModelGateRow,
    ModelOpinionRow,
    ModelsView,
    OperatingMode,
    OrderRow,
    OrdersView,
    PortfolioRow,
    PortfolioView,
    QwenStatusView,
    RepositoryRow,
    ReturnComponentRow,
    RiskLimitRow,
    RiskView,
    ScreenMeta,
    ScreenView,
    ServiceRow,
    ShellSnapshot,
    SourceRow,
    SystemHealthRow,
    SystemView,
    TimelineRow,
    TimelineView,
    WindowOmission,
)


ProjectionSamples: TypeAlias = Mapping[str, SourceSample[object]]

AGENT_SOURCE_ID: Final = "native.agents"
PORTFOLIO_SOURCE_ID: Final = "native.portfolio"
ORDER_SOURCE_ID: Final = "native.orders"
MODEL_SOURCE_ID: Final = "native.models"
RISK_SOURCE_ID: Final = "legacy.risk"
DATA_SOURCE_ID: Final = "native.data"
MEMORY_SOURCE_ID: Final = "native.memory"
REPOSITORY_SYSTEM_SOURCE_ID: Final = "repository.system"
WINDOWS_SYSTEM_SOURCE_ID: Final = "windows.system"
TIMELINE_SOURCE_ID: Final = "events.timeline"
PLATFORM_RUNTIME_SOURCE_ID: Final = "platform.runtime"
ATTENTION_SOURCE_ID: Final = "operations.attention"
NOTIFICATION_HEALTH_SOURCE_ID: Final = "operations.notification-health"

SOURCE_IDS: Final = frozenset(
    {
        AGENT_SOURCE_ID,
        PORTFOLIO_SOURCE_ID,
        ORDER_SOURCE_ID,
        MODEL_SOURCE_ID,
        RISK_SOURCE_ID,
        DATA_SOURCE_ID,
        MEMORY_SOURCE_ID,
        REPOSITORY_SYSTEM_SOURCE_ID,
        WINDOWS_SYSTEM_SOURCE_ID,
        TIMELINE_SOURCE_ID,
        PLATFORM_RUNTIME_SOURCE_ID,
        ATTENTION_SOURCE_ID,
        NOTIFICATION_HEALTH_SOURCE_ID,
    }
)

_EXPECTED_FACT_TYPES: Final = {
    AGENT_SOURCE_ID: AgentFacts,
    PORTFOLIO_SOURCE_ID: PortfolioFacts,
    ORDER_SOURCE_ID: OrderFacts,
    MODEL_SOURCE_ID: ModelFacts,
    RISK_SOURCE_ID: RiskFacts,
    DATA_SOURCE_ID: DataFacts,
    MEMORY_SOURCE_ID: MemoryFacts,
    REPOSITORY_SYSTEM_SOURCE_ID: SystemFacts,
    WINDOWS_SYSTEM_SOURCE_ID: SystemFacts,
    TIMELINE_SOURCE_ID: TimelineFacts,
    PLATFORM_RUNTIME_SOURCE_ID: PlatformRuntimeFacts,
    ATTENTION_SOURCE_ID: AttentionFacts,
    NOTIFICATION_HEALTH_SOURCE_ID: SystemFacts,
}

_ACTION_CAPABILITY_IDS: Final = (
    "note.add",
    "alert.dismiss",
    "layout.reset",
    "approval.approve",
    "approval.hold",
    "approval.reject",
    "approval.rework",
    "agent.send-message",
    "agent.enqueue",
    "agent.pause",
    "agent.stop",
    "agent.retry",
    "agent.set-priority",
    "risk.propose-limit",
    "trading.pause",
    "trading.emergency-stop",
    "service.pause",
    "service.restart",
    "runtime.start",
    "runtime.stop-safe",
    "runtime.stop-force",
    "runtime.prepare-shutdown",
    "mode.switch",
    "mode.leave-live",
    "mode.enable-live",
    "model.request-promotion",
    "model.request-rollback",
    "memory.compress-now",
    "backup.create",
    "backup.restore",
    "source-control.push",
)
_UNAVAILABLE_MODE_REASON: Final = "No reviewed runtime-status adapter is configured."
_DISABLED_ACTION_REASON: Final = "No controller-owned command adapter is configured."
_MAX_WINDOW_ROWS: Final = 10_000
_MAX_WIRE_UINT: Final = 2**64 - 1
_MAX_VIEW_TEXT: Final = 512
_KEEP_NEWEST_TARGETS: Final = frozenset(
    {
        "impact.events",
        "portfolio.history",
        "orders.history",
        "agents.history",
        "timeline.rows",
        "memory.history",
    }
)

_TARGET_ORDER: Final = (
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
)


@dataclass(frozen=True, slots=True)
class ControlState:
    version: int
    hash: str

    def __post_init__(self) -> None:
        if type(self.version) is not int or not 0 <= self.version <= _MAX_WIRE_UINT:
            raise ValueError("control version is outside the wire range")
        if len(self.hash) != 64 or any(
            character not in "0123456789abcdef" for character in self.hash
        ):
            raise ValueError("control hash must be lowercase SHA-256")


class ControlStateBuilder:
    """Hash only facts that can authorize, reject, or gate a command."""

    def build(
        self,
        samples: ProjectionSamples,
        previous: ControlState | ConsoleSnapshot | None = None,
    ) -> ControlState:
        checked = _validated_samples(samples)
        digest = hashlib.sha256(_canonical_json(_control_facts(checked))).hexdigest()
        if previous is None:
            return ControlState(version=0, hash=digest)
        previous_version = (
            previous.control_version if isinstance(previous, ConsoleSnapshot) else previous.version
        )
        previous_hash = (
            previous.control_hash if isinstance(previous, ConsoleSnapshot) else previous.hash
        )
        if digest == previous_hash:
            return ControlState(version=previous_version, hash=digest)
        if previous_version == _MAX_WIRE_UINT:
            raise OverflowError("control version exhausted the wire range")
        return ControlState(version=previous_version + 1, hash=digest)


class SnapshotBuilder:
    """Build one complete immutable snapshot without reading any source."""

    def __init__(
        self,
        *,
        max_frame_bytes: int = MAX_FRAME_BYTES,
        control_builder: ControlStateBuilder | None = None,
    ) -> None:
        if type(max_frame_bytes) is not int or not 1 <= max_frame_bytes <= MAX_FRAME_BYTES:
            raise ValueError("max_frame_bytes must be within the protocol frame limit")
        self._max_frame_bytes = max_frame_bytes
        self._control_builder = control_builder or ControlStateBuilder()

    def build(
        self,
        *,
        samples: ProjectionSamples,
        generated_at_utc: datetime,
        previous: ConsoleSnapshot | None = None,
    ) -> ConsoleSnapshot:
        checked = _validated_samples(samples)
        _require_utc(generated_at_utc)
        control = self._control_builder.build(checked, previous)
        projected = _project(checked, generated_at_utc, previous)
        state_version = previous.shell.state_version if previous is not None else 0
        candidate = self._bounded_snapshot(
            projected,
            generated_at_utc,
            control,
            state_version,
        )
        if previous is None or candidate == previous:
            return candidate
        if state_version == _MAX_WIRE_UINT:
            raise OverflowError("state version exhausted the wire range")
        return self._bounded_snapshot(
            projected,
            generated_at_utc,
            control,
            state_version + 1,
        )

    def _bounded_snapshot(
        self,
        projected: _ProjectedSnapshot,
        generated_at_utc: datetime,
        control: ControlState,
        state_version: int,
    ) -> ConsoleSnapshot:
        windows = {
            target: _initial_window(target, rows) for target, rows in projected.windows.items()
        }
        omitted = {
            target: len(projected.windows[target]) - len(rows)
            for target, rows in windows.items()
            if len(projected.windows[target]) > len(rows)
        }
        for target, count in projected.source_omissions.items():
            if count:
                omitted[target] = omitted.get(target, 0) + count

        while True:
            snapshot = _assemble_snapshot(
                projected,
                windows,
                omitted,
                generated_at_utc,
                control,
                state_version,
            )
            if _maximum_snapshot_envelope_size(snapshot) <= self._max_frame_bytes:
                return snapshot
            populated = [target for target in _TARGET_ORDER if windows[target]]
            if not populated:
                raise ValueError("snapshot metadata cannot fit the configured frame limit")
            target = max(
                populated,
                key=lambda item: (_window_bytes(windows[item]), -_TARGET_ORDER.index(item)),
            )
            remove_count = max(1, len(windows[target]) // 4)
            windows[target] = (
                windows[target][remove_count:]
                if target in _KEEP_NEWEST_TARGETS
                else windows[target][:-remove_count]
            )
            omitted[target] = omitted.get(target, 0) + remove_count


@dataclass(frozen=True, slots=True)
class _ProjectedSnapshot:
    metadata: Mapping[str, _ViewMetadata]
    windows: Mapping[str, tuple[object, ...]]
    source_omissions: Mapping[str, int]
    portfolio_rank_source: str | None
    header: HeaderView
    capabilities: tuple[CapabilityView, ...]
    alerts_available: bool
    memory_agent_usage_error: str
    model_active_model_id: str | None
    model_rollback_model_id: str | None
    model_approved_family: str | None
    model_approved_strategy: str | None
    model_approved_feature_set_id: str | None
    model_final_regime: str | None
    model_final_regime_confidence: float | None
    model_regime_state: str
    model_automatic_changes_blocked: bool
    model_block_reason: str | None
    model_gates: tuple[ModelGateRow, ...]
    risk_blocked_actions: tuple[BlockedActionRow, ...]
    risk_circuit_breaker: CircuitBreakerView
    system_qwen: QwenStatusView
    system_health: tuple[SystemHealthRow, ...]


@dataclass(frozen=True, slots=True)
class _ViewMetadata:
    freshness: Freshness
    as_of_utc: datetime | None
    source: str
    error: str | None

    def values(self) -> dict[str, object]:
        return {
            "freshness": self.freshness,
            "as_of_utc": self.as_of_utc,
            "source": self.source,
            "error": self.error,
        }


def _validated_samples(samples: ProjectionSamples) -> dict[str, SourceSample[object]]:
    if not isinstance(samples, Mapping):
        raise TypeError("samples must be a mapping")
    unknown = sorted(set(samples) - SOURCE_IDS)
    if unknown:
        raise ValueError(f"Unknown projection source: {unknown[0]}")
    checked: dict[str, SourceSample[object]] = {}
    for source_id in sorted(samples):
        sample = samples[source_id]
        if not isinstance(sample, SourceSample):
            raise TypeError(f"Projection source {source_id} did not provide SourceSample")
        expected = _EXPECTED_FACT_TYPES[source_id]
        if sample.value is not None and type(sample.value) is not expected:
            raise TypeError(f"Projection source {source_id} returned the wrong facts type")
        checked[source_id] = sample
    return checked


def _require_utc(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("generated_at_utc must be timezone-aware UTC")


def _unavailable_metadata(name: str) -> _ViewMetadata:
    return _ViewMetadata(
        freshness=Freshness.UNAVAILABLE,
        as_of_utc=None,
        source=f"controller {name} projection",
        error=f"No controller-owned {name} projection is configured.",
    )


def _sample_metadata(sample: SourceSample[object], name: str) -> _ViewMetadata:
    return (
        _ViewMetadata(
            freshness=sample.freshness,
            as_of_utc=sample.observed_at_utc,
            source=sample.source,
            error=sample.error,
        )
        if sample.value is not None
        else _ViewMetadata(
            freshness=sample.freshness,
            as_of_utc=None,
            source=sample.source,
            error=sample.error,
        )
    )


def _metadata_for(
    samples: Mapping[str, SourceSample[object]],
    source_id: str,
    name: str,
) -> _ViewMetadata:
    sample = samples.get(source_id)
    return _unavailable_metadata(name) if sample is None else _sample_metadata(sample, name)


def _project(
    samples: Mapping[str, SourceSample[object]],
    generated_at_utc: datetime,
    previous: ConsoleSnapshot | None,
) -> _ProjectedSnapshot:
    metadata = {
        name: _metadata_for(samples, source_id, name)
        for name, source_id in (
            ("portfolio", PORTFOLIO_SOURCE_ID),
            ("orders", ORDER_SOURCE_ID),
            ("agents", AGENT_SOURCE_ID),
            ("models", MODEL_SOURCE_ID),
            ("timeline", TIMELINE_SOURCE_ID),
            ("risk", RISK_SOURCE_ID),
            ("data", DATA_SOURCE_ID),
            ("memory", MEMORY_SOURCE_ID),
        )
    }
    runtime_sample = samples.get(PLATFORM_RUNTIME_SOURCE_ID)
    if runtime_sample is not None:
        metadata["agents"] = _sample_metadata(runtime_sample, "agents")
    windows: dict[str, tuple[object, ...]] = {target: () for target in _TARGET_ORDER}
    source_omissions: dict[str, int] = {}
    alerts_available = False

    portfolio_sample = samples.get(PORTFOLIO_SOURCE_ID)
    portfolio_facts = _facts(portfolio_sample, PortfolioFacts)
    portfolio_rows, rank_source, portfolio_error = _ordered_portfolio(portfolio_facts, previous)
    if portfolio_error is not None:
        metadata["portfolio"] = _ViewMetadata(
            freshness=Freshness.UNAVAILABLE,
            as_of_utc=None,
            source=(
                portfolio_sample.source if portfolio_sample is not None else "native portfolio"
            ),
            error=portfolio_error,
        )
    windows["portfolio.rows"] = portfolio_rows
    windows["impact.holdings"] = portfolio_rows

    order_sample = samples.get(ORDER_SOURCE_ID)
    order_facts = _facts(order_sample, OrderFacts)
    if order_facts is not None:
        if _has_duplicate_id(order_facts.rows, "order_id"):
            metadata["orders"] = _duplicate_metadata(order_sample, "order IDs")
        else:
            windows["orders.rows"] = order_facts.rows

    agent_sample = samples.get(AGENT_SOURCE_ID)
    agent_facts = _facts(agent_sample, AgentFacts)
    runtime_facts = _facts(runtime_sample, PlatformRuntimeFacts)
    active_agents: tuple[AgentCard, ...] = ()
    if runtime_sample is not None:
        if runtime_facts is not None:
            if _has_duplicate_id(runtime_facts.active_work, "work_id"):
                metadata["agents"] = _duplicate_metadata(runtime_sample, "agent work IDs")
            else:
                active_agents = runtime_facts.active_work
                windows["agents.rows"] = active_agents
    elif agent_facts is not None:
        if agent_facts.active_work is None:
            metadata["agents"] = _ViewMetadata(
                freshness=Freshness.UNAVAILABLE,
                as_of_utc=None,
                source=agent_sample.source if agent_sample is not None else "native agents",
                error=agent_facts.active_work_error,
            )
        else:
            if _has_duplicate_id(agent_facts.active_work, "work_id"):
                metadata["agents"] = _duplicate_metadata(agent_sample, "agent work IDs")
            else:
                active_agents = agent_facts.active_work
                windows["agents.rows"] = active_agents

    model_active_model_id = None
    model_rollback_model_id = None
    model_approved_family = None
    model_approved_strategy = None
    model_approved_feature_set_id = None
    model_final_regime = None
    model_final_regime_confidence = None
    model_regime_state = "unavailable"
    model_automatic_changes_blocked = True
    model_block_reason = "Controller model summary is unavailable."
    model_gates: tuple[ModelGateRow, ...] = ()
    model_sample = samples.get(MODEL_SOURCE_ID)
    model_facts = _facts(model_sample, ModelFacts)
    if model_facts is not None:
        duplicate_models = (
            _has_duplicate_id(model_facts.opinions, "model_id")
            or _has_duplicate_id(model_facts.candidates, "candidate_id")
            or _has_duplicate_id(model_facts.metrics, "metric_id")
            or _has_duplicate_id(model_facts.evidence, "evidence_id")
            or _has_duplicate_id(model_facts.gates, "gate_id")
        )
        if duplicate_models:
            metadata["models"] = _duplicate_metadata(model_sample, "model view IDs")
            model_facts = None
        else:
            windows["models.opinions"] = model_facts.opinions
            windows["models.candidates"] = model_facts.candidates
            windows["models.metrics"] = model_facts.metrics
            windows["models.evidence"] = model_facts.evidence
            model_active_model_id = model_facts.configured_model_id
            model_rollback_model_id = model_facts.rollback_model_id
            model_approved_family = model_facts.approved_family
            model_approved_strategy = model_facts.configured_strategy
            model_approved_feature_set_id = model_facts.approved_feature_set_id
            model_final_regime = model_facts.final_regime
            model_final_regime_confidence = model_facts.final_regime_confidence
            model_regime_state = model_facts.regime_state
            model_automatic_changes_blocked = model_facts.automatic_changes_blocked
            model_block_reason = model_facts.block_reason
            model_gates = model_facts.gates

    timeline_facts = _facts(samples.get(TIMELINE_SOURCE_ID), TimelineFacts)
    timeline_rows: tuple[TimelineRow, ...] = ()
    if timeline_facts is not None:
        if _has_duplicate_id(timeline_facts.rows, "event_id"):
            timeline_sample = samples[TIMELINE_SOURCE_ID]
            duplicate_metadata = _ViewMetadata(
                freshness=Freshness.UNAVAILABLE,
                as_of_utc=None,
                source=timeline_sample.source,
                error="Duplicate timeline event IDs were rejected.",
            )
            metadata["timeline"] = duplicate_metadata
            timeline_facts = None
        else:
            timeline_rows = timeline_facts.rows
    if timeline_facts is not None:
        windows["timeline.rows"] = timeline_rows
        source_omissions["timeline.rows"] = timeline_facts.hidden_event_count
        impact_events = tuple(row for row in timeline_rows if row.impact)
        windows["impact.events"] = impact_events
        source_omissions["impact.events"] = timeline_facts.hidden_impact_event_count
        affected_agents = {row.agent_id for row in impact_events if row.agent_id is not None}
        windows["impact.agents"] = tuple(
            row for row in active_agents if row.agent in affected_agents
        )
        windows["portfolio.history"] = tuple(row for row in timeline_rows if row.symbol is not None)
        windows["orders.history"] = tuple(row for row in timeline_rows if row.order_id is not None)
        windows["agents.history"] = tuple(row for row in timeline_rows if row.agent_id is not None)
    metadata["impact"] = _impact_metadata(metadata)

    risk_blocked_actions: tuple[BlockedActionRow, ...] = ()
    risk_circuit_breaker = CircuitBreakerView(
        state="unavailable",
        reason="Controller circuit-breaker status is unavailable.",
        observed_at_utc=None,
    )
    risk_sample = samples.get(RISK_SOURCE_ID)
    risk_facts = _facts(risk_sample, RiskFacts)
    if risk_facts is not None:
        risk_metadata = metadata["risk"]
        if not risk_facts.broker_reconciled:
            risk_metadata = _ViewMetadata(
                freshness=Freshness.STALE,
                as_of_utc=risk_metadata.as_of_utc,
                source=risk_metadata.source,
                error=_join_reasons(
                    tuple(
                        reason
                        for reason in (
                            risk_metadata.error,
                            "Legacy risk state is not broker-reconciled.",
                        )
                        if reason is not None
                    )
                ),
            )
            metadata["risk"] = risk_metadata
        windows["risk.limits"] = _risk_limits(risk_facts)
        windows["risk.metrics"] = _risk_metrics(risk_facts, risk_metadata)
        if risk_facts.blocked_actions is not None:
            if _has_duplicate_id(risk_facts.blocked_actions, "action_id"):
                metadata["risk"] = _duplicate_metadata(risk_sample, "blocked action IDs")
            else:
                risk_blocked_actions = risk_facts.blocked_actions
        if risk_facts.circuit_breaker is not None:
            risk_circuit_breaker = risk_facts.circuit_breaker
        unavailable_deep_risk = tuple(
            reason
            for reason in (
                risk_facts.blocked_actions_error,
                risk_facts.circuit_breaker_error,
            )
            if reason is not None
        )
        if unavailable_deep_risk and metadata["risk"].freshness is not Freshness.UNAVAILABLE:
            risk_metadata = metadata["risk"]
            metadata["risk"] = _ViewMetadata(
                freshness=Freshness.STALE,
                as_of_utc=risk_metadata.as_of_utc,
                source=risk_metadata.source,
                error=_join_reasons(
                    tuple(
                        reason
                        for reason in (risk_metadata.error, *unavailable_deep_risk)
                        if reason is not None
                    )
                ),
            )

    if runtime_facts is not None:
        if _has_duplicate_id(runtime_facts.pending_approvals, "approval_id"):
            metadata["risk"] = _duplicate_metadata(runtime_sample, "approval IDs")
        else:
            windows["risk.approvals"] = runtime_facts.pending_approvals
            if risk_facts is None:
                metadata["risk"] = _ViewMetadata(
                    freshness=Freshness.STALE,
                    as_of_utc=runtime_sample.observed_at_utc,
                    source=runtime_sample.source,
                    error=_join_reasons(
                        tuple(
                            reason
                            for reason in (
                                (
                                    "Pending approvals are current; risk limits are unavailable."
                                    if runtime_sample.freshness is Freshness.FRESH
                                    else "Pending approvals are retained from a stale runtime read; "
                                    "risk limits are unavailable."
                                ),
                                runtime_sample.error,
                            )
                            if reason is not None
                        )
                    ),
                )
            elif runtime_sample.freshness is not Freshness.FRESH:
                risk_metadata = metadata["risk"]
                metadata["risk"] = _ViewMetadata(
                    freshness=Freshness.STALE,
                    as_of_utc=risk_metadata.as_of_utc,
                    source=risk_metadata.source,
                    error=_join_reasons(
                        tuple(
                            reason
                            for reason in (risk_metadata.error, runtime_sample.error)
                            if reason is not None
                        )
                    ),
                )
    elif runtime_sample is not None:
        if risk_facts is None:
            metadata["risk"] = _ViewMetadata(
                freshness=Freshness.UNAVAILABLE,
                as_of_utc=None,
                source=runtime_sample.source,
                error=_join_reasons(
                    tuple(
                        reason
                        for reason in (
                            "Pending approvals are unavailable; risk limits are unavailable.",
                            runtime_sample.error,
                        )
                        if reason is not None
                    )
                ),
            )
        else:
            risk_metadata = metadata["risk"]
            metadata["risk"] = _ViewMetadata(
                freshness=Freshness.STALE,
                as_of_utc=risk_metadata.as_of_utc,
                source=risk_metadata.source,
                error=_join_reasons(
                    tuple(
                        reason
                        for reason in (
                            risk_metadata.error,
                            "Pending approvals are unavailable.",
                            runtime_sample.error,
                        )
                        if reason is not None
                    )
                ),
            )

    alerts_available, alerts, metadata["risk"] = _merge_attention(
        samples,
        metadata["risk"],
        has_other_risk_facts=risk_facts is not None or runtime_facts is not None,
    )
    windows["shell.alerts"] = alerts
    windows["risk.alerts"] = alerts

    data_sample = samples.get(DATA_SOURCE_ID)
    data_facts = _facts(data_sample, DataFacts)
    if data_facts is not None:
        if _has_duplicate_id(data_facts.sources, "source_id") or _has_duplicate_id(
            data_facts.evidence, "evidence_id"
        ):
            metadata["data"] = _duplicate_metadata(data_sample, "data view IDs")
        else:
            windows["data.sources"] = data_facts.sources
            windows["data.evidence"] = data_facts.evidence

    memory_sample = samples.get(MEMORY_SOURCE_ID)
    memory_facts = _facts(memory_sample, MemoryFacts)
    memory_agent_usage_error = MEMORY_AGENT_USAGE_UNAVAILABLE
    if memory_facts is not None:
        memory_agent_usage_error = memory_facts.agent_usage_error
        if _has_duplicate_id(memory_facts.rows, "memory_id") or _has_duplicate_id(
            memory_facts.history, "event_id"
        ):
            metadata["memory"] = _duplicate_metadata(memory_sample, "memory view IDs")
        else:
            windows["memory.rows"] = memory_facts.rows
            windows["memory.history"] = memory_facts.history

    system_metadata, system_windows, system_qwen, system_health = _merge_system(samples)
    metadata["system"] = system_metadata
    windows.update(system_windows)

    capabilities = _capabilities()
    header = _header(
        metadata,
        generated_at_utc,
        portfolio_rows,
        active_agents,
        system_qwen,
        model_regime_state,
        model_final_regime,
        model_final_regime_confidence,
    )
    return _ProjectedSnapshot(
        metadata=metadata,
        windows=windows,
        source_omissions=source_omissions,
        portfolio_rank_source=rank_source,
        header=header,
        capabilities=capabilities,
        alerts_available=alerts_available,
        memory_agent_usage_error=memory_agent_usage_error,
        model_active_model_id=model_active_model_id,
        model_rollback_model_id=model_rollback_model_id,
        model_approved_family=model_approved_family,
        model_approved_strategy=model_approved_strategy,
        model_approved_feature_set_id=model_approved_feature_set_id,
        model_final_regime=model_final_regime,
        model_final_regime_confidence=model_final_regime_confidence,
        model_regime_state=model_regime_state,
        model_automatic_changes_blocked=model_automatic_changes_blocked,
        model_block_reason=model_block_reason,
        model_gates=model_gates,
        risk_blocked_actions=risk_blocked_actions,
        risk_circuit_breaker=risk_circuit_breaker,
        system_qwen=system_qwen,
        system_health=system_health,
    )


def _merge_attention(
    samples: Mapping[str, SourceSample[object]],
    risk_metadata: _ViewMetadata,
    *,
    has_other_risk_facts: bool,
) -> tuple[bool, tuple[AlertView, ...], _ViewMetadata]:
    sample = samples.get(ATTENTION_SOURCE_ID)
    if sample is None:
        return False, (), risk_metadata
    facts = _facts(sample, AttentionFacts)
    if facts is not None:
        if _has_duplicate_id(facts.alerts, "alert_id"):
            reason = "Duplicate attention alert IDs were rejected."
        else:
            if has_other_risk_facts or risk_metadata.freshness in {
                Freshness.FRESH,
                Freshness.STALE,
            }:
                return True, facts.alerts, risk_metadata
            return (
                True,
                facts.alerts,
                _ViewMetadata(
                    freshness=Freshness.STALE,
                    as_of_utc=sample.observed_at_utc,
                    source=sample.source,
                    error="Attention alerts are current; other risk facts are unavailable.",
                ),
            )
    else:
        reason = sample.error or "Attention alert state is loading."

    if risk_metadata.freshness in {Freshness.FRESH, Freshness.STALE}:
        return (
            False,
            (),
            _ViewMetadata(
                freshness=Freshness.STALE,
                as_of_utc=risk_metadata.as_of_utc,
                source=risk_metadata.source,
                error=_join_reasons(
                    tuple(item for item in (risk_metadata.error, reason) if item is not None)
                ),
            ),
        )
    return (
        False,
        (),
        _ViewMetadata(
            freshness=Freshness.UNAVAILABLE,
            as_of_utc=None,
            source=risk_metadata.source,
            error=_join_reasons(
                tuple(item for item in (risk_metadata.error, reason) if item is not None)
            ),
        ),
    )


def _facts(sample: SourceSample[object] | None, expected: type[object]) -> object | None:
    if sample is None or sample.value is None:
        return None
    if type(sample.value) is not expected:
        raise TypeError("projection fact type changed after validation")
    return sample.value


def _has_duplicate_id(rows: Sequence[object], id_field: str) -> bool:
    identities = [getattr(row, id_field) for row in rows]
    return len(identities) != len(set(identities))


def _duplicate_metadata(
    sample: SourceSample[object] | None,
    label: str,
) -> _ViewMetadata:
    return _ViewMetadata(
        freshness=Freshness.UNAVAILABLE,
        as_of_utc=None,
        source=sample.source if sample is not None else "controller projection",
        error=f"Duplicate {label} were rejected.",
    )


def _ordered_portfolio(
    facts_value: object | None,
    previous: ConsoleSnapshot | None,
) -> tuple[tuple[PortfolioRow, ...], str | None, str | None]:
    facts = cast(PortfolioFacts | None, facts_value)
    if facts is None:
        return (), None, None
    rows = facts.rows
    if len({row.symbol for row in rows}) != len(rows):
        return (), None, "Duplicate portfolio symbols were rejected."
    ranks = [row.confirmed_rank for row in rows if row.confirmed_rank is not None]
    has_complete_confirmed_rank = (
        facts.rank_source is not None
        and len(ranks) == len(rows)
        and len(ranks) == len(set(ranks))
        and all(row.reconciliation in {"matched", "not-required"} for row in rows)
    )
    if has_complete_confirmed_rank:
        return (
            tuple(
                sorted(
                    rows,
                    key=lambda row: (
                        row.confirmed_rank is None,
                        row.confirmed_rank if row.confirmed_rank is not None else _MAX_WIRE_UINT,
                        row.symbol,
                    ),
                )
            ),
            facts.rank_source,
            None,
        )
    by_symbol = {row.symbol: row for row in rows}
    previous_symbols = (
        tuple(row.symbol for row in previous.portfolio.rows) if previous is not None else ()
    )
    retained = [by_symbol.pop(symbol) for symbol in previous_symbols if symbol in by_symbol]
    retained.extend(by_symbol[symbol] for symbol in sorted(by_symbol))
    return tuple(retained), None, None


def _unavailable_qwen(reason: str) -> QwenStatusView:
    return QwenStatusView(
        state="unavailable",
        loaded_model=None,
        current_agent=None,
        queue_length=None,
        context_percent=None,
        last_inference_ms=None,
        observed_at_utc=None,
        error=reason,
    )


def _unavailable_health(reason: str) -> tuple[SystemHealthRow, ...]:
    return tuple(
        SystemHealthRow(
            component=component,
            state="unavailable",
            reason=reason,
            observed_at_utc=None,
            checks=(),
            broker_actions_blocked=component == "recovery",
        )
        for component in ("backup", "recovery", "notifications")
    )


def _merge_system(
    samples: Mapping[str, SourceSample[object]],
) -> tuple[
    _ViewMetadata,
    dict[str, tuple[object, ...]],
    QwenStatusView,
    tuple[SystemHealthRow, ...],
]:
    entries = [
        (source_id, samples[source_id])
        for source_id in (
            REPOSITORY_SYSTEM_SOURCE_ID,
            WINDOWS_SYSTEM_SOURCE_ID,
            NOTIFICATION_HEALTH_SOURCE_ID,
        )
        if source_id in samples
    ]
    empty = {
        "system.services": (),
        "system.metrics": (),
        "system.repositories": (),
    }
    if not entries:
        reason = "No controller-owned system projection is configured."
        return (
            _unavailable_metadata("system"),
            empty,
            _unavailable_qwen(reason),
            _unavailable_health(reason),
        )

    component_specs = (
        ("services", "service_id", "system.services"),
        ("metrics", "metric_id", "system.metrics"),
        ("repositories", "repository_id", "system.repositories"),
    )
    merged: dict[str, dict[str, object]] = {name: {} for name, _, _ in component_specs}
    observed_components = {name: False for name, _, _ in component_specs}
    component_errors: dict[str, list[str]] = {name: [] for name, _, _ in component_specs}
    qwen_errors: list[str] = []
    health_errors: list[str] = []
    reasons: list[str] = []
    observed_times: list[datetime] = []
    sources: list[str] = []
    stale = False
    conflict = False
    qwen: QwenStatusView | None = None
    health: dict[str, SystemHealthRow] = {}

    for _source_id, sample in entries:
        sources.append(sample.source)
        if sample.value is None:
            stale = True
            reasons.append(sample.error or f"{sample.source} is loading.")
            continue
        facts = cast(SystemFacts, sample.value)
        if sample.observed_at_utc is not None:
            observed_times.append(sample.observed_at_utc)
        if sample.freshness is not Freshness.FRESH:
            stale = True
            if sample.error:
                reasons.append(sample.error)
        for component, id_field, _target in component_specs:
            rows = cast(Sequence[object] | None, getattr(facts, component))
            component_error = cast(str | None, getattr(facts, f"{component}_error"))
            if rows is None:
                if component_error:
                    component_errors[component].append(component_error)
                continue
            observed_components[component] = True
            for row in rows:
                entity_id = cast(str, getattr(row, id_field))
                known = merged[component].get(entity_id)
                if known is not None and known != row:
                    conflict = True
                else:
                    merged[component][entity_id] = row
        if facts.qwen is None:
            if facts.qwen_error:
                qwen_errors.append(facts.qwen_error)
        elif qwen is not None and qwen != facts.qwen:
            conflict = True
        else:
            qwen = facts.qwen
        if facts.health is None:
            if facts.health_error:
                health_errors.append(facts.health_error)
        else:
            for row in facts.health:
                known = health.get(row.component)
                if known is not None and known != row:
                    conflict = True
                else:
                    health[row.component] = row

    source = " + ".join(dict.fromkeys(sources))
    if len(source) > _MAX_VIEW_TEXT:
        source = " + ".join(source_id for source_id, _sample in entries)
    if conflict:
        reason = "Conflicting system facts were rejected."
        return (
            _ViewMetadata(
                freshness=Freshness.UNAVAILABLE,
                as_of_utc=None,
                source=source,
                error=reason,
            ),
            empty,
            _unavailable_qwen(reason),
            _unavailable_health(reason),
        )
    missing = [name for name, seen in observed_components.items() if not seen]
    if missing:
        stale = True
        reasons.append(f"System {', '.join(missing)} facts are unavailable.")
        for component in missing:
            reasons.extend(component_errors[component])
    if qwen is None:
        stale = True
        reasons.append("Qwen status is unavailable.")
        reasons.extend(qwen_errors)
    missing_health = tuple(
        component
        for component in ("backup", "recovery", "notifications")
        if component not in health
    )
    if missing_health:
        stale = True
        reasons.append(f"System {', '.join(missing_health)} health is unavailable.")
        reasons.extend(health_errors)
    any_observed = any(observed_components.values()) or qwen is not None or bool(health)
    if not any_observed:
        freshness = (
            Freshness.LOADING
            if entries and all(sample.freshness is Freshness.LOADING for _, sample in entries)
            else Freshness.UNAVAILABLE
        )
        return (
            _ViewMetadata(
                freshness=freshness,
                as_of_utc=None,
                source=source,
                error=None if freshness is Freshness.LOADING else _join_reasons(reasons),
            ),
            empty,
            _unavailable_qwen(_join_reasons(reasons)),
            _unavailable_health(_join_reasons(reasons)),
        )
    if not observed_times:
        reason = "System facts have no trusted observation time."
        return (
            _ViewMetadata(
                freshness=Freshness.UNAVAILABLE,
                as_of_utc=None,
                source=source,
                error=reason,
            ),
            empty,
            _unavailable_qwen(reason),
            _unavailable_health(reason),
        )
    metadata = _ViewMetadata(
        freshness=Freshness.STALE if stale else Freshness.FRESH,
        as_of_utc=max(observed_times),
        source=source,
        error=_join_reasons(reasons) if stale else None,
    )
    windows = {
        target: tuple(merged[component][key] for key in sorted(merged[component]))
        for component, _id_field, target in component_specs
    }
    system_health = tuple(
        health.get(component)
        or SystemHealthRow(
            component=component,
            state="unavailable",
            reason=f"Controller {component} health is unavailable.",
            observed_at_utc=None,
            checks=(),
            broker_actions_blocked=component == "recovery",
        )
        for component in ("backup", "recovery", "notifications")
    )
    return (
        metadata,
        windows,
        qwen or _unavailable_qwen("Controller Qwen status is unavailable."),
        system_health,
    )


def _join_reasons(reasons: Sequence[str]) -> str:
    unique = tuple(dict.fromkeys(reason for reason in reasons if reason.strip()))
    joined = " ".join(unique) or "System facts are unavailable."
    if len(joined) <= _MAX_VIEW_TEXT:
        return joined
    suffix = f" (+{max(len(unique) - 1, 1)} more reasons.)"
    return joined[: _MAX_VIEW_TEXT - len(suffix)].rstrip() + suffix


def _impact_metadata(metadata: Mapping[str, _ViewMetadata]) -> _ViewMetadata:
    components = tuple((name, metadata[name]) for name in ("portfolio", "timeline", "agents"))
    sources = " + ".join(dict.fromkeys(item.source for _, item in components))
    usable = tuple(
        (name, item)
        for name, item in components
        if item.freshness in {Freshness.FRESH, Freshness.STALE}
    )
    if len(usable) == len(components) and all(
        item.freshness is Freshness.FRESH for _, item in usable
    ):
        return _ViewMetadata(
            freshness=Freshness.FRESH,
            as_of_utc=max(cast(datetime, item.as_of_utc) for _, item in usable),
            source=sources,
            error=None,
        )
    if usable:
        reasons = []
        for name, item in components:
            if item.freshness is Freshness.FRESH:
                continue
            reasons.append(
                item.error
                or (
                    f"{name.title()} projection is loading."
                    if item.freshness is Freshness.LOADING
                    else f"{name.title()} projection is not current."
                )
            )
        return _ViewMetadata(
            freshness=Freshness.STALE,
            as_of_utc=max(cast(datetime, item.as_of_utc) for _, item in usable),
            source=sources,
            error=_join_reasons(reasons),
        )
    if all(item.freshness is Freshness.LOADING for _, item in components):
        return _ViewMetadata(
            freshness=Freshness.LOADING,
            as_of_utc=None,
            source=sources,
            error=None,
        )
    return _ViewMetadata(
        freshness=Freshness.UNAVAILABLE,
        as_of_utc=None,
        source=sources,
        error=_join_reasons(
            tuple(
                item.error
                or (
                    f"{name.title()} projection is loading."
                    if item.freshness is Freshness.LOADING
                    else f"{name.title()} projection is unavailable."
                )
                for name, item in components
            )
        ),
    )


def _risk_limits(facts: RiskFacts) -> tuple[RiskLimitRow, ...]:
    return (
        RiskLimitRow(
            limit_id="risk.breaker",
            current_value="1" if facts.breaker_tripped else "0",
            proposed_value=None,
            status="violated" if facts.breaker_tripped else "within",
            proposal_reason=None,
            review_state="not-required",
            evidence_ids=(),
        ),
        RiskLimitRow(
            limit_id="risk.broker-reconciled",
            current_value="0",
            proposed_value=None,
            status="unavailable",
            proposal_reason=None,
            review_state="unavailable",
            evidence_ids=(),
        ),
    )


def _risk_metrics(facts: RiskFacts, metadata: _ViewMetadata) -> tuple[MetricRow, ...]:
    def metric(metric_id: str, value: float, unit: str) -> MetricRow:
        return MetricRow(
            metric_id=metric_id,
            value=value,
            unit=unit,
            freshness=metadata.freshness,
            observed_at_utc=metadata.as_of_utc,
            error=metadata.error,
        )

    return (
        metric("risk.daily-pnl", facts.daily_pnl, "currency"),
        metric("risk.starting-equity", facts.starting_equity, "currency"),
        metric("risk.peak-equity", facts.peak_equity, "currency"),
        metric("risk.legacy-position-count", float(len(facts.positions)), "count"),
    )


def _capabilities() -> tuple[CapabilityView, ...]:
    return (
        CapabilityView(
            capability_id="snapshot.read",
            state=CapabilityState.READ_ONLY,
            reason=None,
        ),
        *(
            CapabilityView(
                capability_id=capability_id,
                state=CapabilityState.DISABLED,
                reason=_DISABLED_ACTION_REASON,
            )
            for capability_id in _ACTION_CAPABILITY_IDS
        ),
    )


def _header(
    metadata: Mapping[str, _ViewMetadata],
    generated_at_utc: datetime,
    portfolio_rows: tuple[PortfolioRow, ...],
    active_agents: tuple[AgentCard, ...],
    qwen: QwenStatusView,
    model_regime_state: str,
    model_final_regime: str | None,
    model_final_regime_confidence: float | None,
) -> HeaderView:
    data_metadata = metadata["data"]
    data_freshness = data_metadata.freshness
    age: float | None = None
    if data_metadata.as_of_utc is not None:
        age = max(0.0, (generated_at_utc - data_metadata.as_of_utc).total_seconds())

    agents_are_fresh = metadata["agents"].freshness is Freshness.FRESH
    running = (
        sorted(
            (row for row in active_agents if row.stage == "running"),
            key=lambda row: (not row.urgent, -row.priority, row.work_id),
        )
        if agents_are_fresh
        else []
    )
    qwen_state = "Unavailable" if qwen.state == "unavailable" else qwen.state
    qwen_context_percent = None if qwen.state == "unavailable" else qwen.context_percent
    models_freshness = metadata["models"].freshness
    models_are_usable = models_freshness in {Freshness.FRESH, Freshness.STALE}
    stale_prefix = "STALE " if models_freshness is Freshness.STALE else ""
    if models_are_usable and model_regime_state == "decided":
        regime_label = stale_prefix + (model_final_regime or "Unavailable")
        regime_confidence = model_final_regime_confidence
    elif models_are_usable and model_regime_state == "uncertain":
        regime_label = stale_prefix + "UNCERTAIN"
        regime_confidence = None
    else:
        regime_label = "Unavailable"
        regime_confidence = None
    portfolio_value = (
        _portfolio_value(portfolio_rows)
        if metadata["portfolio"].freshness is Freshness.FRESH
        else None
    )
    return HeaderView(
        operating_mode=OperatingMode.UNKNOWN,
        operating_mode_freshness=Freshness.UNAVAILABLE,
        operating_mode_reason=_UNAVAILABLE_MODE_REASON,
        data_freshness=data_freshness,
        data_age_seconds=age,
        regime_label=regime_label,
        regime_confidence=regime_confidence,
        portfolio_value=portfolio_value,
        next_rebalance_at_utc=None,
        rebalance_blockers=None,
        active_agent=running[0].agent if running else None,
        agent_queue_length=(
            sum(row.stage in {"queued", "waiting"} for row in active_agents)
            if agents_are_fresh
            else None
        ),
        qwen_state=qwen_state,
        qwen_context_percent=qwen_context_percent,
        current_time_utc=generated_at_utc,
        market_session="Unavailable",
    )


def _portfolio_value(rows: Sequence[PortfolioRow]) -> float | None:
    values = [row.market_value for row in rows]
    if not rows or any(value is None for value in values):
        return None
    return float(sum((Decimal(cast(str, value)) for value in values), Decimal(0)))


def _assemble_snapshot(
    projected: _ProjectedSnapshot,
    windows: Mapping[str, tuple[object, ...]],
    omitted: Mapping[str, int],
    generated_at_utc: datetime,
    control: ControlState,
    state_version: int,
) -> ConsoleSnapshot:
    omissions = tuple(
        WindowOmission(target=cast(EventTarget, target), omitted_count=omitted[target])
        for target in _TARGET_ORDER
        if omitted.get(target, 0) > 0
    )
    timeline_hidden = omitted.get("timeline.rows", 0)
    shell = ShellSnapshot(
        state_version=state_version,
        generated_at_utc=generated_at_utc,
        header=projected.header,
        alerts=(
            cast(tuple[AlertView, ...], windows["shell.alerts"])
            if projected.alerts_available
            else None
        ),
        capabilities=projected.capabilities,
    )
    metadata = projected.metadata
    return ConsoleSnapshot(
        shell=shell,
        control_version=control.version,
        control_hash=control.hash,
        command_specs=(),
        window_omissions=omissions,
        impact=ImpactView(
            **metadata["impact"].values(),
            holdings=cast(tuple[PortfolioRow, ...], windows["impact.holdings"]),
            events=cast(tuple[TimelineRow, ...], windows["impact.events"]),
            agents=cast(tuple[AgentCard, ...], windows["impact.agents"]),
        ),
        portfolio=PortfolioView(
            **metadata["portfolio"].values(),
            rows=cast(tuple[PortfolioRow, ...], windows["portfolio.rows"]),
            returns_today=cast(tuple[ReturnComponentRow, ...], windows["portfolio.returns-today"]),
            returns_since_rebalance=cast(
                tuple[ReturnComponentRow, ...], windows["portfolio.returns-since-rebalance"]
            ),
            returns_since_start=cast(
                tuple[ReturnComponentRow, ...], windows["portfolio.returns-since-start"]
            ),
            metrics=cast(tuple[MetricRow, ...], windows["portfolio.metrics"]),
            history=cast(tuple[TimelineRow, ...], windows["portfolio.history"]),
            rank_source=projected.portfolio_rank_source,
        ),
        orders=OrdersView(
            **metadata["orders"].values(),
            rows=cast(tuple[OrderRow, ...], windows["orders.rows"]),
            reconciliation_agents=cast(
                tuple[AgentCard, ...], windows["orders.reconciliation-agents"]
            ),
            history=cast(tuple[TimelineRow, ...], windows["orders.history"]),
        ),
        agents=AgentsView(
            **metadata["agents"].values(),
            rows=cast(tuple[AgentCard, ...], windows["agents.rows"]),
            history=cast(tuple[TimelineRow, ...], windows["agents.history"]),
        ),
        models=ModelsView(
            **metadata["models"].values(),
            opinions=cast(tuple[ModelOpinionRow, ...], windows["models.opinions"]),
            candidates=cast(tuple, windows["models.candidates"]),
            metrics=cast(tuple[MetricRow, ...], windows["models.metrics"]),
            evidence=cast(tuple[EvidenceRow, ...], windows["models.evidence"]),
            active_model_id=projected.model_active_model_id,
            rollback_model_id=projected.model_rollback_model_id,
            approved_family=projected.model_approved_family,
            approved_strategy=cast(object, projected.model_approved_strategy),
            approved_feature_set_id=projected.model_approved_feature_set_id,
            final_regime=projected.model_final_regime,
            final_regime_confidence=projected.model_final_regime_confidence,
            regime_state=cast(object, projected.model_regime_state),
            automatic_changes_blocked=projected.model_automatic_changes_blocked,
            block_reason=projected.model_block_reason,
            gates=projected.model_gates,
        ),
        timeline=TimelineView(
            **metadata["timeline"].values(),
            rows=cast(tuple[TimelineRow, ...], windows["timeline.rows"]),
            hidden_event_count=timeline_hidden,
        ),
        risk=RiskView(
            **metadata["risk"].values(),
            limits=cast(tuple[RiskLimitRow, ...], windows["risk.limits"]),
            approvals=cast(tuple, windows["risk.approvals"]),
            alerts=cast(tuple[AlertView, ...], windows["risk.alerts"]),
            metrics=cast(tuple[MetricRow, ...], windows["risk.metrics"]),
            blocked_actions=projected.risk_blocked_actions,
            circuit_breaker=projected.risk_circuit_breaker,
        ),
        data=DataView(
            **metadata["data"].values(),
            sources=cast(tuple[SourceRow, ...], windows["data.sources"]),
            evidence=cast(tuple[EvidenceRow, ...], windows["data.evidence"]),
        ),
        memory=MemoryView(
            **metadata["memory"].values(),
            rows=cast(tuple[MemoryRow, ...], windows["memory.rows"]),
            history=cast(tuple[TimelineRow, ...], windows["memory.history"]),
            agent_usage_error=projected.memory_agent_usage_error,
        ),
        system=SystemView(
            **metadata["system"].values(),
            services=cast(tuple[ServiceRow, ...], windows["system.services"]),
            metrics=cast(tuple[MetricRow, ...], windows["system.metrics"]),
            repositories=cast(tuple[RepositoryRow, ...], windows["system.repositories"]),
            live_readiness=unavailable_live_readiness(),
            live_account=None,
            live_transition_plan=None,
            qwen=projected.system_qwen,
            health=projected.system_health,
        ),
    )


def _window_bytes(rows: Sequence[object]) -> int:
    return len(
        json.dumps([_json_value(row) for row in rows], separators=(",", ":")).encode("utf-8")
    )


def _initial_window(target: str, rows: Sequence[object]) -> tuple[object, ...]:
    if target in _KEEP_NEWEST_TARGETS:
        return tuple(rows[-_MAX_WINDOW_ROWS:])
    return tuple(rows[:_MAX_WINDOW_ROWS])


def _maximum_snapshot_envelope_size(snapshot: ConsoleSnapshot) -> int:
    envelope = WireEnvelope(
        schema_version=1,
        message_id="s" * 128,
        sequence=_MAX_WIRE_UINT,
        state_version=snapshot.shell.state_version,
        timestamp_utc=snapshot.shell.generated_at_utc,
        message_type=MessageType.SNAPSHOT,
        payload=SnapshotPayload(snapshot=snapshot).model_dump(mode="json"),
    )
    return len(envelope.model_dump_json().encode("utf-8"))


def _json_value(value: object) -> object:
    model_dump = getattr(value, "model_dump", None)
    return model_dump(mode="json") if callable(model_dump) else value


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _control_facts(samples: Mapping[str, SourceSample[object]]) -> dict[str, object]:
    facts: dict[str, object] = {
        "capabilities": [row.model_dump(mode="json") for row in _capabilities()],
        "sources": {},
    }
    sources = cast(dict[str, object], facts["sources"])
    for source_id in sorted(SOURCE_IDS):
        sample = samples.get(source_id)
        if source_id in {
            AGENT_SOURCE_ID,
            MEMORY_SOURCE_ID,
            ATTENTION_SOURCE_ID,
        }:
            continue
        if source_id == NOTIFICATION_HEALTH_SOURCE_ID:
            if (
                sample is not None
                and isinstance(sample.value, SystemFacts)
                and sample.value.health is not None
            ):
                sources[source_id] = {
                    "freshness": sample.freshness.value,
                    "facts": {"health": _control_health_facts(sample.value.health)},
                }
            continue
        if sample is None or sample.value is None:
            sources[source_id] = {
                "available": False,
                "freshness": sample.freshness.value if sample else "missing",
            }
            continue
        sources[source_id] = {
            "freshness": sample.freshness.value,
            "facts": _control_source_facts(sample.value),
        }
    return facts


def _control_source_facts(value: object) -> object:
    if isinstance(value, PlatformRuntimeFacts):
        return {
            "pending_approvals": [
                {
                    "approval_id": row.approval_id,
                    "run_id": row.run_id,
                    "checkpoint_id": row.checkpoint_id,
                    "state": row.state,
                    "reason": row.reason,
                    "evidence_ids": sorted(row.evidence_ids),
                    "affected_symbols": sorted(row.affected_symbols),
                    "weight_changes": [
                        {
                            "symbol": change.symbol,
                            "current_weight": change.current_weight,
                            "proposed_weight": change.proposed_weight,
                        }
                        for change in sorted(row.weight_changes, key=lambda item: item.symbol)
                    ],
                    "risks": sorted(row.risks),
                    "expected_consequences": sorted(row.expected_consequences),
                    "basis_sha256": row.basis_sha256,
                    "stale_reason": row.stale_reason,
                }
                for row in sorted(value.pending_approvals, key=lambda item: item.approval_id)
            ]
        }
    if isinstance(value, SystemFacts):
        return {
            "services": [
                {"service_id": row.service_id, "state": row.state}
                for row in sorted(value.services or (), key=lambda item: item.service_id)
            ]
            if value.services is not None
            else None,
            "repositories": [
                {
                    "repository_id": row.repository_id,
                    "freshness": row.freshness,
                    "branch": row.branch,
                    "revision": row.revision,
                    "clean": row.clean,
                    "worktrees": sorted(row.worktrees),
                    "unpushed_commit_count": row.unpushed_commit_count,
                    "checks": [
                        {
                            "check_id": check.check_id,
                            "state": check.state,
                            "reason": check.reason,
                        }
                        for check in sorted(row.checks, key=lambda item: item.check_id)
                    ],
                }
                for row in sorted(value.repositories or (), key=lambda item: item.repository_id)
            ]
            if value.repositories is not None
            else None,
            "qwen": (
                {
                    "state": value.qwen.state,
                    "loaded_model": value.qwen.loaded_model,
                    "current_agent": value.qwen.current_agent,
                }
                if value.qwen is not None
                else None
            ),
            "health": (
                _control_health_facts(value.health)
                if value.health is not None
                else None
            ),
        }
    if isinstance(value, PortfolioFacts):
        return {
            "rank_source": value.rank_source,
            "rows": [
                {
                    "symbol": row.symbol,
                    "asset_type": row.asset_type,
                    "quantity": row.quantity,
                    "current_weight": row.current_weight,
                    "proposed_weight": row.proposed_weight,
                    "approved_weight": row.approved_weight,
                    "change_state": row.change_state,
                    "confirmed_rank": row.confirmed_rank,
                    "reconciliation": row.reconciliation,
                }
                for row in sorted(value.rows, key=lambda item: item.symbol)
            ],
        }
    if isinstance(value, OrderFacts):
        return {
            "rows": [
                {
                    "order_id": row.order_id,
                    "symbol": row.symbol,
                    "side": row.side,
                    "quantity": row.quantity,
                    "status": row.status,
                    "broker_order_id": row.broker_order_id,
                    "fills": [
                        {
                            "fill_id": fill.fill_id,
                            "quantity": fill.quantity,
                            "price": fill.price,
                            "fee": fill.fee,
                        }
                        for fill in sorted(row.fills, key=lambda item: item.fill_id)
                    ],
                    "reconciliation": row.reconciliation,
                }
                for row in sorted(value.rows, key=lambda item: item.order_id)
            ]
        }
    if isinstance(value, ModelFacts):
        return {
            "configured_strategy": value.configured_strategy,
            "configured_model_id": value.configured_model_id,
            "rollback_model_id": value.rollback_model_id,
            "approved_family": value.approved_family,
            "approved_feature_set_id": value.approved_feature_set_id,
            "final_regime": value.final_regime,
            "final_regime_confidence": value.final_regime_confidence,
            "regime_state": value.regime_state,
            "automatic_changes_blocked": value.automatic_changes_blocked,
            "block_reason": value.block_reason,
            "opinions": [
                {
                    "model_id": row.model_id,
                    "regime": row.regime,
                    "confidence": row.confidence,
                }
                for row in sorted(value.opinions, key=lambda item: item.model_id)
            ],
            "candidates": [
                {
                    "candidate_id": row.candidate_id,
                    "family": row.family,
                    "strategy": row.strategy,
                    "status": row.status,
                    "evidence_ids": sorted(row.evidence_ids),
                    "feature_set_id": row.feature_set_id,
                    "data_identity": row.data_identity,
                    "evaluation_contract": row.evaluation_contract,
                }
                for row in sorted(value.candidates, key=lambda item: item.candidate_id)
            ],
            "evidence": [
                {
                    "evidence_id": row.evidence_id,
                    "evidence_type": row.evidence_type,
                    "source": row.source,
                    "sha256": row.sha256,
                }
                for row in sorted(value.evidence, key=lambda item: item.evidence_id)
            ],
            "gates": [
                {
                    "gate_id": row.gate_id,
                    "candidate_id": row.candidate_id,
                    "metric_id": row.metric_id,
                    "candidate_value": row.candidate_value,
                    "baseline_value": row.baseline_value,
                    "comparison": row.comparison,
                    "threshold": row.threshold,
                    "evaluation_window": row.evaluation_window,
                    "state": row.state,
                    "reason": row.reason,
                    "evidence_ids": sorted(row.evidence_ids),
                }
                for row in sorted(value.gates, key=lambda item: item.gate_id)
            ],
        }
    if isinstance(value, RiskFacts):
        return {
            "session_date": value.session_date.isoformat() if value.session_date else None,
            "breaker_tripped": value.breaker_tripped,
            "positions": [
                {
                    "symbol": row.symbol,
                    "quantity": row.quantity,
                    "entry_price": row.entry_price,
                }
                for row in sorted(value.positions, key=lambda item: item.symbol)
            ],
            "broker_reconciled": value.broker_reconciled,
            "limits": [
                {
                    "limit_id": row.limit_id,
                    "current_value": row.current_value,
                    "proposed_value": row.proposed_value,
                    "status": row.status,
                    "proposal_reason": row.proposal_reason,
                    "review_state": row.review_state,
                    "evidence_ids": sorted(row.evidence_ids),
                }
                for row in _risk_limits(value)
            ],
            "blocked_actions": (
                [
                    {
                        "action_id": row.action_id,
                        "action": row.action,
                        "reason": row.reason,
                        "affected_symbols": sorted(row.affected_symbols),
                    }
                    for row in sorted(value.blocked_actions, key=lambda item: item.action_id)
                ]
                if value.blocked_actions is not None
                else None
            ),
            "circuit_breaker": (
                {
                    "state": value.circuit_breaker.state,
                    "reason": value.circuit_breaker.reason,
                }
                if value.circuit_breaker is not None
                else None
            ),
        }
    if isinstance(value, DataFacts):
        return {
            "sources": [
                {
                    "source_id": row.source_id,
                    "freshness": row.freshness,
                    "coverage": row.coverage,
                    "consumers": sorted(row.consumers),
                    "dependencies": sorted(row.dependencies),
                }
                for row in sorted(value.sources, key=lambda item: item.source_id)
            ],
            "evidence": [
                {
                    "evidence_id": row.evidence_id,
                    "evidence_type": row.evidence_type,
                    "source": row.source,
                    "sha256": row.sha256,
                }
                for row in sorted(value.evidence, key=lambda item: item.evidence_id)
            ],
        }
    if isinstance(value, TimelineFacts):
        return {
            "incidents": [
                {
                    "event_id": row.event_id,
                    "severity": row.severity,
                    "approval_id": row.approval_id,
                    "order_id": row.order_id,
                }
                for row in sorted(value.rows, key=lambda item: item.event_id)
                if row.severity in {"urgent", "resolved"}
                or row.approval_id is not None
                or row.order_id is not None
            ]
        }
    raise TypeError(f"Unsupported command-prerequisite facts: {type(value).__name__}")


def _control_health_facts(rows: Sequence[SystemHealthRow]) -> list[dict[str, object]]:
    return [
        {
            "component": row.component,
            "state": row.state,
            "broker_actions_blocked": row.broker_actions_blocked,
            "checks": [
                {"check_id": check.check_id, "state": check.state}
                for check in sorted(row.checks, key=lambda item: item.check_id)
            ],
        }
        for row in sorted(rows, key=lambda item: item.component)
    ]


_DIFF_TARGETS: Final = {
    "shell.alerts": ("alert-row", "alert_id"),
    "impact.holdings": ("portfolio-row", "symbol"),
    "impact.events": ("timeline-row", "event_id"),
    "impact.agents": ("agent-card", "work_id"),
    "portfolio.rows": ("portfolio-row", "symbol"),
    "portfolio.returns-today": ("return-component-row", "component"),
    "portfolio.returns-since-rebalance": ("return-component-row", "component"),
    "portfolio.returns-since-start": ("return-component-row", "component"),
    "portfolio.metrics": ("metric-row", "metric_id"),
    "portfolio.history": ("timeline-row", "event_id"),
    "orders.rows": ("order-row", "order_id"),
    "orders.reconciliation-agents": ("agent-card", "work_id"),
    "orders.history": ("timeline-row", "event_id"),
    "agents.rows": ("agent-card", "work_id"),
    "agents.history": ("timeline-row", "event_id"),
    "models.opinions": ("model-opinion-row", "model_id"),
    "models.candidates": ("candidate-row", "candidate_id"),
    "models.metrics": ("metric-row", "metric_id"),
    "models.evidence": ("evidence-row", "evidence_id"),
    "timeline.rows": ("timeline-row", "event_id"),
    "risk.limits": ("risk-limit-row", "limit_id"),
    "risk.approvals": ("approval-row", "approval_id"),
    "risk.alerts": ("alert-row", "alert_id"),
    "risk.metrics": ("metric-row", "metric_id"),
    "data.sources": ("source-row", "source_id"),
    "data.evidence": ("evidence-row", "evidence_id"),
    "memory.rows": ("memory-row", "memory_id"),
    "memory.history": ("timeline-row", "event_id"),
    "system.services": ("service-row", "service_id"),
    "system.metrics": ("metric-row", "metric_id"),
    "system.repositories": ("repository-row", "repository_id"),
}


def diff_snapshots(
    previous: ConsoleSnapshot,
    current: ConsoleSnapshot,
) -> tuple[EventPayload, ...]:
    """Return deterministic row events; metadata-only changes require a snapshot."""

    presentation = _event_presentation(current)
    grouped: dict[
        tuple[str, str, str, bytes],
        tuple[str, str, str, object | None, list[EventTarget]],
    ] = {}
    for target in _TARGET_ORDER:
        entity_type, id_field = _DIFF_TARGETS[target]
        before = _target_entities(previous, target, id_field)
        after = _target_entities(current, target, id_field)
        for entity_id in sorted(set(before) | set(after)):
            if before.get(entity_id) == after.get(entity_id):
                continue
            entity = after.get(entity_id)
            operation = "remove" if entity is None else "upsert"
            fingerprint = b"null" if entity is None else _canonical_json(_json_value(entity))
            key = (entity_type, entity_id, operation, fingerprint)
            pending = grouped.get(key)
            if pending is None:
                grouped[key] = (
                    entity_type,
                    entity_id,
                    operation,
                    entity,
                    [cast(EventTarget, target)],
                )
            else:
                pending[4].append(cast(EventTarget, target))
    return tuple(
        EventPayload(
            entity_type=entity_type,
            entity_id=entity_id,
            operation=operation,
            entity=entity,
            targets=tuple(targets),
            presentation=presentation,
        )
        for entity_type, entity_id, operation, entity, targets in grouped.values()
    )


def requires_full_snapshot(
    previous: ConsoleSnapshot,
    current: ConsoleSnapshot,
) -> bool:
    """Return true when an incremental row event cannot carry changed state."""

    return (
        previous.command_specs != current.command_specs
        or previous.shell.capabilities != current.shell.capabilities
        or (previous.shell.alerts is None) != (current.shell.alerts is None)
        or previous.system.live_readiness != current.system.live_readiness
        or previous.system.live_account != current.system.live_account
        or previous.system.live_transition_plan != current.system.live_transition_plan
        or previous.models.active_model_id != current.models.active_model_id
        or previous.models.rollback_model_id != current.models.rollback_model_id
        or previous.models.approved_family != current.models.approved_family
        or previous.models.approved_strategy != current.models.approved_strategy
        or previous.models.approved_feature_set_id != current.models.approved_feature_set_id
        or previous.models.final_regime != current.models.final_regime
        or previous.models.final_regime_confidence != current.models.final_regime_confidence
        or previous.models.regime_state != current.models.regime_state
        or previous.models.automatic_changes_blocked
        != current.models.automatic_changes_blocked
        or previous.models.block_reason != current.models.block_reason
        or previous.models.gates != current.models.gates
        or previous.risk.blocked_actions != current.risk.blocked_actions
        or previous.risk.circuit_breaker != current.risk.circuit_breaker
        or previous.system.qwen != current.system.qwen
        or previous.system.health != current.system.health
    )


def _target_entities(
    snapshot: ConsoleSnapshot,
    target: str,
    id_field: str,
) -> dict[str, object]:
    rows = _target_rows(snapshot, target)
    result: dict[str, object] = {}
    for row in rows:
        entity_id = cast(str, getattr(row, id_field))
        if entity_id in result:
            raise ValueError(f"Duplicate entity ID in {target}: {entity_id}")
        result[entity_id] = row
    return result


def _target_rows(snapshot: ConsoleSnapshot, target: str) -> Sequence[object]:
    section, field = target.split(".", 1)
    owner = snapshot.shell if section == "shell" else getattr(snapshot, section)
    rows = getattr(owner, field.replace("-", "_"))
    return () if rows is None else cast(Sequence[object], rows)


def _event_presentation(snapshot: ConsoleSnapshot) -> EventPresentation:
    def meta(view: ScreenView) -> ScreenMeta:
        return ScreenMeta(
            freshness=view.freshness,
            as_of_utc=view.as_of_utc,
            source=view.source,
            error=view.error,
        )

    return EventPresentation(
        generated_at_utc=snapshot.shell.generated_at_utc,
        header=snapshot.shell.header,
        control_version=snapshot.control_version,
        control_hash=snapshot.control_hash,
        window_omissions=snapshot.window_omissions,
        impact=meta(snapshot.impact),
        portfolio=meta(snapshot.portfolio),
        orders=meta(snapshot.orders),
        agents=meta(snapshot.agents),
        models=meta(snapshot.models),
        timeline=meta(snapshot.timeline),
        risk=meta(snapshot.risk),
        data=meta(snapshot.data),
        memory=meta(snapshot.memory),
        system=meta(snapshot.system),
        portfolio_rank_source=snapshot.portfolio.rank_source,
        timeline_hidden_event_count=snapshot.timeline.hidden_event_count,
        model_active_model_id=snapshot.models.active_model_id,
        model_rollback_model_id=snapshot.models.rollback_model_id,
        model_approved_family=snapshot.models.approved_family,
        model_approved_strategy=snapshot.models.approved_strategy,
        model_approved_feature_set_id=snapshot.models.approved_feature_set_id,
        model_final_regime=snapshot.models.final_regime,
        model_final_regime_confidence=snapshot.models.final_regime_confidence,
        model_regime_state=snapshot.models.regime_state,
        model_automatic_changes_blocked=snapshot.models.automatic_changes_blocked,
        model_block_reason=snapshot.models.block_reason,
        model_gates=snapshot.models.gates,
        risk_blocked_actions=snapshot.risk.blocked_actions,
        risk_circuit_breaker=snapshot.risk.circuit_breaker,
        system_qwen=snapshot.system.qwen,
        system_health=snapshot.system.health,
    )
