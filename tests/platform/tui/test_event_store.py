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
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type IN ('table', 'view')"
            )
        }
    ledger.close()

    assert {"events", "event_search", "notes", "note_history"} <= tables
    reopened = TuiLedger(database)
    reopened.close()


def test_ledger_rejects_future_wrong_and_corrupt_databases(tmp_path) -> None:
    future = tmp_path / "future.db"
    TuiLedger(future).close()
    with sqlite3.connect(future) as connection:
        connection.execute("PRAGMA user_version = 2")
    future_before = future.read_bytes()
    with pytest.raises(LedgerSchemaError, match="newer"):
        TuiLedger(future)
    assert future.read_bytes() == future_before
    with sqlite3.connect(future) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2

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
            "CREATE TRIGGER events_no_update BEFORE UPDATE ON events "
            "BEGIN SELECT 1; END"
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


def test_event_transaction_helper_requires_its_own_active_ledger_transaction(tmp_path) -> None:
    ledger = TuiLedger(tmp_path / "events.db")
    other_ledger = TuiLedger(tmp_path / "other.db")
    store = EventStore(ledger)
    with ledger.read() as connection:
        with pytest.raises(LedgerTransactionError):
            store._append_in_transaction(connection, _event(1))
    with other_ledger.transaction() as connection:
        with pytest.raises(LedgerTransactionError):
            store._append_in_transaction(connection, _event(1))
    assert store.since(0, 10) == ()
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
