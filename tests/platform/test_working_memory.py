from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from vesper.platform.contracts import WorkingMemoryCandidate, WorkingMemoryType
from vesper.platform.working_memory import WorkingMemoryStore


NOW = datetime(2026, 8, 4, 12, tzinfo=timezone.utc)


def candidate(
    memory_id: str,
    content: str,
    *,
    score: float = 0.8,
    safety_critical: bool = False,
) -> WorkingMemoryCandidate:
    return WorkingMemoryCandidate(
        memory_id=memory_id,
        agent_id="v20-development",
        memory_type=WorkingMemoryType.PROCEDURE,
        content=content,
        evidence_ids=(f"evidence-{memory_id}",),
        evidence=score,
        usefulness=score,
        reuse=score,
        relevance=score,
        age=score,
        safety_rarity=score,
        safety_critical=safety_critical,
        created_at=NOW,
    )


def test_working_memory_curates_under_word_cap_and_archives_lower_value(tmp_path):
    store = WorkingMemoryStore(tmp_path / "working-memory", max_words=5, clock=lambda: NOW)
    store.propose(candidate("high", "high value memory"))
    store.propose(candidate("low", "low value memory", score=0.1))
    store.propose(candidate("extra", "one two three four five six", score=0.9))

    change = store.curate("v20-development")

    assert change.word_count <= 5
    assert [item.memory_id for item in store.core("v20-development")] == ["high"]
    assert store.archive("v20-development")[0].memory_id == "low"
    assert (tmp_path / "working-memory" / "v20-development" / "Core Memory.md").exists()
    assert change.change_id


def test_working_memory_rollback_restores_previous_core(tmp_path):
    store = WorkingMemoryStore(tmp_path / "working-memory", max_words=20, clock=lambda: NOW)
    store.propose(candidate("first", "first durable memory"))
    first_change = store.curate("v20-development")
    store.propose(candidate("second", "second durable memory", score=0.9))
    second_change = store.curate("v20-development")

    store.rollback(second_change.change_id)

    assert [item.memory_id for item in store.core("v20-development")] == ["first"]


def test_working_memory_rejects_temporary_or_oversized_candidates(tmp_path):
    with pytest.raises(ValidationError, match="temporary|secret|credential"):
        candidate("todo", "TODO current blocker: add the API key")

    store = WorkingMemoryStore(tmp_path / "working-memory", max_words=2, clock=lambda: NOW)
    store.propose(candidate("too-large", "one two three"))

    with pytest.raises(ValueError, match="word cap"):
        store.curate("v20-development")
