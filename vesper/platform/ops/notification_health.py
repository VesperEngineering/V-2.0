"""Durable, generic health receipt for local notification delivery."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import TypeAdapter, model_validator

from vesper.platform.ops.supervisor import validate_state_root
from vesper.platform.tui.views import SafeId, StrictModel, UtcDateTime


_SAFE_ID = TypeAdapter(SafeId)
_UTC = TypeAdapter(UtcDateTime)
_HEALTH_FILE = "notification-health.json"


class NotificationHealthRecord(StrictModel):
    state: Literal["healthy", "failed"]
    code: Literal["notification-delivery-healthy", "notification-delivery-failed"]
    observed_at_utc: UtcDateTime

    @model_validator(mode="after")
    def require_matching_state_and_code(self) -> NotificationHealthRecord:
        expected = f"notification-delivery-{self.state}"
        if self.code != expected:
            raise ValueError("notification health state is invalid")
        return self


# Kept while the read-only projection migrates to the bidirectional record name.
NotificationFailureHealthRecord = NotificationHealthRecord


class AtomicNotificationFailureHealthSink:
    """Persist generic delivery health; never persist alert or backend details."""

    def __init__(
        self,
        state_root: Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable")
        self._state_root = validate_state_root(state_root, create=True)
        self._path = self._state_root / _HEALTH_FILE
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def path(self) -> Path:
        return self._path

    def record_notification_failure(self, alert_id: SafeId, code: SafeId) -> None:
        _SAFE_ID.validate_python(alert_id, strict=True)
        _SAFE_ID.validate_python(code, strict=True)
        self._record("failed", "notification-delivery-failed")

    def record_notification_healthy(self) -> None:
        self._record("healthy", "notification-delivery-healthy")

    def _record(
        self,
        state: Literal["healthy", "failed"],
        code: Literal["notification-delivery-healthy", "notification-delivery-failed"],
    ) -> None:
        observed_at = _UTC.validate_python(self._clock(), strict=True)
        self._write(
            NotificationHealthRecord(
                state=state,
                code=code,
                observed_at_utc=observed_at,
            )
        )

    def _write(self, record: NotificationHealthRecord) -> None:
        if type(record) is not NotificationHealthRecord:
            raise TypeError("record must be NotificationHealthRecord")
        payload = record.model_dump_json().encode("utf-8")
        temporary = self._state_root / f".{_HEALTH_FILE}.{uuid4().hex}.tmp"
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


__all__ = [
    "AtomicNotificationFailureHealthSink",
    "NotificationFailureHealthRecord",
    "NotificationHealthRecord",
]
