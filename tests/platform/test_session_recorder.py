from __future__ import annotations

from datetime import datetime, timezone

import pytest

from vesper.platform.dreaming import DreamGate
from vesper.platform.session_recorder import SessionRecorder, SessionRecorderError


NOW = datetime(2026, 8, 5, 1, 0, tzinfo=timezone.utc)


def test_recorder_persists_redacted_turns_and_appends_to_one_session(tmp_path):
    recorder = SessionRecorder(tmp_path / "knowledge", clock=lambda: NOW)

    first = recorder.record_turn(
        role="v20-development",
        session_id="session-1",
        run_id="run-1",
        task_id="task-1",
        repository_revision="revision-1",
        speaker="user",
        content="Remember the durable rule. api_key=super-secret-value",
    )
    second = recorder.record_turn(
        role="v20-development",
        session_id="session-1",
        run_id="run-1",
        task_id="task-1",
        repository_revision="revision-1",
        speaker="assistant",
        content="The durable rule is controller validation before promotion.",
    )

    text = first.path.read_text(encoding="utf-8")
    assert first.path == second.path
    assert "super-secret-value" not in text
    assert "api_key=[REDACTED]" in text
    assert "The durable rule is controller validation before promotion." in text
    assert "turn_count: 2" in text


def test_recorder_rejects_identity_changes_and_invalid_speakers(tmp_path):
    recorder = SessionRecorder(tmp_path / "knowledge", clock=lambda: NOW)
    recorder.record_turn(
        role="v20-development",
        session_id="session-1",
        run_id="run-1",
        task_id="task-1",
        repository_revision="revision-1",
        speaker="user",
        content="Durable discussion.",
    )

    with pytest.raises(SessionRecorderError, match="identity"):
        recorder.record_turn(
            role="v20-development",
            session_id="session-1",
            run_id="different-run",
            task_id="task-1",
            repository_revision="revision-1",
            speaker="assistant",
            content="Different authority.",
        )

    with pytest.raises(SessionRecorderError, match="speaker"):
        recorder.record_turn(
            role="v20-development",
            session_id="session-1",
            run_id="run-1",
            task_id="task-1",
            repository_revision="revision-1",
            speaker="tool",
            content="Not a user or assistant turn.",
        )


def test_recorder_persists_ordered_tool_events_with_redacted_structured_payload(tmp_path):
    recorder = SessionRecorder(tmp_path / "knowledge", clock=lambda: NOW)

    first = recorder.record_event(
        role="v20-model-researcher",
        session_id="session-1",
        run_id="run-1",
        task_id="task-1",
        repository_revision="revision-1",
        speaker="assistant",
        event_type="tool_call",
        content={
            "name": "read_file",
            "arguments": {
                "path": "notes.txt",
                "token": "super-secret",
                "analysis": "private reasoning",
            },
        },
    )
    second = recorder.record_event(
        role="v20-model-researcher",
        session_id="session-1",
        run_id="run-1",
        task_id="task-1",
        repository_revision="revision-1",
        speaker="tool",
        event_type="tool_result",
        content="Observed bounded evidence.",
        metadata={"name": "read_file", "truncated": False},
    )

    text = first.path.read_text(encoding="utf-8")
    assert second.event_count == 2
    assert "## Event 1 — assistant / tool_call" in text
    assert "## Event 2 — tool / tool_result" in text
    assert "super-secret" not in text
    assert "private reasoning" not in text
    assert '"token": "[REDACTED]"' in text
    assert "Observed bounded evidence." in text
    assert "event_count: 2" in text


def test_recorded_session_is_consumed_by_dream_gate(tmp_path):
    knowledge = tmp_path / "knowledge"
    recorder = SessionRecorder(knowledge, clock=lambda: NOW)
    recorder.record_turn(
        role="v20-development",
        session_id="session-1",
        run_id="run-1",
        task_id="task-1",
        repository_revision="revision-1",
        speaker="user",
        content="We should retain controller validation before promotion.",
    )
    recorder.record_turn(
        role="v20-development",
        session_id="session-1",
        run_id="run-1",
        task_id="task-1",
        repository_revision="revision-1",
        speaker="assistant",
        content="That is a durable procedure candidate.",
    )
    active = knowledge / "memory" / "current.md"
    active.parent.mkdir(parents=True)
    active.write_text(
        "---\nvesper_id: current\nvesper_kind: memory\nvesper_status: approved\n"
        "vesper_scope: shared\ntitle: Current\n---\n\n# Current\n\nExisting.\n",
        encoding="utf-8",
    )

    class Client:
        def chat(self, messages, *, response_format=None):
            content = messages[0]["content"]
            assert "controller validation before promotion" in content
            return type("Response", (), {"content": '{"proposals": []}'})()

    report = DreamGate(knowledge, client=Client(), clock=lambda: NOW, id_factory=lambda: "dream-1").run()

    assert report.source_session_ids == ("sessions/2026-08-05/v20-development--session-1.md",)
