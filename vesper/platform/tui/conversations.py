"""Separate, append-only human and agent conversation storage."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Protocol

from pydantic import Field, StringConstraints, TypeAdapter, ValidationError

from vesper.platform.contracts import AgentRole

from .contracts import ApprovedAgentId, ChatEventPayload
from .views import SafeId, Sha256Hex, StrictModel, UtcDateTime


_APPLICATION_ID = 0x56324348  # V2CH
_SCHEMA_VERSION = 1
_MAX_CHUNK_BYTES = 64 * 1024
_MAX_MESSAGE_BYTES = 4 * 1024 * 1024
_MAX_HISTORY_LIMIT = 100
MAX_CHAT_HISTORY_EVENTS = 128
_SAFE_ID = TypeAdapter(SafeId)
_UTC = TypeAdapter(UtcDateTime)
_MessageText = Annotated[str, StringConstraints(max_length=_MAX_MESSAGE_BYTES)]
_TokenCount = Annotated[int, Field(ge=0, le=2**63 - 1)]
_SCHEMA_SQL = """
BEGIN EXCLUSIVE;
CREATE TABLE conversation_messages (
    message_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL UNIQUE,
    agent_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('human', 'agent')),
    created_at_utc TEXT NOT NULL
);
CREATE INDEX conversation_messages_agent_sequence
    ON conversation_messages(agent_id, message_sequence DESC);
CREATE TABLE conversation_chunks (
    message_id TEXT NOT NULL,
    chunk_sequence INTEGER NOT NULL CHECK (chunk_sequence > 0),
    text TEXT NOT NULL CHECK (length(text) > 0),
    token_count INTEGER CHECK (token_count >= 0),
    text_sha256 TEXT NOT NULL,
    PRIMARY KEY (message_id, chunk_sequence),
    FOREIGN KEY (message_id) REFERENCES conversation_messages(message_id)
        ON DELETE RESTRICT
) WITHOUT ROWID;
CREATE TABLE conversation_terminals (
    message_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('complete', 'interrupted')),
    occurred_at_utc TEXT NOT NULL,
    validation_receipt_id TEXT,
    raw_text_sha256 TEXT,
    CHECK (
        (
            status = 'complete'
            AND validation_receipt_id IS NOT NULL
            AND length(raw_text_sha256) = 64
        )
        OR (
            status = 'interrupted'
            AND validation_receipt_id IS NULL
            AND raw_text_sha256 IS NULL
        )
    ),
    FOREIGN KEY (message_id) REFERENCES conversation_messages(message_id)
        ON DELETE RESTRICT
) WITHOUT ROWID;
CREATE TABLE conversation_summaries (
    summary_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    summary_id TEXT NOT NULL UNIQUE,
    agent_id TEXT NOT NULL,
    objective TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    context_sha256 TEXT NOT NULL
);
CREATE TABLE conversation_summary_messages (
    summary_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    message_position INTEGER NOT NULL CHECK (message_position >= 0),
    PRIMARY KEY (summary_id, message_position),
    UNIQUE (summary_id, message_id),
    FOREIGN KEY (summary_id) REFERENCES conversation_summaries(summary_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (message_id) REFERENCES conversation_messages(message_id)
        ON DELETE RESTRICT
) WITHOUT ROWID;
PRAGMA application_id = 1446134600;
PRAGMA user_version = 1;
COMMIT;
"""


def _normalize_schema_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip().rstrip(";")).casefold()


@lru_cache(maxsize=1)
def _expected_schema_objects() -> tuple[tuple[str, str, str], ...]:
    connection = sqlite3.connect(":memory:", isolation_level=None)
    try:
        connection.executescript(_SCHEMA_SQL)
        return tuple(
            (str(name), str(object_type), _normalize_schema_sql(str(sql)))
            for name, object_type, sql in connection.execute(
                "SELECT name, type, sql FROM sqlite_schema "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        )
    finally:
        connection.close()


class ConversationError(RuntimeError):
    """Base error for the local conversation ledger."""


class ConversationConflict(ConversationError):
    """An immutable ID or chunk sequence was reused with different content."""


class ConversationSequenceError(ConversationError):
    """A streamed chunk did not use the next sequence number."""


class ConversationStateError(ConversationError):
    """A caller tried to mutate a terminal message."""


class ConversationCorruptionError(ConversationError):
    """Stored conversation data or schema failed validation."""


class CompletionValidator(Protocol):
    """Controller-owned validation lookup for one exact raw message."""

    def validate_completion(
        self,
        *,
        validation_receipt_id: SafeId,
        agent_id: SafeId,
        message_id: SafeId,
        raw_text_sha256: Sha256Hex,
    ) -> bool: ...


class MessageView(StrictModel):
    message_id: SafeId
    agent_id: SafeId
    role: Literal["human", "agent"]
    status: Literal["draft", "complete", "interrupted"]
    text: _MessageText
    token_count: _TokenCount | None
    created_at_utc: UtcDateTime
    completed_at_utc: UtcDateTime | None
    interrupted_at_utc: UtcDateTime | None
    validation_receipt_id: SafeId | None
    context_summary_ids: tuple[SafeId, ...]


class ConversationHistoryPage(StrictModel):
    agent_id: ApprovedAgentId
    events: Annotated[tuple[ChatEventPayload, ...], Field(max_length=MAX_CHAT_HISTORY_EVENTS)]
    next_cursor: SafeId | None


class _MessageDraft(StrictModel):
    message_id: SafeId
    agent_id: SafeId
    role: Literal["human", "agent"]
    created_at_utc: UtcDateTime


def _default_id_factory() -> str:
    return f"message:{secrets.token_hex(16)}"


def _utc_text(value: datetime) -> str:
    checked = _UTC.validate_python(value, strict=True)
    return checked.isoformat().replace("+00:00", "Z")


def _utc_value(value: str) -> datetime:
    return _UTC.validate_python(value, strict=True)


def _chat_event(values: dict[str, object]) -> ChatEventPayload:
    try:
        digest = hashlib.sha256(
            json.dumps(
                values,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        return ChatEventPayload.model_validate({"event_id": f"chat:{digest}", **values})
    except (TypeError, ValueError, ValidationError) as exc:
        raise ConversationCorruptionError(
            "stored conversation cannot form a valid wire event"
        ) from exc


def _require_plain_int(
    value: object,
    *,
    name: str,
    minimum: int,
    maximum: int,
) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _require_agent_id(value: object) -> str:
    if type(value) is not str:
        raise TypeError("agent_id must be a string")
    try:
        return AgentRole(value).value
    except ValueError as exc:
        raise ValueError("agent_id must name an approved V20 agent") from exc


def _path_redirects(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(callable(is_junction) and is_junction())


def _prepare_database_path(database: Path) -> Path:
    candidate = database.absolute()
    current = Path(candidate.anchor)
    for part in candidate.parent.parts[1:]:
        current = current / part
        if os.path.lexists(current):
            if _path_redirects(current) or not current.is_dir():
                raise ConversationError("conversation database path must be a safe regular file")
        else:
            current.mkdir()
    if os.path.lexists(candidate) and (_path_redirects(candidate) or not candidate.is_file()):
        raise ConversationError("conversation database path must be a safe regular file")
    return candidate


class ConversationStore:
    """Persist immutable messages, chunks, terminal states, and summary lineage."""

    def __init__(
        self,
        database: Path,
        *,
        id_factory: Callable[[], str] = _default_id_factory,
        validator: CompletionValidator | None = None,
    ) -> None:
        if not isinstance(database, Path):
            raise TypeError("database must be a Path")
        if not callable(id_factory):
            raise TypeError("id_factory must be callable")
        if validator is not None and not callable(getattr(validator, "validate_completion", None)):
            raise TypeError("validator must provide validate_completion")
        database = _prepare_database_path(database)
        self._database = database
        self._id_factory = id_factory
        self._validator = validator
        self._lock = threading.RLock()
        self._closed = False
        self._connection = sqlite3.connect(
            database,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        try:
            self._initialize_or_validate_schema()
        except BaseException:
            self._connection.close()
            self._closed = True
            raise

    def __enter__(self) -> ConversationStore:
        self._require_open()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            if self._connection.in_transaction:
                raise ConversationError(
                    "cannot close conversation store during an active transaction"
                )
            self._connection.close()
            self._closed = True

    def start_message(
        self,
        agent_id: SafeId,
        role: Literal["human", "agent"],
        created_at_utc: datetime,
    ) -> MessageView:
        """Create one immutable message identity in an agent-specific thread."""

        self._require_open()
        checked_agent = _require_agent_id(agent_id)
        draft = _MessageDraft.model_validate(
            {
                "message_id": self._id_factory(),
                "agent_id": checked_agent,
                "role": role,
                "created_at_utc": created_at_utc,
            },
            strict=True,
        )
        created = _utc_text(draft.created_at_utc)
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM conversation_messages WHERE message_id = ?",
                (draft.message_id,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["agent_id"],
                    existing["role"],
                    existing["created_at_utc"],
                ) != (draft.agent_id, draft.role, created):
                    raise ConversationConflict(
                        f"message ID {draft.message_id} has conflicting content"
                    )
                return self._decode_message(connection, existing)
            connection.execute(
                """
                INSERT INTO conversation_messages (
                    message_id, agent_id, role, created_at_utc
                ) VALUES (?, ?, ?, ?)
                """,
                (draft.message_id, draft.agent_id, draft.role, created),
            )
            row = connection.execute(
                "SELECT * FROM conversation_messages WHERE message_id = ?",
                (draft.message_id,),
            ).fetchone()
            if row is None:
                raise ConversationCorruptionError("new conversation message disappeared")
            return self._decode_message(connection, row)

    def append_chunk(
        self,
        message_id: SafeId,
        sequence: int,
        text: str,
        *,
        token_count: int | None = None,
    ) -> MessageView:
        """Append exactly the next raw chunk; identical replay is idempotent."""

        self._require_open()
        checked_id = _SAFE_ID.validate_python(message_id, strict=True)
        checked_sequence = _require_plain_int(
            sequence,
            name="sequence",
            minimum=1,
            maximum=2**63 - 1,
        )
        if type(text) is not str:
            raise TypeError("text must be a string")
        if not text:
            raise ValueError("text cannot be empty")
        chunk_bytes = text.encode("utf-8")
        if len(chunk_bytes) > _MAX_CHUNK_BYTES:
            raise ValueError("chunk exceeds the 64 KiB limit")
        checked_tokens = None
        if token_count is not None:
            checked_tokens = _require_plain_int(
                token_count,
                name="token_count",
                minimum=0,
                maximum=2**63 - 1,
            )
        with self._transaction() as connection:
            message = self._require_message(connection, checked_id)
            existing = connection.execute(
                """
                SELECT text, token_count, text_sha256
                FROM conversation_chunks
                WHERE message_id = ? AND chunk_sequence = ?
                """,
                (checked_id, checked_sequence),
            ).fetchone()
            digest = hashlib.sha256(chunk_bytes).hexdigest()
            if existing is not None:
                if tuple(existing) != (text, checked_tokens, digest):
                    raise ConversationConflict(f"chunk {checked_sequence} has conflicting content")
                return self._decode_message(connection, message)
            terminal = self._terminal_row(connection, checked_id)
            if terminal is not None:
                raise ConversationStateError(
                    f"message {checked_id} is terminal ({terminal['status']})"
                )
            last_sequence = int(
                connection.execute(
                    """
                    SELECT COALESCE(MAX(chunk_sequence), 0)
                    FROM conversation_chunks WHERE message_id = ?
                    """,
                    (checked_id,),
                ).fetchone()[0]
            )
            expected = last_sequence + 1
            if checked_sequence != expected:
                raise ConversationSequenceError(
                    f"next chunk sequence is {expected}, got {checked_sequence}"
                )
            current_bytes = int(
                connection.execute(
                    """
                    SELECT COALESCE(SUM(length(CAST(text AS BLOB))), 0)
                    FROM conversation_chunks WHERE message_id = ?
                    """,
                    (checked_id,),
                ).fetchone()[0]
            )
            if current_bytes + len(chunk_bytes) > _MAX_MESSAGE_BYTES:
                raise ValueError("message exceeds the 4 MiB limit")
            connection.execute(
                """
                INSERT INTO conversation_chunks (
                    message_id, chunk_sequence, text, token_count, text_sha256
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (checked_id, checked_sequence, text, checked_tokens, digest),
            )
            return self._decode_message(connection, message)

    def complete(
        self,
        message_id: SafeId,
        validation_receipt_id: SafeId,
        completed_at_utc: datetime,
    ) -> MessageView:
        return self._set_terminal(
            message_id,
            "complete",
            validation_receipt_id,
            completed_at_utc,
        )

    def interrupt(
        self,
        message_id: SafeId,
        interrupted_at_utc: datetime,
    ) -> MessageView:
        return self._set_terminal(
            message_id,
            "interrupted",
            None,
            interrupted_at_utc,
        )

    def interrupt_drafts(
        self,
        agent_id: SafeId,
        interrupted_at_utc: datetime,
    ) -> tuple[MessageView, ...]:
        """Mark one disconnected agent's open messages interrupted."""

        self._require_open()
        checked_agent = _require_agent_id(agent_id)
        occurred = _utc_text(interrupted_at_utc)
        with self._transaction() as connection:
            rows = connection.execute(
                """
                SELECT message.*
                FROM conversation_messages AS message
                LEFT JOIN conversation_terminals AS terminal
                    ON terminal.message_id = message.message_id
                WHERE message.agent_id = ? AND terminal.message_id IS NULL
                ORDER BY message.message_sequence
                """,
                (checked_agent,),
            ).fetchall()
            for row in rows:
                if _utc_value(occurred) < _utc_value(row["created_at_utc"]):
                    raise ValueError("interrupted_at_utc cannot precede message creation")
                connection.execute(
                    """
                    INSERT INTO conversation_terminals (
                        message_id, status, occurred_at_utc, validation_receipt_id
                    ) VALUES (?, 'interrupted', ?, NULL)
                    """,
                    (row["message_id"], occurred),
                )
            return tuple(self._decode_message(connection, row) for row in rows)

    def history(
        self,
        agent_id: SafeId,
        limit: int,
        cursor: SafeId | None,
    ) -> tuple[MessageView, ...]:
        """Return newest-first messages with an exclusive, agent-bound cursor."""

        self._require_open()
        checked_agent = _require_agent_id(agent_id)
        checked_limit = _require_plain_int(
            limit,
            name="limit",
            minimum=1,
            maximum=_MAX_HISTORY_LIMIT,
        )
        with self._read() as connection:
            before_sequence: int | None = None
            if cursor is not None:
                checked_cursor = _SAFE_ID.validate_python(cursor, strict=True)
                cursor_row = connection.execute(
                    """
                    SELECT message_sequence, agent_id
                    FROM conversation_messages WHERE message_id = ?
                    """,
                    (checked_cursor,),
                ).fetchone()
                if cursor_row is None or cursor_row["agent_id"] != checked_agent:
                    raise ValueError("history cursor does not belong to this agent")
                before_sequence = int(cursor_row["message_sequence"])
            if before_sequence is None:
                rows = connection.execute(
                    """
                    SELECT * FROM conversation_messages
                    WHERE agent_id = ?
                    ORDER BY message_sequence DESC LIMIT ?
                    """,
                    (checked_agent, checked_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM conversation_messages
                    WHERE agent_id = ? AND message_sequence < ?
                    ORDER BY message_sequence DESC LIMIT ?
                    """,
                    (checked_agent, before_sequence, checked_limit),
                ).fetchall()
            return tuple(self._decode_message(connection, row) for row in rows)

    def export_history(
        self,
        agent_id: SafeId,
        limit: int,
        cursor: SafeId | None,
    ) -> ConversationHistoryPage:
        """Export one newest-message page as exact chronological wire events."""

        self._require_open()
        checked_agent = _require_agent_id(agent_id)
        checked_limit = _require_plain_int(
            limit,
            name="limit",
            minimum=1,
            maximum=20,
        )
        with self._read() as connection:
            selected = self.history(checked_agent, checked_limit + 1, cursor)
            messages = selected[:checked_limit]
            events: list[ChatEventPayload] = []
            for selected_message in reversed(messages):
                message = self._require_message(connection, selected_message.message_id)
                decoded = self._decode_message(connection, message)
                chunks = connection.execute(
                    """
                    SELECT chunk_sequence, text, token_count
                    FROM conversation_chunks
                    WHERE message_id = ? ORDER BY chunk_sequence
                    """,
                    (decoded.message_id,),
                ).fetchall()
                for chunk in chunks:
                    events.append(
                        _chat_event(
                            {
                                "agent_id": decoded.agent_id,
                                "message_id": decoded.message_id,
                                "role": decoded.role,
                                "operation": "chunk",
                                "chunk_sequence": chunk["chunk_sequence"],
                                "text": chunk["text"],
                                "token_count": chunk["token_count"],
                                "message_created_at_utc": _utc_text(decoded.created_at_utc),
                                "occurred_at_utc": None,
                                "validation_receipt_id": None,
                                "raw_text_sha256": None,
                            }
                        )
                    )
                if decoded.status != "draft":
                    occurred_at_utc = (
                        decoded.completed_at_utc
                        if decoded.status == "complete"
                        else decoded.interrupted_at_utc
                    )
                    if occurred_at_utc is None:
                        raise ConversationCorruptionError("stored conversation terminal is invalid")
                    events.append(
                        _chat_event(
                            {
                                "agent_id": decoded.agent_id,
                                "message_id": decoded.message_id,
                                "role": decoded.role,
                                "operation": decoded.status,
                                "chunk_sequence": None,
                                "text": None,
                                "token_count": None,
                                "message_created_at_utc": _utc_text(decoded.created_at_utc),
                                "occurred_at_utc": _utc_text(occurred_at_utc),
                                "validation_receipt_id": decoded.validation_receipt_id,
                                "raw_text_sha256": (
                                    hashlib.sha256(decoded.text.encode("utf-8")).hexdigest()
                                    if decoded.status == "complete"
                                    else None
                                ),
                            }
                        )
                    )
                if len(events) > MAX_CHAT_HISTORY_EVENTS:
                    raise ConversationStateError(
                        f"conversation history page exceeds {MAX_CHAT_HISTORY_EVENTS} events"
                    )
            event_ids = {event.event_id for event in events}
            if len(event_ids) != len(events):
                raise ConversationCorruptionError("conversation event IDs are not unique")
            return ConversationHistoryPage.model_validate(
                {
                    "agent_id": checked_agent,
                    "events": tuple(events),
                    "next_cursor": (
                        messages[-1].message_id
                        if len(selected) > checked_limit and messages
                        else None
                    ),
                }
            )

    def record_context_summary(
        self,
        summary_id: SafeId,
        agent_id: SafeId,
        objective: str,
        created_at_utc: datetime,
        raw_message_ids: tuple[SafeId, ...],
        context_sha256: Sha256Hex,
    ) -> None:
        """Record immutable context-to-raw-message lineage without rewriting chat."""

        self._require_open()
        checked_summary = _SAFE_ID.validate_python(summary_id, strict=True)
        checked_agent = _require_agent_id(agent_id)
        if type(objective) is not str or not objective.strip() or len(objective) > 8_000:
            raise ValueError("objective must contain 1 through 8000 characters")
        if type(raw_message_ids) is not tuple:
            raise TypeError("raw_message_ids must be a tuple")
        checked_messages = tuple(
            _SAFE_ID.validate_python(message_id, strict=True) for message_id in raw_message_ids
        )
        if len(set(checked_messages)) != len(checked_messages):
            raise ValueError("raw_message_ids must be unique")
        checked_hash = TypeAdapter(Sha256Hex).validate_python(context_sha256, strict=True)
        created = _utc_text(created_at_utc)
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM conversation_summaries WHERE summary_id = ?",
                (checked_summary,),
            ).fetchone()
            if existing is not None:
                linked = tuple(
                    row[0]
                    for row in connection.execute(
                        """
                        SELECT message_id FROM conversation_summary_messages
                        WHERE summary_id = ? ORDER BY message_position
                        """,
                        (checked_summary,),
                    )
                )
                if (
                    existing["agent_id"],
                    existing["objective"],
                    existing["created_at_utc"],
                    existing["context_sha256"],
                    linked,
                ) != (
                    checked_agent,
                    objective.strip(),
                    created,
                    checked_hash,
                    checked_messages,
                ):
                    raise ConversationConflict(
                        f"summary ID {checked_summary} has conflicting content"
                    )
                return
            for message_id in checked_messages:
                message = self._require_message(connection, message_id)
                if message["agent_id"] != checked_agent:
                    raise ValueError("summary message does not belong to this agent")
            connection.execute(
                """
                INSERT INTO conversation_summaries (
                    summary_id, agent_id, objective, created_at_utc, context_sha256
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    checked_summary,
                    checked_agent,
                    objective.strip(),
                    created,
                    checked_hash,
                ),
            )
            connection.executemany(
                """
                INSERT INTO conversation_summary_messages (
                    summary_id, message_id, message_position
                ) VALUES (?, ?, ?)
                """,
                (
                    (checked_summary, message_id, position)
                    for position, message_id in enumerate(checked_messages)
                ),
            )

    def _set_terminal(
        self,
        message_id: SafeId,
        status: Literal["complete", "interrupted"],
        validation_receipt_id: SafeId | None,
        occurred_at_utc: datetime,
    ) -> MessageView:
        self._require_open()
        checked_id = _SAFE_ID.validate_python(message_id, strict=True)
        checked_receipt = (
            None
            if validation_receipt_id is None
            else _SAFE_ID.validate_python(validation_receipt_id, strict=True)
        )
        if status == "complete" and checked_receipt is None:
            raise ValueError("complete requires a validation receipt ID")
        if status == "interrupted" and checked_receipt is not None:
            raise ValueError("interrupted messages cannot have validation receipts")
        occurred = _utc_text(occurred_at_utc)
        with self._transaction() as connection:
            message = self._require_message(connection, checked_id)
            if _utc_value(occurred) < _utc_value(message["created_at_utc"]):
                raise ValueError("terminal time cannot precede message creation")
            existing = self._terminal_row(connection, checked_id)
            if existing is not None:
                if (
                    existing["status"],
                    existing["occurred_at_utc"],
                    existing["validation_receipt_id"],
                ) == (status, occurred, checked_receipt):
                    return self._decode_message(connection, message)
                raise ConversationStateError(
                    f"message {checked_id} is already {existing['status']}"
                )
            raw_text_sha256: str | None = None
            if status == "complete":
                validator = self._validator
                if validator is None:
                    raise ConversationStateError("authoritative completion validator unavailable")
                raw_text = "".join(
                    row[0]
                    for row in connection.execute(
                        """
                        SELECT text FROM conversation_chunks
                        WHERE message_id = ? ORDER BY chunk_sequence
                        """,
                        (checked_id,),
                    )
                )
                raw_text_sha256 = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
                approved = validator.validate_completion(
                    validation_receipt_id=checked_receipt,
                    agent_id=message["agent_id"],
                    message_id=checked_id,
                    raw_text_sha256=raw_text_sha256,
                )
                if type(approved) is not bool or not approved:
                    raise ConversationStateError("authoritative completion binding rejected")
            connection.execute(
                """
                INSERT INTO conversation_terminals (
                    message_id, status, occurred_at_utc, validation_receipt_id,
                    raw_text_sha256
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    checked_id,
                    status,
                    occurred,
                    checked_receipt,
                    raw_text_sha256,
                ),
            )
            return self._decode_message(connection, message)

    def _decode_message(
        self,
        connection: sqlite3.Connection,
        message: sqlite3.Row,
    ) -> MessageView:
        try:
            chunks = connection.execute(
                """
                SELECT chunk_sequence, text, token_count, text_sha256
                FROM conversation_chunks
                WHERE message_id = ? ORDER BY chunk_sequence
                """,
                (message["message_id"],),
            ).fetchall()
            for expected, chunk in enumerate(chunks, start=1):
                if (
                    chunk["chunk_sequence"] != expected
                    or hashlib.sha256(chunk["text"].encode("utf-8")).hexdigest()
                    != chunk["text_sha256"]
                ):
                    raise ValueError("stored chunk sequence or digest is invalid")
            terminal = self._terminal_row(connection, message["message_id"])
            summaries = tuple(
                row[0]
                for row in connection.execute(
                    """
                    SELECT link.summary_id
                    FROM conversation_summary_messages AS link
                    JOIN conversation_summaries AS summary
                        ON summary.summary_id = link.summary_id
                    WHERE link.message_id = ?
                    ORDER BY summary.summary_sequence
                    """,
                    (message["message_id"],),
                )
            )
            text = "".join(chunk["text"] for chunk in chunks)
            token_count = (
                None
                if any(chunk["token_count"] is None for chunk in chunks)
                else sum(int(chunk["token_count"]) for chunk in chunks)
            )
            if not chunks:
                token_count = 0
            status = "draft" if terminal is None else terminal["status"]
            if terminal is not None:
                expected_terminal_hash = (
                    hashlib.sha256(text.encode("utf-8")).hexdigest()
                    if status == "complete"
                    else None
                )
                if terminal["raw_text_sha256"] != expected_terminal_hash:
                    raise ValueError("terminal raw-text binding is invalid")
            occurred = None if terminal is None else terminal["occurred_at_utc"]
            return MessageView.model_validate(
                {
                    "message_id": message["message_id"],
                    "agent_id": message["agent_id"],
                    "role": message["role"],
                    "status": status,
                    "text": text,
                    "token_count": token_count,
                    "created_at_utc": message["created_at_utc"],
                    "completed_at_utc": occurred if status == "complete" else None,
                    "interrupted_at_utc": (occurred if status == "interrupted" else None),
                    "validation_receipt_id": (
                        None if terminal is None else terminal["validation_receipt_id"]
                    ),
                    "context_summary_ids": summaries,
                },
                strict=True,
            )
        except (IndexError, KeyError, TypeError, ValueError, ValidationError) as exc:
            raise ConversationCorruptionError("stored conversation is invalid") from exc

    @staticmethod
    def _terminal_row(
        connection: sqlite3.Connection,
        message_id: str,
    ) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT * FROM conversation_terminals WHERE message_id = ?",
            (message_id,),
        ).fetchone()

    @staticmethod
    def _require_message(
        connection: sqlite3.Connection,
        message_id: str,
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM conversation_messages WHERE message_id = ?",
            (message_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown conversation message: {message_id}")
        return row

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._require_open()
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
            else:
                self._connection.execute("COMMIT")

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._require_open()
            yield self._connection

    def _require_open(self) -> None:
        if self._closed:
            raise ConversationError("conversation store is closed")

    def _initialize_or_validate_schema(self) -> None:
        application_id = int(self._connection.execute("PRAGMA application_id").fetchone()[0])
        version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
        objects = int(
            self._connection.execute(
                "SELECT COUNT(*) FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'"
            ).fetchone()[0]
        )
        if application_id == 0 and version == 0 and objects == 0:
            self._connection.executescript(_SCHEMA_SQL)
        self._validate_schema()

    def _validate_schema(self) -> None:
        if int(self._connection.execute("PRAGMA application_id").fetchone()[0]) != _APPLICATION_ID:
            raise ConversationCorruptionError("unrecognized conversation database")
        if int(self._connection.execute("PRAGMA user_version").fetchone()[0]) != _SCHEMA_VERSION:
            raise ConversationCorruptionError("unsupported conversation schema version")
        actual_objects = tuple(
            (str(name), str(object_type), _normalize_schema_sql(str(sql)))
            for name, object_type, sql in self._connection.execute(
                "SELECT name, type, sql FROM sqlite_schema "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        )
        if actual_objects != _expected_schema_objects():
            raise ConversationCorruptionError("conversation schema definition is invalid")
        expected_columns = {
            "conversation_messages": (
                "message_sequence",
                "message_id",
                "agent_id",
                "role",
                "created_at_utc",
            ),
            "conversation_chunks": (
                "message_id",
                "chunk_sequence",
                "text",
                "token_count",
                "text_sha256",
            ),
            "conversation_terminals": (
                "message_id",
                "status",
                "occurred_at_utc",
                "validation_receipt_id",
                "raw_text_sha256",
            ),
            "conversation_summaries": (
                "summary_sequence",
                "summary_id",
                "agent_id",
                "objective",
                "created_at_utc",
                "context_sha256",
            ),
            "conversation_summary_messages": (
                "summary_id",
                "message_id",
                "message_position",
            ),
        }
        for table, expected in expected_columns.items():
            actual = tuple(
                str(row[1]) for row in self._connection.execute(f"PRAGMA table_info({table})")
            )
            if actual != expected:
                raise ConversationCorruptionError("conversation schema is incomplete")
        if tuple(self._connection.execute("PRAGMA quick_check").fetchone()) != ("ok",):
            raise ConversationCorruptionError("conversation database failed integrity check")
        if self._connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ConversationCorruptionError("conversation database has invalid references")
