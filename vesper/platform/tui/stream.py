"""Bounded polling and coalesced snapshot publication for TUI projections."""

from __future__ import annotations

import json
import queue
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, cast

from vesper.platform.tui.ports import SourceSample
from vesper.platform.tui.views import ConsoleSnapshot, Freshness


STABLE_SOURCE_IDS = frozenset(
    {
        "native.agents",
        "native.portfolio",
        "native.orders",
        "native.models",
        "legacy.risk",
        "native.data",
        "native.memory",
        "repository.system",
        "windows.system",
        "events.timeline",
    }
)
_FAST_SOURCE_ID = "windows.system"
_FAST_POLL_SECONDS = 1.0
_SLOW_POLL_SECONDS = 5.0
_COALESCE_SECONDS = 0.05
_MAX_WAIT_SECONDS = 0.05
_READ_FAILURE = "Source read failed."


class SampleReadPort(Protocol):
    def read(self) -> SourceSample[object]: ...


class SnapshotBuildPort(Protocol):
    def build(
        self,
        *,
        samples: Mapping[str, SourceSample[object]],
        generated_at_utc: datetime,
        previous: ConsoleSnapshot | None = None,
    ) -> ConsoleSnapshot: ...


class SnapshotPublishPort(Protocol):
    def publish_snapshot(self, snapshot: ConsoleSnapshot) -> None: ...


Waiter = Callable[[threading.Event, float], bool]


@dataclass(frozen=True, slots=True)
class _ReadOutcome:
    source_id: str
    sample: object | None
    failed: bool
    fatal: BaseException | None = None


class ProjectionLoop:
    """Poll stable read ports without overlap and publish complete replacements."""

    def __init__(
        self,
        *,
        sources: Mapping[str, SampleReadPort],
        builder: SnapshotBuildPort,
        publisher: SnapshotPublishPort,
        monotonic_clock: Callable[[], float] = time.monotonic,
        utc_clock: Callable[[], datetime] | None = None,
        waiter: Waiter | None = None,
    ) -> None:
        if not sources:
            raise ValueError("at least one projection source is required")
        unknown = set(sources).difference(STABLE_SOURCE_IDS)
        if unknown:
            raise ValueError("projection source ID is not recognized")
        if any(not callable(getattr(reader, "read", None)) for reader in sources.values()):
            raise TypeError("each projection source must provide read()")
        if not callable(getattr(builder, "build", None)):
            raise TypeError("snapshot builder must provide build()")
        if not callable(getattr(publisher, "publish_snapshot", None)):
            raise TypeError("snapshot publisher must provide publish_snapshot()")

        self._sources = dict(sources)
        self._builder = builder
        self._publisher = publisher
        self._monotonic = monotonic_clock
        self._utc_clock = utc_clock or (lambda: datetime.now(timezone.utc))
        self._waiter = waiter or (lambda stop, timeout: stop.wait(timeout))
        self._run_lock = threading.Lock()
        self._started = False

    def run(self, stop_event: threading.Event) -> None:
        """Run once until stopped; blocked reads are abandoned on daemon threads."""
        with self._run_lock:
            if self._started:
                raise RuntimeError("projection loop instances are single-use")
            self._started = True

        results: queue.SimpleQueue[_ReadOutcome] = queue.SimpleQueue()
        in_flight: set[str] = set()
        visible = {
            source_id: SourceSample[object](
                value=None,
                freshness=Freshness.LOADING,
                observed_at_utc=None,
                source=source_id,
                error=None,
            )
            for source_id in self._sources
        }
        encoded = {source_id: self._canonical(sample) for source_id, sample in visible.items()}
        last_good: dict[str, SourceSample[object]] = {}
        next_due = {source_id: self._monotonic() for source_id in self._sources}
        publish_due: float | None = None
        previous: ConsoleSnapshot | None = None

        while not stop_event.is_set():
            now = self._monotonic()
            if self._drain_results(
                results,
                in_flight=in_flight,
                visible=visible,
                encoded=encoded,
                last_good=last_good,
            ):
                publish_due = publish_due if publish_due is not None else now + _COALESCE_SECONDS

            for source_id, reader in self._sources.items():
                if source_id in in_flight or now < next_due[source_id]:
                    continue
                in_flight.add(source_id)
                next_due[source_id] = now + self._poll_seconds(source_id)
                self._launch_read(source_id, reader, results)

            now = self._monotonic()
            if self._drain_results(
                results,
                in_flight=in_flight,
                visible=visible,
                encoded=encoded,
                last_good=last_good,
            ):
                publish_due = publish_due if publish_due is not None else now + _COALESCE_SECONDS

            if publish_due is not None and now >= publish_due:
                snapshot = self._builder.build(
                    samples=dict(visible),
                    generated_at_utc=self._utc_clock(),
                    previous=previous,
                )
                self._publisher.publish_snapshot(snapshot)
                previous = snapshot
                publish_due = None

            if stop_event.is_set():
                break
            timeout = self._next_wait(
                now=self._monotonic(),
                in_flight=in_flight,
                next_due=next_due,
                publish_due=publish_due,
            )
            self._waiter(stop_event, timeout)

    @staticmethod
    def _launch_read(
        source_id: str,
        reader: SampleReadPort,
        results: queue.SimpleQueue[_ReadOutcome],
    ) -> None:
        def read_one() -> None:
            try:
                results.put(_ReadOutcome(source_id, reader.read(), False))
            except AssertionError as error:
                results.put(_ReadOutcome(source_id, None, False, error))
            except (OSError, RuntimeError, ValueError):
                results.put(_ReadOutcome(source_id, None, True))
            except Exception as error:
                results.put(_ReadOutcome(source_id, None, False, error))

        threading.Thread(
            target=read_one,
            name=f"tui-projection-{source_id}",
            daemon=True,
        ).start()

    @classmethod
    def _drain_results(
        cls,
        results: queue.SimpleQueue[_ReadOutcome],
        *,
        in_flight: set[str],
        visible: dict[str, SourceSample[object]],
        encoded: dict[str, bytes],
        last_good: dict[str, SourceSample[object]],
    ) -> bool:
        changed = False
        while True:
            try:
                outcome = results.get_nowait()
            except queue.Empty:
                return changed
            in_flight.discard(outcome.source_id)
            if outcome.fatal is not None:
                raise outcome.fatal
            previous_good = last_good.get(outcome.source_id)
            sample = cls._normalize(outcome, last_good)
            try:
                canonical = cls._canonical(sample)
            except (TypeError, ValueError):
                if previous_good is None:
                    last_good.pop(outcome.source_id, None)
                else:
                    last_good[outcome.source_id] = previous_good
                sample = cls._normalize(
                    _ReadOutcome(outcome.source_id, None, True),
                    last_good,
                )
                canonical = cls._canonical(sample)
            if canonical != encoded[outcome.source_id]:
                visible[outcome.source_id] = sample
                encoded[outcome.source_id] = canonical
                changed = True

    @staticmethod
    def _normalize(
        outcome: _ReadOutcome,
        last_good: dict[str, SourceSample[object]],
    ) -> SourceSample[object]:
        sample = outcome.sample
        if not outcome.failed and isinstance(sample, SourceSample):
            typed = cast(SourceSample[object], sample)
            if typed.freshness in {Freshness.FRESH, Freshness.STALE}:
                last_good[outcome.source_id] = typed
                return typed
            reason = typed.error or _READ_FAILURE
            source = typed.source
        else:
            reason = _READ_FAILURE
            source = outcome.source_id

        retained = last_good.get(outcome.source_id)
        if retained is not None:
            return SourceSample[object](
                value=retained.value,
                freshness=Freshness.STALE,
                observed_at_utc=retained.observed_at_utc,
                source=retained.source,
                error=reason,
            )
        return SourceSample[object](
            value=None,
            freshness=Freshness.UNAVAILABLE,
            observed_at_utc=None,
            source=source,
            error=reason,
        )

    @staticmethod
    def _canonical(sample: SourceSample[object]) -> bytes:
        return json.dumps(
            sample.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @staticmethod
    def _poll_seconds(source_id: str) -> float:
        if source_id == _FAST_SOURCE_ID:
            return _FAST_POLL_SECONDS
        return _SLOW_POLL_SECONDS

    @staticmethod
    def _next_wait(
        *,
        now: float,
        in_flight: set[str],
        next_due: Mapping[str, float],
        publish_due: float | None,
    ) -> float:
        deadlines = [due for source_id, due in next_due.items() if source_id not in in_flight]
        if publish_due is not None:
            deadlines.append(publish_due)
        if not deadlines:
            return _MAX_WAIT_SECONDS
        return min(_MAX_WAIT_SECONDS, max(0.0, min(deadlines) - now))


__all__ = [
    "ProjectionLoop",
    "SampleReadPort",
    "SnapshotBuildPort",
    "SnapshotPublishPort",
    "STABLE_SOURCE_IDS",
]
