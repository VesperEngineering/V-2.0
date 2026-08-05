use std::path::PathBuf;
use std::time::{Duration, Instant};

use crossterm::event::{KeyModifiers, MouseButton, MouseEvent, MouseEventKind};
use ratatui::Terminal;
use ratatui::backend::TestBackend;
use ratatui::layout::Rect;
use serde_json::{Value, json};
use vesper_ratatui_console::ConsoleSnapshot;
use vesper_ratatui_console::app::mouse_to_input;
use vesper_ratatui_console::contract::{
    CommandPayload, Envelope, SearchResultPayload, WireSearchKind, WireSearchRecordType,
    WireSearchScreen,
};
use vesper_ratatui_console::input::InputEvent;
use vesper_ratatui_console::layout::shell_layout;
use vesper_ratatui_console::screens::DetailKind;
use vesper_ratatui_console::search::{
    MAX_SEARCH_QUERY_CHARS, MAX_SEARCH_RESULTS, NoteVisibility, SEARCH_DEBOUNCE, SearchError,
    SearchFilters, SearchIndex, SearchKind, SearchRequest, SearchState, SearchWireError,
    format_filter_expression, parse_filter_expression,
};
use vesper_ratatui_console::state::{AppState, ClientAction, LocalMode, Screen};

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .expect("crate is nested two levels under the repository")
        .to_path_buf()
}

fn snapshot_value() -> Value {
    serde_json::from_slice(
        &std::fs::read(
            repo_root().join("TUI testing/contracts/v1/console_snapshot_empty_command_specs.json"),
        )
        .expect("read shared snapshot fixture"),
    )
    .expect("strict snapshot JSON")
}

fn note_enabled_snapshot_value() -> Value {
    let mut value: Value = serde_json::from_slice(
        &std::fs::read(repo_root().join("TUI testing/contracts/v1/controls_snapshot.json"))
            .expect("read shared controls fixture"),
    )
    .expect("strict controls snapshot JSON");
    value["shell"]["capabilities"] = json!([{
        "capability_id": "note.add",
        "state": "enabled",
        "reason": null
    }]);
    value
}

fn snapshot(value: Value) -> ConsoleSnapshot {
    serde_json::from_value(value).expect("strict console snapshot")
}

fn search_results_envelope(
    sequence: u64,
    state_version: u64,
    request_id: u64,
    results: Vec<Value>,
) -> Envelope {
    serde_json::from_value(json!({
        "schema_version": 1,
        "message_id": format!("server:{sequence}"),
        "sequence": sequence,
        "state_version": state_version,
        "timestamp_utc": "2026-08-03T00:00:00Z",
        "message_type": "search-results",
        "payload": {
            "request_id": request_id,
            "indexed_state_version": state_version,
            "results": results,
            "error": null,
        },
    }))
    .expect("search results envelope")
}

fn memory_content_result_envelope(
    sequence: u64,
    request_id: u64,
    memory_id: &str,
    reviewed_updated_at_utc: &str,
    status: &str,
    content: Option<&str>,
    error: Option<&str>,
) -> Envelope {
    serde_json::from_value(json!({
        "schema_version": 1,
        "message_id": format!("server:{sequence}"),
        "sequence": sequence,
        "state_version": 0,
        "timestamp_utc": "2026-08-03T00:00:00Z",
        "message_type": "memory-content-result",
        "payload": {
            "request_id": request_id,
            "memory_id": memory_id,
            "reviewed_updated_at_utc": reviewed_updated_at_utc,
            "status": status,
            "content": content,
            "error": error,
        },
    }))
    .expect("memory content result envelope")
}

fn issued_search_request_id(actions: &[ClientAction]) -> u64 {
    let [ClientAction::Search(request)] = actions else {
        panic!("expected one search action, got {actions:?}");
    };
    request.request_id.get()
}

fn stock_search_result() -> Value {
    json!({
        "kind": "stock",
        "record_type": "portfolio-row",
        "record_id": "AAPL",
        "label": "AAPL",
        "summary": "Current holding",
        "occurred_at_utc": "2026-08-03T00:00:00Z",
        "source": "fixture",
        "screen": "portfolio",
        "context_only": null,
    })
}

#[test]
fn gateway_search_request_preserves_typed_scope_and_one_source() {
    let request = SearchRequest {
        request_id: 7,
        query: "  AAPL  ".to_owned(),
        filters: SearchFilters {
            screen: Some(Screen::Impact),
            kinds: vec![SearchKind::Stock, SearchKind::Note],
            source: Some("fixture".to_owned()),
        },
    }
    .to_wire()
    .expect("valid gateway search request");

    assert_eq!(request.request_id.get(), 7);
    assert_eq!(request.query.as_str(), "AAPL");
    assert_eq!(
        request.filters.kinds,
        vec![WireSearchKind::Stock, WireSearchKind::Note]
    );
    assert_eq!(
        request.filters.screens,
        vec![
            WireSearchScreen::Portfolio,
            WireSearchScreen::Agents,
            WireSearchScreen::Timeline,
        ]
    );
    assert_eq!(
        request.filters.source.as_ref().map(|value| value.as_str()),
        Some("fixture")
    );
    assert_eq!(request.limit.get(), 100);
}

#[test]
fn gateway_search_result_routes_every_record_type_to_its_detail() {
    let result = |record_type: WireSearchRecordType,
                  kind: WireSearchKind,
                  screen: WireSearchScreen,
                  context_only: Value| {
        serde_json::from_value::<SearchResultPayload>(json!({
            "kind": kind,
            "record_type": record_type,
            "record_id": "shared:id",
            "label": "Shared result",
            "summary": "Result detail",
            "occurred_at_utc": null,
            "source": "fixture",
            "screen": screen,
            "context_only": context_only,
        }))
        .expect("strict wire search result")
        .try_into()
    };

    for (record_type, kind, wire_screen, search_kind, detail_kind, screen) in [
        (
            WireSearchRecordType::PortfolioRow,
            WireSearchKind::Stock,
            WireSearchScreen::Portfolio,
            SearchKind::Stock,
            DetailKind::Stock,
            Screen::Portfolio,
        ),
        (
            WireSearchRecordType::AgentCard,
            WireSearchKind::Agent,
            WireSearchScreen::Agents,
            SearchKind::Agent,
            DetailKind::Agent,
            Screen::Agents,
        ),
        (
            WireSearchRecordType::ModelOpinionRow,
            WireSearchKind::Model,
            WireSearchScreen::ModelsRegime,
            SearchKind::Model,
            DetailKind::ModelOpinion,
            Screen::ModelsRegime,
        ),
        (
            WireSearchRecordType::CandidateRow,
            WireSearchKind::Model,
            WireSearchScreen::ModelsRegime,
            SearchKind::Model,
            DetailKind::ModelCandidate,
            Screen::ModelsRegime,
        ),
        (
            WireSearchRecordType::OrderRow,
            WireSearchKind::Order,
            WireSearchScreen::Orders,
            SearchKind::Order,
            DetailKind::Order,
            Screen::Orders,
        ),
        (
            WireSearchRecordType::ApprovalRow,
            WireSearchKind::Approval,
            WireSearchScreen::RiskApprovals,
            SearchKind::Approval,
            DetailKind::Approval,
            Screen::RiskApprovals,
        ),
        (
            WireSearchRecordType::TimelineRow,
            WireSearchKind::Event,
            WireSearchScreen::Timeline,
            SearchKind::Event,
            DetailKind::Event,
            Screen::Timeline,
        ),
        (
            WireSearchRecordType::EvidenceRow,
            WireSearchKind::Evidence,
            WireSearchScreen::DataEvidence,
            SearchKind::Evidence,
            DetailKind::Evidence,
            Screen::DataEvidence,
        ),
        (
            WireSearchRecordType::MemoryRow,
            WireSearchKind::Memory,
            WireSearchScreen::Memory,
            SearchKind::Memory,
            DetailKind::Memory,
            Screen::Memory,
        ),
        (
            WireSearchRecordType::SourceRow,
            WireSearchKind::Source,
            WireSearchScreen::DataEvidence,
            SearchKind::Source,
            DetailKind::Source,
            Screen::DataEvidence,
        ),
        (
            WireSearchRecordType::RepositoryRow,
            WireSearchKind::Source,
            WireSearchScreen::System,
            SearchKind::Source,
            DetailKind::Repository,
            Screen::System,
        ),
        (
            WireSearchRecordType::Note,
            WireSearchKind::Note,
            WireSearchScreen::Portfolio,
            SearchKind::Note,
            DetailKind::Note,
            Screen::Portfolio,
        ),
    ] {
        let context_only = if record_type == WireSearchRecordType::Note {
            json!(true)
        } else {
            Value::Null
        };
        let row: vesper_ratatui_console::search::SearchResult =
            result(record_type, kind, wire_screen, context_only).expect("valid typed route");
        assert_eq!(row.kind, search_kind, "{record_type:?}");
        assert_eq!(row.target.detail_kind, detail_kind, "{record_type:?}");
        assert_eq!(row.target.screen, screen, "{record_type:?}");
    }

    for wire_screen in [
        WireSearchScreen::Portfolio,
        WireSearchScreen::Orders,
        WireSearchScreen::RiskApprovals,
        WireSearchScreen::Timeline,
    ] {
        let note: vesper_ratatui_console::search::SearchResult = result(
            WireSearchRecordType::Note,
            WireSearchKind::Note,
            wire_screen,
            json!(true),
        )
        .expect("legal note screen");
        assert_eq!(note.target.detail_kind, DetailKind::Note);
        assert!(note.context_only);
    }

    assert_eq!(
        result(
            WireSearchRecordType::CandidateRow,
            WireSearchKind::Stock,
            WireSearchScreen::ModelsRegime,
            Value::Null,
        ),
        Err(SearchWireError::IncompatibleRoute)
    );
    assert_eq!(
        result(
            WireSearchRecordType::Note,
            WireSearchKind::Note,
            WireSearchScreen::ModelsRegime,
            json!(true),
        ),
        Err(SearchWireError::IncompatibleRoute)
    );
    assert_eq!(
        result(
            WireSearchRecordType::PortfolioRow,
            WireSearchKind::Stock,
            WireSearchScreen::Portfolio,
            json!(true),
        ),
        Err(SearchWireError::InvalidContextFlag)
    );
}

fn snapshot_envelope(sequence: u64, state_version: u64, mut value: Value) -> Envelope {
    value["shell"]["state_version"] = json!(state_version);
    serde_json::from_value(json!({
        "schema_version": 1,
        "message_id": format!("server:{sequence}"),
        "sequence": sequence,
        "state_version": state_version,
        "timestamp_utc": "2026-08-03T00:00:00Z",
        "message_type": "snapshot",
        "payload": {"snapshot": value},
    }))
    .expect("snapshot envelope")
}

fn rendered_text(state: &AppState, width: u16, height: u16) -> String {
    let backend = TestBackend::new(width, height);
    let mut terminal = Terminal::new(backend).unwrap();
    terminal
        .draw(|frame| vesper_ratatui_console::ui::render(frame, state))
        .unwrap();
    terminal
        .backend()
        .buffer()
        .content
        .iter()
        .map(|cell| cell.symbol())
        .collect()
}

#[test]
fn memory_search_opens_only_exact_authenticated_full_content_and_returns_to_summary() {
    let mut state = AppState::controller();
    state
        .reduce(snapshot_envelope(1, 0, snapshot_value()))
        .unwrap();
    state.handle(InputEvent::Char('/'));
    for character in "deep archive".chars() {
        state.handle(InputEvent::Char(character));
    }
    let search_id = issued_search_request_id(&state.handle(InputEvent::Tick(SEARCH_DEBOUNCE)));
    state
        .reduce(search_results_envelope(
            2,
            0,
            search_id,
            vec![json!({
                "kind": "memory",
                "record_type": "memory-row",
                "record_id": "memory:deep-archive",
                "label": "Deep archive",
                "summary": "Safe bounded summary only.",
                "occurred_at_utc": "2026-08-02T14:30:00Z",
                "source": "managed-memory",
                "screen": "memory",
                "context_only": null,
            })],
        ))
        .unwrap();

    let actions = state.handle(InputEvent::Char('o'));
    let [ClientAction::MemoryContent(request)] = actions.as_slice() else {
        panic!("expected one exact memory content request, got {actions:?}");
    };
    assert_eq!(request.request_id.get(), 1);
    assert_eq!(request.memory_id.as_str(), "memory:deep-archive");
    assert_eq!(
        request.reviewed_updated_at_utc.as_str(),
        "2026-08-02T14:30:00Z"
    );
    let loading = rendered_text(&state, 120, 36);
    assert!(loading.contains("MEMORY CONTENT"), "{loading}");
    assert!(loading.contains("Loading current content"), "{loading}");
    assert!(
        !loading.contains("Full private current content"),
        "{loading}"
    );

    state
        .reduce(memory_content_result_envelope(
            3,
            1,
            "memory:deep-archive",
            "2026-08-02T14:30:00Z",
            "success",
            Some("Full private current content.\nSecond reviewed line."),
            None,
        ))
        .unwrap();
    let ready = rendered_text(&state, 120, 36);
    assert!(ready.contains("Full private current content."), "{ready}");
    assert!(ready.contains("Second reviewed line."), "{ready}");

    state.handle(InputEvent::Escape);
    let summary = rendered_text(&state, 120, 36);
    assert_eq!(state.mode, LocalMode::Search);
    assert!(summary.contains("SEARCH ALL V20"), "{summary}");
    assert!(summary.contains("Safe bounded summary only."), "{summary}");
    assert!(
        !summary.contains("Full private current content."),
        "{summary}"
    );
}

#[test]
fn direct_memory_rows_request_core_and_archive_bindings_and_show_safe_errors() {
    let mut value = snapshot_value();
    value["memory"]["rows"].as_array_mut().unwrap().push(json!({
        "memory_id": "memory:archive",
        "status": "archived",
        "summary": "Archived bounded summary.",
        "evidence_ids": [],
        "updated_at_utc": "2026-07-01T12:00:00Z",
        "used_by_agents": [],
        "change_reason": null
    }));
    let mut state = AppState::controller();
    state.reduce(snapshot_envelope(1, 0, value)).unwrap();
    state.handle(InputEvent::Char('9'));

    let core = state.handle(InputEvent::Char('o'));
    let [ClientAction::MemoryContent(core)] = core.as_slice() else {
        panic!("core row must issue exact content request: {core:?}");
    };
    assert_eq!(core.request_id.get(), 1);
    assert_eq!(core.memory_id.as_str(), "memory:1");
    assert_eq!(
        core.reviewed_updated_at_utc.as_str(),
        "2026-08-03T00:00:00Z"
    );
    state
        .reduce(memory_content_result_envelope(
            2,
            1,
            "memory:1",
            "2026-08-03T00:00:00Z",
            "error",
            None,
            Some("Memory changed. Search again."),
        ))
        .unwrap();
    let unavailable = rendered_text(&state, 120, 36);
    assert!(
        unavailable.contains("Memory changed. Search again."),
        "{unavailable}"
    );

    state.handle(InputEvent::Escape);
    state.handle(InputEvent::Right);
    let archived = state.handle(InputEvent::Char('o'));
    let [ClientAction::MemoryContent(archived)] = archived.as_slice() else {
        panic!("archived row must issue exact content request: {archived:?}");
    };
    assert_eq!(archived.request_id.get(), 2);
    assert_eq!(archived.memory_id.as_str(), "memory:archive");
    assert_eq!(
        archived.reviewed_updated_at_utc.as_str(),
        "2026-07-01T12:00:00Z"
    );
}

#[test]
fn memory_content_ignores_superseded_results_and_fails_closed_on_binding_mismatch() {
    let mut state = AppState::controller();
    state
        .reduce(snapshot_envelope(1, 0, snapshot_value()))
        .unwrap();
    state.handle(InputEvent::Char('9'));
    assert!(matches!(
        state.handle(InputEvent::Char('o')).as_slice(),
        [ClientAction::MemoryContent(_)]
    ));
    state.handle(InputEvent::Escape);
    assert!(matches!(
        state.handle(InputEvent::Char('o')).as_slice(),
        [ClientAction::MemoryContent(_)]
    ));

    assert_eq!(
        state.reduce(memory_content_result_envelope(
            2,
            1,
            "memory:1",
            "2026-08-03T00:00:00Z",
            "success",
            Some("Old result"),
            None,
        )),
        Ok(vesper_ratatui_console::state::ReduceOutcome::Ignored)
    );
    assert!(!rendered_text(&state, 120, 36).contains("Old result"));

    let error = state
        .reduce(memory_content_result_envelope(
            3,
            2,
            "memory:wrong",
            "2026-08-03T00:00:00Z",
            "success",
            Some("Wrong binding"),
            None,
        ))
        .unwrap_err();
    assert_eq!(error.code, "memory-content");
    assert_eq!(
        state.access,
        vesper_ratatui_console::state::AccessState::ProtocolLockout
    );
}

#[test]
fn indexes_all_supported_kinds_once_and_routes_to_the_owning_entity() {
    let index = SearchIndex::from_snapshot(&snapshot(snapshot_value()));
    for (query, kind, screen, entity_id) in [
        ("AAPL", SearchKind::Stock, Screen::Portfolio, "AAPL"),
        ("work:1", SearchKind::Agent, Screen::Agents, "work:1"),
        (
            "model:active",
            SearchKind::Model,
            Screen::ModelsRegime,
            "model:active",
        ),
        ("order:1", SearchKind::Order, Screen::Orders, "order:1"),
        (
            "approval:1",
            SearchKind::Approval,
            Screen::RiskApprovals,
            "approval:1",
        ),
        ("event:1", SearchKind::Event, Screen::Timeline, "event:1"),
        (
            "evidence:1",
            SearchKind::Evidence,
            Screen::DataEvidence,
            "evidence:1",
        ),
        ("memory:1", SearchKind::Memory, Screen::Memory, "memory:1"),
        (
            "source:massive",
            SearchKind::Source,
            Screen::DataEvidence,
            "source:massive",
        ),
    ] {
        let rows = index.search(query, &SearchFilters::default(), 100).unwrap();
        let exact = rows
            .iter()
            .filter(|row| row.kind == kind && row.entity_id == entity_id)
            .collect::<Vec<_>>();
        assert_eq!(exact.len(), 1, "{kind:?} must be deduplicated");
        assert_eq!(exact[0].target.screen, screen);
        assert_eq!(exact[0].target.entity_id, entity_id);
        assert_eq!(exact[0].target.kind, kind);
    }

    let repository = index
        .search(
            "repository:v20",
            &SearchFilters {
                screen: Some(Screen::System),
                kinds: vec![SearchKind::Source],
                source: Some("git".to_owned()),
            },
            100,
        )
        .unwrap();
    assert_eq!(repository.len(), 1);
    assert_eq!(repository[0].entity_id, "repository:v20");
    assert_eq!(repository[0].target.screen, Screen::System);
}

#[test]
fn local_index_searches_every_deep_field_and_evidence_link_facet() {
    let mut value = snapshot_value();
    let agent = &mut value["agents"]["rows"][0];
    agent["session_id"] = json!("session:sessionneedle");
    agent["plan_steps"] = json!(["planneedle approved input"]);
    agent["activity"][0]["summary"] = json!("activityneedle controller stage");
    agent["activity"][0]["evidence_ids"] = json!(["evidence:activityneedle"]);
    agent["evidence_ids"] = json!(["evidence:agentneedle"]);
    agent["chat_agent_id"] = json!("agent:chatneedle");
    agent["detail_next_cursor"] = json!("cursor:agentcursor");

    let candidate = &mut value["models"]["candidates"][0];
    candidate["feature_set_id"] = json!("features:featureneedle");
    candidate["data_identity"] =
        json!("1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef");
    candidate["evaluation_contract"] =
        json!("fedcba0987654321fedcba0987654321fedcba0987654321fedcba0987654321");
    candidate["status_reason"] = json!("statusneedle evaluation reason");

    let evidence = &mut value["data"]["evidence"][0];
    evidence["symbols"] = json!(["EVIDSYM"]);
    evidence["agent_ids"] = json!(["agent:evidenceagent"]);
    evidence["model_ids"] = json!(["model:evidencemodel"]);
    evidence["order_ids"] = json!(["order:evidenceorder"]);
    evidence["approval_ids"] = json!(["approval:evidenceapproval"]);
    evidence["source_ids"] = json!(["source:evidencesource"]);
    evidence["raw_log_id"] = json!("log:evidencelog");
    evidence["raw_log_excerpt"] = json!(["rawexcerptneedle controller line"]);
    evidence["raw_log_truncated"] = json!(true);
    evidence["raw_log_next_cursor"] = json!("cursor:evidencecursor");

    value["memory"]["rows"][0]["used_by_agents"] = json!(["agent:memoryuserneedle"]);
    value["memory"]["rows"][0]["change_reason"] = json!("memoryreasonneedle retained");
    value["data"]["sources"][0]["dependencies"] = json!(["dependencyneedle calendar"]);
    value["system"]["repositories"][0]["checks"][0]["check_id"] = json!("check:repocheckneedle");
    value["system"]["repositories"][0]["checks"][0]["reason"] = json!("reporeasonneedle verified");

    let index = SearchIndex::from_snapshot(&snapshot(value));
    for (query, kind, entity_id) in [
        ("sessionneedle", SearchKind::Agent, "work:1"),
        ("planneedle", SearchKind::Agent, "work:1"),
        ("activityneedle", SearchKind::Agent, "work:1"),
        ("agentneedle", SearchKind::Agent, "work:1"),
        ("chatneedle", SearchKind::Agent, "work:1"),
        ("agentcursor", SearchKind::Agent, "work:1"),
        ("featureneedle", SearchKind::Model, "candidate:1"),
        ("1234567890abcdef", SearchKind::Model, "candidate:1"),
        ("fedcba0987654321", SearchKind::Model, "candidate:1"),
        ("statusneedle", SearchKind::Model, "candidate:1"),
        ("memoryuserneedle", SearchKind::Memory, "memory:1"),
        ("memoryreasonneedle", SearchKind::Memory, "memory:1"),
        ("dependencyneedle", SearchKind::Source, "source:massive"),
        ("repocheckneedle", SearchKind::Source, "repository:v20"),
        ("reporeasonneedle", SearchKind::Source, "repository:v20"),
    ] {
        let rows = index
            .search(
                query,
                &SearchFilters {
                    kinds: vec![kind],
                    ..SearchFilters::default()
                },
                20,
            )
            .unwrap();
        assert!(
            rows.iter().any(|row| row.entity_id == entity_id),
            "{query} did not find {entity_id}: {rows:?}"
        );
    }

    for query in [
        "EVIDSYM",
        "evidenceagent",
        "evidencemodel",
        "evidenceorder",
        "evidenceapproval",
        "evidencesource",
        "evidencelog",
        "rawexcerptneedle",
        "evidencecursor",
    ] {
        let rows = index
            .search(
                query,
                &SearchFilters {
                    kinds: vec![SearchKind::Evidence],
                    ..SearchFilters::default()
                },
                20,
            )
            .unwrap();
        assert_eq!(
            rows.iter()
                .map(|row| row.entity_id.as_str())
                .collect::<Vec<_>>(),
            vec!["evidence:1"],
            "evidence facet {query}"
        );
    }
}

#[test]
fn ranks_exact_symbol_before_exact_id_then_prefix_then_text() {
    let mut value = snapshot_value();
    value["agents"]["rows"][0]["work_id"] = json!("AAPL");
    value["impact"]["agents"] = json!([]);
    value["orders"]["reconciliation_agents"] = json!([]);
    value["memory"]["rows"][0]["memory_id"] = json!("AAPL-memory");
    value["risk"]["approvals"][0]["reason"] = json!("Investigate AAPL exposure");
    value["risk"]["approvals"][0]["affected_symbols"] = json!(["NVDA"]);
    value["risk"]["approvals"][0]["weight_changes"][0]["symbol"] = json!("NVDA");
    value["risk"]["approvals"][0]["expected_consequences"] = json!(["NVDA allocation rises."]);

    let rows = SearchIndex::from_snapshot(&snapshot(value))
        .search("aapl", &SearchFilters::default(), 100)
        .unwrap();
    let ordered = rows
        .iter()
        .map(|row| (row.kind, row.entity_id.as_str()))
        .collect::<Vec<_>>();
    let stock = ordered
        .iter()
        .position(|row| *row == (SearchKind::Stock, "AAPL"))
        .unwrap();
    let exact_id = ordered
        .iter()
        .position(|row| *row == (SearchKind::Agent, "AAPL"))
        .unwrap();
    let prefix = ordered
        .iter()
        .position(|row| *row == (SearchKind::Memory, "AAPL-memory"))
        .unwrap();
    let text = ordered
        .iter()
        .position(|row| *row == (SearchKind::Approval, "approval:1"))
        .unwrap();
    assert!(stock < exact_id && exact_id < prefix && prefix < text);
}

#[test]
fn duplicate_safe_ids_keep_distinct_typed_model_targets() {
    let mut value = snapshot_value();
    value["models"]["candidates"][0]["candidate_id"] = json!("model:active");

    let rows = SearchIndex::from_snapshot(&snapshot(value))
        .search(
            "model:active",
            &SearchFilters {
                kinds: vec![SearchKind::Model],
                ..SearchFilters::default()
            },
            10,
        )
        .unwrap();
    let kinds = rows
        .iter()
        .map(|row| row.target.detail_kind)
        .collect::<Vec<_>>();

    assert_eq!(
        kinds,
        vec![DetailKind::ModelOpinion, DetailKind::ModelCandidate]
    );
}

#[test]
fn changed_snapshot_clears_cached_search_results_before_escape_can_restore_search() {
    let mut initial = snapshot_value();
    initial["models"]["candidates"][0]["candidate_id"] = json!("model:active");
    let mut state = AppState::controller();
    state
        .reduce(snapshot_envelope(1, 0, initial.clone()))
        .unwrap();
    state.handle(InputEvent::Char('2'));
    state.handle(InputEvent::Char('/'));
    for character in "model:active".chars() {
        state.handle(InputEvent::Char(character));
    }
    let request_id = issued_search_request_id(&state.handle(InputEvent::Tick(SEARCH_DEBOUNCE)));
    state
        .reduce(search_results_envelope(
            2,
            0,
            request_id,
            vec![
                json!({
                    "kind": "model",
                    "record_type": "model-opinion-row",
                    "record_id": "model:active",
                    "label": "model:active",
                    "summary": "Active model opinion",
                    "occurred_at_utc": "2026-08-03T00:00:00Z",
                    "source": "fixture",
                    "screen": "models-regime",
                    "context_only": null,
                }),
                json!({
                    "kind": "model",
                    "record_type": "candidate-row",
                    "record_id": "model:active",
                    "label": "model:active",
                    "summary": "Model candidate",
                    "occurred_at_utc": "2026-08-03T00:00:00Z",
                    "source": "fixture",
                    "screen": "models-regime",
                    "context_only": null,
                }),
            ],
        ))
        .unwrap();
    state.handle(InputEvent::Down);
    state.handle(InputEvent::Enter);

    assert_eq!(state.screen, Screen::ModelsRegime);
    assert_eq!(
        state.screen_state().selected_kind,
        Some(DetailKind::ModelCandidate)
    );
    assert!(state.search_detail().is_some());
    assert!(
        !rendered_text(&state, 140, 40).contains("Add Private/Shared note"),
        "model search detail must not advertise unsupported notes"
    );

    initial["models"]["candidates"][0]["family"] = json!("updated-family");
    state.reduce(snapshot_envelope(3, 1, initial)).unwrap();

    assert!(state.search_detail().is_none());
    assert!(state.search_state().results().is_empty());
    let detail = rendered_text(&state, 140, 40);
    assert!(detail.contains("MODEL CANDIDATE DETAIL"), "{detail}");
    assert!(detail.contains("FAMILY: updated-family"), "{detail}");

    state.handle(InputEvent::Escape);
    assert_eq!(state.mode, LocalMode::Search);
    assert_eq!(state.screen, Screen::Portfolio);
    assert_eq!(state.search_state().query(), "model:active");
    state.handle(InputEvent::Enter);
    assert_eq!(state.mode, LocalMode::Search);
    assert_eq!(state.screen, Screen::Portfolio);

    let request_id = issued_search_request_id(&state.handle(InputEvent::Tick(SEARCH_DEBOUNCE)));
    state
        .reduce(search_results_envelope(
            4,
            1,
            request_id,
            vec![json!({
                "kind": "model",
                "record_type": "candidate-row",
                "record_id": "model:active",
                "label": "model:active",
                "summary": "Updated model candidate",
                "occurred_at_utc": "2026-08-03T00:00:00Z",
                "source": "fixture",
                "screen": "models-regime",
                "context_only": null,
            })],
        ))
        .unwrap();
    assert!(!state.search_state().results().is_empty());
}

#[test]
fn text_matches_use_bm25_relevance_before_stable_id_tiebreaks() {
    let mut value = snapshot_value();
    let base = value["memory"]["rows"][0].clone();
    let mut weak = base.clone();
    weak["memory_id"] = json!("memory:a-weak");
    weak["summary"] = json!("review needle with many unrelated filler words around it");
    let mut strong = base;
    strong["memory_id"] = json!("memory:z-strong");
    strong["summary"] = json!("review needle needle needle");
    value["memory"]["rows"] = json!([weak, strong]);

    let rows = SearchIndex::from_snapshot(&snapshot(value))
        .search(
            "needle",
            &SearchFilters {
                kinds: vec![SearchKind::Memory],
                ..SearchFilters::default()
            },
            10,
        )
        .unwrap();
    assert_eq!(rows[0].entity_id, "memory:z-strong");
    assert_eq!(rows[1].entity_id, "memory:a-weak");
}

#[test]
fn bounds_unicode_queries_requested_limits_and_total_results() {
    let mut value = snapshot_value();
    let base = value["memory"]["rows"][0].clone();
    value["memory"]["rows"] = Value::Array(
        (0..140)
            .map(|index| {
                let mut row = base.clone();
                row["memory_id"] = json!(format!("memory:{index:03}"));
                row["summary"] = json!(format!("common memory {index:03}"));
                row
            })
            .collect(),
    );
    let index = SearchIndex::from_snapshot(&snapshot(value));

    let rows = index
        .search("common", &SearchFilters::default(), usize::MAX)
        .unwrap();
    assert_eq!(rows.len(), MAX_SEARCH_RESULTS);
    assert_eq!(
        rows,
        index
            .search("common", &SearchFilters::default(), usize::MAX)
            .unwrap()
    );
    assert_eq!(
        index
            .search("common", &SearchFilters::default(), 3)
            .unwrap()
            .len(),
        3
    );
    assert!(
        index
            .search(
                &"界".repeat(MAX_SEARCH_QUERY_CHARS),
                &SearchFilters::default(),
                100,
            )
            .is_ok()
    );
    assert_eq!(
        index.search(
            &"界".repeat(MAX_SEARCH_QUERY_CHARS + 1),
            &SearchFilters::default(),
            100,
        ),
        Err(SearchError::QueryTooLong)
    );
}

#[test]
fn applies_screen_kind_and_source_filters_without_changing_rank_order() {
    let index = SearchIndex::from_snapshot(&snapshot(snapshot_value()));
    let stock = index
        .search(
            "AAPL",
            &SearchFilters {
                screen: Some(Screen::Portfolio),
                kinds: vec![SearchKind::Stock],
                source: Some("FIXTURE".to_owned()),
            },
            100,
        )
        .unwrap();
    assert_eq!(stock.len(), 1);
    assert_eq!(stock[0].kind, SearchKind::Stock);

    let event = index
        .search(
            "AAPL",
            &SearchFilters {
                screen: Some(Screen::Timeline),
                kinds: vec![SearchKind::Event],
                source: Some("fixture".to_owned()),
            },
            100,
        )
        .unwrap();
    assert_eq!(event.len(), 1);
    assert_eq!(event[0].entity_id, "event:1");

    let none = index
        .search(
            "AAPL",
            &SearchFilters {
                screen: None,
                kinds: vec![],
                source: Some("another-source".to_owned()),
            },
            100,
        )
        .unwrap();
    assert!(none.is_empty());
}

#[test]
fn sanitizes_every_displayed_field_before_returning_it() {
    let mut value = snapshot_value();
    value["memory"]["rows"][0]["summary"] = json!("danger\n\u{202e}hidden");
    value["memory"]["source"] = json!("local\t\u{2066}source");
    let rows = SearchIndex::from_snapshot(&snapshot(value))
        .search("danger", &SearchFilters::default(), 100)
        .unwrap();
    assert_eq!(rows.len(), 1);
    for field in [
        rows[0].entity_id.as_str(),
        rows[0].title.as_str(),
        rows[0].text.as_str(),
        rows[0].source.as_str(),
        rows[0].target.entity_id.as_str(),
    ] {
        assert!(!field.chars().any(char::is_control));
        assert!(!field.contains('\u{202e}'));
        assert!(!field.contains('\u{2066}'));
    }
    assert!(rows[0].title.contains('?'));
    assert!(rows[0].source.contains('?'));
}

#[test]
fn blank_queries_and_zero_limits_return_no_rows() {
    let index = SearchIndex::from_snapshot(&snapshot(snapshot_value()));
    assert!(
        index
            .search(" \t\n ", &SearchFilters::default(), 100)
            .unwrap()
            .is_empty()
    );
    assert!(
        index
            .search("AAPL", &SearchFilters::default(), 0)
            .unwrap()
            .is_empty()
    );
}

#[test]
fn search_state_debounces_and_ignores_superseded_results() {
    let now = Instant::now();
    let mut state = SearchState::default();
    state.set_filters(
        Screen::Portfolio,
        SearchFilters {
            screen: Some(Screen::Portfolio),
            kinds: vec![SearchKind::Stock],
            source: Some("fixture".to_owned()),
        },
    );
    state.set_active_screen(Screen::Portfolio);
    assert!(state.update_query("AAP".to_owned(), now).is_none());
    assert!(
        state
            .take_due_request(now + SEARCH_DEBOUNCE - Duration::from_millis(1))
            .is_none()
    );

    assert!(
        state
            .update_query("AAPL".to_owned(), now + Duration::from_millis(50))
            .is_none()
    );
    assert!(
        state
            .take_due_request(now + Duration::from_millis(149))
            .is_none()
    );
    let request = state
        .take_due_request(now + Duration::from_millis(150))
        .expect("latest request becomes due");
    assert_eq!(request.query, "AAPL");
    assert_eq!(request.filters.screen, Some(Screen::Portfolio));

    let rows = SearchIndex::from_snapshot(&snapshot(snapshot_value()))
        .search(&request.query, &request.filters, 100)
        .unwrap();
    state.apply_results(request.request_id - 1, rows.clone());
    assert!(
        state.results().is_empty(),
        "superseded results must be ignored"
    );
    state.apply_results(request.request_id, rows);
    assert_eq!(state.results()[0].entity_id, "AAPL");
    assert_eq!(
        state.open_selected().expect("selected route").screen,
        Screen::Portfolio
    );
}

#[test]
fn search_filters_persist_per_screen_and_selection_is_bounded() {
    let mut state = SearchState::default();
    let portfolio = SearchFilters {
        screen: Some(Screen::Portfolio),
        kinds: vec![SearchKind::Stock],
        source: Some("fixture".to_owned()),
    };
    let timeline = SearchFilters {
        screen: Some(Screen::Timeline),
        kinds: vec![SearchKind::Event],
        source: None,
    };
    state.set_filters(Screen::Portfolio, portfolio.clone());
    state.set_filters(Screen::Timeline, timeline.clone());
    assert_eq!(state.filters(Screen::Portfolio), &portfolio);
    assert_eq!(state.filters(Screen::Timeline), &timeline);

    let now = Instant::now();
    state.set_active_screen(Screen::Timeline);
    state.update_query("AAPL".to_owned(), now);
    let request = state
        .take_due_request(now + SEARCH_DEBOUNCE)
        .expect("request");
    assert_eq!(request.filters, timeline);
    let rows = SearchIndex::from_snapshot(&snapshot(snapshot_value()))
        .search(&request.query, &request.filters, 100)
        .unwrap();
    state.apply_results(request.request_id, rows);
    state.move_selection(false);
    assert_eq!(state.selected_index(), 0);
    state.move_selection(true);
    assert_eq!(state.selected_index(), 0);
}

#[test]
fn active_search_renders_query_type_time_source_and_open_help() {
    let value = snapshot_value();
    let envelope: Envelope = serde_json::from_value(json!({
        "schema_version": 1,
        "message_id": "server:1",
        "sequence": 1,
        "state_version": 0,
        "timestamp_utc": "2026-08-03T00:00:00Z",
        "message_type": "snapshot",
        "payload": {"snapshot": value},
    }))
    .expect("snapshot envelope");
    let mut state = AppState::controller();
    state.reduce(envelope).unwrap();
    state.handle(InputEvent::Char('/'));
    for character in "AAPL".chars() {
        state.handle(InputEvent::Char(character));
    }
    let request_id = issued_search_request_id(&state.handle(InputEvent::Tick(SEARCH_DEBOUNCE)));
    state
        .reduce(search_results_envelope(
            2,
            0,
            request_id,
            vec![stock_search_result()],
        ))
        .unwrap();

    let backend = TestBackend::new(120, 36);
    let mut terminal = Terminal::new(backend).unwrap();
    terminal
        .draw(|frame| vesper_ratatui_console::ui::render(frame, &state))
        .unwrap();
    let text = terminal
        .backend()
        .buffer()
        .content
        .iter()
        .map(|cell| cell.symbol())
        .collect::<String>();
    for expected in [
        "SEARCH ALL V20",
        "Query: AAPL",
        "[STOCK]",
        "AAPL",
        "fixture",
        "2026-08-02 20:00:00 EDT",
        "Enter Open",
        "Esc Close",
    ] {
        assert!(text.contains(expected), "missing {expected:?}");
    }
    assert!(!text.contains("2026-08-03T00:00:00Z"));

    state.handle(InputEvent::Enter);
    terminal
        .draw(|frame| vesper_ratatui_console::ui::render(frame, &state))
        .unwrap();
    let detail = terminal
        .backend()
        .buffer()
        .content
        .iter()
        .map(|cell| cell.symbol())
        .collect::<String>();
    for expected in [
        "SEARCH RESULT DETAIL",
        "[STOCK]",
        "ENTITY AAPL",
        "Private/Shared",
        "stored by the controller",
        "Esc Back",
        "2026-08-02 20:00:00 EDT",
    ] {
        assert!(detail.contains(expected), "missing {expected:?}");
    }
}

#[test]
fn filter_editor_rejects_multiple_sources_and_persists_one_source_per_screen() {
    let error = parse_filter_expression(
        Screen::Portfolio,
        "scope:screen kind:stock source:fixture,broker-readback",
    )
    .expect_err("multiple sources must be rejected");
    assert_eq!(error.message(), "Use one source filter at a time.");

    let filters =
        parse_filter_expression(Screen::Portfolio, "scope:screen kind:stock source:fixture")
            .expect("valid one-source filter");
    assert_eq!(filters.screen, Some(Screen::Portfolio));
    assert_eq!(filters.kinds, vec![SearchKind::Stock]);
    assert_eq!(filters.source.as_deref(), Some("fixture"));
    assert_eq!(
        format_filter_expression(&filters),
        "scope:screen kind:stock source:fixture"
    );

    let mut state = AppState::controller();
    state.handle(InputEvent::Char('2'));
    state.handle(InputEvent::Char('f'));
    for _ in 0.."scope:all".chars().count() {
        state.handle(InputEvent::Backspace);
    }
    for character in "scope:screen kind:stock source:fixture".chars() {
        state.handle(InputEvent::Char(character));
    }
    assert!(state.handle(InputEvent::Enter).is_empty());
    assert_eq!(
        state.search_state().filters(Screen::Portfolio),
        &SearchFilters {
            screen: Some(Screen::Portfolio),
            kinds: vec![SearchKind::Stock],
            source: Some("fixture".to_owned()),
        }
    );

    state.handle(InputEvent::Char('6'));
    state.handle(InputEvent::Char('f'));
    assert_eq!(state.filter_input(), "scope:all");
    state.handle(InputEvent::Escape);
    state.handle(InputEvent::Char('2'));
    state.handle(InputEvent::Char('f'));
    assert_eq!(
        state.filter_input(),
        "scope:screen kind:stock source:fixture"
    );
}

#[test]
fn quoted_source_filters_support_built_in_names_and_round_trip_escapes() {
    let built_in = parse_filter_expression(
        Screen::Agents,
        r#"scope:screen source:"native agent profile catalog""#,
    )
    .expect("quoted built-in source");
    assert_eq!(
        built_in.source.as_deref(),
        Some("native agent profile catalog")
    );

    let filters = SearchFilters {
        screen: Some(Screen::Agents),
        kinds: vec![SearchKind::Agent],
        source: Some(r#"native agent "profile" catalog\windows"#.to_owned()),
    };
    let expression = format_filter_expression(&filters);
    assert_eq!(
        expression,
        r#"scope:screen kind:agent source:"native agent \"profile\" catalog\\windows""#
    );
    assert_eq!(
        parse_filter_expression(Screen::Agents, &expression).expect("formatted filter round trip"),
        filters
    );

    let unclosed = parse_filter_expression(Screen::Agents, r#"source:"native platform"#)
        .expect_err("unclosed quote must be rejected");
    assert_eq!(unclosed.message(), "Unclosed quote in filter.");

    let invalid = parse_filter_expression(Screen::Agents, r#"source:"native\q""#)
        .expect_err("invalid quoted escape must be rejected");
    assert_eq!(invalid.message(), "Invalid escape in filter.");
}

#[test]
fn invalid_filter_stays_open_and_renders_a_plain_error() {
    let mut state = AppState::controller();
    state.handle(InputEvent::Char('f'));
    for _ in 0.."scope:all".chars().count() {
        state.handle(InputEvent::Backspace);
    }
    for character in "kind:banana".chars() {
        state.handle(InputEvent::Char(character));
    }
    assert!(state.handle(InputEvent::Enter).is_empty());
    assert_eq!(state.mode, vesper_ratatui_console::state::LocalMode::Filter);
    assert_eq!(state.filter_error(), Some("Unknown kind: banana"));
}

#[test]
fn private_or_shared_note_editor_creates_a_governed_note_command() {
    let envelope: Envelope = serde_json::from_value(json!({
        "schema_version": 1,
        "message_id": "server:1",
        "sequence": 1,
        "state_version": 0,
        "timestamp_utc": "2026-08-03T00:00:00Z",
        "message_type": "snapshot",
        "payload": {"snapshot": note_enabled_snapshot_value()},
    }))
    .unwrap();
    let mut state = AppState::controller();
    state.reduce(envelope).unwrap();
    state.handle(InputEvent::Char('/'));
    for character in "AAPL".chars() {
        state.handle(InputEvent::Char(character));
    }
    let request_id = issued_search_request_id(&state.handle(InputEvent::Tick(SEARCH_DEBOUNCE)));
    state
        .reduce(search_results_envelope(
            2,
            0,
            request_id,
            vec![stock_search_result()],
        ))
        .unwrap();
    state.handle(InputEvent::Enter);
    state.handle(InputEvent::Char('n'));
    assert_eq!(state.note_visibility(), NoteVisibility::Private);
    state.handle(InputEvent::Right);
    assert_eq!(state.note_visibility(), NoteVisibility::Shared);
    for character in "Watch earnings risk".chars() {
        state.handle(InputEvent::Char(character));
    }
    let actions = state.handle(InputEvent::Enter);
    let [ClientAction::Command(command)] = actions.as_slice() else {
        panic!("one governed note command expected")
    };
    let CommandPayload::NoteAdd(note) = &command.payload else {
        panic!("note payload expected")
    };
    assert_eq!(
        note.target_type,
        vesper_ratatui_console::contract::NoteTargetType::Stock
    );
    assert_eq!(note.target_id.as_str(), "AAPL");
    assert_eq!(note.body.as_str(), "Watch earnings risk");
    assert_eq!(
        note.visibility,
        vesper_ratatui_console::contract::NoteVisibility::Shared
    );
    assert!(command.confirmation.is_none());
}

#[test]
fn search_mouse_click_opens_the_same_result_as_keyboard_enter() {
    let envelope: Envelope = serde_json::from_value(json!({
        "schema_version": 1,
        "message_id": "server:1",
        "sequence": 1,
        "state_version": 0,
        "timestamp_utc": "2026-08-03T00:00:00Z",
        "message_type": "snapshot",
        "payload": {"snapshot": snapshot_value()},
    }))
    .unwrap();
    let mut state = AppState::controller();
    state.reduce(envelope).unwrap();
    state.handle(InputEvent::Char('/'));
    for character in "AAPL".chars() {
        state.handle(InputEvent::Char(character));
    }
    let request_id = issued_search_request_id(&state.handle(InputEvent::Tick(SEARCH_DEBOUNCE)));
    state
        .reduce(search_results_envelope(
            2,
            0,
            request_id,
            vec![stock_search_result()],
        ))
        .unwrap();

    let area = Rect::new(0, 0, 120, 36);
    let body = shell_layout(area, state.display_mode()).body;
    let click = MouseEvent {
        kind: MouseEventKind::Down(MouseButton::Left),
        column: body.x + 2,
        row: body.y + 3,
        modifiers: KeyModifiers::NONE,
    };
    let input = mouse_to_input(click, area, &state).expect("search row click");
    assert_eq!(input, InputEvent::OpenSearchResult(0));
    state.handle(input);
    assert_eq!(state.screen, Screen::Portfolio);
    assert!(state.search_detail().is_some());
}

#[test]
fn browse_mouse_click_opens_the_clicked_portfolio_row_not_the_prior_selection() {
    let mut value = snapshot_value();
    let mut second = value["portfolio"]["rows"][0].clone();
    second["symbol"] = json!("MSFT");
    value["portfolio"]["rows"]
        .as_array_mut()
        .expect("portfolio rows")
        .push(second);

    let mut state = AppState::controller();
    state.reduce(snapshot_envelope(1, 0, value)).unwrap();
    state.handle(InputEvent::Char('2'));
    state.handle(InputEvent::Up);
    assert_eq!(state.screen_state().selected_id.as_deref(), Some("AAPL"));

    let area = Rect::new(0, 0, 120, 36);
    let body = shell_layout(area, state.display_mode()).body;
    let second_row = MouseEvent {
        kind: MouseEventKind::Down(MouseButton::Left),
        column: body.x + 2,
        row: body.y + 3,
        modifiers: KeyModifiers::NONE,
    };

    let input = mouse_to_input(second_row, area, &state).expect("second portfolio row click");
    assert_eq!(input, InputEvent::OpenBrowseRow { panel: 0, index: 1 });
    state.handle(input);
    assert_eq!(state.screen_state().selected_id.as_deref(), Some("MSFT"));
    assert_eq!(state.screen_state().selected_kind, Some(DetailKind::Stock));
    assert_eq!(state.mode, LocalMode::Open);
}

#[test]
fn browse_mouse_click_opens_the_clicked_impact_holding() {
    let mut value = snapshot_value();
    let mut second = value["impact"]["holdings"][0].clone();
    second["symbol"] = json!("MSFT");
    value["impact"]["holdings"]
        .as_array_mut()
        .expect("impact holdings")
        .push(second);

    let mut state = AppState::controller();
    state.reduce(snapshot_envelope(1, 0, value)).unwrap();
    state.handle(InputEvent::Up);
    assert_eq!(state.screen_state().selected_id.as_deref(), Some("AAPL"));

    let area = Rect::new(0, 0, 140, 40);
    let body = shell_layout(area, state.display_mode()).body;
    let second_row = MouseEvent {
        kind: MouseEventKind::Down(MouseButton::Left),
        column: body.x + 2,
        row: body.y + 3,
        modifiers: KeyModifiers::NONE,
    };

    let input = mouse_to_input(second_row, area, &state).expect("second impact holding click");
    assert_eq!(input, InputEvent::OpenBrowseRow { panel: 0, index: 1 });
    state.handle(input);
    assert_eq!(state.screen, Screen::Portfolio);
    assert_eq!(state.screen_state().selected_id.as_deref(), Some("MSFT"));
    assert_eq!(state.mode, LocalMode::Open);
}

#[test]
fn browse_mouse_click_switches_panel_and_opens_the_entity_under_the_pointer() {
    let mut state = AppState::controller();
    state
        .reduce(snapshot_envelope(1, 0, snapshot_value()))
        .unwrap();
    state.handle(InputEvent::Char('8'));
    state.handle(InputEvent::Up);
    assert_eq!(
        state.screen_state().selected_id.as_deref(),
        Some("source:massive")
    );

    let area = Rect::new(0, 0, 140, 40);
    let body = shell_layout(area, state.display_mode()).body;
    let evidence_row = MouseEvent {
        kind: MouseEventKind::Down(MouseButton::Left),
        column: body.x + 100,
        row: body.y + 1,
        modifiers: KeyModifiers::NONE,
    };

    let input = mouse_to_input(evidence_row, area, &state).expect("evidence row click");
    assert_eq!(input, InputEvent::OpenBrowseRow { panel: 1, index: 0 });
    state.handle(input);
    assert_eq!(
        state.screen_state().selected_id.as_deref(),
        Some("evidence:1")
    );
    assert_eq!(
        state.screen_state().selected_kind,
        Some(DetailKind::Evidence)
    );
    assert_eq!(state.mode, LocalMode::Open);
}

#[test]
fn browse_mouse_click_opens_the_clicked_agent_card() {
    let mut value = snapshot_value();
    let mut second = value["agents"]["rows"][0].clone();
    second["work_id"] = json!("work:2");
    second["title"] = json!("Second running task");
    value["agents"]["rows"]
        .as_array_mut()
        .expect("agent rows")
        .push(second);

    let mut state = AppState::controller();
    state.reduce(snapshot_envelope(1, 0, value)).unwrap();
    state.handle(InputEvent::Char('4'));
    state.handle(InputEvent::Right);
    state.handle(InputEvent::Up);
    assert_eq!(state.screen_state().selected_id.as_deref(), Some("work:1"));

    let area = Rect::new(0, 0, 140, 50);
    let body = shell_layout(area, state.display_mode()).body;
    let second_card = MouseEvent {
        kind: MouseEventKind::Down(MouseButton::Left),
        column: body.x + 40,
        row: body.y + 5,
        modifiers: KeyModifiers::NONE,
    };

    let input = mouse_to_input(second_card, area, &state).expect("second agent card click");
    assert_eq!(input, InputEvent::OpenBrowseRow { panel: 1, index: 1 });
    state.handle(input);
    assert_eq!(state.screen_state().selected_id.as_deref(), Some("work:2"));
    assert_eq!(state.mode, LocalMode::Open);
}

#[test]
fn browse_mouse_click_opens_the_clicked_model_candidate() {
    let mut value = snapshot_value();
    let mut second = value["models"]["candidates"][0].clone();
    second["candidate_id"] = json!("candidate:2");
    value["models"]["candidates"]
        .as_array_mut()
        .expect("model candidates")
        .push(second);

    let mut state = AppState::controller();
    state.reduce(snapshot_envelope(1, 0, value)).unwrap();
    state.handle(InputEvent::Char('5'));
    state.handle(InputEvent::Right);
    state.handle(InputEvent::Up);
    assert_eq!(
        state.screen_state().selected_id.as_deref(),
        Some("candidate:1")
    );

    let area = Rect::new(0, 0, 140, 40);
    let body = shell_layout(area, state.display_mode()).body;
    let second_candidate = MouseEvent {
        kind: MouseEventKind::Down(MouseButton::Left),
        column: body.x + 50,
        row: body.y + 4,
        modifiers: KeyModifiers::NONE,
    };

    let input =
        mouse_to_input(second_candidate, area, &state).expect("second model candidate click");
    assert_eq!(input, InputEvent::OpenBrowseRow { panel: 1, index: 1 });
    state.handle(input);
    assert_eq!(
        state.screen_state().selected_id.as_deref(),
        Some("candidate:2")
    );
    assert_eq!(state.mode, LocalMode::Open);
}

#[test]
fn browse_mouse_click_opens_the_clicked_timeline_event() {
    let mut value = snapshot_value();
    let mut second = value["timeline"]["rows"][0].clone();
    second["event_id"] = json!("event:2");
    second["summary"] = json!("Second event");
    value["timeline"]["rows"]
        .as_array_mut()
        .expect("timeline rows")
        .push(second);

    let mut state = AppState::controller();
    state.reduce(snapshot_envelope(1, 0, value)).unwrap();
    state.handle(InputEvent::Char('6'));
    state.handle(InputEvent::Up);
    assert_eq!(state.screen_state().selected_id.as_deref(), Some("event:1"));

    let area = Rect::new(0, 0, 140, 40);
    let body = shell_layout(area, state.display_mode()).body;
    let second_event = MouseEvent {
        kind: MouseEventKind::Down(MouseButton::Left),
        column: body.x + 3,
        row: body.y + 6,
        modifiers: KeyModifiers::NONE,
    };

    let input = mouse_to_input(second_event, area, &state).expect("second timeline event click");
    assert_eq!(input, InputEvent::OpenBrowseRow { panel: 0, index: 1 });
    state.handle(input);
    assert_eq!(state.screen_state().selected_id.as_deref(), Some("event:2"));
    assert_eq!(state.mode, LocalMode::Open);
}

#[test]
fn browse_mouse_click_opens_the_clicked_order() {
    let mut value = snapshot_value();
    let mut second = value["orders"]["rows"][0].clone();
    second["order_id"] = json!("order:2");
    second["submitted_at_utc"] = json!("2026-08-02T00:00:00Z");
    second["fills"][0]["fill_id"] = json!("fill:2");
    value["orders"]["rows"]
        .as_array_mut()
        .expect("order rows")
        .push(second);

    let mut state = AppState::controller();
    state.reduce(snapshot_envelope(1, 0, value)).unwrap();
    state.handle(InputEvent::Char('3'));
    state.handle(InputEvent::Up);
    assert_eq!(state.screen_state().selected_id.as_deref(), Some("order:1"));

    let area = Rect::new(0, 0, 140, 40);
    let body = shell_layout(area, state.display_mode()).body;
    let second_order = MouseEvent {
        kind: MouseEventKind::Down(MouseButton::Left),
        column: body.x + 3,
        row: body.y + 5,
        modifiers: KeyModifiers::NONE,
    };

    let input = mouse_to_input(second_order, area, &state).expect("second order click");
    assert_eq!(input, InputEvent::OpenBrowseRow { panel: 0, index: 2 });
    state.handle(input);
    assert_eq!(state.screen_state().selected_id.as_deref(), Some("order:2"));
    assert_eq!(state.mode, LocalMode::Open);
}

#[test]
fn search_detail_scroll_reaches_wrapped_tail_in_a_small_viewport() {
    let mut value = snapshot_value();
    value["models"]["opinions"][0]["regime"] =
        json!(format!("{}tailmarker", "wrapped model opinion ".repeat(8)));
    let envelope = snapshot_envelope(1, 0, value);
    let mut state = AppState::controller();
    state.reduce(envelope).unwrap();
    state.set_terminal_area(Rect::new(0, 0, 30, 24));
    state.handle(InputEvent::Char('/'));
    for character in "tailmarker".chars() {
        state.handle(InputEvent::Char(character));
    }
    let request_id = issued_search_request_id(&state.handle(InputEvent::Tick(SEARCH_DEBOUNCE)));
    state
        .reduce(search_results_envelope(
            2,
            0,
            request_id,
            vec![json!({
                "kind": "model",
                "record_type": "model-opinion-row",
                "record_id": "model:active",
                "label": "model:active",
                "summary": format!("{}tailmarker", "wrapped model opinion ".repeat(8)),
                "occurred_at_utc": "2026-08-03T00:00:00Z",
                "source": "fixture",
                "screen": "models-regime",
                "context_only": null,
            })],
        ))
        .unwrap();
    state.handle(InputEvent::Enter);

    for _ in 0..100 {
        state.handle(InputEvent::Down);
    }

    assert!(state.screen_state().scroll_offset > 9);
    assert!(rendered_text(&state, 30, 24).contains("Esc Back"));
}

#[test]
fn mouse_hit_map_covers_filter_note_detail_and_back_controls() {
    fn left_click(column: u16, row: u16) -> MouseEvent {
        MouseEvent {
            kind: MouseEventKind::Down(MouseButton::Left),
            column,
            row,
            modifiers: KeyModifiers::NONE,
        }
    }

    let area = Rect::new(0, 0, 120, 36);
    let mut state = AppState::controller();
    state
        .reduce(snapshot_envelope(1, 0, note_enabled_snapshot_value()))
        .unwrap();
    state.handle(InputEvent::Char('2'));
    state.handle(InputEvent::Up);
    let layout = shell_layout(area, state.display_mode());

    let direct = mouse_to_input(
        left_click(layout.body.x + 2, layout.body.y + 2),
        area,
        &state,
    );
    assert_eq!(
        direct,
        Some(InputEvent::OpenBrowseRow { panel: 0, index: 0 })
    );
    state.handle(direct.unwrap());
    assert_eq!(state.mode, LocalMode::Open);

    let back = mouse_to_input(
        left_click(layout.footer.x + 2, layout.footer.y + 1),
        area,
        &state,
    );
    assert_eq!(back, Some(InputEvent::Escape));
    state.handle(back.unwrap());

    let filter = mouse_to_input(
        left_click(
            layout.footer.x + layout.footer.width.saturating_sub(3),
            layout.footer.y + 1,
        ),
        area,
        &state,
    );
    assert_eq!(filter, Some(InputEvent::Char('f')));
    state.handle(filter.unwrap());
    assert_eq!(state.mode, LocalMode::Filter);
    assert_eq!(
        mouse_to_input(
            left_click(layout.footer.x + 2, layout.footer.y + 1),
            area,
            &state,
        ),
        Some(InputEvent::Enter)
    );
    assert_eq!(
        mouse_to_input(
            left_click(
                layout.footer.x + layout.footer.width.saturating_sub(3),
                layout.footer.y + 1,
            ),
            area,
            &state,
        ),
        Some(InputEvent::Escape)
    );

    state.handle(InputEvent::Escape);
    state.handle(InputEvent::Char('o'));
    state.handle(InputEvent::Char('n'));
    assert_eq!(state.mode, LocalMode::NoteEditor);
    assert_eq!(
        mouse_to_input(
            left_click(
                layout.body.x + layout.body.width.saturating_sub(3),
                layout.body.y + 2,
            ),
            area,
            &state,
        ),
        Some(InputEvent::Right)
    );
    assert_eq!(
        mouse_to_input(
            left_click(layout.body.x + 2, layout.body.y + 2),
            area,
            &state,
        ),
        Some(InputEvent::Left)
    );
    assert_eq!(
        mouse_to_input(
            left_click(layout.footer.x + 2, layout.footer.y + 1),
            area,
            &state,
        ),
        Some(InputEvent::Enter)
    );
    assert_eq!(
        mouse_to_input(
            left_click(
                layout.footer.x + layout.footer.width.saturating_sub(3),
                layout.footer.y + 1,
            ),
            area,
            &state,
        ),
        Some(InputEvent::Escape)
    );
}
