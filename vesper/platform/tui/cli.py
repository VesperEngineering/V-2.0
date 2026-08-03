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
from typing import Sequence

from .contracts import SafeId, WireEnvelope
from .gateway import Gateway
from .pipe_security import current_logon_sid, pipe_name
from .pipe_server import WindowsPipeServer

_PARENT_IDLE_SECONDS = 30.0
_PIPE_PREFIX = r"\\.\pipe\vesper-v20-tui-"


def default_pipe_name() -> str:
    return pipe_name(current_logon_sid())


def _default_state_root() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise RuntimeError("LOCALAPPDATA is unavailable")
    return Path(local) / "Vesper" / "v20" / "tui"


@dataclass
class _Request:
    client_id: SafeId
    envelope: WireEnvelope
    completed: threading.Event
    result: tuple[WireEnvelope, ...] | None = None
    error: BaseException | None = None


class _GatewayCoordinator:
    """Keep gateway work off named-pipe transport threads."""

    def __init__(self, gateway: Gateway) -> None:
        self._gateway = gateway
        self._requests: queue.Queue[_Request | None] = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="v20-tui-gateway", daemon=True)
        self._thread.start()

    def handle(self, client_id: SafeId, envelope: WireEnvelope) -> tuple[WireEnvelope, ...]:
        request = _Request(client_id, envelope, threading.Event())
        self._requests.put(request)
        request.completed.wait()
        if request.error is not None:
            raise request.error
        assert request.result is not None
        return request.result

    def stop(self) -> None:
        self._requests.put(None)
        self._thread.join(timeout=2)

    def _run(self) -> None:
        while True:
            request = self._requests.get()
            if request is None:
                return
            try:
                request.result = self._gateway.handle(request.client_id, request.envelope)
            except BaseException as error:
                request.error = error
            finally:
                request.completed.set()


class _ConnectionIdentity:
    """Give one worker connection an unguessable ID and release it on exit."""

    def __init__(self, gateway: Gateway) -> None:
        self.client_id = f"pipe-{secrets.token_hex(16)}"
        self._gateway = gateway

    def __del__(self) -> None:
        try:
            self._gateway.disconnect(self.client_id)
        except Exception:
            pass


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
    parser = argparse.ArgumentParser(prog="vesper-tui-gateway")
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

    selected_pipe = args.pipe_name or default_pipe_name()
    if not selected_pipe.startswith(_PIPE_PREFIX):
        parser.error("--pipe-name must use the V20 console prefix")
    gateway = Gateway(args.state_root or _default_state_root())
    coordinator = _GatewayCoordinator(gateway)
    server = WindowsPipeServer(selected_pipe)
    stop_event = threading.Event()
    connection_local = threading.local()

    def handle(body: bytes) -> bytes | None:
        envelope = WireEnvelope.model_validate_json(body)
        identity = getattr(connection_local, "identity", None)
        if identity is None:
            identity = _ConnectionIdentity(gateway)
            connection_local.identity = identity
        responses = coordinator.handle(identity.client_id, envelope)
        if len(responses) != 1:
            raise RuntimeError("phase-1 gateway emitted an invalid response count")
        return responses[0].model_dump_json().encode("utf-8")

    def watch_parent() -> None:
        exit_latch = _ParentExitLatch()
        while not stop_event.wait(0.1):
            parent_alive = args.parent_pid is None or _parent_exists(args.parent_pid)
            if exit_latch.observe(
                parent_alive=parent_alive,
                client_count=server.active_worker_count,
                now=time.monotonic(),
            ):
                stop_event.set()
                server.stop()
                return

    watcher = threading.Thread(target=watch_parent, name="v20-tui-parent-watch", daemon=True)
    watcher.start()
    try:
        server.serve(handle, stop_event)
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
