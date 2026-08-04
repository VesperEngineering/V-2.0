"""Fail-closed runtime and service command adapters for local operations."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from pathlib import Path
from threading import RLock
from typing import Literal, Protocol, Self, cast
from uuid import uuid4

from pydantic import TypeAdapter, model_validator

from vesper.platform.ops.activation import (
    ActivationCapability,
    ActivationGrant,
    OperationsActivationStore,
)
from vesper.platform.ops.supervisor import validate_state_root
from vesper.platform.tui.command_contracts import (
    CommandRequest,
    CommandType,
    RuntimeStartPayload,
    ServicePayload,
)
from vesper.platform.tui.command_ports import RecoveryStatus
from vesper.platform.tui.views import (
    CapabilityState,
    CapabilityView,
    NonEmptyStr,
    SafeId,
    StrictModel,
)


RuntimeOperation = Literal["start", "stop-safe", "stop-force", "prepare-shutdown"]
ServiceOperation = Literal["pause", "restart"]
_RUNTIME_COMMANDS = {
    "runtime.start",
    "runtime.stop-safe",
    "runtime.stop-force",
    "runtime.prepare-shutdown",
}
_SERVICE_COMMANDS = {"service.pause", "service.restart"}
_RUNTIME_NOT_AUTHORIZED = "Runtime start is not activated or authorized."
_RUNTIME_UNAVAILABLE = "The reviewed runtime launcher is unavailable."
_SERVICE_UNAVAILABLE = "No allowlisted healthy service adapter is available."
_SAFE_ID = TypeAdapter(SafeId)


class RuntimeReceipt(StrictModel):
    command_id: SafeId
    accepted: bool
    operation: RuntimeOperation
    code: SafeId
    safe_message: NonEmptyStr
    mode: Literal["shadow", "paper"] | None
    activation_receipt_id: SafeId | None

    @model_validator(mode="after")
    def require_start_binding(self) -> Self:
        if self.operation == "start" and self.mode is None:
            raise ValueError("runtime-receipt-start-binding")
        if self.operation == "start" and self.accepted and self.activation_receipt_id is None:
            raise ValueError("runtime-receipt-start-binding")
        if self.operation != "start" and (
            self.mode is not None or self.activation_receipt_id is not None
        ):
            raise ValueError("runtime-receipt-start-binding")
        return self

    @classmethod
    def rejected(
        cls,
        command_id: SafeId,
        operation: RuntimeOperation,
        code: SafeId,
        message: NonEmptyStr,
        *,
        mode: Literal["shadow", "paper"] | None = None,
        activation_receipt_id: SafeId | None = None,
    ) -> RuntimeReceipt:
        return cls(
            command_id=command_id,
            accepted=False,
            operation=operation,
            code=code,
            safe_message=message,
            mode=mode,
            activation_receipt_id=activation_receipt_id,
        )


class ServiceReceipt(StrictModel):
    command_id: SafeId
    service_id: SafeId
    accepted: bool
    operation: ServiceOperation
    code: SafeId
    safe_message: NonEmptyStr


class ServiceRecoveryReceipt(StrictModel):
    service_id: SafeId
    action: Literal["restarted", "alerted"]
    restart_attempted: bool
    alert_sent: bool
    code: SafeId
    safe_message: NonEmptyStr

    @model_validator(mode="after")
    def require_action_shape(self) -> Self:
        if self.action == "restarted" and (not self.restart_attempted or self.alert_sent):
            raise ValueError("service-recovery-action-shape")
        return self


class RuntimeLauncher(Protocol):
    def available(self) -> CapabilityView: ...

    def lookup_receipt(self, command_id: SafeId) -> RuntimeReceipt | None: ...

    def start_once(self, command_id: SafeId, argv: tuple[str, ...]) -> RuntimeReceipt: ...

    def stop_safe(self, command_id: SafeId) -> RuntimeReceipt: ...

    def stop_force(self, command_id: SafeId) -> RuntimeReceipt: ...

    def prepare_shutdown(self, command_id: SafeId) -> RuntimeReceipt: ...


class ServiceAdapter(Protocol):
    def available(self) -> CapabilityView: ...

    def lookup_receipt(self, command_id: SafeId) -> ServiceReceipt | None: ...

    def pause(self, command_id: SafeId) -> ServiceReceipt: ...

    def restart(self, command_id: SafeId) -> ServiceReceipt: ...


class AlertPort(Protocol):
    def alert(self, service_id: SafeId, message: NonEmptyStr) -> None: ...


class _RuntimeStartCall(StrictModel):
    command_id: SafeId
    mode: Literal["shadow", "paper"]
    activation_receipt_id: SafeId | None


class _ServiceCall(StrictModel):
    command_id: SafeId
    service_id: SafeId


def _strict_capability(value: object, expected_id: str) -> CapabilityView | None:
    if type(value) is not CapabilityView:
        return None
    try:
        capability = CapabilityView.model_validate(
            value.model_dump(mode="python", warnings=False),
            strict=True,
        )
    except Exception:
        return None
    if capability.capability_id != expected_id:
        return None
    return capability


class RuntimeAdapter:
    """Controller port that launches only an exactly authorized local daemon."""

    def __init__(
        self,
        activation_store: OperationsActivationStore,
        launcher: RuntimeLauncher,
        *,
        state_root: Path,
        nonce_factory: Callable[[], str] = lambda: uuid4().hex,
    ) -> None:
        if type(activation_store) is not OperationsActivationStore:
            raise TypeError("activation_store must be OperationsActivationStore")
        if not callable(nonce_factory):
            raise TypeError("nonce_factory must be callable")
        self._activation_store = activation_store
        self._launcher = launcher
        self._state_root = validate_state_root(state_root)
        self._nonce_factory = nonce_factory
        self._lock = RLock()

    def available(self, command_type: CommandType) -> CapabilityView:
        if command_type not in _RUNTIME_COMMANDS:
            raise ValueError("unsupported runtime command")
        if command_type == "runtime.start" and self._validated_start_grant() is None:
            return CapabilityView(
                capability_id=command_type,
                state=CapabilityState.DISABLED,
                reason=_RUNTIME_NOT_AUTHORIZED,
            )
        launcher = self._launcher_capability()
        if launcher is None or launcher.state is not CapabilityState.ENABLED:
            return CapabilityView(
                capability_id=command_type,
                state=CapabilityState.DISABLED,
                reason=(launcher.reason if launcher is not None else _RUNTIME_UNAVAILABLE),
            )
        return CapabilityView(
            capability_id=command_type,
            state=CapabilityState.ENABLED,
            reason=None,
        )

    def start(
        self,
        command_id: SafeId,
        mode: Literal["shadow", "paper"],
        activation_receipt_id: SafeId | None,
    ) -> RuntimeReceipt:
        with self._lock:
            call = _RuntimeStartCall.model_validate(
                {
                    "command_id": command_id,
                    "mode": mode,
                    "activation_receipt_id": activation_receipt_id,
                },
                strict=True,
            )
            grant = self._validated_start_grant()
            if grant is None or not grant.enabled or grant.receipt_id != call.activation_receipt_id:
                return RuntimeReceipt.rejected(
                    call.command_id,
                    "start",
                    "runtime-start-not-authorized",
                    _RUNTIME_NOT_AUTHORIZED,
                    mode=call.mode,
                    activation_receipt_id=call.activation_receipt_id,
                )
            capability = self.available("runtime.start")
            if capability.state is not CapabilityState.ENABLED:
                return RuntimeReceipt.rejected(
                    call.command_id,
                    "start",
                    "runtime-launcher-unavailable",
                    capability.reason or _RUNTIME_UNAVAILABLE,
                    mode=call.mode,
                    activation_receipt_id=call.activation_receipt_id,
                )
            existing = self._lookup_runtime_receipt(
                call.command_id,
                "start",
                mode=call.mode,
                activation_receipt_id=call.activation_receipt_id,
            )
            if existing is not None:
                return existing
            nonce = _SAFE_ID.validate_python(self._nonce_factory(), strict=True)
            argv = (
                "uv",
                "run",
                "--locked",
                "vesper-ops-daemon",
                "--state-root",
                str(self._state_root),
                "--mode",
                call.mode,
                "--activation-receipt-id",
                call.activation_receipt_id,
                "--start-nonce",
                nonce,
            )
            return self._validate_runtime_receipt(
                self._launcher.start_once(call.command_id, argv),
                call.command_id,
                "start",
                mode=call.mode,
                activation_receipt_id=call.activation_receipt_id,
            )

    def stop_safe(self, command_id: SafeId) -> RuntimeReceipt:
        return self._runtime_action(command_id, "stop-safe", self._launcher.stop_safe)

    def stop_force(self, command_id: SafeId) -> RuntimeReceipt:
        return self._runtime_action(command_id, "stop-force", self._launcher.stop_force)

    def prepare_shutdown(self, command_id: SafeId) -> RuntimeReceipt:
        receipt = self._runtime_action(
            command_id,
            "prepare-shutdown",
            self._launcher.prepare_shutdown,
        )
        if receipt.accepted and receipt.safe_message != "SAFE TO SHUT DOWN":
            raise ValueError("shutdown receipt did not confirm the checkpoint")
        return receipt

    def recover(self, command_id: str, request: CommandRequest) -> RecoveryStatus:
        if type(request) is not CommandRequest or command_id != request.command_id:
            return "unknown"
        try:
            request = CommandRequest.model_validate(
                request.model_dump(mode="python", warnings=False),
                strict=True,
            )
            operation = _runtime_operation(request.command_type)
            mode: Literal["shadow", "paper"] | None = None
            receipt_id: str | None = None
            if request.command_type == "runtime.start":
                payload = cast(RuntimeStartPayload, request.payload)
                mode = payload.mode
                receipt_id = payload.activation_receipt_id
            receipt = self._lookup_runtime_receipt(
                command_id,
                operation,
                mode=mode,
                activation_receipt_id=receipt_id,
            )
        except Exception:
            return "unknown"
        if receipt is None:
            return "not-started"
        return "completed" if receipt.accepted else "failed"

    def _runtime_action(
        self,
        command_id: SafeId,
        operation: RuntimeOperation,
        action: Callable[[SafeId], RuntimeReceipt],
    ) -> RuntimeReceipt:
        with self._lock:
            validated_id = _SAFE_ID.validate_python(command_id, strict=True)
            command_type = cast(CommandType, f"runtime.{operation}")
            capability = self.available(command_type)
            if capability.state is not CapabilityState.ENABLED:
                return RuntimeReceipt.rejected(
                    validated_id,
                    operation,
                    "runtime-launcher-unavailable",
                    capability.reason or _RUNTIME_UNAVAILABLE,
                )
            existing = self._lookup_runtime_receipt(validated_id, operation)
            if existing is not None:
                return existing
            return self._validate_runtime_receipt(
                action(validated_id),
                validated_id,
                operation,
            )

    def _validated_start_grant(self):
        try:
            grant = self._activation_store.validated_grant(ActivationCapability.RUNTIME_START)
            if type(grant) is not ActivationGrant:
                return None
            grant = ActivationGrant.model_validate(
                grant.model_dump(mode="python", warnings=False),
                strict=True,
            )
        except Exception:
            return None
        return grant if grant.enabled else None

    def _launcher_capability(self) -> CapabilityView | None:
        try:
            return _strict_capability(
                self._launcher.available(),
                "ops.runtime-launcher",
            )
        except Exception:
            return None

    def _lookup_runtime_receipt(
        self,
        command_id: str,
        operation: RuntimeOperation,
        *,
        mode: Literal["shadow", "paper"] | None = None,
        activation_receipt_id: str | None = None,
    ) -> RuntimeReceipt | None:
        receipt = self._launcher.lookup_receipt(command_id)
        if receipt is None:
            return None
        return self._validate_runtime_receipt(
            receipt,
            command_id,
            operation,
            mode=mode,
            activation_receipt_id=activation_receipt_id,
        )

    @staticmethod
    def _validate_runtime_receipt(
        receipt: object,
        command_id: str,
        operation: RuntimeOperation,
        *,
        mode: Literal["shadow", "paper"] | None = None,
        activation_receipt_id: str | None = None,
    ) -> RuntimeReceipt:
        if type(receipt) is not RuntimeReceipt:
            raise TypeError("runtime launcher must return RuntimeReceipt")
        validated = RuntimeReceipt.model_validate(
            receipt.model_dump(mode="python", warnings=False),
            strict=True,
        )
        expected = (command_id, operation, mode, activation_receipt_id)
        actual = (
            validated.command_id,
            validated.operation,
            validated.mode,
            validated.activation_receipt_id,
        )
        if actual != expected:
            raise ValueError("runtime receipt does not match the command")
        return validated


class ServiceSupervisor:
    """Allowlisted service commands plus one safe automatic restart attempt."""

    def __init__(
        self,
        adapters: Mapping[str, ServiceAdapter],
        *,
        alert_port: AlertPort | None = None,
    ) -> None:
        if not isinstance(adapters, Mapping):
            raise TypeError("adapters must be a mapping")
        validated: dict[str, ServiceAdapter] = {}
        for service_id, adapter in adapters.items():
            safe_id = _SAFE_ID.validate_python(service_id, strict=True)
            if safe_id in validated:
                raise ValueError("service adapter IDs must be unique")
            validated[safe_id] = adapter
        self._adapters = validated
        self._alert_port = alert_port
        self._restart_attempted: set[str] = set()
        self._lock = RLock()

    def available(self, command_type: CommandType) -> CapabilityView:
        if command_type not in _SERVICE_COMMANDS:
            raise ValueError("unsupported service command")
        enabled = any(
            self._healthy_adapter(service_id) is not None for service_id in self._adapters
        )
        return CapabilityView(
            capability_id=command_type,
            state=CapabilityState.ENABLED if enabled else CapabilityState.DISABLED,
            reason=None if enabled else _SERVICE_UNAVAILABLE,
        )

    def pause(self, command_id: SafeId, service_id: SafeId) -> ServiceReceipt:
        return self._service_action(command_id, service_id, "pause")

    def restart(self, command_id: SafeId, service_id: SafeId) -> ServiceReceipt:
        return self._service_action(command_id, service_id, "restart")

    def recover(self, command_id: str, request: CommandRequest) -> RecoveryStatus:
        if type(request) is not CommandRequest or command_id != request.command_id:
            return "unknown"
        try:
            request = CommandRequest.model_validate(
                request.model_dump(mode="python", warnings=False),
                strict=True,
            )
            if request.command_type not in _SERVICE_COMMANDS:
                return "unknown"
            payload = cast(ServicePayload, request.payload)
            operation: ServiceOperation = (
                "pause" if request.command_type == "service.pause" else "restart"
            )
            adapter = self._healthy_adapter(payload.service_id)
            if adapter is None:
                return "unknown"
            receipt = adapter.lookup_receipt(command_id)
            if receipt is None:
                return "not-started"
            validated = self._validate_service_receipt(
                receipt,
                command_id,
                payload.service_id,
                operation,
            )
        except Exception:
            return "unknown"
        return "completed" if validated.accepted else "failed"

    def handle_failure(self, service_id: SafeId) -> ServiceRecoveryReceipt:
        with self._lock:
            validated_id = _SAFE_ID.validate_python(service_id, strict=True)
            adapter = self._healthy_adapter(validated_id)
            attempted_now = False
            if adapter is not None and validated_id not in self._restart_attempted:
                self._restart_attempted.add(validated_id)
                attempted_now = True
                digest = hashlib.sha256(validated_id.encode("utf-8")).hexdigest()[:32]
                command_id = f"service-recovery:{digest}"
                try:
                    receipt = self._service_action(command_id, validated_id, "restart")
                except Exception:
                    receipt = None
                if receipt is not None and receipt.accepted:
                    return ServiceRecoveryReceipt(
                        service_id=validated_id,
                        action="restarted",
                        restart_attempted=True,
                        alert_sent=False,
                        code="safe-restart-completed",
                        safe_message="Service restarted once after a failure.",
                    )
            alert_sent = self._send_alert(validated_id)
            return ServiceRecoveryReceipt(
                service_id=validated_id,
                action="alerted",
                restart_attempted=attempted_now,
                alert_sent=alert_sent,
                code="operator-attention-required",
                safe_message="V20 needs attention",
            )

    def _service_action(
        self,
        command_id: SafeId,
        service_id: SafeId,
        operation: ServiceOperation,
    ) -> ServiceReceipt:
        with self._lock:
            call = _ServiceCall.model_validate(
                {"command_id": command_id, "service_id": service_id},
                strict=True,
            )
            adapter = self._healthy_adapter(call.service_id)
            if adapter is None:
                return ServiceReceipt(
                    command_id=call.command_id,
                    service_id=call.service_id,
                    accepted=False,
                    operation=operation,
                    code="service-adapter-unavailable",
                    safe_message="The service is not allowlisted or its adapter is unhealthy.",
                )
            existing = adapter.lookup_receipt(call.command_id)
            if existing is not None:
                return self._validate_service_receipt(
                    existing,
                    call.command_id,
                    call.service_id,
                    operation,
                )
            action = adapter.pause if operation == "pause" else adapter.restart
            return self._validate_service_receipt(
                action(call.command_id),
                call.command_id,
                call.service_id,
                operation,
            )

    def _healthy_adapter(self, service_id: str) -> ServiceAdapter | None:
        adapter = self._adapters.get(service_id)
        if adapter is None:
            return None
        try:
            capability = _strict_capability(adapter.available(), service_id)
        except Exception:
            return None
        if capability is None or capability.state is not CapabilityState.ENABLED:
            return None
        return adapter

    @staticmethod
    def _validate_service_receipt(
        receipt: object,
        command_id: str,
        service_id: str,
        operation: ServiceOperation,
    ) -> ServiceReceipt:
        if type(receipt) is not ServiceReceipt:
            raise TypeError("service adapter must return ServiceReceipt")
        validated = ServiceReceipt.model_validate(
            receipt.model_dump(mode="python", warnings=False),
            strict=True,
        )
        expected = (command_id, service_id, operation)
        actual = (
            validated.command_id,
            validated.service_id,
            validated.operation,
        )
        if actual != expected:
            raise ValueError("service receipt does not match the command")
        return validated

    def _send_alert(self, service_id: str) -> bool:
        if self._alert_port is None:
            return False
        try:
            self._alert_port.alert(service_id, "V20 needs attention")
        except Exception:
            return False
        return True


def _runtime_operation(command_type: CommandType) -> RuntimeOperation:
    operations: dict[str, RuntimeOperation] = {
        "runtime.start": "start",
        "runtime.stop-safe": "stop-safe",
        "runtime.stop-force": "stop-force",
        "runtime.prepare-shutdown": "prepare-shutdown",
    }
    try:
        return operations[command_type]
    except KeyError as exc:
        raise ValueError("request is not a runtime command") from exc
