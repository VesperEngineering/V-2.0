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
from pathlib import Path
from typing import Literal, Sequence

from .contracts import SafeId, WireEnvelope
from .event_store import EventStore
from .gateway import Gateway
from .notes import NoteStore
from .pipe_security import current_logon_sid, pipe_name
from .pipe_server import ConnectionFactory, WindowsPipeServer
from .ports import UnavailablePort
from .projections import EventTimelineProjection, LegacyStateProjection, NativePlatformProjection
from .projections.repository import RepositoryProjection
from .projections.windows_system import WindowsSystemProjection
from .snapshot import SnapshotBuilder
from .search import GlobalSearchService
from .sqlite_ledger import TuiLedger
from .stream import ProjectionLoop

_PARENT_IDLE_SECONDS = 30.0
_COORDINATOR_WAIT_SECONDS = 10.0
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


@dataclass(frozen=True, slots=True)
class _ProjectionRuntime:
    loop: ProjectionLoop
    ledger: TuiLedger | None
    event_store: EventStore | None
    note_store: NoteStore | None
    search_service: GlobalSearchService

    def close(self) -> None:
        self.search_service.close()
        if self.event_store is not None:
            self.event_store.close()
        if self.note_store is not None:
            self.note_store.close()
        if self.ledger is not None:
            self.ledger.close()


def _build_projection_runtime(state_root: Path, gateway: Gateway) -> _ProjectionRuntime:
    repository_root = Path(__file__).resolve().parents[3]
    ledger: TuiLedger | None = None
    event_store: EventStore | None = None
    note_store: NoteStore | None = None
    search_service: GlobalSearchService | None = None
    persistent_search_error: str | None = None
    try:
        try:
            ledger = TuiLedger(state_root / "operations.sqlite3")
            event_store = EventStore(ledger)
            note_store = NoteStore(ledger)
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
            persistent_search_error = "Persisted search history is unavailable."

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
        sources = {
            "native.agents": agents,
            "native.portfolio": portfolio,
            "native.orders": orders,
            "native.models": UnavailablePort(
                "No controller-owned typed model source is configured.",
                source="native platform",
            ),
            "legacy.risk": risk,
            "native.data": UnavailablePort(
                "No controller-owned typed data-status source is configured.",
                source="native platform",
            ),
            "native.memory": UnavailablePort(
                "No controller-owned typed memory-status source is configured.",
                source="native platform",
            ),
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
            persistent_error=persistent_search_error,
        )
        gateway.attach_search_service(search_service)
    except BaseException:
        if search_service is not None:
            search_service.close()
        if event_store is not None:
            event_store.close()
        if note_store is not None:
            note_store.close()
        if ledger is not None:
            ledger.close()
        raise
    return _ProjectionRuntime(
        loop=loop,
        ledger=ledger,
        event_store=event_store,
        note_store=note_store,
        search_service=search_service,
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
        self._thread.join()
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
        self._thread.join()

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
        if len(responses) != 1:
            raise RuntimeError("gateway emitted an invalid response count")
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
    gateway = Gateway(state_root)
    runtime = _build_projection_runtime(state_root, gateway)
    stop_event = threading.Event()
    coordinator: _GatewayCoordinator | None = None
    server: WindowsPipeServer | None = None
    watcher: threading.Thread | None = None
    projection_thread: threading.Thread | None = None
    projection_errors: list[BaseException] = []
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

        projection_thread = threading.Thread(
            target=run_projection,
            name="v20-tui-projection",
            daemon=True,
        )
        projection_thread.start()
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
            projection_thread.join(timeout=2)
        runtime.close()
    if projection_thread is not None and projection_thread.is_alive():
        raise RuntimeError("projection loop did not stop")
    if projection_errors:
        raise RuntimeError("projection loop failed") from projection_errors[0]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
