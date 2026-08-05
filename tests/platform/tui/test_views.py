"""Strict read-view contracts shared by the Python gateway and Rust console."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from vesper.platform.tui import views as tui_views
from vesper.platform.tui.live_readiness import unavailable_live_readiness
from vesper.platform.tui.views import (
    AgentCard,
    AlertRow,
    AlertView,
    ApprovalRow,
    CandidateRow,
    ConsoleSnapshot,
    DataView,
    DecimalString,
    EventPayload,
    EventPresentation,
    EvidenceRow,
    FillRow,
    Freshness,
    ImpactView,
    MemoryRow,
    MetricRow,
    ModelOpinionRow,
    ModelsView,
    OperatingMode,
    OrderRow,
    OrdersView,
    PortfolioRow,
    PortfolioView,
    ReturnComponentRow,
    RepositoryRow,
    RiskLimitRow,
    RiskView,
    ServiceRow,
    SourceRow,
    SystemView,
    TimelineRow,
    TimelineView,
    UtcDateTime,
)


NOW = datetime(2026, 8, 3, 16, 0, tzinfo=timezone.utc)
SHA = "a" * 64
SHARED_FIXTURE = (
    Path(__file__).parents[3]
    / "TUI testing"
    / "contracts"
    / "v1"
    / "console_snapshot_empty_command_specs.json"
)


def _screen(source: str = "fixture") -> dict[str, object]:
    return {
        "freshness": Freshness.FRESH,
        "as_of_utc": NOW,
        "source": source,
        "error": None,
    }


def _shell() -> dict[str, object]:
    return {
        "state_version": 7,
        "generated_at_utc": NOW,
        "header": {
            "operating_mode": OperatingMode.SHADOW,
            "operating_mode_freshness": Freshness.FRESH,
            "operating_mode_reason": None,
            "data_freshness": Freshness.FRESH,
            "data_age_seconds": 1.0,
            "regime_label": "risk-on",
            "regime_confidence": 0.8,
            "portfolio_value": 1000.0,
            "next_rebalance_at_utc": NOW,
            "rebalance_blockers": (),
            "active_agent": "portfolio-research",
            "agent_queue_length": 1,
            "qwen_state": "busy",
            "qwen_context_percent": 25.0,
            "current_time_utc": NOW,
            "market_session": "Open",
        },
        "alerts": (),
        "capabilities": (),
    }


def _event_presentation(snapshot: ConsoleSnapshot) -> EventPresentation:
    def meta(name: str) -> dict[str, object]:
        view = getattr(snapshot, name)
        return {
            "freshness": view.freshness.value,
            "as_of_utc": view.as_of_utc.isoformat().replace("+00:00", "Z"),
            "source": view.source,
            "error": view.error,
        }

    return EventPresentation.model_validate_json(
        json.dumps(
            {
                "generated_at_utc": snapshot.shell.generated_at_utc.isoformat().replace(
                    "+00:00", "Z"
                ),
                "header": snapshot.shell.header.model_dump(mode="json"),
                "control_version": snapshot.control_version,
                "control_hash": snapshot.control_hash,
                "window_omissions": [
                    item.model_dump(mode="json") for item in snapshot.window_omissions
                ],
                **{
                    name: meta(name)
                    for name in (
                        "impact",
                        "portfolio",
                        "orders",
                        "agents",
                        "models",
                        "timeline",
                        "risk",
                        "data",
                        "memory",
                        "system",
                    )
                },
                "portfolio_rank_source": snapshot.portfolio.rank_source,
                "timeline_hidden_event_count": snapshot.timeline.hidden_event_count,
                "model_active_model_id": snapshot.models.active_model_id,
                "model_rollback_model_id": snapshot.models.rollback_model_id,
                "model_approved_family": snapshot.models.approved_family,
                "model_approved_strategy": snapshot.models.approved_strategy,
                "model_approved_feature_set_id": snapshot.models.approved_feature_set_id,
                "model_final_regime": snapshot.models.final_regime,
                "model_final_regime_confidence": snapshot.models.final_regime_confidence,
                "model_regime_state": snapshot.models.regime_state,
                "model_automatic_changes_blocked": snapshot.models.automatic_changes_blocked,
                "model_block_reason": snapshot.models.block_reason,
                "model_gates": [item.model_dump(mode="json") for item in snapshot.models.gates],
                "risk_blocked_actions": [
                    item.model_dump(mode="json") for item in snapshot.risk.blocked_actions
                ],
                "risk_circuit_breaker": snapshot.risk.circuit_breaker.model_dump(mode="json"),
                "system_qwen": snapshot.system.qwen.model_dump(mode="json"),
                "system_health": [
                    item.model_dump(mode="json") for item in snapshot.system.health
                ],
            }
        )
    )


@pytest.fixture
def full_snapshot_payload() -> dict[str, object]:
    portfolio = {
        "symbol": "AAPL",
        "description": "Apple",
        "asset_type": "stock",
        "quantity": "10",
        "price": "100.25",
        "market_value": "1002.50",
        "current_weight": 0.6,
        "proposed_weight": 0.55,
        "approved_weight": None,
        "change_state": "proposed",
        "confirmed_rank": 1,
        "reconciliation": "pending",
    }
    agent = {
        "work_id": "work:1",
        "agent": "portfolio-research",
        "title": "Review AAPL",
        "stage": "running",
        "priority": 1,
        "urgent": False,
        "elapsed_seconds": 3.0,
        "model": "qwen:64k",
        "affected_areas": ("portfolio",),
        "session_id": "session:1",
        "plan_steps": ("Inspect evidence", "Report result"),
        "activity": (
            {
                "activity_id": "activity:1",
                "kind": "stage",
                "summary": "Review started",
                "occurred_at_utc": NOW,
                "evidence_ids": ("evidence:1",),
            },
        ),
        "evidence_ids": ("evidence:1",),
        "context_percent": 25.0,
        "chat_agent_id": "portfolio-research",
        "detail_next_cursor": None,
    }
    timeline = {
        "event_id": "event:1",
        "occurred_at_utc": NOW,
        "impact": True,
        "severity": "active",
        "summary": "AAPL review started",
        "agent_id": "portfolio-research",
        "symbol": "AAPL",
        "model_id": None,
        "approval_id": None,
        "order_id": None,
        "evidence_ids": ("evidence:1",),
        "work_id": "work:1",
    }
    fill = {
        "fill_id": "fill:1",
        "quantity": "10",
        "price": "100.25",
        "fee": "0",
        "filled_at_utc": NOW,
    }
    order = {
        "order_id": "order:1",
        "symbol": "AAPL",
        "side": "buy",
        "quantity": "10",
        "status": "filled",
        "submitted_at_utc": NOW,
        "broker_order_id": "paper-order-1",
        "fills": (fill,),
        "expected_price": "100.00",
        "actual_price": "100.25",
        "reconciliation": "matched",
    }
    opinion = {
        "model_id": "model:active",
        "regime": "risk-on",
        "confidence": 0.8,
        "as_of_utc": NOW,
    }
    candidate = {
        "candidate_id": "candidate:1",
        "family": "approved-family",
        "strategy": "ml_model",
        "status": "evaluating",
        "evidence_ids": ("evidence:1",),
        "created_at_utc": NOW,
        "feature_set_id": "features:v1",
        "data_identity": SHA,
        "evaluation_contract": SHA,
        "status_reason": "Evaluation is running.",
        "status_at_utc": NOW,
    }
    risk_limit = {
        "limit_id": "limit:concentration",
        "current_value": "0.10",
        "proposed_value": None,
        "status": "within",
        "proposal_reason": None,
        "review_state": "not-required",
        "evidence_ids": (),
    }
    approval = {
        "approval_id": "approval:1",
        "run_id": "run:1",
        "checkpoint_id": "checkpoint:1",
        "state": "pending",
        "reason": "Review required",
        "evidence_ids": ("evidence:1",),
        "requested_at_utc": NOW,
        "affected_symbols": ("AAPL",),
        "weight_changes": (
            {"symbol": "AAPL", "current_weight": 0.6, "proposed_weight": 0.55},
        ),
        "risks": ("Concentration changes.",),
        "expected_consequences": ("AAPL weight decreases.",),
        "basis_sha256": SHA,
        "stale_reason": None,
    }
    source = {
        "source_id": "source:massive",
        "freshness": Freshness.FRESH,
        "as_of_utc": NOW,
        "age_seconds": 1.0,
        "coverage": "S&P 500",
        "error": None,
        "consumers": ("ml_model",),
        "dependencies": ("split adjustments",),
    }
    evidence = {
        "evidence_id": "evidence:1",
        "evidence_type": "receipt",
        "source": "fixture",
        "created_at_utc": NOW,
        "sha256": SHA,
        "symbols": ("AAPL",),
        "agent_ids": ("portfolio-research",),
        "model_ids": ("model:active",),
        "order_ids": ("order:1",),
        "approval_ids": ("approval:1",),
        "source_ids": ("source:massive",),
        "raw_log_id": None,
        "raw_log_excerpt": (),
        "raw_log_truncated": False,
        "raw_log_next_cursor": None,
    }
    memory = {
        "memory_id": "memory:1",
        "status": "core",
        "summary": "Use controller truth.",
        "evidence_ids": ("evidence:1",),
        "updated_at_utc": NOW,
        "used_by_agents": ("portfolio-research",),
        "change_reason": "Retained controller authority rule.",
    }
    service = {
        "service_id": "service:qwen",
        "state": "running",
        "health_reason": None,
        "observed_at_utc": NOW,
    }
    repository = {
        "repository_id": "repository:v20",
        "freshness": Freshness.FRESH,
        "as_of_utc": NOW,
        "source": "git",
        "error": None,
        "branch": "codex/vesper/ratatui-console",
        "revision": "0123456789abcdef",
        "clean": True,
        "worktrees": ("C:/Users/bgonn/Desktop/v20",),
        "unpushed_commit_count": 0,
        "checks": (
            {
                "check_id": "check:tests",
                "state": "pass",
                "reason": None,
                "observed_at_utc": NOW,
            },
        ),
    }
    metric = {
        "metric_id": "metric:cpu",
        "value": 12.5,
        "unit": "percent",
        "freshness": Freshness.FRESH,
        "observed_at_utc": NOW,
        "error": None,
    }
    returns = (
        {"component": "price", "value": "0.01"},
        {"component": "dividends", "value": "0"},
        {"component": "cash-interest", "value": "0"},
        {"component": "fees", "value": "0"},
        {"component": "sp500-total-return", "value": "0.005"},
    )
    alert = {
        "alert_id": "alert:1",
        "severity": "waiting",
        "summary": "Approval waiting",
        "created_at_utc": NOW,
        "resolved_at_utc": None,
    }
    return {
        "shell": _shell(),
        "control_version": 3,
        "control_hash": SHA,
        "command_specs": (),
        "window_omissions": (),
        "impact": {
            **_screen(),
            "holdings": (portfolio,),
            "events": (timeline,),
            "agents": (agent,),
        },
        "portfolio": {
            **_screen(),
            "rows": (portfolio,),
            "returns_today": returns,
            "returns_since_rebalance": returns,
            "returns_since_start": returns,
            "metrics": (metric,),
            "history": (timeline,),
            "rank_source": "confirmed reconciliation",
        },
        "orders": {
            **_screen(),
            "rows": (order,),
            "reconciliation_agents": (agent,),
            "history": (timeline,),
        },
        "agents": {**_screen(), "rows": (agent,), "history": (timeline,)},
        "models": {
            **_screen(),
            "opinions": (opinion,),
            "candidates": (candidate,),
            "metrics": (metric,),
            "evidence": (evidence,),
            "active_model_id": "model:active",
            "rollback_model_id": None,
            "approved_family": "approved-family",
            "approved_strategy": "ml_model",
            "approved_feature_set_id": "features:v1",
            "final_regime": "risk-on",
            "final_regime_confidence": 0.8,
            "regime_state": "decided",
            "automatic_changes_blocked": False,
            "block_reason": None,
            "gates": (
                {
                    "gate_id": "gate:oos-ic",
                    "candidate_id": "candidate:1",
                    "metric_id": "model.oos-ic",
                    "candidate_value": 0.12,
                    "baseline_value": 0.08,
                    "comparison": "gte",
                    "threshold": 0.1,
                    "evaluation_window": "2025-01-01/2025-12-31",
                    "state": "pass",
                    "reason": "Candidate cleared the approved threshold.",
                    "evidence_ids": ("evidence:1",),
                },
            ),
        },
        "timeline": {**_screen(), "rows": (timeline,), "hidden_event_count": 0},
        "risk": {
            **_screen(),
            "limits": (risk_limit,),
            "approvals": (approval,),
            "alerts": (alert,),
            "metrics": (metric,),
            "blocked_actions": (),
            "circuit_breaker": {
                "state": "armed",
                "reason": None,
                "observed_at_utc": NOW,
            },
        },
        "data": {**_screen(), "sources": (source,), "evidence": (evidence,)},
        "memory": {
            **_screen(),
            "rows": (memory,),
            "history": (timeline,),
            "agent_usage_error": "No trusted memory-use source is configured.",
        },
        "system": {
            **_screen(),
            "services": (service,),
            "metrics": (metric,),
            "repositories": (repository,),
            "live_readiness": unavailable_live_readiness(),
            "live_account": None,
            "live_transition_plan": None,
            "qwen": {
                "state": "busy",
                "loaded_model": "qwen:64k",
                "current_agent": "portfolio-research",
                "queue_length": 1,
                "context_percent": 25.0,
                "last_inference_ms": 210.0,
                "observed_at_utc": NOW,
                "error": None,
            },
            "health": tuple(
                {
                    "component": component,
                    "state": "healthy",
                    "reason": None,
                    "observed_at_utc": NOW,
                    "checks": (
                        {
                            "check_id": f"check:{component}",
                            "state": "pass",
                            "reason": None,
                        },
                    ),
                    "broker_actions_blocked": False,
                }
                for component in ("backup", "recovery", "notifications")
            ),
        },
    }


def test_console_snapshot_requires_all_ten_strict_views(full_snapshot_payload) -> None:
    snapshot = ConsoleSnapshot.model_validate(full_snapshot_payload)

    assert snapshot.portfolio.rows[0].symbol == "AAPL"
    assert snapshot.command_specs == ()
    for name in (
        "impact",
        "portfolio",
        "orders",
        "agents",
        "models",
        "timeline",
        "risk",
        "data",
        "memory",
        "system",
    ):
        missing = dict(full_snapshot_payload)
        missing.pop(name)
        with pytest.raises(ValidationError):
            ConsoleSnapshot.model_validate(missing)
    with pytest.raises(ValidationError):
        ConsoleSnapshot.model_validate({**full_snapshot_payload, "unknown": True})


@pytest.mark.parametrize(
    "value",
    ["0", "-0", "10", "-10", "0.25", "-0.25", "12345678901234567890.0001"],
)
def test_decimal_string_accepts_only_canonical_bounded_base_ten(value: str) -> None:
    assert TypeAdapter(DecimalString).validate_python(value, strict=True) == value


@pytest.mark.parametrize(
    "value",
    ["", " ", "+1", "01", ".5", "1.", "1e2", "NaN", "Infinity", "-Infinity", "1" * 129],
)
def test_decimal_string_rejects_noncanonical_or_unbounded_values(value: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(DecimalString).validate_python(value, strict=True)


def test_times_floats_and_u64_values_are_strict_and_bounded(full_snapshot_payload) -> None:
    with pytest.raises(ValidationError):
        ModelOpinionRow(
            model_id="model:1",
            regime="risk-on",
            confidence=math.inf,
            as_of_utc=NOW,
        )
    with pytest.raises(ValidationError):
        ModelOpinionRow(
            model_id="model:1",
            regime="risk-on",
            confidence=0.5,
            as_of_utc=NOW.astimezone(timezone(timedelta(hours=-4))),
        )
    for value in (-1, 2**64):
        payload = {**full_snapshot_payload, "control_version": value}
        with pytest.raises(ValidationError):
            ConsoleSnapshot.model_validate(payload)
    with pytest.raises(ValidationError):
        AgentCard(
            work_id="work:1",
            agent="agent",
            title="title",
            stage="queued",
            priority=101,
            urgent=False,
            elapsed_seconds=None,
            model=None,
            affected_areas=(),
        )


@pytest.mark.parametrize(
    "value",
    [
        "2026-08-03T00:00:00Z",
        "2026-08-03T00:00:00+00:00",
        "2026-08-03T00:00:00.1Z",
        "2026-08-03T00:00:00.123456+00:00",
    ],
)
def test_utc_timestamp_accepts_only_shared_zero_offset_forms(value: str) -> None:
    parsed = TypeAdapter(UtcDateTime).validate_json(json.dumps(value))
    assert parsed.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-08-03T00:00:00Z", '"2026-08-03T00:00:00Z"'),
        ("2026-08-03T00:00:00+00:00", '"2026-08-03T00:00:00Z"'),
        ("2026-08-03T00:00:00.1Z", '"2026-08-03T00:00:00.100000Z"'),
        ("2026-08-03T00:00:00.123+00:00", '"2026-08-03T00:00:00.123000Z"'),
        ("2026-08-03T00:00:00.000000Z", '"2026-08-03T00:00:00Z"'),
    ],
)
def test_utc_timestamp_serialization_uses_zero_or_six_fraction_digits(
    value: str,
    expected: str,
) -> None:
    adapter = TypeAdapter(UtcDateTime)
    parsed = adapter.validate_json(json.dumps(value))
    assert adapter.dump_json(parsed).decode() == expected


@pytest.mark.parametrize(
    "value",
    [
        "2026-08-03T00:00:00-04:00",
        "2026-08-03 00:00:00Z",
        "2026-02-30T00:00:00Z",
        "2026-08-03T00:00:00.Z",
        "2026-08-03T00:00:00.1234567Z",
    ],
)
def test_utc_timestamp_rejects_noncanonical_or_invalid_forms(value: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(UtcDateTime).validate_json(json.dumps(value))


def test_screen_freshness_requires_truthful_time_and_error() -> None:
    fields = {
        "rows": (),
        "returns_today": (),
        "returns_since_rebalance": (),
        "returns_since_start": (),
        "metrics": (),
        "history": (),
        "rank_source": None,
    }
    with pytest.raises(ValidationError):
        PortfolioView(
            freshness=Freshness.FRESH,
            as_of_utc=None,
            source="fixture",
            error=None,
            **fields,
        )
    with pytest.raises(ValidationError):
        PortfolioView(
            freshness=Freshness.STALE,
            as_of_utc=NOW,
            source="fixture",
            error=None,
            **fields,
        )
    unavailable = PortfolioView(
        freshness=Freshness.UNAVAILABLE,
        as_of_utc=None,
        source="fixture",
        error="No controller-owned portfolio adapter is configured.",
        **fields,
    )
    assert unavailable.freshness is Freshness.UNAVAILABLE


def test_event_payload_is_closed_and_binds_operation_type_and_primary_id(
    full_snapshot_payload,
) -> None:
    snapshot = ConsoleSnapshot.model_validate(full_snapshot_payload)
    presentation = _event_presentation(snapshot)
    targets_by_type = {
        "portfolio-row": ("impact.holdings", "portfolio.rows"),
        "agent-card": ("impact.agents", "orders.reconciliation-agents", "agents.rows"),
        "timeline-row": (
            "impact.events",
            "portfolio.history",
            "orders.history",
            "agents.history",
            "timeline.rows",
            "memory.history",
        ),
        "order-row": ("orders.rows",),
        "model-opinion-row": ("models.opinions",),
        "candidate-row": ("models.candidates",),
        "risk-limit-row": ("risk.limits",),
        "approval-row": ("risk.approvals",),
        "source-row": ("data.sources",),
        "evidence-row": ("models.evidence", "data.evidence"),
        "memory-row": ("memory.rows",),
        "service-row": ("system.services",),
        "repository-row": ("system.repositories",),
        "metric-row": (
            "portfolio.metrics",
            "models.metrics",
            "risk.metrics",
            "system.metrics",
        ),
        "return-component-row": (
            "portfolio.returns-today",
            "portfolio.returns-since-rebalance",
            "portfolio.returns-since-start",
        ),
        "alert-row": ("shell.alerts", "risk.alerts"),
    }
    entities = (
        ("portfolio-row", "AAPL", snapshot.portfolio.rows[0], PortfolioRow),
        ("agent-card", "work:1", snapshot.agents.rows[0], AgentCard),
        ("timeline-row", "event:1", snapshot.timeline.rows[0], TimelineRow),
        ("order-row", "order:1", snapshot.orders.rows[0], OrderRow),
        ("model-opinion-row", "model:active", snapshot.models.opinions[0], ModelOpinionRow),
        ("candidate-row", "candidate:1", snapshot.models.candidates[0], CandidateRow),
        ("risk-limit-row", "limit:concentration", snapshot.risk.limits[0], RiskLimitRow),
        ("approval-row", "approval:1", snapshot.risk.approvals[0], ApprovalRow),
        ("source-row", "source:massive", snapshot.data.sources[0], SourceRow),
        ("evidence-row", "evidence:1", snapshot.data.evidence[0], EvidenceRow),
        ("memory-row", "memory:1", snapshot.memory.rows[0], MemoryRow),
        ("service-row", "service:qwen", snapshot.system.services[0], ServiceRow),
        (
            "repository-row",
            "repository:v20",
            snapshot.system.repositories[0],
            RepositoryRow,
        ),
        ("metric-row", "metric:cpu", snapshot.system.metrics[0], MetricRow),
        ("return-component-row", "price", snapshot.portfolio.returns_today[0], ReturnComponentRow),
        ("alert-row", "alert:1", snapshot.risk.alerts[0], AlertRow),
    )
    for entity_type, entity_id, entity, expected_type in entities:
        event = EventPayload(
            entity_type=entity_type,
            entity_id=entity_id,
            operation="upsert",
            entity=entity,
            targets=targets_by_type[entity_type],
            presentation=presentation,
        )
        assert isinstance(event.entity, expected_type)
        incompatible = "orders.rows" if entity_type == "alert-row" else "shell.alerts"
        with pytest.raises(ValidationError):
            EventPayload(
                entity_type=entity_type,
                entity_id=entity_id,
                operation="upsert",
                entity=entity,
                targets=(incompatible,),
                presentation=presentation,
            )

    assert (
        EventPayload(
            entity_type="portfolio-row",
            entity_id="AAPL",
            operation="remove",
            entity=None,
            targets=("portfolio.rows",),
            presentation=presentation,
        ).entity
        is None
    )
    invalid = (
        {
            "entity_type": "portfolio-row",
            "entity_id": "MSFT",
            "operation": "upsert",
            "entity": snapshot.portfolio.rows[0],
            "targets": ("portfolio.rows",),
            "presentation": presentation,
        },
        {
            "entity_type": "order-row",
            "entity_id": "AAPL",
            "operation": "upsert",
            "entity": snapshot.portfolio.rows[0],
            "targets": ("orders.rows",),
            "presentation": presentation,
        },
        {
            "entity_type": "portfolio-row",
            "entity_id": "AAPL",
            "operation": "upsert",
            "entity": None,
            "targets": ("portfolio.rows",),
            "presentation": presentation,
        },
        {
            "entity_type": "portfolio-row",
            "entity_id": "AAPL",
            "operation": "remove",
            "entity": snapshot.portfolio.rows[0],
            "targets": ("portfolio.rows",),
            "presentation": presentation,
        },
        {
            "entity_type": "unknown-row",
            "entity_id": "AAPL",
            "operation": "remove",
            "entity": None,
            "targets": ("portfolio.rows",),
            "presentation": presentation,
        },
    )
    for payload in invalid:
        with pytest.raises(ValidationError):
            EventPayload.model_validate(payload)

    order_json = snapshot.orders.rows[0].model_dump_json()
    event = EventPayload.model_validate_json(
        json.dumps(
            {
                "entity_type": "order-row",
                "entity_id": "order:1",
                "operation": "upsert",
                "entity": json.loads(order_json),
                "targets": ["orders.rows"],
                "presentation": presentation.model_dump(mode="json"),
            }
        )
    )
    assert isinstance(event.entity, OrderRow)
    assert event.entity.fills[0].fill_id == "fill:1"


def test_event_targets_are_required_bounded_unique_canonical_and_closed(
    full_snapshot_payload,
) -> None:
    snapshot = ConsoleSnapshot.model_validate(full_snapshot_payload)
    entity = snapshot.portfolio.rows[0]
    base = {
        "entity_type": "portfolio-row",
        "entity_id": "AAPL",
        "operation": "upsert",
        "entity": entity,
        "targets": ("impact.holdings", "portfolio.rows"),
        "presentation": _event_presentation(snapshot),
    }
    for invalid_targets in (
        (),
        ("portfolio.rows", "impact.holdings"),
        ("portfolio.rows", "portfolio.rows"),
        ("unknown.target",),
        ("portfolio.rows",) * 9,
    ):
        with pytest.raises(ValidationError):
            EventPayload.model_validate({**base, "targets": invalid_targets})
    missing = dict(base)
    missing.pop("targets")
    with pytest.raises(ValidationError):
        EventPayload.model_validate(missing)
    with pytest.raises(ValidationError):
        EventPayload.model_validate(
            {
                **base,
                "entity_type": "fill-row",
                "entity_id": "fill:1",
                "entity": ConsoleSnapshot.model_validate(full_snapshot_payload)
                .orders.rows[0]
                .fills[0],
                "targets": ("orders.rows",),
            }
        )


def test_metric_freshness_and_window_omissions_are_truthful(full_snapshot_payload) -> None:
    base_metric = {
        "metric_id": "metric:test",
        "unit": "percent",
        "value": 1.0,
        "freshness": Freshness.FRESH,
        "observed_at_utc": NOW,
        "error": None,
    }
    assert MetricRow.model_validate(base_metric).value == 1.0
    assert (
        MetricRow.model_validate(
            {**base_metric, "freshness": Freshness.STALE, "error": "Delayed."}
        ).value
        == 1.0
    )
    assert (
        MetricRow.model_validate(
            {
                **base_metric,
                "freshness": Freshness.UNAVAILABLE,
                "value": None,
                "observed_at_utc": None,
                "error": "Unavailable.",
            }
        ).value
        is None
    )
    assert (
        MetricRow.model_validate(
            {
                **base_metric,
                "freshness": Freshness.LOADING,
                "value": None,
                "observed_at_utc": None,
                "error": None,
            }
        ).value
        is None
    )
    for invalid in (
        {**base_metric, "value": None},
        {**base_metric, "freshness": Freshness.STALE, "error": None},
        {**base_metric, "freshness": Freshness.UNAVAILABLE, "error": "Unavailable."},
        {**base_metric, "freshness": Freshness.LOADING},
    ):
        with pytest.raises(ValidationError):
            MetricRow.model_validate(invalid)

    valid = {
        **full_snapshot_payload,
        "window_omissions": (
            {"target": "models.evidence", "omitted_count": None},
            {"target": "timeline.rows", "omitted_count": 3},
        ),
    }
    assert len(ConsoleSnapshot.model_validate(valid).window_omissions) == 2
    for omissions in (
        ({"target": "timeline.rows", "omitted_count": 0},),
        (
            {"target": "timeline.rows", "omitted_count": 1},
            {"target": "timeline.rows", "omitted_count": 2},
        ),
        (
            {"target": "timeline.rows", "omitted_count": 1},
            {"target": "models.evidence", "omitted_count": 2},
        ),
    ):
        with pytest.raises(ValidationError):
            ConsoleSnapshot.model_validate({**full_snapshot_payload, "window_omissions": omissions})


def test_alert_row_is_the_existing_shell_alert_contract() -> None:
    assert AlertRow is AlertView


def test_shared_snapshot_fixture_is_canonical_and_strict() -> None:
    raw = SHARED_FIXTURE.read_bytes().rstrip(b"\r\n")
    snapshot = ConsoleSnapshot.model_validate_json(raw)

    assert snapshot.command_specs == ()
    assert snapshot.model_dump_json().encode("utf-8") == raw
    assert len(raw) < 1_048_576


def test_repository_row_is_strict_and_freshness_is_truthful(full_snapshot_payload) -> None:
    repository = full_snapshot_payload["system"]["repositories"][0]
    row = RepositoryRow.model_validate(repository)
    assert row.repository_id == "repository:v20"
    assert row.clean is True
    assert row.unpushed_commit_count == 0

    missing_nullable = dict(repository)
    missing_nullable.pop("branch")
    with pytest.raises(ValidationError):
        RepositoryRow.model_validate(missing_nullable)

    stale_without_reason = {**repository, "freshness": Freshness.STALE, "error": None}
    with pytest.raises(ValidationError):
        RepositoryRow.model_validate(stale_without_reason)


def test_nullable_fields_are_required_but_accept_explicit_null(full_snapshot_payload) -> None:
    snapshot = ConsoleSnapshot.model_validate(full_snapshot_payload)
    order = snapshot.orders.rows[0].model_dump(mode="json")
    assert order["broker_order_id"] == "paper-order-1"
    order["broker_order_id"] = None
    assert OrderRow.model_validate_json(json.dumps(order)).broker_order_id is None
    order.pop("broker_order_id")
    with pytest.raises(ValidationError):
        OrderRow.model_validate_json(json.dumps(order))


def test_each_named_screen_is_a_strict_screen_view() -> None:
    assert {
        ImpactView,
        PortfolioView,
        OrdersView,
        ModelsView,
        TimelineView,
        RiskView,
        DataView,
        SystemView,
    }


def test_agent_deep_detail_contract_is_bounded_and_linked() -> None:
    activity = tui_views.AgentActivityRow(
        activity_id="activity:1",
        kind="tool",
        summary="Read controller state",
        occurred_at_utc=NOW,
        evidence_ids=("evidence:1",),
    )
    card = AgentCard(
        work_id="work:1",
        agent="portfolio-research",
        title="Review AAPL",
        stage="running",
        priority=1,
        urgent=False,
        elapsed_seconds=3.0,
        model="qwen:64k",
        affected_areas=("portfolio",),
        session_id="session:1",
        plan_steps=("Inspect evidence", "Report result"),
        activity=(activity,),
        evidence_ids=("evidence:1",),
        context_percent=62.5,
        chat_agent_id="portfolio-research",
        detail_next_cursor="cursor:2",
    )

    assert card.activity == (activity,)
    assert card.session_id == "session:1"
    missing_session = card.model_dump()
    missing_session.pop("session_id")
    with pytest.raises(ValidationError):
        AgentCard.model_validate(missing_session)
    with pytest.raises(ValidationError):
        AgentCard.model_validate({**card.model_dump(), "context_percent": 100.1})

    timeline = TimelineRow(
        event_id="event:1",
        occurred_at_utc=NOW,
        impact=True,
        severity="active",
        summary="Work started",
        agent_id="portfolio-research",
        work_id="work:1",
        symbol=None,
        model_id=None,
        approval_id=None,
        order_id=None,
        evidence_ids=(),
    )
    assert timeline.work_id == card.work_id


def test_model_summary_requires_fail_closed_regime_state() -> None:
    gate = tui_views.ModelGateRow(
        gate_id="gate:oos-ic",
        candidate_id="candidate:1",
        metric_id="model.oos-ic",
        candidate_value=0.12,
        baseline_value=0.08,
        comparison="gte",
        threshold=0.1,
        evaluation_window="2025-01-01/2025-12-31",
        state="pass",
        reason="Candidate cleared the approved threshold.",
        evidence_ids=("evidence:1",),
    )
    fields = {
        **_screen(),
        "opinions": (),
        "candidates": (),
        "metrics": (),
        "evidence": (),
        "active_model_id": "model:active",
        "rollback_model_id": "model:rollback",
        "approved_family": "xgboost",
        "approved_strategy": "ml_model",
        "approved_feature_set_id": "features:v1",
        "final_regime": "risk-on",
        "final_regime_confidence": 0.8,
        "regime_state": "decided",
        "automatic_changes_blocked": False,
        "block_reason": None,
        "gates": (gate,),
    }

    assert ModelsView(**fields).gates == (gate,)
    with pytest.raises(ValidationError):
        ModelsView(**{**fields, "final_regime": None})
    with pytest.raises(ValidationError):
        ModelsView(
            **{
                **fields,
                "final_regime": None,
                "final_regime_confidence": None,
                "regime_state": "uncertain",
                "automatic_changes_blocked": False,
                "block_reason": None,
            }
        )

    candidate = {
        "candidate_id": "candidate:1",
        "family": "xgboost",
        "strategy": "ml_model",
        "status": "evaluating",
        "evidence_ids": (),
        "created_at_utc": NOW,
        "feature_set_id": None,
        "data_identity": "not-a-sha256",
        "evaluation_contract": SHA,
        "status_reason": None,
        "status_at_utc": None,
    }
    with pytest.raises(ValidationError):
        CandidateRow.model_validate(candidate)


def test_risk_contract_exposes_blocks_breaker_and_stale_approval_reason() -> None:
    blocked = tui_views.BlockedActionRow(
        action_id="block:1",
        action="rebalance",
        reason="Portfolio read-back mismatch.",
        affected_symbols=("AAPL",),
        created_at_utc=NOW,
    )
    breaker = tui_views.CircuitBreakerView(
        state="tripped",
        reason="Daily loss limit breached.",
        observed_at_utc=NOW,
    )
    risk = RiskView(
        **_screen(),
        limits=(),
        approvals=(),
        alerts=(),
        metrics=(),
        blocked_actions=(blocked,),
        circuit_breaker=breaker,
    )
    assert risk.blocked_actions == (blocked,)
    assert risk.circuit_breaker.state == "tripped"

    approval = {
        "approval_id": "approval:1",
        "run_id": "run:1",
        "checkpoint_id": "checkpoint:1",
        "state": "stale",
        "reason": "Inputs changed.",
        "evidence_ids": ("evidence:1",),
        "requested_at_utc": NOW,
        "affected_symbols": ("AAPL",),
        "weight_changes": (
            {"symbol": "AAPL", "current_weight": 0.1, "proposed_weight": 0.11},
        ),
        "risks": ("Concentration increased.",),
        "expected_consequences": ("AAPL allocation rises.",),
        "basis_sha256": SHA,
        "stale_reason": None,
    }
    with pytest.raises(ValidationError):
        ApprovalRow.model_validate(approval)
    assert ApprovalRow.model_validate(
        {**approval, "stale_reason": "Portfolio basis changed."}
    ).state == "stale"


def test_evidence_memory_source_and_repository_details_are_explicit() -> None:
    evidence = tui_views.EvidenceRow(
        evidence_id="evidence:1",
        evidence_type="agent-log",
        source="controller",
        created_at_utc=NOW,
        sha256=SHA,
        symbols=("AAPL",),
        agent_ids=("portfolio-research",),
        model_ids=("model:active",),
        order_ids=("order:1",),
        approval_ids=("approval:1",),
        source_ids=("source:massive",),
        raw_log_id="log:1",
        raw_log_excerpt=("line 1",),
        raw_log_truncated=True,
        raw_log_next_cursor="cursor:2",
    )
    assert evidence.raw_log_excerpt == ("line 1",)
    with pytest.raises(ValidationError):
        tui_views.EvidenceRow.model_validate(
            {**evidence.model_dump(), "raw_log_id": None}
        )

    source = SourceRow(
        source_id="source:massive",
        freshness=Freshness.FRESH,
        as_of_utc=NOW,
        age_seconds=1.0,
        coverage="S&P 500",
        error=None,
        consumers=("portfolio",),
        dependencies=("split adjustments",),
    )
    assert source.dependencies == ("split adjustments",)

    memory = MemoryRow(
        memory_id="memory:1",
        status="core",
        summary="Keep broker reconciliation fail-closed.",
        evidence_ids=("evidence:1",),
        updated_at_utc=NOW,
        used_by_agents=("risk-agent",),
        change_reason="Required safety rule.",
    )
    assert memory.used_by_agents == ("risk-agent",)

    check = tui_views.RepositoryCheckRow(
        check_id="check:tests",
        state="pass",
        reason=None,
        observed_at_utc=NOW,
    )
    assert check.state == "pass"
    with pytest.raises(ValidationError):
        tui_views.RepositoryCheckRow(
            check_id="check:tests",
            state="fail",
            reason=None,
            observed_at_utc=NOW,
        )


def test_system_detail_is_explicit_and_has_each_health_component_once() -> None:
    qwen = tui_views.QwenStatusView(
        state="busy",
        loaded_model="qwen:64k",
        current_agent="portfolio-research",
        queue_length=2,
        context_percent=75.0,
        last_inference_ms=210.0,
        observed_at_utc=NOW,
        error=None,
    )
    health = tuple(
        tui_views.SystemHealthRow(
            component=component,
            state="healthy",
            reason=None,
            observed_at_utc=NOW,
            checks=(
                tui_views.SystemHealthCheckRow(
                    check_id=f"check:{component}",
                    state="pass",
                    reason=None,
                ),
            ),
            broker_actions_blocked=False,
        )
        for component in ("backup", "recovery", "notifications")
    )
    fields = {
        **_screen(),
        "services": (),
        "metrics": (),
        "repositories": (),
        "live_readiness": unavailable_live_readiness(),
        "live_account": None,
        "live_transition_plan": None,
        "qwen": qwen,
        "health": health,
    }

    assert len(SystemView(**fields).health) == 3
    with pytest.raises(ValidationError):
        SystemView(**{**fields, "health": health[:-1]})
    with pytest.raises(ValidationError):
        tui_views.QwenStatusView(
            state="unavailable",
            loaded_model=None,
            current_agent=None,
            queue_length=None,
            context_percent=None,
            last_inference_ms=None,
            observed_at_utc=None,
            error=None,
        )
    with pytest.raises(ValidationError):
        tui_views.SystemHealthCheckRow(
            check_id="check:recovery",
            state="unavailable",
            reason=None,
        )
    with pytest.raises(ValidationError):
        tui_views.SystemHealthRow(
            component="recovery",
            state="blocked",
            reason=None,
            observed_at_utc=NOW,
            checks=(),
            broker_actions_blocked=True,
        )
