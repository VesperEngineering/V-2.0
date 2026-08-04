"""Locked, control-only session coordinator for the local V20 console."""

from __future__ import annotations

import hashlib
import json
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
    SearchRequestPayload,
    SearchResultsPayload,
    ServerHelloPayload,
    ShellSnapshot,
    SnapshotPayload,
    WireEnvelope,
    decode_payload,
)
from .outbox import OutboundQueue
from .search import GlobalSearchService
from .snapshot import diff_snapshots
from .views import (
    AgentsView,
    ConsoleSnapshot,
    DataView,
    EventPayload,
    ImpactView,
    MemoryView,
    ModelsView,
    OrdersView,
    PortfolioView,
    RiskView,
    ScreenView,
    SystemView,
    TimelineView,
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
        self._subscribed = False
        self._outbox = OutboundQueue()
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
        self._subscribed = False


class Gateway:
    """Validate and coordinate phase-1 console messages without V20 access."""

    def __init__(
        self,
        state_root: Path,
        *,
        clock: Callable[[], datetime] | None = None,
        search_service: GlobalSearchService | None = None,
    ) -> None:
        self._verifier_path = Path(state_root) / "password-verifier.json"
        self._password_store = PasswordStore(self._verifier_path)
        self._lease = ControlLease()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._sessions: dict[str, GatewaySession] = {}
        self._sessions_lock = threading.Lock()
        self._publication_lock = threading.RLock()
        self._snapshot = self._unavailable_snapshot()
        self._has_projection_snapshot = False
        self._search_service = search_service
        if search_service is not None:
            search_service.update_snapshot(self._snapshot)

    @property
    def controller_id(self) -> str | None:
        return self._lease.controller_id

    @property
    def search_service(self) -> GlobalSearchService | None:
        return self._search_service

    def attach_search_service(self, service: GlobalSearchService) -> None:
        """Attach the one controller-owned read-only search service."""

        if type(service) is not GlobalSearchService:
            raise TypeError("service must be GlobalSearchService")
        with self._publication_lock:
            if self._search_service is not None and self._search_service is not service:
                raise RuntimeError("search service is already attached")
            service.update_snapshot(self._snapshot)
            self._search_service = service

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
                session._outbox.close()

    def poll(self, client_id: SafeId) -> WireEnvelope | None:
        """Return the next admitted frame without running any V20 service."""

        client_id = _SAFE_ID_ADAPTER.validate_python(client_id, strict=True)
        with self._sessions_lock:
            session = self._sessions.get(client_id)
        if session is None:
            raise ConnectionAbortedError("connection-closed")
        return session._outbox.pop()

    def publish_snapshot(self, snapshot: ConsoleSnapshot) -> None:
        """Atomically publish a complete projection to subscribed sessions."""

        if not isinstance(snapshot, ConsoleSnapshot):
            raise TypeError("snapshot must be a ConsoleSnapshot")
        with self._publication_lock:
            previous = self._snapshot
            if self._has_projection_snapshot:
                if snapshot == previous:
                    return
                if snapshot.shell.state_version <= previous.shell.state_version:
                    raise ValueError("snapshot state version must advance")
            events: tuple[EventPayload, ...] = ()
            if self._has_projection_snapshot and self._can_publish_incrementally(
                previous,
                snapshot,
            ):
                try:
                    events = diff_snapshots(previous, snapshot)
                except (TypeError, ValueError):
                    events = ()
            self._snapshot = snapshot
            if self._search_service is not None:
                self._search_service.update_snapshot(snapshot)
            first_projection = not self._has_projection_snapshot
            self._has_projection_snapshot = True
            if first_projection or not events:
                self._publish_to_subscribers(
                    MessageType.SNAPSHOT,
                    SnapshotPayload(snapshot=snapshot),
                    state_version=snapshot.shell.state_version,
                    replace_key=("snapshot",),
                )
                return
            for event in events:
                self._publish_event_to_subscribers(
                    event,
                    state_version=snapshot.shell.state_version,
                )

    @staticmethod
    def _can_publish_incrementally(
        previous: ConsoleSnapshot,
        current: ConsoleSnapshot,
    ) -> bool:
        return (
            previous.command_specs == current.command_specs
            and previous.shell.capabilities == current.shell.capabilities
            and (previous.shell.alerts is None) == (current.shell.alerts is None)
        )

    def publish_event(self, event: EventPayload) -> None:
        """Publish one validated event without calling a runtime or broker."""

        if not isinstance(event, EventPayload):
            raise TypeError("event must be an EventPayload")
        with self._publication_lock:
            self._publish_event_to_subscribers(
                event,
                state_version=self._snapshot.shell.state_version,
            )

    def _publish_event_to_subscribers(
        self,
        event: EventPayload,
        *,
        state_version: int,
    ) -> None:
        replace_key = (
            ("metric", event.entity_id, *event.targets)
            if event.entity_type == "metric-row"
            else None
        )
        self._publish_to_subscribers(
            MessageType.EVENT,
            event,
            state_version=state_version,
            replace_key=replace_key,
        )

    def _publish_to_subscribers(
        self,
        message_type: MessageType,
        payload: object,
        *,
        state_version: int,
        replace_key: tuple[str, ...] | None,
    ) -> None:
        with self._sessions_lock:
            sessions = tuple(self._sessions.values())
        for session in sessions:
            with session._lock:
                if not session._authenticated or not session._subscribed:
                    continue
                try:
                    admitted = self._emit(
                        session,
                        message_type,
                        payload,
                        state_version=state_version,
                        replace_key=replace_key,
                    )
                except ConnectionAbortedError:
                    session._subscribed = False
                    continue
                if admitted.message_type is MessageType.PROTOCOL_ERROR:
                    session._subscribed = False

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
                snapshot = self.snapshot()
                response = self._emit(
                    session,
                    MessageType.SNAPSHOT,
                    SnapshotPayload(snapshot=snapshot),
                    state_version=snapshot.shell.state_version,
                )
                if response.message_type is MessageType.SNAPSHOT:
                    session._subscribed = True
                return (response,)
            if envelope.message_type is MessageType.SEARCH_REQUEST:
                payload = self._payload(envelope, SearchRequestPayload, session)
                if isinstance(payload, WireEnvelope):
                    return (payload,)
                assert isinstance(payload, SearchRequestPayload)
                service = self._search_service
                if service is None:
                    result = SearchResultsPayload(
                        request_id=payload.request_id,
                        indexed_state_version=self._snapshot.shell.state_version,
                        results=(),
                        error="Search is unavailable.",
                    )
                else:
                    try:
                        page = service.search(payload.query, payload.filters, payload.limit)
                    except (OSError, RuntimeError, ValueError):
                        result = SearchResultsPayload(
                            request_id=payload.request_id,
                            indexed_state_version=service.indexed_state_version,
                            results=(),
                            error="Search is unavailable.",
                        )
                    else:
                        result = SearchResultsPayload(
                            request_id=payload.request_id,
                            indexed_state_version=page.indexed_state_version,
                            results=page.results,
                            error=page.error,
                        )
                return (
                    self._emit(
                        session,
                        MessageType.SEARCH_RESULTS,
                        result,
                        state_version=result.indexed_state_version,
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
            return (
                self._error(session, "direction", "Message type is not accepted from clients."),
            )

    def snapshot(self) -> ConsoleSnapshot:
        return self._snapshot

    def _unavailable_snapshot(self) -> ConsoleSnapshot:
        now = self._clock().astimezone(timezone.utc)
        capabilities = tuple(
            CapabilityView(
                capability_id=capability_id,
                state=CapabilityState.DISABLED,
                reason=_PHASE_ONE_REASON,
            )
            for capability_id in _ACTION_CAPABILITIES
        )
        shell = ShellSnapshot(
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
                rebalance_blockers=None,
                active_agent=None,
                agent_queue_length=None,
                qwen_state="Unavailable",
                qwen_context_percent=None,
                current_time_utc=now,
                market_session="Unavailable",
            ),
            alerts=None,
            capabilities=capabilities,
        )
        impact = ImpactView(
            **self._unavailable_view("impact"),
            holdings=(),
            events=(),
            agents=(),
        )
        portfolio = PortfolioView(
            **self._unavailable_view("portfolio"),
            rows=(),
            returns_today=(),
            returns_since_rebalance=(),
            returns_since_start=(),
            metrics=(),
            history=(),
            rank_source=None,
        )
        orders = OrdersView(
            **self._unavailable_view("orders"),
            rows=(),
            reconciliation_agents=(),
            history=(),
        )
        agents = AgentsView(**self._unavailable_view("agents"), rows=(), history=())
        models = ModelsView(
            **self._unavailable_view("models"),
            opinions=(),
            candidates=(),
            metrics=(),
            evidence=(),
        )
        timeline = TimelineView(
            **self._unavailable_view("timeline"),
            rows=(),
            hidden_event_count=0,
        )
        risk = RiskView(
            **self._unavailable_view("risk"),
            limits=(),
            approvals=(),
            alerts=(),
            metrics=(),
        )
        data = DataView(**self._unavailable_view("data"), sources=(), evidence=())
        memory = MemoryView(**self._unavailable_view("memory"), rows=(), history=())
        system = SystemView(
            **self._unavailable_view("system"),
            services=(),
            metrics=(),
            repositories=(),
        )
        command_views: dict[str, ScreenView] = {
            "portfolio": portfolio,
            "orders": orders,
            "models": models,
            "risk": risk,
            "data": data,
            "system": system,
        }
        control_facts = {
            "capabilities": [item.model_dump(mode="json") for item in capabilities],
            "command_prerequisites": {
                name: {
                    "freshness": view.freshness.value,
                    "source": view.source,
                    "error": view.error,
                }
                for name, view in command_views.items()
            },
        }
        control_hash = hashlib.sha256(
            json.dumps(control_facts, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return ConsoleSnapshot(
            shell=shell,
            control_version=0,
            control_hash=control_hash,
            command_specs=(),
            window_omissions=(),
            impact=impact,
            portfolio=portfolio,
            orders=orders,
            agents=agents,
            models=models,
            timeline=timeline,
            risk=risk,
            data=data,
            memory=memory,
            system=system,
        )

    @staticmethod
    def _unavailable_view(name: str) -> dict[str, object]:
        return {
            "freshness": Freshness.UNAVAILABLE,
            "as_of_utc": None,
            "source": f"controller {name} projection",
            "error": f"No controller-owned {name} projection is configured.",
        }

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
                if not isinstance(payload, AuthSetupPayload) or os.path.lexists(
                    self._verifier_path
                ):
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
    def _emit(
        session: GatewaySession,
        message_type: MessageType,
        payload: object,
        *,
        state_version: int = 0,
        replace_key: tuple[str, ...] | None = None,
    ) -> WireEnvelope:
        assert hasattr(payload, "model_dump")
        return session._outbox.admit(
            message_type,
            payload,
            state_version,
            datetime.now(timezone.utc),
            replace_key=replace_key,
        )
