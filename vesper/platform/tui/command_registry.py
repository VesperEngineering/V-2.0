"""Policy-first execution and recovery for reviewed TUI commands."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType
from typing import cast

from pydantic import TypeAdapter

from vesper.platform.contracts import AgentRole

from .command_contracts import (
    COMMAND_SPECS,
    MAX_COMMAND_PAYLOAD_BYTES,
    AgentEnqueuePayload,
    ApprovalPayload,
    BackupCreatePayload,
    BackupRestorePayload,
    CommandJsonValue,
    CommandReceipt,
    CommandRequest,
    CommandType,
    CompressMemoryPayload,
    NoteAddPayload,
    ReceiptStatus,
    RuntimeStartPayload,
    ServicePayload,
)
from .command_policy import (
    AuthorizationDecision,
    CommandContext,
    CommandPolicy,
    EvaluatedPrerequisites,
    canonical_request_hash,
)
from .compression import CompressionReceipt
from .command_ports import (
    BackupCommandPort,
    DISABLED_COMMAND_REASONS,
    MemoryCommandPort,
    PlatformCommandPort,
    PortResult,
    RuntimeCommandPort,
    ServiceCommandPort,
)
from .command_store import (
    CommandClaim,
    CommandStore,
    SafeRequestMetadata,
    canonical_request_sha256,
)
from .notes import NoteStore, NoteTarget, NoteVisibility
from .operator_decisions import OperatorDecisionStore
from .sqlite_ledger import LedgerClosedError, LedgerCorruptionError, TuiLedger
from .views import CapabilityState, CapabilityView, CommandSpecView, UtcDateTime


_HANDLER_KEYS: Mapping[CommandType, str] = MappingProxyType(
    {
        "note.add": "note.add",
        "approval.approve": "approval.approve",
        "approval.hold": "approval.hold",
        "approval.reject": "approval.reject",
        "agent.enqueue": "agent.enqueue",
        "memory.compress-now": "memory.compress-now",
        "service.pause": "service.pause",
        "service.restart": "service.restart",
        "runtime.start": "runtime.start",
        "runtime.stop-safe": "runtime.stop-safe",
        "runtime.stop-force": "runtime.stop-force",
        "runtime.prepare-shutdown": "runtime.prepare-shutdown",
        "backup.create": "backup.create",
        "backup.restore": "backup.restore",
    }
)
_EXTERNAL_HANDLERS = {
    "approval.approve",
    "approval.reject",
    "agent.enqueue",
    "service.pause",
    "service.restart",
    "runtime.start",
    "runtime.stop-safe",
    "runtime.stop-force",
    "runtime.prepare-shutdown",
    "backup.create",
    "backup.restore",
}
_RUNTIME_HANDLERS = frozenset(
    {
        "runtime.start",
        "runtime.stop-safe",
        "runtime.stop-force",
        "runtime.prepare-shutdown",
    }
)
_SERVICE_HANDLERS = frozenset({"service.pause", "service.restart"})
_BACKUP_HANDLERS = frozenset({"backup.create", "backup.restore"})
_RECOVERY_STATES = {"not-started", "completed", "failed", "unknown"}
_MANUAL_INTERVENTION_MESSAGE = "Downstream command state is unknown; inspect it before any retry."
_UTC = TypeAdapter(UtcDateTime)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sanitize_json_value(value: object) -> CommandJsonValue:
    if value is None or type(value) in {bool, str}:
        return cast(CommandJsonValue, value)
    if type(value) is int:
        if not -(2**63) <= value <= 2**64 - 1:
            raise ValueError("command result integer is outside the shared JSON range")
        return cast(CommandJsonValue, value)
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("command result floats must be finite")
        return cast(CommandJsonValue, value)
    if type(value) is list:
        return cast(CommandJsonValue, [_sanitize_json_value(child) for child in value])
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise TypeError("command result object keys must be strings")
        return cast(
            CommandJsonValue,
            {key: _sanitize_json_value(child) for key, child in value.items()},
        )
    raise TypeError("command result contains a non-JSON value")


def _sanitize_result(
    result: dict[str, object] | None,
) -> dict[str, CommandJsonValue] | None:
    if result is None:
        return None
    if type(result) is not dict:
        raise TypeError("port result must be a dictionary or None")
    sanitized = cast(dict[str, CommandJsonValue], _sanitize_json_value(result))
    encoded = json.dumps(
        sanitized,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > MAX_COMMAND_PAYLOAD_BYTES:
        raise ValueError("command result exceeds the bounded JSON size")
    return sanitized


class CommandRegistry:
    """Authorize, persist, execute, and recover reviewed command handlers."""

    def __init__(
        self,
        ledger: Path | TuiLedger,
        port: PlatformCommandPort,
        *,
        memory_port: MemoryCommandPort | None = None,
        runtime_port: RuntimeCommandPort | None = None,
        service_port: ServiceCommandPort | None = None,
        backup_port: BackupCommandPort | None = None,
        policy: CommandPolicy | None = None,
        specs: tuple[CommandSpecView, ...] = COMMAND_SPECS,
        clock: Callable[[], datetime] = _utc_now,
        worker_id: str = "worker:tui-command-registry",
        claim_lease: timedelta = timedelta(seconds=30),
    ) -> None:
        if isinstance(ledger, TuiLedger):
            self._ledger = ledger
            self._owns_ledger = False
        else:
            self._ledger = TuiLedger(Path(ledger))
            self._owns_ledger = True
        if type(specs) is not tuple or any(type(spec) is not CommandSpecView for spec in specs):
            raise TypeError("specs must be a tuple of CommandSpecView values")
        if len({spec.command_type for spec in specs}) != len(specs):
            raise ValueError("command specs must have unique command types")
        if type(claim_lease) is not timedelta or claim_lease <= timedelta(0):
            raise ValueError("claim lease must be a positive timedelta")
        self._port = port
        self._memory_port = memory_port
        self._runtime_port = runtime_port
        self._service_port = service_port
        self._backup_port = backup_port
        self._policy = CommandPolicy() if policy is None else policy
        if type(self._policy) is not CommandPolicy:
            raise TypeError("policy must be CommandPolicy")
        self._specs = MappingProxyType({spec.command_type: spec for spec in specs})
        self._clock = clock
        self._worker_id = worker_id
        self._claim_lease = claim_lease
        self._store = CommandStore(self._ledger)
        self._notes = NoteStore(self._ledger, clock=self._clock)
        self._decisions = OperatorDecisionStore(self._ledger)
        self._closed = False

    @property
    def ledger(self) -> TuiLedger:
        self._require_open()
        return self._ledger

    @property
    def specs(self) -> tuple[CommandSpecView, ...]:
        self._require_open()
        return tuple(self._specs.values())

    @property
    def enabled_command_types(self) -> tuple[CommandType, ...]:
        """Return handlers currently backed by a reviewed healthy adapter."""

        self._require_open()
        return tuple(
            command_type for command_type in self._specs if self._handler_enabled(command_type)
        )

    @property
    def command_capabilities(self) -> tuple[CapabilityView, ...]:
        """Return current adapter truth for every command in catalog order."""

        self._require_open()
        return tuple(self._handler_capability(command_type) for command_type in self._specs)

    def __enter__(self) -> CommandRegistry:
        self._require_open()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._notes.close()
        self._decisions.close()
        self._store.close()
        if self._owns_ledger:
            self._ledger.close()
        self._closed = True

    def _require_open(self) -> None:
        if self._closed:
            raise LedgerClosedError("command registry is closed")

    def execute(
        self,
        context: CommandContext,
        request: CommandRequest,
    ) -> CommandReceipt:
        self._require_open()
        if type(context) is not CommandContext:
            raise TypeError("context must be CommandContext")
        if type(request) is not CommandRequest:
            raise TypeError("request must be CommandRequest")
        context = CommandContext.model_validate(
            context.model_dump(mode="python", warnings=False),
            strict=True,
        )
        request = CommandRequest.model_validate(
            request.model_dump(mode="python", warnings=False),
            strict=True,
        )
        if request.command_type == "memory.compress-now":
            self._require_memory_agent(request)
        handler_key = _HANDLER_KEYS.get(request.command_type)
        if context.authenticated and context.owns_control_lease:
            reconnect_receipt = self._store.exact_operator_replay(
                request,
                operator_id=context.operator_id,
                accepted_handler_key=handler_key,
            )
            if reconnect_receipt is not None:
                return reconnect_receipt
        spec = self._specs.get(request.command_type)
        if spec is None:
            decision = AuthorizationDecision(
                allowed=False,
                code="unknown-command",
                safe_message="Command is not in the current catalog.",
            )
        else:
            decision = self._policy.authorize(context, request, spec)
        if decision.allowed and not self._handler_enabled(request.command_type):
            decision = AuthorizationDecision(
                allowed=False,
                code="capability-disabled",
                safe_message=DISABLED_COMMAND_REASONS[request.command_type],
            )
        now = self._now()
        if not decision.allowed:
            return self._store.reject(
                canonical_request_sha256(request),
                SafeRequestMetadata(
                    command_id=request.command_id,
                    command_type=request.command_type,
                    operator_id=context.operator_id,
                    client_id=context.client_id,
                    reviewed_control_version=request.reviewed_control_version,
                    reviewed_control_hash=request.reviewed_control_hash,
                ),
                decision,
                now,
            )
        handler_key = _HANDLER_KEYS[request.command_type]
        receipt = self._store.accept(request, context, handler_key, now)
        if receipt.status is not ReceiptStatus.ACCEPTED:
            return receipt
        claim = self._store.claim(
            request.command_id,
            self._worker_id,
            now,
            now + self._claim_lease,
        )
        if claim is None:
            current = self._store.get(request.command_id)
            if current is None:
                raise LedgerCorruptionError("accepted command disappeared before claim")
            return current
        return self._execute_claimed(request, context, claim)

    def recover_running(self, now_utc: datetime) -> tuple[CommandReceipt, ...]:
        self._require_open()
        now = _UTC.validate_python(now_utc, strict=True)
        recovered: list[CommandReceipt] = []
        for candidate in self._store.recoverable(now):
            accepted = self._store.get_accepted(candidate.command_id)
            if accepted is None:
                raise LedgerCorruptionError("recoverable command has no accepted request")
            request = accepted.request
            expected_handler = _HANDLER_KEYS.get(request.command_type)
            if expected_handler is None or accepted.handler_key != expected_handler:
                raise LedgerCorruptionError("recoverable command handler binding is invalid")
            context = self._recovery_context(accepted)
            if request.command_type in {"note.add", "approval.hold"}:
                claim = self._claim_for_recovery(
                    request.command_id,
                    max(now, self._now()),
                )
                if claim is None:
                    recovered.append(self._current_receipt(request.command_id))
                    continue
                recovered.append(self._execute_claimed(request, context, claim))
                continue
            if request.command_type == "memory.compress-now":
                recovered.append(
                    self._recover_memory_command(
                        request,
                        context,
                        max(now, self._now()),
                    )
                )
                continue
            if request.command_type not in _EXTERNAL_HANDLERS:
                raise LedgerCorruptionError("recoverable command has no reviewed handler")
            state = self._recover_external(request)
            if state not in _RECOVERY_STATES:
                raise ValueError("command recovery port returned an invalid state")
            claim = self._claim_for_recovery(
                request.command_id,
                max(now, self._now()),
            )
            if claim is None:
                recovered.append(self._current_receipt(request.command_id))
                continue
            if state == "not-started":
                recovered.append(self._execute_claimed(request, context, claim))
            elif state == "completed":
                recovered.append(
                    self._store.finish(
                        request.command_id,
                        claim.claim_token,
                        ReceiptStatus.COMPLETED,
                        None,
                        max(now, self._now()),
                    )
                )
            elif state == "failed":
                recovered.append(
                    self._store.finish(
                        request.command_id,
                        claim.claim_token,
                        ReceiptStatus.FAILED,
                        None,
                        max(now, self._now()),
                    )
                )
            else:
                recovered.append(
                    self._store.finish(
                        request.command_id,
                        claim.claim_token,
                        ReceiptStatus.FAILED,
                        None,
                        max(now, self._now()),
                        code="manual-intervention-required",
                        safe_message=_MANUAL_INTERVENTION_MESSAGE,
                    )
                )
        return tuple(recovered)

    def _claim_for_recovery(
        self,
        command_id: str,
        now: datetime,
    ) -> CommandClaim | None:
        return self._store.claim(
            command_id,
            self._worker_id,
            now,
            now + self._claim_lease,
        )

    def _recover_memory_command(
        self,
        request: CommandRequest,
        context: CommandContext,
        now: datetime,
    ) -> CommandReceipt:
        recovered_receipt: CompressionReceipt | None = None
        recovery_conflict = False
        memory_port = self._memory_port
        try:
            self._require_memory_agent(request)
        except ValueError:
            recovery_conflict = True
        if not recovery_conflict:
            if not self._memory_port_healthy() or memory_port is None:
                recovery_conflict = True
            else:
                try:
                    candidate = memory_port.lookup_receipt(request.command_id)
                    if candidate is not None:
                        recovered_receipt = self._validate_compression_receipt(
                            candidate,
                            request,
                        )
                except Exception:
                    recovery_conflict = True
        claim = self._claim_for_recovery(request.command_id, now)
        if claim is None:
            return self._current_receipt(request.command_id)
        if recovery_conflict:
            return self._store.finish(
                request.command_id,
                claim.claim_token,
                ReceiptStatus.FAILED,
                None,
                max(now, self._now()),
                code="manual-intervention-required",
                safe_message=_MANUAL_INTERVENTION_MESSAGE,
            )
        if recovered_receipt is None:
            return self._execute_claimed(request, context, claim)
        result = _sanitize_result(recovered_receipt.model_dump(mode="json"))
        return self._store.finish(
            request.command_id,
            claim.claim_token,
            ReceiptStatus.COMPLETED,
            result,
            max(now, self._now()),
            code="completed",
            safe_message="Context compression completed.",
        )

    def _execute_claimed(
        self,
        request: CommandRequest,
        context: CommandContext,
        claim: CommandClaim,
    ) -> CommandReceipt:
        if request.command_type == "note.add":
            payload = cast(NoteAddPayload, request.payload)
            with self._ledger.transaction() as connection:
                note = self._notes.add_for_command_in_transaction(
                    connection,
                    request.command_id,
                    NoteTarget(
                        target_type=payload.target_type,
                        target_id=payload.target_id,
                    ),
                    payload.body,
                    NoteVisibility(payload.visibility),
                    context.operator_id,
                )
                finished_at = self._now()
                return self._store.finish_in_transaction(
                    connection,
                    request.command_id,
                    claim.claim_token,
                    ReceiptStatus.COMPLETED,
                    {"note_id": note.note_id},
                    finished_at,
                )
        if request.command_type == "approval.hold":
            _ = cast(ApprovalPayload, request.payload)
            _, receipt = self._decisions.hold(
                request,
                context,
                claim.claim_token,
                clock=self._clock,
            )
            return receipt
        port_result = self._execute_external(request)
        if type(port_result) is not PortResult or type(port_result.ok) is not bool:
            raise TypeError("command port must return PortResult")
        result = _sanitize_result(port_result.result)
        status = ReceiptStatus.COMPLETED if port_result.ok else ReceiptStatus.FAILED
        return self._store.finish(
            request.command_id,
            claim.claim_token,
            status,
            result,
            self._now(),
            code=port_result.code,
            safe_message=port_result.safe_message,
        )

    def _execute_external(self, request: CommandRequest) -> PortResult:
        if request.command_type == "approval.approve":
            payload = cast(ApprovalPayload, request.payload)
            return self._port.approve_run(
                request.command_id,
                payload.run_id,
                payload.checkpoint_id,
                request.reason,
            )
        if request.command_type == "approval.reject":
            payload = cast(ApprovalPayload, request.payload)
            if request.reason is None:
                raise LedgerCorruptionError("accepted approval.reject has no reason")
            return self._port.reject_run(
                request.command_id,
                payload.run_id,
                payload.checkpoint_id,
                request.reason,
            )
        if request.command_type == "agent.enqueue":
            return self._port.enqueue(
                request.command_id,
                cast(AgentEnqueuePayload, request.payload),
            )
        if request.command_type == "memory.compress-now":
            if not self._memory_port_healthy():
                return PortResult(
                    ok=False,
                    code="capability-disabled",
                    safe_message=DISABLED_COMMAND_REASONS["memory.compress-now"],
                )
            payload = cast(CompressMemoryPayload, request.payload)
            memory_port = self._memory_port
            if memory_port is None:
                raise LedgerCorruptionError("healthy memory port disappeared")
            receipt = self._validate_compression_receipt(
                memory_port.compress_now(request.command_id, payload.agent_id),
                request,
            )
            return PortResult(
                ok=True,
                code="completed",
                safe_message="Context compression completed.",
                result=receipt.model_dump(mode="json"),
            )
        if request.command_type in _RUNTIME_HANDLERS:
            runtime_port = self._runtime_port
            if runtime_port is None:
                raise LedgerCorruptionError("enabled runtime port disappeared")
            if request.command_type == "runtime.start":
                payload = cast(RuntimeStartPayload, request.payload)
                runtime_receipt = runtime_port.start(
                    request.command_id,
                    payload.mode,
                    payload.activation_receipt_id,
                )
            elif request.command_type == "runtime.stop-safe":
                runtime_receipt = runtime_port.stop_safe(request.command_id)
            elif request.command_type == "runtime.stop-force":
                runtime_receipt = runtime_port.stop_force(request.command_id)
            else:
                runtime_receipt = runtime_port.prepare_shutdown(request.command_id)
            return self._runtime_result(runtime_receipt, request)
        if request.command_type in _SERVICE_HANDLERS:
            service_port = self._service_port
            if service_port is None:
                raise LedgerCorruptionError("enabled service port disappeared")
            payload = cast(ServicePayload, request.payload)
            service_receipt = (
                service_port.pause(request.command_id, payload.service_id)
                if request.command_type == "service.pause"
                else service_port.restart(request.command_id, payload.service_id)
            )
            return self._service_result(service_receipt, request)
        if request.command_type in _BACKUP_HANDLERS:
            backup_port = self._backup_port
            if backup_port is None:
                raise LedgerCorruptionError("enabled backup port disappeared")
            if request.command_type == "backup.create":
                payload = cast(BackupCreatePayload, request.payload)
                backup_receipt = backup_port.create(
                    request.command_id,
                    Path(payload.destination),
                )
            else:
                from .backup import RestoreConfirmation

                payload = cast(BackupRestorePayload, request.payload)
                confirmation = request.confirmation
                if confirmation is None:
                    raise LedgerCorruptionError("accepted backup.restore has no confirmation")
                backup_receipt = backup_port.restore(
                    request.command_id,
                    Path(payload.archive),
                    payload.preview_hash,
                    payload.safety_backup_receipt_id,
                    RestoreConfirmation(
                        preview_hash=payload.preview_hash,
                        safety_backup_receipt_id=payload.safety_backup_receipt_id,
                        first_confirmed=confirmation.first_confirmed,
                        second_confirmed=confirmation.second_confirmed,
                    ),
                )
            return self._backup_result(backup_receipt, request)
        raise LedgerCorruptionError("claimed command has no reviewed external handler")

    def _recover_external(self, request: CommandRequest) -> str:
        if request.command_type in _RUNTIME_HANDLERS:
            port = self._runtime_port
        elif request.command_type in _SERVICE_HANDLERS:
            port = self._service_port
        elif request.command_type in _BACKUP_HANDLERS:
            port = self._backup_port
        else:
            port = self._port
        if port is None:
            return "unknown"
        try:
            return port.recover(request.command_id, request)
        except Exception:
            return "unknown"

    @staticmethod
    def _runtime_result(receipt: object, request: CommandRequest) -> PortResult:
        from vesper.platform.ops.services import RuntimeReceipt

        if type(receipt) is not RuntimeReceipt:
            raise TypeError("runtime port must return RuntimeReceipt")
        validated = RuntimeReceipt.model_validate(
            receipt.model_dump(mode="python", warnings=False),
            strict=True,
        )
        operations = {
            "runtime.start": "start",
            "runtime.stop-safe": "stop-safe",
            "runtime.stop-force": "stop-force",
            "runtime.prepare-shutdown": "prepare-shutdown",
        }
        payload = cast(RuntimeStartPayload, request.payload)
        expected = (
            request.command_id,
            operations[request.command_type],
            payload.mode if request.command_type == "runtime.start" else None,
            (payload.activation_receipt_id if request.command_type == "runtime.start" else None),
        )
        actual = (
            validated.command_id,
            validated.operation,
            validated.mode,
            validated.activation_receipt_id,
        )
        if actual != expected:
            raise ValueError("runtime receipt does not match the command")
        return PortResult(
            ok=validated.accepted,
            code=validated.code,
            safe_message=validated.safe_message,
            result=validated.model_dump(mode="json"),
        )

    @staticmethod
    def _service_result(receipt: object, request: CommandRequest) -> PortResult:
        from vesper.platform.ops.services import ServiceReceipt

        if type(receipt) is not ServiceReceipt:
            raise TypeError("service port must return ServiceReceipt")
        validated = ServiceReceipt.model_validate(
            receipt.model_dump(mode="python", warnings=False),
            strict=True,
        )
        payload = cast(ServicePayload, request.payload)
        expected = (
            request.command_id,
            payload.service_id,
            "pause" if request.command_type == "service.pause" else "restart",
        )
        actual = (
            validated.command_id,
            validated.service_id,
            validated.operation,
        )
        if actual != expected:
            raise ValueError("service receipt does not match the command")
        return PortResult(
            ok=validated.accepted,
            code=validated.code,
            safe_message=validated.safe_message,
            result=validated.model_dump(mode="json"),
        )

    @staticmethod
    def _backup_result(receipt: object, request: CommandRequest) -> PortResult:
        from .backup import BackupManifest, RestoreReceipt

        if request.command_type == "backup.create":
            if type(receipt) is not BackupManifest:
                raise TypeError("backup port must return BackupManifest")
            validated = BackupManifest.model_validate(
                receipt.model_dump(mode="python", warnings=False),
                strict=True,
            )
            payload = cast(BackupCreatePayload, request.payload)
            if Path(validated.destination) != Path(payload.destination):
                raise ValueError("backup manifest does not match the command")
            return PortResult(
                ok=True,
                code="completed",
                safe_message="Encrypted backup created.",
                result=validated.model_dump(mode="json"),
            )
        if type(receipt) is not RestoreReceipt:
            raise TypeError("backup port must return RestoreReceipt")
        validated_restore = RestoreReceipt.model_validate(
            receipt.model_dump(mode="python", warnings=False),
            strict=True,
        )
        payload = cast(BackupRestorePayload, request.payload)
        if validated_restore.preview_hash != payload.preview_hash or (
            validated_restore.accepted
            and validated_restore.safety_backup_receipt_id != payload.safety_backup_receipt_id
        ):
            raise ValueError("restore receipt does not match the command")
        return PortResult(
            ok=validated_restore.accepted,
            code="completed" if validated_restore.accepted else "restore-rejected",
            safe_message=validated_restore.reason,
            result=validated_restore.model_dump(mode="json"),
        )

    @staticmethod
    def _require_memory_agent(request: CommandRequest) -> str:
        payload = cast(CompressMemoryPayload, request.payload)
        try:
            return AgentRole(payload.agent_id).value
        except ValueError as exc:
            raise ValueError("agent_id must name an approved V20 agent") from exc

    @staticmethod
    def _validate_compression_receipt(
        receipt: object,
        request: CommandRequest,
    ) -> CompressionReceipt:
        if type(receipt) is not CompressionReceipt:
            raise TypeError("memory port must return CompressionReceipt")
        validated = CompressionReceipt.model_validate(
            receipt.model_dump(mode="python"),
            strict=True,
        )
        payload = cast(CompressMemoryPayload, request.payload)
        if validated.command_id != request.command_id or validated.agent_id != payload.agent_id:
            raise ValueError("memory port receipt does not match the command")
        return validated

    def _handler_enabled(self, command_type: CommandType) -> bool:
        return self._handler_capability(command_type).state is CapabilityState.ENABLED

    def _handler_capability(self, command_type: CommandType) -> CapabilityView:
        if command_type == "memory.compress-now":
            enabled = self._memory_port_healthy()
            return CapabilityView(
                capability_id=command_type,
                state=CapabilityState.ENABLED if enabled else CapabilityState.DISABLED,
                reason=None if enabled else DISABLED_COMMAND_REASONS[command_type],
            )
        if command_type in _RUNTIME_HANDLERS:
            return self._optional_port_capability(command_type, self._runtime_port)
        if command_type in _SERVICE_HANDLERS:
            return self._optional_port_capability(command_type, self._service_port)
        if command_type in _BACKUP_HANDLERS:
            return self._optional_port_capability(command_type, self._backup_port)
        enabled = command_type in _HANDLER_KEYS
        return CapabilityView(
            capability_id=command_type,
            state=CapabilityState.ENABLED if enabled else CapabilityState.DISABLED,
            reason=None if enabled else DISABLED_COMMAND_REASONS[command_type],
        )

    @staticmethod
    def _optional_port_capability(command_type: CommandType, port: object) -> CapabilityView:
        if port is None:
            return CapabilityView(
                capability_id=command_type,
                state=CapabilityState.DISABLED,
                reason=DISABLED_COMMAND_REASONS[command_type],
            )
        try:
            available = getattr(port, "available")
            candidate = available(command_type)
            if type(candidate) is not CapabilityView:
                raise TypeError("port capability must be CapabilityView")
            capability = CapabilityView.model_validate(
                candidate.model_dump(mode="python", warnings=False),
                strict=True,
            )
            if capability.capability_id != command_type:
                raise ValueError("port capability ID does not match command")
            return capability
        except Exception:
            return CapabilityView(
                capability_id=command_type,
                state=CapabilityState.DISABLED,
                reason=DISABLED_COMMAND_REASONS[command_type],
            )

    def _memory_port_healthy(self) -> bool:
        if self._memory_port is None:
            return False
        try:
            healthy = self._memory_port.healthy
            compress_now = getattr(self._memory_port, "compress_now", None)
            lookup_receipt = getattr(self._memory_port, "lookup_receipt", None)
        except Exception:
            return False
        return (
            type(healthy) is bool
            and healthy
            and callable(compress_now)
            and callable(lookup_receipt)
        )

    def _recovery_context(self, accepted) -> CommandContext:
        request = accepted.request
        return CommandContext(
            operator_id=accepted.operator_id,
            client_id=accepted.client_id,
            authenticated=True,
            owns_control_lease=True,
            control_version=request.reviewed_control_version,
            control_hash=request.reviewed_control_hash,
            capabilities=(),
            prerequisites=EvaluatedPrerequisites(
                request_sha256=canonical_request_hash(request),
                complete=True,
                checks=(),
            ),
        )

    def _current_receipt(self, command_id: str) -> CommandReceipt:
        receipt = self._store.get(command_id)
        if receipt is None:
            raise LedgerCorruptionError("command disappeared during recovery")
        return receipt

    def _now(self) -> datetime:
        return _UTC.validate_python(self._clock(), strict=True)
