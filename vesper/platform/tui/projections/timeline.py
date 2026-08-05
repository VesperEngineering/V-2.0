"""Bounded read projection for the TUI-local append-only event store."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from vesper.platform.tui.event_store import EventStore
from vesper.platform.tui.ports import SourceSample, TimelineFacts
from vesper.platform.tui.views import Freshness, TimelineRow


_SOURCE = "tui event store"


class EventTimelineProjection:
    """Read one newest event window without creating or mutating storage."""

    def __init__(
        self,
        store: EventStore,
        *,
        limit: int,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if type(store) is not EventStore:
            raise TypeError("store must be EventStore")
        if type(limit) is not int or not 1 <= limit <= 10_000:
            raise ValueError("limit must be between 1 and 10000")
        self._store = store
        self._limit = limit
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def read(self) -> SourceSample[TimelineFacts]:
        try:
            observed_at = self._clock()
            if (
                not isinstance(observed_at, datetime)
                or observed_at.tzinfo is None
                or observed_at.utcoffset() != timedelta(0)
            ):
                raise ValueError("clock did not return UTC")
        except (OSError, RuntimeError, TypeError, ValueError):
            return self._unavailable("Timeline projection clock did not return UTC.")
        try:
            window = self._store.latest(self._limit)
            rows = tuple(
                TimelineRow.model_validate(
                    event.model_dump(
                        mode="python",
                        exclude={"source", "sequence"},
                    ),
                    strict=True,
                )
                for event in window.events
            )
            facts = TimelineFacts(
                rows=rows,
                hidden_event_count=window.hidden_event_count,
                hidden_impact_event_count=window.hidden_impact_event_count,
                last_sequence=window.last_sequence,
            )
        except (OSError, RuntimeError, sqlite3.DatabaseError, ValidationError, ValueError):
            return self._unavailable("Timeline event storage is unavailable.")
        return SourceSample[TimelineFacts](
            value=facts,
            freshness=Freshness.FRESH,
            observed_at_utc=observed_at,
            source=_SOURCE,
            error=None,
        )

    @staticmethod
    def _unavailable(reason: str) -> SourceSample[TimelineFacts]:
        return SourceSample[TimelineFacts](
            value=None,
            freshness=Freshness.UNAVAILABLE,
            observed_at_utc=None,
            source=_SOURCE,
            error=reason,
        )
