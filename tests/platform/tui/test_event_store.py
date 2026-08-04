from __future__ import annotations

import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from vesper.platform.tui.event_store import (
    EventConflictError,
    EventFilters,
    EventInput,
    EventStore,
)
from vesper.platform.tui.sqlite_ledger import (
    LedgerClosedError,
    LedgerCorruptionError,
    LedgerSchemaError,
    LedgerTransactionError,
    TuiLedger,
)


NOW = datetime(2026, 8, 3, 16, 0, tzinfo=timezone.utc)
APPLICATION_ID = 0x56323054

_V1_SCHEMA = """
CREATE TABLE events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    occurred_at_utc TEXT NOT NULL,
    impact INTEGER NOT NULL CHECK (impact IN (0, 1)),
    severity TEXT NOT NULL CHECK (
        severity IN ('info', 'active', 'waiting', 'urgent', 'resolved')
    ),
    summary TEXT NOT NULL,
    agent_id TEXT,
    symbol TEXT,
    model_id TEXT,
    approval_id TEXT,
    order_id TEXT,
    source TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
);

CREATE VIRTUAL TABLE event_search USING fts5(
    event_id,
    source,
    summary,
    agent_id,
    symbol,
    model_id,
    approval_id,
    order_id,
    evidence_ids,
    tokenize='unicode61'
);

CREATE TABLE notes (
    note_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id TEXT NOT NULL UNIQUE,
    target_type TEXT NOT NULL CHECK (
        target_type IN ('stock', 'order', 'approval', 'agent-event')
    ),
    target_id TEXT NOT NULL,
    body TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 8000),
    visibility TEXT NOT NULL CHECK (visibility IN ('private', 'shared')),
    author TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
);

CREATE INDEX notes_target_order
ON notes(target_type, target_id, note_sequence DESC);

CREATE TABLE note_history (
    history_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    changed_at_utc TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    UNIQUE(note_id, revision),
    FOREIGN KEY(note_id) REFERENCES notes(note_id) ON DELETE RESTRICT
);

CREATE TRIGGER events_no_update
BEFORE UPDATE ON events
BEGIN
    SELECT RAISE(ABORT, 'events are append-only');
END;

CREATE TRIGGER events_no_delete
BEFORE DELETE ON events
BEGIN
    SELECT RAISE(ABORT, 'events are append-only');
END;

CREATE TRIGGER note_history_no_update
BEFORE UPDATE ON note_history
BEGIN
    SELECT RAISE(ABORT, 'note history is immutable');
END;

CREATE TRIGGER note_history_no_delete
BEFORE DELETE ON note_history
BEGIN
    SELECT RAISE(ABORT, 'note history is immutable');
END;
"""

_NOTE_SEARCH_SCHEMA = """
CREATE VIRTUAL TABLE note_search USING fts5(
    note_id,
    target_type,
    target_id,
    body,
    visibility,
    author,
    tokenize='unicode61'
);
"""


def _create_v1_database(path, *, with_note: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(_V1_SCHEMA)
        connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        connection.execute("PRAGMA user_version = 1")
        if with_note:
            payload = json.dumps(
                {
                    "author": "operator",
                    "body": "legacy risk context",
                    "context_only": True,
                    "created_at_utc": "2026-08-03T16:00:00Z",
                    "note_id": "note:legacy",
                    "revision": 1,
                    "target": {"target_id": "AAPL", "target_type": "stock"},
                    "updated_at_utc": "2026-08-03T16:00:00Z",
                    "visibility": "private",
                },
                separators=(",", ":"),
                sort_keys=True,
            )
            connection.execute(
                """
                INSERT INTO notes (
                    note_id, target_type, target_id, body, visibility, author,
                    revision, created_at_utc, updated_at_utc, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "note:legacy",
                    "stock",
                    "AAPL",
                    "legacy risk context",
                    "private",
                    "operator",
                    1,
                    "2026-08-03T16:00:00Z",
                    "2026-08-03T16:00:00Z",
                    payload,
                ),
            )
            connection.execute(
                """
                INSERT INTO note_history (
                    note_id, revision, changed_at_utc, payload_json
                ) VALUES (?, ?, ?, ?)
                """,
                ("note:legacy", 1, "2026-08-03T16:00:00Z", payload),
            )


def _create_v2_database(path, *, with_note: bool = False) -> None:
    _create_v1_database(path, with_note=with_note)
    with sqlite3.connect(path) as connection:
        connection.execute(_NOTE_SEARCH_SCHEMA)
        connection.execute(
            """
            INSERT INTO note_search (
                rowid, note_id, target_type, target_id, body, visibility, author
            )
            SELECT
                note_sequence, note_id, target_type, target_id, body, visibility, author
            FROM notes
            ORDER BY note_sequence
            """
        )
        connection.execute("PRAGMA user_version = 2")


def _event(index: int, **changes: object) -> EventInput:
    values: dict[str, object] = {
        "event_id": f"event:{index}",
        "occurred_at_utc": NOW + timedelta(seconds=index),
        "impact": index % 2 == 0,
        "severity": "active",
        "summary": f"AAPL review event {index}",
        "agent_id": "v20-product",
        "symbol": "AAPL",
        "model_id": None,
        "approval_id": None,
        "order_id": None,
        "evidence_ids": (f"evidence:{index}",),
        "source": "native-platform",
    }
    values.update(changes)
    return EventInput(**values)


def test_ledger_migrates_reopens_and_configures_required_pragmas(tmp_path) -> None:
    database = tmp_path / "state" / "events.db"
    ledger = TuiLedger(database)
    with ledger.read() as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5_000
        assert connection.execute("PRAGMA application_id").fetchone()[0] == APPLICATION_ID
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type IN ('table', 'view')"
            )
        }
    ledger.close()

    assert {
        "events",
        "event_search",
        "notes",
        "note_history",
        "note_search",
        "commands",
        "command_receipt_events",
    } <= tables
    reopened = TuiLedger(database)
    reopened.close()


def test_ledger_rejects_future_wrong_and_corrupt_databases(tmp_path) -> None:
    future = tmp_path / "future.db"
    TuiLedger(future).close()
    with sqlite3.connect(future) as connection:
        connection.execute("PRAGMA user_version = 4")
    future_before = future.read_bytes()
    with pytest.raises(LedgerSchemaError, match="newer"):
        TuiLedger(future)
    assert future.read_bytes() == future_before
    with sqlite3.connect(future) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 4

    wrong = tmp_path / "wrong.db"
    with sqlite3.connect(wrong) as connection:
        connection.execute("CREATE TABLE foreign_state(value TEXT)")
    with pytest.raises(LedgerSchemaError, match="unrecognized"):
        TuiLedger(wrong)

    wrong_application = tmp_path / "wrong-application.db"
    TuiLedger(wrong_application).close()
    with sqlite3.connect(wrong_application) as connection:
        connection.execute("PRAGMA application_id = 12345")
    before_failed_open = wrong_application.read_bytes()
    with pytest.raises(LedgerSchemaError, match="application"):
        TuiLedger(wrong_application)
    assert wrong_application.read_bytes() == before_failed_open

    incomplete = tmp_path / "incomplete.db"
    TuiLedger(incomplete).close()
    with sqlite3.connect(incomplete) as connection:
        connection.execute("DROP TRIGGER events_no_delete")
    before_failed_open = incomplete.read_bytes()
    with pytest.raises(LedgerSchemaError, match="schema"):
        TuiLedger(incomplete)
    assert incomplete.read_bytes() == before_failed_open

    wrong_column = tmp_path / "wrong-column.db"
    TuiLedger(wrong_column).close()
    with sqlite3.connect(wrong_column) as connection:
        connection.execute("ALTER TABLE events RENAME COLUMN summary TO changed_summary")
    with pytest.raises(LedgerSchemaError, match="schema"):
        TuiLedger(wrong_column)

    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"not a sqlite database")
    with pytest.raises(LedgerCorruptionError):
        TuiLedger(corrupt)
    assert corrupt.read_bytes() == b"not a sqlite database"


def test_ledger_migrates_exact_v1_data_and_backfills_note_search(tmp_path) -> None:
    database = tmp_path / "legacy.db"
    _create_v1_database(database, with_note=True)

    ledger = TuiLedger(database)
    with ledger.read() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        row = connection.execute(
            "SELECT note_id, body FROM note_search WHERE note_search MATCH ?",
            ('"legacy"*',),
        ).fetchone()
        parity = connection.execute(
            """
            SELECT COUNT(*)
            FROM notes AS n
            JOIN note_search AS s ON s.rowid = n.note_sequence
            WHERE s.note_id = n.note_id
              AND s.target_type = n.target_type
              AND s.target_id = n.target_id
              AND s.body = n.body
              AND s.visibility = n.visibility
              AND s.author = n.author
            """
        ).fetchone()[0]
        note_count = connection.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    ledger.close()

    assert tuple(row) == ("note:legacy", "legacy risk context")
    assert parity == note_count == 1


def test_ledger_migrates_exact_v2_data_and_adds_empty_command_ledger(tmp_path) -> None:
    database = tmp_path / "legacy-v2.db"
    _create_v2_database(database, with_note=True)

    ledger = TuiLedger(database)
    with ledger.read() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM note_search").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM commands").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM command_receipt_events"
        ).fetchone()[0] == 0
    ledger.close()


def test_ledger_rejects_corrupt_v2_before_v3_migration_without_partial_schema(
    tmp_path,
) -> None:
    database = tmp_path / "corrupt-v2.db"
    _create_v2_database(database, with_note=True)
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM note_search")
    before = database.read_bytes()

    with pytest.raises(LedgerCorruptionError, match="note search"):
        TuiLedger(database)

    assert database.read_bytes() == before
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_schema WHERE name = 'commands'"
        ).fetchone()[0] == 0


def test_ledger_rejects_semantically_corrupt_v1_note_without_modification(tmp_path) -> None:
    database = tmp_path / "semantic-v1.db"
    _create_v1_database(database, with_note=True)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE notes SET body = 'column disagrees' WHERE note_id = 'note:legacy'"
        )
    before = database.read_bytes()

    with pytest.raises(LedgerCorruptionError, match="note content"):
        TuiLedger(database)

    assert database.read_bytes() == before
    assert not database.with_name(f"{database.name}-wal").exists()
    assert not database.with_name(f"{database.name}-shm").exists()
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_schema WHERE name = 'note_search'"
        ).fetchone()[0] == 0


def test_ledger_rejects_v1_note_history_identity_mutation(tmp_path) -> None:
    database = tmp_path / "identity-v1.db"
    _create_v1_database(database, with_note=True)
    with sqlite3.connect(database) as connection:
        original = json.loads(
            connection.execute(
                "SELECT payload_json FROM notes WHERE note_id = 'note:legacy'"
            ).fetchone()[0]
        )
        mutated_history = json.loads(json.dumps(original))
        mutated_history["target"]["target_id"] = "MSFT"
        mutated_history_json = json.dumps(
            mutated_history,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        current = json.loads(json.dumps(original))
        current["body"] = "new context"
        current["revision"] = 2
        current["updated_at_utc"] = "2026-08-03T16:00:01Z"
        current_json = json.dumps(
            current,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        connection.execute(
            """
            UPDATE notes
            SET body = ?, revision = ?, updated_at_utc = ?, payload_json = ?
            WHERE note_id = 'note:legacy'
            """,
            ("new context", 2, "2026-08-03T16:00:01Z", current_json),
        )
        connection.execute("DROP TRIGGER note_history_no_update")
        connection.execute(
            "UPDATE note_history SET payload_json = ? WHERE note_id = 'note:legacy'",
            (mutated_history_json,),
        )
        connection.executescript(
            """
            CREATE TRIGGER note_history_no_update
            BEFORE UPDATE ON note_history
            BEGIN
                SELECT RAISE(ABORT, 'note history is immutable');
            END;
            """
        )
        connection.execute(
            """
            INSERT INTO note_history(note_id, revision, changed_at_utc, payload_json)
            VALUES ('note:legacy', 2, '2026-08-03T16:00:01Z', ?)
            """,
            (current_json,),
        )
    before = database.read_bytes()

    with pytest.raises(LedgerCorruptionError, match="note content"):
        TuiLedger(database)

    assert database.read_bytes() == before


def test_ledger_rejects_damaged_v1_without_modifying_it(tmp_path) -> None:
    database = tmp_path / "damaged-v1.db"
    _create_v1_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TRIGGER events_no_delete")
    before = database.read_bytes()

    with pytest.raises(LedgerSchemaError, match="schema"):
        TuiLedger(database)

    assert database.read_bytes() == before
    assert not database.with_name(f"{database.name}-wal").exists()
    assert not database.with_name(f"{database.name}-shm").exists()


def test_ledger_rejects_foreign_object_in_claimed_v1_without_modifying_it(tmp_path) -> None:
    database = tmp_path / "foreign-v1.db"
    _create_v1_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE foreign_state(value TEXT)")
    before = database.read_bytes()

    with pytest.raises(LedgerSchemaError, match="schema"):
        TuiLedger(database)

    assert database.read_bytes() == before


def test_ledger_rejects_nested_transactions_and_rolls_back(tmp_path) -> None:
    ledger = TuiLedger(tmp_path / "events.db")
    with ledger.transaction() as connection:
        with pytest.raises(LedgerTransactionError, match="nested"):
            with ledger.transaction():
                pass
        connection.execute("CREATE TABLE committed_probe(value INTEGER)")

    with pytest.raises(RuntimeError, match="abort"):
        with ledger.transaction() as connection:
            connection.execute("CREATE TABLE rolled_back_probe(value INTEGER)")
            raise RuntimeError("abort")

    with ledger.read() as connection:
        names = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_schema WHERE type = 'table'")
        }
    ledger.close()
    assert "committed_probe" in names
    assert "rolled_back_probe" not in names


def test_ledger_close_is_idempotent_and_blocks_all_later_access(tmp_path) -> None:
    ledger = TuiLedger(tmp_path / "events.db")
    ledger.close()
    ledger.close()
    with pytest.raises(LedgerClosedError):
        with ledger.read():
            pass
    with pytest.raises(LedgerClosedError):
        with ledger.transaction():
            pass


def test_ledger_claims_only_a_truly_empty_sqlite_database(tmp_path) -> None:
    database = tmp_path / "empty.db"
    sqlite3.connect(database).close()

    ledger = TuiLedger(database)
    with ledger.read() as connection:
        assert connection.execute("PRAGMA application_id").fetchone()[0] == APPLICATION_ID
    ledger.close()


def test_read_context_is_query_only_and_transactions_still_write(tmp_path) -> None:
    ledger = TuiLedger(tmp_path / "events.db")
    with ledger.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("CREATE TABLE bypass(value INTEGER)")

    with ledger.transaction() as connection:
        connection.execute("CREATE TABLE governed(value INTEGER)")
    ledger.close()


def test_schema_validation_rejects_inert_triggers_and_fake_fts(tmp_path) -> None:
    inert_trigger = tmp_path / "inert-trigger.db"
    TuiLedger(inert_trigger).close()
    with sqlite3.connect(inert_trigger) as connection:
        connection.execute("DROP TRIGGER events_no_update")
        connection.execute(
            "CREATE TRIGGER events_no_update BEFORE UPDATE ON events BEGIN SELECT 1; END"
        )
    with pytest.raises(LedgerSchemaError, match="schema"):
        TuiLedger(inert_trigger)

    fake_fts = tmp_path / "fake-fts.db"
    TuiLedger(fake_fts).close()
    with sqlite3.connect(fake_fts) as connection:
        connection.execute("DROP TABLE event_search")
        connection.execute(
            "CREATE TABLE event_search("
            "event_id TEXT, source TEXT, summary TEXT, agent_id TEXT, symbol TEXT, "
            "model_id TEXT, approval_id TEXT, order_id TEXT, evidence_ids TEXT)"
        )
    with pytest.raises(LedgerSchemaError, match="schema"):
        TuiLedger(fake_fts)


def test_append_is_ordered_idempotent_and_conflicting_replay_is_rejected(tmp_path) -> None:
    store = EventStore(tmp_path / "events.db")
    first = store.append(_event(1, occurred_at_utc=NOW + timedelta(days=1)))
    second = store.append(_event(2, occurred_at_utc=NOW - timedelta(days=1)))

    assert (first.sequence, second.sequence) == (1, 2)
    assert store.append(_event(1, occurred_at_utc=NOW + timedelta(days=1))) == first
    with pytest.raises(EventConflictError, match="event:1"):
        store.append(
            _event(
                1,
                occurred_at_utc=NOW + timedelta(days=1),
                summary="Conflicting content",
            )
        )
    third = store.append(_event(3))
    assert third.sequence == 3
    with store._ledger.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM event_search").fetchone()[0] == 3
    assert tuple(row.event_id for row in store.since(0, 10)) == (
        "event:1",
        "event:2",
        "event:3",
    )
    store.close()


def test_append_uses_sorted_json_and_sql_tables_are_append_only(tmp_path) -> None:
    ledger = TuiLedger(tmp_path / "events.db")
    store = EventStore(ledger)
    stored = store.append(_event(1))
    with ledger.read() as connection:
        raw = connection.execute(
            "SELECT payload_json FROM events WHERE event_id = ?", (stored.event_id,)
        ).fetchone()[0]
    assert raw == json.dumps(
        _event(1).model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with ledger.transaction() as connection:
            connection.execute("UPDATE events SET summary = 'changed' WHERE event_id = 'event:1'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with ledger.transaction() as connection:
            connection.execute("DELETE FROM events WHERE event_id = 'event:1'")
    ledger.close()


def test_since_validates_bounds_and_pages_ten_thousand_rows_without_gaps(tmp_path) -> None:
    ledger = TuiLedger(tmp_path / "events.db")
    store = EventStore(ledger)
    with ledger.transaction() as connection:
        for index in range(1, 10_001):
            store._append_in_transaction(connection, _event(index))

    sequences: list[int] = []
    cursor = 0
    while True:
        page = store.since(cursor, 997)
        if not page:
            break
        sequences.extend(item.sequence for item in page)
        cursor = page[-1].sequence
    assert sequences == list(range(1, 10_001))

    for sequence, limit in ((-1, 1), (True, 1), (0, 0), (0, 10_001)):
        with pytest.raises((TypeError, ValueError)):
            store.since(sequence, limit)  # type: ignore[arg-type]
    ledger.close()


def test_latest_returns_newest_admission_window_and_exact_hidden_counts(tmp_path) -> None:
    store = EventStore(tmp_path / "events.db")
    for index in range(1, 6):
        store.append(_event(index))

    window = store.latest(2)

    assert tuple(item.sequence for item in window.events) == (4, 5)
    assert tuple(item.event_id for item in window.events) == ("event:4", "event:5")
    assert window.hidden_event_count == 3
    assert window.hidden_impact_event_count == 1
    assert window.last_sequence == 5

    for limit in (0, True, 10_001):
        with pytest.raises((TypeError, ValueError)):
            store.latest(limit)  # type: ignore[arg-type]
    store.close()


def test_latest_empty_store_has_zero_cursor_and_no_hidden_events(tmp_path) -> None:
    store = EventStore(tmp_path / "events.db")

    window = store.latest(100)

    assert window.events == ()
    assert window.hidden_event_count == 0
    assert window.hidden_impact_event_count == 0
    assert window.last_sequence == 0
    store.close()


def test_search_is_bounded_filtered_deterministic_and_fts_safe(tmp_path) -> None:
    store = EventStore(tmp_path / "events.db")
    for index in range(1, 121):
        symbol = "AAPL" if index % 2 else "MSFT"
        store.append(_event(index, symbol=symbol, summary=f"review signal common {index}"))
    id_only = store.append(
        _event(
            121,
            event_id="lookup:unique",
            summary="separate text",
            evidence_ids=(),
        )
    )

    results = store.search("review common", EventFilters(symbol="AAPL"), 100)
    assert len(results) == 60
    assert all(item.symbol == "AAPL" for item in results)
    assert [item.sequence for item in results] == sorted(
        (item.sequence for item in results), reverse=True
    )
    assert len(store.search("common", EventFilters(), 100)) == 100
    assert store.search("lookup unique", EventFilters(), 100) == (id_only,)
    assert store.search("look uni", EventFilters(), 100) == (id_only,)
    assert store.search("--- ??? ' \"", EventFilters(), 100) == ()
    for hostile in ('AAPL" OR MSFT*', "NEAR(AAPL MSFT)", "agent_id:AAPL", "' OR 1=1 --"):
        filtered = store.search(hostile, EventFilters(symbol="AAPL"), 100)
        assert all(item.symbol == "AAPL" for item in filtered)
    with pytest.raises(ValueError, match="256"):
        store.search("x" * 257, EventFilters(), 100)
    with pytest.raises(ValueError, match="empty"):
        store.search("", EventFilters(), 100)
    with pytest.raises(ValueError, match="empty"):
        store.search("   ", EventFilters(), 100)
    store.search("x", EventFilters(), 100)
    store.search("x" * 256, EventFilters(), 100)
    for invalid_limit in (0, 101, True):
        with pytest.raises((TypeError, ValueError)):
            store.search("common", EventFilters(), invalid_limit)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        EventFilters.model_validate({"unknown": "field"})
    store.close()


def test_two_store_instances_serialize_concurrent_writers(tmp_path) -> None:
    database = tmp_path / "events.db"
    stores = (EventStore(database), EventStore(database))
    barrier = threading.Barrier(2)

    def append_range(store: EventStore, start: int) -> None:
        barrier.wait(timeout=5)
        for index in range(start, start + 50):
            store.append(_event(index))

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (
            executor.submit(append_range, stores[0], 1),
            executor.submit(append_range, stores[1], 51),
        )
        for future in futures:
            future.result(timeout=15)

    rows = stores[0].since(0, 1_000)
    assert [row.sequence for row in rows] == list(range(1, 101))
    assert len({row.event_id for row in rows}) == 100
    for store in stores:
        store.close()


def test_concurrent_same_id_replays_once_and_conflict_changes_nothing(tmp_path) -> None:
    database = tmp_path / "events.db"
    stores = (EventStore(database), EventStore(database))
    barrier = threading.Barrier(2)

    def append_same(store: EventStore):
        barrier.wait(timeout=5)
        return store.append(_event(1))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(append_same, stores))
    assert results[0] == results[1]
    assert results[0].sequence == 1

    with pytest.raises(EventConflictError):
        stores[1].append(_event(1, summary="conflict"))
    assert stores[0].append(_event(2)).sequence == 2
    with stores[0]._ledger.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM event_search").fetchone()[0] == 2
    for store in stores:
        store.close()


def test_wal_reader_sees_only_committed_events(tmp_path) -> None:
    database = tmp_path / "events.db"
    writer_ledger = TuiLedger(database)
    writer = EventStore(writer_ledger)
    reader = EventStore(database)

    with writer_ledger.transaction() as connection:
        writer._append_in_transaction(connection, _event(1))
        assert reader.since(0, 10) == ()
    assert tuple(row.event_id for row in reader.since(0, 10)) == ("event:1",)
    reader.close()
    writer_ledger.close()


def test_strict_inputs_and_corrupt_rows_fail_closed(tmp_path) -> None:
    with pytest.raises(ValidationError):
        EventInput.model_validate({**_event(1).model_dump(mode="python"), "unknown": True})
    with pytest.raises(ValidationError):
        EventInput.model_validate_json(
            json.dumps(
                {
                    **_event(1).model_dump(mode="json"),
                    "occurred_at_utc": "2026-08-03T12:00:00-04:00",
                }
            )
        )
    zero_offset = EventInput.model_validate_json(
        json.dumps(
            {
                **_event(1).model_dump(mode="json"),
                "occurred_at_utc": "2026-08-03T16:00:00+00:00",
            }
        )
    )
    assert zero_offset.occurred_at_utc == NOW
    with pytest.raises(ValidationError):
        EventInput.model_validate_json(
            json.dumps(
                {
                    **_event(1).model_dump(mode="json"),
                    "occurred_at_utc": "2026-08-03T16:00:00",
                }
            )
        )

    ledger = TuiLedger(tmp_path / "events.db")
    store = EventStore(ledger)
    store.append(_event(1))
    with ledger.transaction() as connection:
        connection.execute("DROP TRIGGER events_no_update")
        connection.execute(
            "UPDATE events SET payload_json = ? WHERE event_id = 'event:1'",
            ('{"event_id":"event:1"}',),
        )
    with pytest.raises(LedgerCorruptionError):
        store.since(0, 10)
    ledger.close()


def test_reopen_preserves_rows_and_continues_the_admission_sequence(tmp_path) -> None:
    database = tmp_path / "events.db"
    first = EventStore(database)
    first.append(_event(1, occurred_at_utc=NOW.replace(microsecond=123456)))
    first.close()

    reopened = EventStore(database)
    assert reopened.since(0, 10)[0].occurred_at_utc.microsecond == 123456
    assert reopened.append(_event(2)).sequence == 2
    with reopened._ledger.read() as connection:
        raw = connection.execute(
            "SELECT payload_json FROM events WHERE event_id = 'event:1'"
        ).fetchone()[0]
    assert '"occurred_at_utc":"2026-08-03T16:00:00.123456Z"' in raw
    reopened.close()


def test_owned_and_borrowed_ledger_close_behavior(tmp_path) -> None:
    owned = EventStore(tmp_path / "owned.db")
    owned.close()
    owned.close()
    with pytest.raises(LedgerClosedError):
        owned.since(0, 1)

    ledger = TuiLedger(tmp_path / "shared.db")
    borrowed = EventStore(ledger)
    borrowed.close()
    borrowed.close()
    other = EventStore(ledger)
    assert other.append(_event(1)).sequence == 1
    ledger.close()

    retryable = EventStore(tmp_path / "retryable.db")
    with retryable._ledger.transaction():
        with pytest.raises(LedgerTransactionError):
            retryable.close()
    assert retryable.append(_event(1)).sequence == 1
    retryable.close()


def test_public_event_admission_is_transaction_bound_idempotent_and_conflict_safe(
    tmp_path,
) -> None:
    ledger = TuiLedger(tmp_path / "events.db")
    other_ledger = TuiLedger(tmp_path / "other.db")
    store = EventStore(ledger)
    with ledger.read() as connection:
        with pytest.raises(LedgerTransactionError):
            store.append_in_transaction(connection, _event(1))
    with other_ledger.transaction() as connection:
        with pytest.raises(LedgerTransactionError):
            store.append_in_transaction(connection, _event(1))

    with ledger.transaction() as connection:
        admitted = store.append_in_transaction(connection, _event(1))
        replayed = store.append_in_transaction(connection, _event(1))
        assert replayed == admitted
        with pytest.raises(EventConflictError):
            store.append_in_transaction(connection, _event(1, summary="conflict"))

    assert store.since(0, 10) == (admitted,)
    with ledger.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM event_search").fetchone()[0] == 1
    ledger.close()
    other_ledger.close()


def test_fts_failure_rolls_back_the_event_row(tmp_path) -> None:
    ledger = TuiLedger(tmp_path / "events.db")
    store = EventStore(ledger)
    with ledger.transaction() as connection:
        connection.execute("DROP TABLE event_search")

    with pytest.raises(sqlite3.OperationalError):
        store.append(_event(1))
    with ledger.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    ledger.close()


def test_invalid_event_json_is_rejected_by_the_database(tmp_path) -> None:
    ledger = TuiLedger(tmp_path / "events.db")
    with pytest.raises(sqlite3.IntegrityError):
        with ledger.transaction() as connection:
            connection.execute(
                """
                INSERT INTO events (
                    event_id, occurred_at_utc, impact, severity, summary, agent_id,
                    symbol, model_id, approval_id, order_id, source, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "event:invalid-json",
                    "2026-08-03T16:00:00Z",
                    0,
                    "info",
                    "invalid JSON probe",
                    None,
                    None,
                    None,
                    None,
                    None,
                    "test",
                    "{",
                ),
            )
    with ledger.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    ledger.close()


def test_unicode_search_and_database_path_are_supported(tmp_path) -> None:
    store = EventStore(tmp_path / "state with spaces" / "résumé.db")
    stored = store.append(_event(1, summary="Résumé review"))
    assert store.search("résumé", EventFilters(), 10) == (stored,)
    store.close()
