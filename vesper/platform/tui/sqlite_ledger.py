"""Shared SQLite transaction owner for local TUI state."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Iterator


APPLICATION_ID = 0x56323054
SCHEMA_VERSION = 4

_COMMAND_STATUS_MESSAGES = {
    "accepted": ("accepted", "Command accepted."),
    "running": ("running", "Command is running."),
    "completed": ("completed", "Command completed."),
    "failed": ("failed", "Command failed."),
    "cancelled": ("cancelled", "Command cancelled."),
}

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

_COMMAND_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE commands (
        command_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        command_id TEXT NOT NULL UNIQUE,
        command_type TEXT NOT NULL,
        request_sha256 TEXT NOT NULL CHECK (
            length(request_sha256) = 64
            AND request_sha256 NOT GLOB '*[^0-9a-f]*'
        ),
        operator_id TEXT NOT NULL,
        client_id TEXT NOT NULL,
        reviewed_control_version TEXT NOT NULL CHECK (
            reviewed_control_version = '0'
            OR (
                reviewed_control_version NOT LIKE '0%'
                AND reviewed_control_version NOT GLOB '*[^0-9]*'
                AND (
                    length(reviewed_control_version) < 20
                    OR (
                        length(reviewed_control_version) = 20
                        AND reviewed_control_version <= '18446744073709551615'
                    )
                )
            )
        ),
        reviewed_control_hash TEXT NOT NULL CHECK (
            length(reviewed_control_hash) = 64
            AND reviewed_control_hash NOT GLOB '*[^0-9a-f]*'
        ),
        handler_key TEXT,
        accepted_request_json TEXT CHECK (
            accepted_request_json IS NULL OR json_valid(accepted_request_json)
        ),
        status TEXT NOT NULL CHECK (
            status IN (
                'accepted', 'rejected', 'running', 'completed', 'failed', 'cancelled'
            )
        ),
        code TEXT NOT NULL,
        safe_message TEXT NOT NULL CHECK (length(trim(safe_message)) BETWEEN 1 AND 512),
        admitted_at_utc TEXT NOT NULL,
        accepted_at_utc TEXT,
        finished_at_utc TEXT,
        result_json TEXT CHECK (result_json IS NULL OR json_valid(result_json)),
        claim_worker_id TEXT,
        claim_token_sha256 TEXT CHECK (
            claim_token_sha256 IS NULL
            OR (
                length(claim_token_sha256) = 64
                AND claim_token_sha256 NOT GLOB '*[^0-9a-f]*'
            )
        ),
        claimed_at_utc TEXT,
        claim_expires_at_utc TEXT,
        CHECK (
            (
                status = 'rejected'
                AND handler_key IS NULL
                AND accepted_request_json IS NULL
                AND accepted_at_utc IS NULL
                AND finished_at_utc IS NOT NULL
                AND result_json IS NULL
                AND claim_worker_id IS NULL
                AND claim_token_sha256 IS NULL
                AND claimed_at_utc IS NULL
                AND claim_expires_at_utc IS NULL
            )
            OR (
                status = 'accepted'
                AND handler_key IS NOT NULL
                AND accepted_request_json IS NOT NULL
                AND accepted_at_utc IS NOT NULL
                AND finished_at_utc IS NULL
                AND result_json IS NULL
                AND claim_worker_id IS NULL
                AND claim_token_sha256 IS NULL
                AND claimed_at_utc IS NULL
                AND claim_expires_at_utc IS NULL
            )
            OR (
                status = 'running'
                AND handler_key IS NOT NULL
                AND accepted_request_json IS NOT NULL
                AND accepted_at_utc IS NOT NULL
                AND finished_at_utc IS NULL
                AND result_json IS NULL
                AND claim_worker_id IS NOT NULL
                AND claim_token_sha256 IS NOT NULL
                AND claimed_at_utc IS NOT NULL
                AND claim_expires_at_utc IS NOT NULL
            )
            OR (
                status IN ('completed', 'failed', 'cancelled')
                AND handler_key IS NOT NULL
                AND accepted_request_json IS NOT NULL
                AND accepted_at_utc IS NOT NULL
                AND finished_at_utc IS NOT NULL
                AND claim_worker_id IS NOT NULL
                AND claim_token_sha256 IS NOT NULL
                AND claimed_at_utc IS NOT NULL
                AND claim_expires_at_utc IS NOT NULL
            )
        )
    )
    """,
    """
    CREATE INDEX commands_status_expiry
    ON commands(status, claim_expires_at_utc, command_sequence)
    """,
    """
    CREATE TABLE command_receipt_events (
        event_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        command_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK (
            status IN (
                'accepted', 'rejected', 'running', 'completed', 'failed', 'cancelled'
            )
        ),
        code TEXT NOT NULL,
        safe_message TEXT NOT NULL CHECK (length(trim(safe_message)) BETWEEN 1 AND 512),
        occurred_at_utc TEXT NOT NULL,
        worker_id TEXT,
        result_json TEXT CHECK (result_json IS NULL OR json_valid(result_json)),
        FOREIGN KEY(command_id) REFERENCES commands(command_id) ON DELETE RESTRICT,
        CHECK (
            (status IN ('accepted', 'rejected') AND worker_id IS NULL AND result_json IS NULL)
            OR (status = 'running' AND worker_id IS NOT NULL AND result_json IS NULL)
            OR (status IN ('completed', 'failed', 'cancelled') AND worker_id IS NOT NULL)
        )
    )
    """,
    """
    CREATE INDEX command_receipt_events_command_order
    ON command_receipt_events(command_id, event_sequence)
    """,
    """
    CREATE TRIGGER command_receipt_events_no_update
    BEFORE UPDATE ON command_receipt_events
    BEGIN
        SELECT RAISE(ABORT, 'command receipt events are append-only');
    END
    """,
    """
    CREATE TRIGGER command_receipt_events_no_delete
    BEFORE DELETE ON command_receipt_events
    BEGIN
        SELECT RAISE(ABORT, 'command receipt events are append-only');
    END
    """,
    """
    CREATE TRIGGER commands_no_delete
    BEFORE DELETE ON commands
    BEGIN
        SELECT RAISE(ABORT, 'commands cannot be deleted');
    END
    """,
    """
    CREATE TRIGGER commands_admission_immutable
    BEFORE UPDATE ON commands
    WHEN NEW.command_sequence IS NOT OLD.command_sequence
      OR NEW.command_id IS NOT OLD.command_id
      OR NEW.command_type IS NOT OLD.command_type
      OR NEW.request_sha256 IS NOT OLD.request_sha256
      OR NEW.operator_id IS NOT OLD.operator_id
      OR NEW.client_id IS NOT OLD.client_id
      OR NEW.reviewed_control_version IS NOT OLD.reviewed_control_version
      OR NEW.reviewed_control_hash IS NOT OLD.reviewed_control_hash
      OR NEW.handler_key IS NOT OLD.handler_key
      OR NEW.accepted_request_json IS NOT OLD.accepted_request_json
      OR NEW.admitted_at_utc IS NOT OLD.admitted_at_utc
      OR NEW.accepted_at_utc IS NOT OLD.accepted_at_utc
    BEGIN
        SELECT RAISE(ABORT, 'command admission is immutable');
    END
    """,
    """
    CREATE TRIGGER commands_terminal_immutable
    BEFORE UPDATE ON commands
    WHEN OLD.status IN ('rejected', 'completed', 'failed', 'cancelled')
    BEGIN
        SELECT RAISE(ABORT, 'terminal command receipt is immutable');
    END
    """,
    """
    CREATE TRIGGER commands_status_transition
    BEFORE UPDATE ON commands
    WHEN (
        NEW.status IS NOT OLD.status
        OR NEW.code IS NOT OLD.code
        OR NEW.safe_message IS NOT OLD.safe_message
        OR NEW.finished_at_utc IS NOT OLD.finished_at_utc
        OR NEW.result_json IS NOT OLD.result_json
        OR NEW.claim_worker_id IS NOT OLD.claim_worker_id
        OR NEW.claim_token_sha256 IS NOT OLD.claim_token_sha256
        OR NEW.claimed_at_utc IS NOT OLD.claimed_at_utc
        OR NEW.claim_expires_at_utc IS NOT OLD.claim_expires_at_utc
    )
    AND NOT (
        (OLD.status = 'accepted' AND NEW.status = 'running')
        OR (
            OLD.status = 'running'
            AND NEW.status = 'running'
            AND (
                CASE
                    WHEN instr(NEW.claimed_at_utc, '.') = 0
                    THEN substr(NEW.claimed_at_utc, 1, 19) || '.000000Z'
                    ELSE substr(NEW.claimed_at_utc, 1, 20)
                         || substr(
                             substr(
                                 NEW.claimed_at_utc,
                                 21,
                                 length(NEW.claimed_at_utc) - 21
                             ) || '000000',
                             1,
                             6
                         ) || 'Z'
                END
            ) >= (
                CASE
                    WHEN instr(OLD.claim_expires_at_utc, '.') = 0
                    THEN substr(OLD.claim_expires_at_utc, 1, 19) || '.000000Z'
                    ELSE substr(OLD.claim_expires_at_utc, 1, 20)
                         || substr(
                             substr(
                                 OLD.claim_expires_at_utc,
                                 21,
                                 length(OLD.claim_expires_at_utc) - 21
                             ) || '000000',
                             1,
                             6
                         ) || 'Z'
                END
            )
            AND NEW.claim_token_sha256 IS NOT OLD.claim_token_sha256
        )
        OR (
            OLD.status = 'running'
            AND NEW.status IN ('completed', 'failed', 'cancelled')
        )
    )
    BEGIN
        SELECT RAISE(ABORT, 'invalid command status transition');
    END
    """,
)

_COMMAND_SCHEMA = ";\n".join(statement.strip() for statement in _COMMAND_SCHEMA_STATEMENTS) + ";\n"

_OPERATOR_DECISION_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE operator_decisions (
        decision_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        decision_id TEXT NOT NULL UNIQUE,
        command_id TEXT NOT NULL UNIQUE,
        run_id TEXT NOT NULL,
        checkpoint_id TEXT NOT NULL,
        operator_id TEXT NOT NULL,
        reason TEXT NOT NULL CHECK (length(trim(reason)) BETWEEN 1 AND 2000),
        decision TEXT NOT NULL CHECK (decision = 'hold'),
        decided_at_utc TEXT NOT NULL,
        content_json TEXT NOT NULL CHECK (json_valid(content_json)),
        FOREIGN KEY(command_id) REFERENCES commands(command_id) ON DELETE RESTRICT
    )
    """,
    """
    CREATE TRIGGER operator_decisions_no_update
    BEFORE UPDATE ON operator_decisions
    BEGIN
        SELECT RAISE(ABORT, 'operator decisions are immutable');
    END
    """,
    """
    CREATE TRIGGER operator_decisions_no_delete
    BEFORE DELETE ON operator_decisions
    BEGIN
        SELECT RAISE(ABORT, 'operator decisions are immutable');
    END
    """,
)

_OPERATOR_DECISION_SCHEMA = ";\n".join(
    statement.strip() for statement in _OPERATOR_DECISION_SCHEMA_STATEMENTS
) + ";\n"

_SCHEMAS = {
    1: _SCHEMA_V1,
    2: _SCHEMA_V1 + _NOTE_SEARCH_SCHEMA,
    3: _SCHEMA_V1 + _NOTE_SEARCH_SCHEMA + _COMMAND_SCHEMA,
    4: _SCHEMA_V1 + _NOTE_SEARCH_SCHEMA + _COMMAND_SCHEMA + _OPERATOR_DECISION_SCHEMA,
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
    3: {
        **_REQUIRED_COLUMNS_V1,
        "note_search": (
            "note_id",
            "target_type",
            "target_id",
            "body",
            "visibility",
            "author",
        ),
        "commands": (
            "command_sequence",
            "command_id",
            "command_type",
            "request_sha256",
            "operator_id",
            "client_id",
            "reviewed_control_version",
            "reviewed_control_hash",
            "handler_key",
            "accepted_request_json",
            "status",
            "code",
            "safe_message",
            "admitted_at_utc",
            "accepted_at_utc",
            "finished_at_utc",
            "result_json",
            "claim_worker_id",
            "claim_token_sha256",
            "claimed_at_utc",
            "claim_expires_at_utc",
        ),
        "command_receipt_events": (
            "event_sequence",
            "command_id",
            "status",
            "code",
            "safe_message",
            "occurred_at_utc",
            "worker_id",
            "result_json",
        ),
    },
    4: {
        **_REQUIRED_COLUMNS_V1,
        "note_search": (
            "note_id",
            "target_type",
            "target_id",
            "body",
            "visibility",
            "author",
        ),
        "commands": (
            "command_sequence",
            "command_id",
            "command_type",
            "request_sha256",
            "operator_id",
            "client_id",
            "reviewed_control_version",
            "reviewed_control_hash",
            "handler_key",
            "accepted_request_json",
            "status",
            "code",
            "safe_message",
            "admitted_at_utc",
            "accepted_at_utc",
            "finished_at_utc",
            "result_json",
            "claim_worker_id",
            "claim_token_sha256",
            "claimed_at_utc",
            "claim_expires_at_utc",
        ),
        "command_receipt_events": (
            "event_sequence",
            "command_id",
            "status",
            "code",
            "safe_message",
            "occurred_at_utc",
            "worker_id",
            "result_json",
        ),
        "operator_decisions": (
            "decision_sequence",
            "decision_id",
            "command_id",
            "run_id",
            "checkpoint_id",
            "operator_id",
            "reason",
            "decision",
            "decided_at_utc",
            "content_json",
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


def _invalid_command_content() -> LedgerCorruptionError:
    return LedgerCorruptionError("TUI ledger command content is invalid")


def _invalid_operator_decision_content() -> LedgerCorruptionError:
    return LedgerCorruptionError("TUI ledger operator decision content is invalid")


def _is_safe_id(value: object) -> bool:
    return type(value) is str and _SAFE_ID_PATTERN.fullmatch(value) is not None


def _is_sha256(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_wire_uint_text(value: object) -> bool:
    return (
        type(value) is str
        and value.isascii()
        and value.isdecimal()
        and (value == "0" or not value.startswith("0"))
        and int(value) <= 2**64 - 1
    )


def _decode_canonical_object(value: object) -> dict[str, object]:
    if type(value) is not str:
        raise _invalid_command_content()
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise _invalid_command_content() from exc
    if type(decoded) is not dict:
        raise _invalid_command_content()
    try:
        canonical = json.dumps(
            decoded,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise _invalid_command_content() from exc
    if canonical != value:
        raise _invalid_command_content()
    return decoded


def _contains_sensitive_key(value: object) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = "".join(
                character
                for character in unicodedata.normalize("NFKC", key).casefold()
                if character.isalnum()
            )
            if any(
                marker in normalized
                for marker in ("secret", "token", "password", "credential", "apikey")
            ) or _contains_sensitive_key(child):
                return True
    elif isinstance(value, list):
        return any(_contains_sensitive_key(child) for child in value)
    return False


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
            self._validate_note_search_parity(connection, check_index=True)
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
        if version not in (1, 2, 3):
            raise LedgerSchemaError("unsupported TUI ledger schema version")
        try:
            connection.execute("BEGIN IMMEDIATE")
            TuiLedger._validate_v1_note_content(connection)
            if version == 1:
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
            TuiLedger._validate_note_search_parity(connection, check_index=True)
            if version in (1, 2):
                for statement in _COMMAND_SCHEMA_STATEMENTS:
                    connection.execute(statement)
            TuiLedger._validate_command_content(connection)
            TuiLedger._validate_legacy_command_terminal_messages(connection)
            for statement in _OPERATOR_DECISION_SCHEMA_STATEMENTS:
                connection.execute(statement)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            TuiLedger._validate_operator_decision_content(connection)
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
    def _validate_note_search_parity(
        connection: sqlite3.Connection,
        *,
        check_index: bool,
    ) -> None:
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
        if check_index:
            connection.execute("INSERT INTO note_search(note_search) VALUES ('integrity-check')")

    @staticmethod
    def _validate_command_content(connection: sqlite3.Connection) -> None:
        from .command_contracts import (
            PAYLOAD_MODELS,
            CommandReceipt,
            CommandRequest,
            ReceiptStatus,
        )
        from .command_policy import AuthorizationDecision

        commands: dict[str, sqlite3.Row] = {}
        for row in connection.execute("SELECT * FROM commands ORDER BY command_sequence"):
            command_id = row["command_id"]
            request_sha256 = row["request_sha256"]
            control_version = row["reviewed_control_version"]
            control_hash = row["reviewed_control_hash"]
            admitted_at = _parse_canonical_utc(row["admitted_at_utc"])
            accepted_at = (
                None
                if row["accepted_at_utc"] is None
                else _parse_canonical_utc(row["accepted_at_utc"])
            )
            finished_at = (
                None
                if row["finished_at_utc"] is None
                else _parse_canonical_utc(row["finished_at_utc"])
            )
            claimed_at = (
                None
                if row["claimed_at_utc"] is None
                else _parse_canonical_utc(row["claimed_at_utc"])
            )
            claim_expires_at = (
                None
                if row["claim_expires_at_utc"] is None
                else _parse_canonical_utc(row["claim_expires_at_utc"])
            )
            if (
                not _is_safe_id(command_id)
                or not _is_safe_id(row["command_type"])
                or row["command_type"] not in PAYLOAD_MODELS
                or not _is_safe_id(row["operator_id"])
                or not _is_safe_id(row["client_id"])
                or not _is_sha256(request_sha256)
                or not _is_wire_uint_text(control_version)
                or not _is_sha256(control_hash)
                or not _is_safe_id(row["code"])
                or type(row["safe_message"]) is not str
                or not 1 <= len(row["safe_message"].strip()) <= 512
                or admitted_at is None
                or (
                    row["claim_worker_id"] is not None
                    and not _is_safe_id(row["claim_worker_id"])
                )
                or (
                    row["claim_token_sha256"] is not None
                    and not _is_sha256(row["claim_token_sha256"])
                )
            ):
                raise _invalid_command_content()
            status = row["status"]
            request_json = row["accepted_request_json"]
            result_json = row["result_json"]
            if status in {"accepted", "running"} and (
                row["code"],
                row["safe_message"],
            ) != _COMMAND_STATUS_MESSAGES[status]:
                raise _invalid_command_content()
            if request_json is not None:
                request = _decode_canonical_object(request_json)
                try:
                    typed_request = CommandRequest.model_validate_json(
                        request_json,
                        strict=True,
                    )
                    typed_canonical = json.dumps(
                        typed_request.model_dump(mode="json"),
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                        allow_nan=False,
                    )
                except (TypeError, ValueError) as exc:
                    raise _invalid_command_content() from exc
                if (
                    set(request)
                    != {
                        "command_id",
                        "command_type",
                        "confirmation",
                        "payload",
                        "reason",
                        "reviewed_control_hash",
                        "reviewed_control_version",
                    }
                    or request["command_id"] != command_id
                    or request["command_type"] != row["command_type"]
                    or request["reviewed_control_version"] != int(control_version)
                    or request["reviewed_control_hash"] != control_hash
                    or typed_canonical != request_json
                    or hashlib.sha256(request_json.encode("utf-8")).hexdigest()
                    != request_sha256
                ):
                    raise _invalid_command_content()
            if result_json is not None:
                result = _decode_canonical_object(result_json)
                if _contains_sensitive_key(result):
                    raise _invalid_command_content()
            else:
                result = None
            try:
                CommandReceipt(
                    command_id=command_id,
                    status=ReceiptStatus(status),
                    code=row["code"],
                    safe_message=row["safe_message"],
                    accepted_at_utc=row["accepted_at_utc"],
                    finished_at_utc=row["finished_at_utc"],
                    result=result,
                )
            except (TypeError, ValueError) as exc:
                raise _invalid_command_content() from exc
            if (
                (accepted_at is not None and accepted_at < admitted_at)
                or (finished_at is not None and finished_at < admitted_at)
                or (claimed_at is not None and accepted_at is not None and claimed_at < accepted_at)
                or (
                    claim_expires_at is not None
                    and claimed_at is not None
                    and claim_expires_at <= claimed_at
                )
            ):
                raise _invalid_command_content()
            if status == "rejected":
                try:
                    AuthorizationDecision(
                        allowed=False,
                        code=row["code"],
                        safe_message=row["safe_message"],
                    )
                except (TypeError, ValueError) as exc:
                    raise _invalid_command_content() from exc
                if (
                    request_json is not None
                    or accepted_at is not None
                    or finished_at is None
                    or finished_at != admitted_at
                ):
                    raise _invalid_command_content()
            elif status in {"accepted", "running", "completed", "failed", "cancelled"}:
                if (
                    request_json is None
                    or accepted_at is None
                    or not _is_safe_id(row["handler_key"])
                    or accepted_at != admitted_at
                ):
                    raise _invalid_command_content()
                if status in {"completed", "failed", "cancelled"} and (
                    finished_at is None
                    or claimed_at is None
                    or claim_expires_at is None
                    or finished_at < claimed_at
                    or finished_at >= claim_expires_at
                ):
                    raise _invalid_command_content()
            else:
                raise _invalid_command_content()
            commands[str(command_id)] = row

        events: dict[str, list[sqlite3.Row]] = {}
        for row in connection.execute(
            "SELECT * FROM command_receipt_events ORDER BY event_sequence"
        ):
            command_id = row["command_id"]
            if (
                command_id not in commands
                or not _is_safe_id(row["code"])
                or type(row["safe_message"]) is not str
                or not 1 <= len(row["safe_message"].strip()) <= 512
                or _parse_canonical_utc(row["occurred_at_utc"]) is None
                or (row["worker_id"] is not None and not _is_safe_id(row["worker_id"]))
            ):
                raise _invalid_command_content()
            if (
                row["status"] in {"accepted", "rejected"}
                and (row["worker_id"] is not None or row["result_json"] is not None)
            ) or (
                row["status"] == "running"
                and (row["worker_id"] is None or row["result_json"] is not None)
            ) or (
                row["status"] in {"completed", "failed", "cancelled"}
                and row["worker_id"] is None
            ):
                raise _invalid_command_content()
            if row["status"] in {"accepted", "running"} and (
                row["code"],
                row["safe_message"],
            ) != _COMMAND_STATUS_MESSAGES[row["status"]]:
                raise _invalid_command_content()

            if row["result_json"] is not None:
                result = _decode_canonical_object(row["result_json"])
                if _contains_sensitive_key(result):
                    raise _invalid_command_content()
            else:
                result = None
            try:
                CommandReceipt(
                    command_id=command_id,
                    status=ReceiptStatus(row["status"]),
                    code=row["code"],
                    safe_message=row["safe_message"],
                    accepted_at_utc=None,
                    finished_at_utc=None,
                    result=result,
                )
            except (TypeError, ValueError) as exc:
                raise _invalid_command_content() from exc
            events.setdefault(str(command_id), []).append(row)

        if set(events) != set(commands):
            raise _invalid_command_content()
        terminal = {"rejected", "completed", "failed", "cancelled"}
        for command_id, command_events in events.items():
            statuses = [str(event["status"]) for event in command_events]
            event_times = [
                _parse_canonical_utc(event["occurred_at_utc"])
                for event in command_events
            ]
            previous_event_time: datetime | None = None
            previous_running_time: datetime | None = None
            for event_status, event_time in zip(statuses, event_times, strict=True):
                if event_time is None or (
                    previous_event_time is not None
                    and event_time < previous_event_time
                ):
                    raise _invalid_command_content()
                if event_status == "running":
                    if (
                        previous_running_time is not None
                        and event_time <= previous_running_time
                    ):
                        raise _invalid_command_content()
                    previous_running_time = event_time
                previous_event_time = event_time
            first = statuses[0]
            if first not in {"accepted", "rejected"}:
                raise _invalid_command_content()
            if first == "rejected" and len(statuses) != 1:
                raise _invalid_command_content()
            if first == "accepted":
                seen_running = False
                seen_terminal = False
                for index, status in enumerate(statuses[1:], start=1):
                    if status == "running" and not seen_terminal:
                        seen_running = True
                        continue
                    if status in {"completed", "failed", "cancelled"} and seen_running:
                        if seen_terminal or index != len(statuses) - 1:
                            raise _invalid_command_content()
                        seen_terminal = True
                        continue
                    raise _invalid_command_content()
            current = commands[command_id]
            latest = command_events[-1]
            first_event = command_events[0]
            running_events = [
                event for event in command_events if event["status"] == "running"
            ]
            if (
                first == "accepted"
                and first_event["occurred_at_utc"] != current["accepted_at_utc"]
            ):
                raise _invalid_command_content()
            if running_events:
                latest_running = running_events[-1]
                if (
                    latest_running["occurred_at_utc"] != current["claimed_at_utc"]
                    or latest_running["worker_id"] != current["claim_worker_id"]
                ):
                    raise _invalid_command_content()
            expected_latest_time = {
                "accepted": current["accepted_at_utc"],
                "rejected": current["finished_at_utc"],
                "running": current["claimed_at_utc"],
                "completed": current["finished_at_utc"],
                "failed": current["finished_at_utc"],
                "cancelled": current["finished_at_utc"],
            }[str(current["status"])]
            if (
                latest["status"] != current["status"]
                or latest["code"] != current["code"]
                or latest["safe_message"] != current["safe_message"]
                or latest["result_json"] != current["result_json"]
                or latest["worker_id"] != current["claim_worker_id"]
                or latest["occurred_at_utc"] != expected_latest_time
            ):
                raise _invalid_command_content()

    @staticmethod
    def _validate_legacy_command_terminal_messages(
        connection: sqlite3.Connection,
    ) -> None:
        terminal = {"completed", "failed", "cancelled"}
        for table in ("commands", "command_receipt_events"):
            for row in connection.execute(
                f"SELECT status, code, safe_message FROM {table}"
            ):
                if row["status"] in terminal and (
                    row["code"],
                    row["safe_message"],
                ) != _COMMAND_STATUS_MESSAGES[row["status"]]:
                    raise _invalid_command_content()

    @staticmethod
    def _validate_operator_decision_content(connection: sqlite3.Connection) -> None:
        from .command_contracts import ApprovalPayload, CommandRequest
        from .operator_decisions import OperatorDecision, canonical_decision_json

        for row in connection.execute(
            "SELECT * FROM operator_decisions ORDER BY decision_sequence"
        ):
            try:
                decision = OperatorDecision.model_validate_json(
                    row["content_json"],
                    strict=True,
                )
            except (TypeError, ValueError) as exc:
                raise _invalid_operator_decision_content() from exc
            expected_id = "tui-decision:" + hashlib.sha256(
                decision.command_id.encode("utf-8")
            ).hexdigest()
            if (
                decision.decision_id != expected_id
                or canonical_decision_json(decision) != row["content_json"]
                or row["decision_id"] != decision.decision_id
                or row["command_id"] != decision.command_id
                or row["run_id"] != decision.run_id
                or row["checkpoint_id"] != decision.checkpoint_id
                or row["operator_id"] != decision.operator_id
                or row["reason"] != decision.reason
                or row["decision"] != "hold"
                or row["decided_at_utc"]
                != decision.model_dump(mode="json")["decided_at_utc"]
            ):
                raise _invalid_operator_decision_content()
            command = connection.execute(
                "SELECT * FROM commands WHERE command_id = ?",
                (decision.command_id,),
            ).fetchone()
            if command is None or command["accepted_request_json"] is None:
                raise _invalid_operator_decision_content()
            try:
                request = CommandRequest.model_validate_json(
                    command["accepted_request_json"],
                    strict=True,
                )
            except (TypeError, ValueError) as exc:
                raise _invalid_operator_decision_content() from exc
            if (
                request.command_type != "approval.hold"
                or type(request.payload) is not ApprovalPayload
                or request.payload.run_id != decision.run_id
                or request.payload.checkpoint_id != decision.checkpoint_id
                or request.reason != decision.reason
                or command["operator_id"] != decision.operator_id
                or command["handler_key"] != "approval.hold"
                or command["status"] != "completed"
                or command["code"] != "completed"
                or command["safe_message"] != "Command completed."
                or command["finished_at_utc"] != row["decided_at_utc"]
                or command["result_json"]
                != json.dumps(
                    {"decision_id": decision.decision_id},
                    separators=(",", ":"),
                    sort_keys=True,
                )
            ):
                raise _invalid_operator_decision_content()

        missing = connection.execute(
            """
            SELECT command_id
            FROM commands AS command
            WHERE command.command_type = 'approval.hold'
              AND command.status = 'completed'
              AND (
                  SELECT COUNT(*)
                  FROM operator_decisions AS decision
                  WHERE decision.command_id = command.command_id
              ) != 1
            LIMIT 1
            """
        ).fetchone()
        if missing is not None:
            raise _invalid_operator_decision_content()

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
        TuiLedger._validate_v1_note_content(connection)
        if version >= 2:
            TuiLedger._validate_note_search_parity(connection, check_index=False)
        if version >= 3:
            TuiLedger._validate_command_content(connection)
        if version == 3:
            TuiLedger._validate_legacy_command_terminal_messages(connection)
        if version >= 4:
            TuiLedger._validate_operator_decision_content(connection)
        quick_check = tuple(
            str(row[0]) for row in connection.execute("PRAGMA quick_check")
        )
        if quick_check != ("ok",):
            raise LedgerCorruptionError("TUI ledger failed SQLite integrity checking")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise LedgerCorruptionError("TUI ledger has invalid foreign-key references")
