"""Independent local operations loop with atomic lifecycle records."""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import TypeAdapter

from vesper.platform.ops.policy import ActionDecision, OperationsPolicy, OperationsState
from vesper.platform.tui.views import NonEmptyStr, SafeId, StrictModel, UtcDateTime


_UTC = TypeAdapter(UtcDateTime)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_reparse_point(path: Path) -> bool:
    try:
        status = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise ValueError("state_root cannot be inspected safely") from error
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    attributes = getattr(status, "st_file_attributes", 0)
    return stat.S_ISLNK(status.st_mode) or bool(attributes & reparse_flag)


def validate_state_root(state_root: Path, *, create: bool = False) -> Path:
    """Accept only a narrow absolute local path with no reparse boundary."""

    if not isinstance(state_root, Path):
        raise TypeError("state_root must be Path")
    if not state_root.is_absolute():
        raise ValueError("state_root must be absolute")
    if state_root == Path(state_root.anchor):
        raise ValueError("state_root cannot be a filesystem root")
    for candidate in (state_root, *state_root.parents):
        if _is_reparse_point(candidate):
            raise ValueError("state_root cannot cross a reparse point")
    resolved = state_root.resolve(strict=False)
    if resolved == Path(resolved.anchor):
        raise ValueError("state_root cannot be a filesystem root")
    if create:
        resolved.mkdir(parents=True, exist_ok=True)
        if _is_reparse_point(resolved):
            raise ValueError("state_root cannot be a reparse point")
    return resolved


class DaemonHealthReceipt(StrictModel):
    run_id: SafeId
    healthy: bool
    state: Literal["running", "stopped", "failed"]
    observed_at_utc: UtcDateTime
    error: NonEmptyStr | None


class DaemonHeartbeatReceipt(StrictModel):
    run_id: SafeId
    sequence: int
    observed_at_utc: UtcDateTime
    decision_kind: SafeId
    decision_reason: NonEmptyStr


class DaemonCleanStopReceipt(StrictModel):
    run_id: SafeId
    clean: Literal[True]
    stopped_at_utc: UtcDateTime


class OperationsStateReader(Protocol):
    def read(self) -> OperationsState: ...


class OperationsExecutor(Protocol):
    def execute(self, decision: ActionDecision) -> None: ...


class AtomicDaemonStateStore:
    """Write complete JSON records, then atomically replace the visible file."""

    def __init__(self, state_root: Path) -> None:
        self._state_root = validate_state_root(state_root, create=True)

    @property
    def state_root(self) -> Path:
        return self._state_root

    def begin_run(self) -> None:
        clean_stop = self._state_root / "clean-stop.json"
        try:
            clean_stop.unlink()
        except FileNotFoundError:
            pass

    def write_health(self, receipt: DaemonHealthReceipt) -> None:
        self._write("health.json", receipt)

    def write_heartbeat(self, receipt: DaemonHeartbeatReceipt) -> None:
        self._write("heartbeat.json", receipt)

    def write_clean_stop(self, receipt: DaemonCleanStopReceipt) -> None:
        self._write("clean-stop.json", receipt)

    def _write(self, filename: str, receipt: StrictModel) -> None:
        if type(receipt) not in {
            DaemonHealthReceipt,
            DaemonHeartbeatReceipt,
            DaemonCleanStopReceipt,
        }:
            raise TypeError("unsupported daemon receipt")
        payload = receipt.model_dump_json(indent=None).encode("utf-8")
        destination = self._state_root / filename
        temporary = self._state_root / f".{filename}.{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


class OperationsSupervisor:
    """Run independently until its own stop event is set."""

    def __init__(
        self,
        policy: OperationsPolicy,
        state_reader: OperationsStateReader,
        executor: OperationsExecutor,
        state_store: AtomicDaemonStateStore,
        *,
        clock: Callable[[], datetime] = _utc_now,
        run_id: SafeId = "operations-daemon",
    ) -> None:
        if type(policy) is not OperationsPolicy:
            raise TypeError("policy must be OperationsPolicy")
        if type(state_store) is not AtomicDaemonStateStore:
            raise TypeError("state_store must be AtomicDaemonStateStore")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._policy = policy
        self._state_reader = state_reader
        self._executor = executor
        self._state_store = state_store
        self._clock = clock
        self._run_id = TypeAdapter(SafeId).validate_python(run_id, strict=True)

    def run(self, stop_event: Event) -> None:
        if not callable(getattr(stop_event, "is_set", None)) or not callable(
            getattr(stop_event, "wait", None)
        ):
            raise TypeError("stop_event must provide is_set and wait")
        self._state_store.begin_run()
        self._write_health(healthy=True, state="running", error=None)
        sequence = 0
        try:
            while not stop_event.is_set():
                state = self._state_reader.read()
                if type(state) is not OperationsState:
                    raise TypeError("state reader must return OperationsState")
                now = self._now()
                decision = self._policy.next_action(state, now)
                if type(decision) is not ActionDecision:
                    raise TypeError("operations policy returned an invalid decision")
                self._executor.execute(decision)
                sequence += 1
                self._state_store.write_heartbeat(
                    DaemonHeartbeatReceipt(
                        run_id=self._run_id,
                        sequence=sequence,
                        observed_at_utc=now,
                        decision_kind=decision.kind,
                        decision_reason=decision.reason,
                    )
                )
                self._write_health(healthy=True, state="running", error=None)
                if stop_event.wait(decision.pause_seconds):
                    break
        except Exception as error:
            message = f"Operations loop failed ({type(error).__name__})."
            self._write_health(
                healthy=False,
                state="failed",
                error=message,
            )
            raise
        stopped_at = self._now()
        self._state_store.write_health(
            DaemonHealthReceipt(
                run_id=self._run_id,
                healthy=True,
                state="stopped",
                observed_at_utc=stopped_at,
                error=None,
            )
        )
        self._state_store.write_clean_stop(
            DaemonCleanStopReceipt(
                run_id=self._run_id,
                clean=True,
                stopped_at_utc=stopped_at,
            )
        )

    def _write_health(
        self,
        *,
        healthy: bool,
        state: Literal["running", "stopped", "failed"],
        error: str | None,
    ) -> None:
        self._state_store.write_health(
            DaemonHealthReceipt(
                run_id=self._run_id,
                healthy=healthy,
                state=state,
                observed_at_utc=self._now(),
                error=error,
            )
        )

    def _now(self) -> datetime:
        return _UTC.validate_python(self._clock(), strict=True)
