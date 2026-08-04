"""Idempotent governed-command receipts in the shared TUI ledger."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import unicodedata
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated

from pydantic import StringConstraints, TypeAdapter

from .command_contracts import (
    CommandJsonValue,
    CommandReceipt,
    CommandRequest,
    CommandType,
    ReceiptStatus,
)
from .command_policy import AuthorizationDecision, CommandContext
from .sqlite_ledger import LedgerClosedError, LedgerCorruptionError, TuiLedger
from .views import NonEmptyStr, SafeId, Sha256Hex, StrictModel, UtcDateTime, WireUInt


_TERMINAL_STATUSES = {
    ReceiptStatus.COMPLETED,
    ReceiptStatus.FAILED,
    ReceiptStatus.CANCELLED,
}
_STATUS_MESSAGES = {
    ReceiptStatus.ACCEPTED: ("accepted", "Command accepted."),
    ReceiptStatus.RUNNING: ("running", "Command is running."),
    ReceiptStatus.COMPLETED: ("completed", "Command completed."),
    ReceiptStatus.FAILED: ("failed", "Command failed."),
    ReceiptStatus.CANCELLED: ("cancelled", "Command cancelled."),
}
_CLAIM_TOKEN = TypeAdapter(
    Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
)
_SAFE_ID = TypeAdapter(SafeId)
_SAFE_MESSAGE = TypeAdapter(NonEmptyStr)
_SHA256 = TypeAdapter(Sha256Hex)
_UTC = TypeAdapter(UtcDateTime)


class CommandConflict(RuntimeError):
    """Raised when one command ID is reused with different request bytes."""


class CommandClaimError(RuntimeError):
    """Raised when a worker claim is missing, stale, or expired."""


class CommandStateError(RuntimeError):
    """Raised when a command transition is invalid or immutable."""


class SafeRequestMetadata(StrictModel):
    """Audit fields safe to retain for rejected commands."""

    command_id: SafeId
    command_type: CommandType
    operator_id: SafeId
    client_id: SafeId
    reviewed_control_version: WireUInt
    reviewed_control_hash: Sha256Hex


class CommandClaim(StrictModel):
    command_id: SafeId
    worker_id: SafeId
    claim_token: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    claimed_at_utc: UtcDateTime
    lease_expires_at_utc: UtcDateTime
    receipt: CommandReceipt


class StoredAcceptedCommand(StrictModel):
    request: CommandRequest
    operator_id: SafeId
    client_id: SafeId
    handler_key: SafeId
    receipt: CommandReceipt


def canonical_request_json(request: CommandRequest) -> str:
    """Return the one canonical UTF-8 request representation used for hashing."""

    if type(request) is not CommandRequest:
        raise TypeError("request must be CommandRequest")
    return json.dumps(
        request.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )


def canonical_request_sha256(request: CommandRequest) -> str:
    return hashlib.sha256(canonical_request_json(request).encode("utf-8")).hexdigest()


def _utc_text(value: datetime) -> str:
    validated = _UTC.validate_python(value, strict=True)
    return validated.isoformat().replace("+00:00", "Z")


def _parse_utc(value: object) -> datetime:
    if type(value) is not str:
        raise LedgerCorruptionError("stored command timestamp is invalid")
    try:
        return _UTC.validate_python(value, strict=True)
    except ValueError as exc:
        raise LedgerCorruptionError("stored command timestamp is invalid") from exc


def _canonical_result_json(result: dict[str, CommandJsonValue] | None) -> str | None:
    if result is None:
        return None
    return json.dumps(
        result,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )


def _redact_result_value(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _redact_result_value(child)
            for key, child in value.items()
            if type(key) is str and not _is_sensitive_result_key(key)
        }
    if isinstance(value, list):
        return [_redact_result_value(child) for child in value]
    return value


def _is_sensitive_result_key(key: str) -> bool:
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKC", key).casefold()
        if character.isalnum()
    )
    return any(
        marker in normalized
        for marker in ("secret", "token", "password", "credential", "apikey")
    )


def _redact_result(
    result: dict[str, CommandJsonValue] | None,
) -> dict[str, CommandJsonValue] | None:
    if result is None:
        return None
    if type(result) is not dict:
        raise TypeError("result must be a dictionary or None")
    redacted = _redact_result_value(result)
    if not isinstance(redacted, dict):
        raise TypeError("result must be a dictionary")
    return redacted  # type: ignore[return-value]


def _plain_limit(value: object) -> int:
    if type(value) is not int:
        raise TypeError("limit must be an integer")
    if not 1 <= value <= 100:
        raise ValueError("limit must be between 1 and 100")
    return value


class CommandStore:
    """Persist one immutable admission and append-only receipt history per command."""

    def __init__(
        self,
        ledger: Path | TuiLedger,
        *,
        token_factory: Callable[[], str] = lambda: secrets.token_hex(32),
    ) -> None:
        if isinstance(ledger, TuiLedger):
            self._ledger = ledger
            self._owns_ledger = False
        else:
            self._ledger = TuiLedger(Path(ledger))
            self._owns_ledger = True
        self._token_factory = token_factory
        self._closed = False

    @property
    def ledger(self) -> TuiLedger:
        self._require_open()
        return self._ledger

    def __enter__(self) -> CommandStore:
        self._require_open()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        if self._owns_ledger:
            self._ledger.close()
        self._closed = True

    def _require_open(self) -> None:
        if self._closed:
            raise LedgerClosedError("command store is closed")

    def reject(
        self,
        request_sha256: str,
        metadata: SafeRequestMetadata,
        decision: AuthorizationDecision,
        rejected_at_utc: datetime,
    ) -> CommandReceipt:
        self._require_open()
        with self._ledger.transaction() as connection:
            return self.reject_in_transaction(
                connection,
                request_sha256,
                metadata,
                decision,
                rejected_at_utc,
            )

    def reject_in_transaction(
        self,
        connection: sqlite3.Connection,
        request_sha256: str,
        metadata: SafeRequestMetadata,
        decision: AuthorizationDecision,
        rejected_at_utc: datetime,
    ) -> CommandReceipt:
        self._require_open()
        self._ledger.require_transaction(connection)
        if type(metadata) is not SafeRequestMetadata:
            raise TypeError("metadata must be SafeRequestMetadata")
        if type(decision) is not AuthorizationDecision:
            raise TypeError("decision must be AuthorizationDecision")
        if decision.allowed:
            raise ValueError("an allowed decision cannot be stored as rejected")
        checked_hash = _SHA256.validate_python(request_sha256, strict=True)
        rejected_at = _utc_text(rejected_at_utc)
        existing = self._existing_or_conflict(
            connection,
            checked_hash,
            metadata,
            accepted_handler_key=None,
        )
        if existing is not None:
            return existing
        connection.execute(
            """
            INSERT INTO commands (
                command_id, command_type, request_sha256, operator_id, client_id,
                reviewed_control_version, reviewed_control_hash, handler_key,
                accepted_request_json, status, code, safe_message, admitted_at_utc,
                accepted_at_utc, finished_at_utc, result_json, claim_worker_id,
                claim_token_sha256, claimed_at_utc, claim_expires_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, 'rejected', ?, ?, ?, NULL, ?,
                      NULL, NULL, NULL, NULL, NULL)
            """,
            (
                metadata.command_id,
                metadata.command_type,
                checked_hash,
                metadata.operator_id,
                metadata.client_id,
                str(metadata.reviewed_control_version),
                metadata.reviewed_control_hash,
                decision.code,
                decision.safe_message,
                rejected_at,
                rejected_at,
            ),
        )
        self._append_event(
            connection,
            metadata.command_id,
            ReceiptStatus.REJECTED,
            decision.code,
            decision.safe_message,
            rejected_at,
            None,
            None,
        )
        return self._receipt_by_id(connection, metadata.command_id)

    def accept(
        self,
        request: CommandRequest,
        context: CommandContext,
        handler_key: str,
        accepted_at_utc: datetime,
    ) -> CommandReceipt:
        self._require_open()
        with self._ledger.transaction() as connection:
            return self.accept_in_transaction(
                connection,
                request,
                context,
                handler_key,
                accepted_at_utc,
            )

    def accept_in_transaction(
        self,
        connection: sqlite3.Connection,
        request: CommandRequest,
        context: CommandContext,
        handler_key: str,
        accepted_at_utc: datetime,
    ) -> CommandReceipt:
        self._require_open()
        self._ledger.require_transaction(connection)
        if type(request) is not CommandRequest:
            raise TypeError("request must be CommandRequest")
        if type(context) is not CommandContext:
            raise TypeError("context must be CommandContext")
        checked_handler = _SAFE_ID.validate_python(handler_key, strict=True)
        if (
            request.reviewed_control_version != context.control_version
            or not hmac.compare_digest(request.reviewed_control_hash, context.control_hash)
        ):
            raise ValueError("accepted request and context control state disagree")
        request_json = canonical_request_json(request)
        request_sha256 = hashlib.sha256(request_json.encode("utf-8")).hexdigest()
        accepted_at = _utc_text(accepted_at_utc)
        metadata = SafeRequestMetadata(
            command_id=request.command_id,
            command_type=request.command_type,
            operator_id=context.operator_id,
            client_id=context.client_id,
            reviewed_control_version=request.reviewed_control_version,
            reviewed_control_hash=request.reviewed_control_hash,
        )
        existing = self._existing_or_conflict(
            connection,
            request_sha256,
            metadata,
            accepted_handler_key=checked_handler,
        )
        if existing is not None:
            return existing
        code, safe_message = _STATUS_MESSAGES[ReceiptStatus.ACCEPTED]
        connection.execute(
            """
            INSERT INTO commands (
                command_id, command_type, request_sha256, operator_id, client_id,
                reviewed_control_version, reviewed_control_hash, handler_key,
                accepted_request_json, status, code, safe_message, admitted_at_utc,
                accepted_at_utc, finished_at_utc, result_json, claim_worker_id,
                claim_token_sha256, claimed_at_utc, claim_expires_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'accepted', ?, ?, ?, ?, NULL,
                      NULL, NULL, NULL, NULL, NULL)
            """,
            (
                request.command_id,
                request.command_type,
                request_sha256,
                context.operator_id,
                context.client_id,
                str(context.control_version),
                context.control_hash,
                checked_handler,
                request_json,
                code,
                safe_message,
                accepted_at,
                accepted_at,
            ),
        )
        self._append_event(
            connection,
            request.command_id,
            ReceiptStatus.ACCEPTED,
            code,
            safe_message,
            accepted_at,
            None,
            None,
        )
        return self._receipt_by_id(connection, request.command_id)

    def claim(
        self,
        command_id: str,
        worker_id: str,
        claimed_at_utc: datetime,
        lease_expires_at_utc: datetime,
    ) -> CommandClaim | None:
        self._require_open()
        with self._ledger.transaction() as connection:
            return self.claim_in_transaction(
                connection,
                command_id,
                worker_id,
                claimed_at_utc,
                lease_expires_at_utc,
            )

    def claim_in_transaction(
        self,
        connection: sqlite3.Connection,
        command_id: str,
        worker_id: str,
        claimed_at_utc: datetime,
        lease_expires_at_utc: datetime,
    ) -> CommandClaim | None:
        self._require_open()
        self._ledger.require_transaction(connection)
        checked_command_id = _SAFE_ID.validate_python(command_id, strict=True)
        checked_worker_id = _SAFE_ID.validate_python(worker_id, strict=True)
        claimed_at = _utc_text(claimed_at_utc)
        lease_expires_at = _utc_text(lease_expires_at_utc)
        if lease_expires_at_utc <= claimed_at_utc:
            raise ValueError("claim lease must expire after it begins")
        row = connection.execute(
            "SELECT * FROM commands WHERE command_id = ?",
            (checked_command_id,),
        ).fetchone()
        if row is None or row["status"] in {
            "rejected",
            "completed",
            "failed",
            "cancelled",
        }:
            return None
        if row["status"] == "running" and _parse_utc(row["claim_expires_at_utc"]) > claimed_at_utc:
            return None
        accepted_at = _parse_utc(row["accepted_at_utc"])
        if claimed_at_utc < accepted_at:
            raise ValueError("claim cannot predate command acceptance")
        claim_token = _CLAIM_TOKEN.validate_python(self._token_factory(), strict=True)
        token_sha256 = hashlib.sha256(claim_token.encode("ascii")).hexdigest()
        code, safe_message = _STATUS_MESSAGES[ReceiptStatus.RUNNING]
        connection.execute(
            """
            UPDATE commands
            SET status = 'running', code = ?, safe_message = ?, finished_at_utc = NULL,
                result_json = NULL, claim_worker_id = ?, claim_token_sha256 = ?,
                claimed_at_utc = ?, claim_expires_at_utc = ?
            WHERE command_id = ?
            """,
            (
                code,
                safe_message,
                checked_worker_id,
                token_sha256,
                claimed_at,
                lease_expires_at,
                checked_command_id,
            ),
        )
        self._append_event(
            connection,
            checked_command_id,
            ReceiptStatus.RUNNING,
            code,
            safe_message,
            claimed_at,
            checked_worker_id,
            None,
        )
        return CommandClaim(
            command_id=checked_command_id,
            worker_id=checked_worker_id,
            claim_token=claim_token,
            claimed_at_utc=claimed_at_utc,
            lease_expires_at_utc=lease_expires_at_utc,
            receipt=self._receipt_by_id(connection, checked_command_id),
        )

    def finish(
        self,
        command_id: str,
        claim_token: str,
        status: ReceiptStatus,
        result: dict[str, CommandJsonValue] | None,
        finished_at_utc: datetime,
        *,
        code: str | None = None,
        safe_message: str | None = None,
    ) -> CommandReceipt:
        self._require_open()
        with self._ledger.transaction() as connection:
            return self.finish_in_transaction(
                connection,
                command_id,
                claim_token,
                status,
                result,
                finished_at_utc,
                code=code,
                safe_message=safe_message,
            )

    def finish_in_transaction(
        self,
        connection: sqlite3.Connection,
        command_id: str,
        claim_token: str,
        status: ReceiptStatus,
        result: dict[str, CommandJsonValue] | None,
        finished_at_utc: datetime,
        *,
        code: str | None = None,
        safe_message: str | None = None,
    ) -> CommandReceipt:
        self._require_open()
        self._ledger.require_transaction(connection)
        checked_command_id = _SAFE_ID.validate_python(command_id, strict=True)
        checked_token = _CLAIM_TOKEN.validate_python(claim_token, strict=True)
        if type(status) is not ReceiptStatus or status not in _TERMINAL_STATUSES:
            raise CommandStateError("finish requires a terminal receipt status")
        default_code, default_message = _STATUS_MESSAGES[status]
        checked_code = (
            default_code if code is None else _SAFE_ID.validate_python(code, strict=True)
        )
        checked_message = (
            default_message
            if safe_message is None
            else _SAFE_MESSAGE.validate_python(safe_message, strict=True)
        )
        finished_at = _utc_text(finished_at_utc)
        row = connection.execute(
            "SELECT * FROM commands WHERE command_id = ?",
            (checked_command_id,),
        ).fetchone()
        if row is None:
            raise CommandStateError("command does not exist")
        token_sha256 = hashlib.sha256(checked_token.encode("ascii")).hexdigest()
        stored_token_sha256 = row["claim_token_sha256"]
        if stored_token_sha256 is None or not hmac.compare_digest(
            stored_token_sha256,
            token_sha256,
        ):
            raise CommandClaimError("command claim token is stale or unknown")
        redacted_result = _redact_result(result)
        proposed = CommandReceipt(
            command_id=checked_command_id,
            status=status,
            code=checked_code,
            safe_message=checked_message,
            accepted_at_utc=row["accepted_at_utc"],
            finished_at_utc=finished_at,
            result=redacted_result,
        )
        result_json = _canonical_result_json(proposed.result)
        if row["status"] in {"rejected", "completed", "failed", "cancelled"}:
            current = self._receipt_from_row(row)
            if (
                current.status is status
                and current.code == proposed.code
                and current.safe_message == proposed.safe_message
                and current.result == proposed.result
                and current.finished_at_utc == finished_at_utc
            ):
                return current
            raise CommandStateError("terminal command receipt is immutable")
        if row["status"] != "running":
            raise CommandStateError("command must be claimed before finishing")
        if finished_at_utc >= _parse_utc(row["claim_expires_at_utc"]):
            raise CommandClaimError("command claim has expired")
        if finished_at_utc < _parse_utc(row["claimed_at_utc"]):
            raise ValueError("finish cannot predate the worker claim")
        connection.execute(
            """
            UPDATE commands
            SET status = ?, code = ?, safe_message = ?, finished_at_utc = ?, result_json = ?
            WHERE command_id = ?
            """,
            (
                status.value,
                checked_code,
                checked_message,
                finished_at,
                result_json,
                checked_command_id,
            ),
        )
        self._append_event(
            connection,
            checked_command_id,
            status,
            checked_code,
            checked_message,
            finished_at,
            row["claim_worker_id"],
            result_json,
        )
        return self._receipt_by_id(connection, checked_command_id)

    def get(self, command_id: str) -> CommandReceipt | None:
        self._require_open()
        checked_command_id = _SAFE_ID.validate_python(command_id, strict=True)
        with self._ledger.read() as connection:
            row = connection.execute(
                "SELECT * FROM commands WHERE command_id = ?",
                (checked_command_id,),
            ).fetchone()
        return None if row is None else self._receipt_from_row(row)

    def get_in_transaction(
        self,
        connection: sqlite3.Connection,
        command_id: str,
    ) -> CommandReceipt | None:
        self._require_open()
        self._ledger.require_transaction(connection)
        checked_command_id = _SAFE_ID.validate_python(command_id, strict=True)
        row = connection.execute(
            "SELECT * FROM commands WHERE command_id = ?",
            (checked_command_id,),
        ).fetchone()
        return None if row is None else self._receipt_from_row(row)

    def get_accepted(self, command_id: str) -> StoredAcceptedCommand | None:
        self._require_open()
        checked_command_id = _SAFE_ID.validate_python(command_id, strict=True)
        with self._ledger.read() as connection:
            row = connection.execute(
                "SELECT * FROM commands WHERE command_id = ?",
                (checked_command_id,),
            ).fetchone()
        if row is None or row["accepted_request_json"] is None:
            return None
        try:
            request = CommandRequest.model_validate_json(
                row["accepted_request_json"],
                strict=True,
            )
            if (
                canonical_request_json(request) != row["accepted_request_json"]
                or canonical_request_sha256(request) != row["request_sha256"]
            ):
                raise ValueError("request integrity mismatch")
            return StoredAcceptedCommand(
                request=request,
                operator_id=row["operator_id"],
                client_id=row["client_id"],
                handler_key=row["handler_key"],
                receipt=self._receipt_from_row(row),
            )
        except (TypeError, ValueError) as exc:
            raise LedgerCorruptionError("stored accepted command is invalid") from exc

    def list(self, limit: int, cursor: str | None) -> tuple[CommandReceipt, ...]:
        self._require_open()
        page_size = _plain_limit(limit)
        checked_cursor = (
            None if cursor is None else _SAFE_ID.validate_python(cursor, strict=True)
        )
        with self._ledger.read() as connection:
            if checked_cursor is None:
                rows = connection.execute(
                    "SELECT * FROM commands ORDER BY command_sequence DESC LIMIT ?",
                    (page_size,),
                ).fetchall()
            else:
                cursor_row = connection.execute(
                    "SELECT command_sequence FROM commands WHERE command_id = ?",
                    (checked_cursor,),
                ).fetchone()
                if cursor_row is None:
                    return ()
                rows = connection.execute(
                    """
                    SELECT * FROM commands
                    WHERE command_sequence < ?
                    ORDER BY command_sequence DESC
                    LIMIT ?
                    """,
                    (cursor_row["command_sequence"], page_size),
                ).fetchall()
        return tuple(self._receipt_from_row(row) for row in rows)

    def expired_running(self, now_utc: datetime) -> tuple[CommandReceipt, ...]:
        self._require_open()
        now = _UTC.validate_python(now_utc, strict=True)
        with self._ledger.read() as connection:
            rows = connection.execute(
                """
                SELECT * FROM commands
                WHERE status = 'running'
                ORDER BY command_sequence
                """
            ).fetchall()
        return tuple(
            self._receipt_from_row(row)
            for row in rows
            if _parse_utc(row["claim_expires_at_utc"]) <= now
        )

    def recoverable(self, now_utc: datetime) -> tuple[CommandReceipt, ...]:
        """List unclaimed accepts and expired running commands in admission order."""

        self._require_open()
        now = _UTC.validate_python(now_utc, strict=True)
        with self._ledger.read() as connection:
            rows = connection.execute(
                """
                SELECT * FROM commands
                WHERE status IN ('accepted', 'running')
                ORDER BY command_sequence
                """
            ).fetchall()
        return tuple(
            self._receipt_from_row(row)
            for row in rows
            if row["status"] == "accepted"
            or _parse_utc(row["claim_expires_at_utc"]) <= now
        )

    def _existing_or_conflict(
        self,
        connection: sqlite3.Connection,
        request_sha256: str,
        metadata: SafeRequestMetadata,
        *,
        accepted_handler_key: str | None,
    ) -> CommandReceipt | None:
        row = connection.execute(
            "SELECT * FROM commands WHERE command_id = ?",
            (metadata.command_id,),
        ).fetchone()
        if row is None:
            return None
        if not hmac.compare_digest(row["request_sha256"], request_sha256):
            raise CommandConflict(
                f"command ID {metadata.command_id} has conflicting request content"
            )
        replay_context_matches = (
            row["command_type"] == metadata.command_type
            and row["operator_id"] == metadata.operator_id
            and row["client_id"] == metadata.client_id
            and row["reviewed_control_version"]
            == str(metadata.reviewed_control_version)
            and hmac.compare_digest(
                row["reviewed_control_hash"],
                metadata.reviewed_control_hash,
            )
            and (
                accepted_handler_key is None
                or row["status"] == "rejected"
                or row["handler_key"] == accepted_handler_key
            )
        )
        if not replay_context_matches:
            raise CommandConflict(
                f"command ID {metadata.command_id} has conflicting replay context"
            )
        return self._receipt_from_row(row)

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        command_id: str,
        status: ReceiptStatus,
        code: str,
        safe_message: str,
        occurred_at_utc: str,
        worker_id: str | None,
        result_json: str | None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO command_receipt_events (
                command_id, status, code, safe_message, occurred_at_utc,
                worker_id, result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                command_id,
                status.value,
                code,
                safe_message,
                occurred_at_utc,
                worker_id,
                result_json,
            ),
        )

    def _receipt_by_id(
        self,
        connection: sqlite3.Connection,
        command_id: str,
    ) -> CommandReceipt:
        row = connection.execute(
            "SELECT * FROM commands WHERE command_id = ?",
            (command_id,),
        ).fetchone()
        if row is None:
            raise LedgerCorruptionError("stored command disappeared")
        return self._receipt_from_row(row)

    @staticmethod
    def _receipt_from_row(row: sqlite3.Row) -> CommandReceipt:
        try:
            result = None if row["result_json"] is None else json.loads(row["result_json"])
            return CommandReceipt(
                command_id=row["command_id"],
                status=ReceiptStatus(row["status"]),
                code=row["code"],
                safe_message=row["safe_message"],
                accepted_at_utc=row["accepted_at_utc"],
                finished_at_utc=row["finished_at_utc"],
                result=result,
            )
        except (TypeError, ValueError) as exc:
            raise LedgerCorruptionError("stored command receipt is invalid") from exc
