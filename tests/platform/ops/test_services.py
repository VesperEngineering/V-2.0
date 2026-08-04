from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from vesper.platform.ops.activation import (
    ActivationAuthorityError,
    ActivationCapability,
    ActivationGrant,
    OperationsActivation,
    OperationsActivationStore,
)
from vesper.platform.ops.services import (
    RuntimeAdapter,
    RuntimeReceipt,
    ServiceReceipt,
    ServiceSupervisor,
)
from vesper.platform.tui.command_contracts import CommandRequest
from vesper.platform.tui.views import CapabilityState, CapabilityView


class ReceiptAuthority:
    def __init__(self, receipt_id: str | None) -> None:
        self.receipt_id = receipt_id

    def require(self, capability: ActivationCapability, receipt_id: str) -> None:
        if capability is not ActivationCapability.RUNTIME_START or receipt_id != self.receipt_id:
            raise ActivationAuthorityError("activation receipt is unavailable or mismatched")


def _activation_store(
    *, enabled: bool = False, receipt_id: str | None = None, authority: str | None = None
) -> OperationsActivationStore:
    activation = OperationsActivation(
        runtime_start=ActivationGrant(enabled=enabled, receipt_id=receipt_id)
    )
    return OperationsActivationStore(activation, ReceiptAuthority(authority))


class FakeLauncher:
    def __init__(self, *, healthy: bool = True) -> None:
        self.healthy = healthy
        self.calls: list[tuple[str, object]] = []
        self.receipts: dict[str, RuntimeReceipt] = {}
        self.raise_after_effect: set[str] = set()
        self.return_invalid_copy = False

    def available(self) -> CapabilityView:
        self.calls.append(("available", None))
        return CapabilityView(
            capability_id="ops.runtime-launcher",
            state=CapabilityState.ENABLED if self.healthy else CapabilityState.DISABLED,
            reason=None if self.healthy else "Runtime launcher is unhealthy.",
        )

    def lookup_receipt(self, command_id: str) -> RuntimeReceipt | None:
        self.calls.append(("lookup", command_id))
        return self.receipts.get(command_id)

    def start_once(self, command_id: str, argv: tuple[str, ...]) -> RuntimeReceipt:
        self.calls.append(("start", argv))
        receipt = RuntimeReceipt(
            command_id=command_id,
            accepted=True,
            operation="start",
            code="started",
            safe_message="Runtime started.",
            mode=argv[argv.index("--mode") + 1],
            activation_receipt_id=argv[argv.index("--activation-receipt-id") + 1],
        )
        self.receipts[command_id] = receipt
        if command_id in self.raise_after_effect:
            raise RuntimeError("crash after launch")
        if self.return_invalid_copy:
            return receipt.model_copy(update={"accepted": "yes"})
        return receipt

    def stop_safe(self, command_id: str) -> RuntimeReceipt:
        return self._record(command_id, "stop-safe", "stopped-safe", "Runtime stopped safely.")

    def stop_force(self, command_id: str) -> RuntimeReceipt:
        return self._record(command_id, "stop-force", "stopped-force", "Runtime force-stopped.")

    def prepare_shutdown(self, command_id: str) -> RuntimeReceipt:
        self.calls.append(("checkpoint", command_id))
        return self._record(command_id, "prepare-shutdown", "prepared", "SAFE TO SHUT DOWN")

    def _record(self, command_id: str, operation: str, code: str, message: str) -> RuntimeReceipt:
        self.calls.append((operation, command_id))
        receipt = RuntimeReceipt(
            command_id=command_id,
            accepted=True,
            operation=operation,
            code=code,
            safe_message=message,
            mode=None,
            activation_receipt_id=None,
        )
        self.receipts[command_id] = receipt
        return receipt


def test_runtime_start_requires_exact_authority_before_launcher_probe(tmp_path: Path) -> None:
    launcher = FakeLauncher()
    disabled = RuntimeAdapter(_activation_store(), launcher, state_root=tmp_path)

    result = disabled.start("cmd-disabled", "shadow", None)

    assert result.accepted is False
    assert result.code == "runtime-start-not-authorized"
    assert launcher.calls == []

    mismatched = RuntimeAdapter(
        _activation_store(enabled=True, receipt_id="grant-1", authority="grant-1"),
        launcher,
        state_root=tmp_path,
    )
    result = mismatched.start("cmd-mismatch", "paper", "wrong")

    assert result.accepted is False
    assert launcher.calls == []

    unavailable = RuntimeAdapter(
        _activation_store(enabled=True, receipt_id="grant-1", authority="other"),
        launcher,
        state_root=tmp_path,
    )
    result = unavailable.start("cmd-unproven", "shadow", "grant-1")

    assert result.accepted is False
    assert launcher.calls == []


def test_runtime_adapter_rejects_relative_and_filesystem_root_state_paths() -> None:
    launcher = FakeLauncher()

    with pytest.raises(ValueError, match="absolute"):
        RuntimeAdapter(_activation_store(), launcher, state_root=Path("relative-state"))
    with pytest.raises(ValueError, match="filesystem root"):
        RuntimeAdapter(_activation_store(), launcher, state_root=Path(Path.cwd().anchor))

    assert launcher.calls == []


def test_runtime_start_uses_one_direct_argv_and_replays_once(tmp_path: Path) -> None:
    launcher = FakeLauncher()
    adapter = RuntimeAdapter(
        _activation_store(enabled=True, receipt_id="grant-1", authority="grant-1"),
        launcher,
        state_root=tmp_path,
        nonce_factory=lambda: "nonce-1",
    )

    first = adapter.start("cmd-start", "paper", "grant-1")
    second = adapter.start("cmd-start", "paper", "grant-1")

    assert first == second
    starts = [value for name, value in launcher.calls if name == "start"]
    assert starts == [
        (
            "uv",
            "run",
            "--locked",
            "vesper-ops-daemon",
            "--state-root",
            str(tmp_path.resolve()),
            "--mode",
            "paper",
            "--activation-receipt-id",
            "grant-1",
            "--start-nonce",
            "nonce-1",
        )
    ]


def test_runtime_recovery_finds_effect_after_crash_without_second_launch(tmp_path: Path) -> None:
    launcher = FakeLauncher()
    launcher.raise_after_effect.add("cmd-crash")
    adapter = RuntimeAdapter(
        _activation_store(enabled=True, receipt_id="grant-1", authority="grant-1"),
        launcher,
        state_root=tmp_path,
        nonce_factory=lambda: "nonce-1",
    )

    with pytest.raises(RuntimeError, match="crash after launch"):
        adapter.start("cmd-crash", "shadow", "grant-1")

    request = CommandRequest.model_validate(
        {
            "command_id": "cmd-crash",
            "command_type": "runtime.start",
            "reviewed_control_version": 1,
            "reviewed_control_hash": "a" * 64,
            "reason": "Approved start.",
            "confirmation": {"first_confirmed": True},
            "payload": {"mode": "shadow", "activation_receipt_id": "grant-1"},
        },
        strict=True,
    )

    assert adapter.recover("cmd-crash", request) == "completed"
    assert len([call for call in launcher.calls if call[0] == "start"]) == 1


def test_runtime_adapter_revalidates_model_copy_receipts(tmp_path: Path) -> None:
    launcher = FakeLauncher()
    launcher.return_invalid_copy = True
    adapter = RuntimeAdapter(
        _activation_store(enabled=True, receipt_id="grant-1", authority="grant-1"),
        launcher,
        state_root=tmp_path,
        nonce_factory=lambda: "nonce-1",
    )

    with pytest.raises(ValidationError):
        adapter.start("cmd-invalid", "shadow", "grant-1")


def test_runtime_stop_and_shutdown_are_healthy_idempotent_checkpointed_actions(
    tmp_path: Path,
) -> None:
    launcher = FakeLauncher()
    adapter = RuntimeAdapter(_activation_store(), launcher, state_root=tmp_path)

    safe = adapter.stop_safe("cmd-safe")
    force = adapter.stop_force("cmd-force")
    prepared = adapter.prepare_shutdown("cmd-prepare")
    replay = adapter.prepare_shutdown("cmd-prepare")

    assert safe.code == "stopped-safe"
    assert force.code == "stopped-force"
    assert prepared.safe_message == "SAFE TO SHUT DOWN"
    assert replay == prepared
    assert len([call for call in launcher.calls if call[0] == "checkpoint"]) == 1


class FakeServiceAdapter:
    def __init__(self, service_id: str, *, healthy: bool = True, restart_ok: bool = True) -> None:
        self.service_id = service_id
        self.healthy = healthy
        self.restart_ok = restart_ok
        self.calls: list[tuple[str, str]] = []
        self.receipts: dict[str, ServiceReceipt] = {}

    def available(self) -> CapabilityView:
        return CapabilityView(
            capability_id=self.service_id,
            state=CapabilityState.ENABLED if self.healthy else CapabilityState.DISABLED,
            reason=None if self.healthy else "Service adapter is unhealthy.",
        )

    def lookup_receipt(self, command_id: str) -> ServiceReceipt | None:
        return self.receipts.get(command_id)

    def pause(self, command_id: str) -> ServiceReceipt:
        return self._record(command_id, "pause", True)

    def restart(self, command_id: str) -> ServiceReceipt:
        return self._record(command_id, "restart", self.restart_ok)

    def _record(self, command_id: str, operation: str, accepted: bool) -> ServiceReceipt:
        self.calls.append((operation, command_id))
        receipt = ServiceReceipt(
            command_id=command_id,
            service_id=self.service_id,
            accepted=accepted,
            operation=operation,
            code="completed" if accepted else "service-action-failed",
            safe_message="Service action completed." if accepted else "Service action failed.",
        )
        self.receipts[command_id] = receipt
        return receipt


class AlertSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def alert(self, service_id: str, message: str) -> None:
        self.calls.append((service_id, message))


def test_service_commands_require_an_allowlisted_healthy_adapter() -> None:
    healthy = FakeServiceAdapter("service:qwen")
    unhealthy = FakeServiceAdapter("service:data", healthy=False)
    supervisor = ServiceSupervisor(
        {"service:qwen": healthy, "service:data": unhealthy},
        alert_port=AlertSpy(),
    )

    unknown = supervisor.pause("cmd-unknown", "service:other")
    blocked = supervisor.restart("cmd-unhealthy", "service:data")
    completed = supervisor.restart("cmd-qwen", "service:qwen")
    replay = supervisor.restart("cmd-qwen", "service:qwen")

    assert unknown.accepted is False
    assert blocked.accepted is False
    assert unhealthy.calls == []
    assert completed.accepted is True
    assert replay == completed
    assert healthy.calls == [("restart", "cmd-qwen")]


def test_service_failure_restarts_once_then_alerts() -> None:
    service = FakeServiceAdapter("service:qwen")
    alerts = AlertSpy()
    supervisor = ServiceSupervisor({"service:qwen": service}, alert_port=alerts)

    first = supervisor.handle_failure("service:qwen")
    second = supervisor.handle_failure("service:qwen")

    assert first.action == "restarted"
    assert first.restart_attempted is True
    assert second.action == "alerted"
    assert second.restart_attempted is False
    assert service.calls == [("restart", service.calls[0][1])]
    assert alerts.calls == [("service:qwen", "V20 needs attention")]
