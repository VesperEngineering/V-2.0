"""Occurrence-bound, TUI-owned alert dismissal state."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from vesper.platform.ops.alerts import OperationsAlertRecord
from vesper.platform.ops.supervisor import validate_state_root

from .command_contracts import AlertDismissPayload, CommandRequest
from .sqlite_ledger import LedgerClosedError, TuiLedger
from .views import SafeId, StrictModel, UtcDateTime


_SAFE_ID = TypeAdapter(SafeId)
_UTC = TypeAdapter(UtcDateTime)
_ALERT_FILE = "attention-alert.json"


class AlertOccurrenceUnavailable(RuntimeError):
    """Raised when the current daemon-owned alert cannot be bound safely."""


class AlertOccurrenceNotResolved(AlertOccurrenceUnavailable):
    """Raised when an active alert has not reached the resolved state."""


class AlertDismissalUnavailable(RuntimeError):
    """Raised when durable dismissal state cannot be read safely."""


class AlertOccurrence(StrictModel):
    alert_id: SafeId
    created_at_utc: UtcDateTime


class AlertDismissalBinding(StrictModel):
    command_id: SafeId
    alert_id: SafeId
    created_at_utc: UtcDateTime


class AlertDismissal(StrictModel):
    command_id: SafeId
    alert_id: SafeId
    created_at_utc: UtcDateTime
    dismissed_at_utc: UtcDateTime


class AlertDismissalStore:
    """Bind dismissal commands and persist effects in the shared TUI ledger."""

    def __init__(self, ledger: Path | TuiLedger, state_root: Path) -> None:
        if isinstance(ledger, TuiLedger):
            self._ledger = ledger
            self._owns_ledger = False
        else:
            self._ledger = TuiLedger(Path(ledger))
            self._owns_ledger = True
        self._path = validate_state_root(state_root) / _ALERT_FILE
        self._closed = False

    @property
    def healthy(self) -> bool:
        if self._closed:
            return False
        try:
            with self._ledger.read() as connection:
                connection.execute("SELECT 1 FROM alert_dismissals LIMIT 1").fetchone()
        except (LedgerClosedError, sqlite3.DatabaseError):
            return False
        return True

    @property
    def dismissible(self) -> bool:
        """Return whether the current alert is valid and resolved."""

        if self._closed:
            return False
        try:
            return self._read_current_record().severity == "resolved"
        except AlertOccurrenceUnavailable:
            return False

    def close(self) -> None:
        if self._closed:
            return
        if self._owns_ledger:
            self._ledger.close()
        self._closed = True

    def current_occurrence(self, alert_id: str) -> AlertOccurrence:
        self._require_open()
        checked_id = _SAFE_ID.validate_python(alert_id, strict=True)
        record = self._read_current_record()
        if record.severity != "resolved":
            raise AlertOccurrenceNotResolved("Only a resolved alert can be dismissed.")
        if record.alert_id != checked_id:
            raise AlertOccurrenceUnavailable("Selected alert is no longer current.")
        return AlertOccurrence(
            alert_id=record.alert_id,
            created_at_utc=record.created_at_utc,
        )

    def _read_current_record(self) -> OperationsAlertRecord:
        try:
            raw = self._path.read_bytes()
        except (FileNotFoundError, OSError) as exc:
            raise AlertOccurrenceUnavailable("Current alert state is unavailable.") from exc
        try:
            record = OperationsAlertRecord.model_validate_json(raw, strict=True)
        except (ValidationError, ValueError) as exc:
            raise AlertOccurrenceUnavailable("Current alert state is unavailable.") from exc
        return record

    def bind_for_command_in_transaction(
        self,
        connection: sqlite3.Connection,
        command_id: str,
        occurrence: AlertOccurrence,
    ) -> AlertDismissalBinding:
        self._require_open()
        self._ledger.require_transaction(connection)
        checked_command_id = _SAFE_ID.validate_python(command_id, strict=True)
        if type(occurrence) is not AlertOccurrence:
            raise TypeError("occurrence must be AlertOccurrence")
        command = connection.execute(
            "SELECT * FROM commands WHERE command_id = ?",
            (checked_command_id,),
        ).fetchone()
        if command is None or command["accepted_request_json"] is None:
            raise AlertDismissalUnavailable("Alert dismissal command is unavailable.")
        try:
            request = CommandRequest.model_validate_json(
                command["accepted_request_json"],
                strict=True,
            )
        except (ValidationError, ValueError) as exc:
            raise AlertDismissalUnavailable("Alert dismissal command is invalid.") from exc
        if (
            request.command_type != "alert.dismiss"
            or type(request.payload) is not AlertDismissPayload
            or request.payload.alert_id != occurrence.alert_id
            or request.payload.created_at_utc != occurrence.created_at_utc
            or command["handler_key"] != "alert.dismiss"
            or command["status"] != "accepted"
        ):
            raise AlertDismissalUnavailable("Alert dismissal command does not match.")
        binding = AlertDismissalBinding(
            command_id=checked_command_id,
            alert_id=occurrence.alert_id,
            created_at_utc=occurrence.created_at_utc,
        )
        values = binding.model_dump(mode="json")
        existing = connection.execute(
            "SELECT * FROM alert_dismissal_bindings WHERE command_id = ?",
            (checked_command_id,),
        ).fetchone()
        if existing is None:
            connection.execute(
                """
                INSERT INTO alert_dismissal_bindings (
                    command_id, alert_id, alert_created_at_utc
                ) VALUES (?, ?, ?)
                """,
                (
                    values["command_id"],
                    values["alert_id"],
                    values["created_at_utc"],
                ),
            )
        elif (
            existing["alert_id"],
            existing["alert_created_at_utc"],
        ) != (values["alert_id"], values["created_at_utc"]):
            raise AlertDismissalUnavailable("Alert dismissal binding conflicts.")
        return binding

    def binding_for_command_in_transaction(
        self,
        connection: sqlite3.Connection,
        command_id: str,
    ) -> AlertDismissalBinding | None:
        self._require_open()
        self._ledger.require_transaction(connection)
        checked_command_id = _SAFE_ID.validate_python(command_id, strict=True)
        try:
            return self._binding_in_transaction(connection, checked_command_id)
        except (ValidationError, ValueError) as exc:
            raise AlertDismissalUnavailable("Alert dismissal binding is invalid.") from exc

    def dismiss_for_command_in_transaction(
        self,
        connection: sqlite3.Connection,
        command_id: str,
        dismissed_at_utc: datetime,
    ) -> AlertDismissal:
        self._require_open()
        self._ledger.require_transaction(connection)
        checked_command_id = _SAFE_ID.validate_python(command_id, strict=True)
        dismissed_at = _UTC.validate_python(dismissed_at_utc, strict=True)
        binding = self._binding_in_transaction(connection, checked_command_id)
        if binding is None:
            raise AlertDismissalUnavailable("Alert dismissal binding is unavailable.")
        dismissal = AlertDismissal(
            command_id=checked_command_id,
            alert_id=binding.alert_id,
            created_at_utc=binding.created_at_utc,
            dismissed_at_utc=dismissed_at,
        )
        values = dismissal.model_dump(mode="json")
        existing = connection.execute(
            "SELECT * FROM alert_dismissals WHERE command_id = ?",
            (checked_command_id,),
        ).fetchone()
        if existing is None:
            connection.execute(
                """
                INSERT INTO alert_dismissals (
                    command_id, alert_id, alert_created_at_utc, dismissed_at_utc
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    values["command_id"],
                    values["alert_id"],
                    values["created_at_utc"],
                    values["dismissed_at_utc"],
                ),
            )
        elif (
            existing["alert_id"],
            existing["alert_created_at_utc"],
            existing["dismissed_at_utc"],
        ) != (
            values["alert_id"],
            values["created_at_utc"],
            values["dismissed_at_utc"],
        ):
            raise AlertDismissalUnavailable("Alert dismissal replay conflicts.")
        return dismissal

    def binding_for_command(self, command_id: str) -> AlertDismissalBinding | None:
        self._require_open()
        checked_command_id = _SAFE_ID.validate_python(command_id, strict=True)
        try:
            with self._ledger.read() as connection:
                return self._binding_in_transaction(connection, checked_command_id)
        except (LedgerClosedError, sqlite3.DatabaseError) as exc:
            raise AlertDismissalUnavailable("Alert dismissal state is unavailable.") from exc

    def is_dismissed(self, alert_id: str, created_at_utc: datetime) -> bool:
        self._require_open()
        checked_id = _SAFE_ID.validate_python(alert_id, strict=True)
        created_at = _UTC.validate_python(created_at_utc, strict=True)
        created_at_text = AlertOccurrence(
            alert_id=checked_id,
            created_at_utc=created_at,
        ).model_dump(mode="json")["created_at_utc"]
        try:
            with self._ledger.read() as connection:
                row = connection.execute(
                    """
                    SELECT 1
                    FROM alert_dismissals
                    WHERE alert_id = ? AND alert_created_at_utc = ?
                    LIMIT 1
                    """,
                    (checked_id, created_at_text),
                ).fetchone()
        except (LedgerClosedError, sqlite3.DatabaseError) as exc:
            raise AlertDismissalUnavailable("Alert dismissal state is unavailable.") from exc
        return row is not None

    @staticmethod
    def _binding_in_transaction(
        connection: sqlite3.Connection,
        command_id: str,
    ) -> AlertDismissalBinding | None:
        row = connection.execute(
            "SELECT * FROM alert_dismissal_bindings WHERE command_id = ?",
            (command_id,),
        ).fetchone()
        if row is None:
            return None
        return AlertDismissalBinding(
            command_id=row["command_id"],
            alert_id=row["alert_id"],
            created_at_utc=row["alert_created_at_utc"],
        )

    def _require_open(self) -> None:
        if self._closed:
            raise LedgerClosedError("alert dismissal store is closed")


__all__ = [
    "AlertDismissal",
    "AlertDismissalBinding",
    "AlertDismissalStore",
    "AlertDismissalUnavailable",
    "AlertOccurrence",
    "AlertOccurrenceNotResolved",
    "AlertOccurrenceUnavailable",
]
