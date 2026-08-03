"""Strict, versioned wire and read-only shell contracts for the V20 console."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal, TypeAlias
from types import MappingProxyType

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
NonNegativeInt = Annotated[int, Field(ge=0)]


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
    rebalance_blockers: tuple[str, ...]
    active_agent: str | None
    agent_queue_length: int
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
    state_version: int
    generated_at_utc: datetime
    header: HeaderView
    alerts: tuple[AlertView, ...]
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
    sequence: NonNegativeInt
    state_version: NonNegativeInt
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


class UntrustedProtocolDiagnostic:
    """A synchronous-only view that clears raw unknown fields after callback return."""

    __slots__ = ("frame_sha256", "_unknown_fields")

    def __init__(self, frame_sha256: str, unknown_fields: dict[str, JsonValue]) -> None:
        self.frame_sha256 = frame_sha256
        self._unknown_fields = _freeze_json_value(unknown_fields)

    @property
    def unknown_fields(self) -> object:
        """Expose raw fields only while the callback is executing."""

        return self._unknown_fields

    def _invalidate(self) -> None:
        self._unknown_fields = MappingProxyType({})

    def __getstate__(self) -> object:
        raise TypeError("untrusted protocol diagnostics cannot be serialized")

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("untrusted protocol diagnostics cannot be pickled")


DiagnosticCallback: TypeAlias = Callable[[UntrustedProtocolDiagnostic], None]


def _freeze_json_value(value: JsonValue) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json_value(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json_value(item) for item in value)
    return value


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
    except ValidationError:
        _report_untrusted(raw_bytes, unknown, on_untrusted)
        raise
    try:
        decode_payload(envelope)
    except ValidationError as error:
        payload = raw_value.get("payload")
        if isinstance(payload, dict):
            _report_untrusted(
                raw_bytes,
                _unknown_fields_from_validation(envelope.payload, error),
                on_untrusted,
            )
        raise
    return envelope
