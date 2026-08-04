"""Bounded read-only projection of persisted platform approvals and agent work."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, cast

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.types import Interrupt
from pydantic import BaseModel

from vesper.platform.agent_profiles import AUTONOMOUS_AGENT_ROLES
from vesper.platform.agent_queue import AgentWorkItem
from vesper.platform.contracts import (
    DataResearchResult,
    EvidenceArtifactRef,
    HumanApprovalDecision,
    HumanApprovalRequest,
    ModelEvaluationResult,
    RiskReviewDecision,
    SpecialistReceipt,
    TaskRequest,
    ValidationResult,
)
from vesper.platform.persistence import PlatformPaths
from vesper.platform.tui.ports import PlatformRuntimeFacts, SourceSample
from vesper.platform.tui.views import AgentCard, ApprovalRow, Freshness


_SOURCE = "native platform runtime"
_UNAVAILABLE = "Platform runtime state is unavailable."
_BOUNDS_EXCEEDED = "Platform runtime state exceeds bounded read limits."
_APPROVAL_REQUEST_PREFIX = "system.approval-requests"
_APPROVAL_DECISION_PREFIX = "system.approval-decisions"
_AGENT_WORK_PREFIX = "agent-work.items"
_MAX_APPROVAL_ROWS = 100
_MAX_WORK_ROWS = 10_000
_MAX_WRITES_PER_CHECKPOINT = 10_000
_MAX_VALUE_BYTES = 64 * 1024
_MAX_TOTAL_BYTES = 1024 * 1024
_BUSY_TIMEOUT_MS = 250
_SERDE = JsonPlusSerializer()
_CHECKPOINT_SCHEMA = {
    "thread_id": ("TEXT", 1, 1),
    "checkpoint_ns": ("TEXT", 1, 2),
    "checkpoint_id": ("TEXT", 1, 3),
    "parent_checkpoint_id": ("TEXT", 0, 0),
    "type": ("TEXT", 0, 0),
    "checkpoint": ("BLOB", 0, 0),
    "metadata": ("BLOB", 0, 0),
}
_WRITES_SCHEMA = {
    "thread_id": ("TEXT", 1, 1),
    "checkpoint_ns": ("TEXT", 1, 2),
    "checkpoint_id": ("TEXT", 1, 3),
    "task_id": ("TEXT", 1, 4),
    "idx": ("INTEGER", 1, 5),
    "channel": ("TEXT", 1, 0),
    "type": ("TEXT", 0, 0),
    "value": ("BLOB", 0, 0),
}
_STORE_SCHEMA = {
    "prefix": ("TEXT", 1, 1),
    "key": ("TEXT", 1, 2),
    "value": ("TEXT", 1, 0),
}


class _UnsafeRuntimeState(RuntimeError):
    pass


class _BoundedReadError(_UnsafeRuntimeState):
    pass


@dataclass(slots=True)
class _ReadBudget:
    total: int = 0

    def add(self, *values: object) -> None:
        for value in values:
            if value is None:
                continue
            if isinstance(value, str):
                body = value.encode("utf-8")
            elif isinstance(value, bytes):
                body = value
            else:
                raise _UnsafeRuntimeState
            if len(body) > _MAX_VALUE_BYTES:
                raise _BoundedReadError
            self.total += len(body)
            if self.total > _MAX_TOTAL_BYTES:
                raise _BoundedReadError


class PlatformRuntimeProjection:
    """Read existing runtime SQLite files without setup, migration, or writes."""

    def __init__(
        self,
        paths: PlatformPaths,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._paths = paths
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def read(self) -> SourceSample[PlatformRuntimeFacts]:
        try:
            observed_at = self._clock()
            _require_utc(observed_at)
            checkpoint_db, store_db = _validated_paths(self._paths)
            budget = _ReadBudget()
            with _readonly_database(store_db) as store_connection:
                _require_schema(store_connection, "store", _STORE_SCHEMA)
                approvals = _store_rows(
                    store_connection,
                    _APPROVAL_REQUEST_PREFIX,
                    _MAX_APPROVAL_ROWS,
                    budget,
                )
                work = _store_rows(
                    store_connection,
                    _AGENT_WORK_PREFIX,
                    _MAX_WORK_ROWS,
                    budget,
                )
                with _readonly_database(checkpoint_db) as checkpoint_connection:
                    _require_schema(
                        checkpoint_connection,
                        "checkpoints",
                        _CHECKPOINT_SCHEMA,
                    )
                    _require_schema(checkpoint_connection, "writes", _WRITES_SCHEMA)
                    pending = _pending_approvals(
                        approvals,
                        store_connection,
                        checkpoint_connection,
                        budget,
                    )
            facts = PlatformRuntimeFacts(
                pending_approvals=pending,
                active_work=_active_work(work, observed_at),
            )
            return SourceSample[PlatformRuntimeFacts](
                value=facts,
                freshness=Freshness.FRESH,
                observed_at_utc=observed_at,
                source=_SOURCE,
                error=None,
            )
        except _BoundedReadError:
            return _unavailable(_BOUNDS_EXCEEDED)
        except Exception:
            return _unavailable(_UNAVAILABLE)


def platform_runtime_control_binding(
    sample: SourceSample[PlatformRuntimeFacts],
) -> dict[str, object]:
    """Return deterministic command-prerequisite facts for Gateway hashing."""

    value = sample.value
    if value is not None and type(value) is not PlatformRuntimeFacts:
        raise TypeError("platform runtime sample contains an unexpected fact type")
    binding: dict[str, object] = {
        "available": value is not None,
        "freshness": sample.freshness.value,
    }
    if value is not None:
        binding["pending_approvals"] = [
            row.model_dump(mode="json")
            for row in sorted(value.pending_approvals, key=lambda item: item.approval_id)
        ]
        binding["active_work"] = [
            row.model_dump(mode="json")
            for row in sorted(value.active_work, key=lambda item: item.work_id)
        ]
    return binding


def _unavailable(reason: str) -> SourceSample[PlatformRuntimeFacts]:
    return SourceSample[PlatformRuntimeFacts](
        value=None,
        freshness=Freshness.UNAVAILABLE,
        observed_at_utc=None,
        source=_SOURCE,
        error=reason,
    )


def _require_utc(value: datetime) -> None:
    if (
        not isinstance(value, datetime)
        or value.utcoffset() is None
        or value.utcoffset() != timezone.utc.utcoffset(value)
    ):
        raise _UnsafeRuntimeState


def _normalized(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))


def _is_reparse(metadata: os.stat_result) -> bool:
    marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & marker
    )


def _validated_paths(paths: PlatformPaths) -> tuple[Path, Path]:
    root = Path(os.path.abspath(paths.root))
    metadata = root.lstat()
    if _is_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
        raise _UnsafeRuntimeState
    expected_checkpoint = root / "checkpoints.sqlite3"
    expected_store = root / "store.sqlite3"
    if _normalized(paths.checkpoint_db) != _normalized(expected_checkpoint) or _normalized(
        paths.store_db
    ) != _normalized(expected_store):
        raise _UnsafeRuntimeState
    for path in (expected_checkpoint, expected_store):
        file_metadata = path.lstat()
        if (
            _is_reparse(file_metadata)
            or not stat.S_ISREG(file_metadata.st_mode)
            or file_metadata.st_nlink != 1
        ):
            raise _UnsafeRuntimeState
    return expected_checkpoint, expected_store


@contextmanager
def _readonly_database(path: Path) -> Iterator[sqlite3.Connection]:
    with path.open("rb") as database:
        header = database.read(20)
    if len(header) != 20 or header[:16] != b"SQLite format 3\x00":
        raise _UnsafeRuntimeState
    if header[18:20] == b"\x02\x02":
        wal_mode = True
    elif header[18:20] == b"\x01\x01":
        wal_mode = False
    else:
        raise _UnsafeRuntimeState
    wal = Path(f"{path}-wal")
    shared_memory = Path(f"{path}-shm")
    wal_exists = _validated_auxiliary_file(wal)
    shared_memory_exists = _validated_auxiliary_file(shared_memory)
    if wal_exists != shared_memory_exists or (not wal_mode and wal_exists):
        raise _UnsafeRuntimeState
    immutable = wal_mode and not wal_exists
    uri = f"{path.as_uri()}?mode=ro"
    if immutable:
        uri += "&immutable=1"
    connection = sqlite3.connect(
        uri,
        uri=True,
        check_same_thread=False,
        isolation_level=None,
        timeout=_BUSY_TIMEOUT_MS / 1000,
    )
    try:
        connection.execute("PRAGMA query_only = ON")
        connection.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
        row = connection.execute("PRAGMA query_only").fetchone()
        if row != (1,):
            raise _UnsafeRuntimeState
        yield connection
    finally:
        connection.close()
        if immutable and (wal.exists() or shared_memory.exists()):
            raise _UnsafeRuntimeState


def _validated_auxiliary_file(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    if _is_reparse(metadata) or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise _UnsafeRuntimeState
    return True


def _require_schema(
    connection: sqlite3.Connection,
    table: str,
    required: Mapping[str, tuple[str, int, int]],
) -> None:
    kind = connection.execute(
        "SELECT type FROM sqlite_schema WHERE name = ?",
        (table,),
    ).fetchone()
    if kind != ("table",):
        raise _UnsafeRuntimeState
    rows = connection.execute(f"PRAGMA table_info('{table}')").fetchall()
    actual = {str(row[1]): (str(row[2]).upper(), int(row[3]), int(row[5])) for row in rows}
    if any(actual.get(name) != contract for name, contract in required.items()):
        raise _UnsafeRuntimeState


def _store_rows(
    connection: sqlite3.Connection,
    prefix: str,
    maximum: int,
    budget: _ReadBudget,
) -> tuple[tuple[str, str], ...]:
    cursor = connection.execute(
        "SELECT key, value FROM store WHERE prefix = ? ORDER BY key LIMIT ?",
        (prefix, maximum + 1),
    )
    rows: list[tuple[str, str]] = []
    for raw_key, raw_value in cursor:
        if len(rows) == maximum:
            raise _BoundedReadError
        if not isinstance(raw_key, str) or not isinstance(raw_value, (str, bytes)):
            raise _UnsafeRuntimeState
        budget.add(raw_key, raw_value)
        rows.append((raw_key, _text(raw_value)))
    return tuple(rows)


def _pending_approvals(
    rows: tuple[tuple[str, str], ...],
    store: sqlite3.Connection,
    checkpoints: sqlite3.Connection,
    budget: _ReadBudget,
) -> tuple[ApprovalRow, ...]:
    pending: list[ApprovalRow] = []
    for key, raw in rows:
        request = HumanApprovalRequest.model_validate_json(raw)
        if key != request.run_id:
            raise _UnsafeRuntimeState
        checkpoint, writes = _checkpoint_state(checkpoints, request, budget)
        _validate_pending_request(request, checkpoint, writes)
        decision = _approval_decision(store, request.run_id, budget)
        if decision is not None:
            _validate_decision(request, decision)
            continue
        pending.append(
            ApprovalRow(
                approval_id=request.request_id,
                run_id=request.run_id,
                checkpoint_id=request.checkpoint_id,
                state="pending",
                reason=request.summary,
                evidence_ids=tuple(item.artifact_id for item in request.evidence),
                requested_at_utc=request.created_at,
            )
        )
    pending.sort(key=lambda item: (item.requested_at_utc, item.approval_id))
    return tuple(pending)


def _approval_decision(
    store: sqlite3.Connection,
    run_id: str,
    budget: _ReadBudget,
) -> HumanApprovalDecision | None:
    row = store.execute(
        "SELECT key, value FROM store WHERE prefix = ? AND key = ? LIMIT 1",
        (_APPROVAL_DECISION_PREFIX, run_id),
    ).fetchone()
    if row is None:
        return None
    key, raw = row
    if not isinstance(key, str) or not isinstance(raw, (str, bytes)) or key != run_id:
        raise _UnsafeRuntimeState
    budget.add(key, raw)
    return HumanApprovalDecision.model_validate_json(_text(raw))


def _checkpoint_state(
    connection: sqlite3.Connection,
    request: HumanApprovalRequest,
    budget: _ReadBudget,
) -> tuple[Mapping[str, object], tuple[tuple[str, object], ...]]:
    row = connection.execute(
        "SELECT checkpoint_id, type, checkpoint, metadata FROM checkpoints "
        "WHERE thread_id = ? AND checkpoint_ns = '' "
        "ORDER BY checkpoint_id DESC LIMIT 1",
        (request.run_id,),
    ).fetchone()
    if row is None:
        raise _UnsafeRuntimeState
    checkpoint_id, checkpoint_type, checkpoint_blob, metadata = row
    budget.add(checkpoint_id, checkpoint_type, checkpoint_blob, metadata)
    if checkpoint_id != request.checkpoint_id:
        raise _UnsafeRuntimeState
    checkpoint = _SERDE.loads_typed((checkpoint_type, checkpoint_blob))
    if not isinstance(checkpoint, Mapping):
        raise _UnsafeRuntimeState
    if checkpoint.get("id") not in {None, checkpoint_id}:
        raise _UnsafeRuntimeState

    raw_writes = connection.execute(
        "SELECT task_id, channel, type, value FROM writes "
        "WHERE thread_id = ? AND checkpoint_ns = '' AND checkpoint_id = ? "
        "ORDER BY task_id, idx LIMIT ?",
        (request.run_id, checkpoint_id, _MAX_WRITES_PER_CHECKPOINT + 1),
    )
    writes: list[tuple[str, object]] = []
    for task_id, channel, value_type, value in raw_writes:
        if len(writes) == _MAX_WRITES_PER_CHECKPOINT:
            raise _BoundedReadError
        budget.add(task_id, channel, value_type, value)
        if not isinstance(channel, str):
            raise _UnsafeRuntimeState
        writes.append((channel, _SERDE.loads_typed((value_type, value))))
    return cast(Mapping[str, object], checkpoint), tuple(writes)


def _validate_pending_request(
    request: HumanApprovalRequest,
    checkpoint: Mapping[str, object],
    writes: tuple[tuple[str, object], ...],
) -> None:
    values = checkpoint.get("channel_values")
    if not isinstance(values, Mapping):
        raise _UnsafeRuntimeState
    task = _contract(TaskRequest, values.get("task"))
    if (
        request.run_id != task.run_id
        or request.task_id != task.task_id
        or request.repository_revision != task.repository_revision
        or values.get("status") != "awaiting-approval"
        or "branch:to:human_approval" not in values
        or values.get("branch:to:human_approval") is not None
        or values.get("reviewed_workspace_sha256") != request.workspace_sha256
        or _approval_evidence(values) != request.evidence
    ):
        raise _UnsafeRuntimeState
    interrupt_values = [value for channel, value in writes if channel == "__interrupt__"]
    if len(interrupt_values) != 1:
        raise _UnsafeRuntimeState
    encoded = interrupt_values[0]
    if not isinstance(encoded, Sequence) or isinstance(encoded, (str, bytes)) or len(encoded) != 1:
        raise _UnsafeRuntimeState
    interrupt = encoded[0]
    if not isinstance(interrupt, Interrupt) or not isinstance(interrupt.value, Mapping):
        raise _UnsafeRuntimeState
    if dict(interrupt.value) != {
        "request_id": request.request_id,
        "run_id": request.run_id,
        "task_id": request.task_id,
        "summary": request.summary,
    }:
        raise _UnsafeRuntimeState


def _contract(model: type[BaseModel], raw: object) -> BaseModel:
    if isinstance(raw, model):
        return raw
    return model.model_validate_json(json.dumps(raw))


def _approval_evidence(values: Mapping[str, object]) -> tuple[EvidenceArtifactRef, ...]:
    artifacts: list[EvidenceArtifactRef] = []
    raw_data = values.get("data_research")
    if raw_data is not None:
        artifacts.extend(cast(DataResearchResult, _contract(DataResearchResult, raw_data)).evidence)
    raw_model = values.get("model_evaluation")
    if raw_model is not None:
        artifacts.extend(
            cast(ModelEvaluationResult, _contract(ModelEvaluationResult, raw_model)).evidence
        )
    receipts = values.get("receipts", ())
    if not isinstance(receipts, Sequence) or isinstance(receipts, (str, bytes)):
        raise _UnsafeRuntimeState
    for raw_receipt in receipts:
        artifacts.extend(
            cast(SpecialistReceipt, _contract(SpecialistReceipt, raw_receipt)).evidence
        )
    raw_validation = values.get("validation")
    if raw_validation is not None:
        validation = cast(ValidationResult, _contract(ValidationResult, raw_validation))
        artifacts.extend(item for check in validation.checks for item in check.evidence)
    raw_risk = values.get("risk_review")
    if raw_risk is not None:
        artifacts.extend(cast(RiskReviewDecision, _contract(RiskReviewDecision, raw_risk)).evidence)
    return tuple(
        {(artifact.relative_path, artifact.sha256): artifact for artifact in artifacts}.values()
    )


def _validate_decision(
    request: HumanApprovalRequest,
    decision: HumanApprovalDecision,
) -> None:
    if (
        decision.run_id != request.run_id
        or decision.task_id != request.task_id
        or decision.repository_revision != request.repository_revision
        or decision.created_at != request.created_at
        or decision.request_id != request.request_id
        or decision.checkpoint_id != request.checkpoint_id
    ):
        raise _UnsafeRuntimeState


def _active_work(
    rows: tuple[tuple[str, str], ...],
    observed_at: datetime,
) -> tuple[AgentCard, ...]:
    active: list[tuple[AgentCard, datetime]] = []
    for key, raw in rows:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise _UnsafeRuntimeState
        if "title" not in payload:
            payload["title"] = payload.get("objective")
        item = AgentWorkItem.model_validate_json(json.dumps(payload))
        _require_utc(item.created_at)
        if key != item.work_id or item.role not in AUTONOMOUS_AGENT_ROLES:
            raise _UnsafeRuntimeState
        if item.status == "queued":
            if item.claimed_by is not None or item.lease_expires_at is not None:
                raise _UnsafeRuntimeState
            stage = "queued"
        elif item.status == "claimed":
            if not item.claimed_by or item.lease_expires_at is None:
                raise _UnsafeRuntimeState
            _require_utc(item.lease_expires_at)
            stage = "running" if item.lease_expires_at > observed_at else "waiting"
        else:
            continue
        active.append(
            (
                AgentCard(
                    work_id=item.work_id,
                    agent=item.role.value,
                    title=item.title,
                    stage=stage,
                    priority=item.priority,
                    urgent=False,
                    elapsed_seconds=None,
                    model="qwen:64k",
                    affected_areas=(),
                ),
                item.created_at,
            )
        )
    active.sort(key=lambda pair: (-pair[0].priority, pair[1], pair[0].work_id))
    return tuple(pair[0] for pair in active)


def _text(value: str | bytes) -> str:
    if isinstance(value, str):
        return value
    return value.decode("utf-8", errors="strict")


__all__ = ["PlatformRuntimeProjection", "platform_runtime_control_binding"]
