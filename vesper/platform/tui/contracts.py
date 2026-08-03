"""Strict, versioned wire and read-only shell contracts for the V20 console."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    AfterValidator,
    field_serializer,
    field_validator,
)
from typing_extensions import TypeAliasType

MAX_UNTRUSTED_UNKNOWN_FIELDS = 16
MAX_UNTRUSTED_JSON_DEPTH = 8
MAX_UNTRUSTED_JSON_ITEMS = 32
MAX_UNTRUSTED_STRING_LENGTH = 4096
_MISSING = object()


def _require_finite_float(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("floating-point values must be finite")
    return value


FiniteFloat = Annotated[float, AfterValidator(_require_finite_float)]
JsonScalar: TypeAlias = None | bool | int | FiniteFloat | str
JsonValue = TypeAliasType(
    "JsonValue",
    JsonScalar | list["JsonValue"] | dict[str, "JsonValue"],
)
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
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
WireUInt = Annotated[int, Field(ge=0, le=2**64 - 1)]


class StrictModel(BaseModel):
    """Reject coercion and undeclared input at every wire boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


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
    PROTOCOL_ERROR = "protocol-error"
    PING = "ping"
    PONG = "pong"


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


def _require_utc(value: datetime) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError("timestamps must be timezone-aware UTC")
    return value


def _serialize_utc(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


class CapabilityView(StrictModel):
    capability_id: NonEmptyStr
    state: CapabilityState
    reason: NonEmptyStr | None = None


class AlertView(StrictModel):
    alert_id: NonEmptyStr
    severity: Literal["info", "active", "waiting", "urgent", "resolved"]
    summary: NonEmptyStr
    created_at_utc: datetime
    resolved_at_utc: datetime | None

    @field_validator("created_at_utc", "resolved_at_utc")
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _require_utc(value)

    @field_serializer("created_at_utc", "resolved_at_utc", when_used="unless-none")
    def serialize_utc(self, value: datetime) -> str:
        return _serialize_utc(value)


class HeaderView(StrictModel):
    operating_mode: OperatingMode
    operating_mode_freshness: Freshness
    operating_mode_reason: NonEmptyStr | None
    data_freshness: Freshness
    data_age_seconds: float | None
    regime_label: str
    regime_confidence: float | None
    portfolio_value: float | None
    next_rebalance_at_utc: datetime | None
    rebalance_blockers: tuple[str, ...] | None
    active_agent: str | None
    agent_queue_length: WireUInt | None
    qwen_state: str
    qwen_context_percent: float | None
    current_time_utc: datetime
    market_session: str

    @field_validator(
        "data_age_seconds",
        "regime_confidence",
        "portfolio_value",
        "qwen_context_percent",
    )
    @classmethod
    def require_finite_float(cls, value: float | None) -> float | None:
        return None if value is None else _require_finite_float(value)

    @field_validator("next_rebalance_at_utc", "current_time_utc")
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _require_utc(value)

    @field_serializer("next_rebalance_at_utc", "current_time_utc", when_used="unless-none")
    def serialize_utc(self, value: datetime) -> str:
        return _serialize_utc(value)


class ShellSnapshot(StrictModel):
    state_version: WireUInt
    generated_at_utc: datetime
    header: HeaderView
    alerts: tuple[AlertView, ...] | None
    capabilities: tuple[CapabilityView, ...]

    @field_validator("generated_at_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @field_serializer("generated_at_utc")
    def serialize_utc(self, value: datetime) -> str:
        return _serialize_utc(value)


class WireEnvelope(StrictModel):
    schema_version: Literal[1]
    message_id: SafeId
    sequence: WireUInt
    state_version: WireUInt
    timestamp_utc: datetime
    message_type: MessageType
    payload: dict[str, JsonValue]

    @field_validator("message_id")
    @classmethod
    def reject_dot_ids(cls, value: str) -> str:
        if value in {".", ".."}:
            raise ValueError("wire IDs cannot be dot paths")
        return value

    @field_validator("timestamp_utc")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _require_utc(value)

    @field_serializer("timestamp_utc")
    def serialize_utc(self, value: datetime) -> str:
        return _serialize_utc(value)


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
    snapshot: ShellSnapshot


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
    MessageType.PROTOCOL_ERROR: ProtocolErrorPayload,
    MessageType.PING: PingPayload,
    MessageType.PONG: PongPayload,
}


def decode_payload(envelope: WireEnvelope) -> StrictPayload:
    """Decode only the payload model assigned to the envelope message type."""

    return PAYLOAD_MODELS[envelope.message_type].model_validate_json(
        json.dumps(envelope.payload, separators=(",", ":")),
    )


_FIXTURE_SNAPSHOT = {
    "state_version": 0,
    "generated_at_utc": "2026-08-03T00:00:00Z",
    "header": {
        "operating_mode": "unknown",
        "operating_mode_freshness": "unavailable",
        "operating_mode_reason": None,
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
    "alerts": [
        {
            "alert_id": "alert:1",
            "severity": "info",
            "summary": "Ready",
            "created_at_utc": "2026-08-03T00:00:00Z",
            "resolved_at_utc": None,
        }
    ],
    "capabilities": [
        {
            "capability_id": "snapshot.read",
            "state": "read-only",
            "reason": None,
        }
    ],
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
        "optional_default": ["capability.reason"],
        "nullable_required": [
            "auth-result.reason",
            "lease-result.reason",
            "snapshot.alerts",
            "alert.resolved_at_utc",
            "header.operating_mode_reason",
            "header.data_age_seconds",
            "header.regime_confidence",
            "header.portfolio_value",
            "header.next_rebalance_at_utc",
            "header.rebalance_blockers",
            "header.active_agent",
            "header.agent_queue_length",
            "header.qwen_context_percent",
        ],
        "integer_fields": [
            "envelope.sequence",
            "envelope.state_version",
            "snapshot.state_version",
            "header.agent_queue_length",
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


def _report_untrusted(
    raw_bytes: bytes,
    unknown_fields: dict[str, JsonValue],
    on_untrusted: DiagnosticCallback | None,
) -> None:
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
            payload_unknown = _unknown_fields_from_validation(envelope.payload, error)
        else:
            payload_unknown = {}
    else:
        payload_error = None
        payload_unknown = {}
    if payload_error is not None:
        _report_untrusted(raw_bytes, payload_unknown, on_untrusted)
        raise payload_error
    return envelope
