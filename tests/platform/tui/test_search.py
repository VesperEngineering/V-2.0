from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from vesper.platform.tui.event_store import EventInput, EventStore
from vesper.platform.tui.notes import NoteStore, NoteTarget, NoteVisibility
from vesper.platform.tui.projections.managed_memory import ManagedMemoryProjection
from vesper.platform.tui.search import (
    GlobalSearchService,
    SearchFilters,
    SearchKind,
    SearchRecordType,
    SearchScreen,
    SearchService,
)
from vesper.platform.tui.sqlite_ledger import TuiLedger
from vesper.platform.tui.views import ConsoleSnapshot
from vesper.platform.tui.working_memory import (
    MemoryCandidate,
    MemoryValueScore,
    WorkingMemoryStore,
)


FIXTURE = Path("TUI testing/contracts/v1/console_snapshot_empty_command_specs.json")
NOW = datetime(2026, 8, 3, 16, 0, tzinfo=timezone.utc)


def _event(index: int, *, summary: str, event_id: str | None = None) -> EventInput:
    return EventInput(
        event_id=event_id or f"history:{index:05d}",
        occurred_at_utc=NOW + timedelta(seconds=index),
        impact=False,
        severity="info",
        summary=summary,
        agent_id="v20-product",
        symbol="AAPL",
        model_id=None,
        approval_id=None,
            order_id=None,
            evidence_ids=(),
            work_id=None,
            source="controller",
    )


@pytest.fixture
def search() -> SearchService:
    snapshot = ConsoleSnapshot.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    service = SearchService(snapshot)
    yield service
    service.close()


def test_search_covers_every_supported_record_type_and_routes_to_its_owner(
    search: SearchService,
) -> None:
    cases = (
        (
            "AAPL",
            SearchKind.STOCK,
            SearchRecordType.PORTFOLIO_ROW,
            "AAPL",
            SearchScreen.PORTFOLIO,
        ),
        (
            "work:1",
            SearchKind.AGENT,
            SearchRecordType.AGENT_CARD,
            "work:1",
            SearchScreen.AGENTS,
        ),
        (
            "model:active",
            SearchKind.MODEL,
            SearchRecordType.MODEL_OPINION_ROW,
            "model:active",
            SearchScreen.MODELS,
        ),
        (
            "order:1",
            SearchKind.ORDER,
            SearchRecordType.ORDER_ROW,
            "order:1",
            SearchScreen.ORDERS,
        ),
        (
            "approval:1",
            SearchKind.APPROVAL,
            SearchRecordType.APPROVAL_ROW,
            "approval:1",
            SearchScreen.RISK,
        ),
        (
            "event:1",
            SearchKind.EVENT,
            SearchRecordType.TIMELINE_ROW,
            "event:1",
            SearchScreen.TIMELINE,
        ),
        (
            "evidence:1",
            SearchKind.EVIDENCE,
            SearchRecordType.EVIDENCE_ROW,
            "evidence:1",
            SearchScreen.DATA,
        ),
        (
            "memory:1",
            SearchKind.MEMORY,
            SearchRecordType.MEMORY_ROW,
            "memory:1",
            SearchScreen.MEMORY,
        ),
        (
            "source:massive",
            SearchKind.SOURCE,
            SearchRecordType.SOURCE_ROW,
            "source:massive",
            SearchScreen.DATA,
        ),
    )

    for query, kind, record_type, record_id, screen in cases:
        results = search.search(query, SearchFilters(kinds=(kind,)), 10)
        assert [(item.kind, item.record_type, item.record_id, item.screen) for item in results] == [
            (kind, record_type, record_id, screen)
        ]


def test_search_ranks_exact_stock_then_exact_id_then_prefix_then_text(
    search: SearchService,
) -> None:
    aapl = search.search("AAPL", SearchFilters(), 20)
    assert (aapl[0].kind, aapl[0].record_id) == (SearchKind.STOCK, "AAPL")

    evidence = search.search("evidence:1", SearchFilters(), 20)
    assert (evidence[0].kind, evidence[0].record_id) == (
        SearchKind.EVIDENCE,
        "evidence:1",
    )

    source = search.search("source", SearchFilters(), 20)
    assert (source[0].kind, source[0].record_id) == (
        SearchKind.SOURCE,
        "source:massive",
    )


def test_search_matches_partial_prefix_tokens(search: SearchService) -> None:
    assert search.search("AAP", SearchFilters(kinds=(SearchKind.STOCK,)), 10)[0].record_id == "AAPL"
    assert (
        search.search("evid", SearchFilters(kinds=(SearchKind.EVIDENCE,)), 10)[0].record_id
        == "evidence:1"
    )


def test_search_tokenization_keeps_unicode_words() -> None:
    snapshot = ConsoleSnapshot.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    holding = snapshot.portfolio.rows[0].model_copy(update={"description": "Société énergie"})
    updated = snapshot.model_copy(
        update={
            "portfolio": snapshot.portfolio.model_copy(update={"rows": (holding,)}),
            "impact": snapshot.impact.model_copy(update={"holdings": (holding,)}),
        }
    )
    service = SearchService(updated)
    try:
        results = service.search(
            "société",
            SearchFilters(kinds=(SearchKind.STOCK,)),
            10,
        )
    finally:
        service.close()

    assert [result.record_id for result in results] == [holding.symbol]


def test_search_deduplicates_entities_repeated_across_screen_views(
    search: SearchService,
) -> None:
    cases = (
        ("AAPL", SearchKind.STOCK, "AAPL"),
        ("work:1", SearchKind.AGENT, "work:1"),
        ("event:1", SearchKind.EVENT, "event:1"),
        ("evidence:1", SearchKind.EVIDENCE, "evidence:1"),
    )

    for query, kind, record_id in cases:
        results = search.search(query, SearchFilters(kinds=(kind,)), 100)
        assert [item.record_id for item in results].count(record_id) == 1


def test_search_preserves_same_broad_kind_and_id_for_distinct_record_types() -> None:
    snapshot = ConsoleSnapshot.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    candidate = snapshot.models.candidates[0].model_copy(update={"candidate_id": "model:active"})
    repository = snapshot.system.repositories[0].model_copy(
        update={"repository_id": "source:massive"}
    )
    updated = snapshot.model_copy(
        update={
            "models": snapshot.models.model_copy(update={"candidates": (candidate,)}),
            "system": snapshot.system.model_copy(update={"repositories": (repository,)}),
        }
    )
    service = SearchService(updated)
    try:
        model_results = service.search(
            "model active",
            SearchFilters(kinds=(SearchKind.MODEL,)),
            10,
        )
        source_results = service.search(
            "source massive",
            SearchFilters(kinds=(SearchKind.SOURCE,)),
            10,
        )
    finally:
        service.close()

    assert {(item.record_type, item.record_id) for item in model_results} == {
        (SearchRecordType.MODEL_OPINION_ROW, "model:active"),
        (SearchRecordType.CANDIDATE_ROW, "model:active"),
    }
    assert {(item.record_type, item.record_id) for item in source_results} == {
        (SearchRecordType.SOURCE_ROW, "source:massive"),
        (SearchRecordType.REPOSITORY_ROW, "source:massive"),
    }


def test_search_applies_kind_screen_and_source_filters(search: SearchService) -> None:
    event_only = search.search(
        "AAPL",
        SearchFilters(kinds=(SearchKind.EVENT,), screens=(SearchScreen.TIMELINE,)),
        10,
    )
    assert [(item.kind, item.record_id) for item in event_only] == [(SearchKind.EVENT, "event:1")]

    assert (
        search.search(
            "AAPL",
            SearchFilters(kinds=(SearchKind.EVENT,), screens=(SearchScreen.ORDERS,)),
            10,
        )
        == ()
    )
    assert (
        search.search("AAPL", SearchFilters(kinds=(SearchKind.EVENT,), source="not-fixture"), 10)
        == ()
    )


def test_search_rejects_unbounded_or_malformed_requests(search: SearchService) -> None:
    assert search.search("x" * 256, SearchFilters(), 100) == ()

    for query in ("", "   ", "x" * 257):
        with pytest.raises(ValueError):
            search.search(query, SearchFilters(), 10)
    for limit in (0, 101, True):
        with pytest.raises((TypeError, ValueError)):
            search.search("AAPL", SearchFilters(), limit)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        search.search("AAPL", object(), 10)  # type: ignore[arg-type]


def test_rebuild_replaces_old_results_instead_of_leaking_stale_rows(
    search: SearchService,
) -> None:
    snapshot = ConsoleSnapshot.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    updated = snapshot.model_copy(
        update={
            "portfolio": snapshot.portfolio.model_copy(update={"rows": ()}),
            "impact": snapshot.impact.model_copy(update={"holdings": ()}),
        }
    )

    search.rebuild(updated)

    assert search.search("AAPL", SearchFilters(kinds=(SearchKind.STOCK,)), 10) == ()


def test_global_search_merges_snapshot_history_and_context_notes(tmp_path: Path) -> None:
    snapshot = ConsoleSnapshot.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    ledger = TuiLedger(tmp_path / "operations.sqlite3")
    events = EventStore(ledger)
    notes = NoteStore(
        ledger,
        clock=lambda: NOW,
        id_factory=lambda: "event:1",
    )
    events.append(
        _event(
            1,
            event_id="event:1",
            summary="AAPL review started",
        )
    )
    private = notes.add(
        NoteTarget(target_type="stock", target_id="AAPL"),
        "Private concentration context",
        NoteVisibility.PRIVATE,
        "operator",
    )
    service = GlobalSearchService(snapshot, events, notes)
    try:
        merged = service.search("AAPL", SearchFilters(), 100)
        keys = [(item.kind, item.record_id) for item in merged.results]
        assert keys[0] == (SearchKind.STOCK, "AAPL")
        assert keys.count((SearchKind.EVENT, "event:1")) == 1
        assert (SearchKind.NOTE, "event:1") in keys

        note_page = service.search(
            "Private conc",
            SearchFilters(
                kinds=(SearchKind.NOTE,),
                screens=(SearchScreen.PORTFOLIO,),
                source="operator",
            ),
            10,
        )
        assert [(item.kind, item.record_id) for item in note_page.results] == [
            (SearchKind.NOTE, private.note_id)
        ]
        assert note_page.results[0].context_only is True
        assert note_page.error is None
        assert note_page.indexed_state_version == snapshot.shell.state_version
        assert (
            service.search(
                "Private",
                SearchFilters(screens=(SearchScreen.ORDERS,)),
                10,
            ).results
            == ()
        )
    finally:
        service.close()
        events.close()
        notes.close()
        ledger.close()


def test_global_search_finds_oldest_event_outside_snapshot_window_after_restart(
    tmp_path: Path,
) -> None:
    database = tmp_path / "operations.sqlite3"
    ledger = TuiLedger(database)
    events = EventStore(ledger)
    notes = NoteStore(ledger)
    with ledger.transaction() as connection:
        events.append_in_transaction(
            connection,
            _event(0, summary="oldest sentinel history"),
        )
        for index in range(1, 10_001):
            events.append_in_transaction(
                connection,
                _event(index, summary=f"routine controller history {index}"),
            )
    window = events.latest(10_000)
    assert window.hidden_event_count == 1
    assert all(item.event_id != "history:00000" for item in window.events)

    snapshot = ConsoleSnapshot.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    service = GlobalSearchService(snapshot, events, notes)
    assert [
        item.record_id for item in service.search("oldest sent", SearchFilters(), 10).results
    ] == ["history:00000"]
    service.close()
    events.close()
    notes.close()
    ledger.close()

    reopened_ledger = TuiLedger(database)
    reopened_events = EventStore(reopened_ledger)
    reopened_notes = NoteStore(reopened_ledger)
    reopened = GlobalSearchService(snapshot, reopened_events, reopened_notes)
    try:
        assert [
            item.record_id
            for item in reopened.search("oldest sentinel", SearchFilters(), 10).results
        ] == ["history:00000"]
    finally:
        reopened.close()
        reopened_events.close()
        reopened_notes.close()
        reopened_ledger.close()


def test_global_search_matches_full_archived_memory_beyond_snapshot_summary(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    score = lambda value: MemoryValueScore(value, value, value, value, value, value)
    with WorkingMemoryStore(
        vault,
        clock=lambda: NOW,
        id_factory=lambda: "change:archive-search",
        candidate_validator=lambda _candidate: True,
    ) as store:
        store.propose(
            MemoryCandidate(
                memory_id="memory:deep-archive",
                content=("ordinary archive context " * 240) + "deeparchivesentinel",
                scope="v20",
                category="durable-lesson",
                supported=True,
                evidence_ids=("evidence:archive",),
                reason="Verified archived detail.",
                score=score(10),
            )
        )
        store.propose(
            MemoryCandidate(
                memory_id="memory:core-winner",
                content="high value core context " * 400,
                scope="v20",
                category="durable-lesson",
                supported=True,
                evidence_ids=("evidence:core",),
                reason="Higher-value Core memory.",
                score=score(20),
            )
        )
        store.curate("validated-work")

    snapshot = ConsoleSnapshot.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    projection = ManagedMemoryProjection(vault, clock=lambda: NOW)
    before = {path.name: path.read_bytes() for path in vault.iterdir() if path.is_file()}
    service = GlobalSearchService(
        snapshot,
        None,
        None,
        memory_archive=projection,
    )
    try:
        page = service.search(
            "deeparchivesentinel",
            SearchFilters(
                kinds=(SearchKind.MEMORY,),
                screens=(SearchScreen.MEMORY,),
            ),
            10,
        )
    finally:
        service.close()

    assert [(row.record_id, row.summary, row.source) for row in page.results] == [
        ("memory:deep-archive", "archived", "managed V20 working memory")
    ]
    assert page.error is None
    assert {path.name: path.read_bytes() for path in vault.iterdir() if path.is_file()} == before


def test_global_search_is_bounded_fts_safe_and_reports_store_errors_without_leaks(
    tmp_path: Path,
) -> None:
    snapshot = ConsoleSnapshot.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    events = EventStore(tmp_path / "operations.sqlite3")
    service = GlobalSearchService(snapshot, events, None)
    events.close()

    for hostile in ('AAPL" OR MSFT*', "NEAR(AAPL MSFT)", "agent_id:AAPL", "' OR 1=1 --"):
        page = service.search(hostile, SearchFilters(), 100)
        assert len(page.results) <= 100
        assert page.error == "Persisted search history is unavailable."
        assert "closed" not in page.error.casefold()

    limited = service.search("AAPL", SearchFilters(), 1)
    assert len(limited.results) == 1
    assert limited.results[0].kind is SearchKind.STOCK
    service.close()


def test_global_search_interleaves_providers_before_the_hundred_result_limit(
    tmp_path: Path,
) -> None:
    snapshot = ConsoleSnapshot.model_validate_json(FIXTURE.read_text(encoding="utf-8"))
    template = snapshot.portfolio.rows[0]
    holdings = tuple(
        template.model_copy(
            update={"symbol": f"S{index:03d}", "description": f"common holding {index}"}
        )
        for index in range(100)
    )
    snapshot = snapshot.model_copy(
        update={
            "portfolio": snapshot.portfolio.model_copy(update={"rows": holdings}),
            "impact": snapshot.impact.model_copy(update={"holdings": holdings}),
        }
    )
    ledger = TuiLedger(tmp_path / "operations.sqlite3")
    events = EventStore(ledger)
    notes = NoteStore(ledger, clock=lambda: NOW, id_factory=lambda: "note:persisted")
    event = events.append(_event(1, summary="common persisted event"))
    note = notes.add(
        NoteTarget(target_type="stock", target_id="S000"),
        "common persisted note",
        NoteVisibility.PRIVATE,
        "operator",
    )
    service = GlobalSearchService(snapshot, events, notes)
    try:
        page = service.search("common", SearchFilters(), 100)
    finally:
        service.close()
        events.close()
        notes.close()
        ledger.close()

    assert len(page.results) == 100
    assert (SearchRecordType.TIMELINE_ROW, event.event_id) in {
        (item.record_type, item.record_id) for item in page.results
    }
    assert (SearchRecordType.NOTE, note.note_id) in {
        (item.record_type, item.record_id) for item in page.results
    }
