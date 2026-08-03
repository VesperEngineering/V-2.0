"""Strict, versioned wire and read-only shell contracts for the V20 console."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_serializer,
    field_validator,
)
from typing_extensions import TypeAliasType

JsonScalar: TypeAlias = None | bool | int | float | str
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


class UntrustedProtocolDiagnostic(StrictModel):
    """Ephemeral raw unknown fields, reserved for a synchronous diagnostic hook."""

    frame_sha256: Sha256Hex
    unknown_fields: dict[str, JsonValue]


DiagnosticCallback: TypeAlias = Callable[[UntrustedProtocolDiagnostic], None]


def _unknown_fields(values: dict[str, JsonValue], model: PayloadModel | type[WireEnvelope]) -> dict[str, JsonValue]:
    return {name: value for name, value in values.items() if name not in model.model_fields}


def _report_untrusted(
    raw_bytes: bytes,
    unknown_fields: dict[str, JsonValue],
    on_untrusted: DiagnosticCallback | None,
) -> None:
    if not unknown_fields or on_untrusted is None:
        return
    diagnostic = UntrustedProtocolDiagnostic(
        frame_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        unknown_fields=unknown_fields,
    )
    try:
        on_untrusted(diagnostic)
    finally:
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
    except ValidationError:
        payload = raw_value.get("payload")
        if isinstance(payload, dict):
            _report_untrusted(
                raw_bytes,
                _unknown_fields(payload, PAYLOAD_MODELS[envelope.message_type]),
                on_untrusted,
            )
        raise
    return envelope
