"""Pure cadence decisions; this module never installs or starts a scheduler."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Protocol


class SessionCalendar(Protocol):
    def session_close(self, session_date: date) -> datetime | None: ...


class CadencePolicy:
    EVENT_TYPES = frozenset(
        {
            "market-data-arrived",
            "research-requested",
            "model-artifact-changed",
            "validation-requested",
            "performance-data-arrived",
            "operator-action",
        }
    )

    def __init__(self, calendar: SessionCalendar) -> None:
        self.calendar = calendar

    def should_enqueue(self, event_type: str) -> bool:
        return event_type in self.EVENT_TYPES

    def digest_due(self, session_date: date, now: datetime) -> bool:
        close = self.calendar.session_close(session_date)
        return close is not None and now >= close + timedelta(minutes=15)
