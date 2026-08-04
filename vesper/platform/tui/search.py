"""Bounded full-text search over a controller-owned console snapshot."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum
from threading import RLock
from typing import Annotated, Literal

from pydantic import Field, ValidationError

from vesper.platform.tui.event_store import EventFilters, EventStore, StoredEvent
from vesper.platform.tui.notes import NoteFilters, NoteStore, NoteTargetType, NoteView
from vesper.platform.tui.views import (
    AgentCard,
    ApprovalRow,
    CandidateRow,
    ConsoleSnapshot,
    EvidenceRow,
    MemoryRow,
    ModelOpinionRow,
    NonEmptyStr,
    OrderRow,
    PortfolioRow,
    RepositoryRow,
    SafeId,
    SourceRow,
    StrictModel,
    TimelineRow,
    UtcDateTime,
    WireUInt,
)


class SearchKind(StrEnum):
    STOCK = "stock"
    AGENT = "agent"
    MODEL = "model"
    ORDER = "order"
    APPROVAL = "approval"
    EVENT = "event"
    EVIDENCE = "evidence"
    MEMORY = "memory"
    SOURCE = "source"
    NOTE = "note"


class SearchRecordType(StrEnum):
    PORTFOLIO_ROW = "portfolio-row"
    AGENT_CARD = "agent-card"
    MODEL_OPINION_ROW = "model-opinion-row"
    CANDIDATE_ROW = "candidate-row"
    ORDER_ROW = "order-row"
    APPROVAL_ROW = "approval-row"
    TIMELINE_ROW = "timeline-row"
    EVIDENCE_ROW = "evidence-row"
    MEMORY_ROW = "memory-row"
    SOURCE_ROW = "source-row"
    REPOSITORY_ROW = "repository-row"
    NOTE = "note"


class SearchScreen(StrEnum):
    PORTFOLIO = "portfolio"
    AGENTS = "agents"
    MODELS = "models-regime"
    ORDERS = "orders"
    RISK = "risk-approvals"
    TIMELINE = "timeline"
    DATA = "data-evidence"
    MEMORY = "memory"
    SYSTEM = "system"


class SearchFilters(StrictModel):
    kinds: Annotated[tuple[SearchKind, ...], Field(max_length=len(SearchKind))] = ()
    screens: Annotated[tuple[SearchScreen, ...], Field(max_length=len(SearchScreen))] = ()
    source: NonEmptyStr | None = None


class SearchResult(StrictModel):
    kind: SearchKind
    record_type: SearchRecordType
    record_id: SafeId
    label: NonEmptyStr
    summary: NonEmptyStr
    occurred_at_utc: UtcDateTime | None
    source: NonEmptyStr
    screen: SearchScreen
    context_only: Literal[True] | None = None


class SearchPage(StrictModel):
    """One bounded search result set tied to an exact snapshot version."""

    indexed_state_version: WireUInt
    results: Annotated[tuple[SearchResult, ...], Field(max_length=100)]
    error: NonEmptyStr | None = None


class _IndexRecord(StrictModel):
    kind: SearchKind
    record_type: SearchRecordType
    record_id: SafeId
    label: NonEmptyStr
    summary: NonEmptyStr
    occurred_at_utc: UtcDateTime | None
    source: NonEmptyStr
    screen: SearchScreen
    terms: str


class SearchService:
    """Own a disposable FTS5 index rebuilt from one immutable snapshot."""

    def __init__(self, snapshot: ConsoleSnapshot) -> None:
        self._connection = sqlite3.connect(":memory:", check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = RLock()
        self._connection.execute(
            """
            CREATE VIRTUAL TABLE search_index USING fts5(
                kind UNINDEXED,
                record_type UNINDEXED,
                record_id,
                label,
                summary,
                occurred_at_utc UNINDEXED,
                source UNINDEXED,
                screen UNINDEXED,
                terms,
                tokenize = 'unicode61'
            )
            """
        )
        self.rebuild(snapshot)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def rebuild(self, snapshot: ConsoleSnapshot) -> None:
        if type(snapshot) is not ConsoleSnapshot:
            raise TypeError("snapshot must be ConsoleSnapshot")
        records = tuple(self._snapshot_records(snapshot))
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM search_index")
            self._connection.executemany(
                """
                INSERT INTO search_index(
                    kind, record_type, record_id, label, summary, occurred_at_utc,
                    source, screen, terms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        record.kind.value,
                        record.record_type.value,
                        record.record_id,
                        record.label,
                        record.summary,
                        _serialize_time(record.occurred_at_utc),
                        record.source,
                        record.screen.value,
                        record.terms,
                    )
                    for record in records
                ),
            )

    def search(
        self,
        query: str,
        filters: SearchFilters,
        limit: int = 100,
    ) -> tuple[SearchResult, ...]:
        _validate_search_request(query, filters, limit)

        tokens = _search_tokens(query)
        if not tokens:
            return ()
        match_expression = " AND ".join(f'"{token}"*' for token in tokens)
        clauses = ["search_index MATCH ?"]
        parameters: list[object] = [match_expression]
        if filters.kinds:
            placeholders = ", ".join("?" for _ in filters.kinds)
            clauses.append(f"kind IN ({placeholders})")
            parameters.extend(kind.value for kind in filters.kinds)
        if filters.screens:
            placeholders = ", ".join("?" for _ in filters.screens)
            clauses.append(f"screen IN ({placeholders})")
            parameters.extend(screen.value for screen in filters.screens)
        if filters.source is not None:
            clauses.append("lower(source) = ?")
            parameters.append(filters.source.casefold())
        parameters.extend((query, query, query, query, limit))

        with self._lock:
            rows = self._connection.execute(
                f"""
                SELECT kind, record_type, record_id, label, summary, occurred_at_utc,
                       source, screen
                FROM search_index
                WHERE {" AND ".join(clauses)}
                ORDER BY
                    CASE
                        WHEN kind = 'stock' AND upper(record_id) = upper(?) THEN 0
                        WHEN lower(record_id) = lower(?) THEN 1
                        WHEN lower(record_id) LIKE lower(?) || '%'
                          OR lower(label) LIKE lower(?) || '%' THEN 2
                        ELSE 3
                    END,
                    bm25(search_index),
                    lower(label),
                    lower(record_id)
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return tuple(
            SearchResult(
                kind=SearchKind(row["kind"]),
                record_type=SearchRecordType(row["record_type"]),
                record_id=row["record_id"],
                label=row["label"],
                summary=row["summary"],
                occurred_at_utc=row["occurred_at_utc"],
                source=row["source"],
                screen=SearchScreen(row["screen"]),
            )
            for row in rows
        )

    @staticmethod
    def _snapshot_records(snapshot: ConsoleSnapshot) -> Iterable[_IndexRecord]:
        seen: set[tuple[SearchRecordType, str]] = set()

        def unique(records: Iterable[_IndexRecord]) -> Iterable[_IndexRecord]:
            for record in records:
                key = (record.record_type, record.record_id.casefold())
                if key not in seen:
                    seen.add(key)
                    yield record

        yield from unique(
            _stock_record(row, snapshot.portfolio.source, snapshot.portfolio.as_of_utc)
            for row in (*snapshot.portfolio.rows, *snapshot.impact.holdings)
        )
        yield from unique(
            _agent_record(row, snapshot.agents.source, snapshot.agents.as_of_utc)
            for row in (
                *snapshot.agents.rows,
                *snapshot.impact.agents,
                *snapshot.orders.reconciliation_agents,
            )
        )
        yield from unique(
            _model_opinion_record(row, snapshot.models.source) for row in snapshot.models.opinions
        )
        yield from unique(
            _candidate_record(row, snapshot.models.source) for row in snapshot.models.candidates
        )
        yield from unique(
            _order_record(row, snapshot.orders.source, snapshot.orders.as_of_utc)
            for row in snapshot.orders.rows
        )
        yield from unique(
            _approval_record(row, snapshot.risk.source) for row in snapshot.risk.approvals
        )
        yield from unique(
            _event_record(row, snapshot.timeline.source)
            for row in (
                *snapshot.timeline.rows,
                *snapshot.portfolio.history,
                *snapshot.orders.history,
                *snapshot.agents.history,
                *snapshot.memory.history,
                *snapshot.impact.events,
            )
        )
        yield from unique(
            _evidence_record(row) for row in (*snapshot.data.evidence, *snapshot.models.evidence)
        )
        yield from unique(
            _memory_record(row, snapshot.memory.source) for row in snapshot.memory.rows
        )
        yield from unique(
            _source_record(row, snapshot.data.source) for row in snapshot.data.sources
        )
        yield from unique(_repository_record(row) for row in snapshot.system.repositories)


class GlobalSearchService:
    """Merge current projection truth with complete event and note history."""

    def __init__(
        self,
        snapshot: ConsoleSnapshot,
        event_store: EventStore | None,
        note_store: NoteStore | None,
        *,
        persistent_error: str | None = None,
    ) -> None:
        if type(snapshot) is not ConsoleSnapshot:
            raise TypeError("snapshot must be ConsoleSnapshot")
        self._current = SearchService(snapshot)
        self._event_store = event_store
        self._note_store = note_store
        self._persistent_error = persistent_error
        self._indexed_state_version = snapshot.shell.state_version
        self._index_error: str | None = None
        self._closed = False
        self._lock = RLock()

    @property
    def indexed_state_version(self) -> int:
        with self._lock:
            return self._indexed_state_version

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._current.close()
            self._closed = True

    def update_snapshot(self, snapshot: ConsoleSnapshot) -> None:
        """Replace only the disposable current-state index."""

        if type(snapshot) is not ConsoleSnapshot:
            raise TypeError("snapshot must be ConsoleSnapshot")
        with self._lock:
            self._require_open()
            try:
                self._current.rebuild(snapshot)
            except (OSError, RuntimeError, sqlite3.DatabaseError):
                self._index_error = "Current search index is unavailable."
                return
            self._indexed_state_version = snapshot.shell.state_version
            self._index_error = None

    def search(
        self,
        query: str,
        filters: SearchFilters,
        limit: int = 100,
    ) -> SearchPage:
        _validate_search_request(query, filters, limit)
        with self._lock:
            self._require_open()
            providers: list[tuple[SearchResult, ...]] = []
            errors: list[str] = (
                [self._persistent_error] if self._persistent_error is not None else []
            )
            if self._index_error is not None:
                errors.append(self._index_error)
                providers.append(())
            else:
                try:
                    providers.append(self._current.search(query, filters, 100))
                except (OSError, RuntimeError, sqlite3.DatabaseError):
                    errors.append("Current search index is unavailable.")
                    providers.append(())

            if self._allows(filters, SearchKind.EVENT, SearchScreen.TIMELINE):
                providers.append(self._event_results(errors, query, filters))
            else:
                providers.append(())
            if self._allows_note(filters):
                providers.append(self._note_results(errors, query, filters))
            else:
                providers.append(())

            unique_providers = _deduplicate_providers(tuple(providers))
            error = next(iter(dict.fromkeys(errors)), None)
            return SearchPage(
                indexed_state_version=self._indexed_state_version,
                results=_interleave_ranked(query, unique_providers, limit),
                error=error,
            )

    def _event_results(
        self,
        errors: list[str],
        query: str,
        filters: SearchFilters,
    ) -> tuple[SearchResult, ...]:
        if self._event_store is None:
            return ()
        try:
            event_filters = EventFilters(source=filters.source)
        except ValidationError:
            return ()
        try:
            events = self._event_store.search(
                query,
                event_filters,
                100,
            )
        except (OSError, RuntimeError, sqlite3.DatabaseError):
            errors.append("Persisted search history is unavailable.")
            return ()
        return tuple(_stored_event_result(event) for event in events)

    def _note_results(
        self,
        errors: list[str],
        query: str,
        filters: SearchFilters,
    ) -> tuple[SearchResult, ...]:
        if self._note_store is None:
            return ()
        target_types = _note_target_types(filters.screens)
        try:
            notes: list[NoteView] = []
            if target_types is None:
                try:
                    note_filters = NoteFilters(author=filters.source)
                except ValidationError:
                    return ()
                notes.extend(
                    self._note_store.search(
                        query,
                        note_filters,
                        100,
                    )
                )
            else:
                for target_type in target_types:
                    try:
                        note_filters = NoteFilters(
                            target_type=target_type,
                            author=filters.source,
                        )
                    except ValidationError:
                        return ()
                    notes.extend(
                        self._note_store.search(
                            query,
                            note_filters,
                            100,
                        )
                    )
        except (OSError, RuntimeError, sqlite3.DatabaseError):
            errors.append("Persisted search history is unavailable.")
            return ()
        return tuple(_note_result(note) for note in notes)

    @staticmethod
    def _allows(
        filters: SearchFilters,
        kind: SearchKind,
        screen: SearchScreen,
    ) -> bool:
        return (not filters.kinds or kind in filters.kinds) and (
            not filters.screens or screen in filters.screens
        )

    @staticmethod
    def _allows_note(filters: SearchFilters) -> bool:
        if filters.kinds and SearchKind.NOTE not in filters.kinds:
            return False
        note_screens = {
            SearchScreen.PORTFOLIO,
            SearchScreen.ORDERS,
            SearchScreen.RISK,
            SearchScreen.TIMELINE,
        }
        return not filters.screens or bool(note_screens.intersection(filters.screens))

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("global search service is closed")


def _validate_search_request(query: object, filters: object, limit: object) -> None:
    if type(query) is not str:
        raise TypeError("query must be a string")
    if not query.strip():
        raise ValueError("query cannot be empty")
    if len(query) > 256:
        raise ValueError("query cannot exceed 256 characters")
    if type(filters) is not SearchFilters:
        raise TypeError("filters must be SearchFilters")
    if type(limit) is not int:
        raise TypeError("limit must be an integer")
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")


def _stored_event_result(event: StoredEvent) -> SearchResult:
    return SearchResult(
        kind=SearchKind.EVENT,
        record_type=SearchRecordType.TIMELINE_ROW,
        record_id=event.event_id,
        label=event.summary,
        summary=f"{event.severity} event",
        occurred_at_utc=event.occurred_at_utc,
        source=event.source,
        screen=SearchScreen.TIMELINE,
    )


_NOTE_SCREENS: dict[NoteTargetType, SearchScreen] = {
    "stock": SearchScreen.PORTFOLIO,
    "order": SearchScreen.ORDERS,
    "approval": SearchScreen.RISK,
    "agent-event": SearchScreen.TIMELINE,
}


def _note_result(note: NoteView) -> SearchResult:
    summary = note.body.strip() or "NOTE BODY IS BLANK"
    return SearchResult(
        kind=SearchKind.NOTE,
        record_type=SearchRecordType.NOTE,
        record_id=note.note_id,
        label=f"{note.target.target_id} note",
        summary=summary[:512],
        occurred_at_utc=note.updated_at_utc,
        source=note.author,
        screen=_NOTE_SCREENS[note.target.target_type],
        context_only=True,
    )


def _note_target_types(
    screens: tuple[SearchScreen, ...],
) -> tuple[NoteTargetType, ...] | None:
    if not screens:
        return None
    return tuple(
        target_type
        for target_type, screen in _NOTE_SCREENS.items()
        if screen in screens
    )


def _global_rank(query: str, result: SearchResult) -> int:
    normalized = query.strip().casefold()
    record_id = result.record_id.casefold()
    label = result.label.casefold()
    if result.kind is SearchKind.STOCK and record_id == normalized:
        return 0
    elif record_id == normalized:
        return 1
    elif record_id.startswith(normalized) or label.startswith(normalized):
        return 2
    return 3


def _deduplicate_providers(
    providers: tuple[tuple[SearchResult, ...], ...],
) -> tuple[tuple[SearchResult, ...], ...]:
    seen: set[tuple[SearchRecordType, str]] = set()
    unique: list[tuple[SearchResult, ...]] = []
    for provider in providers:
        rows: list[SearchResult] = []
        for result in provider:
            key = (result.record_type, result.record_id.casefold())
            if key in seen:
                continue
            seen.add(key)
            rows.append(result)
        unique.append(tuple(rows))
    return tuple(unique)


def _interleave_ranked(
    query: str,
    providers: tuple[tuple[SearchResult, ...], ...],
    limit: int,
) -> tuple[SearchResult, ...]:
    results: list[SearchResult] = []
    for tier in range(4):
        ranked = tuple(
            tuple(result for result in provider if _global_rank(query, result) == tier)
            for provider in providers
        )
        positions = [0] * len(ranked)
        while len(results) < limit:
            admitted = False
            for provider_index, provider in enumerate(ranked):
                position = positions[provider_index]
                if position >= len(provider):
                    continue
                results.append(provider[position])
                positions[provider_index] += 1
                admitted = True
                if len(results) == limit:
                    break
            if not admitted:
                break
        if len(results) == limit:
            break
    return tuple(results)


def _search_tokens(value: str) -> tuple[str, ...]:
    tokens: list[str] = []
    current: list[str] = []
    for character in value.casefold():
        if character.isalnum() or character == "_":
            current.append(character)
        elif current:
            tokens.append("".join(current))
            current.clear()
    if current:
        tokens.append("".join(current))
    return tuple(tokens)


def _record(
    *,
    kind: SearchKind,
    record_type: SearchRecordType,
    record_id: str,
    label: str,
    summary: str,
    occurred_at_utc: datetime | None,
    source: str,
    screen: SearchScreen,
    terms: Iterable[object],
) -> _IndexRecord:
    searchable = " ".join(str(value) for value in terms if value is not None)
    return _IndexRecord(
        kind=kind,
        record_type=record_type,
        record_id=record_id,
        label=label,
        summary=summary,
        occurred_at_utc=occurred_at_utc,
        source=source,
        screen=screen,
        terms=searchable,
    )


def _stock_record(row: PortfolioRow, source: str, as_of: datetime | None) -> _IndexRecord:
    return _record(
        kind=SearchKind.STOCK,
        record_type=SearchRecordType.PORTFOLIO_ROW,
        record_id=row.symbol,
        label=row.symbol,
        summary=row.description or f"{row.asset_type} holding",
        occurred_at_utc=as_of,
        source=source,
        screen=SearchScreen.PORTFOLIO,
        terms=(
            row.symbol,
            row.description,
            row.asset_type,
            row.quantity,
            row.current_weight,
            row.proposed_weight,
            row.approved_weight,
            row.change_state,
            row.reconciliation,
        ),
    )


def _agent_record(row: AgentCard, source: str, as_of: datetime | None) -> _IndexRecord:
    return _record(
        kind=SearchKind.AGENT,
        record_type=SearchRecordType.AGENT_CARD,
        record_id=row.work_id,
        label=row.agent,
        summary=row.title,
        occurred_at_utc=as_of,
        source=source,
        screen=SearchScreen.AGENTS,
        terms=(
            row.work_id,
            row.agent,
            row.title,
            row.stage,
            row.model,
            *row.affected_areas,
        ),
    )


def _model_opinion_record(row: ModelOpinionRow, source: str) -> _IndexRecord:
    return _record(
        kind=SearchKind.MODEL,
        record_type=SearchRecordType.MODEL_OPINION_ROW,
        record_id=row.model_id,
        label=row.model_id,
        summary=f"{row.regime} at {row.confidence:.0%} confidence",
        occurred_at_utc=row.as_of_utc,
        source=source,
        screen=SearchScreen.MODELS,
        terms=(row.model_id, row.regime, row.confidence),
    )


def _candidate_record(row: CandidateRow, source: str) -> _IndexRecord:
    return _record(
        kind=SearchKind.MODEL,
        record_type=SearchRecordType.CANDIDATE_ROW,
        record_id=row.candidate_id,
        label=row.candidate_id,
        summary=f"{row.family} {row.strategy} {row.status}",
        occurred_at_utc=row.created_at_utc,
        source=source,
        screen=SearchScreen.MODELS,
        terms=(
            row.candidate_id,
            row.family,
            row.strategy,
            row.status,
            *row.evidence_ids,
        ),
    )


def _order_record(row: OrderRow, source: str, as_of: datetime | None) -> _IndexRecord:
    return _record(
        kind=SearchKind.ORDER,
        record_type=SearchRecordType.ORDER_ROW,
        record_id=row.order_id,
        label=row.order_id,
        summary=f"{row.side} {row.quantity} {row.symbol} - {row.status}",
        occurred_at_utc=row.submitted_at_utc or as_of,
        source=source,
        screen=SearchScreen.ORDERS,
        terms=(
            row.order_id,
            row.symbol,
            row.side,
            row.quantity,
            row.status,
            row.broker_order_id,
            row.reconciliation,
        ),
    )


def _approval_record(row: ApprovalRow, source: str) -> _IndexRecord:
    return _record(
        kind=SearchKind.APPROVAL,
        record_type=SearchRecordType.APPROVAL_ROW,
        record_id=row.approval_id,
        label=row.approval_id,
        summary=row.reason or row.state,
        occurred_at_utc=row.requested_at_utc,
        source=source,
        screen=SearchScreen.RISK,
        terms=(row.approval_id, row.state, row.reason, *row.evidence_ids),
    )


def _event_record(row: TimelineRow, source: str) -> _IndexRecord:
    return _record(
        kind=SearchKind.EVENT,
        record_type=SearchRecordType.TIMELINE_ROW,
        record_id=row.event_id,
        label=row.summary,
        summary=f"{row.severity} event",
        occurred_at_utc=row.occurred_at_utc,
        source=source,
        screen=SearchScreen.TIMELINE,
        terms=(
            row.event_id,
            row.summary,
            row.severity,
            row.agent_id,
            row.symbol,
            row.model_id,
            row.approval_id,
            row.order_id,
            *row.evidence_ids,
        ),
    )


def _evidence_record(row: EvidenceRow) -> _IndexRecord:
    return _record(
        kind=SearchKind.EVIDENCE,
        record_type=SearchRecordType.EVIDENCE_ROW,
        record_id=row.evidence_id,
        label=row.evidence_id,
        summary=f"{row.evidence_type} from {row.source}",
        occurred_at_utc=row.created_at_utc,
        source=row.source,
        screen=SearchScreen.DATA,
        terms=(row.evidence_id, row.evidence_type, row.source, row.sha256),
    )


def _memory_record(row: MemoryRow, source: str) -> _IndexRecord:
    return _record(
        kind=SearchKind.MEMORY,
        record_type=SearchRecordType.MEMORY_ROW,
        record_id=row.memory_id,
        label=row.summary,
        summary=row.status,
        occurred_at_utc=row.updated_at_utc,
        source=source,
        screen=SearchScreen.MEMORY,
        terms=(row.memory_id, row.status, row.summary, *row.evidence_ids),
    )


def _source_record(row: SourceRow, source: str) -> _IndexRecord:
    return _record(
        kind=SearchKind.SOURCE,
        record_type=SearchRecordType.SOURCE_ROW,
        record_id=row.source_id,
        label=row.source_id,
        summary=row.coverage or row.freshness,
        occurred_at_utc=row.as_of_utc,
        source=source,
        screen=SearchScreen.DATA,
        terms=(
            row.source_id,
            row.freshness,
            row.coverage,
            row.error,
            *row.consumers,
        ),
    )


def _repository_record(row: RepositoryRow) -> _IndexRecord:
    return _record(
        kind=SearchKind.SOURCE,
        record_type=SearchRecordType.REPOSITORY_ROW,
        record_id=row.repository_id,
        label=row.repository_id,
        summary=row.branch or row.freshness,
        occurred_at_utc=row.as_of_utc,
        source=row.source,
        screen=SearchScreen.SYSTEM,
        terms=(
            row.repository_id,
            row.branch,
            row.revision,
            row.freshness,
            row.error,
            *row.worktrees,
        ),
    )


def _serialize_time(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")
