"""Immutable TUI-owned operator hold decisions."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Callable, Literal

from pydantic import TypeAdapter

from .command_contracts import (
    ApprovalPayload,
    CommandReceipt,
    CommandRequest,
    ReasonText,
    ReceiptStatus,
)
from .command_policy import CommandContext
from .command_store import CommandStore, canonical_request_json
from .sqlite_ledger import LedgerClosedError, TuiLedger
from .views import SafeId, StrictModel, UtcDateTime


_UTC = TypeAdapter(UtcDateTime)
_SAFE_ID = TypeAdapter(SafeId)


class OperatorDecisionError(RuntimeError):
    """Raised when a request cannot create an operator hold decision."""


class OperatorDecisionConflict(RuntimeError):
    """Raised when a decision replay differs from stored command authority."""


class OperatorDecision(StrictModel):
    decision_id: SafeId
    command_id: SafeId
    run_id: SafeId
    checkpoint_id: SafeId
    operator_id: SafeId
    reason: ReasonText
    decision: Literal["hold"]
    decided_at_utc: UtcDateTime


def canonical_decision_json(decision: OperatorDecision) -> str:
    if type(decision) is not OperatorDecision:
        raise TypeError("decision must be OperatorDecision")
    return json.dumps(
        decision.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )


class OperatorDecisionStore:
    """Store approval holds and their terminal receipts in one ledger transaction."""

    def __init__(self, ledger: Path | TuiLedger) -> None:
        if isinstance(ledger, TuiLedger):
            self._ledger = ledger
            self._owns_ledger = False
        else:
            self._ledger = TuiLedger(Path(ledger))
            self._owns_ledger = True
        self._commands = CommandStore(self._ledger)
        self._closed = False

    def __enter__(self) -> OperatorDecisionStore:
        self._require_open()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._commands.close()
        if self._owns_ledger:
            self._ledger.close()
        self._closed = True

    def _require_open(self) -> None:
        if self._closed:
            raise LedgerClosedError("operator decision store is closed")

    def hold(
        self,
        request: CommandRequest,
        context: CommandContext,
        claim_token: str,
        decided_at_utc: datetime | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> tuple[OperatorDecision, CommandReceipt]:
        self._require_open()
        if type(request) is not CommandRequest:
            raise TypeError("request must be CommandRequest")
        if type(context) is not CommandContext:
            raise TypeError("context must be CommandContext")
        if request.command_type != "approval.hold" or type(request.payload) is not ApprovalPayload:
            raise OperatorDecisionError("operator decisions require approval.hold")
        if request.reason is None:
            raise OperatorDecisionError("approval.hold requires a reason")
        if (decided_at_utc is None) == (clock is None):
            raise TypeError("provide exactly one decision timestamp or clock")
        fixed_decided_at = (
            None
            if decided_at_utc is None
            else _UTC.validate_python(decided_at_utc, strict=True)
        )
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable")

        with self._ledger.transaction() as connection:
            command = connection.execute(
                "SELECT * FROM commands WHERE command_id = ?",
                (request.command_id,),
            ).fetchone()
            if command is None or command["accepted_request_json"] != canonical_request_json(
                request
            ):
                raise OperatorDecisionConflict("accepted request does not match exactly")
            if (
                command["command_type"] != "approval.hold"
                or command["handler_key"] != "approval.hold"
                or command["operator_id"] != context.operator_id
                or command["client_id"] != context.client_id
                or not context.authenticated
                or not context.owns_control_lease
                or request.reviewed_control_version != context.control_version
                or not hmac.compare_digest(
                    request.reviewed_control_hash,
                    context.control_hash,
                )
                or command["reviewed_control_version"]
                != str(context.control_version)
                or not hmac.compare_digest(
                    command["reviewed_control_hash"],
                    context.control_hash,
                )
            ):
                raise OperatorDecisionConflict("accepted request caller identity differs")
            decided_at = (
                fixed_decided_at
                if fixed_decided_at is not None
                else _UTC.validate_python(clock(), strict=True)
            )
            decision_id = "tui-decision:" + hashlib.sha256(
                request.command_id.encode("utf-8")
            ).hexdigest()
            decision = OperatorDecision(
                decision_id=decision_id,
                command_id=request.command_id,
                run_id=request.payload.run_id,
                checkpoint_id=request.payload.checkpoint_id,
                operator_id=context.operator_id,
                reason=request.reason,
                decision="hold",
                decided_at_utc=decided_at,
            )
            content_json = canonical_decision_json(decision)
            existing = connection.execute(
                "SELECT * FROM operator_decisions WHERE command_id = ?",
                (request.command_id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO operator_decisions (
                        decision_id, command_id, run_id, checkpoint_id, operator_id,
                        reason, decision, decided_at_utc, content_json
                    ) VALUES (?, ?, ?, ?, ?, ?, 'hold', ?, ?)
                    """,
                    (
                        decision.decision_id,
                        decision.command_id,
                        decision.run_id,
                        decision.checkpoint_id,
                        decision.operator_id,
                        decision.reason,
                        decision.model_dump(mode="json")["decided_at_utc"],
                        content_json,
                    ),
                )
            else:
                stored = OperatorDecision.model_validate_json(
                    existing["content_json"],
                    strict=True,
                )
                if (
                    stored.decision_id != decision.decision_id
                    or stored.command_id != decision.command_id
                    or stored.run_id != decision.run_id
                    or stored.checkpoint_id != decision.checkpoint_id
                    or stored.operator_id != decision.operator_id
                    or stored.reason != decision.reason
                    or stored.decision != decision.decision
                ):
                    raise OperatorDecisionConflict("operator decision replay differs")
                receipt = self._commands.get_in_transaction(
                    connection,
                    request.command_id,
                )
                if (
                    receipt is None
                    or receipt.status is not ReceiptStatus.COMPLETED
                    or receipt.code != "completed"
                    or receipt.safe_message != "Command completed."
                    or receipt.finished_at_utc != stored.decided_at_utc
                    or receipt.result != {"decision_id": stored.decision_id}
                ):
                    raise OperatorDecisionConflict("operator decision receipt differs")
                return stored, receipt
            receipt = self._commands.finish_in_transaction(
                connection,
                request.command_id,
                claim_token,
                ReceiptStatus.COMPLETED,
                {"decision_id": decision.decision_id},
                decided_at,
            )
        return decision, receipt

    def get(self, command_id: str) -> OperatorDecision | None:
        self._require_open()
        checked_command_id = _SAFE_ID.validate_python(command_id, strict=True)
        with self._ledger.read() as connection:
            row = connection.execute(
                "SELECT content_json FROM operator_decisions WHERE command_id = ?",
                (checked_command_id,),
            ).fetchone()
        return None if row is None else OperatorDecision.model_validate_json(
            row["content_json"], strict=True
        )

    def list(self) -> tuple[OperatorDecision, ...]:
        self._require_open()
        with self._ledger.read() as connection:
            rows = connection.execute(
                "SELECT content_json FROM operator_decisions ORDER BY decision_sequence"
            ).fetchall()
        return tuple(
            OperatorDecision.model_validate_json(row["content_json"], strict=True)
            for row in rows
        )
