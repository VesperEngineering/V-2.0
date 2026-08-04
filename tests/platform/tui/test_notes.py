from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from vesper.platform.tui.event_store import EventStore
from vesper.platform.tui.notes import NoteStore, NoteTarget, NoteVisibility
from vesper.platform.tui.sqlite_ledger import (
    LedgerClosedError,
    LedgerTransactionError,
    TuiLedger,
)


NOW = datetime(2026, 8, 3, 16, 0, tzinfo=timezone.utc)


def _target(target_type: str = "stock", target_id: str = "AAPL") -> NoteTarget:
    return NoteTarget(target_type=target_type, target_id=target_id)  # type: ignore[arg-type]


@pytest.mark.parametrize("target_type", ("stock", "order", "approval", "agent-event"))
def test_notes_accept_only_the_four_context_targets(tmp_path, target_type: str) -> None:
    store = NoteStore(
        tmp_path / "events.db",
        clock=lambda: NOW,
        id_factory=lambda: f"note:{target_type}",
    )
    note = store.add(
        _target(target_type, f"target:{target_type}"),
        "context",
        NoteVisibility.PRIVATE,
        "operator",
    )
    assert note.target.target_type == target_type
    assert note.context_only is True
    assert "command" not in type(note).model_fields
    assert set(type(note).model_fields) == {
        "note_id",
        "target",
        "body",
        "visibility",
        "author",
        "revision",
        "created_at_utc",
        "updated_at_utc",
        "context_only",
    }
    store.close()


def test_note_add_is_atomic_persistent_and_history_is_immutable(tmp_path) -> None:
    database = tmp_path / "events.db"
    ledger = TuiLedger(database)
    store = NoteStore(
        ledger,
        clock=lambda: NOW,
        id_factory=lambda: "note:1",
    )
    note = store.add(_target(), "private context", NoteVisibility.PRIVATE, "operator")
    assert note.note_id == "note:1"
    assert note.revision == 1
    assert note.created_at_utc == NOW
    assert note.updated_at_utc == NOW
    assert store.list(_target()) == (note,)

    with ledger.read() as connection:
        current_json = connection.execute(
            "SELECT payload_json FROM notes WHERE note_id = 'note:1'"
        ).fetchone()[0]
        history_json = connection.execute(
            "SELECT payload_json FROM note_history WHERE note_id = 'note:1'"
        ).fetchone()[0]
    expected_json = json.dumps(
        note.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    assert current_json == expected_json
    assert history_json == expected_json

    with pytest.raises(sqlite3.IntegrityError):
        with ledger.transaction() as connection:
            connection.execute(
                "UPDATE notes SET payload_json = '{' WHERE note_id = 'note:1'"
            )
    with pytest.raises(sqlite3.IntegrityError):
        with ledger.transaction() as connection:
            connection.execute(
                """
                INSERT INTO note_history (
                    note_id, revision, changed_at_utc, payload_json
                ) VALUES ('note:1', 2, '2026-08-03T16:00:00Z', '{')
                """
            )

    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with ledger.transaction() as connection:
            connection.execute("UPDATE note_history SET revision = 2 WHERE note_id = 'note:1'")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with ledger.transaction() as connection:
            connection.execute("DELETE FROM note_history WHERE note_id = 'note:1'")

    store.close()
    reopened = NoteStore(database)
    assert reopened.list(_target()) == (note,)
    reopened.close()
    ledger.close()


def test_note_transaction_helper_rolls_back_with_its_future_receipt_transaction(tmp_path) -> None:
    ledger = TuiLedger(tmp_path / "events.db")
    store = NoteStore(
        ledger,
        clock=lambda: NOW,
        id_factory=lambda: "note:rollback",
    )
    with pytest.raises(RuntimeError, match="receipt failed"):
        with ledger.transaction() as connection:
            store._add_in_transaction(
                connection,
                _target(),
                "context",
                NoteVisibility.SHARED,
                "operator",
            )
            raise RuntimeError("receipt failed")
    assert store.list(_target()) == ()
    ledger.close()


def test_event_and_note_effects_share_one_rollback_boundary(tmp_path) -> None:
    from vesper.platform.tui.event_store import EventInput

    ledger = TuiLedger(tmp_path / "events.db")
    events = EventStore(ledger)
    notes = NoteStore(ledger, clock=lambda: NOW, id_factory=lambda: "note:atomic")
    event = EventInput(
        event_id="event:atomic",
        occurred_at_utc=NOW,
        impact=True,
        severity="active",
        summary="Atomic effect",
        agent_id="v20-product",
        symbol="AAPL",
        model_id=None,
        approval_id=None,
        order_id=None,
        evidence_ids=(),
        source="native-platform",
    )

    with pytest.raises(RuntimeError, match="receipt failed"):
        with ledger.transaction() as connection:
            events._append_in_transaction(connection, event)
            notes._add_in_transaction(
                connection,
                _target(),
                "context",
                NoteVisibility.SHARED,
                "operator",
            )
            raise RuntimeError("receipt failed")
    assert events.since(0, 10) == ()
    assert notes.list(_target()) == ()
    assert events.append(event).sequence == 1
    ledger.close()


def test_note_body_visibility_author_and_target_are_strict_and_bounded(tmp_path) -> None:
    counter = iter(("note:max", "note:one", "note:space"))
    store = NoteStore(
        tmp_path / "events.db",
        clock=lambda: NOW,
        id_factory=lambda: next(counter),
    )
    maximum = store.add(_target(), "x" * 8_000, NoteVisibility.SHARED, "operator")
    one = store.add(_target(), "x", NoteVisibility.PRIVATE, "operator")
    whitespace = store.add(_target(), " ", NoteVisibility.PRIVATE, "operator")
    assert len(maximum.body) == 8_000
    assert maximum.visibility is NoteVisibility.SHARED
    assert one.body == "x"
    assert one.visibility is NoteVisibility.PRIVATE
    assert whitespace.body == " "

    with pytest.raises(ValidationError):
        store.add(_target(), "", NoteVisibility.SHARED, "operator")
    with pytest.raises(ValidationError):
        store.add(_target(), "x" * 8_001, NoteVisibility.SHARED, "operator")
    with pytest.raises((TypeError, ValidationError)):
        store.add(_target(), "context", "private", "operator")  # type: ignore[arg-type]
    with pytest.raises((TypeError, ValidationError)):
        store.add(_target(), "context", NoteVisibility.PRIVATE, "bad author")
    with pytest.raises((TypeError, ValidationError)):
        store.add(
            {"target_type": "stock", "target_id": "AAPL"},  # type: ignore[arg-type]
            "context",
            NoteVisibility.PRIVATE,
            "operator",
        )
    with pytest.raises(ValidationError):
        NoteTarget.model_validate(
            {"target_type": "conversation", "target_id": "AAPL"}, strict=True
        )
    with pytest.raises(ValidationError):
        NoteTarget.model_validate(
            {"target_type": "stock", "target_id": "bad target"}, strict=True
        )
    with pytest.raises(ValidationError):
        NoteTarget.model_validate(
            {"target_type": "stock", "target_id": "AAPL", "command": "buy"}, strict=True
        )
    store.close()


def test_note_list_is_target_isolated_and_newest_first(tmp_path) -> None:
    identifiers = iter(("note:1", "note:2", "note:3"))
    store = NoteStore(
        tmp_path / "events.db",
        clock=lambda: NOW,
        id_factory=lambda: next(identifiers),
    )
    store.add(_target(), "first", NoteVisibility.PRIVATE, "operator")
    store.add(_target("order", "order:1"), "other", NoteVisibility.SHARED, "operator")
    store.add(_target(), "newest", NoteVisibility.SHARED, "operator")

    assert [note.body for note in store.list(_target())] == ["newest", "first"]
    assert [note.body for note in store.list(_target("order", "order:1"))] == ["other"]
    store.close()


def test_note_schema_has_no_command_field_and_both_store_open_orders_work(tmp_path) -> None:
    first_database = tmp_path / "first.db"
    events = EventStore(first_database)
    notes = NoteStore(first_database, clock=lambda: NOW, id_factory=lambda: "note:first")
    notes.add(_target(), "context", NoteVisibility.PRIVATE, "operator")
    notes.close()
    events.close()

    second_database = tmp_path / "second.db"
    notes = NoteStore(second_database, clock=lambda: NOW, id_factory=lambda: "note:second")
    events = EventStore(second_database)
    notes.add(_target(), "context", NoteVisibility.SHARED, "operator")
    events.close()
    notes.close()

    with sqlite3.connect(second_database) as connection:
        note_columns = {row[1] for row in connection.execute("PRAGMA table_info(notes)")}
        history_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(note_history)")
        }
    assert not any("command" in name for name in note_columns)
    assert not any("command" in name for name in history_columns)


def test_borrowed_note_store_close_does_not_close_shared_ledger(tmp_path) -> None:
    ledger = TuiLedger(tmp_path / "events.db")
    closed = NoteStore(ledger, clock=lambda: NOW, id_factory=lambda: "note:closed")
    closed.close()
    closed.close()
    with pytest.raises(LedgerClosedError):
        closed.list(_target())

    active = NoteStore(ledger, clock=lambda: NOW, id_factory=lambda: "note:active")
    assert active.add(_target(), "context", NoteVisibility.PRIVATE, "operator").note_id == (
        "note:active"
    )
    ledger.close()

    retryable = NoteStore(
        tmp_path / "retryable.db",
        clock=lambda: NOW,
        id_factory=lambda: "note:retryable",
    )
    with retryable._ledger.transaction():
        with pytest.raises(LedgerTransactionError):
            retryable.close()
    assert retryable.add(
        _target(), "context", NoteVisibility.PRIVATE, "operator"
    ).note_id == "note:retryable"
    retryable.close()


def test_note_transaction_helper_requires_its_own_active_ledger_transaction(tmp_path) -> None:
    ledger = TuiLedger(tmp_path / "events.db")
    other_ledger = TuiLedger(tmp_path / "other.db")
    store = NoteStore(ledger, clock=lambda: NOW, id_factory=lambda: "note:guard")
    with ledger.read() as connection:
        with pytest.raises(LedgerTransactionError):
            store._add_in_transaction(
                connection,
                _target(),
                "context",
                NoteVisibility.PRIVATE,
                "operator",
            )
    with other_ledger.transaction() as connection:
        with pytest.raises(LedgerTransactionError):
            store._add_in_transaction(
                connection,
                _target(),
                "context",
                NoteVisibility.PRIVATE,
                "operator",
            )
    assert store.list(_target()) == ()
    ledger.close()
    other_ledger.close()


@pytest.mark.parametrize(
    "bad_time",
    (
        datetime(2026, 8, 3, 16, 0),
        datetime(2026, 8, 3, 12, 0, tzinfo=timezone(-timedelta(hours=4))),
    ),
)
def test_note_clock_must_return_utc(tmp_path, bad_time: datetime) -> None:
    store = NoteStore(
        tmp_path / "bad-clock.db",
        clock=lambda: bad_time,
        id_factory=lambda: "note:bad-clock",
    )
    with pytest.raises(ValidationError):
        store.add(_target(), "context", NoteVisibility.PRIVATE, "operator")
    store.close()
