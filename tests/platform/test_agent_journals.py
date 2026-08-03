from datetime import datetime, timezone

import pytest

from vesper.platform.contracts import AgentRole, JournalEventType
from vesper.platform.journals import AgentJournal, JournalConflictError
from vesper.platform.persistence import PlatformPaths, open_persistence


NOW = datetime(2026, 8, 2, 20, 0, tzinfo=timezone.utc)


def test_journal_is_append_only_hash_chained_and_reopens(tmp_path):
    paths = PlatformPaths.below(tmp_path / "state")
    with open_persistence(paths) as persistence:
        journal = AgentJournal(persistence.store)
        first = journal.append(
            event_id="event-1",
            role=AgentRole.MODEL_RESEARCHER,
            session_id="session-1",
            run_id="run-1",
            task_id="task-1",
            repository_revision="abc123",
            created_at=NOW,
            event_type=JournalEventType.PROPOSAL_CREATED,
            payload={"summary": "candidate"},
        )
        replay = journal.append(
            event_id="event-1",
            role=AgentRole.MODEL_RESEARCHER,
            session_id="session-1",
            run_id="run-1",
            task_id="task-1",
            repository_revision="abc123",
            created_at=NOW,
            event_type=JournalEventType.PROPOSAL_CREATED,
            payload={"summary": "candidate"},
        )
        second = journal.append(
            event_id="event-2",
            role=AgentRole.MODEL_RESEARCHER,
            session_id="session-1",
            run_id="run-1",
            task_id="task-1",
            repository_revision="abc123",
            created_at=NOW,
            event_type=JournalEventType.ROUTING_DECISION,
            payload={"status": "admitted"},
        )
        assert replay == first
        assert second.sequence == 2
        assert second.previous_hash == first.event_hash

    with open_persistence(paths) as persistence:
        journal = AgentJournal(persistence.store)
        events = journal.list(AgentRole.MODEL_RESEARCHER, "session-1")
        assert [event.event_id for event in events] == ["event-1", "event-2"]
        assert journal.verify(AgentRole.MODEL_RESEARCHER, "session-1") is True


def test_conflicting_replay_is_rejected(tmp_path):
    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        journal = AgentJournal(persistence.store)
        fields = dict(
            event_id="event-1",
            role=AgentRole.PORTFOLIO_RESEARCHER,
            session_id="session-1",
            run_id="run-1",
            task_id="task-1",
            repository_revision="abc123",
            created_at=NOW,
            event_type=JournalEventType.PROPOSAL_CREATED,
        )
        journal.append(**fields, payload={"summary": "first"})
        with pytest.raises(JournalConflictError):
            journal.append(**fields, payload={"summary": "changed"})


def test_role_namespaces_are_isolated(tmp_path):
    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        journal = AgentJournal(persistence.store)
        for role in (AgentRole.PRODUCT, AgentRole.INDEPENDENT_QUANT_VALIDATOR):
            journal.append(
                event_id=f"event-{role.value}",
                role=role,
                session_id="same",
                run_id="run",
                task_id="task",
                repository_revision="abc",
                created_at=NOW,
                event_type=JournalEventType.OBSERVATION,
                payload={"role": role.value},
            )
        assert len(journal.list(AgentRole.PRODUCT, "same")) == 1
        assert len(journal.list(AgentRole.INDEPENDENT_QUANT_VALIDATOR, "same")) == 1
