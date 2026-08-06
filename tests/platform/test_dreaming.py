from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from vesper.platform.dreaming import MAX_DREAM_SESSION_CHARS, DreamGate


NOW = datetime(2026, 8, 4, 23, 0, tzinfo=timezone.utc)


class FakeDreamClient:
    def __init__(self, content: str):
        self.content = content
        self.calls = []

    def chat(self, messages, *, response_format=None):
        self.calls.append((messages, response_format))
        return SimpleNamespace(content=self.content)


def _write_active_note(vault):
    path = vault / "memory" / "v20-core" / "current.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\nvesper_id: current-memory\nvesper_kind: memory\n"
        "vesper_status: approved\nvesper_scope: shared\ntitle: Current\n---\n\n"
        "# Current\n\nKeep validated facts.\n",
        encoding="utf-8",
    )
    return path


def test_dream_gate_writes_report_and_applies_memory_learning(tmp_path):
    vault = tmp_path / "knowledge"
    active = _write_active_note(vault)
    session = vault / "sessions" / "2026-08-04.md"
    session.parent.mkdir(parents=True)
    session.write_text(
        "---\nkind: session-transcript\n---\n\n"
        "## Event 1 — user / message\n\n"
        "We repeatedly chose controller validation before promotion.\n",
        encoding="utf-8",
    )
    client = FakeDreamClient(
        json.dumps(
            {
                "proposals": [
                    {
                        "proposal_id": "proposal-1",
                        "proposal_type": "update",
                        "target": "knowledge/memory/v20-core/current.md",
                        "summary": "Clarify controller validation.",
                        "evidence": "Repeated session summary.",
                        "confidence": "high",
                    }
                ]
            }
        )
    )
    gate = DreamGate(vault, client=client, clock=lambda: NOW, id_factory=lambda: "dream-1")

    report = gate.run()

    assert report.dream_id == "dream-1"
    assert report.model == "qwen:64k"
    assert report.proposals[0].auto_apply is True
    assert report.proposals[0].status == "applied"
    assert report.applied_changes[0].action == "updated"
    assert report.source_hashes == (hashlib.sha256(session.read_bytes()).hexdigest(),)
    assert report.active_memory_sha256
    assert "Clarify controller validation." in active.read_text(encoding="utf-8")
    assert "vesper_status: approved" in active.read_text(encoding="utf-8")
    assert (vault / "dreams" / "reports" / "dream-1.json").exists()


def test_dream_gate_without_sessions_is_a_memory_audit(tmp_path):
    vault = tmp_path / "knowledge"
    _write_active_note(vault)
    client = FakeDreamClient('{"proposals": []}')

    report = DreamGate(vault, client=client, clock=lambda: NOW, id_factory=lambda: "audit-1").run()

    assert report.mode.value == "memory-audit-only"
    assert report.source_session_ids == ()


def test_dream_gate_ignores_non_transcript_session_notes(tmp_path):
    vault = tmp_path / "knowledge"
    _write_active_note(vault)
    sessions = vault / "sessions"
    sessions.mkdir(parents=True)
    (sessions / "handoff.md").write_text(
        "---\nkind: session-handoff\n---\n\n## Objective\nNot a transcript.\n",
        encoding="utf-8",
    )
    (sessions / "transcript.md").write_text(
        "## Event 1 — user / message\n\nA captured event.\n",
        encoding="utf-8",
    )

    report = DreamGate(
        vault,
        client=FakeDreamClient('{"proposals": []}'),
        clock=lambda: NOW,
        id_factory=lambda: "dream-1",
    ).run()

    assert report.source_session_ids == ("sessions/transcript.md",)


def test_dream_gate_dry_run_writes_receipt_without_model_call(tmp_path):
    vault = tmp_path / "knowledge"
    _write_active_note(vault)
    client = FakeDreamClient("not valid JSON")

    report = DreamGate(vault, client=client, clock=lambda: NOW, id_factory=lambda: "dry-1").run(
        dry_run=True
    )

    assert report.dream_id == "dry-1"
    assert report.proposals == ()
    assert any("Dry run" in item for item in report.limitations)
    assert client.calls == []


def test_dream_gate_bounds_cold_transcript_context_but_keeps_source_receipt():
    sessions = ((
        "sessions/2026-08-04/agent--session.md",
        "a" * 64,
        "event " * MAX_DREAM_SESSION_CHARS,
    ),)

    bounded = DreamGate._bounded_session_text(sessions)

    assert len(bounded) <= MAX_DREAM_SESSION_CHARS
    assert "SOURCE sessions/2026-08-04/agent--session.md sha256=" in bounded
    assert "TRUNCATED FOR DREAM CONTEXT" in bounded
