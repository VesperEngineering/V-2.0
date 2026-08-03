"""Serve the locked local V20 console gateway."""

from __future__ import annotations

import argparse
import os
import queue
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

from .contracts import SafeId, WireEnvelope
from .gateway import Gateway
from .pipe_security import current_logon_sid, pipe_name
from .pipe_server import ConnectionFactory, WindowsPipeServer

_PARENT_IDLE_SECONDS = 30.0
_COORDINATOR_WAIT_SECONDS = 10.0


def default_pipe_name() -> str:
    return pipe_name(current_logon_sid())


def _default_state_root() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise RuntimeError("LOCALAPPDATA is unavailable")
    return Path(local) / "Vesper" / "v20" / "tui"


def _normalize_state_root(value: Path) -> Path:
    if not value.is_absolute():
        raise ValueError("state root must be absolute")
    try:
        if value.is_symlink():
            raise ValueError("state root cannot be a symbolic link")
        normalized = value.resolve(strict=False)
    except OSError as error:
        raise ValueError("state root cannot be resolved safely") from error
    if normalized == Path(normalized.anchor):
        raise ValueError("state root cannot be a filesystem root")
    if normalized.exists() and not normalized.is_dir():
        raise ValueError("state root must be a directory")
    return normalized


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
        self._thread.join(timeout=_COORDINATOR_WAIT_SECONDS)

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


def _gateway_connection_factory(coordinator: _GatewayCoordinator) -> ConnectionFactory:
    """Create one explicit authenticated-session boundary per pipe connection."""

    def factory():
        client_id = f"pipe-{secrets.token_hex(16)}"

        def handle(body: bytes) -> bytes | None:
            envelope = WireEnvelope.model_validate_json(body)
            responses = coordinator.handle(client_id, envelope)
            if len(responses) != 1:
                raise RuntimeError("phase-1 gateway emitted an invalid response count")
            return responses[0].model_dump_json().encode("utf-8")

        def close() -> None:
            coordinator.disconnect(client_id)

        return handle, close

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
        state_root = _normalize_state_root(args.state_root or _default_state_root())
    except ValueError as error:
        parser.error(str(error))
    gateway = Gateway(state_root)
    coordinator = _GatewayCoordinator(gateway)
    server = WindowsPipeServer(selected_pipe)
    stop_event = threading.Event()
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

    watcher = threading.Thread(target=watch_parent, name="v20-tui-parent-watch", daemon=True)
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
        coordinator.stop()
        watcher.join(timeout=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
