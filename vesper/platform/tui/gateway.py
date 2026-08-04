"""Locked, control-only session coordinator for the local V20 console."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from pydantic import TypeAdapter, ValidationError

from vesper.platform.agent_profiles import AUTONOMOUS_AGENT_ROLES
from vesper.platform.contracts import AgentRole

from .auth import ControlLease, LeaseStatus, PasswordStore
from .command_contracts import (
    COMMAND_SPECS,
    AgentEnqueuePayload,
    ApprovalPayload,
    CommandMessagePayload,
    CommandReceiptPayload,
    CommandRequest,
    NoteAddPayload,
)
from .command_policy import (
    CommandContext,
    EvaluatedPrerequisites,
    PrerequisiteCheck,
    canonical_request_hash,
)
from .command_ports import DISABLED_COMMAND_REASONS
from .command_registry import CommandRegistry
from .contracts import (
    AuthResultPayload,
    AuthSetupPayload,
    AuthUnlockPayload,
    CapabilityState,
    CapabilityView,
    ChatEventPayload,
    ChatHistoryRequestPayload,
    ChatHistoryResultPayload,
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
from .conversations import ConversationStore
from .outbox import OutboundQueue
from .pipe_security import current_logon_sid
from .search import GlobalSearchService
from .live_readiness import unavailable_live_readiness
from .snapshot import diff_snapshots, requires_full_snapshot
from .snapshot_cache import CachedSnapshot, SnapshotCache, SnapshotCacheError
from .ports import PlatformRuntimeFacts, SourceSample
from .projections.platform_runtime import platform_runtime_control_binding
from .recovery import RecoveryReport, RecoveryService
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
_RUNTIME_GOVERNED_COMMANDS = frozenset(
    {
        "approval.approve",
        "approval.hold",
        "approval.reject",
        "agent.enqueue",
    }
)
_RUNTIME_UNAVAILABLE_REASON = "Platform runtime state is unavailable."
_MAX_WIRE_UINT = 2**64 - 1
_PLATFORM_RUNTIME_SAMPLE_ADAPTER = TypeAdapter(SourceSample[PlatformRuntimeFacts])


class _PlatformRuntimeReadPort(Protocol):
    def read(self) -> SourceSample[PlatformRuntimeFacts]: ...


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
        command_registry: CommandRegistry | None = None,
        platform_runtime_reader: _PlatformRuntimeReadPort | None = None,
        recovery_service: RecoveryService | None = None,
        snapshot_cache: SnapshotCache | None = None,
        conversation_store: ConversationStore | None = None,
        logon_sid_provider: Callable[[], str] = current_logon_sid,
    ) -> None:
        if not callable(logon_sid_provider):
            raise TypeError("logon_sid_provider must be callable")
        if recovery_service is not None and type(recovery_service) is not RecoveryService:
            raise TypeError("recovery_service must be a RecoveryService")
        if snapshot_cache is not None and type(snapshot_cache) is not SnapshotCache:
            raise TypeError("snapshot_cache must be a SnapshotCache")
        if conversation_store is not None and type(conversation_store) is not ConversationStore:
            raise TypeError("conversation_store must be a ConversationStore")
        self._verifier_path = Path(state_root) / "password-verifier.json"
        self._password_store = PasswordStore(self._verifier_path)
        self._lease = ControlLease()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._sessions: dict[str, GatewaySession] = {}
        self._sessions_lock = threading.Lock()
        self._publication_lock = threading.RLock()
        self._control_lock = threading.RLock()
        self._snapshot = self._unavailable_snapshot()
        self._upstream_snapshot = self._snapshot
        self._has_projection_snapshot = False
        self._search_service = search_service
        self._command_registry: CommandRegistry | None = None
        self._platform_runtime_reader: _PlatformRuntimeReadPort | None = None
        self._platform_runtime_sample = self._unavailable_platform_runtime_sample()
        self._recovery_service = recovery_service
        self._snapshot_cache = snapshot_cache
        self._conversation_store = conversation_store
        self._cached_snapshot: CachedSnapshot | None = None
        self._snapshot_cache_unavailable = False
        self._logon_sid_provider = logon_sid_provider
        self._operator_id_value: str | None = None
        if search_service is not None:
            search_service.update_snapshot(self._snapshot)
        if platform_runtime_reader is not None:
            self.attach_platform_runtime_reader(platform_runtime_reader)
        if command_registry is not None:
            self.attach_command_registry(command_registry)

    @property
    def controller_id(self) -> str | None:
        return self._lease.controller_id

    @property
    def search_service(self) -> GlobalSearchService | None:
        return self._search_service

    def recovery_report(self) -> RecoveryReport | None:
        """Expose read-only recovery facts; this method cannot resume V20."""

        with self._control_lock:
            service = self._recovery_service
        return None if service is None else service.inspect()

    def cached_snapshot(self, client_id: SafeId) -> CachedSnapshot | None:
        """Return cached data only to an authenticated local session."""

        client_id = _SAFE_ID_ADAPTER.validate_python(client_id, strict=True)
        with self._sessions_lock:
            session = self._sessions.get(client_id)
        if session is None:
            return None
        with session._lock:
            if not session._authenticated:
                return None
        with self._control_lock:
            return self._cached_snapshot

    @property
    def snapshot_cache_unavailable(self) -> bool:
        with self._control_lock:
            return self._snapshot_cache_unavailable

    @property
    def operator_id(self) -> str:
        """Return one stable, non-reversible identifier for this Windows logon."""

        with self._control_lock:
            if self._operator_id_value is None:
                sid = self._logon_sid_provider()
                if type(sid) is not str or not sid:
                    raise ValueError("current logon SID is unavailable")
                self._operator_id_value = (
                    f"windows:{hashlib.sha256(sid.encode('utf-8')).hexdigest()}"
                )
            return self._operator_id_value

    def attach_search_service(self, service: GlobalSearchService) -> None:
        """Attach the one controller-owned read-only search service."""

        if type(service) is not GlobalSearchService:
            raise TypeError("service must be GlobalSearchService")
        with self._publication_lock:
            if self._search_service is not None and self._search_service is not service:
                raise RuntimeError("search service is already attached")
            service.update_snapshot(self._snapshot)
            self._search_service = service

    def attach_conversation_store(self, store: ConversationStore) -> None:
        """Attach the one controller-owned durable agent-chat store."""

        if type(store) is not ConversationStore:
            raise TypeError("store must be a ConversationStore")
        with self._publication_lock:
            if self._conversation_store is store:
                return
            if self._conversation_store is not None:
                raise RuntimeError("conversation store is already attached")
            self._conversation_store = store

    def attach_platform_runtime_reader(
        self,
        reader: _PlatformRuntimeReadPort,
    ) -> None:
        """Attach the one synchronous read port used for command authorization."""

        if not callable(getattr(reader, "read", None)):
            raise TypeError("platform runtime reader must provide read()")
        with self._publication_lock:
            with self._control_lock:
                if self._platform_runtime_reader is reader:
                    return
                if self._platform_runtime_reader is not None:
                    raise RuntimeError("platform runtime reader is already attached")
                if self._command_registry is not None:
                    raise RuntimeError("command registry is already attached")
                self._platform_runtime_reader = reader

    def attach_command_registry(self, registry: CommandRegistry) -> None:
        """Attach the reviewed command registry and publish its exact catalog."""

        if type(registry) is not CommandRegistry:
            raise TypeError("registry must be CommandRegistry")
        if registry.specs != COMMAND_SPECS:
            raise ValueError("registry must use the canonical command catalog")
        with self._publication_lock:
            with self._control_lock:
                if self._command_registry is registry:
                    return
                if self._command_registry is not None:
                    raise RuntimeError("command registry is already attached")
                if self._platform_runtime_reader is None:
                    raise ValueError("command registry requires a platform runtime read port")
                previous = self._snapshot
                runtime_sample = self._read_platform_runtime()
                snapshot = self._command_snapshot(
                    self._upstream_snapshot,
                    previous,
                    runtime_sample,
                    registry,
                )
                self._command_registry = registry
                self._platform_runtime_sample = runtime_sample
                self._snapshot = snapshot
            if self._search_service is not None:
                self._search_service.update_snapshot(snapshot)
            self._publish_to_subscribers(
                MessageType.SNAPSHOT,
                SnapshotPayload(snapshot=snapshot),
                state_version=snapshot.shell.state_version,
                replace_key=("snapshot",),
            )

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
            with self._control_lock:
                previous = self._snapshot
                previous_upstream = self._upstream_snapshot
                same_upstream = self._has_projection_snapshot and snapshot == previous_upstream
                if self._has_projection_snapshot:
                    if (
                        not same_upstream
                        and snapshot.shell.state_version <= previous_upstream.shell.state_version
                    ):
                        raise ValueError("snapshot state version must advance")
                if self._command_registry is not None:
                    runtime_sample = self._read_platform_runtime()
                    effective = self._command_snapshot(
                        snapshot,
                        previous,
                        runtime_sample,
                    )
                    self._platform_runtime_sample = runtime_sample
                else:
                    effective = self._disabled_command_snapshot(snapshot)
                if same_upstream and effective == previous:
                    return
                events: tuple[EventPayload, ...] = ()
                if self._has_projection_snapshot and self._can_publish_incrementally(
                    previous,
                    effective,
                ):
                    try:
                        events = diff_snapshots(previous, effective)
                    except (TypeError, ValueError):
                        events = ()
                self._upstream_snapshot = snapshot
                self._snapshot = effective
                self._cached_snapshot = None
                first_projection = not self._has_projection_snapshot
                self._has_projection_snapshot = True
                cache = self._snapshot_cache
                if cache is not None:
                    try:
                        cache.write(effective)
                    except SnapshotCacheError:
                        self._snapshot_cache_unavailable = True
                    else:
                        self._snapshot_cache_unavailable = False
            if self._search_service is not None:
                self._search_service.update_snapshot(effective)
            if first_projection or not events:
                self._publish_to_subscribers(
                    MessageType.SNAPSHOT,
                    SnapshotPayload(snapshot=effective),
                    state_version=effective.shell.state_version,
                    replace_key=("snapshot",),
                )
                return
            for event in events:
                self._publish_event_to_subscribers(
                    event,
                    state_version=effective.shell.state_version,
                )

    @staticmethod
    def _can_publish_incrementally(
        previous: ConsoleSnapshot,
        current: ConsoleSnapshot,
    ) -> bool:
        return not requires_full_snapshot(previous, current)

    def publish_event(self, event: EventPayload) -> None:
        """Publish one validated event without calling a runtime or broker."""

        if not isinstance(event, EventPayload):
            raise TypeError("event must be an EventPayload")
        with self._publication_lock:
            self._publish_event_to_subscribers(
                event,
                state_version=self._snapshot.shell.state_version,
            )

    def publish_chat_event(self, event: ChatEventPayload) -> None:
        """Publish one validated agent-chat event to subscribed sessions."""

        if type(event) is not ChatEventPayload:
            raise TypeError("event must be a ChatEventPayload")
        validated = ChatEventPayload.model_validate(
            event.model_dump(mode="python"),
            strict=True,
        )
        with self._publication_lock:
            self._publish_to_subscribers(
                MessageType.CHAT_EVENT,
                validated,
                state_version=self._snapshot.shell.state_version,
                replace_key=None,
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

            if envelope.message_type is MessageType.CHAT_HISTORY_REQUEST:
                payload = self._payload(envelope, ChatHistoryRequestPayload, session)
                if isinstance(payload, WireEnvelope):
                    return (payload,)
                assert isinstance(payload, ChatHistoryRequestPayload)
                store = self._conversation_store
                if store is None:
                    return (
                        self._error(
                            session,
                            "chat-unavailable",
                            "Chat history is unavailable.",
                        ),
                    )
                try:
                    page = store.export_history(payload.agent_id, payload.limit, payload.cursor)
                except Exception:
                    return (
                        self._error(
                            session,
                            "chat-unavailable",
                            "Chat history is unavailable.",
                        ),
                    )
                responses: list[WireEnvelope] = []
                for event in page.events:
                    response = self._emit(
                        session,
                        MessageType.CHAT_EVENT,
                        event,
                        state_version=self._snapshot.shell.state_version,
                    )
                    if response.message_type is MessageType.PROTOCOL_ERROR:
                        return (response,)
                    responses.append(response)
                result = self._emit(
                    session,
                    MessageType.CHAT_HISTORY_RESULT,
                    ChatHistoryResultPayload(
                        agent_id=page.agent_id,
                        next_cursor=page.next_cursor,
                    ),
                    state_version=self._snapshot.shell.state_version,
                )
                if result.message_type is MessageType.PROTOCOL_ERROR:
                    return (result,)
                responses.append(result)
                return tuple(responses)

            if envelope.message_type is MessageType.COMMAND:
                registry = self._command_registry
                if registry is None:
                    return (
                        self._error(
                            session,
                            "direction",
                            "Message type is not accepted from clients.",
                        ),
                    )
                payload = self._payload(envelope, CommandMessagePayload, session)
                if isinstance(payload, WireEnvelope):
                    return (payload,)
                assert isinstance(payload, CommandMessagePayload)
                try:
                    with self._control_lock:
                        runtime_sample = self._read_platform_runtime()
                        snapshot = self._command_snapshot(
                            self._upstream_snapshot,
                            self._snapshot,
                            runtime_sample,
                        )
                        self._platform_runtime_sample = runtime_sample
                        self._snapshot = snapshot
                        request = payload.request
                        context = CommandContext(
                            operator_id=self.operator_id,
                            client_id=session.client_id,
                            authenticated=session._authenticated,
                            owns_control_lease=(self._lease.controller_id == session.client_id),
                            control_version=snapshot.control_version,
                            control_hash=snapshot.control_hash,
                            capabilities=snapshot.shell.capabilities,
                            prerequisites=self._prerequisites(
                                snapshot,
                                request,
                                runtime_sample,
                            ),
                        )
                        receipt = registry.execute(context, request)
                except Exception:
                    return (
                        self._error(
                            session,
                            "command-unavailable",
                            "Command processing is unavailable; inspect its receipt before retrying.",
                        ),
                    )
                return (
                    self._emit(
                        session,
                        MessageType.COMMAND_RECEIPT,
                        CommandReceiptPayload(receipt=receipt),
                        state_version=snapshot.shell.state_version,
                    ),
                )

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
        with self._control_lock:
            return self._snapshot

    def _read_platform_runtime(self) -> SourceSample[PlatformRuntimeFacts]:
        reader = self._platform_runtime_reader
        if reader is None:
            return self._unavailable_platform_runtime_sample()
        try:
            return _PLATFORM_RUNTIME_SAMPLE_ADAPTER.validate_python(
                reader.read(),
                strict=True,
            )
        except Exception:
            return self._unavailable_platform_runtime_sample()

    @staticmethod
    def _unavailable_platform_runtime_sample() -> SourceSample[PlatformRuntimeFacts]:
        return SourceSample[PlatformRuntimeFacts](
            value=None,
            freshness=Freshness.UNAVAILABLE,
            observed_at_utc=None,
            source="native platform runtime",
            error=_RUNTIME_UNAVAILABLE_REASON,
        )

    @staticmethod
    def _prerequisite_hash(value: object) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _prerequisites(
        self,
        snapshot: ConsoleSnapshot,
        request: CommandRequest,
        runtime_sample: SourceSample[PlatformRuntimeFacts],
    ) -> EvaluatedPrerequisites:
        checks: tuple[PrerequisiteCheck, ...] = ()
        if request.command_type == "note.add":
            payload = request.payload
            assert isinstance(payload, NoteAddPayload)
            entity = self._note_target(snapshot, payload)
            binding = {
                "target_type": payload.target_type,
                "target_id": payload.target_id,
                "entity": None if entity is None else entity.model_dump(mode="json"),
            }
            checks = (
                PrerequisiteCheck(
                    prerequisite_id="note-target",
                    state="satisfied" if entity is not None else "failed",
                    binding_hash=self._prerequisite_hash(binding),
                    reason=(
                        None
                        if entity is not None
                        else "The selected note target is not present in the current snapshot."
                    ),
                ),
            )
        elif request.command_type in {
            "approval.approve",
            "approval.hold",
            "approval.reject",
        }:
            payload = request.payload
            assert isinstance(payload, ApprovalPayload)
            runtime = runtime_sample.value if runtime_sample.freshness is Freshness.FRESH else None
            approval = next(
                (
                    row
                    for row in (() if runtime is None else runtime.pending_approvals)
                    if row.state == "pending"
                    and row.run_id == payload.run_id
                    and row.checkpoint_id == payload.checkpoint_id
                ),
                None,
            )
            binding = {
                "run_id": payload.run_id,
                "checkpoint_id": payload.checkpoint_id,
                "approval": (None if approval is None else approval.model_dump(mode="json")),
            }
            checks = (
                PrerequisiteCheck(
                    prerequisite_id="pending-approval",
                    state="satisfied" if approval is not None else "failed",
                    binding_hash=self._prerequisite_hash(binding),
                    reason=(
                        None
                        if approval is not None
                        else "The exact run checkpoint is not pending approval."
                    ),
                ),
            )
        elif request.command_type == "agent.enqueue":
            payload = request.payload
            assert isinstance(payload, AgentEnqueuePayload)
            try:
                role = AgentRole(payload.agent_id)
            except ValueError:
                role = None
            approved = role in AUTONOMOUS_AGENT_ROLES if role is not None else False
            binding = {
                "agent_id": payload.agent_id,
                "approved_autonomous_roles": [role.value for role in AUTONOMOUS_AGENT_ROLES],
            }
            checks = (
                PrerequisiteCheck(
                    prerequisite_id="autonomous-agent-role",
                    state="satisfied" if approved else "failed",
                    binding_hash=self._prerequisite_hash(binding),
                    reason=(
                        None
                        if approved
                        else "The requested agent is not an approved autonomous role."
                    ),
                ),
            )
        return EvaluatedPrerequisites(
            request_sha256=canonical_request_hash(request),
            complete=True,
            checks=checks,
        )

    @staticmethod
    def _note_target(snapshot: ConsoleSnapshot, payload: NoteAddPayload) -> object | None:
        if payload.target_type == "stock":
            return next(
                (row for row in snapshot.portfolio.rows if row.symbol == payload.target_id),
                None,
            )
        if payload.target_type == "order":
            return next(
                (row for row in snapshot.orders.rows if row.order_id == payload.target_id),
                None,
            )
        if payload.target_type == "approval":
            return next(
                (row for row in snapshot.risk.approvals if row.approval_id == payload.target_id),
                None,
            )
        return next(
            (row for row in snapshot.timeline.rows if row.event_id == payload.target_id),
            None,
        )

    @staticmethod
    def _command_capabilities(
        runtime_sample: SourceSample[PlatformRuntimeFacts],
        registry: CommandRegistry,
    ) -> tuple[CapabilityView, ...]:
        runtime_fresh = (
            runtime_sample.freshness is Freshness.FRESH and runtime_sample.value is not None
        )
        adapter_capabilities = {row.capability_id: row for row in registry.command_capabilities}
        return (
            CapabilityView(
                capability_id="snapshot.read",
                state=CapabilityState.READ_ONLY,
                reason=None,
            ),
            *(
                (
                    CapabilityView(
                        capability_id=spec.capability_id,
                        state=CapabilityState.DISABLED,
                        reason=_RUNTIME_UNAVAILABLE_REASON,
                    )
                    if (
                        spec.command_type in _RUNTIME_GOVERNED_COMMANDS
                        and not runtime_fresh
                        and adapter_capabilities[spec.command_type].state is CapabilityState.ENABLED
                    )
                    else adapter_capabilities[spec.command_type]
                )
                for spec in COMMAND_SPECS
            ),
        )

    @staticmethod
    def _disabled_command_snapshot(upstream: ConsoleSnapshot) -> ConsoleSnapshot:
        current = {row.capability_id: row for row in upstream.shell.capabilities}
        snapshot_read = current.get("snapshot.read")
        capabilities = (
            (
                CapabilityView(
                    capability_id="snapshot.read",
                    state=CapabilityState.READ_ONLY,
                    reason=None,
                ),
            )
            if snapshot_read is not None
            else ()
        ) + tuple(
            CapabilityView(
                capability_id=capability_id,
                state=CapabilityState.DISABLED,
                reason=(
                    row.reason
                    if (row := current.get(capability_id)) is not None
                    and row.state is CapabilityState.DISABLED
                    else _PHASE_ONE_REASON
                ),
            )
            for capability_id in _ACTION_CAPABILITIES
        )
        if capabilities == upstream.shell.capabilities:
            return upstream
        return upstream.model_copy(
            update={"shell": upstream.shell.model_copy(update={"capabilities": capabilities})}
        )

    def _command_snapshot(
        self,
        upstream: ConsoleSnapshot,
        previous: ConsoleSnapshot | None,
        runtime_sample: SourceSample[PlatformRuntimeFacts],
        registry: CommandRegistry | None = None,
    ) -> ConsoleSnapshot:
        selected_registry = self._command_registry if registry is None else registry
        if selected_registry is None:
            raise RuntimeError("command registry is unavailable")
        capabilities = self._command_capabilities(runtime_sample, selected_registry)
        facts = {
            "upstream_control_version": upstream.control_version,
            "upstream_control_hash": upstream.control_hash,
            "command_specs": [row.model_dump(mode="json") for row in COMMAND_SPECS],
            "capabilities": [row.model_dump(mode="json") for row in capabilities],
            "platform_runtime": platform_runtime_control_binding(runtime_sample),
            "approved_autonomous_agent_roles": [role.value for role in AUTONOMOUS_AGENT_ROLES],
        }
        control_hash = hashlib.sha256(
            json.dumps(facts, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if previous is None:
            control_version = upstream.control_version
        elif previous.control_hash == control_hash:
            control_version = previous.control_version
        else:
            if previous.control_version == _MAX_WIRE_UINT:
                raise OverflowError("control version exhausted the wire range")
            control_version = previous.control_version + 1
        return upstream.model_copy(
            update={
                "shell": upstream.shell.model_copy(update={"capabilities": capabilities}),
                "control_version": control_version,
                "control_hash": control_hash,
                "command_specs": COMMAND_SPECS,
            }
        )

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
            live_readiness=unavailable_live_readiness(),
            live_account=None,
            live_transition_plan=None,
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
        else:
            self._load_cached_snapshot_after_unlock()
        return self._emit(
            session,
            MessageType.AUTH_RESULT,
            AuthResultPayload(
                success=success,
                access_state="viewer" if success else "locked",
                reason=reason,
            ),
        )

    def _load_cached_snapshot_after_unlock(self) -> None:
        cache = self._snapshot_cache
        if cache is None:
            return
        with self._control_lock:
            if self._has_projection_snapshot or self._cached_snapshot is not None:
                return
            try:
                cached = cache.read_after_unlock()
            except SnapshotCacheError:
                self._snapshot_cache_unavailable = True
                return
            if cached is None:
                return
            self._cached_snapshot = cached
            self._snapshot = cached.snapshot
            self._snapshot_cache_unavailable = False

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
