"""Context-only operator notes stored in the shared TUI ledger."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, TypeAdapter, ValidationError

from vesper.platform.tui.sqlite_ledger import (
    LedgerClosedError,
    LedgerCorruptionError,
    TuiLedger,
)
from vesper.platform.tui.views import SafeId, StrictModel, UtcDateTime


NoteBody = Annotated[str, StringConstraints(min_length=1, max_length=8_000)]
NoteRevision = Annotated[int, Field(ge=1, le=2**63 - 1)]
NoteTargetType = Literal["stock", "order", "approval", "agent-event"]
_SEARCH_TOKEN = re.compile(r"\w+", re.UNICODE)
_SAFE_ID = TypeAdapter(SafeId)


class NoteConflictError(RuntimeError):
    """Raised when a deterministic note ID points at different content."""


class NoteVisibility(StrEnum):
    PRIVATE = "private"
    SHARED = "shared"


class NoteFilters(StrictModel):
    """Exact optional filters applied to full-text note search."""

    target_type: NoteTargetType | None = None
    target_id: SafeId | None = None
    visibility: NoteVisibility | None = None
    author: SafeId | None = None


class NoteTarget(StrictModel):
    target_type: NoteTargetType
    target_id: SafeId


class NoteView(StrictModel):
    note_id: SafeId
    target: NoteTarget
    body: NoteBody
    visibility: NoteVisibility
    author: SafeId
    revision: NoteRevision
    created_at_utc: UtcDateTime
    updated_at_utc: UtcDateTime
    context_only: Literal[True] = True


class _NoteDraft(StrictModel):
    body: NoteBody
    visibility: NoteVisibility
    author: SafeId


def _canonical_note_json(note: NoteView) -> str:
    return json.dumps(
        note.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


def _default_id_factory() -> str:
    return f"note:{secrets.token_hex(16)}"


def _require_plain_int(value: object, *, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


class NoteStore:
    """Store current context notes plus immutable revision-one history."""

    def __init__(
        self,
        ledger: Path | TuiLedger,
        *,
        clock: Callable[[], datetime] = _default_clock,
        id_factory: Callable[[], str] = _default_id_factory,
    ) -> None:
        if isinstance(ledger, TuiLedger):
            self._ledger = ledger
            self._owns_ledger = False
        else:
            self._ledger = TuiLedger(Path(ledger))
            self._owns_ledger = True
        self._clock = clock
        self._id_factory = id_factory
        self._closed = False

    def __enter__(self) -> NoteStore:
        self._require_open()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        if self._owns_ledger:
            self._ledger.close()
        self._closed = True

    def _require_open(self) -> None:
        if self._closed:
            raise LedgerClosedError("note store is closed")

    def add(
        self,
        target: NoteTarget,
        body: str,
        visibility: NoteVisibility,
        author: str,
    ) -> NoteView:
        """Add one context note and its immutable first history revision."""

        self._require_open()
        self._validate_target(target)
        self._validate_draft(body, visibility, author)
        with self._ledger.transaction() as connection:
            return self.add_in_transaction(
                connection,
                target,
                body,
                visibility,
                author,
            )

    def add_in_transaction(
        self,
        connection: sqlite3.Connection,
        target: NoteTarget,
        body: str,
        visibility: NoteVisibility,
        author: str,
        *,
        note_id: str | None = None,
    ) -> NoteView:
        """Add a note inside the caller's active ledger transaction."""

        self._require_open()
        self._validate_target(target)
        draft = self._validate_draft(body, visibility, author)
        self._ledger.require_transaction(connection)
        now = self._clock()
        selected_note_id = self._id_factory() if note_id is None else note_id
        note = NoteView.model_validate(
            {
                "note_id": selected_note_id,
                "target": target,
                "body": draft.body,
                "visibility": draft.visibility,
                "author": draft.author,
                "revision": 1,
                "created_at_utc": now,
                "updated_at_utc": now,
                "context_only": True,
            },
            strict=True,
        )
        existing_row = connection.execute(
            "SELECT * FROM notes WHERE note_id = ?",
            (note.note_id,),
        ).fetchone()
        if existing_row is not None:
            existing = self._decode_row(existing_row)
            if (
                existing.target == note.target
                and existing.body == note.body
                and existing.visibility is note.visibility
                and existing.author == note.author
            ):
                return existing
            raise NoteConflictError(f"note ID {note.note_id} has conflicting content")
        values = note.model_dump(mode="json")
        payload_json = _canonical_note_json(note)
        cursor = connection.execute(
            """
            INSERT INTO notes (
                note_id, target_type, target_id, body, visibility, author,
                revision, created_at_utc, updated_at_utc, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                note.note_id,
                note.target.target_type,
                note.target.target_id,
                note.body,
                note.visibility,
                note.author,
                note.revision,
                values["created_at_utc"],
                values["updated_at_utc"],
                payload_json,
            ),
        )
        note_sequence = cursor.lastrowid
        if note_sequence is None:
            raise LedgerCorruptionError("SQLite did not assign a note sequence")
        connection.execute(
            """
            INSERT INTO note_search (
                rowid, note_id, target_type, target_id, body, visibility, author
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                note_sequence,
                note.note_id,
                note.target.target_type,
                note.target.target_id,
                note.body,
                note.visibility,
                note.author,
            ),
        )
        connection.execute(
            """
            INSERT INTO note_history (
                note_id, revision, changed_at_utc, payload_json
            ) VALUES (?, ?, ?, ?)
            """,
            (
                note.note_id,
                note.revision,
                values["updated_at_utc"],
                payload_json,
            ),
        )
        return note

    def add_for_command_in_transaction(
        self,
        connection: sqlite3.Connection,
        command_id: str,
        target: NoteTarget,
        body: str,
        visibility: NoteVisibility,
        author: str,
    ) -> NoteView:
        """Add or replay the one deterministic note owned by a command."""

        checked_command_id = _SAFE_ID.validate_python(command_id, strict=True)
        digest = hashlib.sha256(checked_command_id.encode("ascii")).hexdigest()
        return self.add_in_transaction(
            connection,
            target,
            body,
            visibility,
            author,
            note_id=f"note:command:{digest}",
        )

    def list(self, target: NoteTarget) -> tuple[NoteView, ...]:
        """List one target's notes, newest database admission first."""

        self._require_open()
        self._validate_target(target)
        with self._ledger.read() as connection:
            rows = connection.execute(
                """
                SELECT * FROM notes
                WHERE target_type = ? AND target_id = ?
                ORDER BY note_sequence DESC
                """,
                (target.target_type, target.target_id),
            ).fetchall()
        return tuple(self._decode_row(row) for row in rows)

    def search(
        self,
        query: str,
        filters: NoteFilters,
        limit: int,
    ) -> tuple[NoteView, ...]:
        """Search current context notes with bounded FTS and exact filters."""

        self._require_open()
        if type(query) is not str:
            raise TypeError("query must be a string")
        if not query.strip():
            raise ValueError("query cannot be empty")
        if len(query) > 256:
            raise ValueError("query cannot exceed 256 characters")
        if type(filters) is not NoteFilters:
            raise TypeError("filters must be NoteFilters")
        page_size = _require_plain_int(limit, name="limit", minimum=1, maximum=100)
        tokens = _SEARCH_TOKEN.findall(query.casefold())
        if not tokens:
            return ()
        match_expression = " AND ".join(f'"{token}"*' for token in tokens)
        clauses = ["note_search MATCH ?"]
        parameters: list[object] = [match_expression]
        for name in ("target_type", "target_id", "visibility", "author"):
            value = getattr(filters, name)
            if value is None:
                continue
            clauses.append(f"n.{name} = ?")
            parameters.append(value.value if isinstance(value, NoteVisibility) else value)
        normalized_query = query.strip()
        parameters.extend(
            (normalized_query, normalized_query, normalized_query, page_size)
        )
        statement = f"""
            SELECT n.*
            FROM note_search
            JOIN notes AS n ON n.note_sequence = note_search.rowid
            WHERE {" AND ".join(clauses)}
            ORDER BY
                CASE
                    WHEN lower(n.note_id) = lower(?) THEN 0
                    WHEN lower(n.note_id) LIKE lower(?) || '%'
                      OR lower(n.target_id) LIKE lower(?) || '%' THEN 1
                    ELSE 2
                END,
                bm25(note_search),
                n.note_sequence DESC
            LIMIT ?
        """
        with self._ledger.read() as connection:
            rows = connection.execute(statement, parameters).fetchall()
        return tuple(self._decode_row(row) for row in rows)

    @staticmethod
    def _validate_target(target: object) -> None:
        if type(target) is not NoteTarget:
            raise TypeError("target must be NoteTarget")

    @staticmethod
    def _validate_draft(
        body: object,
        visibility: object,
        author: object,
    ) -> _NoteDraft:
        if type(visibility) is not NoteVisibility:
            raise TypeError("visibility must be NoteVisibility")
        return _NoteDraft.model_validate(
            {"body": body, "visibility": visibility, "author": author},
            strict=True,
        )

    @staticmethod
    def _decode_row(row: sqlite3.Row) -> NoteView:
        try:
            payload_json = row["payload_json"]
            note = NoteView.model_validate_json(payload_json, strict=True)
            values = note.model_dump(mode="json")
            expected_columns = {
                "note_id": note.note_id,
                "target_type": note.target.target_type,
                "target_id": note.target.target_id,
                "body": note.body,
                "visibility": note.visibility.value,
                "author": note.author,
                "revision": note.revision,
                "created_at_utc": values["created_at_utc"],
                "updated_at_utc": values["updated_at_utc"],
            }
            if payload_json != _canonical_note_json(note):
                raise ValueError("note JSON is not canonical")
            if any(row[name] != value for name, value in expected_columns.items()):
                raise ValueError("note columns disagree with payload")
            return note
        except (IndexError, KeyError, TypeError, ValueError, ValidationError) as exc:
            raise LedgerCorruptionError("stored note is invalid") from exc
