"""Command-ID-bound ports for the small set of reviewed TUI effects."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Callable, Literal, Mapping, Protocol

from vesper.platform.agent_profiles import AUTONOMOUS_AGENT_ROLES
from vesper.platform.contracts import ApprovalDecision, AgentRole
from vesper.platform.service import LocalPlatformService, SpecialistRuntimeUnavailable
from vesper.platform.tui.command_contracts import (
    AgentEnqueuePayload,
    ApprovalPayload,
    CommandRequest,
    CommandType,
    ConfirmationProof,
    GitRevision,
)
from vesper.platform.tui.compression import CompressionReceipt
from vesper.platform.tui.views import CapabilityView, SafeId

if TYPE_CHECKING:
    from vesper.platform.ops.services import RuntimeReceipt, ServiceReceipt
    from vesper.platform.tui.backup import BackupManifest, RestoreConfirmation, RestoreReceipt
    from vesper.platform.tui.git_port import GitReceipt


RecoveryStatus = Literal["not-started", "completed", "failed", "unknown"]
DEFAULT_APPROVAL_REASON = "Approved through V20 TUI."

DISABLED_COMMAND_REASONS: Mapping[str, str] = MappingProxyType(
    {
        "alert.dismiss": "No controller-owned alert dismissal store is configured.",
        "approval.rework": "No reviewed approval rework queue adapter is configured.",
        "agent.send-message": "No controller-owned agent message port is configured.",
        "agent.pause": "No controller-owned pause port is configured.",
        "agent.stop": "The selected work item has no reviewed stop adapter.",
        "agent.retry": "No controller-owned retry port is configured.",
        "agent.set-priority": "No controller-owned priority port is configured.",
        "risk.propose-limit": "No controller-owned risk settings port is configured.",
        "trading.pause": "No controller-owned trading control port is configured.",
        "trading.emergency-stop": "No controller-owned trading control port is configured.",
        "service.pause": "No reviewed service supervisor is configured.",
        "service.restart": "No reviewed service supervisor is configured.",
        "runtime.start": "No reviewed runtime manager is configured.",
        "runtime.stop-safe": "No reviewed runtime manager is configured.",
        "runtime.stop-force": "No reviewed runtime manager is configured.",
        "runtime.prepare-shutdown": "No reviewed runtime manager is configured.",
        "mode.switch": "No reviewed runtime mode manager is configured.",
        "mode.leave-live": "No reviewed runtime mode manager is configured.",
        "mode.enable-live": "Live broker activation is not configured or authorized.",
        "model.request-promotion": "No reviewed model promotion port is configured.",
        "model.request-rollback": "No reviewed model rollback port is configured.",
        "memory.compress-now": "No controller-owned context compression port is configured.",
        "backup.create": "No controller-owned backup command adapter is configured.",
        "backup.restore": "No controller-owned backup command adapter is configured.",
        "source-control.push": "No reviewed source-control push adapter is configured.",
    }
)


def _deterministic_id(prefix: str, source_id: str) -> str:
    return f"{prefix}:{hashlib.sha256(source_id.encode('utf-8')).hexdigest()}"


def deterministic_approval_id(command_id: str) -> str:
    return _deterministic_id("tui-approval", command_id)


def deterministic_work_id(command_id: str) -> str:
    return _deterministic_id("tui-work", command_id)


def stable_session_id(agent_id: str) -> str:
    return _deterministic_id("tui-session", agent_id)


@dataclass(frozen=True, slots=True)
class PortResult:
    ok: bool
    code: str
    safe_message: str
    result: dict[str, object] | None = None


class RecoverableCommandPort(Protocol):
    def recover(self, command_id: str, request: CommandRequest) -> RecoveryStatus: ...


class PlatformCommandPort(RecoverableCommandPort, Protocol):
    def approve_run(
        self,
        command_id: str,
        run_id: str,
        checkpoint_id: str,
        reason: str | None = None,
    ) -> PortResult: ...

    def reject_run(
        self,
        command_id: str,
        run_id: str,
        checkpoint_id: str,
        reason: str,
    ) -> PortResult: ...

    def enqueue(self, command_id: str, payload: AgentEnqueuePayload) -> PortResult: ...


class MemoryCommandPort(Protocol):
    """Injected context-compression adapter; absent and unhealthy mean disabled."""

    @property
    def healthy(self) -> bool: ...

    def compress_now(
        self,
        command_id: SafeId,
        agent_id: SafeId,
    ) -> CompressionReceipt: ...

    def lookup_receipt(
        self,
        command_id: SafeId,
    ) -> CompressionReceipt | None: ...


class RuntimeCommandPort(Protocol):
    """Optional reviewed runtime lifecycle adapter."""

    def available(self, command_type: CommandType) -> CapabilityView: ...

    def start(
        self,
        command_id: SafeId,
        mode: Literal["shadow", "paper"],
        activation_receipt_id: SafeId | None,
    ) -> RuntimeReceipt: ...

    def stop_safe(self, command_id: SafeId) -> RuntimeReceipt: ...

    def stop_force(self, command_id: SafeId) -> RuntimeReceipt: ...

    def prepare_shutdown(self, command_id: SafeId) -> RuntimeReceipt: ...

    def recover(self, command_id: str, request: CommandRequest) -> RecoveryStatus: ...


class ServiceCommandPort(Protocol):
    """Optional allowlisted service lifecycle adapter."""

    def available(self, command_type: CommandType) -> CapabilityView: ...

    def pause(self, command_id: SafeId, service_id: SafeId) -> ServiceReceipt: ...

    def restart(self, command_id: SafeId, service_id: SafeId) -> ServiceReceipt: ...

    def recover(self, command_id: str, request: CommandRequest) -> RecoveryStatus: ...


class BackupCommandPort(Protocol):
    """Optional current-user encrypted backup adapter."""

    def available(self, command_type: CommandType) -> CapabilityView: ...

    def create(self, command_id: SafeId, destination: Path) -> BackupManifest: ...

    def restore(
        self,
        command_id: SafeId,
        archive: Path,
        preview_hash: str,
        safety_backup_receipt_id: SafeId,
        confirmation: RestoreConfirmation,
    ) -> RestoreReceipt: ...

    def recover(self, command_id: str, request: CommandRequest) -> RecoveryStatus: ...


class SourceControlCommandPort(Protocol):
    """Optional manual push adapter; never used by automatic maintenance."""

    def available(self, command_type: CommandType) -> CapabilityView: ...

    def push(
        self,
        command_id: SafeId,
        expected_revision: GitRevision,
        confirmation: ConfirmationProof,
    ) -> GitReceipt: ...

    def recover(self, command_id: str, request: CommandRequest) -> RecoveryStatus: ...


class LocalPlatformCommandPort:
    def __init__(
        self,
        service: LocalPlatformService,
        *,
        operator_id: str,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._service = service
        self._operator_id = operator_id
        self._clock = clock

    def approve_run(
        self,
        command_id: str,
        run_id: str,
        checkpoint_id: str,
        reason: str | None = None,
    ) -> PortResult:
        return self._record_decision(
            command_id,
            run_id,
            checkpoint_id,
            ApprovalDecision.APPROVE,
            DEFAULT_APPROVAL_REASON if reason is None else reason,
        )

    def reject_run(
        self,
        command_id: str,
        run_id: str,
        checkpoint_id: str,
        reason: str,
    ) -> PortResult:
        return self._record_decision(
            command_id,
            run_id,
            checkpoint_id,
            ApprovalDecision.REJECT,
            reason,
        )

    def _record_decision(
        self,
        command_id: str,
        run_id: str,
        checkpoint_id: str,
        decision: ApprovalDecision,
        reason: str,
    ) -> PortResult:
        result = self._service.record_tui_approval_decision(
            command_id=command_id,
            approval_id=deterministic_approval_id(command_id),
            run_id=run_id,
            checkpoint_id=checkpoint_id,
            operator_id=self._operator_id,
            decision=decision,
            reason=reason,
            decided_at=self._clock(),
        )
        return PortResult(
            ok=True,
            code="completed",
            safe_message="Operator decision recorded.",
            result=result,
        )

    def enqueue(self, command_id: str, payload: AgentEnqueuePayload) -> PortResult:
        try:
            role = AgentRole(payload.agent_id)
        except ValueError as exc:
            raise SpecialistRuntimeUnavailable(
                "TUI queue requires an approved autonomous quant role"
            ) from exc
        if role not in AUTONOMOUS_AGENT_ROLES:
            raise SpecialistRuntimeUnavailable(
                "TUI queue requires an approved autonomous quant role"
            )
        work_id = deterministic_work_id(command_id)
        session_id = stable_session_id(payload.agent_id)
        existing = self._service.get_tui_agent_work(work_id)
        if existing is not None:
            expected = (
                role.value,
                session_id,
                payload.title,
                payload.objective,
                payload.priority,
            )
            actual = tuple(
                existing[key] for key in ("role", "session_id", "title", "objective", "priority")
            )
            if actual != expected:
                raise SpecialistRuntimeUnavailable(
                    f"conflicting TUI agent work for command {command_id}"
                )
            result = existing
        else:
            result = self._service.enqueue_tui_agent_work(
                work_id=work_id,
                role=role,
                session_id=session_id,
                title=payload.title,
                objective=payload.objective,
                priority=payload.priority,
                created_at=self._clock(),
            )
        return PortResult(
            ok=True,
            code="completed",
            safe_message="Agent work queued.",
            result=result,
        )

    def recover(self, command_id: str, request: CommandRequest) -> RecoveryStatus:
        if command_id != request.command_id:
            return "unknown"
        if request.command_type == "agent.enqueue":
            return self._recover_enqueue(request)
        if request.command_type in {"approval.approve", "approval.reject"}:
            return self._recover_approval(request)
        return "unknown"

    def _recover_enqueue(self, request: CommandRequest) -> RecoveryStatus:
        payload = request.payload
        if not isinstance(payload, AgentEnqueuePayload):
            return "unknown"
        try:
            role = AgentRole(payload.agent_id)
        except ValueError:
            return "unknown"
        if role not in AUTONOMOUS_AGENT_ROLES:
            return "unknown"
        work_id = deterministic_work_id(request.command_id)
        try:
            work = self._service.get_tui_agent_work(work_id)
        except Exception:
            return "unknown"
        if work is None:
            return "not-started"
        expected = (
            work_id,
            role.value,
            stable_session_id(payload.agent_id),
            payload.title,
            payload.objective,
            payload.priority,
        )
        actual = tuple(
            work[key] for key in ("work_id", "role", "session_id", "title", "objective", "priority")
        )
        return "completed" if actual == expected else "unknown"

    def _recover_approval(self, request: CommandRequest) -> RecoveryStatus:
        payload = request.payload
        if not isinstance(payload, ApprovalPayload):
            return "unknown"
        try:
            work = self._service.get_tui_agent_work(deterministic_work_id(request.command_id))
        except Exception:
            return "unknown"
        if work is not None:
            return "unknown"
        decision = (
            ApprovalDecision.APPROVE
            if request.command_type == "approval.approve"
            else ApprovalDecision.REJECT
        )
        reason = request.reason
        if decision is ApprovalDecision.APPROVE and reason is None:
            reason = DEFAULT_APPROVAL_REASON
        if reason is None:
            return "unknown"
        try:
            return self._service.recover_tui_approval(
                approval_id=deterministic_approval_id(request.command_id),
                run_id=payload.run_id,
                checkpoint_id=payload.checkpoint_id,
                operator_id=self._operator_id,
                decision=decision,
                reason=reason,
            )
        except Exception:
            return "unknown"


class DisabledCommandPort:
    """Explicit no-effect adapter for command domains not yet reviewed."""

    def execute(self, command_id: str, command_type: str, payload: object = None) -> PortResult:
        del command_id, payload
        try:
            reason = DISABLED_COMMAND_REASONS[command_type]
        except KeyError as exc:
            raise ValueError(f"unsupported disabled command: {command_type}") from exc
        return PortResult(
            ok=False,
            code="capability-disabled",
            safe_message=reason,
        )


class DisabledAgentActionPort:
    def __init__(self) -> None:
        self._disabled = DisabledCommandPort()

    def send_message(self, command_id: str, payload: object) -> PortResult:
        return self._disabled.execute(command_id, "agent.send-message", payload)

    def pause(self, command_id: str, work_id: str) -> PortResult:
        return self._disabled.execute(command_id, "agent.pause", work_id)

    def stop(self, command_id: str, payload: object) -> PortResult:
        return self._disabled.execute(command_id, "agent.stop", payload)

    def retry(self, command_id: str, work_id: str) -> PortResult:
        return self._disabled.execute(command_id, "agent.retry", work_id)

    def set_priority(self, command_id: str, payload: object) -> PortResult:
        return self._disabled.execute(command_id, "agent.set-priority", payload)
