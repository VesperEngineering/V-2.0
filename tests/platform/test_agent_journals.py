import sqlite3
import threading
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


def test_manifest_advances_with_new_events_and_is_stable_on_replay(tmp_path):
    paths = PlatformPaths.below(tmp_path / "state")
    role = AgentRole.MODEL_RESEARCHER
    session_id = "session-manifest"
    namespace = ("agent-journals", role.value, session_id)

    with open_persistence(paths) as persistence:
        journal = AgentJournal(persistence.store)
        first = journal.append(
            event_id="event-1",
            role=role,
            session_id=session_id,
            run_id="run-1",
            task_id="task-1",
            repository_revision="abc123",
            created_at=NOW,
            event_type=JournalEventType.OBSERVATION,
            payload={"worker": 1},
        )
        assert persistence.store.get(namespace, "__journal_manifest__") == {
            "role": role.value,
            "session_id": session_id,
            "event_count": 1,
            "head_event_id": first.event_id,
            "head_hash": first.event_hash,
        }
        second_fields = dict(
            event_id="event-2",
            role=role,
            session_id=session_id,
            run_id="run-2",
            task_id="task-2",
            repository_revision="abc123",
            created_at=NOW,
            event_type=JournalEventType.OBSERVATION,
            payload={"worker": 2},
        )
        second = journal.append(**second_fields)
        advanced = persistence.store.get(namespace, "__journal_manifest__")
        assert advanced == {
            "role": role.value,
            "session_id": session_id,
            "event_count": 2,
            "head_event_id": second.event_id,
            "head_hash": second.event_hash,
        }

        assert journal.append(**second_fields) == second
        assert persistence.store.get(namespace, "__journal_manifest__") == advanced


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


def test_correction_append_and_replay_preserve_the_chain(tmp_path):
    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        journal = AgentJournal(persistence.store)
        original = journal.append(
            event_id="event-1",
            role=AgentRole.PORTFOLIO_RESEARCHER,
            session_id="session-1",
            run_id="run-1",
            task_id="task-1",
            repository_revision="abc123",
            created_at=NOW,
            event_type=JournalEventType.OBSERVATION,
            payload={"summary": "first"},
        )
        correction_fields = dict(
            event_id="event-2",
            role=AgentRole.PORTFOLIO_RESEARCHER,
            session_id="session-1",
            run_id="run-1",
            task_id="task-1",
            repository_revision="abc123",
            created_at=NOW,
            event_type=JournalEventType.CORRECTION,
            payload={"summary": "corrected"},
            correction_of=original.event_id,
        )

        correction = journal.append(**correction_fields)
        replay = journal.append(**correction_fields)

        assert replay == correction
        assert correction.sequence == 2
        assert correction.previous_hash == original.event_hash
        assert correction.correction_of == original.event_id
        assert journal.verify(AgentRole.PORTFOLIO_RESEARCHER, "session-1") is True


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


def test_prefix_related_session_names_are_isolated(tmp_path):
    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        journal = AgentJournal(persistence.store)
        for session_id in ("session-1", "session-1-retry"):
            journal.append(
                event_id=f"event-{session_id}",
                role=AgentRole.QUANT_RESEARCH_LEAD,
                session_id=session_id,
                run_id=f"run-{session_id}",
                task_id="task",
                repository_revision="abc",
                created_at=NOW,
                event_type=JournalEventType.OBSERVATION,
                payload={"session": session_id},
            )

        assert [
            event.session_id for event in journal.list(AgentRole.QUANT_RESEARCH_LEAD, "session-1")
        ] == ["session-1"]
        assert journal.verify(AgentRole.QUANT_RESEARCH_LEAD, "session-1") is True
        assert journal.verify(AgentRole.QUANT_RESEARCH_LEAD, "session-1-retry") is True

        persistence.store.put(
            ("agent-journals", AgentRole.QUANT_RESEARCH_LEAD.value, "session-1-bad"),
            "malformed",
            {"role": AgentRole.QUANT_RESEARCH_LEAD.value, "session_id": "session-1-bad"},
        )
        assert [
            event.session_id for event in journal.list(AgentRole.QUANT_RESEARCH_LEAD, "session-1")
        ] == ["session-1"]


def test_two_persistence_connections_append_one_valid_session_chain(tmp_path, monkeypatch):
    paths = PlatformPaths.below(tmp_path / "state")
    role = AgentRole.MODEL_RESEARCHER
    session_id = "shared-session"
    namespace = ("agent-journals", role.value, session_id)

    with open_persistence(paths) as first, open_persistence(paths) as second:
        journals = (AgentJournal(first.store), AgentJournal(second.store))
        stores = (first.store, second.store)
        originals = (first.store.put, second.store.put)
        starts_ready = threading.Barrier(2)
        writes_ready = threading.Barrier(2)

        def synchronized_put(index):
            def put(target_namespace, key, value):
                if target_namespace == namespace:
                    writes_ready.wait(timeout=5)
                return originals[index](target_namespace, key, value)

            return put

        for index, store in enumerate(stores):
            monkeypatch.setattr(store, "put", synchronized_put(index))

        errors = []

        def append(index):
            try:
                starts_ready.wait(timeout=5)
                journals[index].append(
                    event_id=f"event-{index + 1}",
                    role=role,
                    session_id=session_id,
                    run_id=f"run-{index + 1}",
                    task_id=f"task-{index + 1}",
                    repository_revision="abc123",
                    created_at=NOW,
                    event_type=JournalEventType.OBSERVATION,
                    payload={"worker": index + 1},
                )
            except BaseException as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        threads = tuple(threading.Thread(target=append, args=(index,)) for index in range(2))
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert all(not thread.is_alive() for thread in threads)
        assert errors == []
        events = journals[0].list(role, session_id)
        assert [event.sequence for event in events] == [1, 2]
        assert events[1].previous_hash == events[0].event_hash
        assert journals[0].verify(role, session_id) is True


def test_session_registration_failure_rolls_back_new_event(tmp_path):
    paths = PlatformPaths.below(tmp_path / "state")
    role = AgentRole.MODEL_RESEARCHER
    session_id = "session-atomic"

    with open_persistence(paths) as persistence:
        persistence.langgraph_store.conn.execute(
            """
            CREATE TRIGGER reject_journal_session_registration
            BEFORE INSERT ON store
            WHEN NEW.prefix = 'agent-journals.sessions'
            BEGIN
                SELECT RAISE(ABORT, 'session registry blocked');
            END
            """
        )
        journal = AgentJournal(persistence.store)

        with pytest.raises(sqlite3.IntegrityError, match="session registry blocked"):
            journal.append(
                event_id="event-1",
                role=role,
                session_id=session_id,
                run_id="run-1",
                task_id="task-1",
                repository_revision="abc123",
                created_at=NOW,
                event_type=JournalEventType.OBSERVATION,
                payload={"worker": 1},
            )

        assert journal.list(role, session_id) == ()
        assert journal.sessions() == ()
        assert (
            persistence.store.get(
                ("agent-journals", role.value, session_id),
                "__journal_manifest__",
            )
            is None
        )


def test_manifest_write_failure_rolls_back_event_and_registry(tmp_path):
    paths = PlatformPaths.below(tmp_path / "state")
    role = AgentRole.MODEL_RESEARCHER
    session_id = "session-manifest-failure"
    namespace = ("agent-journals", role.value, session_id)

    with open_persistence(paths) as persistence:
        persistence.langgraph_store.conn.execute(
            """
            CREATE TRIGGER reject_journal_manifest
            BEFORE INSERT ON store
            WHEN NEW.prefix = 'agent-journals.v20-model-researcher.session-manifest-failure'
                 AND NEW.key = '__journal_manifest__'
            BEGIN
                SELECT RAISE(ABORT, 'manifest blocked');
            END
            """
        )
        journal = AgentJournal(persistence.store)

        with pytest.raises(sqlite3.IntegrityError, match="manifest blocked"):
            journal.append(
                event_id="event-1",
                role=role,
                session_id=session_id,
                run_id="run-1",
                task_id="task-1",
                repository_revision="abc123",
                created_at=NOW,
                event_type=JournalEventType.OBSERVATION,
                payload={"worker": 1},
            )

        assert persistence.store.search_exact_records(namespace) == ()
        assert journal.sessions() == ()
        assert journal.verify(role, session_id) is False


def test_replay_repairs_missing_session_registration(tmp_path):
    paths = PlatformPaths.below(tmp_path / "state")
    role = AgentRole.MODEL_RESEARCHER
    session_id = "session-replay"
    fields = dict(
        event_id="event-1",
        role=role,
        session_id=session_id,
        run_id="run-1",
        task_id="task-1",
        repository_revision="abc123",
        created_at=NOW,
        event_type=JournalEventType.OBSERVATION,
        payload={"worker": 1},
    )

    with open_persistence(paths) as persistence:
        journal = AgentJournal(persistence.store)
        first = journal.append(**fields)
        persistence.store.delete(
            ("agent-journals", "sessions"),
            f"{role.value}:{session_id}",
        )
        assert journal.sessions() == ((role, session_id),)
        assert journal.verify(role, session_id) is False

        replay = journal.append(**fields)

        assert replay == first
        assert journal.sessions() == ((role, session_id),)
        assert journal.verify(role, session_id) is True


def test_sibling_session_registry_namespace_is_rejected(tmp_path):
    paths = PlatformPaths.below(tmp_path / "state")
    with open_persistence(paths) as persistence:
        persistence.store.put(
            ("agent-journals", "sessions", "injected"),
            "v20-product:injected",
            {"role": AgentRole.PRODUCT.value, "session_id": "injected"},
        )

        with pytest.raises(JournalConflictError, match="registry namespace"):
            AgentJournal(persistence.store).sessions()


def test_missing_manifest_is_visible_but_replay_cannot_rebuild_it(tmp_path):
    paths = PlatformPaths.below(tmp_path / "state")
    role = AgentRole.MODEL_RESEARCHER
    session_id = "session-missing-manifest"
    namespace = ("agent-journals", role.value, session_id)
    fields = dict(
        event_id="event-1",
        role=role,
        session_id=session_id,
        run_id="run-1",
        task_id="task-1",
        repository_revision="abc123",
        created_at=NOW,
        event_type=JournalEventType.OBSERVATION,
        payload={"worker": 1},
    )

    with open_persistence(paths) as persistence:
        journal = AgentJournal(persistence.store)
        journal.append(**fields)
        persistence.store.delete(namespace, "__journal_manifest__")

        assert journal.sessions() == ((role, session_id),)
        assert journal.verify(role, session_id) is False
        with pytest.raises(JournalConflictError, match="manifest is missing"):
            journal.append(**fields)
        assert persistence.store.get(namespace, "__journal_manifest__") is None


@pytest.mark.parametrize(
    "manifest_update",
    ({"event_count": 2}, {"head_hash": "f" * 64}),
    ids=("count", "head"),
)
def test_corrupt_manifest_blocks_extension(tmp_path, manifest_update):
    paths = PlatformPaths.below(tmp_path / "state")
    role = AgentRole.MODEL_RESEARCHER
    session_id = "session-corrupt-manifest"
    namespace = ("agent-journals", role.value, session_id)

    with open_persistence(paths) as persistence:
        journal = AgentJournal(persistence.store)
        journal.append(
            event_id="event-1",
            role=role,
            session_id=session_id,
            run_id="run-1",
            task_id="task-1",
            repository_revision="abc123",
            created_at=NOW,
            event_type=JournalEventType.OBSERVATION,
            payload={"worker": 1},
        )
        manifest = dict(persistence.store.get(namespace, "__journal_manifest__") or {})
        persistence.store.put(
            namespace,
            "__journal_manifest__",
            {**manifest, **manifest_update},
        )

        assert journal.verify(role, session_id) is False
        with pytest.raises(JournalConflictError, match="manifest does not match"):
            journal.append(
                event_id="event-2",
                role=role,
                session_id=session_id,
                run_id="run-2",
                task_id="task-2",
                repository_revision="abc123",
                created_at=NOW,
                event_type=JournalEventType.OBSERVATION,
                payload={"worker": 2},
            )


def test_journal_transaction_shares_langgraph_connection_lock(tmp_path, monkeypatch):
    paths = PlatformPaths.below(tmp_path / "state")
    role = AgentRole.MODEL_RESEARCHER
    session_id = "session-shared-connection"

    with open_persistence(paths) as persistence:
        direct_transaction_started = threading.Event()
        release_direct_transaction = threading.Event()
        append_entered = threading.Event()
        append_finished = threading.Event()
        errors = []
        original_batch_put = persistence.langgraph_store._batch_put_ops
        original_atomic_create = persistence.store.atomic_create

        def blocking_batch_put(*args, **kwargs):
            direct_transaction_started.set()
            if not release_direct_transaction.wait(timeout=5):
                raise TimeoutError("direct transaction was not released")
            return original_batch_put(*args, **kwargs)

        def announced_atomic_create(*args, **kwargs):
            append_entered.set()
            return original_atomic_create(*args, **kwargs)

        monkeypatch.setattr(persistence.langgraph_store, "_batch_put_ops", blocking_batch_put)
        monkeypatch.setattr(persistence.store, "atomic_create", announced_atomic_create)

        def direct_write():
            try:
                persistence.langgraph_store.put(("direct",), "item", {"value": 1})
            except BaseException as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        def append_event():
            try:
                AgentJournal(persistence.store).append(
                    event_id="event-1",
                    role=role,
                    session_id=session_id,
                    run_id="run-1",
                    task_id="task-1",
                    repository_revision="abc123",
                    created_at=NOW,
                    event_type=JournalEventType.OBSERVATION,
                    payload={"worker": 1},
                )
            except BaseException as exc:  # pragma: no cover - asserted below
                errors.append(exc)
            finally:
                append_finished.set()

        direct_thread = threading.Thread(target=direct_write)
        append_thread = threading.Thread(target=append_event)
        direct_thread.start()
        assert direct_transaction_started.wait(timeout=5)
        append_thread.start()
        assert append_entered.wait(timeout=5)
        append_finished.wait(timeout=0.1)
        release_direct_transaction.set()
        direct_thread.join(timeout=10)
        append_thread.join(timeout=10)

        assert not direct_thread.is_alive()
        assert not append_thread.is_alive()
        assert errors == []
        assert persistence.store.get(("direct",), "item") == {"value": 1}
        journal = AgentJournal(persistence.store)
        assert len(journal.list(role, session_id)) == 1
        assert journal.verify(role, session_id) is True


def test_append_rejects_corrupted_existing_chain_before_writing(tmp_path):
    paths = PlatformPaths.below(tmp_path / "state")
    role = AgentRole.MODEL_RESEARCHER
    session_id = "session-corrupt"

    with open_persistence(paths) as persistence:
        journal = AgentJournal(persistence.store)
        first = journal.append(
            event_id="event-1",
            role=role,
            session_id=session_id,
            run_id="run-1",
            task_id="task-1",
            repository_revision="abc123",
            created_at=NOW,
            event_type=JournalEventType.OBSERVATION,
            payload={"worker": 1},
        )
        persistence.store.put(
            ("agent-journals", role.value, session_id),
            first.event_id,
            first.model_copy(update={"event_hash": "f" * 64}).model_dump(mode="json"),
        )

        with pytest.raises(JournalConflictError, match="chain"):
            journal.append(
                event_id="event-2",
                role=role,
                session_id=session_id,
                run_id="run-2",
                task_id="task-2",
                repository_revision="abc123",
                created_at=NOW,
                event_type=JournalEventType.OBSERVATION,
                payload={"worker": 2},
            )

        assert [event.event_id for event in journal.list(role, session_id)] == ["event-1"]


@pytest.mark.parametrize(
    "identity_update",
    (
        {"role": AgentRole.PRODUCT},
        {"session_id": "different-session"},
    ),
    ids=("role", "session"),
)
def test_identity_corruption_is_not_filtered_out_or_extended(tmp_path, identity_update):
    paths = PlatformPaths.below(tmp_path / "state")
    role = AgentRole.MODEL_RESEARCHER
    session_id = "session-identity"
    namespace = ("agent-journals", role.value, session_id)

    with open_persistence(paths) as persistence:
        journal = AgentJournal(persistence.store)
        first = journal.append(
            event_id="event-1",
            role=role,
            session_id=session_id,
            run_id="run-1",
            task_id="task-1",
            repository_revision="abc123",
            created_at=NOW,
            event_type=JournalEventType.OBSERVATION,
            payload={"worker": 1},
        )
        persistence.store.put(
            namespace,
            first.event_id,
            first.model_copy(update=identity_update).model_dump(mode="json"),
        )

        assert journal.verify(role, session_id) is False
        with pytest.raises(JournalConflictError, match="identity"):
            journal.append(
                event_id="event-2",
                role=role,
                session_id=session_id,
                run_id="run-2",
                task_id="task-2",
                repository_revision="abc123",
                created_at=NOW,
                event_type=JournalEventType.OBSERVATION,
                payload={"worker": 2},
            )


def test_event_storage_key_must_match_embedded_event_id(tmp_path):
    paths = PlatformPaths.below(tmp_path / "state")
    role = AgentRole.MODEL_RESEARCHER
    session_id = "session-key"
    namespace = ("agent-journals", role.value, session_id)

    with open_persistence(paths) as persistence:
        journal = AgentJournal(persistence.store)
        first = journal.append(
            event_id="event-1",
            role=role,
            session_id=session_id,
            run_id="run-1",
            task_id="task-1",
            repository_revision="abc123",
            created_at=NOW,
            event_type=JournalEventType.OBSERVATION,
            payload={"worker": 1},
        )
        persistence.store.delete(namespace, first.event_id)
        persistence.store.put(namespace, "moved-key", first.model_dump(mode="json"))

        assert journal.verify(role, session_id) is False
        with pytest.raises(JournalConflictError, match="storage key"):
            journal.append(
                event_id="event-1",
                role=role,
                session_id=session_id,
                run_id="run-1",
                task_id="task-1",
                repository_revision="abc123",
                created_at=NOW,
                event_type=JournalEventType.OBSERVATION,
                payload={"worker": 1},
            )


def test_reserved_manifest_key_and_unknown_session_fail_closed(tmp_path):
    role = AgentRole.MODEL_RESEARCHER
    session_id = "session-reserved"
    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        journal = AgentJournal(persistence.store)
        assert journal.verify(role, "unknown-session") is False
        with pytest.raises(JournalConflictError, match="reserved"):
            journal.append(
                event_id="__journal_manifest__",
                role=role,
                session_id=session_id,
                run_id="run-1",
                task_id="task-1",
                repository_revision="abc123",
                created_at=NOW,
                event_type=JournalEventType.OBSERVATION,
                payload={"worker": 1},
            )


@pytest.mark.parametrize("event_count", (1, 2), ids=("only-event", "latest-event"))
def test_manifest_detects_tail_deletion_and_blocks_extension(tmp_path, event_count):
    paths = PlatformPaths.below(tmp_path / "state")
    role = AgentRole.MODEL_RESEARCHER
    session_id = "session-tail"
    namespace = ("agent-journals", role.value, session_id)

    with open_persistence(paths) as persistence:
        journal = AgentJournal(persistence.store)
        events = [
            journal.append(
                event_id=f"event-{index}",
                role=role,
                session_id=session_id,
                run_id=f"run-{index}",
                task_id=f"task-{index}",
                repository_revision="abc123",
                created_at=NOW,
                event_type=JournalEventType.OBSERVATION,
                payload={"worker": index},
            )
            for index in range(1, event_count + 1)
        ]
        persistence.store.delete(namespace, events[-1].event_id)

        assert journal.sessions() == ((role, session_id),)
        assert journal.verify(role, session_id) is False
        with pytest.raises(JournalConflictError, match="manifest"):
            journal.append(
                event_id="event-next",
                role=role,
                session_id=session_id,
                run_id="run-next",
                task_id="task-next",
                repository_revision="abc123",
                created_at=NOW,
                event_type=JournalEventType.OBSERVATION,
                payload={"worker": "next"},
            )
        with pytest.raises(JournalConflictError, match="manifest"):
            journal.append(
                event_id=events[-1].event_id,
                role=role,
                session_id=session_id,
                run_id=f"run-{event_count}",
                task_id=f"task-{event_count}",
                repository_revision="abc123",
                created_at=NOW,
                event_type=JournalEventType.OBSERVATION,
                payload={"worker": event_count},
            )
