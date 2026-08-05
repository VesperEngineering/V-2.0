from __future__ import annotations

from datetime import datetime, timedelta, timezone

from vesper.platform.tui.event_store import EventInput, EventStore
from vesper.platform.tui.projections.timeline import EventTimelineProjection
from vesper.platform.tui.views import Freshness


NOW = datetime(2026, 8, 3, 16, 0, tzinfo=timezone.utc)


def _event(index: int) -> EventInput:
    return EventInput(
        event_id=f"event:{index}",
        occurred_at_utc=NOW + timedelta(seconds=index),
        impact=index % 2 == 0,
        severity="active",
        summary=f"Event {index}",
        agent_id="v20-product",
        symbol="AAPL",
        model_id=None,
        approval_id=None,
        order_id=None,
        evidence_ids=(),
        work_id=None,
        source="native-platform",
    )


def test_event_timeline_projection_returns_fresh_newest_window(tmp_path) -> None:
    store = EventStore(tmp_path / "events.db")
    for index in range(1, 6):
        store.append(_event(index))

    sample = EventTimelineProjection(store, limit=2, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.FRESH
    assert sample.observed_at_utc == NOW
    assert sample.error is None
    assert sample.value is not None
    assert tuple(row.event_id for row in sample.value.rows) == ("event:4", "event:5")
    assert sample.value.hidden_event_count == 3
    assert sample.value.hidden_impact_event_count == 1
    assert sample.value.last_sequence == 5
    store.close()


def test_event_timeline_projection_proves_a_fresh_empty_store(tmp_path) -> None:
    store = EventStore(tmp_path / "events.db")

    sample = EventTimelineProjection(store, limit=100, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.FRESH
    assert sample.value is not None
    assert sample.value.rows == ()
    assert sample.value.hidden_event_count == 0
    assert sample.value.last_sequence == 0
    store.close()


def test_event_timeline_projection_fails_closed_for_closed_store_or_clock(tmp_path) -> None:
    store = EventStore(tmp_path / "events.db")
    store.close()
    closed = EventTimelineProjection(store, limit=100, clock=lambda: NOW).read()
    assert closed.freshness is Freshness.UNAVAILABLE
    assert closed.value is None
    assert closed.error == "Timeline event storage is unavailable."

    open_store = EventStore(tmp_path / "other.db")

    def failed_clock() -> datetime:
        raise OSError("clock unavailable")

    bad_clock = EventTimelineProjection(open_store, limit=100, clock=failed_clock).read()
    assert bad_clock.freshness is Freshness.UNAVAILABLE
    assert bad_clock.value is None
    assert bad_clock.error == "Timeline projection clock did not return UTC."
    open_store.close()
