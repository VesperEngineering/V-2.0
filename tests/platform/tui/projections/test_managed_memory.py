from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from vesper.platform.tui.projections.managed_memory import (
    ManagedMemoryProjection,
    MemoryContentStale,
    MemoryContentUnavailable,
)
from vesper.platform.tui.views import Freshness
from vesper.platform.tui.working_memory import (
    MemoryCandidate,
    MemoryValueScore,
    WorkingMemoryStore,
)


NOW = datetime(2026, 8, 4, 14, 30, tzinfo=timezone.utc)


def _score(value: int) -> MemoryValueScore:
    return MemoryValueScore(value, value, value, value, value, value)


def _candidate(memory_id: str, content: str, score: int) -> MemoryCandidate:
    return MemoryCandidate(
        memory_id=memory_id,
        content=content,
        scope="v20",
        category="durable-lesson",
        supported=True,
        evidence_ids=(f"evidence:{memory_id.rsplit(':', 1)[-1]}",),
        reason="Verified reusable V20 fact.",
        score=_score(score),
    )


def _populate(vault: Path) -> None:
    identifiers = iter(("change:one", "change:two"))
    with WorkingMemoryStore(
        vault,
        clock=lambda: NOW,
        id_factory=lambda: next(identifiers),
        candidate_validator=lambda _candidate: True,
    ) as store:
        store.propose(_candidate("memory:old", "old " * 1_500, 10))
        store.propose(_candidate("memory:best", "best " * 1_500, 20))
        store.curate("validated-work")


def test_projection_reads_core_and_archive_from_controller_ledger(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _populate(vault)

    sample = ManagedMemoryProjection(vault, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.FRESH
    assert sample.observed_at_utc == NOW
    assert sample.source == "managed V20 working memory"
    assert sample.error is None
    assert sample.value is not None
    assert [(row.memory_id, row.status) for row in sample.value.rows] == [
        ("memory:best", "core"),
        ("memory:old", "archived"),
    ]
    assert sample.value.rows[0].evidence_ids == ("evidence:best",)
    assert sample.value.rows[0].updated_at_utc == NOW
    assert len(sample.value.rows[0].summary) == 512
    assert sample.value.rows[0].summary.endswith("...")
    assert len(sample.value.history) == 1
    change = sample.value.history[0]
    assert change.event_id == "change:one"
    assert change.occurred_at_utc == NOW
    assert change.impact is True
    assert change.severity == "resolved"
    assert change.summary == (
        "Validated-work memory curation committed: 1 added to Core; 0 moved to archive. "
        "Reason: Controller curation after validated-work."
    )
    assert change.evidence_ids == ("evidence:best", "evidence:old")
    assert change.agent_id is None
    assert change.symbol is None
    assert change.model_id is None
    assert change.approval_id is None
    assert change.order_id is None
    assert sample.value.agent_usage_error == "No trusted memory-use source is configured."


def test_projection_reads_one_exact_full_memory_without_writing(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _populate(vault)
    before = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in vault.iterdir()
        if path.is_file()
    }
    projection = ManagedMemoryProjection(vault, clock=lambda: NOW)

    document = projection.read_content("memory:old", NOW)

    assert document.memory_id == "memory:old"
    assert document.updated_at_utc == NOW
    assert document.content == "old " * 1_500
    assert {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in vault.iterdir()
        if path.is_file()
    } == before


def test_projection_full_memory_rejects_stale_or_missing_binding(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _populate(vault)
    projection = ManagedMemoryProjection(vault, clock=lambda: NOW)

    with pytest.raises(MemoryContentStale):
        projection.read_content("memory:old", NOW - timedelta(microseconds=1))
    with pytest.raises(MemoryContentUnavailable):
        projection.read_content("memory:missing", NOW)


def test_projection_does_not_create_a_missing_vault(tmp_path: Path) -> None:
    vault = tmp_path / "missing"

    sample = ManagedMemoryProjection(vault, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.error == "Managed V20 working-memory ledger is not initialized."
    assert not vault.exists()


def test_projection_uses_a_read_only_sqlite_connection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    vault = tmp_path / "vault"
    with WorkingMemoryStore(vault) as store:
        assert store.core() == ()
    before = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in vault.iterdir()
        if path.is_file()
    }
    original_connect = sqlite3.connect
    calls: list[tuple[object, dict[str, object]]] = []

    def recording_connect(*args, **kwargs):
        calls.append((args[0], dict(kwargs)))
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(
        "vesper.platform.tui.projections.managed_memory.sqlite3.connect", recording_connect
    )

    sample = ManagedMemoryProjection(vault, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.FRESH
    assert len(calls) == 1
    assert "mode=ro" in str(calls[0][0])
    assert "immutable=1" in str(calls[0][0])
    assert calls[0][1]["uri"] is True
    assert calls[0][1]["isolation_level"] is None
    assert {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in vault.iterdir()
        if path.is_file()
    } == before


def test_projection_reads_committed_memory_from_a_live_wal_without_writing(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    identifiers = iter(("change:live",))
    store = WorkingMemoryStore(
        vault,
        clock=lambda: NOW,
        id_factory=lambda: next(identifiers),
        candidate_validator=lambda _candidate: True,
    )
    try:
        store.propose(_candidate("memory:live", "Live committed memory.", 10))
        store.curate("validated-work")
        wal = vault / ".working-memory.sqlite3-wal"
        assert wal.is_file() and wal.stat().st_size > 0
        before_names = {path.name for path in vault.iterdir() if path.is_file()}
        before = {
            path.name: (path.read_bytes(), path.stat().st_mtime_ns)
            for path in vault.iterdir()
            if path.is_file() and path.name != ".working-memory.sqlite3-shm"
        }

        sample = ManagedMemoryProjection(vault, clock=lambda: NOW).read()

        assert sample.freshness is Freshness.FRESH
        assert sample.value is not None
        assert [(row.memory_id, row.status) for row in sample.value.rows] == [
            ("memory:live", "core")
        ]
        assert sample.value.history[0].event_id == "change:live"
        assert {path.name for path in vault.iterdir() if path.is_file()} == before_names
        assert {
            path.name: (path.read_bytes(), path.stat().st_mtime_ns)
            for path in vault.iterdir()
            if path.is_file() and path.name != ".working-memory.sqlite3-shm"
        } == before
    finally:
        store.close()


def test_projection_rejects_tampered_candidate_content(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _populate(vault)
    database = vault / ".working-memory.sqlite3"
    with sqlite3.connect(database) as connection:
        raw = connection.execute(
            "SELECT candidate_json FROM memory_proposals WHERE memory_id = 'memory:best'"
        ).fetchone()[0]
        connection.execute(
            "UPDATE memory_proposals SET candidate_sha256 = ? WHERE memory_id = 'memory:best'",
            (hashlib.sha256((str(raw) + "tampered").encode("utf-8")).hexdigest(),),
        )
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    sample = ManagedMemoryProjection(vault, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.error == "Managed V20 working-memory ledger is invalid or unsafe."


def test_projection_rejects_unrecovered_prepared_change(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _populate(vault)
    database = vault / ".working-memory.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE memory_changes SET status = 'prepared' WHERE change_id = 'change:one'"
        )
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    sample = ManagedMemoryProjection(vault, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.error == "Managed V20 working memory has an unrecovered change."


def test_projection_fails_closed_when_clock_is_not_utc(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    with WorkingMemoryStore(vault):
        pass

    sample = ManagedMemoryProjection(
        vault,
        clock=lambda: datetime(2026, 8, 4, 14, 30),
    ).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.error == "Managed V20 working-memory projection clock is unavailable."


def test_projection_rejects_an_oversized_ledger_before_opening_it(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    with WorkingMemoryStore(vault):
        pass
    with (vault / ".working-memory.sqlite3").open("r+b") as database:
        database.truncate(64 * 1024 * 1024 + 1)

    sample = ManagedMemoryProjection(vault, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.error == "Managed V20 working memory exceeds bounded read limits."


def test_projection_rejects_core_word_overflow_without_writing(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _populate(vault)
    database = vault / ".working-memory.sqlite3"
    with sqlite3.connect(database) as connection:
        raw = connection.execute(
            "SELECT candidate_json FROM memory_proposals WHERE memory_id = 'memory:best'"
        ).fetchone()[0]
        candidate = json.loads(str(raw))
        candidate["content"] = "core " * 2_001
        candidate_json = json.dumps(
            candidate,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
        connection.execute(
            """
            UPDATE memory_proposals
            SET candidate_json = ?, candidate_sha256 = ?
            WHERE memory_id = 'memory:best'
            """,
            (
                candidate_json,
                hashlib.sha256(candidate_json.encode("utf-8")).hexdigest(),
            ),
        )
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    before = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in vault.iterdir()
        if path.is_file()
    }

    sample = ManagedMemoryProjection(vault, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.error == "Managed V20 Core Memory exceeds the 2,000-word limit."
    assert {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in vault.iterdir()
        if path.is_file()
    } == before


def test_projection_history_exposes_the_committed_receipt_reason(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _populate(vault)
    database = vault / ".working-memory.sqlite3"
    with sqlite3.connect(database) as connection:
        raw = connection.execute(
            "SELECT receipt_json FROM memory_changes WHERE change_id = 'change:one'"
        ).fetchone()[0]
        receipt = json.loads(str(raw))
        receipt["reason"] = "Private operator-only explanation."
        connection.execute(
            "UPDATE memory_changes SET receipt_json = ? WHERE change_id = 'change:one'",
            (
                json.dumps(
                    receipt,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                    allow_nan=False,
                ),
            ),
        )
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    sample = ManagedMemoryProjection(vault, clock=lambda: NOW).read()

    assert sample.value is not None
    assert sample.value.history[0].summary == (
        "Validated-work memory curation committed: 1 added to Core; 0 moved to archive. "
        "Reason: Private operator-only explanation."
    )


def test_projection_history_is_newest_first(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    identifiers = iter(("change:older", "change:newer"))
    current = [NOW]
    with WorkingMemoryStore(
        vault,
        clock=lambda: current[0],
        id_factory=lambda: next(identifiers),
        candidate_validator=lambda _candidate: True,
    ) as store:
        store.propose(_candidate("memory:first", "First durable fact.", 10))
        store.curate("validated-work")
        current[0] = NOW + timedelta(minutes=1)
        store.propose(_candidate("memory:second", "Second durable fact.", 20))
        store.curate("daily")

    sample = ManagedMemoryProjection(vault, clock=lambda: current[0]).read()

    assert sample.freshness is Freshness.FRESH
    assert sample.value is not None
    assert [row.event_id for row in sample.value.history] == [
        "change:newer",
        "change:older",
    ]
    assert [row.occurred_at_utc for row in sample.value.history] == [
        NOW + timedelta(minutes=1),
        NOW,
    ]


def test_projection_fails_closed_when_committed_history_exceeds_bound(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from vesper.platform.tui.projections import managed_memory

    vault = tmp_path / "vault"
    _populate(vault)
    with WorkingMemoryStore(
        vault,
        clock=lambda: NOW + timedelta(seconds=1),
        id_factory=lambda: "change:two",
    ) as store:
        store.curate("daily")
    before = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in vault.iterdir()
        if path.is_file()
    }
    monkeypatch.setattr(managed_memory, "_MAX_HISTORY_ROWS", 1)

    sample = ManagedMemoryProjection(vault, clock=lambda: NOW).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.error == "Managed V20 working memory exceeds bounded read limits."
    assert {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in vault.iterdir()
        if path.is_file()
    } == before
