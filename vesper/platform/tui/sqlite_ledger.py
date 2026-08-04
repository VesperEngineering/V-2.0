"""Shared SQLite transaction owner for local TUI state."""

from __future__ import annotations

import re
import sqlite3
import threading
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator


APPLICATION_ID = 0x56323054
SCHEMA_VERSION = 1


class LedgerClosedError(RuntimeError):
    """Raised when a closed ledger is used."""


class LedgerCorruptionError(RuntimeError):
    """Raised when the database is not readable SQLite state."""


class LedgerSchemaError(RuntimeError):
    """Raised when the database schema is not owned or understood by V20."""


class LedgerTransactionError(RuntimeError):
    """Raised when transaction ownership is violated."""


_REQUIRED_OBJECTS = {
    "events": "table",
    "event_search": "table",
    "notes": "table",
    "note_history": "table",
    "events_no_update": "trigger",
    "events_no_delete": "trigger",
    "note_history_no_update": "trigger",
    "note_history_no_delete": "trigger",
    "notes_target_order": "index",
}

_REQUIRED_COLUMNS = {
    "events": (
        "sequence",
        "event_id",
        "occurred_at_utc",
        "impact",
        "severity",
        "summary",
        "agent_id",
        "symbol",
        "model_id",
        "approval_id",
        "order_id",
        "source",
        "payload_json",
    ),
    "event_search": (
        "event_id",
        "source",
        "summary",
        "agent_id",
        "symbol",
        "model_id",
        "approval_id",
        "order_id",
        "evidence_ids",
    ),
    "notes": (
        "note_sequence",
        "note_id",
        "target_type",
        "target_id",
        "body",
        "visibility",
        "author",
        "revision",
        "created_at_utc",
        "updated_at_utc",
        "payload_json",
    ),
    "note_history": (
        "history_sequence",
        "note_id",
        "revision",
        "changed_at_utc",
        "payload_json",
    ),
}

_SCHEMA = """
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


def _normalize_schema_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip().rstrip(";")).casefold()


@lru_cache(maxsize=1)
def _expected_schema_sql() -> tuple[tuple[str, str], ...]:
    connection = sqlite3.connect(":memory:", isolation_level=None)
    try:
        connection.executescript(_SCHEMA)
        placeholders = ",".join("?" for _ in _REQUIRED_OBJECTS)
        rows = connection.execute(
            f"SELECT name, sql FROM sqlite_schema WHERE name IN ({placeholders})",
            tuple(_REQUIRED_OBJECTS),
        ).fetchall()
        return tuple(
            sorted((str(name), _normalize_schema_sql(str(sql))) for name, sql in rows)
        )
    finally:
        connection.close()


class TuiLedger:
    """Own one serialized SQLite connection and its transaction boundary."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._connection: sqlite3.Connection | None = None
        self._transaction_owner: int | None = None

        existed = self.path.exists() and self.path.stat().st_size > 0
        claim_empty_database = False
        if existed:
            claim_empty_database = self._preflight_existing()
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)

        try:
            connection = sqlite3.connect(
                self.path,
                check_same_thread=False,
                isolation_level=None,
                timeout=5,
            )
            connection.row_factory = sqlite3.Row
            self._connection = connection
            if existed and not claim_empty_database:
                self._validate_owned_schema(connection)
                self._configure(connection)
            else:
                self._configure(connection)
                self._initialize_schema(connection)
            self._validate_owned_schema(connection)
        except LedgerSchemaError:
            self._close_after_failed_open()
            raise
        except sqlite3.DatabaseError as exc:
            self._close_after_failed_open()
            raise LedgerCorruptionError("TUI ledger is not readable SQLite state") from exc
        except BaseException:
            self._close_after_failed_open()
            raise

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        """Hold the shared connection lock for one consistent read operation."""

        with self._lock:
            connection = self._require_open()
            if self._transaction_owner is not None or connection.in_transaction:
                raise LedgerTransactionError(
                    "public reads are not allowed during an active transaction"
                )
            previous_query_only = int(
                connection.execute("PRAGMA query_only").fetchone()[0]
            )
            connection.execute("PRAGMA query_only = ON")
            try:
                yield connection
            finally:
                connection.execute(f"PRAGMA query_only = {previous_query_only}")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run one serialized immediate transaction and roll back on any failure."""

        with self._lock:
            connection = self._require_open()
            if self._transaction_owner is not None or connection.in_transaction:
                raise LedgerTransactionError("nested ledger transactions are not allowed")
            owner = threading.get_ident()
            self._transaction_owner = owner
            try:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    yield connection
                except BaseException:
                    if connection.in_transaction:
                        connection.execute("ROLLBACK")
                    raise
                try:
                    connection.execute("COMMIT")
                except BaseException:
                    if connection.in_transaction:
                        connection.execute("ROLLBACK")
                    raise
            finally:
                self._transaction_owner = None

    def require_transaction(self, connection: sqlite3.Connection) -> None:
        """Require the caller to use this ledger's active transaction."""

        with self._lock:
            current = self._require_open()
            if (
                connection is not current
                or self._transaction_owner != threading.get_ident()
                or not current.in_transaction
            ):
                raise LedgerTransactionError(
                    "operation requires this ledger's active transaction"
                )

    def close(self) -> None:
        """Close the owned connection; repeated closes are harmless."""

        with self._lock:
            connection = self._connection
            if connection is None:
                return
            if self._transaction_owner is not None or connection.in_transaction:
                raise LedgerTransactionError("cannot close an active ledger transaction")
            self._connection = None
            connection.close()

    def _require_open(self) -> sqlite3.Connection:
        connection = self._connection
        if connection is None:
            raise LedgerClosedError("TUI ledger is closed")
        return connection

    def _close_after_failed_open(self) -> None:
        connection = self._connection
        self._connection = None
        if connection is not None:
            connection.close()

    def _preflight_existing(self) -> bool:
        try:
            uri = f"{self.path.resolve().as_uri()}?mode=ro"
            connection = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5)
            connection.row_factory = sqlite3.Row
            try:
                if self._is_unclaimed_empty(connection):
                    return True
                self._validate_owned_schema(connection)
                return False
            finally:
                connection.close()
        except LedgerSchemaError:
            raise
        except sqlite3.DatabaseError as exc:
            raise LedgerCorruptionError("TUI ledger is not readable SQLite state") from exc

    @staticmethod
    def _configure(connection: sqlite3.Connection) -> None:
        mode = str(connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]).casefold()
        if mode != "wal":
            raise LedgerSchemaError("TUI ledger could not enable WAL mode")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise LedgerSchemaError("TUI ledger could not enable foreign keys")

    @staticmethod
    def _initialize_schema(connection: sqlite3.Connection) -> None:
        try:
            connection.executescript(
                "BEGIN IMMEDIATE;\n"
                + _SCHEMA
                + f"\nPRAGMA application_id = {APPLICATION_ID};"
                + f"\nPRAGMA user_version = {SCHEMA_VERSION};"
                + "\nCOMMIT;"
            )
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise

    @staticmethod
    def _is_unclaimed_empty(connection: sqlite3.Connection) -> bool:
        application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        object_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'"
            ).fetchone()[0]
        )
        return application_id == 0 and version == 0 and object_count == 0

    @staticmethod
    def _validate_owned_schema(connection: sqlite3.Connection) -> None:
        application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        objects = {
            str(row[0]): (str(row[1]), "" if row[2] is None else str(row[2]))
            for row in connection.execute(
                "SELECT name, type, sql FROM sqlite_schema "
                "WHERE name NOT LIKE 'sqlite_%'"
            )
        }
        if application_id == 0 and version == 0 and not objects:
            raise LedgerSchemaError("unrecognized empty SQLite database")
        if application_id != APPLICATION_ID:
            if application_id == 0:
                raise LedgerSchemaError("unrecognized SQLite database")
            raise LedgerSchemaError("unexpected TUI ledger application ID")
        if version > SCHEMA_VERSION:
            raise LedgerSchemaError("TUI ledger schema is newer than this V20 build")
        if version != SCHEMA_VERSION:
            raise LedgerSchemaError("unsupported TUI ledger schema version")
        for name, expected_type in _REQUIRED_OBJECTS.items():
            actual = objects.get(name)
            if actual is None or actual[0] != expected_type:
                raise LedgerSchemaError("TUI ledger schema is incomplete or damaged")
        expected_sql = dict(_expected_schema_sql())
        for name in _REQUIRED_OBJECTS:
            if _normalize_schema_sql(objects[name][1]) != expected_sql.get(name):
                raise LedgerSchemaError("TUI ledger schema definition is invalid")
        for table, expected_columns in _REQUIRED_COLUMNS.items():
            actual_columns = tuple(
                str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")
            )
            if actual_columns != expected_columns:
                raise LedgerSchemaError("TUI ledger schema columns are incomplete or damaged")
        quick_check = tuple(
            str(row[0]) for row in connection.execute("PRAGMA quick_check")
        )
        if quick_check != ("ok",):
            raise LedgerCorruptionError("TUI ledger failed SQLite integrity checking")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise LedgerCorruptionError("TUI ledger has invalid foreign-key references")
