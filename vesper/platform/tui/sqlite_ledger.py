"""Shared SQLite transaction owner for local TUI state."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Iterator


APPLICATION_ID = 0x56323054
SCHEMA_VERSION = 2

_SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_UTC_TIMESTAMP_PATTERN = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?Z$"
)
_NOTE_PAYLOAD_KEYS = {
    "author",
    "body",
    "context_only",
    "created_at_utc",
    "note_id",
    "revision",
    "target",
    "updated_at_utc",
    "visibility",
}


class LedgerClosedError(RuntimeError):
    """Raised when a closed ledger is used."""


class LedgerCorruptionError(RuntimeError):
    """Raised when the database is not readable SQLite state."""


class LedgerSchemaError(RuntimeError):
    """Raised when the database schema is not owned or understood by V20."""


class LedgerTransactionError(RuntimeError):
    """Raised when transaction ownership is violated."""


_REQUIRED_COLUMNS_V1 = {
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

_SCHEMA_V1 = """
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

_SCHEMAS = {
    1: _SCHEMA_V1,
    2: _SCHEMA_V1 + _NOTE_SEARCH_SCHEMA,
}
_REQUIRED_COLUMNS = {
    1: _REQUIRED_COLUMNS_V1,
    2: {
        **_REQUIRED_COLUMNS_V1,
        "note_search": (
            "note_id",
            "target_type",
            "target_id",
            "body",
            "visibility",
            "author",
        ),
    },
}


def _normalize_schema_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip().rstrip(";")).casefold()


@lru_cache(maxsize=len(_SCHEMAS))
def _expected_schema_objects(version: int) -> tuple[tuple[str, str, str], ...]:
    connection = sqlite3.connect(":memory:", isolation_level=None)
    try:
        connection.executescript(_SCHEMAS[version])
        rows = connection.execute(
            "SELECT name, type, sql FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY name",
        ).fetchall()
        return tuple(
            (
                str(name),
                str(object_type),
                "" if sql is None else _normalize_schema_sql(str(sql)),
            )
            for name, object_type, sql in rows
        )
    finally:
        connection.close()


def _invalid_note_content() -> LedgerCorruptionError:
    return LedgerCorruptionError("TUI ledger note content is invalid")


def _is_safe_id(value: object) -> bool:
    return type(value) is str and _SAFE_ID_PATTERN.fullmatch(value) is not None


def _parse_canonical_utc(value: object) -> datetime | None:
    if type(value) is not str or _UTC_TIMESTAMP_PATTERN.fullmatch(value) is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _decode_note_payload(payload_json: object) -> dict[str, object]:
    if type(payload_json) is not str:
        raise _invalid_note_content()
    try:
        payload = json.loads(payload_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise _invalid_note_content() from exc
    if type(payload) is not dict or set(payload) != _NOTE_PAYLOAD_KEYS:
        raise _invalid_note_content()
    target = payload["target"]
    if type(target) is not dict or set(target) != {"target_id", "target_type"}:
        raise _invalid_note_content()
    revision = payload["revision"]
    created_at = _parse_canonical_utc(payload["created_at_utc"])
    updated_at = _parse_canonical_utc(payload["updated_at_utc"])
    if (
        not _is_safe_id(payload["note_id"])
        or not _is_safe_id(payload["author"])
        or type(payload["body"]) is not str
        or not 1 <= len(payload["body"]) <= 8_000
        or type(payload["visibility"]) is not str
        or payload["visibility"] not in {"private", "shared"}
        or type(revision) is not int
        or not 1 <= revision <= 2**63 - 1
        or payload["context_only"] is not True
        or type(target["target_type"]) is not str
        or target["target_type"] not in {"stock", "order", "approval", "agent-event"}
        or not _is_safe_id(target["target_id"])
        or created_at is None
        or updated_at is None
        or updated_at < created_at
    ):
        raise _invalid_note_content()
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if canonical != payload_json:
        raise _invalid_note_content()
    return payload


def _note_identity(payload: dict[str, object]) -> tuple[object, object, object, object]:
    target = payload["target"]
    if not isinstance(target, dict):
        raise _invalid_note_content()
    return (
        target["target_type"],
        target["target_id"],
        payload["author"],
        payload["created_at_utc"],
    )


class TuiLedger:
    """Own one serialized SQLite connection and its transaction boundary."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._connection: sqlite3.Connection | None = None
        self._transaction_owner: int | None = None

        existed = self.path.exists() and self.path.stat().st_size > 0
        existing_version = 0
        if existed:
            existing_version = self._preflight_existing()
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
            if existed and existing_version:
                self._validate_owned_schema(connection, expected_version=existing_version)
                self._configure(connection)
                if existing_version < SCHEMA_VERSION:
                    self._migrate_schema(connection, existing_version)
            else:
                self._configure(connection)
                self._initialize_schema(connection)
            self._validate_owned_schema(connection, expected_version=SCHEMA_VERSION)
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

    def _preflight_existing(self) -> int:
        try:
            uri = f"{self.path.resolve().as_uri()}?mode=ro"
            connection = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5)
            connection.row_factory = sqlite3.Row
            try:
                if self._is_unclaimed_empty(connection):
                    return 0
                self._validate_owned_schema(connection)
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                if version == 1:
                    self._validate_v1_note_content(connection)
                return version
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
                + _SCHEMAS[SCHEMA_VERSION]
                + f"\nPRAGMA application_id = {APPLICATION_ID};"
                + f"\nPRAGMA user_version = {SCHEMA_VERSION};"
                + "\nCOMMIT;"
            )
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise

    @staticmethod
    def _migrate_schema(connection: sqlite3.Connection, version: int) -> None:
        if version != 1:
            raise LedgerSchemaError("unsupported TUI ledger schema version")
        try:
            connection.execute("BEGIN IMMEDIATE")
            TuiLedger._validate_v1_note_content(connection)
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
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            TuiLedger._validate_note_search_parity(connection)
            TuiLedger._validate_owned_schema(
                connection,
                expected_version=SCHEMA_VERSION,
            )
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise

    @staticmethod
    def _validate_v1_note_content(connection: sqlite3.Connection) -> None:
        current: dict[str, tuple[int, str, dict[str, object]]] = {}
        for row in connection.execute("SELECT * FROM notes ORDER BY note_sequence"):
            payload = _decode_note_payload(row["payload_json"])
            target = payload["target"]
            assert isinstance(target, dict)
            expected = {
                "note_id": payload["note_id"],
                "target_type": target["target_type"],
                "target_id": target["target_id"],
                "body": payload["body"],
                "visibility": payload["visibility"],
                "author": payload["author"],
                "revision": payload["revision"],
                "created_at_utc": payload["created_at_utc"],
                "updated_at_utc": payload["updated_at_utc"],
            }
            if any(row[name] != value for name, value in expected.items()):
                raise _invalid_note_content()
            note_id = str(payload["note_id"])
            current[note_id] = (
                int(payload["revision"]),
                str(row["payload_json"]),
                payload,
            )

        history: dict[str, list[tuple[int, str, dict[str, object]]]] = {}
        for row in connection.execute(
            "SELECT * FROM note_history ORDER BY note_id, revision"
        ):
            payload = _decode_note_payload(row["payload_json"])
            expected = {
                "note_id": payload["note_id"],
                "revision": payload["revision"],
                "changed_at_utc": payload["updated_at_utc"],
            }
            if any(row[name] != value for name, value in expected.items()):
                raise _invalid_note_content()
            note_id = str(payload["note_id"])
            history.setdefault(note_id, []).append(
                (int(payload["revision"]), str(row["payload_json"]), payload)
            )

        if set(history) != set(current):
            raise _invalid_note_content()
        for note_id, (current_revision, current_json, current_payload) in current.items():
            revisions = history[note_id]
            if [revision for revision, _, _ in revisions] != list(
                range(1, current_revision + 1)
            ):
                raise _invalid_note_content()
            latest_revision, latest_json, _ = revisions[-1]
            if (latest_revision, latest_json) != (current_revision, current_json):
                raise _invalid_note_content()
            identity = _note_identity(current_payload)
            previous_updated: datetime | None = None
            for _, _, payload in revisions:
                if _note_identity(payload) != identity:
                    raise _invalid_note_content()
                updated = _parse_canonical_utc(payload["updated_at_utc"])
                if updated is None:
                    raise _invalid_note_content()
                if previous_updated is not None and updated < previous_updated:
                    raise _invalid_note_content()
                previous_updated = updated

    @staticmethod
    def _validate_note_search_parity(connection: sqlite3.Connection) -> None:
        note_count = int(connection.execute("SELECT COUNT(*) FROM notes").fetchone()[0])
        search_count = int(
            connection.execute("SELECT COUNT(*) FROM note_search").fetchone()[0]
        )
        parity_count = int(
            connection.execute(
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
        )
        if search_count != note_count or parity_count != note_count:
            raise LedgerCorruptionError("TUI ledger note search content is invalid")
        connection.execute("INSERT INTO note_search(note_search) VALUES ('integrity-check')")

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
    def _validate_owned_schema(
        connection: sqlite3.Connection,
        *,
        expected_version: int | None = None,
    ) -> None:
        application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        objects = tuple(
            (
                str(row[0]),
                str(row[1]),
                "" if row[2] is None else _normalize_schema_sql(str(row[2])),
            )
            for row in connection.execute(
                "SELECT name, type, sql FROM sqlite_schema "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        )
        if application_id == 0 and version == 0 and not objects:
            raise LedgerSchemaError("unrecognized empty SQLite database")
        if application_id != APPLICATION_ID:
            if application_id == 0:
                raise LedgerSchemaError("unrecognized SQLite database")
            raise LedgerSchemaError("unexpected TUI ledger application ID")
        if version > SCHEMA_VERSION:
            raise LedgerSchemaError("TUI ledger schema is newer than this V20 build")
        if version not in _SCHEMAS:
            raise LedgerSchemaError("unsupported TUI ledger schema version")
        if expected_version is not None and version != expected_version:
            raise LedgerSchemaError("TUI ledger schema version changed unexpectedly")
        if objects != _expected_schema_objects(version):
            raise LedgerSchemaError("TUI ledger schema definition is invalid")
        for table, expected_columns in _REQUIRED_COLUMNS[version].items():
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
