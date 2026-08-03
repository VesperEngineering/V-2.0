"""Locked, control-only session coordinator for the local V20 console."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from .auth import ControlLease, LeaseStatus, PasswordStore
from .contracts import (
    AuthResultPayload,
    AuthSetupPayload,
    AuthUnlockPayload,
    CapabilityState,
    CapabilityView,
    ClientHelloPayload,
    Freshness,
    HeaderView,
    LeaseResultPayload,
    LockResultPayload,
    MessageType,
    OperatingMode,
    PingPayload,
    PongPayload,
    ProtocolErrorPayload,
    SafeId,
    ServerHelloPayload,
    ShellSnapshot,
    SnapshotPayload,
    WireEnvelope,
    decode_payload,
)

_SERVER_VERSION = "0.1.0"
_MODE_REASON = "No reviewed runtime-status adapter is configured."
_PHASE_ONE_REASON = "Phase 1 provides the secure console shell only."
_ACTION_CAPABILITIES = (
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
_SAFE_ID_ADAPTER = TypeAdapter(SafeId)


class GatewaySession:
    """Authentication and lease state owned by one pipe session."""

    def __init__(self, client_id: SafeId, lease: ControlLease) -> None:
        self.client_id = client_id
        self._lease = lease
        self._authenticated = False
        self._greeted = False
        self._input_sequence = 0
        self._output_sequence = 0
        self._lock = threading.RLock()

    @property
    def access_state(self) -> str:
        if not self._authenticated:
            return "locked"
        if self._lease.controller_id == self.client_id:
            return "controller"
        return "viewer"

    def take_control(self) -> LeaseResultPayload:
        if not self._authenticated:
            return LeaseResultPayload(status="viewer", reason="Console session is locked.")
        status = self._lease.acquire(self.client_id)
        if status is LeaseStatus.VIEWER:
            return LeaseResultPayload(
                status="lease-held",
                reason="Another authenticated session has control.",
            )
        return LeaseResultPayload(status=status.value, reason=None)

    def lock(self) -> None:
        self._lease.release(self.client_id)
        self._authenticated = False


class Gateway:
    """Validate and coordinate phase-1 console messages without V20 access."""

    def __init__(
        self,
        state_root: Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._verifier_path = Path(state_root) / "password-verifier.json"
        self._password_store = PasswordStore(self._verifier_path)
        self._lease = ControlLease()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._sessions: dict[str, GatewaySession] = {}
        self._sessions_lock = threading.Lock()

    @property
    def controller_id(self) -> str | None:
        return self._lease.controller_id

    def session(self, client_id: SafeId) -> GatewaySession:
        client_id = _SAFE_ID_ADAPTER.validate_python(client_id, strict=True)
        with self._sessions_lock:
            session = self._sessions.get(client_id)
            if session is None:
                session = GatewaySession(client_id, self._lease)
                self._sessions[client_id] = session
            return session

    def disconnect(self, client_id: SafeId) -> None:
        with self._sessions_lock:
            session = self._sessions.pop(client_id, None)
        if session is not None:
            with session._lock:
                session.lock()

    def handle(
        self,
        client_id: SafeId,
        envelope: WireEnvelope,
    ) -> tuple[WireEnvelope, ...]:
        session = self.session(client_id)
        with session._lock:
            expected = session._input_sequence + 1
            if envelope.sequence != expected:
                return (self._error(session, "sequence", "Message sequence is invalid."),)
            session._input_sequence = envelope.sequence

            if envelope.message_type is MessageType.PING:
                payload = self._payload(envelope, PingPayload, session)
                if isinstance(payload, WireEnvelope):
                    return (payload,)
                return (self._emit(session, MessageType.PONG, PongPayload(nonce=payload.nonce)),)

            if envelope.message_type is MessageType.CLIENT_HELLO:
                if session._greeted:
                    return (self._error(session, "state", "Client hello was already received."),)
                payload = self._payload(envelope, ClientHelloPayload, session)
                if isinstance(payload, WireEnvelope):
                    return (payload,)
                session._greeted = True
                return (
                    self._emit(
                        session,
                        MessageType.SERVER_HELLO,
                        ServerHelloPayload(
                            server_version=_SERVER_VERSION,
                            requires_setup=not os.path.lexists(self._verifier_path),
                        ),
                    ),
                )

            if envelope.message_type in {MessageType.AUTH_SETUP, MessageType.AUTH_UNLOCK}:
                return (self._authenticate(session, envelope),)

            if not session._authenticated:
                return (self._error(session, "locked", "Console session is locked."),)

            if envelope.message_type is MessageType.SNAPSHOT_REQUEST:
                payload = self._payload(envelope, object, session)
                if isinstance(payload, WireEnvelope):
                    return (payload,)
                return (
                    self._emit(
                        session,
                        MessageType.SNAPSHOT,
                        SnapshotPayload(snapshot=self.snapshot()),
                    ),
                )
            if envelope.message_type is MessageType.LEASE_REQUEST:
                try:
                    decode_payload(envelope)
                except ValidationError:
                    return (self._error(session, "invalid-payload", "Message payload is invalid."),)
                return (
                    self._emit(
                        session,
                        MessageType.LEASE_RESULT,
                        session.take_control(),
                    ),
                )
            if envelope.message_type is MessageType.LOCK_REQUEST:
                try:
                    decode_payload(envelope)
                except ValidationError:
                    return (self._error(session, "invalid-payload", "Message payload is invalid."),)
                session.lock()
                return (
                    self._emit(
                        session,
                        MessageType.LOCK_RESULT,
                        LockResultPayload(locked=True),
                    ),
                )
            return (self._error(session, "direction", "Message type is not accepted from clients."),)

    def snapshot(self) -> ShellSnapshot:
        now = self._clock().astimezone(timezone.utc)
        capabilities = tuple(
            CapabilityView(
                capability_id=capability_id,
                state=CapabilityState.DISABLED,
                reason=_PHASE_ONE_REASON,
            )
            for capability_id in _ACTION_CAPABILITIES
        )
        return ShellSnapshot(
            state_version=0,
            generated_at_utc=now,
            header=HeaderView(
                operating_mode=OperatingMode.UNKNOWN,
                operating_mode_freshness=Freshness.UNAVAILABLE,
                operating_mode_reason=_MODE_REASON,
                data_freshness=Freshness.UNAVAILABLE,
                data_age_seconds=None,
                regime_label="Unavailable",
                regime_confidence=None,
                portfolio_value=None,
                next_rebalance_at_utc=None,
                rebalance_blockers=(),
                active_agent=None,
                agent_queue_length=0,
                qwen_state="Unavailable",
                qwen_context_percent=None,
                current_time_utc=now,
                market_session="Unavailable",
            ),
            alerts=(),
            capabilities=capabilities,
        )

    def _authenticate(self, session: GatewaySession, envelope: WireEnvelope) -> WireEnvelope:
        if not session._greeted:
            return self._error(session, "state", "Client hello is required first.")
        if session._authenticated:
            return self._error(session, "state", "Console session is already unlocked.")
        success = False
        reason: str | None = None
        try:
            payload = decode_payload(envelope)
            if envelope.message_type is MessageType.AUTH_SETUP:
                if not isinstance(payload, AuthSetupPayload) or os.path.lexists(self._verifier_path):
                    reason = "Password setup is unavailable."
                else:
                    self._password_store.setup(payload.password, payload.confirmation)
                    success = True
            elif not isinstance(payload, AuthUnlockPayload):
                reason = "Unlock request is invalid."
            elif not os.path.lexists(self._verifier_path):
                reason = "Password setup is required."
            else:
                success = self._password_store.verify(payload.password)
                if not success:
                    reason = "Unlock failed."
        except (OSError, ValueError, ValidationError):
            reason = "Authentication failed."
        session._authenticated = success
        if not success:
            self._lease.release(session.client_id)
        return self._emit(
            session,
            MessageType.AUTH_RESULT,
            AuthResultPayload(
                success=success,
                access_state="viewer" if success else "locked",
                reason=reason,
            ),
        )

    @staticmethod
    def _payload(
        envelope: WireEnvelope,
        expected_type: type[object],
        session: GatewaySession,
    ) -> object | WireEnvelope:
        try:
            payload = decode_payload(envelope)
        except ValidationError:
            return Gateway._error(session, "invalid-payload", "Message payload is invalid.")
        if expected_type is not object and not isinstance(payload, expected_type):
            return Gateway._error(session, "invalid-payload", "Message payload is invalid.")
        return payload

    @staticmethod
    def _error(session: GatewaySession, code: str, message: str) -> WireEnvelope:
        return Gateway._emit(
            session,
            MessageType.PROTOCOL_ERROR,
            ProtocolErrorPayload(code=code, safe_message=message),
        )

    @staticmethod
    def _emit(session: GatewaySession, message_type: MessageType, payload: object) -> WireEnvelope:
        session._output_sequence += 1
        sequence = session._output_sequence
        assert hasattr(payload, "model_dump")
        return WireEnvelope(
            schema_version=1,
            message_id=f"server:{sequence}",
            sequence=sequence,
            state_version=0,
            timestamp_utc=datetime.now(timezone.utc),
            message_type=message_type,
            payload=payload.model_dump(mode="json"),
        )
