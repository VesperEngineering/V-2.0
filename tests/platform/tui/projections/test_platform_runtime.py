from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from tests.platform.test_workflow import controller as workflow_controller
from tests.platform.test_workflow import task as workflow_task
from vesper.platform.agent_queue import AgentWorkItem, AgentWorkQueue
from vesper.platform.contracts import (
    AgentRole,
    ApprovalDecision,
    HumanApprovalDecision,
    HumanApprovalRequest,
)
from vesper.platform.persistence import (
    PlatformPaths,
    default_platform_paths,
    default_platform_root,
    open_persistence,
)
from vesper.platform.tui.ports import PlatformRuntimeFacts, SourceSample
from vesper.platform.tui.projections.platform_runtime import (
    PlatformRuntimeProjection,
    platform_runtime_control_binding,
)
from vesper.platform.tui.snapshot import ControlStateBuilder, SnapshotBuilder
from vesper.platform.tui.stream import STABLE_SOURCE_IDS
from vesper.platform.tui.views import ApprovalRow, Freshness


NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
_SERDE = JsonPlusSerializer()
_APPROVAL_REQUEST_PREFIX = "system.approval-requests"
_APPROVAL_DECISION_PREFIX = "system.approval-decisions"
_AGENT_WORK_PREFIX = "agent-work.items"


def _seed_runtime(paths: PlatformPaths, workspace: Path):
    with open_persistence(paths) as persistence:
        workflow, *_ = workflow_controller(persistence)
        view = workflow.start(workflow_task(workspace))
        queue = AgentWorkQueue(persistence.store)
        queue.enqueue(
            "work-queued",
            AgentRole.MODEL_RESEARCHER,
            "session-model",
            "Review the active model.",
            "Review the active model evidence.",
            50,
            NOW - timedelta(minutes=3),
        )
        queue.enqueue(
            "work-running",
            AgentRole.QUANT_RESEARCH_LEAD,
            "session-quant",
            "Inspect current data.",
            "Inspect current data coverage.",
            90,
            NOW - timedelta(minutes=2),
        )
        queue.claim("worker-running", NOW, lease_seconds=900)
        expired = AgentWorkItem(
            work_id="work-expired",
            role=AgentRole.PORTFOLIO_RESEARCHER,
            session_id="session-portfolio",
            title="Review portfolio weights.",
            objective="Review portfolio weights and evidence.",
            priority=80,
            created_at=NOW - timedelta(minutes=1),
            status="claimed",
            attempt=1,
            claimed_by="worker-expired",
            lease_expires_at=NOW - timedelta(seconds=1),
        )
        persistence.store.put(
            ("agent-work", "items"),
            expired.work_id,
            expired.model_dump(mode="json"),
        )
    return view


def _fingerprint(root: Path) -> tuple[tuple[str, int, int, str], ...]:
    return tuple(
        (
            path.relative_to(root).as_posix(),
            path.stat().st_size,
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def _store_value(paths: PlatformPaths, prefix: str, key: str) -> dict[str, object]:
    with sqlite3.connect(paths.store_db) as connection:
        row = connection.execute(
            "SELECT value FROM store WHERE prefix = ? AND key = ?",
            (prefix, key),
        ).fetchone()
    assert row is not None
    raw = row[0]
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def _put_store_value(
    paths: PlatformPaths,
    prefix: str,
    key: str,
    value: dict[str, object],
) -> None:
    with sqlite3.connect(paths.store_db) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO store (prefix, key, value) VALUES (?, ?, ?)",
            (prefix, key, json.dumps(value, separators=(",", ":"), sort_keys=True)),
        )


def _mutate_latest_checkpoint(paths: PlatformPaths, mutator) -> None:
    with sqlite3.connect(paths.checkpoint_db) as connection:
        row = connection.execute(
            "SELECT rowid, type, checkpoint FROM checkpoints "
            "WHERE thread_id = ? AND checkpoint_ns = '' "
            "ORDER BY checkpoint_id DESC LIMIT 1",
            ("run-001",),
        ).fetchone()
        assert row is not None
        checkpoint = _SERDE.loads_typed((row[1], row[2]))
        mutator(checkpoint)
        checkpoint_type, checkpoint_blob = _SERDE.dumps_typed(checkpoint)
        connection.execute(
            "UPDATE checkpoints SET type = ?, checkpoint = ? WHERE rowid = ?",
            (checkpoint_type, checkpoint_blob, row[0]),
        )


def _delete_interrupt(paths: PlatformPaths) -> None:
    with sqlite3.connect(paths.checkpoint_db) as connection:
        checkpoint_id = connection.execute(
            "SELECT checkpoint_id FROM checkpoints WHERE thread_id = ? "
            "AND checkpoint_ns = '' ORDER BY checkpoint_id DESC LIMIT 1",
            ("run-001",),
        ).fetchone()[0]
        connection.execute(
            "DELETE FROM writes WHERE thread_id = ? AND checkpoint_ns = '' "
            "AND checkpoint_id = ? AND channel = '__interrupt__'",
            ("run-001", checkpoint_id),
        )


def test_absent_platform_root_remains_absent(tmp_path: Path) -> None:
    paths = PlatformPaths.below(tmp_path / "missing-platform")

    sample = PlatformRuntimeProjection(paths, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert not paths.root.exists()


def test_default_platform_paths_require_local_appdata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    expected = (tmp_path / "V20" / "agent-platform").resolve()

    assert default_platform_root() == expected
    assert default_platform_paths() == PlatformPaths.below(expected)

    monkeypatch.delenv("LOCALAPPDATA")
    with pytest.raises(RuntimeError, match="LOCALAPPDATA"):
        default_platform_root()


def test_projection_reads_exact_pending_approval_and_active_queue_without_writes(
    tmp_path: Path,
) -> None:
    paths = PlatformPaths.below(tmp_path / "platform")
    view = _seed_runtime(paths, tmp_path)
    before = _fingerprint(paths.root)

    sample = PlatformRuntimeProjection(paths, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.FRESH
    assert sample.value is not None
    assert len(sample.value.pending_approvals) == 1
    approval = sample.value.pending_approvals[0]
    assert approval.approval_id == view.pending_approval.request_id
    assert approval.run_id == view.pending_approval.run_id
    assert approval.checkpoint_id == view.checkpoint_id
    assert approval.reason == view.pending_approval.summary
    assert approval.evidence_ids == tuple(
        item.artifact_id for item in view.pending_approval.evidence
    )
    assert tuple((row.work_id, row.stage) for row in sample.value.active_work) == (
        ("work-running", "running"),
        ("work-expired", "waiting"),
        ("work-queued", "queued"),
    )
    assert all(row.model == "qwen:64k" for row in sample.value.active_work)
    assert _fingerprint(paths.root) == before


@pytest.mark.parametrize(
    "corruption",
    ("checkpoint", "status", "next", "interrupt", "evidence", "workspace"),
)
def test_projection_rejects_approval_without_every_exact_checkpoint_fact(
    tmp_path: Path,
    corruption: str,
) -> None:
    paths = PlatformPaths.below(tmp_path / "platform")
    _seed_runtime(paths, tmp_path)
    if corruption == "checkpoint":
        raw = _store_value(paths, _APPROVAL_REQUEST_PREFIX, "run-001")
        raw["checkpoint_id"] = "checkpoint-other"
        _put_store_value(paths, _APPROVAL_REQUEST_PREFIX, "run-001", raw)
    elif corruption == "status":
        _mutate_latest_checkpoint(
            paths,
            lambda checkpoint: checkpoint["channel_values"].__setitem__("status", "accepted"),
        )
    elif corruption == "next":
        _mutate_latest_checkpoint(
            paths,
            lambda checkpoint: checkpoint["channel_values"].pop("branch:to:human_approval"),
        )
    elif corruption == "interrupt":
        _delete_interrupt(paths)
    elif corruption == "evidence":
        _mutate_latest_checkpoint(
            paths,
            lambda checkpoint: checkpoint["channel_values"].__setitem__("risk_review", None),
        )
    else:
        _mutate_latest_checkpoint(
            paths,
            lambda checkpoint: checkpoint["channel_values"].__setitem__(
                "reviewed_workspace_sha256", "c" * 64
            ),
        )

    sample = PlatformRuntimeProjection(paths, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.value is None


def test_projection_excludes_an_exact_decided_approval(tmp_path: Path) -> None:
    paths = PlatformPaths.below(tmp_path / "platform")
    _seed_runtime(paths, tmp_path)
    request = HumanApprovalRequest.model_validate_json(
        json.dumps(_store_value(paths, _APPROVAL_REQUEST_PREFIX, "run-001"))
    )
    decision = HumanApprovalDecision(
        run_id=request.run_id,
        task_id=request.task_id,
        repository_revision=request.repository_revision,
        created_at=request.created_at,
        approval_id="approval-decided",
        request_id=request.request_id,
        checkpoint_id=request.checkpoint_id,
        operator_id="operator-test",
        decision=ApprovalDecision.APPROVE,
        reason="Approved in test.",
        decided_at=NOW,
    )
    _put_store_value(
        paths,
        _APPROVAL_DECISION_PREFIX,
        request.run_id,
        decision.model_dump(mode="json"),
    )

    sample = PlatformRuntimeProjection(paths, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.FRESH
    assert sample.value is not None
    assert sample.value.pending_approvals == ()


def test_projection_rejects_a_conflicting_decision(tmp_path: Path) -> None:
    paths = PlatformPaths.below(tmp_path / "platform")
    _seed_runtime(paths, tmp_path)
    request = _store_value(paths, _APPROVAL_REQUEST_PREFIX, "run-001")
    decision = {
        **request,
        "approval_id": "approval-conflict",
        "request_id": "another-request",
        "operator_id": "operator-test",
        "decision": "approve",
        "reason": "Conflicting decision.",
        "decided_at": NOW.isoformat(),
    }
    decision.pop("workspace_sha256")
    decision.pop("summary")
    decision.pop("evidence")
    _put_store_value(paths, _APPROVAL_DECISION_PREFIX, "run-001", decision)

    sample = PlatformRuntimeProjection(paths, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.value is None


def _empty_databases(paths: PlatformPaths) -> None:
    with open_persistence(paths):
        pass


def _insert_store_rows(
    paths: PlatformPaths,
    prefix: str,
    rows: list[tuple[str, str]],
) -> None:
    with sqlite3.connect(paths.store_db) as connection:
        connection.executemany(
            "INSERT INTO store (prefix, key, value) VALUES (?, ?, ?)",
            ((prefix, key, value) for key, value in rows),
        )


@pytest.mark.parametrize(
    ("prefix", "count"),
    ((_APPROVAL_REQUEST_PREFIX, 101), (_AGENT_WORK_PREFIX, 10_001)),
)
def test_projection_rejects_row_limit_overflow(
    tmp_path: Path,
    prefix: str,
    count: int,
) -> None:
    paths = PlatformPaths.below(tmp_path / "platform")
    _empty_databases(paths)
    _insert_store_rows(
        paths,
        prefix,
        [(f"row-{index}", "{}") for index in range(count)],
    )

    sample = PlatformRuntimeProjection(paths, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.error == "Platform runtime state exceeds bounded read limits."


def test_projection_rejects_one_oversized_value(tmp_path: Path) -> None:
    paths = PlatformPaths.below(tmp_path / "platform")
    _empty_databases(paths)
    _insert_store_rows(
        paths,
        _AGENT_WORK_PREFIX,
        [("oversized", "x" * (64 * 1024 + 1))],
    )

    sample = PlatformRuntimeProjection(paths, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.error == "Platform runtime state exceeds bounded read limits."


def test_projection_rejects_total_value_overflow(tmp_path: Path) -> None:
    paths = PlatformPaths.below(tmp_path / "platform")
    _empty_databases(paths)
    rows = []
    for index in range(18):
        item = AgentWorkItem(
            work_id=f"work-{index}",
            role=AgentRole.MODEL_RESEARCHER,
            session_id=f"session-{index}",
            title="Bounded title.",
            objective="x" * 60_000,
            priority=1,
            created_at=NOW,
            status="queued",
            attempt=0,
        )
        rows.append(
            (
                item.work_id,
                json.dumps(item.model_dump(mode="json"), separators=(",", ":")),
            )
        )
    _insert_store_rows(paths, _AGENT_WORK_PREFIX, rows)

    sample = PlatformRuntimeProjection(paths, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.error == "Platform runtime state exceeds bounded read limits."


def test_runtime_facts_project_into_agents_and_approvals_and_bind_control() -> None:
    facts = PlatformRuntimeFacts(
        pending_approvals=(),
        active_work=(),
    )
    sample = SourceSample[PlatformRuntimeFacts](
        value=facts,
        freshness=Freshness.FRESH,
        observed_at_utc=NOW,
        source="native platform runtime",
        error=None,
    )

    snapshot = SnapshotBuilder().build(
        samples={"platform.runtime": sample},
        generated_at_utc=NOW,
    )
    binding = platform_runtime_control_binding(sample)

    assert "platform.runtime" in STABLE_SOURCE_IDS
    assert snapshot.agents.rows == ()
    assert snapshot.risk.approvals == ()
    assert binding == {
        "available": True,
        "freshness": "fresh",
        "pending_approvals": [],
        "active_work": [],
    }
    assert (
        ControlStateBuilder().build({}).hash
        != ControlStateBuilder().build({"platform.runtime": sample}).hash
    )


def test_runtime_approval_stays_visible_as_partial_stale_without_risk_limits() -> None:
    approval = ApprovalRow(
        approval_id="approval-visible",
        run_id="run-visible",
        checkpoint_id="checkpoint-visible",
        state="pending",
        reason="Operator decision required.",
        evidence_ids=("evidence-visible",),
        requested_at_utc=NOW,
        affected_symbols=(),
        weight_changes=(),
        risks=(),
        expected_consequences=(),
        basis_sha256=None,
        stale_reason=None,
    )
    sample = SourceSample[PlatformRuntimeFacts](
        value=PlatformRuntimeFacts(pending_approvals=(approval,), active_work=()),
        freshness=Freshness.FRESH,
        observed_at_utc=NOW,
        source="native platform runtime",
        error=None,
    )

    snapshot = SnapshotBuilder().build(
        samples={"platform.runtime": sample},
        generated_at_utc=NOW,
    )

    assert snapshot.risk.approvals == (approval,)
    assert snapshot.risk.freshness is Freshness.STALE
    assert snapshot.risk.as_of_utc == NOW
    assert "limits" in snapshot.risk.error.lower()


def test_retained_runtime_approval_is_labeled_stale_not_current() -> None:
    approval = ApprovalRow(
        approval_id="approval-retained",
        run_id="run-retained",
        checkpoint_id="checkpoint-retained",
        state="pending",
        reason="Operator decision required.",
        evidence_ids=("evidence-retained",),
        requested_at_utc=NOW,
        affected_symbols=(),
        weight_changes=(),
        risks=(),
        expected_consequences=(),
        basis_sha256=None,
        stale_reason=None,
    )
    sample = SourceSample[PlatformRuntimeFacts](
        value=PlatformRuntimeFacts(pending_approvals=(approval,), active_work=()),
        freshness=Freshness.STALE,
        observed_at_utc=NOW,
        source="native platform runtime",
        error="Runtime read failed; showing retained state.",
    )

    snapshot = SnapshotBuilder().build(
        samples={"platform.runtime": sample},
        generated_at_utc=NOW,
    )

    assert snapshot.risk.approvals == (approval,)
    assert snapshot.risk.freshness is Freshness.STALE
    assert "retained" in snapshot.risk.error.lower()
    assert "current" not in snapshot.risk.error.lower()


def test_unavailable_runtime_approval_source_is_visible_on_risk_screen() -> None:
    sample = SourceSample[PlatformRuntimeFacts](
        value=None,
        freshness=Freshness.UNAVAILABLE,
        observed_at_utc=None,
        source="native platform runtime",
        error="Runtime read failed.",
    )

    snapshot = SnapshotBuilder().build(
        samples={"platform.runtime": sample},
        generated_at_utc=NOW,
    )

    assert snapshot.risk.approvals == ()
    assert snapshot.risk.freshness is Freshness.UNAVAILABLE
    assert "approvals are unavailable" in snapshot.risk.error.lower()
    assert "runtime read failed" in snapshot.risk.error.lower()


def test_projection_rejects_missing_required_schema_without_recreating_it(
    tmp_path: Path,
) -> None:
    paths = PlatformPaths.below(tmp_path / "platform")
    _empty_databases(paths)
    with sqlite3.connect(paths.store_db) as connection:
        connection.execute("DROP TABLE store")

    sample = PlatformRuntimeProjection(paths, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    with sqlite3.connect(paths.store_db) as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'store'"
            ).fetchone()
            is None
        )


def test_projection_rejects_corrupt_database(tmp_path: Path) -> None:
    paths = PlatformPaths.below(tmp_path / "platform")
    _empty_databases(paths)
    paths.store_db.write_bytes(b"not-a-sqlite-database")

    sample = PlatformRuntimeProjection(paths, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE


def test_projection_rejects_non_regular_database(tmp_path: Path) -> None:
    paths = PlatformPaths.below(tmp_path / "platform")
    _empty_databases(paths)
    paths.store_db.unlink()
    paths.store_db.mkdir()

    sample = PlatformRuntimeProjection(paths, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE


def test_projection_rejects_symlink_database(tmp_path: Path) -> None:
    paths = PlatformPaths.below(tmp_path / "platform")
    _empty_databases(paths)
    linked = tmp_path / "linked-store.sqlite3"
    shutil.copy2(paths.store_db, linked)
    paths.store_db.unlink()
    try:
        paths.store_db.symlink_to(linked)
    except OSError as error:
        pytest.skip(f"symlink creation is unavailable: {error}")

    sample = PlatformRuntimeProjection(paths, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE


def test_projection_fails_closed_when_database_is_busy(tmp_path: Path) -> None:
    paths = PlatformPaths.below(tmp_path / "platform")
    _empty_databases(paths)
    with sqlite3.connect(paths.store_db, isolation_level=None) as lock:
        lock.execute("PRAGMA journal_mode = DELETE")
        lock.execute("BEGIN EXCLUSIVE")

        sample = PlatformRuntimeProjection(paths, clock=lambda: NOW).read()

        lock.execute("ROLLBACK")
    assert sample.freshness is Freshness.UNAVAILABLE


def test_projection_never_constructs_controller_service_or_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = PlatformPaths.below(tmp_path / "platform")
    _seed_runtime(paths, tmp_path)
    from vesper.platform import evidence, service, workflow

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("forbidden runtime constructor reached")

    monkeypatch.setattr(service.LocalPlatformService, "__init__", forbidden)
    monkeypatch.setattr(workflow.WorkflowController, "__init__", forbidden)
    monkeypatch.setattr(evidence.FilesystemEvidenceStore, "__init__", forbidden)

    sample = PlatformRuntimeProjection(paths, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.FRESH
