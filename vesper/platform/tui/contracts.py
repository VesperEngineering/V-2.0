"""Strict, versioned wire and read-only shell contracts for the V20 console."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from typing import Annotated, Literal, TypeAlias, cast

from pydantic import (
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
)
from typing_extensions import TypeAliasType

from .search import SearchFilters, SearchResult
from .views import (
    AlertView,
    CapabilityState,
    CapabilityView,
    ConsoleSnapshot,
    EventPayload,
    FiniteFloat,
    Freshness,
    HeaderView,
    NonEmptyStr,
    OperatingMode,
    SafeId,
    Sha256Hex,
    ShellSnapshot,
    StrictModel,
    WireUInt,
    UtcDateTime,
    event_model,
)

MAX_UNTRUSTED_UNKNOWN_FIELDS = 16
MAX_UNTRUSTED_JSON_DEPTH = 8
MAX_UNTRUSTED_JSON_ITEMS = 32
MAX_UNTRUSTED_STRING_LENGTH = 4096
_MISSING = object()


JsonScalar: TypeAlias = None | bool | int | FiniteFloat | str
JsonValue = TypeAliasType(
    "JsonValue",
    JsonScalar | list["JsonValue"] | dict[str, "JsonValue"],
)
class MessageType(StrEnum):
    CLIENT_HELLO = "client-hello"
    SERVER_HELLO = "server-hello"
    AUTH_SETUP = "auth-setup"
    AUTH_UNLOCK = "auth-unlock"
    AUTH_RESULT = "auth-result"
    LEASE_REQUEST = "lease-request"
    LEASE_RESULT = "lease-result"
    LOCK_REQUEST = "lock-request"
    LOCK_RESULT = "lock-result"
    SNAPSHOT_REQUEST = "snapshot-request"
    SNAPSHOT = "snapshot"
    SEARCH_REQUEST = "search-request"
    SEARCH_RESULTS = "search-results"
    EVENT = "event"
    PROTOCOL_ERROR = "protocol-error"
    PING = "ping"
    PONG = "pong"

def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


class WireEnvelope(StrictModel):
    schema_version: Literal[1]
    message_id: SafeId
    sequence: WireUInt
    state_version: WireUInt
    timestamp_utc: UtcDateTime
    message_type: MessageType
    payload: dict[str, JsonValue]

    @field_validator("message_id")
    @classmethod
    def reject_dot_ids(cls, value: str) -> str:
        if value in {".", ".."}:
            raise ValueError("wire IDs cannot be dot paths")
        return value

CANONICAL_WIRE_FIXTURE = (
    b'{"schema_version":1,"message_id":"server:1","sequence":1,'
    b'"state_version":0,"timestamp_utc":"2026-08-03T00:00:00Z",'
    b'"message_type":"server-hello",'
    b'"payload":{"server_version":"0.1.0","requires_setup":true}}'
)
CANONICAL_WIRE_FIXTURE_SHA256 = hashlib.sha256(CANONICAL_WIRE_FIXTURE).hexdigest()
WIRE_SCHEMA_RECEIPT = _canonical_json_bytes(WireEnvelope.model_json_schema())
WIRE_SCHEMA_RECEIPT_SHA256 = hashlib.sha256(WIRE_SCHEMA_RECEIPT).hexdigest()


class ClientHelloPayload(StrictModel):
    client_version: NonEmptyStr
    supported_schema_versions: tuple[Literal[1], ...]


class ServerHelloPayload(StrictModel):
    server_version: NonEmptyStr
    requires_setup: bool


class AuthSetupPayload(StrictModel):
    password: Annotated[str, StringConstraints(min_length=1, max_length=1024)]
    confirmation: Annotated[str, StringConstraints(min_length=1, max_length=1024)]


class AuthUnlockPayload(StrictModel):
    password: Annotated[str, StringConstraints(min_length=1, max_length=1024)]


class AuthResultPayload(StrictModel):
    success: bool
    access_state: Literal["locked", "controller", "viewer"]
    reason: str | None


class LeaseRequestPayload(StrictModel):
    action: Literal["take-control"]


class LeaseResultPayload(StrictModel):
    status: Literal["controller", "viewer", "transferred", "lease-held"]
    reason: str | None


class LockRequestPayload(StrictModel):
    action: Literal["lock"]


class LockResultPayload(StrictModel):
    locked: Literal[True]


class SnapshotRequestPayload(StrictModel):
    pass


class SnapshotPayload(StrictModel):
    snapshot: ConsoleSnapshot


SearchQuery = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=256),
]
SearchLimit = Annotated[int, Field(ge=1, le=100)]
SearchRequestId = Annotated[int, Field(ge=1, le=2**64 - 1)]


class SearchRequestPayload(StrictModel):
    request_id: SearchRequestId
    query: SearchQuery
    filters: SearchFilters
    limit: SearchLimit


class SearchResultsPayload(StrictModel):
    request_id: SearchRequestId
    indexed_state_version: WireUInt
    results: Annotated[tuple[SearchResult, ...], Field(max_length=100)]
    error: NonEmptyStr | None


class ProtocolErrorPayload(StrictModel):
    code: SafeId
    safe_message: NonEmptyStr

    @field_validator("code")
    @classmethod
    def reject_dot_ids(cls, value: str) -> str:
        if value in {".", ".."}:
            raise ValueError("wire IDs cannot be dot paths")
        return value


class PingPayload(StrictModel):
    nonce: SafeId

    @field_validator("nonce")
    @classmethod
    def reject_dot_ids(cls, value: str) -> str:
        if value in {".", ".."}:
            raise ValueError("wire IDs cannot be dot paths")
        return value


class PongPayload(PingPayload):
    pass


StrictPayload: TypeAlias = (
    ClientHelloPayload
    | ServerHelloPayload
    | AuthSetupPayload
    | AuthUnlockPayload
    | AuthResultPayload
    | LeaseRequestPayload
    | LeaseResultPayload
    | LockRequestPayload
    | LockResultPayload
    | SnapshotRequestPayload
    | SnapshotPayload
    | SearchRequestPayload
    | SearchResultsPayload
    | EventPayload
    | ProtocolErrorPayload
    | PingPayload
    | PongPayload
)

PayloadModel: TypeAlias = type[StrictPayload]
PAYLOAD_MODELS: dict[MessageType, PayloadModel] = {
    MessageType.CLIENT_HELLO: ClientHelloPayload,
    MessageType.SERVER_HELLO: ServerHelloPayload,
    MessageType.AUTH_SETUP: AuthSetupPayload,
    MessageType.AUTH_UNLOCK: AuthUnlockPayload,
    MessageType.AUTH_RESULT: AuthResultPayload,
    MessageType.LEASE_REQUEST: LeaseRequestPayload,
    MessageType.LEASE_RESULT: LeaseResultPayload,
    MessageType.LOCK_REQUEST: LockRequestPayload,
    MessageType.LOCK_RESULT: LockResultPayload,
    MessageType.SNAPSHOT_REQUEST: SnapshotRequestPayload,
    MessageType.SNAPSHOT: SnapshotPayload,
    MessageType.SEARCH_REQUEST: SearchRequestPayload,
    MessageType.SEARCH_RESULTS: SearchResultsPayload,
    MessageType.EVENT: EventPayload,
    MessageType.PROTOCOL_ERROR: ProtocolErrorPayload,
    MessageType.PING: PingPayload,
    MessageType.PONG: PongPayload,
}


def decode_payload(envelope: WireEnvelope) -> StrictPayload:
    """Decode only the payload model assigned to the envelope message type."""

    return PAYLOAD_MODELS[envelope.message_type].model_validate_json(
        json.dumps(envelope.payload, separators=(",", ":")),
    )


_FIXTURE_SHELL = {
    "state_version": 0,
    "generated_at_utc": "2026-08-03T00:00:00Z",
    "header": {
        "operating_mode": "unknown",
        "operating_mode_freshness": "unavailable",
        "operating_mode_reason": "No reviewed runtime-status adapter is configured.",
        "data_freshness": "unavailable",
        "data_age_seconds": None,
        "regime_label": "Unavailable",
        "regime_confidence": None,
        "portfolio_value": None,
        "next_rebalance_at_utc": None,
        "rebalance_blockers": None,
        "active_agent": None,
        "agent_queue_length": None,
        "qwen_state": "Unavailable",
        "qwen_context_percent": None,
        "current_time_utc": "2026-08-03T00:00:00Z",
        "market_session": "Unavailable",
    },
    "alerts": [],
    "capabilities": [
        {"capability_id": "snapshot.read", "state": "read-only", "reason": None}
    ],
}
_FIXTURE_VIEW = {
    "freshness": "fresh",
    "as_of_utc": "2026-08-03T00:00:00Z",
    "source": "fixture",
    "error": None,
}
_FIXTURE_PORTFOLIO_ROW = {
    "symbol": "AAPL",
    "description": "Apple",
    "asset_type": "stock",
    "quantity": "10",
    "price": "100.25",
    "market_value": "1002.50",
    "current_weight": 0.1,
    "proposed_weight": 0.11,
    "approved_weight": None,
    "change_state": "proposed",
    "confirmed_rank": 1,
    "reconciliation": "pending",
}
_FIXTURE_AGENT_ROW = {
    "work_id": "work:1",
    "agent": "portfolio-research",
    "title": "Review AAPL",
    "stage": "running",
    "priority": 10,
    "urgent": False,
    "elapsed_seconds": 3.0,
    "model": "qwen:64k",
    "affected_areas": ["portfolio"],
}
_FIXTURE_TIMELINE_ROW = {
    "event_id": "event:1",
    "occurred_at_utc": "2026-08-03T00:00:00Z",
    "impact": True,
    "severity": "active",
    "summary": "AAPL review started",
    "agent_id": "portfolio-research",
    "symbol": "AAPL",
    "model_id": None,
    "approval_id": None,
    "order_id": "order:1",
    "evidence_ids": ["evidence:1"],
}
_FIXTURE_FILL_ROW = {
    "fill_id": "fill:1",
    "quantity": "10",
    "price": "100.25",
    "fee": "0",
    "filled_at_utc": "2026-08-03T00:00:00Z",
}
_FIXTURE_ORDER_ROW = {
    "order_id": "order:1",
    "symbol": "AAPL",
    "side": "buy",
    "quantity": "10",
    "status": "filled",
    "submitted_at_utc": "2026-08-03T00:00:00Z",
    "broker_order_id": "paper-order-1",
    "fills": [_FIXTURE_FILL_ROW],
    "expected_price": "100.00",
    "actual_price": "100.25",
    "reconciliation": "matched",
}
_FIXTURE_MODEL_OPINION_ROW = {
    "model_id": "model:active",
    "regime": "risk-on",
    "confidence": 0.8,
    "as_of_utc": "2026-08-03T00:00:00Z",
}
_FIXTURE_CANDIDATE_ROW = {
    "candidate_id": "candidate:1",
    "family": "approved-family",
    "strategy": "ml_model",
    "status": "evaluating",
    "evidence_ids": ["evidence:1"],
    "created_at_utc": "2026-08-03T00:00:00Z",
}
_FIXTURE_RISK_LIMIT_ROW = {
    "limit_id": "limit:concentration",
    "current_value": "0.10",
    "proposed_value": None,
    "status": "within",
}
_FIXTURE_APPROVAL_ROW = {
    "approval_id": "approval:1",
    "state": "pending",
    "reason": "Review required",
    "evidence_ids": ["evidence:1"],
    "requested_at_utc": "2026-08-03T00:00:00Z",
}
_FIXTURE_SOURCE_ROW = {
    "source_id": "source:massive",
    "freshness": "fresh",
    "as_of_utc": "2026-08-03T00:00:00Z",
    "age_seconds": 1.0,
    "coverage": "S&P 500",
    "error": None,
    "consumers": ["ml_model"],
}
_FIXTURE_EVIDENCE_ROW = {
    "evidence_id": "evidence:1",
    "evidence_type": "receipt",
    "source": "fixture",
    "created_at_utc": "2026-08-03T00:00:00Z",
    "sha256": "a" * 64,
}
_FIXTURE_MEMORY_ROW = {
    "memory_id": "memory:1",
    "status": "core",
    "summary": "Use controller truth.",
    "evidence_ids": ["evidence:1"],
    "updated_at_utc": "2026-08-03T00:00:00Z",
}
_FIXTURE_SERVICE_ROW = {
    "service_id": "service:qwen",
    "state": "running",
    "health_reason": None,
    "observed_at_utc": "2026-08-03T00:00:00Z",
}
_FIXTURE_REPOSITORY_ROW = {
    "repository_id": "repository:v20",
    "freshness": "fresh",
    "as_of_utc": "2026-08-03T00:00:00Z",
    "source": "git",
    "error": None,
    "branch": "codex/vesper/ratatui-console",
    "revision": "0123456789abcdef",
    "clean": True,
    "worktrees": ["C:/Users/bgonn/Desktop/v20"],
    "unpushed_commit_count": 0,
}
_FIXTURE_METRIC_ROW = {
    "metric_id": "metric:cpu",
    "value": 12.5,
    "unit": "percent",
    "freshness": "fresh",
    "observed_at_utc": "2026-08-03T00:00:00Z",
    "error": None,
}
_FIXTURE_RETURN_ROWS = [
    {"component": "price", "value": "0.01"},
    {"component": "dividends", "value": "0"},
    {"component": "cash-interest", "value": "0"},
    {"component": "fees", "value": "0"},
    {"component": "sp500-total-return", "value": "0.005"},
]
_FIXTURE_ALERT_ROW = {
    "alert_id": "alert:1",
    "severity": "waiting",
    "summary": "Approval waiting",
    "created_at_utc": "2026-08-03T00:00:00Z",
    "resolved_at_utc": None,
}
_FIXTURE_SNAPSHOT = {
    "shell": _FIXTURE_SHELL,
    "control_version": 0,
    "control_hash": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
    "command_specs": [],
    "window_omissions": [],
    "impact": {
        **_FIXTURE_VIEW,
        "holdings": [_FIXTURE_PORTFOLIO_ROW],
        "events": [_FIXTURE_TIMELINE_ROW],
        "agents": [_FIXTURE_AGENT_ROW],
    },
    "portfolio": {
        **_FIXTURE_VIEW,
        "rows": [_FIXTURE_PORTFOLIO_ROW],
        "returns_today": _FIXTURE_RETURN_ROWS,
        "returns_since_rebalance": _FIXTURE_RETURN_ROWS,
        "returns_since_start": _FIXTURE_RETURN_ROWS,
        "metrics": [_FIXTURE_METRIC_ROW],
        "history": [_FIXTURE_TIMELINE_ROW],
        "rank_source": "confirmed reconciliation",
    },
    "orders": {
        **_FIXTURE_VIEW,
        "rows": [_FIXTURE_ORDER_ROW],
        "reconciliation_agents": [_FIXTURE_AGENT_ROW],
        "history": [_FIXTURE_TIMELINE_ROW],
    },
    "agents": {**_FIXTURE_VIEW, "rows": [_FIXTURE_AGENT_ROW], "history": [_FIXTURE_TIMELINE_ROW]},
    "models": {
        **_FIXTURE_VIEW,
        "opinions": [_FIXTURE_MODEL_OPINION_ROW],
        "candidates": [_FIXTURE_CANDIDATE_ROW],
        "metrics": [_FIXTURE_METRIC_ROW],
        "evidence": [_FIXTURE_EVIDENCE_ROW],
    },
    "timeline": {**_FIXTURE_VIEW, "rows": [_FIXTURE_TIMELINE_ROW], "hidden_event_count": 0},
    "risk": {
        **_FIXTURE_VIEW,
        "limits": [_FIXTURE_RISK_LIMIT_ROW],
        "approvals": [_FIXTURE_APPROVAL_ROW],
        "alerts": [_FIXTURE_ALERT_ROW],
        "metrics": [_FIXTURE_METRIC_ROW],
    },
    "data": {
        **_FIXTURE_VIEW,
        "sources": [_FIXTURE_SOURCE_ROW],
        "evidence": [_FIXTURE_EVIDENCE_ROW],
    },
    "memory": {
        **_FIXTURE_VIEW,
        "rows": [_FIXTURE_MEMORY_ROW],
        "history": [_FIXTURE_TIMELINE_ROW],
    },
    "system": {
        **_FIXTURE_VIEW,
        "services": [_FIXTURE_SERVICE_ROW],
        "metrics": [_FIXTURE_METRIC_ROW],
        "repositories": [_FIXTURE_REPOSITORY_ROW],
    },
}

_FIXTURE_PAYLOADS: tuple[tuple[MessageType, dict[str, JsonValue]], ...] = (
    (MessageType.CLIENT_HELLO, {"client_version": "0.1.0", "supported_schema_versions": [1]}),
    (MessageType.SERVER_HELLO, {"server_version": "0.1.0", "requires_setup": True}),
    (MessageType.AUTH_SETUP, {"password": "fixture-password", "confirmation": "fixture-password"}),
    (MessageType.AUTH_UNLOCK, {"password": "fixture-password"}),
    (MessageType.AUTH_RESULT, {"success": True, "access_state": "viewer", "reason": None}),
    (MessageType.LEASE_REQUEST, {"action": "take-control"}),
    (MessageType.LEASE_RESULT, {"status": "controller", "reason": None}),
    (MessageType.LOCK_REQUEST, {"action": "lock"}),
    (MessageType.LOCK_RESULT, {"locked": True}),
    (MessageType.SNAPSHOT_REQUEST, {}),
    (MessageType.SNAPSHOT, {"snapshot": _FIXTURE_SNAPSHOT}),
    (
        MessageType.SEARCH_REQUEST,
        {
            "request_id": 1,
            "query": "AAPL",
            "filters": {
                "kinds": ["stock", "note"],
                "screens": ["portfolio"],
                "source": None,
            },
            "limit": 100,
        },
    ),
    (
        MessageType.SEARCH_RESULTS,
        {
            "request_id": 1,
            "indexed_state_version": 0,
            "results": [
                {
                    "kind": "note",
                    "record_type": "note",
                    "record_id": "note:1",
                    "label": "AAPL note",
                    "summary": "Review concentration risk.",
                    "occurred_at_utc": "2026-08-03T00:00:00Z",
                    "source": "operator",
                    "screen": "portfolio",
                    "context_only": True,
                }
            ],
            "error": None,
        },
    ),
    (
        MessageType.EVENT,
        {
            "entity_type": "alert-row",
            "entity_id": "alert:1",
            "operation": "upsert",
            "entity": {
                "alert_id": "alert:1",
                "severity": "info",
                "summary": "Ready",
                "created_at_utc": "2026-08-03T00:00:00Z",
                "resolved_at_utc": None,
            },
            "targets": ["shell.alerts"],
            "presentation": {
                "generated_at_utc": _FIXTURE_SHELL["generated_at_utc"],
                "header": _FIXTURE_SHELL["header"],
                "control_version": _FIXTURE_SNAPSHOT["control_version"],
                "control_hash": _FIXTURE_SNAPSHOT["control_hash"],
                "window_omissions": _FIXTURE_SNAPSHOT["window_omissions"],
                "impact": _FIXTURE_VIEW,
                "portfolio": _FIXTURE_VIEW,
                "orders": _FIXTURE_VIEW,
                "agents": _FIXTURE_VIEW,
                "models": _FIXTURE_VIEW,
                "timeline": _FIXTURE_VIEW,
                "risk": _FIXTURE_VIEW,
                "data": _FIXTURE_VIEW,
                "memory": _FIXTURE_VIEW,
                "system": _FIXTURE_VIEW,
                "portfolio_rank_source": _FIXTURE_SNAPSHOT["portfolio"]["rank_source"],
                "timeline_hidden_event_count": _FIXTURE_SNAPSHOT["timeline"][
                    "hidden_event_count"
                ],
            },
        },
    ),
    (MessageType.PROTOCOL_ERROR, {"code": "locked", "safe_message": "Locked."}),
    (MessageType.PING, {"nonce": "nonce:1"}),
    (MessageType.PONG, {"nonce": "nonce:1"}),
)


def _canonical_wire_fixture(message_type: MessageType, payload: dict[str, JsonValue]) -> bytes:
    raw = json.dumps(
        {
            "schema_version": 1,
            "message_id": "server:1",
            "sequence": 1,
            "state_version": 0,
            "timestamp_utc": "2026-08-03T00:00:00Z",
            "message_type": message_type.value,
            "payload": payload,
        },
        separators=(",", ":"),
    )
    envelope = WireEnvelope.model_validate_json(raw)
    decode_payload(envelope)
    return envelope.model_dump_json().encode("utf-8")


CANONICAL_WIRE_FIXTURES = tuple(
    _canonical_wire_fixture(message_type, payload) for message_type, payload in _FIXTURE_PAYLOADS
)

WIRE_CONTRACT_DESCRIPTOR = _canonical_json_bytes(
    {
        "schema_version": 1,
        "envelope_required": [
            "schema_version",
            "message_id",
            "sequence",
            "state_version",
            "timestamp_utc",
            "message_type",
            "payload",
        ],
        "messages": {
            message_type.value: [
                name for name, field in model.model_fields.items() if field.is_required()
            ]
            for message_type, model in PAYLOAD_MODELS.items()
        },
        "shell_required": {
            "snapshot": [
                name for name, field in ShellSnapshot.model_fields.items() if field.is_required()
            ],
            "header": [
                name for name, field in HeaderView.model_fields.items() if field.is_required()
            ],
            "alert": [
                name for name, field in AlertView.model_fields.items() if field.is_required()
            ],
            "capability": [
                name for name, field in CapabilityView.model_fields.items() if field.is_required()
            ],
        },
        "field_catalog_scope": [
            "envelope",
            "payloads",
            "shell",
            "snapshot-observability-metadata",
            "event-presentation-metadata",
            "repository-status",
        ],
        "optional_default": ["capability.reason"],
        "nullable_required": [
            "auth-result.reason",
            "lease-result.reason",
            "search-results.error",
            "search-results.results[].occurred_at_utc",
            "search-results.results[].context_only",
            "event.entity",
            "snapshot.shell.alerts",
            "alert.resolved_at_utc",
            "snapshot.shell.header.operating_mode_reason",
            "snapshot.shell.header.data_age_seconds",
            "snapshot.shell.header.regime_confidence",
            "snapshot.shell.header.portfolio_value",
            "snapshot.shell.header.next_rebalance_at_utc",
            "snapshot.shell.header.rebalance_blockers",
            "snapshot.shell.header.active_agent",
            "snapshot.shell.header.agent_queue_length",
            "snapshot.shell.header.qwen_context_percent",
            "snapshot.window_omissions[].omitted_count",
            "snapshot.impact.as_of_utc",
            "snapshot.impact.error",
            "snapshot.portfolio.as_of_utc",
            "snapshot.portfolio.error",
            "snapshot.portfolio.rank_source",
            "snapshot.orders.as_of_utc",
            "snapshot.orders.error",
            "snapshot.agents.as_of_utc",
            "snapshot.agents.error",
            "snapshot.models.as_of_utc",
            "snapshot.models.error",
            "snapshot.timeline.as_of_utc",
            "snapshot.timeline.error",
            "snapshot.risk.as_of_utc",
            "snapshot.risk.error",
            "snapshot.data.as_of_utc",
            "snapshot.data.error",
            "snapshot.memory.as_of_utc",
            "snapshot.memory.error",
            "snapshot.system.as_of_utc",
            "snapshot.system.error",
            "event.presentation.header.operating_mode_reason",
            "event.presentation.header.data_age_seconds",
            "event.presentation.header.regime_confidence",
            "event.presentation.header.portfolio_value",
            "event.presentation.header.next_rebalance_at_utc",
            "event.presentation.header.rebalance_blockers",
            "event.presentation.header.active_agent",
            "event.presentation.header.agent_queue_length",
            "event.presentation.header.qwen_context_percent",
            "event.presentation.window_omissions[].omitted_count",
            "event.presentation.impact.as_of_utc",
            "event.presentation.impact.error",
            "event.presentation.portfolio.as_of_utc",
            "event.presentation.portfolio.error",
            "event.presentation.orders.as_of_utc",
            "event.presentation.orders.error",
            "event.presentation.agents.as_of_utc",
            "event.presentation.agents.error",
            "event.presentation.models.as_of_utc",
            "event.presentation.models.error",
            "event.presentation.timeline.as_of_utc",
            "event.presentation.timeline.error",
            "event.presentation.risk.as_of_utc",
            "event.presentation.risk.error",
            "event.presentation.data.as_of_utc",
            "event.presentation.data.error",
            "event.presentation.memory.as_of_utc",
            "event.presentation.memory.error",
            "event.presentation.system.as_of_utc",
            "event.presentation.system.error",
            "event.presentation.portfolio_rank_source",
        ],
        "integer_fields": [
            "envelope.sequence",
            "envelope.state_version",
            "snapshot.shell.state_version",
            "snapshot.control_version",
            "snapshot.shell.header.agent_queue_length",
            "snapshot.timeline.hidden_event_count",
            "snapshot.window_omissions[].omitted_count",
            "event.presentation.control_version",
            "event.presentation.header.agent_queue_length",
            "event.presentation.timeline_hidden_event_count",
            "event.presentation.window_omissions[].omitted_count",
            "repository.unpushed_commit_count",
        ],
    }
)


class UntrustedProtocolDiagnostic:
    """A synchronous-only view that clears raw unknown fields after callback return."""

    __slots__ = ("frame_sha256", "_state", "_unknown_fields")

    def __init__(self, frame_sha256: str, unknown_fields: dict[str, JsonValue]) -> None:
        self.frame_sha256 = frame_sha256
        self._state = _UntrustedDiagnosticState(unknown_fields)
        self._unknown_fields = _RevocableJsonMapping(self._state, unknown_fields)

    @property
    def unknown_fields(self) -> Mapping[str, object]:
        """Expose raw fields only while the callback is executing."""

        return self._unknown_fields

    def _invalidate(self) -> None:
        self._state.invalidate()

    def __getstate__(self) -> object:
        raise TypeError("untrusted protocol diagnostics cannot be serialized")

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("untrusted protocol diagnostics cannot be pickled")


DiagnosticCallback: TypeAlias = Callable[[UntrustedProtocolDiagnostic], None]


class _UntrustedDiagnosticState:
    __slots__ = ("active", "containers", "views")

    def __init__(self, values: dict[str, JsonValue]) -> None:
        self.active = True
        self.containers: list[dict[str, JsonValue] | list[JsonValue]] = [values]
        self.views: list[_RevocableJsonScalar] = []

    def register_container(self, values: dict[str, JsonValue] | list[JsonValue]) -> None:
        self.containers.append(values)

    def register(self, view: _RevocableJsonScalar) -> None:
        self.views.append(view)

    def invalidate(self) -> None:
        self.active = False
        for view in self.views:
            view._revoke()
        self.views.clear()
        for values in self.containers:
            _scrub_json_value(values)
        self.containers.clear()


def _scrub_json_value(value: dict[str, JsonValue] | list[JsonValue]) -> None:
    if isinstance(value, dict):
        for child in value.values():
            if isinstance(child, (dict, list)):
                _scrub_json_value(child)
        value.clear()
        return
    for child in value:
        if isinstance(child, (dict, list)):
            _scrub_json_value(child)
    value.clear()


class _RevocableJsonIterator:
    __slots__ = ("_state", "_iterator", "_transform")

    def __init__(self, state: _UntrustedDiagnosticState, iterator: object, transform: Callable[[object], object]) -> None:
        self._state = state
        self._iterator = iterator
        self._transform = transform

    def __iter__(self) -> _RevocableJsonIterator:
        return self

    def __next__(self) -> object:
        if not self._state.active:
            raise StopIteration
        return self._transform(next(self._iterator))

    def __getstate__(self) -> object:
        raise TypeError("untrusted protocol diagnostics cannot be serialized")

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("untrusted protocol diagnostics cannot be pickled")


class _RevocableJsonScalar:
    __slots__ = ("_state", "_value")

    def __init__(self, state: _UntrustedDiagnosticState, value: JsonScalar) -> None:
        self._state = state
        self._value: JsonScalar | object = value
        state.register(self)

    def _revoke(self) -> None:
        self._value = _MISSING

    def _require_value(self) -> JsonScalar:
        if not self._state.active or self._value is _MISSING:
            raise RuntimeError("untrusted diagnostic value has expired")
        return self._value

    def __eq__(self, other: object) -> bool:
        return self._require_value() == other

    def __bool__(self) -> bool:
        return bool(self._require_value())

    def __str__(self) -> str:
        return str(self._require_value())

    def __repr__(self) -> str:
        return "<untrusted diagnostic value>" if self._state.active else "<expired diagnostic value>"

    def __getstate__(self) -> object:
        raise TypeError("untrusted protocol diagnostics cannot be serialized")

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("untrusted protocol diagnostics cannot be pickled")


class _RevocableJsonMapping(Mapping[str, object]):
    __slots__ = ("_state", "_values")

    def __init__(self, state: _UntrustedDiagnosticState, values: dict[str, JsonValue]) -> None:
        self._state = state
        self._values = values

    def __getitem__(self, key: str) -> object:
        if not self._state.active:
            raise KeyError(key)
        return _revocable_json_value(self._state, self._values[key])

    def __iter__(self) -> _RevocableJsonIterator:
        return _RevocableJsonIterator(self._state, iter(self._values), lambda key: key)

    def __len__(self) -> int:
        return len(self._values) if self._state.active else 0

    def __getstate__(self) -> object:
        raise TypeError("untrusted protocol diagnostics cannot be serialized")

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("untrusted protocol diagnostics cannot be pickled")


class _RevocableJsonSequence(Sequence[object]):
    __slots__ = ("_state", "_values")

    def __init__(self, state: _UntrustedDiagnosticState, values: list[JsonValue]) -> None:
        self._state = state
        self._values = values

    def __getitem__(self, index: int | slice) -> object:
        if not self._state.active:
            raise IndexError(index)
        if isinstance(index, slice):
            values = self._values[index]
            self._state.register_container(values)
            return _RevocableJsonSequence(self._state, values)
        return _revocable_json_value(self._state, self._values[index])

    def __iter__(self) -> _RevocableJsonIterator:
        return _RevocableJsonIterator(
            self._state,
            iter(range(len(self._values))),
            lambda index: _revocable_json_value(self._state, self._values[index]),
        )

    def __len__(self) -> int:
        return len(self._values) if self._state.active else 0

    def __getstate__(self) -> object:
        raise TypeError("untrusted protocol diagnostics cannot be serialized")

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("untrusted protocol diagnostics cannot be pickled")


def _revocable_json_value(state: _UntrustedDiagnosticState, value: JsonValue) -> object:
    if isinstance(value, dict):
        return _RevocableJsonMapping(state, value)
    if isinstance(value, list):
        return _RevocableJsonSequence(state, value)
    return _RevocableJsonScalar(state, value)


def _bounded_json_value(value: JsonValue, depth: int = 0) -> JsonValue:
    if depth >= MAX_UNTRUSTED_JSON_DEPTH:
        return "[truncated]"
    if isinstance(value, str):
        return value[:MAX_UNTRUSTED_STRING_LENGTH]
    if isinstance(value, list):
        return [_bounded_json_value(item, depth + 1) for item in value[:MAX_UNTRUSTED_JSON_ITEMS]]
    if isinstance(value, dict):
        return {
            key: _bounded_json_value(item, depth + 1)
            for key, item in list(value.items())[:MAX_UNTRUSTED_JSON_ITEMS]
        }
    return value


def _unknown_fields(values: dict[str, JsonValue], model: PayloadModel | type[WireEnvelope]) -> dict[str, JsonValue]:
    unknown: dict[str, JsonValue] = {}
    for name, value in values.items():
        if name not in model.model_fields:
            unknown[name] = _bounded_json_value(value)
        if len(unknown) == MAX_UNTRUSTED_UNKNOWN_FIELDS:
            break
    return unknown


def _read_json_location(value: JsonValue, location: tuple[object, ...]) -> JsonValue | object:
    current: object = value
    for part in location:
        if isinstance(current, dict) and isinstance(part, str) and part in current:
            current = current[part]
        elif isinstance(current, list) and isinstance(part, int) and 0 <= part < len(current):
            current = current[part]
        else:
            return _MISSING
    return current


def _assign_unknown_location(
    result: dict[str, JsonValue],
    location: tuple[object, ...],
    value: JsonValue,
) -> None:
    current = result
    for part in location[:-1]:
        key = str(part)
        child = current.get(key)
        if not isinstance(child, dict):
            child = {}
            current[key] = child
        current = child
    if location:
        current[str(location[-1])] = _bounded_json_value(value)


def _unknown_fields_from_validation(
    payload: dict[str, JsonValue],
    error: ValidationError,
) -> dict[str, JsonValue]:
    unknown: dict[str, JsonValue] = {}
    count = 0
    for detail in error.errors():
        if detail["type"] != "extra_forbidden" or count == MAX_UNTRUSTED_UNKNOWN_FIELDS:
            continue
        location = tuple(detail["loc"])
        value = _read_json_location(payload, location)
        if value is not _MISSING:
            _assign_unknown_location(unknown, location, value)
            count += 1
    return unknown


def _event_unknown_fields(
    payload: dict[str, JsonValue],
    error: ValidationError,
) -> dict[str, JsonValue]:
    unknown = _unknown_fields(payload, EventPayload)
    validation_unknown = _unknown_fields_from_validation(payload, error)
    validation_unknown.pop("entity", None)
    unknown.update(validation_unknown)
    entity_type = payload.get("entity_type")
    entity = payload.get("entity")
    model = event_model(entity_type) if isinstance(entity_type, str) else None
    if model is None or not isinstance(entity, dict):
        return unknown
    try:
        model.model_validate_json(json.dumps(entity, separators=(",", ":")))
    except ValidationError as error:
        nested = _unknown_fields_from_validation(entity, error)
        if nested:
            unknown["entity"] = nested
    return unknown


def _limit_unknown_json_leaves(
    value: JsonValue,
    budget: int,
) -> tuple[JsonValue | object, int]:
    if budget == 0:
        return _MISSING, 0
    if isinstance(value, dict):
        if not value:
            return {}, 1
        limited: dict[str, JsonValue] = {}
        used = 0
        for key, item in value.items():
            child, child_used = _limit_unknown_json_leaves(item, budget - used)
            if child is not _MISSING:
                limited[key] = cast(JsonValue, child)
                used += child_used
            if used == budget:
                break
        return (limited, used) if limited else (_MISSING, 0)
    if isinstance(value, list):
        if not value:
            return [], 1
        limited_items: list[JsonValue] = []
        used = 0
        for item in value:
            child, child_used = _limit_unknown_json_leaves(item, budget - used)
            if child is not _MISSING:
                limited_items.append(cast(JsonValue, child))
                used += child_used
            if used == budget:
                break
        return (limited_items, used) if limited_items else (_MISSING, 0)
    return value, 1


def _limit_unknown_fields(values: dict[str, JsonValue]) -> dict[str, JsonValue]:
    limited, _ = _limit_unknown_json_leaves(values, MAX_UNTRUSTED_UNKNOWN_FIELDS)
    return limited if isinstance(limited, dict) else {}


def _report_untrusted(
    raw_bytes: bytes,
    unknown_fields: dict[str, JsonValue],
    on_untrusted: DiagnosticCallback | None,
) -> None:
    unknown_fields = _limit_unknown_fields(unknown_fields)
    if not unknown_fields or on_untrusted is None:
        return
    diagnostic = UntrustedProtocolDiagnostic(hashlib.sha256(raw_bytes).hexdigest(), unknown_fields)
    try:
        on_untrusted(diagnostic)
    finally:
        diagnostic._invalidate()
        del diagnostic



def decode_envelope_json(
    raw_frame: bytes | str,
    on_untrusted: DiagnosticCallback | None = None,
) -> WireEnvelope:
    """Strictly decode JSON and synchronously expose only raw unknown fields."""

    raw_bytes = raw_frame.encode("utf-8") if isinstance(raw_frame, str) else raw_frame
    try:
        raw_value = json.loads(raw_bytes)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return WireEnvelope.model_validate_json(raw_bytes)
    if not isinstance(raw_value, dict):
        return WireEnvelope.model_validate(raw_value)

    unknown = _unknown_fields(raw_value, WireEnvelope)
    try:
        envelope = WireEnvelope.model_validate_json(raw_bytes)
    except ValidationError as error:
        envelope_error = error
    else:
        envelope_error = None
    if envelope_error is not None:
        _report_untrusted(raw_bytes, unknown, on_untrusted)
        raise envelope_error
    try:
        decode_payload(envelope)
    except ValidationError as error:
        payload_error = error
        payload = raw_value.get("payload")
        if isinstance(payload, dict):
            payload_unknown = (
                _event_unknown_fields(envelope.payload, error)
                if envelope.message_type is MessageType.EVENT
                else _unknown_fields_from_validation(envelope.payload, error)
            )
        else:
            payload_unknown = {}
    else:
        payload_error = None
        payload_unknown = {}
    if payload_error is not None:
        _report_untrusted(raw_bytes, payload_unknown, on_untrusted)
        raise payload_error
    return envelope
