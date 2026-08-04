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

from .command_contracts import (
    COMMAND_SPECS,
    MAX_COMMAND_PAYLOAD_BYTES,
    AgentEnqueuePayload,
    ApprovalPayload,
    CommandJsonValue,
    CommandReceipt,
    CommandRequest,
    CommandType,
    NoteAddPayload,
    ReceiptStatus,
)
from .command_policy import (
    AuthorizationDecision,
    CommandContext,
    CommandPolicy,
    EvaluatedPrerequisites,
    canonical_request_hash,
)
from .command_ports import DISABLED_COMMAND_REASONS, PlatformCommandPort, PortResult
from .command_store import (
    CommandClaim,
    CommandStore,
    SafeRequestMetadata,
    canonical_request_sha256,
)
from .notes import NoteStore, NoteTarget, NoteVisibility
from .operator_decisions import OperatorDecisionStore
from .sqlite_ledger import LedgerClosedError, LedgerCorruptionError, TuiLedger
from .views import CommandSpecView, UtcDateTime


_HANDLER_KEYS: Mapping[CommandType, str] = MappingProxyType(
    {
        "note.add": "note.add",
        "approval.approve": "approval.approve",
        "approval.hold": "approval.hold",
        "approval.reject": "approval.reject",
        "agent.enqueue": "agent.enqueue",
    }
)
_EXTERNAL_HANDLERS = {
    "approval.approve",
    "approval.reject",
    "agent.enqueue",
}
_RECOVERY_STATES = {"not-started", "completed", "failed", "unknown"}
_MANUAL_INTERVENTION_MESSAGE = (
    "Downstream command state is unknown; inspect it before any retry."
)
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
    """Authorize, persist, execute, and recover the five reviewed handlers."""

    def __init__(
        self,
        ledger: Path | TuiLedger,
        port: PlatformCommandPort,
        *,
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
        spec = self._specs.get(request.command_type)
        if spec is None:
            decision = AuthorizationDecision(
                allowed=False,
                code="unknown-command",
                safe_message="Command is not in the current catalog.",
            )
        else:
            decision = self._policy.authorize(context, request, spec)
        if decision.allowed and request.command_type not in _HANDLER_KEYS:
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
            if request.command_type not in _EXTERNAL_HANDLERS:
                raise LedgerCorruptionError("recoverable command has no reviewed handler")
            state = self._port.recover(request.command_id, request)
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
        raise LedgerCorruptionError("claimed command has no reviewed external handler")

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
