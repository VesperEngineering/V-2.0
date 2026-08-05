"""Opaque, daemon-owned attention alert persistence and notification routing."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, TypeAdapter, ValidationError, model_validator

from vesper.platform.ops.policy import OperationsState
from vesper.platform.ops.supervisor import validate_state_root
from vesper.platform.tui.notifications import NotificationPort
from vesper.platform.tui.views import SafeId, StrictModel, UtcDateTime


_SAFE_ID = TypeAdapter(SafeId)
_UTC = TypeAdapter(UtcDateTime)
_ALERT_FILE = "attention-alert.json"
_OPERATIONS_LOOP_FAILURE_INCIDENT = "operations-loop-failed"
MAX_NOTIFICATION_CLEANUP_IDS = 64


class OperationsAlertRecord(StrictModel):
    alert_id: SafeId
    severity: Literal["urgent", "resolved"]
    created_at_utc: UtcDateTime
    resolved_at_utc: UtcDateTime | None
    notification_cleanup_pending: bool = False
    notification_cleanup_alert_ids: Annotated[
        tuple[SafeId, ...],
        Field(max_length=MAX_NOTIFICATION_CLEANUP_IDS),
    ] = ()
    notification_cleanup_overflow: bool = False

    @model_validator(mode="after")
    def require_resolution_time(self) -> OperationsAlertRecord:
        if (self.severity == "resolved") != (self.resolved_at_utc is not None):
            raise ValueError("alert resolution state is invalid")
        if self.resolved_at_utc is not None and self.resolved_at_utc < self.created_at_utc:
            raise ValueError("alert resolution precedes creation")
        if self.severity == "urgent" and self.notification_cleanup_pending:
            raise ValueError("urgent alerts cannot have pending notification cleanup")
        if len(self.notification_cleanup_alert_ids) != len(
            set(self.notification_cleanup_alert_ids)
        ):
            raise ValueError("notification cleanup IDs must be unique")
        if self.severity == "urgent" and self.alert_id in self.notification_cleanup_alert_ids:
            raise ValueError("the active alert cannot be queued for cleanup")
        return self


class AtomicAlertRecordStore:
    """Persist one opaque current/resolved alert without incident details."""

    def __init__(self, state_root: Path) -> None:
        self._state_root = validate_state_root(state_root, create=True)
        self._path = self._state_root / _ALERT_FILE

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> OperationsAlertRecord | None:
        try:
            raw = self._path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise OSError("attention alert state is unavailable") from exc
        try:
            return OperationsAlertRecord.model_validate_json(raw, strict=True)
        except (ValidationError, ValueError) as exc:
            raise ValueError("attention alert state is invalid") from exc

    def write(self, record: OperationsAlertRecord) -> None:
        if type(record) is not OperationsAlertRecord:
            raise TypeError("record must be OperationsAlertRecord")
        payload = record.model_dump_json().encode("utf-8")
        temporary = self._state_root / f".{_ALERT_FILE}.{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _opaque_alert_id(incident_id: object) -> SafeId:
    if type(incident_id) is not str:
        raise TypeError("incident_id must be a string")
    digest = hashlib.sha256(f"v20-incident\0{incident_id}".encode("utf-8")).hexdigest()[:32]
    return _SAFE_ID.validate_python(f"alert:{digest}", strict=True)


class OperationsAlertRouter:
    """Route only an explicit operations incident ID to generic attention."""

    def __init__(
        self,
        notifications: NotificationPort,
        store: AtomicAlertRecordStore,
    ) -> None:
        if not callable(getattr(notifications, "send_attention", None)) or not callable(
            getattr(notifications, "resolve", None)
        ):
            raise TypeError("notifications must provide send_attention and resolve")
        if type(store) is not AtomicAlertRecordStore:
            raise TypeError("store must be AtomicAlertRecordStore")
        self._notifications = notifications
        self._store = store
        self._active_alert_id: SafeId | None = None

    def observe(self, state: OperationsState, observed_at_utc: datetime) -> None:
        if type(state) is not OperationsState:
            raise TypeError("state must be OperationsState")
        observed_at = _UTC.validate_python(observed_at_utc, strict=True)
        existing = self._store.read()
        current = self._active_alert_id
        if current is None and existing is not None and existing.severity == "urgent":
            current = existing.alert_id

        if state.incident_id is None:
            if current is None:
                if existing is not None and existing.severity == "resolved":
                    normalized, _ = _with_cleanup_id(
                        existing,
                        existing.alert_id if existing.notification_cleanup_pending else None,
                    )
                    if normalized != existing:
                        self._store.write(normalized)
                    if normalized.notification_cleanup_overflow:
                        self._record_cleanup_overflow(normalized.alert_id)
                    self._retry_notification_cleanup(normalized, raise_failures=True)
                return
            created_at = existing.created_at_utc if existing is not None else observed_at
            resolved_at = max(observed_at, created_at)
            base = existing or OperationsAlertRecord(
                alert_id=current,
                severity="urgent",
                created_at_utc=created_at,
                resolved_at_utc=None,
            )
            resolved, _ = _with_cleanup_id(
                OperationsAlertRecord(
                    alert_id=current,
                    severity="resolved",
                    created_at_utc=created_at,
                    resolved_at_utc=resolved_at,
                    notification_cleanup_alert_ids=_normalized_cleanup_ids(base),
                    notification_cleanup_overflow=base.notification_cleanup_overflow,
                ),
                current,
            )
            self._store.write(resolved)
            self._active_alert_id = None
            if resolved.notification_cleanup_overflow:
                self._record_cleanup_overflow(resolved.alert_id)
            self._retry_notification_cleanup(resolved, raise_failures=True)
            return

        self._observe_incident(state.incident_id, observed_at)

    def _retry_notification_cleanup(
        self,
        record: OperationsAlertRecord,
        *,
        raise_failures: bool,
    ) -> OperationsAlertRecord:
        current = record
        failed = False
        for alert_id in tuple(current.notification_cleanup_alert_ids):
            try:
                self._notifications.resolve(alert_id)
            except Exception:
                failed = True
                continue
            remaining = tuple(
                candidate
                for candidate in current.notification_cleanup_alert_ids
                if candidate != alert_id
            )
            updated = _replace_cleanup_ids(current, remaining)
            try:
                self._store.write(updated)
            except Exception:
                failed = True
                break
            current = updated
        if failed and raise_failures:
            raise RuntimeError("notification cleanup remains pending")
        return current

    def _record_cleanup_overflow(self, alert_id: SafeId) -> None:
        reporter = getattr(self._notifications, "record_cleanup_overflow", None)
        if not callable(reporter):
            return
        try:
            reporter(alert_id)
        except Exception:
            pass

    def observe_failure(self, observed_at_utc: datetime) -> None:
        observed_at = _UTC.validate_python(observed_at_utc, strict=True)
        self._observe_incident(_OPERATIONS_LOOP_FAILURE_INCIDENT, observed_at)

    def _observe_incident(self, incident_id: str, observed_at: datetime) -> None:
        existing = self._store.read()
        current = self._active_alert_id
        if current is None and existing is not None and existing.severity == "urgent":
            current = existing.alert_id
        alert_id = _opaque_alert_id(incident_id)
        current_record = existing
        if existing is None or existing.alert_id != alert_id or existing.severity != "urgent":
            created_at = _next_occurrence_time(observed_at, existing)
            cleanup_ids = (
                ()
                if existing is None
                else tuple(
                    cleanup_id
                    for cleanup_id in _normalized_cleanup_ids(existing)
                    if cleanup_id != alert_id
                )
            )
            current_record = OperationsAlertRecord(
                alert_id=alert_id,
                severity="urgent",
                created_at_utc=created_at,
                resolved_at_utc=None,
                notification_cleanup_alert_ids=cleanup_ids,
                notification_cleanup_overflow=(
                    False if existing is None else existing.notification_cleanup_overflow
                ),
            )
            if current is not None and current != alert_id:
                current_record, _ = _with_cleanup_id(current_record, current)
            self._store.write(current_record)
        self._active_alert_id = alert_id
        assert current_record is not None
        try:
            self._notifications.send_attention(alert_id)
        finally:
            if current_record.notification_cleanup_overflow:
                self._record_cleanup_overflow(alert_id)
        self._retry_notification_cleanup(current_record, raise_failures=False)


def _normalized_cleanup_ids(record: OperationsAlertRecord) -> tuple[SafeId, ...]:
    identifiers = list(record.notification_cleanup_alert_ids)
    if record.notification_cleanup_pending and record.alert_id not in identifiers:
        identifiers.append(record.alert_id)
    return tuple(identifiers)


def _replace_cleanup_ids(
    record: OperationsAlertRecord,
    identifiers: tuple[SafeId, ...],
    *,
    overflow: bool | None = None,
) -> OperationsAlertRecord:
    return OperationsAlertRecord(
        alert_id=record.alert_id,
        severity=record.severity,
        created_at_utc=record.created_at_utc,
        resolved_at_utc=record.resolved_at_utc,
        notification_cleanup_pending=False,
        notification_cleanup_alert_ids=identifiers,
        notification_cleanup_overflow=(
            record.notification_cleanup_overflow if overflow is None else overflow
        ),
    )


def _with_cleanup_id(
    record: OperationsAlertRecord,
    alert_id: SafeId | None,
) -> tuple[OperationsAlertRecord, bool]:
    identifiers = list(_normalized_cleanup_ids(record))
    if alert_id is None or alert_id in identifiers:
        return _replace_cleanup_ids(record, tuple(identifiers)), False
    overflowed = len(identifiers) == MAX_NOTIFICATION_CLEANUP_IDS
    if overflowed:
        identifiers = identifiers[1:]
    identifiers.append(alert_id)
    return (
        _replace_cleanup_ids(
            record,
            tuple(identifiers),
            overflow=record.notification_cleanup_overflow or overflowed,
        ),
        overflowed,
    )


def _next_occurrence_time(
    observed_at: datetime,
    existing: OperationsAlertRecord | None,
) -> datetime:
    if existing is None:
        return observed_at
    floor = max(existing.created_at_utc, existing.resolved_at_utc or existing.created_at_utc)
    if observed_at > floor:
        return observed_at
    try:
        return floor + timedelta(microseconds=1)
    except OverflowError as exc:
        raise ValueError("alert occurrence time is exhausted") from exc


__all__ = [
    "AtomicAlertRecordStore",
    "MAX_NOTIFICATION_CLEANUP_IDS",
    "OperationsAlertRecord",
    "OperationsAlertRouter",
]
