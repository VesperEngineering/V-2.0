"""CLI for the local, current-user V20 operations daemon."""

from __future__ import annotations

import argparse
import hashlib
import signal
from collections.abc import Callable, Sequence
from pathlib import Path
from threading import Event
from typing import Literal, Protocol

from vesper.platform.ops.activation import OperationsActivation, OperationsActivationStore
from vesper.platform.ops.policy import OperationsPolicy, OperationsState, ResourceState
from vesper.platform.ops.supervisor import (
    AtomicDaemonStateStore,
    OperationsSupervisor,
    validate_state_root,
)
from vesper.platform.tui.pipe_security import current_logon_sid
from vesper.platform.tui.views import SafeId, StrictModel


class DaemonLaunchConfig(StrictModel):
    state_root: Path
    mode: Literal["shadow", "paper"]
    activation_receipt_id: SafeId
    start_nonce: SafeId


class Mutex(Protocol):
    def acquire(self) -> bool: ...

    def release(self) -> None: ...


def operations_mutex_name(logon_sid: str) -> str:
    if type(logon_sid) is not str or not logon_sid.strip():
        raise ValueError("logon SID is required")
    suffix = hashlib.sha256(logon_sid.encode("utf-8")).hexdigest()[:16]
    return f"Local\\V20OperationsDaemon-{suffix}"


class CurrentUserMutex:
    """One named mutex per Windows logon session."""

    def __init__(self, name: str) -> None:
        if type(name) is not str or not name.startswith("Local\\V20OperationsDaemon-"):
            raise ValueError("operations mutex name is invalid")
        self._name = name
        self._handle = None

    def acquire(self) -> bool:
        if self._handle is not None:
            raise RuntimeError("operations mutex is already acquired")
        try:
            import win32api
            import win32event
            import winerror
        except ImportError as exc:  # pragma: no cover - Windows production dependency
            raise RuntimeError("Windows mutex support is unavailable") from exc
        handle = win32event.CreateMutex(None, True, self._name)
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            win32api.CloseHandle(handle)
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is None:
            return
        import win32api
        import win32event

        handle = self._handle
        self._handle = None
        try:
            win32event.ReleaseMutex(handle)
        finally:
            win32api.CloseHandle(handle)


class _NoAuthority:
    def require(self, _capability, _receipt_id: str) -> None:
        raise RuntimeError("no operations activation authority is configured")


class _IdleStateReader:
    def read(self) -> OperationsState:
        return OperationsState(
            resources=ResourceState(
                gpu_percent=0,
                gpu_temperature_c=0,
                memory_percent=0,
                disk_free_gb=0,
                recent_errors=0,
                qwen_lease_active=False,
            )
        )


class _NoEffectExecutor:
    def execute(self, _decision) -> None:
        return None


def _default_supervisor(config: DaemonLaunchConfig) -> OperationsSupervisor:
    activation_store = OperationsActivationStore(OperationsActivation(), _NoAuthority())
    return OperationsSupervisor(
        OperationsPolicy(activation_store),
        _IdleStateReader(),
        _NoEffectExecutor(),
        AtomicDaemonStateStore(config.state_root),
        run_id=config.start_nonce,
    )


def _parse_args(argv: Sequence[str] | None) -> DaemonLaunchConfig:
    parser = argparse.ArgumentParser(prog="vesper-ops-daemon")
    parser.add_argument("--state-root", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=("shadow", "paper"))
    parser.add_argument("--activation-receipt-id", required=True)
    parser.add_argument("--start-nonce", required=True)
    values = parser.parse_args(argv)
    state_root = validate_state_root(values.state_root)
    return DaemonLaunchConfig.model_validate(
        {
            "state_root": state_root,
            "mode": values.mode,
            "activation_receipt_id": values.activation_receipt_id,
            "start_nonce": values.start_nonce,
        },
        strict=True,
    )


def run(
    argv: Sequence[str] | None = None,
    *,
    logon_sid_provider: Callable[[], str] = current_logon_sid,
    mutex_factory: Callable[[str], Mutex] = CurrentUserMutex,
    supervisor_factory: Callable[[DaemonLaunchConfig], OperationsSupervisor] = (
        _default_supervisor
    ),
) -> int:
    config = _parse_args(argv)
    mutex = mutex_factory(operations_mutex_name(logon_sid_provider()))
    if not mutex.acquire():
        return 2
    stop_event = Event()
    previous_handlers: dict[signal.Signals, object] = {}

    def request_stop(_signum, _frame) -> None:
        stop_event.set()

    try:
        for signal_name in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signal_name] = signal.getsignal(signal_name)
            signal.signal(signal_name, request_stop)
        supervisor = supervisor_factory(config)
        supervisor.run(stop_event)
        return 0
    finally:
        for signal_name, handler in previous_handlers.items():
            signal.signal(signal_name, handler)
        mutex.release()


def main() -> None:
    raise SystemExit(run())
