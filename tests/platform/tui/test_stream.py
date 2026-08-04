from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from vesper.platform.tui.ports import SourceSample
from vesper.platform.tui.stream import ProjectionLoop
from vesper.platform.tui.views import Freshness


NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


class FakeTime:
    def __init__(self) -> None:
        self.seconds = 0.0
        self._lock = threading.Lock()

    def monotonic(self) -> float:
        with self._lock:
            return self.seconds

    def utc_now(self) -> datetime:
        with self._lock:
            return NOW + timedelta(seconds=self.seconds)

    def advance(self, seconds: float) -> None:
        with self._lock:
            self.seconds += max(seconds, 0.000_001)


class AdvancingWaiter:
    def __init__(
        self,
        clock: FakeTime,
        *,
        stop_at: float | None = None,
    ) -> None:
        self._clock = clock
        self._stop_at = stop_at

    def __call__(self, stop_event: threading.Event, timeout: float) -> bool:
        self._clock.advance(timeout)
        time.sleep(0.000_5)
        if self._stop_at is not None and self._clock.monotonic() >= self._stop_at:
            stop_event.set()
        return stop_event.is_set()


@dataclass(frozen=True)
class BuiltSnapshot:
    number: int


class RecordingBuilder:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, SourceSample[object]], datetime, object | None]] = []

    def build(
        self,
        *,
        samples: Mapping[str, SourceSample[object]],
        generated_at_utc: datetime,
        previous: object | None = None,
    ) -> BuiltSnapshot:
        self.calls.append((dict(samples), generated_at_utc, previous))
        return BuiltSnapshot(len(self.calls))


class RecordingPublisher:
    def __init__(
        self,
        *,
        after_publish: Callable[[], None] | None = None,
    ) -> None:
        self.snapshots: list[object] = []
        self._after_publish = after_publish

    def publish_snapshot(self, snapshot: object) -> None:
        self.snapshots.append(snapshot)
        if self._after_publish is not None:
            self._after_publish()


class Reader:
    def __init__(self, values: list[object]) -> None:
        self._values = values
        self.calls = 0

    def read(self) -> object:
        index = min(self.calls, len(self._values) - 1)
        self.calls += 1
        value = self._values[index]
        if isinstance(value, BaseException):
            raise value
        return value


def fresh(value: str, *, observed_at: datetime = NOW) -> SourceSample[object]:
    return SourceSample[object](
        value=value,
        freshness=Freshness.FRESH,
        observed_at_utc=observed_at,
        source="test source",
        error=None,
    )


def unavailable(reason: str) -> SourceSample[object]:
    return SourceSample[object](
        value=None,
        freshness=Freshness.UNAVAILABLE,
        observed_at_utc=None,
        source="test source",
        error=reason,
    )


def stale(value: str, reason: str) -> SourceSample[object]:
    return SourceSample[object](
        value=value,
        freshness=Freshness.STALE,
        observed_at_utc=NOW,
        source="test source",
        error=reason,
    )


def run_loop(loop: ProjectionLoop, stop_event: threading.Event) -> None:
    thread = threading.Thread(target=loop.run, args=(stop_event,), daemon=True)
    thread.start()
    thread.join(timeout=2.0)
    if thread.is_alive():
        stop_event.set()
        thread.join(timeout=0.5)
    assert not thread.is_alive(), "projection loop did not stop"


def make_loop(
    *,
    sources: Mapping[str, object],
    clock: FakeTime,
    builder: RecordingBuilder,
    publisher: RecordingPublisher,
    stop_at: float | None = None,
) -> ProjectionLoop:
    return ProjectionLoop(
        sources=sources,
        builder=builder,
        publisher=publisher,
        monotonic_clock=clock.monotonic,
        utc_clock=clock.utc_now,
        waiter=AdvancingWaiter(clock, stop_at=stop_at),
    )


def test_coalesces_simultaneous_source_changes_into_one_snapshot() -> None:
    clock = FakeTime()
    stop_event = threading.Event()
    builder = RecordingBuilder()
    publisher = RecordingPublisher(after_publish=stop_event.set)
    loop = make_loop(
        sources={
            "native.agents": Reader([fresh("agents")]),
            "legacy.risk": Reader([fresh("risk")]),
        },
        clock=clock,
        builder=builder,
        publisher=publisher,
    )

    run_loop(loop, stop_event)

    assert len(publisher.snapshots) == 1
    assert len(builder.calls) == 1
    samples, generated_at, previous = builder.calls[0]
    assert samples["native.agents"].value == "agents"
    assert samples["legacy.risk"].value == "risk"
    assert generated_at >= NOW + timedelta(milliseconds=50)
    assert previous is None


def test_windows_source_polls_each_second_and_other_sources_each_five_seconds() -> None:
    clock = FakeTime()
    stop_event = threading.Event()
    windows = Reader([fresh("windows")])
    agents = Reader([fresh("agents")])
    loop = make_loop(
        sources={"windows.system": windows, "native.agents": agents},
        clock=clock,
        builder=RecordingBuilder(),
        publisher=RecordingPublisher(),
        stop_at=5.2,
    )

    run_loop(loop, stop_event)

    assert windows.calls == 6
    assert agents.calls == 2


def test_first_read_failure_is_unavailable_then_recovery_is_fresh() -> None:
    clock = FakeTime()
    stop_event = threading.Event()
    builder = RecordingBuilder()
    publisher = RecordingPublisher(
        after_publish=lambda: stop_event.set() if len(builder.calls) == 2 else None
    )
    loop = make_loop(
        sources={"windows.system": Reader([OSError("private detail"), fresh("ok")])},
        clock=clock,
        builder=builder,
        publisher=publisher,
    )

    run_loop(loop, stop_event)

    samples = [call[0]["windows.system"] for call in builder.calls]
    assert [sample.freshness for sample in samples] == [
        Freshness.UNAVAILABLE,
        Freshness.FRESH,
    ]
    assert samples[0].error == "Source read failed."
    assert "private detail" not in samples[0].model_dump_json()
    assert samples[1].value == "ok"


def test_boundary_assertion_from_reader_is_raised_on_loop_thread() -> None:
    class BoundarySpyReader:
        def read(self) -> SourceSample[object]:
            raise AssertionError("forbidden boundary reached")

    clock = FakeTime()
    stop_event = threading.Event()
    loop = make_loop(
        sources={"windows.system": BoundarySpyReader()},
        clock=clock,
        builder=RecordingBuilder(),
        publisher=RecordingPublisher(after_publish=stop_event.set),
    )

    with pytest.raises(AssertionError, match="forbidden boundary reached"):
        loop.run(stop_event)


def test_programmer_error_from_reader_is_raised_on_loop_thread() -> None:
    clock = FakeTime()
    stop_event = threading.Event()
    loop = make_loop(
        sources={"windows.system": Reader([TypeError("reader wiring bug")])},
        clock=clock,
        builder=RecordingBuilder(),
        publisher=RecordingPublisher(),
        stop_at=0.2,
    )

    with pytest.raises(TypeError, match="reader wiring bug"):
        loop.run(stop_event)


def test_unserializable_reader_value_fails_closed_as_unavailable() -> None:
    clock = FakeTime()
    stop_event = threading.Event()
    builder = RecordingBuilder()
    publisher = RecordingPublisher(after_publish=stop_event.set)
    malformed = SourceSample[object](
        value=object(),
        freshness=Freshness.FRESH,
        observed_at_utc=NOW,
        source="malformed test source",
        error=None,
    )
    loop = make_loop(
        sources={"windows.system": Reader([malformed])},
        clock=clock,
        builder=builder,
        publisher=publisher,
        stop_at=1.2,
    )

    run_loop(loop, stop_event)

    assert len(builder.calls) == 1
    sample = builder.calls[0][0]["windows.system"]
    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.value is None
    assert sample.error == "Source read failed."


def test_later_failure_retains_last_good_value_as_stale_then_recovers() -> None:
    clock = FakeTime()
    stop_event = threading.Event()
    builder = RecordingBuilder()
    publisher = RecordingPublisher(
        after_publish=lambda: stop_event.set() if len(builder.calls) == 3 else None
    )
    reader = Reader([fresh("held"), unavailable("feed stopped"), fresh("recovered")])
    loop = make_loop(
        sources={"windows.system": reader},
        clock=clock,
        builder=builder,
        publisher=publisher,
    )

    run_loop(loop, stop_event)

    samples = [call[0]["windows.system"] for call in builder.calls]
    assert [sample.freshness for sample in samples] == [
        Freshness.FRESH,
        Freshness.STALE,
        Freshness.FRESH,
    ]
    assert samples[1].value == "held"
    assert samples[1].observed_at_utc == NOW
    assert samples[1].error == "feed stopped"
    assert samples[2].value == "recovered"


def test_valid_stale_sample_is_retained_across_a_later_failure() -> None:
    clock = FakeTime()
    stop_event = threading.Event()
    builder = RecordingBuilder()
    publisher = RecordingPublisher(
        after_publish=lambda: stop_event.set() if len(builder.calls) == 2 else None
    )
    loop = make_loop(
        sources={
            "legacy.risk": Reader(
                [stale("legacy facts", "not broker-reconciled"), unavailable("read failed")]
            )
        },
        clock=clock,
        builder=builder,
        publisher=publisher,
    )

    run_loop(loop, stop_event)

    samples = [call[0]["legacy.risk"] for call in builder.calls]
    assert [sample.freshness for sample in samples] == [Freshness.STALE, Freshness.STALE]
    assert samples[1].value == "legacy facts"
    assert samples[1].observed_at_utc == NOW
    assert samples[1].error == "read failed"


def test_byte_identical_poll_does_not_build_or_publish_again() -> None:
    clock = FakeTime()
    stop_event = threading.Event()
    sample = fresh("same")
    builder = RecordingBuilder()
    publisher = RecordingPublisher()
    loop = make_loop(
        sources={"windows.system": Reader([sample])},
        clock=clock,
        builder=builder,
        publisher=publisher,
        stop_at=2.2,
    )

    run_loop(loop, stop_event)

    assert len(builder.calls) == 1
    assert len(publisher.snapshots) == 1


def test_a_blocked_source_never_overlaps_and_stop_remains_bounded() -> None:
    clock = FakeTime()
    stop_event = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    calls = 0
    active = 0
    maximum_active = 0

    class BlockingReader:
        def read(self) -> SourceSample[object]:
            nonlocal calls, active, maximum_active
            with lock:
                calls += 1
                active += 1
                maximum_active = max(maximum_active, active)
            release.wait(timeout=2.0)
            with lock:
                active -= 1
            return fresh("done")

    loop = make_loop(
        sources={"windows.system": BlockingReader()},
        clock=clock,
        builder=RecordingBuilder(),
        publisher=RecordingPublisher(),
        stop_at=3.1,
    )

    started = time.monotonic()
    run_loop(loop, stop_event)
    elapsed = time.monotonic() - started
    release.set()

    assert calls == 1
    assert maximum_active == 1
    assert elapsed < 0.5


@pytest.mark.parametrize(
    "sources",
    (
        {},
        {"system.windows": Reader([fresh("typo")])},
    ),
)
def test_rejects_empty_or_unknown_source_ids(sources: Mapping[str, object]) -> None:
    with pytest.raises(ValueError, match="source"):
        ProjectionLoop(
            sources=sources,
            builder=RecordingBuilder(),
            publisher=RecordingPublisher(),
        )
