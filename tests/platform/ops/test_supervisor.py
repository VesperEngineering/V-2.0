from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event

import pytest

from vesper.platform.ops import cli as ops_cli
from vesper.platform.ops.activation import OperationsActivation, OperationsActivationStore
from vesper.platform.ops.alerts import AtomicAlertRecordStore, OperationsAlertRouter
from vesper.platform.ops.notification_health import AtomicNotificationFailureHealthSink
from vesper.platform.ops.cli import operations_mutex_name, run
from vesper.platform.ops.policy import OperationsPolicy, OperationsState, ResourceState
from vesper.platform.ops.services import RuntimeReceipt, ServiceReceipt
from vesper.platform.ops import supervisor as supervisor_module
from vesper.platform.ops.supervisor import AtomicDaemonStateStore, OperationsSupervisor
from vesper.platform.tui.command_contracts import CommandRequest, ConfirmationProof, ReceiptStatus
from vesper.platform.tui.command_policy import (
    CommandContext,
    EvaluatedPrerequisites,
    canonical_request_hash,
)
from vesper.platform.tui.command_ports import PortResult
from vesper.platform.tui.command_registry import CommandRegistry
from vesper.platform.tui.gateway import Gateway
from vesper.platform.tui.ports import PlatformRuntimeFacts, SourceSample
from vesper.platform.tui.views import CapabilityState, CapabilityView, Freshness


NOW = datetime(2026, 8, 4, 14, 0, tzinfo=timezone.utc)
CONTROL_HASH = "b" * 64


class NoAuthority:
    def require(self, capability, receipt_id: str) -> None:  # pragma: no cover - disabled
        raise AssertionError((capability, receipt_id))


def _policy() -> OperationsPolicy:
    return OperationsPolicy(OperationsActivationStore(OperationsActivation(), NoAuthority()))


def _state() -> OperationsState:
    return OperationsState(
        resources=ResourceState(
            gpu_percent=0,
            gpu_temperature_c=30,
            memory_percent=10,
            disk_free_gb=100,
            recent_errors=0,
            qwen_lease_active=False,
        )
    )


class StateReader:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    def read(self) -> OperationsState:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return _state()


class Executor:
    def __init__(self) -> None:
        self.decisions = []

    def execute(self, decision) -> None:
        self.decisions.append(decision)


class FailingObserver:
    def __init__(self) -> None:
        self.calls: list[tuple[OperationsState, datetime]] = []

    def observe(self, state: OperationsState, observed_at_utc: datetime) -> None:
        self.calls.append((state, observed_at_utc))
        raise RuntimeError("private-notification-failure")

    def observe_failure(self, observed_at_utc: datetime) -> None:
        del observed_at_utc


class NotificationRecorder:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send_attention(self, alert_id: str):
        self.sent.append(alert_id)

    def resolve(self, alert_id: str) -> None:
        raise AssertionError(alert_id)


class FailingFailureObserver:
    def __init__(self) -> None:
        self.failure_calls: list[datetime] = []

    def observe(self, state: OperationsState, observed_at_utc: datetime) -> None:
        del state, observed_at_utc

    def observe_failure(self, observed_at_utc: datetime) -> None:
        self.failure_calls.append(observed_at_utc)
        raise RuntimeError("private-observer-failure")


class StopAfter:
    def __init__(self, waits: int) -> None:
        self.remaining = waits
        self.timeouts: list[float] = []

    def is_set(self) -> bool:
        return False

    def wait(self, timeout: float) -> bool:
        self.timeouts.append(timeout)
        self.remaining -= 1
        return self.remaining == 0


def test_supervisor_writes_atomic_heartbeat_health_and_clean_stop(tmp_path: Path) -> None:
    reader = StateReader()
    executor = Executor()
    store = AtomicDaemonStateStore(tmp_path)
    supervisor = OperationsSupervisor(_policy(), reader, executor, store, clock=lambda: NOW)

    supervisor.run(StopAfter(1))

    heartbeat = json.loads((tmp_path / "heartbeat.json").read_text(encoding="utf-8"))
    health = json.loads((tmp_path / "health.json").read_text(encoding="utf-8"))
    clean_stop = json.loads((tmp_path / "clean-stop.json").read_text(encoding="utf-8"))
    assert heartbeat["decision_kind"] == "rest"
    assert health["state"] == "stopped"
    assert clean_stop["clean"] is True
    assert not tuple(tmp_path.glob("*.tmp"))
    assert len(executor.decisions) == 1


def test_notification_observer_failure_degrades_health_without_stopping_loop(
    tmp_path: Path,
) -> None:
    observer = FailingObserver()
    executor = Executor()
    supervisor = OperationsSupervisor(
        _policy(),
        StateReader(),
        executor,
        AtomicDaemonStateStore(tmp_path),
        clock=lambda: NOW,
        state_observer=observer,
    )

    supervisor.run(StopAfter(1))

    health_raw = (tmp_path / "health.json").read_text(encoding="utf-8")
    health = json.loads(health_raw)
    assert health["healthy"] is False
    assert health["state"] == "stopped"
    assert health["error"] == "Operations observer failed (RuntimeError)."
    assert "private-notification-failure" not in health_raw
    assert observer.calls == [(_state(), NOW)]
    assert len(executor.decisions) == 1


def test_notification_setup_failure_never_prevents_default_daemon_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_probe():
        raise OSError("private-notification-setup-failure")

    monkeypatch.setattr(ops_cli, "CurrentLogonSessionProbe", fail_probe)
    supervisor = ops_cli._default_supervisor(
        ops_cli.DaemonLaunchConfig(
            state_root=tmp_path,
            mode="shadow",
            activation_receipt_id="grant-1",
            start_nonce="nonce-1",
        )
    )

    supervisor.run(StopAfter(1))

    health_raw = (tmp_path / "health.json").read_text(encoding="utf-8")
    assert json.loads(health_raw)["state"] == "stopped"
    assert "private-notification-setup-failure" not in health_raw
    notification_raw = (tmp_path / "notification-health.json").read_text(encoding="utf-8")
    notification = json.loads(notification_raw)
    assert set(notification) == {"code", "observed_at_utc", "state"}
    assert notification["code"] == "notification-delivery-failed"
    assert notification["state"] == "failed"
    assert isinstance(notification["observed_at_utc"], str)
    assert "private-notification-setup-failure" not in notification_raw
    alert_raw = (tmp_path / "attention-alert.json").read_text(encoding="utf-8")
    alert = json.loads(alert_raw)
    assert alert["severity"] == "urgent"
    assert alert["alert_id"].startswith("alert:")
    assert "notification-setup" not in alert_raw
    heartbeat = json.loads((tmp_path / "heartbeat.json").read_text(encoding="utf-8"))
    assert heartbeat["decision_kind"] == "incident"


def test_default_daemon_injects_durable_generic_notification_health(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class NotificationPortSpy:
        def __init__(self, sessions, *, health) -> None:
            captured["sessions"] = sessions
            captured["health"] = health

        def send_attention(self, alert_id):  # pragma: no cover - construction only
            raise AssertionError(alert_id)

        def resolve(self, alert_id):  # pragma: no cover - construction only
            raise AssertionError(alert_id)

    session_probe = object()
    monkeypatch.setattr(ops_cli, "CurrentLogonSessionProbe", lambda: session_probe)
    monkeypatch.setattr(ops_cli, "WindowsNotificationPort", NotificationPortSpy)

    ops_cli._default_supervisor(
        ops_cli.DaemonLaunchConfig(
            state_root=tmp_path,
            mode="shadow",
            activation_receipt_id="grant-1",
            start_nonce="nonce-1",
        )
    )

    assert captured["sessions"] is session_probe
    health = captured["health"]
    assert isinstance(health, AtomicNotificationFailureHealthSink)
    assert health.path == tmp_path / "notification-health.json"
    assert not health.path.exists()


def test_supervisor_failure_records_unhealthy_without_false_clean_stop(tmp_path: Path) -> None:
    store = AtomicDaemonStateStore(tmp_path)
    supervisor = OperationsSupervisor(
        _policy(),
        StateReader(error=RuntimeError("token=do-not-persist-this")),
        Executor(),
        store,
        clock=lambda: NOW,
    )

    with pytest.raises(RuntimeError, match="do-not-persist-this"):
        supervisor.run(StopAfter(1))

    raw_health = (tmp_path / "health.json").read_text(encoding="utf-8")
    health = json.loads(raw_health)
    assert health["healthy"] is False
    assert health["state"] == "failed"
    assert health["error"] == "Operations loop failed (RuntimeError)."
    assert "do-not-persist-this" not in raw_health
    assert not (tmp_path / "clean-stop.json").exists()


def test_real_operations_loop_failure_persists_and_notifies_generic_incident(
    tmp_path: Path,
) -> None:
    notifications = NotificationRecorder()
    observer = OperationsAlertRouter(notifications, AtomicAlertRecordStore(tmp_path))
    supervisor = OperationsSupervisor(
        _policy(),
        StateReader(error=RuntimeError("portfolio=private")),
        Executor(),
        AtomicDaemonStateStore(tmp_path),
        clock=lambda: NOW,
        state_observer=observer,
    )

    with pytest.raises(RuntimeError, match="portfolio=private"):
        supervisor.run(StopAfter(1))

    raw = (tmp_path / "attention-alert.json").read_text(encoding="utf-8")
    record = json.loads(raw)
    assert record["severity"] == "urgent"
    assert record["resolved_at_utc"] is None
    assert notifications.sent == [record["alert_id"]]
    assert "portfolio" not in raw


def test_failure_observer_error_never_masks_original_loop_error(tmp_path: Path) -> None:
    observer = FailingFailureObserver()
    supervisor = OperationsSupervisor(
        _policy(),
        StateReader(error=RuntimeError("original-loop-error")),
        Executor(),
        AtomicDaemonStateStore(tmp_path),
        clock=lambda: NOW,
        state_observer=observer,
    )

    with pytest.raises(RuntimeError, match="original-loop-error"):
        supervisor.run(StopAfter(1))

    raw = (tmp_path / "health.json").read_text(encoding="utf-8")
    assert "private-observer-failure" not in raw
    assert observer.failure_calls == [NOW]


def test_state_store_rejects_relative_root_and_reparse_points(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ValueError, match="absolute"):
        AtomicDaemonStateStore(Path("relative-state"))

    original = supervisor_module._is_reparse_point
    monkeypatch.setattr(
        supervisor_module,
        "_is_reparse_point",
        lambda path: path == tmp_path or original(path),
    )
    with pytest.raises(ValueError, match="reparse"):
        AtomicDaemonStateStore(tmp_path)


def test_state_root_inspection_errors_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = Path.lstat

    def fail_selected(path: Path):
        if path == tmp_path:
            raise PermissionError("inspection denied")
        return original(path)

    monkeypatch.setattr(Path, "lstat", fail_selected)

    with pytest.raises(ValueError, match="inspect"):
        AtomicDaemonStateStore(tmp_path)


def test_cli_rejects_relative_state_root_before_mutex_creation() -> None:
    mutex_calls: list[str] = []

    with pytest.raises(ValueError, match="absolute"):
        run(
            [
                "--state-root",
                "relative-state",
                "--mode",
                "shadow",
                "--activation-receipt-id",
                "grant-1",
                "--start-nonce",
                "nonce-1",
            ],
            logon_sid_provider=lambda: "S-1-5-5-1-2",
            mutex_factory=lambda name: mutex_calls.append(name) or MutexSpy(True),
            supervisor_factory=lambda _args: SupervisorSpy(),
        )

    assert mutex_calls == []


def test_supervisor_is_independent_of_tui_gateway_lifetime(tmp_path: Path) -> None:
    gateway_closed = Event()
    gateway_closed.set()
    reader = StateReader()
    executor = Executor()
    supervisor = OperationsSupervisor(
        _policy(), reader, executor, AtomicDaemonStateStore(tmp_path), clock=lambda: NOW
    )

    supervisor.run(StopAfter(2))

    assert gateway_closed.is_set()
    assert reader.calls == 2
    assert len(executor.decisions) == 2


class MutexSpy:
    def __init__(self, acquired: bool) -> None:
        self.acquired = acquired
        self.released = False

    def acquire(self) -> bool:
        return self.acquired

    def release(self) -> None:
        self.released = True


class SupervisorSpy:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, stop_event) -> None:
        self.calls += 1
        stop_event.set()


def test_current_user_named_mutex_blocks_duplicate_daemon(tmp_path: Path) -> None:
    mutex = MutexSpy(acquired=False)
    supervisor = SupervisorSpy()
    names: list[str] = []

    exit_code = run(
        [
            "--state-root",
            str(tmp_path),
            "--mode",
            "shadow",
            "--activation-receipt-id",
            "grant-1",
            "--start-nonce",
            "nonce-1",
        ],
        logon_sid_provider=lambda: "S-1-5-5-1-2",
        mutex_factory=lambda name: names.append(name) or mutex,
        supervisor_factory=lambda _args: supervisor,
    )

    assert exit_code == 2
    assert supervisor.calls == 0
    assert names == [operations_mutex_name("S-1-5-5-1-2")]
    assert names[0].startswith("Local\\V20OperationsDaemon-")
    assert mutex.released is False


class PlatformPort:
    def approve_run(self, *args, **kwargs) -> PortResult:  # pragma: no cover
        raise AssertionError((args, kwargs))

    def reject_run(self, *args, **kwargs) -> PortResult:  # pragma: no cover
        raise AssertionError((args, kwargs))

    def enqueue(self, *args, **kwargs) -> PortResult:  # pragma: no cover
        raise AssertionError((args, kwargs))

    def recover(self, command_id: str, request: CommandRequest) -> str:
        return "unknown"


class MutableClock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


class RuntimePort:
    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self.calls: list[tuple[str, str]] = []
        self.effects: set[str] = set()
        self.raise_after_effect: set[str] = set()

    def available(self, command_type: str) -> CapabilityView:
        return CapabilityView(
            capability_id=command_type,
            state=CapabilityState.ENABLED if self.enabled else CapabilityState.DISABLED,
            reason=None if self.enabled else "Runtime start is not activated or authorized.",
        )

    def start(
        self, command_id: str, mode: str, activation_receipt_id: str | None
    ) -> RuntimeReceipt:
        del mode, activation_receipt_id
        self.calls.append(("start", command_id))
        self.effects.add(command_id)
        if command_id in self.raise_after_effect:
            raise RuntimeError("crash after effect")
        return RuntimeReceipt(
            command_id=command_id,
            accepted=True,
            operation="start",
            code="started",
            safe_message="Runtime started.",
            mode="shadow",
            activation_receipt_id="grant-1",
        )

    def stop_safe(self, command_id: str) -> RuntimeReceipt:
        return self._simple(command_id, "stop-safe")

    def stop_force(self, command_id: str) -> RuntimeReceipt:
        return self._simple(command_id, "stop-force")

    def prepare_shutdown(self, command_id: str) -> RuntimeReceipt:
        return self._simple(command_id, "prepare-shutdown", "SAFE TO SHUT DOWN")

    def recover(self, command_id: str, request: CommandRequest) -> str:
        del request
        return "completed" if command_id in self.effects else "not-started"

    def _simple(
        self, command_id: str, operation: str, message: str = "Completed."
    ) -> RuntimeReceipt:
        return RuntimeReceipt(
            command_id=command_id,
            accepted=True,
            operation=operation,
            code="completed",
            safe_message=message,
            mode=None,
            activation_receipt_id=None,
        )


class ServicePort:
    def available(self, command_type: str) -> CapabilityView:
        return CapabilityView(
            capability_id=command_type,
            state=CapabilityState.ENABLED,
            reason=None,
        )

    def pause(self, command_id: str, service_id: str) -> ServiceReceipt:
        return self._receipt(command_id, service_id, "pause")

    def restart(self, command_id: str, service_id: str) -> ServiceReceipt:
        return self._receipt(command_id, service_id, "restart")

    def recover(self, command_id: str, request: CommandRequest) -> str:
        del command_id, request
        return "not-started"

    @staticmethod
    def _receipt(command_id: str, service_id: str, operation: str) -> ServiceReceipt:
        return ServiceReceipt(
            command_id=command_id,
            service_id=service_id,
            accepted=True,
            operation=operation,
            code="completed",
            safe_message="Service action completed.",
        )


def _runtime_request(command_id: str) -> CommandRequest:
    return CommandRequest(
        command_id=command_id,
        command_type="runtime.start",
        reviewed_control_version=1,
        reviewed_control_hash=CONTROL_HASH,
        reason="Approved start.",
        confirmation=ConfirmationProof(first_confirmed=True),
        payload={"mode": "shadow", "activation_receipt_id": "grant-1"},
    )


def _context(request: CommandRequest) -> CommandContext:
    return CommandContext(
        operator_id="operator:windows",
        client_id="client:tui",
        authenticated=True,
        owns_control_lease=True,
        control_version=1,
        control_hash=CONTROL_HASH,
        capabilities=(
            CapabilityView(
                capability_id=request.command_type,
                state=CapabilityState.ENABLED,
                reason=None,
            ),
        ),
        prerequisites=EvaluatedPrerequisites(
            request_sha256=canonical_request_hash(request),
            complete=True,
            checks=(),
        ),
    )


def test_optional_operation_ports_default_disabled_and_recover_after_crash(
    tmp_path: Path,
) -> None:
    request = _runtime_request("cmd-runtime")
    with CommandRegistry(
        tmp_path / "disabled.sqlite3", PlatformPort(), clock=lambda: NOW
    ) as disabled:
        denied = disabled.execute(_context(request), request)
        assert denied.status is ReceiptStatus.REJECTED
        assert denied.code == "capability-disabled"

    clock = MutableClock()
    runtime = RuntimePort()
    runtime.raise_after_effect.add(request.command_id)
    with CommandRegistry(
        tmp_path / "enabled.sqlite3",
        PlatformPort(),
        runtime_port=runtime,
        service_port=ServicePort(),
        clock=clock,
        claim_lease=timedelta(seconds=1),
    ) as registry:
        with pytest.raises(RuntimeError, match="crash after effect"):
            registry.execute(_context(request), request)
        clock.now += timedelta(seconds=2)
        recovered = registry.recover_running(clock.now)

        assert recovered[0].status is ReceiptStatus.COMPLETED
        assert runtime.calls == [("start", request.command_id)]


def test_gateway_reports_injected_port_truth_even_without_platform_runtime(
    tmp_path: Path,
) -> None:
    runtime = RuntimePort(enabled=True)
    with CommandRegistry(
        tmp_path / "gateway.sqlite3",
        PlatformPort(),
        runtime_port=runtime,
        service_port=ServicePort(),
        clock=lambda: NOW,
    ) as registry:
        unavailable_runtime = SourceSample[PlatformRuntimeFacts](
            value=None,
            freshness=Freshness.UNAVAILABLE,
            observed_at_utc=None,
            source="native platform runtime",
            error="Runtime facts unavailable.",
        )
        capabilities = {
            row.capability_id: row
            for row in Gateway._command_capabilities(unavailable_runtime, registry)
        }

    assert capabilities["runtime.start"].state is CapabilityState.ENABLED
    assert capabilities["runtime.stop-safe"].state is CapabilityState.ENABLED
    assert capabilities["service.restart"].state is CapabilityState.ENABLED
    assert capabilities["approval.approve"].state is CapabilityState.DISABLED
