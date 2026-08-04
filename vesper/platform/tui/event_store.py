"""Durable, append-only timeline events for the local operations console."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from vesper.platform.tui.sqlite_ledger import (
    LedgerClosedError,
    LedgerCorruptionError,
    TuiLedger,
)
from vesper.platform.tui.views import SafeId, StrictModel, TimelineRow, WireUInt


_MAX_SQLITE_INTEGER = 2**63 - 1
_SEARCH_TOKEN = re.compile(r"\w+", re.UNICODE)


class EventConflictError(RuntimeError):
    """The same event ID was reused for different content."""


class EventInput(TimelineRow):
    """Complete timeline event admitted to durable storage."""

    source: SafeId


class StoredEvent(EventInput):
    """Timeline event plus its database admission sequence."""

    sequence: WireUInt


class EventWindow(StrictModel):
    """Newest bounded admission window plus exact omitted-event counts."""

    events: tuple[StoredEvent, ...]
    hidden_event_count: WireUInt
    hidden_impact_event_count: WireUInt
    last_sequence: WireUInt


class EventFilters(StrictModel):
    """Exact, optional filters applied to full-text event search."""

    source: SafeId | None = None
    severity: Literal["info", "active", "waiting", "urgent", "resolved"] | None = None
    impact: bool | None = None
    agent_id: SafeId | None = None
    symbol: SafeId | None = None
    model_id: SafeId | None = None
    approval_id: SafeId | None = None
    order_id: SafeId | None = None


def _canonical_event_json(event: EventInput) -> str:
    return json.dumps(
        event.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _require_plain_int(value: object, *, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


class EventStore:
    """Read and append timeline events through a shared SQLite ledger."""

    def __init__(self, ledger: Path | TuiLedger) -> None:
        if isinstance(ledger, TuiLedger):
            self._ledger = ledger
            self._owns_ledger = False
        else:
            self._ledger = TuiLedger(Path(ledger))
            self._owns_ledger = True
        self._closed = False

    def __enter__(self) -> EventStore:
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
            raise LedgerClosedError("event store is closed")

    def append(self, event: EventInput) -> StoredEvent:
        """Append one event, or replay an identical event ID without duplication."""

        self._require_open()
        self._require_event(event)
        with self._ledger.transaction() as connection:
            return self._append_in_transaction(connection, event)

    def _append_in_transaction(
        self,
        connection: sqlite3.Connection,
        event: EventInput,
    ) -> StoredEvent:
        """Append inside the caller's active ledger transaction."""

        self._require_open()
        self._require_event(event)
        self._ledger.require_transaction(connection)
        payload_json = _canonical_event_json(event)
        existing = connection.execute(
            "SELECT * FROM events WHERE event_id = ?",
            (event.event_id,),
        ).fetchone()
        if existing is not None:
            if existing["payload_json"] != payload_json:
                raise EventConflictError(
                    f"event ID {event.event_id!r} already has different content"
                )
            return self._decode_row(existing)

        values = event.model_dump(mode="json")
        cursor = connection.execute(
            """
            INSERT INTO events (
                event_id, occurred_at_utc, impact, severity, summary, agent_id,
                symbol, model_id, approval_id, order_id, source, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                values["occurred_at_utc"],
                int(event.impact),
                event.severity,
                event.summary,
                event.agent_id,
                event.symbol,
                event.model_id,
                event.approval_id,
                event.order_id,
                event.source,
                payload_json,
            ),
        )
        sequence = cursor.lastrowid
        if sequence is None:
            raise LedgerCorruptionError("SQLite did not assign an event sequence")
        connection.execute(
            """
            INSERT INTO event_search (
                rowid, event_id, source, summary, agent_id, symbol, model_id,
                approval_id, order_id, evidence_ids
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sequence,
                event.event_id,
                event.source,
                event.summary,
                event.agent_id or "",
                event.symbol or "",
                event.model_id or "",
                event.approval_id or "",
                event.order_id or "",
                " ".join(event.evidence_ids),
            ),
        )
        return StoredEvent.model_validate(
            {**event.model_dump(mode="python"), "sequence": sequence},
            strict=True,
        )

    def since(self, sequence: int, limit: int) -> tuple[StoredEvent, ...]:
        """Return events after a database sequence, oldest admitted first."""

        self._require_open()
        cursor = _require_plain_int(
            sequence,
            name="sequence",
            minimum=0,
            maximum=_MAX_SQLITE_INTEGER,
        )
        page_size = _require_plain_int(limit, name="limit", minimum=1, maximum=10_000)
        with self._ledger.read() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE sequence > ? ORDER BY sequence ASC LIMIT ?",
                (cursor, page_size),
            ).fetchall()
        return tuple(self._decode_row(row) for row in rows)

    def latest(self, limit: int) -> EventWindow:
        """Return the newest admission window in ascending sequence order."""

        self._require_open()
        page_size = _require_plain_int(limit, name="limit", minimum=1, maximum=10_000)
        with self._ledger.read() as connection:
            rows = connection.execute(
                """
                WITH ranked AS (
                    SELECT
                        events.*,
                        COUNT(*) OVER () AS window_total_count,
                        COALESCE(SUM(impact) OVER (), 0) AS window_impact_count,
                        COALESCE(MAX(sequence) OVER (), 0) AS window_last_sequence,
                        ROW_NUMBER() OVER (ORDER BY sequence DESC) AS newest_rank
                    FROM events
                )
                SELECT *
                FROM ranked
                WHERE newest_rank <= ?
                ORDER BY sequence ASC
                """,
                (page_size,),
            ).fetchall()
        if not rows:
            return EventWindow(
                events=(),
                hidden_event_count=0,
                hidden_impact_event_count=0,
                last_sequence=0,
            )
        events = tuple(self._decode_row(row) for row in rows)
        total_count = rows[0]["window_total_count"]
        impact_count = rows[0]["window_impact_count"]
        last_sequence = rows[0]["window_last_sequence"]
        if any(
            type(value) is not int or value < 0
            for value in (total_count, impact_count, last_sequence)
        ):
            raise LedgerCorruptionError("stored event window metadata is invalid")
        visible_impact_count = sum(int(event.impact) for event in events)
        return EventWindow(
            events=events,
            hidden_event_count=total_count - len(events),
            hidden_impact_event_count=impact_count - visible_impact_count,
            last_sequence=last_sequence,
        )

    def search(
        self,
        query: str,
        filters: EventFilters,
        limit: int,
    ) -> tuple[StoredEvent, ...]:
        """Search timeline text as plain tokens with exact structured filters."""

        self._require_open()
        if type(query) is not str:
            raise TypeError("query must be a string")
        if not query.strip():
            raise ValueError("query cannot be empty")
        if len(query) > 256:
            raise ValueError("query cannot exceed 256 characters")
        if type(filters) is not EventFilters:
            raise TypeError("filters must be EventFilters")
        page_size = _require_plain_int(limit, name="limit", minimum=1, maximum=100)
        tokens = _SEARCH_TOKEN.findall(query.casefold())
        if not tokens:
            return ()
        match_expression = " AND ".join(f'"{token}"' for token in tokens)
        clauses = ["event_search MATCH ?"]
        parameters: list[object] = [match_expression]
        for name in (
            "source",
            "severity",
            "impact",
            "agent_id",
            "symbol",
            "model_id",
            "approval_id",
            "order_id",
        ):
            value = getattr(filters, name)
            if value is None:
                continue
            clauses.append(f"e.{name} = ?")
            parameters.append(int(value) if name == "impact" else value)
        parameters.append(page_size)
        statement = f"""
            SELECT e.*
            FROM event_search
            JOIN events AS e ON e.sequence = event_search.rowid
            WHERE {" AND ".join(clauses)}
            ORDER BY bm25(event_search), e.sequence DESC
            LIMIT ?
        """
        with self._ledger.read() as connection:
            rows = connection.execute(statement, parameters).fetchall()
        return tuple(self._decode_row(row) for row in rows)

    @staticmethod
    def _require_event(event: object) -> None:
        if type(event) is not EventInput:
            raise TypeError("event must be EventInput")

    @staticmethod
    def _decode_row(row: sqlite3.Row) -> StoredEvent:
        try:
            payload_json = row["payload_json"]
            event = EventInput.model_validate_json(payload_json, strict=True)
            values = event.model_dump(mode="json")
            expected_columns = {
                "event_id": event.event_id,
                "occurred_at_utc": values["occurred_at_utc"],
                "impact": int(event.impact),
                "severity": event.severity,
                "summary": event.summary,
                "agent_id": event.agent_id,
                "symbol": event.symbol,
                "model_id": event.model_id,
                "approval_id": event.approval_id,
                "order_id": event.order_id,
                "source": event.source,
            }
            if payload_json != _canonical_event_json(event):
                raise ValueError("event JSON is not canonical")
            if any(row[name] != value for name, value in expected_columns.items()):
                raise ValueError("event columns disagree with payload")
            sequence = row["sequence"]
            if type(sequence) is not int or not 0 <= sequence <= _MAX_SQLITE_INTEGER:
                raise ValueError("invalid event sequence")
            return StoredEvent.model_validate(
                {**event.model_dump(mode="python"), "sequence": sequence},
                strict=True,
            )
        except (IndexError, KeyError, TypeError, ValueError, ValidationError) as exc:
            raise LedgerCorruptionError("stored event is invalid") from exc
