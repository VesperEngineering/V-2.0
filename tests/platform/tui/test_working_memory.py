from __future__ import annotations

import dataclasses
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from vesper.platform.tui import working_memory as working_memory_module
from vesper.platform.tui.working_memory import (
    CORE_WORD_LIMIT,
    MemoryCandidate,
    MemoryValueScore,
    WorkingMemoryConflict,
    WorkingMemoryError,
    WorkingMemoryRejected,
    WorkingMemoryStore,
    default_vault_path,
    word_count,
)


NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def _score(value: int, *, safety_rarity: int = 0) -> MemoryValueScore:
    return MemoryValueScore(
        evidence=value,
        usefulness=value,
        reuse=value,
        relevance=value,
        age=value,
        safety_rarity=safety_rarity,
    )


def _candidate(
    memory_id: str,
    content: str,
    *,
    score: MemoryValueScore | None = None,
    category: str = "durable-lesson",
    supported: bool = True,
    scope: str = "v20",
    evidence_ids: tuple[str, ...] = ("evidence:1",),
    supersedes: tuple[str, ...] = (),
) -> MemoryCandidate:
    return MemoryCandidate(
        memory_id=memory_id,
        content=content,
        scope=scope,
        category=category,  # type: ignore[arg-type]
        supported=supported,
        evidence_ids=evidence_ids,
        reason="Verified reusable V20 fact.",
        score=_score(10) if score is None else score,
        supersedes=supersedes,
    )


def _store(vault: Path, **kwargs: object) -> WorkingMemoryStore:
    ids = iter(f"change:{index}" for index in range(100))
    kwargs.setdefault("candidate_validator", lambda _candidate: True)
    return WorkingMemoryStore(
        vault,
        clock=lambda: NOW,
        id_factory=lambda: next(ids),
        **kwargs,  # type: ignore[arg-type]
    )


def _front_matter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    front, _body = text[4:].split("\n---\n", 1)
    parsed = yaml.safe_load(front)
    assert isinstance(parsed, dict)
    return parsed


def _raise_after_files(_change_id: str) -> None:
    raise RuntimeError("ledger unavailable after files")


def _crash_after_files(vault: Path) -> None:
    store = WorkingMemoryStore(
        vault,
        clock=lambda: NOW,
        id_factory=lambda: "change:crashed",
        candidate_validator=lambda _candidate: True,
        after_files_written=lambda _change_id: os._exit(87),
    )
    store.propose(_candidate("memory:new", "new core fact", score=_score(30)))
    store.curate("validated-work")


def _hold_after_files(vault: Path, ready: object, release: object) -> None:
    def hold(_change_id: str) -> None:
        ready.set()  # type: ignore[attr-defined]
        if not release.wait(10):  # type: ignore[attr-defined]
            os._exit(88)

    store = WorkingMemoryStore(
        vault,
        clock=lambda: NOW,
        id_factory=lambda: "change:held",
        candidate_validator=lambda _candidate: True,
        after_files_written=hold,
    )
    store.propose(_candidate("memory:new", "new " * 1_100, score=_score(30)))
    store.curate("validated-work")
    store.close()


def test_contract_has_no_manual_pin_and_default_path_is_not_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    expected = tmp_path / "Documents" / "V20 Qwen Vault"
    assert default_vault_path() == expected
    assert not expected.exists()
    assert "pin" not in {field.name for field in dataclasses.fields(MemoryCandidate)}
    assert "pin" not in {field.name for field in dataclasses.fields(MemoryValueScore)}


@pytest.mark.parametrize(
    ("candidate", "reason"),
    (
        (_candidate("memory:scope", "general fact", scope="general"), "V20 scope"),
        (_candidate("memory:secret", "api_key = top-secret-value"), "secret"),
        (
            _candidate("memory:progress", "Task is in progress", category="task-progress"),
            "durable category",
        ),
        (
            _candidate("memory:blocker", "Waiting for this run", category="temporary-blocker"),
            "durable category",
        ),
        (
            _candidate(
                "memory:unsupported",
                "This might be true",
                category="unsupported-claim",
                supported=False,
            ),
            "supported",
        ),
        (
            _candidate("memory:no-evidence", "Claim", evidence_ids=()),
            "evidence",
        ),
        (
            dataclasses.replace(
                _candidate("memory:reason-secret", "Safe content"),
                reason="password = top-secret-value",
            ),
            "secret",
        ),
        (
            _candidate("memory:progress-disguised", "Task progress: tests are running."),
            "task progress",
        ),
        (
            _candidate(
                "memory:blocker-disguised",
                "Temporary blocker: waiting for network.",
            ),
            "temporary blocker",
        ),
        (
            _candidate("memory:unsupported-disguised", "Unverified: returns improve."),
            "unsupported claim",
        ),
        (
            _candidate("memory:github-token", "ghp_abcdefghijklmnopqrstuvwxyz1234567890"),
            "secret",
        ),
        (
            _candidate("memory:broker-secret", "ALPACA_SECRET_KEY = example-test-value"),
            "secret",
        ),
    ),
)
def test_propose_rejects_non_v20_secret_transient_and_unsupported_content(
    tmp_path: Path, candidate: MemoryCandidate, reason: str
) -> None:
    store = _store(tmp_path / "vault")
    with pytest.raises(WorkingMemoryRejected, match=reason):
        store.propose(candidate)
    assert store.core() == ()
    store.close()


def test_store_rejects_repository_knowledge_as_a_vault(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    forbidden = repository / "knowledge" / "managed"
    with pytest.raises(WorkingMemoryRejected, match="repository knowledge"):
        WorkingMemoryStore(forbidden, repository_root=repository)
    assert not forbidden.exists()


def test_proposal_replay_is_exact_and_conflicting_id_is_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path / "vault")
    candidate = _candidate("memory:one", "Controller facts outrank working memory.")
    first = store.propose(candidate)
    assert store.propose(candidate) == first
    with pytest.raises(WorkingMemoryConflict, match="different content"):
        store.propose(_candidate("memory:one", "Different content."))
    assert first.evidence_ids == ("evidence:1",)
    assert first.reason == "Verified reusable V20 fact."
    store.close()


def test_proposal_requires_controller_validation_not_candidate_self_attestation(
    tmp_path: Path,
) -> None:
    candidate = _candidate("memory:one", "V20 fact")
    no_validator = WorkingMemoryStore(tmp_path / "no-validator")
    with pytest.raises(WorkingMemoryRejected, match="controller validation"):
        no_validator.propose(candidate)
    no_validator.close()

    denied = WorkingMemoryStore(
        tmp_path / "denied",
        candidate_validator=lambda _candidate: False,
    )
    with pytest.raises(WorkingMemoryRejected, match="controller validation"):
        denied.propose(candidate)
    denied.close()


def test_core_is_v20_only_bounded_and_stronger_candidate_moves_weaker_to_archive(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "vault")
    weak = _candidate("memory:weak", "weak " * 1_200, score=_score(4))
    strong = _candidate("memory:strong", "strong " * 900, score=_score(20))
    store.propose(weak)
    store.propose(strong)

    change = store.curate("validated-work")

    assert tuple(item.memory_id for item in store.core()) == ("memory:strong",)
    assert word_count(store.core()) == 900
    assert word_count(store.core()) <= CORE_WORD_LIMIT
    assert all(item.scope == "v20" for item in store.core())
    assert tuple(item.memory_id for item in store.archive("weak")) == ("memory:weak",)
    assert change.added_ids == ("memory:strong",)
    assert change.evidence_ids == ("evidence:1",)
    assert "validated-work" in change.reason
    store.close()


def test_status_transition_updates_timestamp_without_changing_created_time(
    tmp_path: Path,
) -> None:
    later = NOW + timedelta(hours=1)
    current = NOW

    def clock() -> datetime:
        return current

    identifiers = iter(("change:initial", "change:replacement"))
    store = WorkingMemoryStore(
        tmp_path / "vault",
        clock=clock,
        id_factory=lambda: next(identifiers),
        candidate_validator=lambda _candidate: True,
    )
    store.propose(_candidate("memory:old", "old " * 1_500, score=_score(10)))
    store.curate("validated-work")
    current = later
    store.propose(_candidate("memory:new", "new " * 1_500, score=_score(20)))
    store.curate("validated-work")

    archived = store.archive("old")

    assert len(archived) == 1
    assert archived[0].memory_id == "memory:old"
    assert archived[0].created_at_utc == NOW
    assert archived[0].updated_at_utc == later
    store.close()


def test_new_item_timestamp_never_precedes_acceptance_when_clock_moves_back(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    current = NOW

    def clock() -> datetime:
        return current

    store = WorkingMemoryStore(
        vault,
        clock=clock,
        id_factory=lambda: "change:clock-rollback",
        candidate_validator=lambda _candidate: True,
    )
    store.propose(_candidate("memory:rollback", "Clock-safe memory."))
    current = NOW - timedelta(hours=1)

    store.curate("validated-work")

    item = store.core()[0]
    assert item.created_at_utc == NOW
    assert item.updated_at_utc == NOW
    core_metadata = _front_matter(vault / "Core Memory.md")
    assert core_metadata["created_utc"] == "2026-08-04T12:00:00Z"
    assert core_metadata["updated_utc"] == "2026-08-04T12:00:00Z"
    with sqlite3.connect(vault / ".working-memory.sqlite3") as connection:
        row = connection.execute(
            "SELECT created_at_utc, updated_at_utc FROM memory_items "
            "WHERE memory_id = 'memory:rollback'"
        ).fetchone()
    assert row == ("2026-08-04T12:00:00Z", "2026-08-04T12:00:00Z")
    store.close()


def test_rare_safety_fact_has_protected_score_floor(tmp_path: Path) -> None:
    store = _store(tmp_path / "vault")
    safety = _candidate(
        "memory:safety",
        "Fail closed on broker reconciliation. " * 400,
        score=_score(0, safety_rarity=100),
        category="safety-fact",
    )
    popular = _candidate(
        "memory:popular",
        "Frequently reused display preference. " * 400,
        score=_score(50),
    )
    assert safety.score.total > popular.score.total
    store.propose(popular)
    store.propose(safety)
    store.curate("validated-work")
    assert [item.memory_id for item in store.core()] == ["memory:safety"]
    store.close()


def test_unicode_word_count_and_deterministic_id_tie_break(tmp_path: Path) -> None:
    assert word_count("Résumé naïve 東京") == 3
    assert word_count("don't l’esprit") == 2
    store = _store(tmp_path / "vault")
    store.propose(_candidate("memory:z", "z " * 1_100, score=_score(10)))
    store.propose(_candidate("memory:a", "a " * 1_100, score=_score(10)))
    store.curate("daily")
    assert [item.memory_id for item in store.core()] == ["memory:a"]
    store.close()

    reopened = WorkingMemoryStore(tmp_path / "vault")
    assert [item.memory_id for item in reopened.core()] == ["memory:a"]
    reopened.close()


def test_obsidian_files_and_sqlite_history_include_required_provenance(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    store = _store(vault)
    store.propose(
        _candidate(
            "memory:one",
            "V20 controller validates memory changes.",
            score=_score(12),
            supersedes=("memory:older",),
        )
    )
    receipt = store.curate("validated-work")

    core_meta = _front_matter(vault / "Core Memory.md")
    history_meta = _front_matter(vault / "History" / "change%3A0.md")
    assert core_meta["id"] == "core-memory"
    assert core_meta["status"] == "core"
    assert core_meta["evidence_ids"] == ["evidence:1"]
    assert set(core_meta["score_components"]) == {
        "evidence",
        "usefulness",
        "reuse",
        "relevance",
        "age",
        "safety_rarity",
    }
    assert core_meta["supersedes"] == ["memory:older"]
    assert len(str(core_meta["content_sha256"])) == 64
    assert history_meta["id"] == receipt.change_id
    assert history_meta["status"] == "committed"

    with sqlite3.connect(vault / ".working-memory.sqlite3") as connection:
        assert connection.execute(
            "SELECT status FROM memory_changes WHERE change_id = ?", (receipt.change_id,)
        ).fetchone() == ("committed",)
    store.close()


def test_demotion_is_archived_and_rollback_restores_prior_core_exactly(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    store = _store(vault)
    store.propose(_candidate("memory:old", "old " * 1_100, score=_score(8)))
    first = store.curate("validated-work")
    expected_core = store.core()
    expected_bytes = (vault / "Core Memory.md").read_bytes()
    assert first.before_hash != first.after_hash

    store.propose(_candidate("memory:new", "new " * 1_100, score=_score(30)))
    second = store.curate("validated-work")
    assert [item.memory_id for item in store.core()] == ["memory:new"]
    assert [item.memory_id for item in store.archive("old")] == ["memory:old"]
    assert (vault / "Archive" / "memory%3Aold.md").exists()

    rollback = store.rollback(second.change_id)
    assert store.core() == expected_core
    assert (vault / "Core Memory.md").read_bytes() == expected_bytes
    assert rollback.restored_hash == second.before_hash
    assert rollback.after_hash == first.after_hash
    assert rollback.removed_ids == ("memory:new",)
    assert [item.memory_id for item in store.archive("new")] == ["memory:new"]
    assert [row.change_id for row in store.history()] == [
        rollback.change_id,
        second.change_id,
        first.change_id,
    ]
    store.close()


def test_archive_query_and_history_limits_are_strict(tmp_path: Path) -> None:
    store = _store(tmp_path / "vault")
    store.propose(_candidate("memory:weak", "Résumé archive", score=_score(1)))
    store.propose(_candidate("memory:strong", "other " * 2_000, score=_score(20)))
    store.curate("validated-work")
    assert [item.memory_id for item in store.archive("résumé", 1)] == ["memory:weak"]
    for query in ("", "   ", "x" * 257):
        with pytest.raises(ValueError):
            store.archive(query)
    for limit in (0, 101, True):
        with pytest.raises((TypeError, ValueError)):
            store.archive("archive", limit)  # type: ignore[arg-type]
        with pytest.raises((TypeError, ValueError)):
            store.history(limit)  # type: ignore[arg-type]
    store.close()


def test_file_failure_restores_before_images_and_records_rollback(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    healthy = _store(vault)
    healthy.propose(_candidate("memory:old", "old fact", score=_score(10)))
    healthy.curate("validated-work")
    before = (vault / "Core Memory.md").read_bytes()
    healthy.close()

    failing = WorkingMemoryStore(
        vault,
        clock=lambda: NOW,
        id_factory=lambda: "change:failed",
        candidate_validator=lambda _candidate: True,
        after_files_written=_raise_after_files,
    )
    failing.propose(_candidate("memory:new", "new fact", score=_score(20)))
    with pytest.raises(RuntimeError, match="ledger unavailable"):
        failing.curate("validated-work")
    assert (vault / "Core Memory.md").read_bytes() == before
    with sqlite3.connect(vault / ".working-memory.sqlite3") as connection:
        assert connection.execute(
            "SELECT status FROM memory_changes WHERE change_id = 'change:failed'"
        ).fetchone() == ("rolled_back",)
    failing.close()


def test_reopen_repairs_a_real_process_crash_between_files_and_commit(tmp_path: Path) -> None:
    import multiprocessing

    vault = tmp_path / "vault"
    initial = _store(vault)
    initial.propose(_candidate("memory:old", "old fact", score=_score(10)))
    initial.curate("validated-work")
    before = (vault / "Core Memory.md").read_bytes()
    initial.close()

    process = multiprocessing.get_context("spawn").Process(
        target=_crash_after_files,
        args=(vault,),
    )
    process.start()
    process.join(timeout=20)
    assert process.exitcode == 87
    assert (vault / "Core Memory.md").read_bytes() != before

    repaired = WorkingMemoryStore(vault)
    assert (vault / "Core Memory.md").read_bytes() == before
    assert [item.memory_id for item in repaired.core()] == ["memory:old"]
    with sqlite3.connect(vault / ".working-memory.sqlite3") as connection:
        assert connection.execute(
            "SELECT status FROM memory_changes WHERE change_id = 'change:crashed'"
        ).fetchone() == ("rolled_back",)
    repaired.close()


def test_live_writer_cannot_be_repaired_by_a_second_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import multiprocessing

    vault = tmp_path / "vault"
    initial = _store(vault)
    initial.propose(_candidate("memory:old", "old " * 1_100, score=_score(10)))
    initial.curate("validated-work")
    initial.close()

    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    process = context.Process(target=_hold_after_files, args=(vault, ready, release))
    process.start()
    assert ready.wait(timeout=20)
    monkeypatch.setattr(working_memory_module, "_LOCK_TIMEOUT_SECONDS", 0.2)
    with pytest.raises(WorkingMemoryError, match="writer lock"):
        WorkingMemoryStore(vault)

    release.set()
    process.join(timeout=20)
    assert process.exitcode == 0
    reopened = WorkingMemoryStore(vault)
    assert [item.memory_id for item in reopened.core()] == ["memory:new"]
    with sqlite3.connect(vault / ".working-memory.sqlite3") as connection:
        assert connection.execute(
            "SELECT status FROM memory_changes WHERE change_id = 'change:held'"
        ).fetchone() == ("committed",)
    reopened.close()


def test_reopen_fails_closed_when_the_ledger_schema_loses_a_table(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    store = _store(vault)
    store.propose(_candidate("memory:one", "durable fact"))
    store.curate("validated-work")
    core_before = (vault / "Core Memory.md").read_bytes()
    store.close()

    with sqlite3.connect(vault / ".working-memory.sqlite3") as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DROP TABLE memory_items")

    with pytest.raises(WorkingMemoryError, match="schema"):
        WorkingMemoryStore(vault)
    assert (vault / "Core Memory.md").read_bytes() == core_before
