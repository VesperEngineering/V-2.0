"""Serve the locked local V20 console gateway."""

from __future__ import annotations

import argparse
import os
import queue
import secrets
import stat
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Sequence

from vesper.platform.persistence import PlatformPaths, default_platform_paths
from vesper.platform.service import LocalPlatformService

from .alert_dismissals import AlertDismissalStore
from .command_contracts import CommandReceipt
from .command_ports import LocalPlatformCommandPort
from .command_registry import CommandRegistry
from .contracts import SafeId, WireEnvelope
from .conversations import ConversationStore
from .event_store import EventStore
from .gateway import Gateway
from .notes import NoteStore
from .pipe_security import current_logon_sid, pipe_name
from .pipe_server import ConnectionFactory, WindowsPipeServer
from .ports import UnavailablePort
from .projections import (
    AttentionAlertProjection,
    EventTimelineProjection,
    LegacyStateProjection,
    ManagedMemoryProjection,
    NativePlatformProjection,
    NotificationHealthProjection,
    PlatformRuntimeProjection,
)
from .projections.repository import RepositoryProjection
from .projections.windows_system import WindowsSystemProjection
from .snapshot import SnapshotBuilder
from .search import GlobalSearchService
from .session_presence import NamedEventSessionPresence, SessionPresencePublisher
from .snapshot_cache import SnapshotCache
from .sqlite_ledger import TuiLedger
from .stream import ProjectionLoop
from .views import Freshness
from .working_memory import default_vault_path

_PARENT_IDLE_SECONDS = 30.0
_COORDINATOR_WAIT_SECONDS = 10.0
_COORDINATOR_JOIN_SECONDS = 1.0
_RECOVERY_POLL_SECONDS = 5.0
_PROJECTION_JOIN_SECONDS = 2.0
_RECOVERY_JOIN_SECONDS = 1.0
_OPERATIONAL_ADAPTER_ERRORS = (OSError, RuntimeError, ValueError)


def default_pipe_name() -> str:
    return pipe_name(current_logon_sid())


def _default_state_root() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise RuntimeError("LOCALAPPDATA is unavailable")
    return Path(local) / "Vesper" / "v20" / "tui"


def _contains_reparse_point(value: Path) -> bool:
    current = Path(value.anchor)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    for part in value.parts[1:]:
        current /= part
        if not os.path.lexists(current):
            continue
        try:
            attributes = getattr(os.lstat(current), "st_file_attributes", 0)
        except OSError as error:
            raise ValueError("state root cannot be inspected safely") from error
        if attributes & reparse_flag:
            return True
    return False


def _normalize_state_root(value: Path) -> Path:
    if not value.is_absolute():
        raise ValueError("state root must be absolute")
    if str(value).startswith("\\\\"):
        raise ValueError("state root cannot be a UNC path")
    try:
        if _contains_reparse_point(value):
            raise ValueError("state root cannot contain a reparse-point alias")
        normalized = value.resolve(strict=False)
    except OSError as error:
        raise ValueError("state root cannot be resolved safely") from error
    if normalized == Path(normalized.anchor):
        raise ValueError("state root cannot be a filesystem root")
    if normalized.exists() and not normalized.is_dir():
        raise ValueError("state root must be a directory")
    return normalized


def _serving_state_root(value: Path | None) -> Path:
    canonical = _normalize_state_root(_default_state_root())
    selected = canonical if value is None else _normalize_state_root(value)
    if selected != canonical:
        raise ValueError("state root must equal the canonical LocalAppData path")
    return canonical


def _build_gateway(
    state_root: Path,
    *,
    session_presence: SessionPresencePublisher | None = None,
) -> Gateway:
    """Build the production gateway with current-user encrypted startup cache."""

    return Gateway(
        state_root,
        snapshot_cache=SnapshotCache(state_root / "snapshot-cache.dpapi"),
        session_presence=session_presence,
    )


@dataclass(frozen=True, slots=True)
class _ProjectionRuntime:
    loop: ProjectionLoop
    ledger: TuiLedger | None
    event_store: EventStore | None
    note_store: NoteStore | None
    search_service: GlobalSearchService
    platform_runtime_reader: PlatformRuntimeProjection
    command_registry: CommandRegistry | None
    conversation_store: ConversationStore | None

    def recover_commands(
        self,
        now_utc: datetime | None = None,
    ) -> tuple[CommandReceipt, ...]:
        registry = self.command_registry
        if registry is None:
            return ()
        now = datetime.now(timezone.utc) if now_utc is None else now_utc
        recovered = list(registry.recover_local_running(now))
        runtime_sample = self.platform_runtime_reader.read()
        if runtime_sample.freshness is Freshness.FRESH:
            recovered.extend(registry.recover_running(now))
        return tuple(recovered)

    def close(self) -> None:
        self.search_service.close()
        if self.command_registry is not None:
            self.command_registry.close()
        if self.event_store is not None:
            self.event_store.close()
        if self.note_store is not None:
            self.note_store.close()
        if self.conversation_store is not None:
            self.conversation_store.close()
        if self.ledger is not None:
            self.ledger.close()


def _build_projection_runtime(
    state_root: Path,
    gateway: Gateway,
    *,
    platform_paths: PlatformPaths | None = None,
) -> _ProjectionRuntime:
    repository_root = Path(__file__).resolve().parents[3]
    selected_platform_paths = default_platform_paths() if platform_paths is None else platform_paths
    platform_runtime_reader = PlatformRuntimeProjection(selected_platform_paths)
    gateway.attach_platform_runtime_reader(platform_runtime_reader)
    ledger: TuiLedger | None = None
    event_store: EventStore | None = None
    note_store: NoteStore | None = None
    command_registry: CommandRegistry | None = None
    conversation_store: ConversationStore | None = None
    search_service: GlobalSearchService | None = None
    dismissal_projection_store: AlertDismissalStore | None = None
    persistent_search_error: str | None = None
    try:
        try:
            ledger = TuiLedger(state_root / "operations.sqlite3")
            event_store = EventStore(ledger)
            note_store = NoteStore(ledger)
            dismissal_projection_store = AlertDismissalStore(ledger, state_root)
        except _OPERATIONAL_ADAPTER_ERRORS:
            if event_store is not None:
                event_store.close()
                event_store = None
            if note_store is not None:
                note_store.close()
                note_store = None
            if ledger is not None:
                ledger.close()
                ledger = None
            dismissal_projection_store = None
            persistent_search_error = "Persisted search history is unavailable."

        try:
            conversation_store = ConversationStore(state_root / "conversations.sqlite3")
            gateway.attach_conversation_store(conversation_store)
        except _OPERATIONAL_ADAPTER_ERRORS:
            if conversation_store is not None:
                conversation_store.close()
                conversation_store = None

        try:
            native = NativePlatformProjection(repository_root)
            agents = native
            portfolio = native.portfolio_port
            orders = native.order_port
        except _OPERATIONAL_ADAPTER_ERRORS:
            agents = UnavailablePort(
                "Native agent projection could not be initialized.",
                source="native platform",
            )
            portfolio = UnavailablePort(
                "No typed reconciled portfolio source is configured.",
                source="native platform",
            )
            orders = UnavailablePort(
                "No controller-owned typed order source is configured.",
                source="native platform",
            )

        def unavailable(reason: str, source: str) -> UnavailablePort:
            return UnavailablePort(reason, source=source)

        try:
            risk = LegacyStateProjection(repository_root, Path("data/engine_state.json"))
        except _OPERATIONAL_ADAPTER_ERRORS:
            risk = unavailable(
                "Legacy risk projection could not be initialized.",
                "legacy saved engine state",
            )
        try:
            repository = RepositoryProjection(repository_root)
        except _OPERATIONAL_ADAPTER_ERRORS:
            repository = unavailable(
                "Repository projection could not be initialized.",
                "repository",
            )
        try:
            windows = WindowsSystemProjection(disk_paths={"workspace": repository_root})
        except _OPERATIONAL_ADAPTER_ERRORS:
            windows = unavailable(
                "Windows system projection could not be initialized.",
                "windows-system",
            )
        timeline = (
            EventTimelineProjection(event_store, limit=10_000)
            if event_store is not None
            else unavailable(
                "Timeline event storage is unavailable.",
                "tui event store",
            )
        )
        try:
            memory = ManagedMemoryProjection(default_vault_path())
        except _OPERATIONAL_ADAPTER_ERRORS:
            memory = unavailable(
                "Managed V20 working-memory projection could not be initialized.",
                "managed V20 working memory",
            )
        sources = {
            "native.agents": agents,
            "native.portfolio": portfolio,
            "native.orders": orders,
            "native.models": UnavailablePort(
                "No controller-owned active, rollback, candidate, and regime registry is configured.",
                source="native platform",
            ),
            "legacy.risk": risk,
            "native.data": UnavailablePort(
                "No controller-owned typed data-status source is configured.",
                source="native platform",
            ),
            "native.memory": memory,
            "platform.runtime": platform_runtime_reader,
            "operations.attention": AttentionAlertProjection(
                state_root,
                dismissals=dismissal_projection_store,
            ),
            "operations.notification-health": NotificationHealthProjection(state_root),
            "repository.system": repository,
            "windows.system": windows,
            "events.timeline": timeline,
        }
        loop = ProjectionLoop(
            sources=sources,
            builder=SnapshotBuilder(),
            publisher=gateway,
        )
        search_service = GlobalSearchService(
            gateway.snapshot(),
            event_store,
            note_store,
            memory_archive=(memory if isinstance(memory, ManagedMemoryProjection) else None),
            persistent_error=persistent_search_error,
        )
        gateway.attach_search_service(search_service)
        if isinstance(memory, ManagedMemoryProjection):
            gateway.attach_memory_projection(memory)

        if ledger is not None:
            try:
                service = LocalPlatformService(
                    selected_platform_paths,
                    profiles_root=repository_root / "profiles" / "native",
                )
                port = LocalPlatformCommandPort(
                    service,
                    operator_id=gateway.operator_id,
                )
                command_registry = CommandRegistry(
                    ledger,
                    port,
                    alert_store=AlertDismissalStore(ledger, state_root),
                )
                recovery_now = datetime.now(timezone.utc)
                command_registry.recover_local_running(recovery_now)
                initial_runtime = platform_runtime_reader.read()
                if initial_runtime.freshness is Freshness.FRESH:
                    command_registry.recover_running(recovery_now)
                gateway.attach_command_registry(command_registry)
            except _OPERATIONAL_ADAPTER_ERRORS:
                if command_registry is not None:
                    command_registry.close()
                    command_registry = None
    except BaseException:
        if command_registry is not None:
            command_registry.close()
        if search_service is not None:
            search_service.close()
        if event_store is not None:
            event_store.close()
        if note_store is not None:
            note_store.close()
        if conversation_store is not None:
            conversation_store.close()
        if ledger is not None:
            ledger.close()
        raise
    return _ProjectionRuntime(
        loop=loop,
        ledger=ledger,
        event_store=event_store,
        note_store=note_store,
        search_service=search_service,
        platform_runtime_reader=platform_runtime_reader,
        command_registry=command_registry,
        conversation_store=conversation_store,
    )


@dataclass
class _Request:
    client_id: SafeId
    operation: Literal["handle", "disconnect"]
    completed: threading.Event
    envelope: WireEnvelope | None = None
    result: tuple[WireEnvelope, ...] | None = None
    error: BaseException | None = None


class CoordinatorClosedError(RuntimeError):
    """The bounded gateway coordinator no longer accepts work."""


class _GatewayCoordinator:
    """Keep gateway work off named-pipe transport threads."""

    def __init__(self, gateway: Gateway) -> None:
        self._gateway = gateway
        self._requests: queue.Queue[_Request | None] = queue.Queue()
        self._admission_lock = threading.Lock()
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="v20-tui-gateway", daemon=True)
        self._thread.start()

    @property
    def closed(self) -> bool:
        with self._admission_lock:
            return self._closed

    def handle(self, client_id: SafeId, envelope: WireEnvelope) -> tuple[WireEnvelope, ...]:
        request = _Request(client_id, "handle", threading.Event(), envelope=envelope)
        self._submit(request)
        if request.error is not None:
            raise request.error
        assert request.result is not None
        return request.result

    def disconnect(self, client_id: SafeId) -> None:
        request = _Request(client_id, "disconnect", threading.Event())
        self._submit(request)
        if request.error is not None:
            raise request.error

    def poll(self, client_id: SafeId) -> WireEnvelope | None:
        """Drain only the bounded connection outbox on the transport thread."""

        return self._gateway.poll(client_id)

    def disconnect_after_stop(self, client_id: SafeId) -> None:
        """Release a late-closing session only after queued work is fully drained."""

        with self._admission_lock:
            if not self._closed:
                raise RuntimeError("coordinator is still accepting disconnects")
        if self._thread.is_alive():
            return
        self._gateway.disconnect(client_id)

    def _submit(self, request: _Request) -> None:
        with self._admission_lock:
            if self._closed:
                raise CoordinatorClosedError("gateway coordinator is closed")
            self._requests.put(request)
        if not request.completed.wait(_COORDINATOR_WAIT_SECONDS):
            raise CoordinatorClosedError("gateway coordinator request did not complete")

    def stop(self) -> None:
        with self._admission_lock:
            if not self._closed:
                self._closed = True
                self._requests.put(None)
        self._thread.join(timeout=_COORDINATOR_JOIN_SECONDS)

    def _run(self) -> None:
        while True:
            request = self._requests.get()
            if request is None:
                return
            try:
                if request.operation == "disconnect":
                    self._gateway.disconnect(request.client_id)
                else:
                    assert request.envelope is not None
                    request.result = self._gateway.handle(request.client_id, request.envelope)
            except BaseException as error:
                request.error = error
            finally:
                request.completed.set()


class _GatewayConnection:
    """One callable request path plus nonblocking idle-push polling."""

    def __init__(self, coordinator: _GatewayCoordinator, client_id: SafeId) -> None:
        self._coordinator = coordinator
        self._client_id = client_id

    def __call__(self, body: bytes) -> bytes | None:
        envelope = WireEnvelope.model_validate_json(body)
        responses = self._coordinator.handle(self._client_id, envelope)
        if not responses:
            raise RuntimeError("gateway emitted no response")
        return self.poll()

    def poll(self) -> bytes | None:
        envelope = self._coordinator.poll(self._client_id)
        if envelope is None:
            return None
        return envelope.model_dump_json().encode("utf-8")


def _gateway_connection_factory(coordinator: _GatewayCoordinator) -> ConnectionFactory:
    """Create one explicit authenticated-session boundary per pipe connection."""

    def factory():
        client_id = f"pipe-{secrets.token_hex(16)}"
        close_lock = threading.Lock()
        closed = False

        connection = _GatewayConnection(coordinator, client_id)

        def close() -> None:
            nonlocal closed
            with close_lock:
                if closed:
                    return
                closed = True
            try:
                coordinator.disconnect(client_id)
            except CoordinatorClosedError:
                coordinator.disconnect_after_stop(client_id)

        return connection, close

    return factory


class _ParentExitLatch:
    """Require one uninterrupted idle window after the launcher parent exits."""

    def __init__(self, idle_seconds: float = _PARENT_IDLE_SECONDS) -> None:
        self._idle_seconds = idle_seconds
        self._idle_since: float | None = None

    def observe(self, *, parent_alive: bool, client_count: int, now: float) -> bool:
        if parent_alive or client_count:
            self._idle_since = None
            return False
        if self._idle_since is None:
            self._idle_since = now
            return False
        return now - self._idle_since >= self._idle_seconds


def _parent_exists(parent_pid: int) -> bool:
    try:
        os.kill(parent_pid, 0)
    except OSError:
        return False
    return True


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vesper-tui-gateway", allow_abbrev=False)
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--pipe-name")
    parser.add_argument("--parent-pid", type=int)
    parser.add_argument("--print-pipe-name", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.print_pipe_name:
        if args.state_root is not None or args.pipe_name is not None or args.parent_pid is not None:
            parser.error("--print-pipe-name cannot be combined with serving options")
        print(default_pipe_name())
        return 0
    if args.parent_pid is not None and args.parent_pid <= 0:
        parser.error("--parent-pid must be positive")

    expected_pipe = default_pipe_name()
    selected_pipe = args.pipe_name or expected_pipe
    if selected_pipe != expected_pipe:
        parser.error("--pipe-name must equal the current logon pipe name")
    try:
        state_root = _serving_state_root(args.state_root)
    except ValueError as error:
        parser.error(str(error))
    presence = NamedEventSessionPresence()
    try:
        gateway = _build_gateway(state_root, session_presence=presence)
    except BaseException:
        presence.close()
        raise
    try:
        runtime = _build_projection_runtime(state_root, gateway)
    except BaseException:
        gateway.close()
        raise
    stop_event = threading.Event()
    coordinator: _GatewayCoordinator | None = None
    server: WindowsPipeServer | None = None
    watcher: threading.Thread | None = None
    projection_thread: threading.Thread | None = None
    recovery_thread: threading.Thread | None = None
    projection_errors: list[BaseException] = []
    recovery_errors: list[BaseException] = []
    projection_stuck = False
    recovery_stuck = False
    try:
        coordinator = _GatewayCoordinator(gateway)
        server = WindowsPipeServer(selected_pipe)
        connection_factory = _gateway_connection_factory(coordinator)

        def watch_parent() -> None:
            exit_latch = _ParentExitLatch()
            while not stop_event.is_set() and not server.ready_event.wait(0.1):
                pass
            while not stop_event.wait(0.1):
                parent_alive = args.parent_pid is None or _parent_exists(args.parent_pid)
                if exit_latch.observe(
                    parent_alive=parent_alive,
                    client_count=server.active_client_count,
                    now=time.monotonic(),
                ):
                    stop_event.set()
                    server.stop()
                    return

        def run_projection() -> None:
            try:
                runtime.loop.run(stop_event)
            except BaseException as error:
                projection_errors.append(error)
                stop_event.set()
                server.stop()

        def run_recovery() -> None:
            while not stop_event.wait(_RECOVERY_POLL_SECONDS):
                try:
                    runtime.recover_commands()
                except BaseException as error:
                    recovery_errors.append(error)
                    stop_event.set()
                    server.stop()
                    return

        projection_thread = threading.Thread(
            target=run_projection,
            name="v20-tui-projection",
            daemon=True,
        )
        projection_thread.start()
        recovery_callback = getattr(runtime, "recover_commands", None)
        if callable(recovery_callback):
            recovery_thread = threading.Thread(
                target=run_recovery,
                name="v20-tui-command-recovery",
                daemon=True,
            )
            recovery_thread.start()
        watcher = threading.Thread(
            target=watch_parent,
            name="v20-tui-parent-watch",
            daemon=True,
        )
        watcher.start()
        try:
            server.serve(
                lambda body: body,
                stop_event,
                connection_factory=connection_factory,
            )
        except KeyboardInterrupt:
            stop_event.set()
            server.stop()
    finally:
        stop_event.set()
        if server is not None:
            server.stop()
        if coordinator is not None:
            coordinator.stop()
        if watcher is not None:
            watcher.join(timeout=1)
        if projection_thread is not None:
            projection_thread.join(timeout=_PROJECTION_JOIN_SECONDS)
        if recovery_thread is not None:
            recovery_thread.join(timeout=_RECOVERY_JOIN_SECONDS)
        projection_stuck = projection_thread is not None and projection_thread.is_alive()
        recovery_stuck = recovery_thread is not None and recovery_thread.is_alive()
        if projection_stuck or recovery_stuck:
            gateway.close()
        else:
            try:
                runtime.close()
            finally:
                gateway.close()
    if projection_stuck:
        raise RuntimeError("projection loop did not stop; runtime was left open")
    if recovery_stuck:
        raise RuntimeError("command recovery loop did not stop; runtime was left open")
    if projection_errors:
        raise RuntimeError("projection loop failed") from projection_errors[0]
    if recovery_errors:
        raise RuntimeError("command recovery loop failed") from recovery_errors[0]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
