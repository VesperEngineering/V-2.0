use serde_json::{Value, json};
use std::time::Duration;

use ratatui::Terminal;
use ratatui::backend::TestBackend;
use ratatui::layout::Rect;
use vesper_ratatui_console::contract::Envelope;
use vesper_ratatui_console::input::InputEvent;
use vesper_ratatui_console::screens::DetailKind;
use vesper_ratatui_console::search::SearchStatus;
use vesper_ratatui_console::state::{
    AccessState, AppState, AuthFeedback, ClientAction, LocalMode, ReduceOutcome, Screen,
};

fn envelope(sequence: u64, state_version: u64, message_type: &str, payload: Value) -> Envelope {
    serde_json::from_value(json!({
        "schema_version": 1,
        "message_id": format!("server:{sequence}"),
        "sequence": sequence,
        "state_version": state_version,
        "timestamp_utc": "2026-08-03T00:00:00Z",
        "message_type": message_type,
        "payload": payload,
    }))
    .expect("valid test envelope")
}

fn snapshot(sequence: u64, state_version: u64, regime: &str) -> Envelope {
    let mut snapshot: Value = serde_json::from_slice(include_bytes!(
        "../../contracts/v1/console_snapshot_empty_command_specs.json"
    ))
    .expect("valid shared console snapshot");
    snapshot["shell"]["state_version"] = json!(state_version);
    snapshot["shell"]["header"]["regime_label"] = json!(regime);
    envelope(
        sequence,
        state_version,
        "snapshot",
        json!({"snapshot": snapshot}),
    )
}

fn snapshot_with_qwen_state(
    sequence: u64,
    state_version: u64,
    regime: &str,
    qwen_state: &str,
) -> Envelope {
    let mut value = serde_json::to_value(snapshot(sequence, state_version, regime)).unwrap();
    value["payload"]["snapshot"]["shell"]["header"]["qwen_state"] = json!(qwen_state);
    serde_json::from_value(value).unwrap()
}

fn stale_cache_snapshot(sequence: u64, state_version: u64, regime: &str) -> Envelope {
    let mut value = serde_json::to_value(snapshot_with_qwen_state(
        sequence,
        state_version,
        regime,
        "STALE CACHE",
    ))
    .unwrap();
    value["payload"]["snapshot"]["command_specs"] = json!([]);
    for capability in value["payload"]["snapshot"]["shell"]["capabilities"]
        .as_array_mut()
        .expect("capability array")
    {
        capability["state"] = json!("disabled");
        capability["reason"] = json!("Cached state cannot authorize actions.");
    }
    serde_json::from_value(value).unwrap()
}

fn snapshot_with_note_control(sequence: u64, state_version: u64, regime: &str) -> Envelope {
    let mut value = serde_json::to_value(snapshot(sequence, state_version, regime)).unwrap();
    value["payload"]["snapshot"]["command_specs"] = json!([{
        "command_type": "note.add",
        "payload_model": "NoteAddPayload",
        "capability_id": "note.add",
        "reason_rule": "forbidden",
        "confirmation_level": "none"
    }]);
    value["payload"]["snapshot"]["shell"]["capabilities"] = json!([{
        "capability_id": "note.add",
        "state": "enabled",
        "reason": null
    }]);
    serde_json::from_value(value).unwrap()
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

fn server_hello(sequence: u64, requires_setup: bool) -> Envelope {
    envelope(
        sequence,
        0,
        "server-hello",
        json!({
            "server_version": "0.1.0",
            "requires_setup": requires_setup
        }),
    )
}

fn auth_result(sequence: u64, success: bool, access_state: &str) -> Envelope {
    envelope(
        sequence,
        0,
        "auth-result",
        json!({
            "success": success,
            "access_state": access_state,
            "reason": if success { Value::Null } else { json!("Unlock failed.") }
        }),
    )
}

fn lease_result(sequence: u64, status: &str) -> Envelope {
    envelope(
        sequence,
        0,
        "lease-result",
        json!({
            "status": status,
            "reason": if status == "lease-held" {
                json!("Another authenticated session has control.")
            } else {
                Value::Null
            }
        }),
    )
}

fn lock_result(sequence: u64, state_version: u64) -> Envelope {
    envelope(
        sequence,
        state_version,
        "lock-result",
        json!({ "locked": true }),
    )
}

fn pong(sequence: u64, state_version: u64, nonce: &str) -> Envelope {
    envelope(sequence, state_version, "pong", json!({ "nonce": nonce }))
}

fn event(sequence: u64, state_version: u64) -> Envelope {
    let snapshot: Value = serde_json::from_slice(include_bytes!(
        "../../contracts/v1/console_snapshot_empty_command_specs.json"
    ))
    .expect("valid shared console snapshot");
    let screen_meta = |name: &str| {
        json!({
            "freshness": snapshot[name]["freshness"].clone(),
            "as_of_utc": snapshot[name]["as_of_utc"].clone(),
            "source": snapshot[name]["source"].clone(),
            "error": snapshot[name]["error"].clone(),
        })
    };
    envelope(
        sequence,
        state_version,
        "event",
        json!({
            "entity_type": "alert-row",
            "entity_id": "alert:1",
            "operation": "remove",
            "entity": null,
            "targets": ["shell.alerts"],
            "presentation": {
                "generated_at_utc": snapshot["shell"]["generated_at_utc"].clone(),
                "header": snapshot["shell"]["header"].clone(),
                "control_version": snapshot["control_version"].clone(),
                "control_hash": snapshot["control_hash"].clone(),
                "window_omissions": snapshot["window_omissions"].clone(),
                "impact": screen_meta("impact"),
                "portfolio": screen_meta("portfolio"),
                "orders": screen_meta("orders"),
                "agents": screen_meta("agents"),
                "models": screen_meta("models"),
                "timeline": screen_meta("timeline"),
                "risk": screen_meta("risk"),
                "data": screen_meta("data"),
                "memory": screen_meta("memory"),
                "system": screen_meta("system"),
                "portfolio_rank_source": snapshot["portfolio"]["rank_source"].clone(),
                "timeline_hidden_event_count": snapshot["timeline"]["hidden_event_count"].clone(),
                "model_active_model_id": snapshot["models"]["active_model_id"].clone(),
                "model_rollback_model_id": snapshot["models"]["rollback_model_id"].clone(),
                "model_approved_family": snapshot["models"]["approved_family"].clone(),
                "model_approved_strategy": snapshot["models"]["approved_strategy"].clone(),
                "model_approved_feature_set_id": snapshot["models"]["approved_feature_set_id"].clone(),
                "model_final_regime": snapshot["models"]["final_regime"].clone(),
                "model_final_regime_confidence": snapshot["models"]["final_regime_confidence"].clone(),
                "model_regime_state": snapshot["models"]["regime_state"].clone(),
                "model_automatic_changes_blocked": snapshot["models"]["automatic_changes_blocked"].clone(),
                "model_block_reason": snapshot["models"]["block_reason"].clone(),
                "model_gates": snapshot["models"]["gates"].clone(),
                "risk_blocked_actions": snapshot["risk"]["blocked_actions"].clone(),
                "risk_circuit_breaker": snapshot["risk"]["circuit_breaker"].clone(),
                "system_qwen": snapshot["system"]["qwen"].clone(),
                "system_health": snapshot["system"]["health"].clone(),
            }
        }),
    )
}

fn search_results(
    sequence: u64,
    envelope_state_version: u64,
    request_id: u64,
    indexed_state_version: u64,
    results: Vec<Value>,
    error: Option<&str>,
) -> Envelope {
    envelope(
        sequence,
        envelope_state_version,
        "search-results",
        json!({
            "request_id": request_id,
            "indexed_state_version": indexed_state_version,
            "results": results,
            "error": error,
        }),
    )
}

fn stock_search_result() -> Value {
    json!({
        "kind": "stock",
        "record_type": "portfolio-row",
        "record_id": "AAPL",
        "label": "AAPL",
        "summary": "Current holding",
        "occurred_at_utc": null,
        "source": "fixture",
        "screen": "portfolio",
        "context_only": null,
    })
}

fn issue_search(state: &mut AppState, query: &str) -> u64 {
    state.handle(InputEvent::Char('/'));
    for character in query.chars() {
        state.handle(InputEvent::Char(character));
    }
    let actions = state.handle(InputEvent::Tick(Duration::from_millis(100)));
    let [ClientAction::Search(payload)] = actions.as_slice() else {
        panic!("expected one search action, got {actions:?}");
    };
    payload.request_id.get()
}

#[test]
fn ordered_events_reduce_into_the_current_snapshot_after_non_event_messages() {
    let mut state = AppState::controller();
    assert_eq!(
        state.reduce(snapshot(1, 1, "Before")),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(
        state.reduce(pong(2, 1, "keepalive")),
        Ok(ReduceOutcome::Ignored)
    );

    assert_eq!(state.reduce(event(3, 2)), Ok(ReduceOutcome::Changed));
    let current = state
        .snapshot
        .as_ref()
        .expect("event keeps a live snapshot");
    assert_eq!(current.shell.state_version, 2);
    assert_eq!(current.shell.header.regime_label.as_str(), "Unavailable");
    assert!(!state.awaiting_snapshot());
}

#[test]
fn gapped_and_stale_events_both_request_a_full_snapshot() {
    let mut state = AppState::controller();
    assert_eq!(
        state.reduce(snapshot(1, 2, "Current")),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(
        state.reduce(event(2, 1)),
        Ok(ReduceOutcome::RequestSnapshot)
    );
    assert!(state.snapshot.is_none());

    let mut state = AppState::controller();
    assert_eq!(
        state.reduce(snapshot(1, 2, "Current")),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(
        state.reduce(event(3, 3)),
        Ok(ReduceOutcome::RequestSnapshot)
    );
    assert!(state.snapshot.is_none());
}

#[test]
fn global_search_debounces_for_100ms_and_emits_exactly_one_action() {
    let mut state = AppState::controller();
    state.reduce(snapshot(1, 1, "Current")).unwrap();

    state.handle(InputEvent::Char('/'));
    assert_eq!(state.mode, LocalMode::Search);
    for character in "AAPL".chars() {
        state.handle(InputEvent::Char(character));
    }
    assert!(
        state
            .handle(InputEvent::Tick(Duration::from_millis(99)))
            .is_empty()
    );
    let actions = state.handle(InputEvent::Tick(Duration::from_millis(1)));
    assert!(matches!(actions.as_slice(), [ClientAction::Search(_)]));
    assert!(
        state
            .handle(InputEvent::Tick(Duration::from_millis(100)))
            .is_empty()
    );
}

#[test]
fn current_search_result_applies_and_opens_the_selected_owning_entity() {
    let mut state = AppState::controller();
    state.reduce(snapshot(1, 1, "Current")).unwrap();
    let request_id = issue_search(&mut state, "AAPL");

    assert_eq!(
        state.reduce(search_results(
            2,
            1,
            request_id,
            1,
            vec![stock_search_result()],
            None,
        )),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(state.search_state().status(), SearchStatus::Fresh);
    assert_eq!(state.search_state().results()[0].entity_id, "AAPL");

    assert!(state.handle(InputEvent::Enter).is_empty());
    assert_eq!(state.mode, LocalMode::Open);
    assert_eq!(state.screen, Screen::Portfolio);
    assert_eq!(state.screen_state().selected_id.as_deref(), Some("AAPL"));
    assert!(state.screen_state().detail_open);
}

#[test]
fn partial_search_result_reports_incomplete() {
    let mut state = AppState::controller();
    state.reduce(snapshot(1, 1, "Current")).unwrap();
    let request_id = issue_search(&mut state, "AAPL");

    assert_eq!(
        state.reduce(search_results(
            2,
            1,
            request_id,
            1,
            vec![stock_search_result()],
            Some("Notes unavailable."),
        )),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(state.search_state().status(), SearchStatus::Incomplete);
    assert_eq!(state.search_state().results().len(), 1);
    assert_eq!(
        state.search_state().server_error(),
        Some("Notes unavailable.")
    );
}

#[test]
fn failed_search_without_rows_reports_unavailable() {
    let mut state = AppState::controller();
    state.reduce(snapshot(1, 1, "Current")).unwrap();
    let request_id = issue_search(&mut state, "AAPL");

    assert_eq!(
        state.reduce(search_results(
            2,
            1,
            request_id,
            1,
            vec![],
            Some("Search unavailable."),
        )),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(state.search_state().status(), SearchStatus::Unavailable);
    assert!(state.search_state().results().is_empty());
    assert_eq!(
        state.search_state().server_error(),
        Some("Search unavailable.")
    );
}

#[test]
fn unknown_search_request_id_fails_closed() {
    let mut state = AppState::controller();
    state.reduce(snapshot(1, 1, "Current")).unwrap();

    let error = state
        .reduce(search_results(2, 1, 99, 1, vec![], None))
        .expect_err("unknown request ID must fail closed");

    assert_eq!(error.code, "search-request");
    assert_eq!(state.access, AccessState::ProtocolLockout);
}

#[test]
fn superseded_search_response_is_ignored() {
    let mut state = AppState::controller();
    state.reduce(snapshot(1, 1, "Current")).unwrap();
    let first_request_id = issue_search(&mut state, "AAP");
    state.handle(InputEvent::Char('L'));
    let actions = state.handle(InputEvent::Tick(Duration::from_millis(100)));
    let [ClientAction::Search(second)] = actions.as_slice() else {
        panic!("expected replacement search action, got {actions:?}");
    };
    assert!(second.request_id.get() > first_request_id);

    assert_eq!(
        state.reduce(search_results(
            2,
            1,
            first_request_id,
            1,
            vec![stock_search_result()],
            None,
        )),
        Ok(ReduceOutcome::Ignored)
    );
    assert!(state.search_state().results().is_empty());
    assert_eq!(state.search_state().status(), SearchStatus::Loading);
}

#[test]
fn search_response_for_older_index_requeues_the_query() {
    let mut state = AppState::controller();
    state.reduce(snapshot(1, 2, "Current")).unwrap();
    let request_id = issue_search(&mut state, "AAPL");

    assert_eq!(
        state.reduce(search_results(2, 1, request_id, 1, vec![], None)),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(state.search_state().status(), SearchStatus::StaleRefreshing);
    let actions = state.handle(InputEvent::Tick(Duration::from_millis(100)));
    let [ClientAction::Search(retry)] = actions.as_slice() else {
        panic!("expected refreshed search action, got {actions:?}");
    };
    assert!(retry.request_id.get() > request_id);
}

#[test]
fn search_response_for_future_index_requests_snapshot() {
    let mut state = AppState::controller();
    state.reduce(snapshot(1, 1, "Current")).unwrap();
    let request_id = issue_search(&mut state, "AAPL");

    assert_eq!(
        state.reduce(search_results(2, 2, request_id, 2, vec![], None)),
        Ok(ReduceOutcome::RequestSnapshot)
    );
    assert!(state.awaiting_snapshot());
    assert!(state.snapshot.is_none());
    assert_eq!(state.search_state().status(), SearchStatus::StaleRefreshing);
}

#[test]
fn search_envelope_and_payload_version_mismatch_fails_closed() {
    let mut state = AppState::controller();
    state.reduce(snapshot(1, 1, "Current")).unwrap();
    let request_id = issue_search(&mut state, "AAPL");

    let error = state
        .reduce(search_results(2, 1, request_id, 2, vec![], None))
        .expect_err("mismatched search versions must fail closed");

    assert_eq!(error.code, "state-version");
    assert_eq!(state.access, AccessState::ProtocolLockout);
}

#[test]
fn manual_lock_ignores_a_known_in_flight_search_response() {
    let mut state = AppState::controller();
    state.reduce(snapshot(1, 1, "Current")).unwrap();
    let request_id = issue_search(&mut state, "AAPL");
    assert_eq!(
        state.handle(InputEvent::LockTui),
        vec![ClientAction::RequestLock]
    );

    assert_eq!(
        state.reduce(search_results(
            2,
            1,
            request_id,
            1,
            vec![stock_search_result()],
            None,
        )),
        Ok(ReduceOutcome::Ignored)
    );
    assert_eq!(state.access, AccessState::Locked);
    assert!(state.lock_pending());
    assert_eq!(state.reduce(lock_result(3, 1)), Ok(ReduceOutcome::Changed));
}

#[test]
fn changed_event_clears_results_and_requeues_the_current_query() {
    let mut state = AppState::controller();
    state.reduce(snapshot(1, 1, "Current")).unwrap();
    let request_id = issue_search(&mut state, "AAPL");
    state
        .reduce(search_results(
            2,
            1,
            request_id,
            1,
            vec![stock_search_result()],
            None,
        ))
        .unwrap();
    assert_eq!(state.search_state().results().len(), 1);

    assert_eq!(state.reduce(event(3, 2)), Ok(ReduceOutcome::Changed));
    assert!(state.search_state().results().is_empty());
    assert_eq!(state.search_state().status(), SearchStatus::StaleRefreshing);

    assert!(matches!(
        state
            .handle(InputEvent::Tick(Duration::from_millis(100)))
            .as_slice(),
        [ClientAction::Search(_)]
    ));
}

#[test]
fn task8_arrow_keys_reach_every_focus_panel_and_overflow_row() {
    let mut envelope_value = serde_json::to_value(snapshot(1, 1, "Current")).unwrap();
    let sources = envelope_value["payload"]["snapshot"]["data"]["sources"]
        .as_array_mut()
        .expect("source rows");
    let mut second = sources[0].clone();
    second["source_id"] = json!("source:second");
    sources.push(second);

    let mut state = AppState::controller();
    state
        .reduce(serde_json::from_value(envelope_value).unwrap())
        .unwrap();
    for (screen, panels) in [
        (Screen::RiskApprovals, 4),
        (Screen::DataEvidence, 2),
        (Screen::Memory, 3),
        (Screen::System, 4),
    ] {
        state.screen = screen;
        for expected in 1..panels {
            state.handle(InputEvent::Right);
            assert_eq!(state.screen_state().narrow_panel, expected, "{screen:?}");
        }
        state.handle(InputEvent::Right);
        assert_eq!(state.screen_state().narrow_panel, 0, "{screen:?}");
        state.handle(InputEvent::Left);
        assert_eq!(state.screen_state().narrow_panel, panels - 1, "{screen:?}");
        state.handle(InputEvent::Right);
    }

    state.screen = Screen::DataEvidence;
    state.handle(InputEvent::Down);
    assert_eq!(state.screen_state().scroll_offset, 1);
    state.handle(InputEvent::Up);
    assert_eq!(state.screen_state().scroll_offset, 0);
}

#[test]
fn task7_keys_reach_agent_detail_model_panels_and_all_timeline_events() {
    let mut value = serde_json::to_value(snapshot(1, 1, "Current")).unwrap();
    let agent = value["payload"]["snapshot"]["agents"]["rows"][0].clone();
    let mut second_agent = agent.clone();
    second_agent["work_id"] = json!("work:2");
    second_agent["title"] = json!("Review MSFT");
    second_agent["priority"] = json!(5);
    value["payload"]["snapshot"]["agents"]["rows"] = json!([agent, second_agent]);

    let event = value["payload"]["snapshot"]["timeline"]["rows"][0].clone();
    let mut second_event = event.clone();
    second_event["event_id"] = json!("event:2");
    second_event["summary"] = json!("MSFT review started");
    second_event["symbol"] = json!("MSFT");
    value["payload"]["snapshot"]["timeline"]["rows"] = json!([event, second_event]);

    let mut state = AppState::controller();
    state
        .reduce(serde_json::from_value(value).unwrap())
        .unwrap();

    state.screen = Screen::Agents;
    state.handle(InputEvent::Right);
    state.handle(InputEvent::Up);
    assert_eq!(state.screen_state().selected_id.as_deref(), Some("work:1"));
    assert!(rendered_text(&state, 140, 40).contains("> [ ] RUNNING"));
    state.handle(InputEvent::Down);
    assert_eq!(state.screen_state().selected_id.as_deref(), Some("work:2"));
    state.handle(InputEvent::Char('o'));
    assert!(state.screen_state().detail_open);
    assert_eq!(state.screen_state().scroll_offset, 0);
    assert_eq!(state.mode, vesper_ratatui_console::state::LocalMode::Open);
    assert!(rendered_text(&state, 120, 36).contains("TASK ID: work:2"));
    state.handle(InputEvent::Escape);
    state.handle(InputEvent::Left);
    assert_eq!(state.screen_state().narrow_panel, 0);
    state.handle(InputEvent::Left);
    assert_eq!(state.screen_state().narrow_panel, 4);
    state.handle(InputEvent::Right);
    assert_eq!(state.screen_state().narrow_panel, 0);

    state.screen = Screen::ModelsRegime;
    state.handle(InputEvent::Down);
    assert_eq!(state.screen_state().scroll_offset, 0);
    assert_eq!(
        state.screen_state().selected_kind,
        Some(DetailKind::ModelOpinion)
    );
    state.handle(InputEvent::Right);
    assert_eq!(state.screen_state().narrow_panel, 1);
    assert_eq!(state.screen_state().scroll_offset, 0);
    state.handle(InputEvent::Right);
    assert_eq!(state.screen_state().narrow_panel, 2);
    state.handle(InputEvent::Right);
    assert_eq!(state.screen_state().narrow_panel, 0);

    state.screen = Screen::Timeline;
    assert!(!state.screen_state().show_all_events);
    state.handle(InputEvent::Up);
    assert_eq!(state.screen_state().selected_id.as_deref(), Some("event:1"));
    state.handle(InputEvent::Char('o'));
    let detail = rendered_text(&state, 120, 36);
    assert!(detail.contains("EVENT DETAIL"));
    assert!(detail.contains("EVENT ID: event:1"));
    state.set_terminal_area(Rect::new(0, 0, 120, 36));
    for _ in 0..100 {
        state.handle(InputEvent::Down);
    }
    let detail = rendered_text(&state, 120, 36);
    assert!(detail.contains("SOURCE: fixture"));
    state.handle(InputEvent::Escape);
    state.handle(InputEvent::Char('e'));
    assert!(state.screen_state().show_all_events);
    state.handle(InputEvent::Char('e'));
    assert!(!state.screen_state().show_all_events);
}

#[test]
fn direct_o_reaches_full_detail_on_every_remaining_screen_panel() {
    let cases = [
        ('3', 0, "ORDER DETAIL"),
        ('5', 0, "MODEL OPINION DETAIL"),
        ('5', 1, "MODEL CANDIDATE DETAIL"),
        ('5', 2, "MODEL METRIC DETAIL"),
        ('7', 0, "RISK LIMIT DETAIL"),
        ('7', 1, "APPROVAL DETAIL"),
        ('7', 2, "RISK ALERT DETAIL"),
        ('7', 3, "RISK METRIC DETAIL"),
        ('8', 0, "DATA SOURCE DETAIL"),
        ('8', 1, "DATA EVIDENCE DETAIL"),
        ('9', 0, "MEMORY CONTENT"),
        ('9', 2, "MEMORY HISTORY DETAIL"),
        ('0', 0, "SERVICE DETAIL"),
        ('0', 1, "SYSTEM METRIC DETAIL"),
        ('0', 2, "REPOSITORY DETAIL"),
    ];
    for (key, panel, expected) in cases {
        let mut state = AppState::controller();
        state.reduce(snapshot(1, 1, "Current")).unwrap();
        state.handle(InputEvent::Char(key));
        for _ in 0..panel {
            state.handle(InputEvent::Right);
        }
        state.handle(InputEvent::Up);
        state.handle(InputEvent::Char('o'));
        let detail = rendered_text(&state, 140, 40);
        assert!(
            detail.contains(expected),
            "{key} panel {panel} did not open {expected}\n{detail}"
        );
    }
}

#[test]
fn orders_and_models_navigate_typed_entities_in_rendered_order() {
    let mut state = AppState::controller();
    state.reduce(snapshot(1, 1, "Current")).unwrap();

    state.handle(InputEvent::Char('3'));
    state.handle(InputEvent::Up);
    assert_eq!(state.screen_state().selected_id.as_deref(), Some("order:1"));
    assert_eq!(state.screen_state().selected_kind, Some(DetailKind::Order));
    assert!(rendered_text(&state, 140, 40).contains("> order:1"));
    for (id, kind) in [
        ("fill:1", DetailKind::Fill),
        ("work:1", DetailKind::Agent),
        ("event:1", DetailKind::Event),
    ] {
        state.handle(InputEvent::Down);
        assert_eq!(state.screen_state().selected_id.as_deref(), Some(id));
        assert_eq!(state.screen_state().selected_kind, Some(kind));
        assert!(
            rendered_text(&state, 140, 40).contains(&format!("> {id}")),
            "selected Orders row {id} must be visible"
        );
    }
    state.handle(InputEvent::Char('o'));
    assert!(rendered_text(&state, 140, 40).contains("ORDER HISTORY DETAIL"));

    state.handle(InputEvent::Escape);
    state.handle(InputEvent::Char('5'));
    state.handle(InputEvent::Up);
    assert_eq!(
        state.screen_state().selected_kind,
        Some(DetailKind::ModelOpinion)
    );
    state.handle(InputEvent::Right);
    state.handle(InputEvent::Up);
    assert_eq!(
        state.screen_state().selected_kind,
        Some(DetailKind::ModelCandidate)
    );
    state.handle(InputEvent::Right);
    state.handle(InputEvent::Up);
    assert_eq!(state.screen_state().selected_kind, Some(DetailKind::Metric));
    state.handle(InputEvent::Down);
    assert_eq!(
        state.screen_state().selected_id.as_deref(),
        Some("evidence:1")
    );
    assert_eq!(
        state.screen_state().selected_kind,
        Some(DetailKind::Evidence)
    );
    assert!(rendered_text(&state, 140, 40).contains("> evidence:1"));
    state.handle(InputEvent::Char('o'));
    assert!(rendered_text(&state, 140, 40).contains("MODEL EVIDENCE DETAIL"));
}

#[test]
fn only_supported_direct_detail_targets_offer_context_notes() {
    for (panel, expected_target) in [
        (0, None),
        (1, Some(("approval", "approval:1"))),
        (2, None),
        (3, None),
    ] {
        let mut state = AppState::controller();
        state
            .reduce(snapshot_with_note_control(1, 1, "Current"))
            .unwrap();
        state.handle(InputEvent::Char('7'));
        for _ in 0..panel {
            state.handle(InputEvent::Right);
        }
        state.handle(InputEvent::Up);
        state.handle(InputEvent::Char('o'));
        assert_eq!(state.note_editor_target(), expected_target, "panel {panel}");
        state.handle(InputEvent::Char('n'));
        assert_eq!(
            state.mode,
            if expected_target.is_some() {
                LocalMode::NoteEditor
            } else {
                LocalMode::Open
            },
            "panel {panel}"
        );
    }
}

#[test]
fn direct_detail_scroll_uses_wrapped_content_height_instead_of_a_fixed_cap() {
    let mut value = serde_json::to_value(snapshot(1, 1, "Current")).unwrap();
    value["payload"]["snapshot"]["risk"]["alerts"][0]["summary"] =
        json!(format!("{}TAIL MARKER", "wrapped alert detail ".repeat(10)));
    let mut state = AppState::controller();
    state
        .reduce(serde_json::from_value(value).unwrap())
        .unwrap();
    state.set_terminal_area(Rect::new(0, 0, 50, 26));
    state.handle(InputEvent::Char('7'));
    state.handle(InputEvent::Right);
    state.handle(InputEvent::Right);
    state.handle(InputEvent::Up);
    state.handle(InputEvent::Char('o'));

    for _ in 0..100 {
        state.handle(InputEvent::Down);
    }

    assert!(state.screen_state().scroll_offset > 9);
    assert!(rendered_text(&state, 50, 26).contains("RESOLVED: NOT RESOLVED"));
}

#[test]
fn events_before_authentication_fail_closed() {
    let mut state = AppState::locked();
    let error = state
        .reduce(event(1, 1))
        .expect_err("event must fail closed");

    assert_eq!(error.code, "state");
    assert_eq!(state.access, AccessState::ProtocolLockout);
    assert!(state.snapshot.is_none());
}

#[test]
fn number_keys_select_all_ten_screens_after_unlock() {
    let mut state = AppState::controller();

    for (key, expected) in [
        ('1', Screen::Impact),
        ('2', Screen::Portfolio),
        ('3', Screen::Orders),
        ('4', Screen::Agents),
        ('5', Screen::ModelsRegime),
        ('6', Screen::Timeline),
        ('7', Screen::RiskApprovals),
        ('8', Screen::DataEvidence),
        ('9', Screen::Memory),
        ('0', Screen::System),
    ] {
        state.handle(InputEvent::Char(key));
        assert_eq!(state.screen, expected);
    }
}

#[test]
fn p_toggles_account_mask_only_on_system_and_never_mutates_the_snapshot() {
    let mut state = AppState::controller();
    state.reduce(snapshot(1, 7, "First")).unwrap();
    let before = serde_json::to_value(state.snapshot.as_ref().unwrap()).unwrap();

    state.screen = Screen::Portfolio;
    state.handle(InputEvent::Char('p'));
    assert!(!state.preferences().mask_account_details);

    state.screen = Screen::System;
    state.handle(InputEvent::Char('p'));
    assert!(state.preferences().mask_account_details);
    assert!(state.screen_state().mask_account_details);
    assert_eq!(
        serde_json::to_value(state.snapshot.as_ref().unwrap()).unwrap(),
        before
    );

    state.handle(InputEvent::Char('p'));
    assert!(!state.preferences().mask_account_details);
}

#[test]
fn system_live_panel_keyboard_scroll_reaches_long_transition_plans() {
    let mut state = AppState::controller();
    state.reduce(snapshot(1, 7, "First")).unwrap();
    let mut value = serde_json::to_value(state.snapshot.take().unwrap()).unwrap();
    value["system"]["live_transition_plan"] = json!({
        "broker_positions_as_of_utc":"2026-08-04T12:00:00Z",
        "desired_portfolio_id":"portfolio:candidate",
        "orders": (0..8).map(|index| json!({
            "symbol": format!("SYM{index}"),
            "side":"buy",
            "quantity":"1",
            "approval_required":true
        })).collect::<Vec<_>>()
    });
    state.snapshot = Some(serde_json::from_value(value).unwrap());
    state.screen = Screen::System;
    for _ in 0..3 {
        state.handle(InputEvent::Right);
    }
    for _ in 0..20 {
        state.handle(InputEvent::Down);
    }

    assert_eq!(state.screen_state().narrow_panel, 3);
    assert!(
        state.screen_state().scroll_offset >= 8,
        "scroll offset was {}",
        state.screen_state().scroll_offset
    );
}

#[test]
fn manual_lock_hides_content_and_blocks_auth_until_lock_result() {
    let mut state = AppState::controller();
    assert_eq!(
        state.reduce(snapshot(1, 7, "First")),
        Ok(ReduceOutcome::Changed)
    );

    assert_eq!(
        state.handle(InputEvent::LockTui),
        vec![ClientAction::RequestLock]
    );
    assert_eq!(state.access, AccessState::Locked);
    assert!(state.snapshot.is_none());
    assert!(state.lock_pending());
    state.handle(InputEvent::Char('p'));
    assert!(state.handle(InputEvent::Enter).is_empty());
    assert_eq!(state.masked_auth_input(), "");

    let result = state.reduce(envelope(2, 7, "lock-result", json!({ "locked": true })));
    assert_eq!(result, Ok(ReduceOutcome::Changed));
    assert_eq!(state.access, AccessState::Locked);
    assert!(state.snapshot.is_none());
    assert!(!state.lock_pending());
}

#[test]
fn manual_lock_ignores_an_expected_snapshot_until_lock_result() {
    let mut state = AppState::locked();
    state.reduce(server_hello(1, false)).unwrap();
    state.handle(InputEvent::Char('p'));
    state.handle(InputEvent::Enter);
    assert_eq!(
        state.reduce(auth_result(2, true, "viewer")),
        Ok(ReduceOutcome::RequestSnapshot)
    );
    state.handle(InputEvent::LockTui);

    assert_eq!(
        state.reduce(snapshot(3, 1, "In flight")),
        Ok(ReduceOutcome::Ignored)
    );
    assert_eq!(state.access, AccessState::Locked);
    assert!(state.snapshot.is_none());
    assert!(state.lock_pending());
    assert_eq!(state.reduce(lock_result(4, 1)), Ok(ReduceOutcome::Changed));
}

#[test]
fn manual_lock_rejects_an_in_flight_snapshot_with_mismatched_versions() {
    let mut state = AppState::locked();
    state.reduce(server_hello(1, false)).unwrap();
    state.handle(InputEvent::Char('p'));
    state.handle(InputEvent::Enter);
    state.reduce(auth_result(2, true, "viewer")).unwrap();
    state.handle(InputEvent::LockTui);
    let mut mismatch = snapshot(3, 1, "Mismatch");
    mismatch.state_version = 2;

    assert!(state.reduce(mismatch).is_err());
    assert_eq!(state.access, AccessState::ProtocolLockout);
    assert!(state.snapshot.is_none());
}

#[test]
fn manual_lock_ignores_an_expected_lease_result_and_pong_until_lock_result() {
    let mut lease = AppState::viewer();
    lease.handle(InputEvent::TakeControl);
    lease.handle(InputEvent::LockTui);
    assert_eq!(
        lease.reduce(lease_result(1, "controller")),
        Ok(ReduceOutcome::Ignored)
    );
    assert_eq!(lease.access, AccessState::Locked);
    assert!(lease.lock_pending());
    assert_eq!(lease.reduce(lock_result(2, 0)), Ok(ReduceOutcome::Changed));

    let mut pong_state = AppState::viewer();
    pong_state.handle(InputEvent::LockTui);
    assert_eq!(
        pong_state.reduce(pong(1, 0, "in-flight")),
        Ok(ReduceOutcome::Ignored)
    );
    assert_eq!(pong_state.access, AccessState::Locked);
    assert_eq!(
        pong_state.reduce(lock_result(2, 0)),
        Ok(ReduceOutcome::Changed)
    );
}

#[test]
fn manual_lock_consumes_each_expected_in_flight_reply_only_once() {
    let mut snapshot_state = AppState::locked();
    snapshot_state.reduce(server_hello(1, false)).unwrap();
    snapshot_state.handle(InputEvent::Char('p'));
    snapshot_state.handle(InputEvent::Enter);
    snapshot_state
        .reduce(auth_result(2, true, "viewer"))
        .unwrap();
    snapshot_state.handle(InputEvent::LockTui);
    assert_eq!(
        snapshot_state.reduce(snapshot(3, 1, "First")),
        Ok(ReduceOutcome::Ignored)
    );
    assert!(snapshot_state.reduce(snapshot(4, 1, "Duplicate")).is_err());
    assert_eq!(snapshot_state.access, AccessState::ProtocolLockout);

    let mut lease_state = AppState::viewer();
    lease_state.handle(InputEvent::TakeControl);
    lease_state.handle(InputEvent::LockTui);
    assert_eq!(
        lease_state.reduce(lease_result(1, "controller")),
        Ok(ReduceOutcome::Ignored)
    );
    assert!(lease_state.reduce(lease_result(2, "controller")).is_err());
    assert_eq!(lease_state.access, AccessState::ProtocolLockout);
}

#[test]
fn control_transition_gaps_and_gapped_fatal_messages_require_reconnect() {
    let mut lock = AppState::viewer();
    lock.handle(InputEvent::LockTui);
    assert!(lock.reduce(pong(2, 0, "gap")).is_err());
    assert_eq!(lock.access, AccessState::ProtocolLockout);

    let mut lease = AppState::viewer();
    lease.handle(InputEvent::TakeControl);
    assert!(lease.reduce(lease_result(2, "controller")).is_err());
    assert_eq!(lease.access, AccessState::ProtocolLockout);

    let mut fatal = AppState::viewer();
    assert!(
        fatal
            .reduce(envelope(
                2,
                0,
                "protocol-error",
                json!({ "code": "fatal", "safe_message": "Reconnect." }),
            ))
            .is_err()
    );
    assert_eq!(fatal.access, AccessState::ProtocolLockout);

    let mut wrong_direction = AppState::viewer();
    assert!(
        wrong_direction
            .reduce(envelope(
                2,
                0,
                "lease-request",
                json!({ "action": "take-control" }),
            ))
            .is_err()
    );
    assert_eq!(wrong_direction.access, AccessState::ProtocolLockout);
}

#[test]
fn newer_snapshot_replaces_state_and_duplicate_sequence_is_ignored() {
    let mut state = AppState::controller();

    assert_eq!(
        state.reduce(snapshot(1, 7, "First")),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(state.state_version(), 7);
    assert_eq!(
        state.reduce(snapshot(2, 8, "Second")),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(state.state_version(), 8);

    assert_eq!(
        state.reduce(snapshot(2, 99, "Duplicate")),
        Ok(ReduceOutcome::Ignored)
    );
    assert_eq!(state.state_version(), 8);
}

#[test]
fn sequence_gap_requests_a_fresh_snapshot() {
    let mut state = AppState::controller();
    assert_eq!(
        state.reduce(snapshot(1, 7, "First")),
        Ok(ReduceOutcome::Changed)
    );

    let outcome = state.reduce(envelope(3, 7, "pong", json!({ "nonce": "gap" })));

    assert_eq!(outcome, Ok(ReduceOutcome::RequestSnapshot));
    assert!(state.awaiting_snapshot());
}

#[test]
fn stale_snapshot_during_resync_fails_closed_instead_of_leaving_a_blank_wait() {
    let mut state = AppState::controller();
    state.reduce(snapshot(1, 7, "Current")).unwrap();
    assert_eq!(
        state.reduce(pong(3, 7, "gap")),
        Ok(ReduceOutcome::RequestSnapshot)
    );

    assert!(state.reduce(snapshot(4, 6, "Stale")).is_err());
    assert_eq!(state.access, AccessState::ProtocolLockout);
    assert!(state.snapshot.is_none());
}

#[test]
fn server_hello_selects_setup_or_unlock_only_as_the_first_server_message() {
    let mut setup = AppState::locked();
    assert_eq!(
        setup.reduce(server_hello(1, true)),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(setup.access, AccessState::FirstRun);

    let mut unlock = AppState::locked();
    assert_eq!(
        unlock.reduce(server_hello(1, false)),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(unlock.access, AccessState::Locked);

    assert!(unlock.reduce(server_hello(2, false)).is_err());
    assert_eq!(unlock.access, AccessState::ProtocolLockout);
}

#[test]
fn server_sequence_zero_is_never_treated_as_a_duplicate() {
    let mut state = AppState::locked();

    assert!(state.reduce(server_hello(0, false)).is_err());
    assert_eq!(state.access, AccessState::ProtocolLockout);
}

#[test]
fn auth_success_becomes_viewer_clears_secret_and_requests_snapshot() {
    let mut state = AppState::locked();
    state.reduce(server_hello(1, false)).unwrap();
    for character in "SENSITIVE".chars() {
        state.handle(InputEvent::Char(character));
    }
    assert!(matches!(
        state.handle(InputEvent::Enter).as_slice(),
        [ClientAction::Authenticate(_)]
    ));

    assert_eq!(
        state.reduce(auth_result(2, true, "viewer")),
        Ok(ReduceOutcome::RequestSnapshot)
    );
    assert_eq!(state.access, AccessState::Viewer);
    assert_eq!(state.masked_auth_input(), "");
    assert!(state.awaiting_snapshot());
}

#[test]
fn auth_success_cannot_grant_controller_without_an_explicit_lease() {
    let mut state = AppState::locked();
    state.reduce(server_hello(1, false)).unwrap();
    state.handle(InputEvent::Char('p'));
    state.handle(InputEvent::Enter);

    assert!(state.reduce(auth_result(2, true, "controller")).is_err());
    assert_eq!(state.access, AccessState::ProtocolLockout);
    assert!(state.snapshot.is_none());
}

#[test]
fn pong_is_rejected_before_server_hello_and_during_authentication() {
    let mut before_hello = AppState::locked();
    assert!(before_hello.reduce(pong(1, 0, "early")).is_err());
    assert_eq!(before_hello.access, AccessState::ProtocolLockout);

    let mut awaiting_password = AppState::locked();
    awaiting_password.reduce(server_hello(1, false)).unwrap();
    assert!(awaiting_password.reduce(pong(2, 0, "during-auth")).is_err());
    assert_eq!(awaiting_password.access, AccessState::ProtocolLockout);

    let mut awaiting_result = AppState::locked();
    awaiting_result.reduce(server_hello(1, false)).unwrap();
    awaiting_result.handle(InputEvent::Char('p'));
    awaiting_result.handle(InputEvent::Enter);
    assert!(awaiting_result.reduce(pong(2, 0, "during-result")).is_err());
    assert_eq!(awaiting_result.access, AccessState::ProtocolLockout);
}

#[test]
fn auth_failure_clears_secret_and_remains_in_the_current_auth_flow() {
    let mut unlock = AppState::locked();
    unlock.reduce(server_hello(1, false)).unwrap();
    unlock.handle(InputEvent::Char('x'));
    assert!(matches!(
        unlock.handle(InputEvent::Enter).as_slice(),
        [ClientAction::Authenticate(_)]
    ));
    assert_eq!(
        unlock.reduce(auth_result(2, false, "locked")),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(unlock.access, AccessState::Locked);
    assert_eq!(unlock.masked_auth_input(), "");

    let mut setup = AppState::locked();
    setup.reduce(server_hello(1, true)).unwrap();
    setup.handle(InputEvent::Char('x'));
    setup.handle(InputEvent::Enter);
    setup.handle(InputEvent::Char('x'));
    assert!(matches!(
        setup.handle(InputEvent::Enter).as_slice(),
        [ClientAction::Authenticate(_)]
    ));
    assert_eq!(
        setup.reduce(auth_result(2, false, "locked")),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(setup.access, AccessState::FirstRun);
    assert_eq!(setup.masked_auth_input(), "");
}

#[test]
fn authentication_feedback_tracks_pending_failure_and_first_run_mismatch() {
    let mut unlock = AppState::locked();
    unlock.reduce(server_hello(1, false)).unwrap();
    unlock.handle(InputEvent::Char('x'));
    unlock.handle(InputEvent::Enter);
    assert_eq!(unlock.auth_feedback(), AuthFeedback::Pending);
    unlock
        .reduce(envelope(
            2,
            0,
            "auth-result",
            json!({
                "success": false,
                "access_state": "locked",
                "reason": "SENSITIVE SERVER DETAIL"
            }),
        ))
        .unwrap();
    assert_eq!(unlock.auth_feedback(), AuthFeedback::Failed);

    let mut setup = AppState::locked();
    setup.reduce(server_hello(1, true)).unwrap();
    setup.handle(InputEvent::Char('a'));
    setup.handle(InputEvent::Enter);
    setup.handle(InputEvent::Char('b'));
    setup.handle(InputEvent::Enter);
    assert_eq!(setup.auth_feedback(), AuthFeedback::PasswordMismatch);
}

#[test]
fn lease_results_control_only_the_foundation_access_role() {
    for status in ["controller", "transferred"] {
        let mut state = AppState::viewer();
        assert_eq!(
            state.handle(InputEvent::TakeControl),
            vec![ClientAction::RequestLease]
        );
        state.reduce(lease_result(1, status)).unwrap();
        assert_eq!(state.access, AccessState::Controller);
    }

    for status in ["viewer", "lease-held"] {
        let mut state = AppState::viewer();
        assert_eq!(
            state.handle(InputEvent::TakeControl),
            vec![ClientAction::RequestLease]
        );
        state.reduce(lease_result(1, status)).unwrap();
        assert_eq!(state.access, AccessState::Viewer);
    }
}

#[test]
fn protocol_error_is_a_fatal_lockout_that_requires_reconnect() {
    let mut state = AppState::controller();
    state.reduce(snapshot(1, 7, "First")).unwrap();

    let error = state
        .reduce(envelope(
            2,
            7,
            "protocol-error",
            json!({ "code": "schema", "safe_message": "Protocol mismatch." }),
        ))
        .expect_err("protocol error must fail closed");

    assert_eq!(error.code, "schema");
    assert_eq!(state.access, AccessState::ProtocolLockout);
    assert!(state.snapshot.is_none());
    state.handle(InputEvent::Char('p'));
    assert!(state.handle(InputEvent::Enter).is_empty());
    assert_eq!(state.masked_auth_input(), "");
    assert_eq!(
        state.handle(InputEvent::Char('q')),
        vec![ClientAction::CloseTui]
    );
    assert_eq!(
        state.handle(InputEvent::Reconnect),
        vec![ClientAction::Reconnect]
    );
}

#[test]
fn resync_rebases_to_observed_sequence_and_only_next_exact_snapshot_clears_it() {
    let mut state = AppState::controller();
    state.reduce(snapshot(1, 7, "First")).unwrap();

    assert_eq!(
        state.reduce(snapshot(3, 8, "Gap snapshot")),
        Ok(ReduceOutcome::RequestSnapshot)
    );
    assert!(state.awaiting_snapshot());
    assert_eq!(state.state_version(), 7);

    assert_eq!(
        state.reduce(pong(4, 7, "still-waiting")),
        Ok(ReduceOutcome::Ignored)
    );
    assert!(state.awaiting_snapshot());

    assert_eq!(
        state.reduce(snapshot(5, 8, "Fresh")),
        Ok(ReduceOutcome::Changed)
    );
    assert!(!state.awaiting_snapshot());
    assert_eq!(state.state_version(), 8);
}

#[test]
fn snapshot_versions_reject_mismatch_stale_and_equal_divergence() {
    let mut mismatch = AppState::controller();
    assert!(mismatch.reduce(snapshot(1, 7, "First")).is_ok());
    let mut mismatched = serde_json::to_value(snapshot(2, 8, "Mismatch")).unwrap();
    mismatched["state_version"] = json!(9);
    assert!(
        mismatch
            .reduce(serde_json::from_value(mismatched).unwrap())
            .is_err()
    );
    assert_eq!(mismatch.access, AccessState::ProtocolLockout);

    let mut versions = AppState::controller();
    versions.reduce(snapshot(1, 7, "First")).unwrap();
    assert_eq!(
        versions.reduce(snapshot(2, 6, "Older")),
        Ok(ReduceOutcome::Ignored)
    );
    assert_eq!(versions.state_version(), 7);
    assert_eq!(
        versions.reduce(snapshot(3, 7, "First")),
        Ok(ReduceOutcome::Ignored)
    );
    assert!(versions.reduce(snapshot(4, 7, "Divergent")).is_err());
    assert_eq!(versions.access, AccessState::ProtocolLockout);
}

#[test]
fn equal_version_cache_can_be_replaced_once_by_a_fresh_projection_only() {
    let mut replacement = AppState::controller();
    assert_eq!(
        replacement.reduce(stale_cache_snapshot(1, 0, "Cached")),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(
        replacement.reduce(snapshot_with_qwen_state(2, 0, "Fresh", "READY")),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(
        replacement
            .snapshot
            .as_ref()
            .expect("fresh snapshot")
            .shell
            .header
            .regime_label,
        "Fresh"
    );

    let mut reverse = AppState::controller();
    reverse
        .reduce(snapshot_with_qwen_state(1, 0, "Fresh", "READY"))
        .unwrap();
    assert!(
        reverse
            .reduce(stale_cache_snapshot(2, 0, "Cached"))
            .is_err()
    );
    assert_eq!(reverse.access, AccessState::ProtocolLockout);

    let mut nonzero = AppState::controller();
    assert!(
        nonzero
            .reduce(stale_cache_snapshot(1, 7, "Cached"))
            .is_err(),
        "only a version-zero startup cache is valid"
    );
    assert_eq!(nonzero.access, AccessState::ProtocolLockout);
}

#[test]
fn forged_cache_label_with_an_enabled_capability_is_rejected() {
    let mut forged = serde_json::to_value(stale_cache_snapshot(1, 0, "Forged")).unwrap();
    forged["payload"]["snapshot"]["shell"]["capabilities"] = json!([{
        "capability_id": "note.add",
        "state": "enabled",
        "reason": null
    }]);
    let mut state = AppState::controller();

    assert!(
        state
            .reduce(serde_json::from_value(forged).unwrap())
            .is_err()
    );
    assert_eq!(state.access, AccessState::ProtocolLockout);
}

#[test]
fn manual_lock_reauthenticates_on_the_same_sequence_and_returns_as_viewer() {
    let mut state = AppState::controller();
    state.reduce(snapshot(1, 7, "First")).unwrap();
    assert_eq!(
        state.handle(InputEvent::LockTui),
        vec![ClientAction::RequestLock]
    );
    assert_eq!(state.access, AccessState::Locked);
    assert!(state.snapshot.is_none());
    assert!(state.lock_pending());

    assert_eq!(state.reduce(lock_result(2, 7)), Ok(ReduceOutcome::Changed));
    assert_eq!(state.access, AccessState::Locked);
    assert!(state.snapshot.is_none());
    state.handle(InputEvent::Char('p'));
    assert!(matches!(
        state.handle(InputEvent::Enter).as_slice(),
        [ClientAction::Authenticate(_)]
    ));

    assert_eq!(
        state.reduce(auth_result(3, true, "viewer")),
        Ok(ReduceOutcome::RequestSnapshot)
    );
    assert_eq!(state.access, AccessState::Viewer);
}

#[test]
fn snapshot_before_authentication_fails_closed() {
    let mut state = AppState::locked();
    state.reduce(server_hello(1, false)).unwrap();

    assert!(state.reduce(snapshot(2, 1, "Forbidden")).is_err());
    assert_eq!(state.access, AccessState::ProtocolLockout);
    assert!(state.snapshot.is_none());
}

#[test]
fn wrong_direction_message_fails_closed_but_old_messages_are_ignored() {
    let mut state = AppState::viewer();
    state.reduce(pong(1, 0, "first")).unwrap();
    assert_eq!(
        state.reduce(envelope(
            1,
            0,
            "protocol-error",
            json!({ "code": "old", "safe_message": "Old message." }),
        )),
        Ok(ReduceOutcome::Ignored)
    );
    assert_eq!(state.access, AccessState::Viewer);

    assert!(
        state
            .reduce(envelope(
                2,
                0,
                "lease-request",
                json!({ "action": "take-control" }),
            ))
            .is_err()
    );
    assert_eq!(state.access, AccessState::ProtocolLockout);
}

#[test]
fn auth_result_without_a_submitted_request_fails_closed() {
    let mut state = AppState::locked();
    state.reduce(server_hello(1, false)).unwrap();

    assert!(state.reduce(auth_result(2, true, "viewer")).is_err());
    assert_eq!(state.access, AccessState::ProtocolLockout);
}

#[test]
fn auth_failure_returns_to_retry_and_accepts_one_new_submission() {
    let mut state = AppState::locked();
    state.reduce(server_hello(1, false)).unwrap();
    state.handle(InputEvent::Char('x'));
    assert!(matches!(
        state.handle(InputEvent::Enter).as_slice(),
        [ClientAction::Authenticate(_)]
    ));

    state.reduce(auth_result(2, false, "locked")).unwrap();
    assert!(!state.auth_pending());
    state.handle(InputEvent::Char('y'));
    assert!(matches!(
        state.handle(InputEvent::Enter).as_slice(),
        [ClientAction::Authenticate(_)]
    ));
    assert!(state.auth_pending());
}

#[test]
fn sequence_gap_during_auth_or_manual_reauth_requires_reconnect() {
    let mut initial = AppState::locked();
    assert!(initial.reduce(server_hello(2, false)).is_err());
    assert_eq!(initial.access, AccessState::ProtocolLockout);

    let mut authenticating = AppState::locked();
    authenticating.reduce(server_hello(1, false)).unwrap();
    authenticating.handle(InputEvent::Char('p'));
    authenticating.handle(InputEvent::Enter);
    assert!(
        authenticating
            .reduce(auth_result(3, true, "viewer"))
            .is_err()
    );
    assert_eq!(authenticating.access, AccessState::ProtocolLockout);

    let mut relocking = AppState::controller();
    relocking.reduce(snapshot(1, 7, "First")).unwrap();
    relocking.handle(InputEvent::LockTui);
    relocking.reduce(lock_result(2, 7)).unwrap();
    relocking.handle(InputEvent::Char('p'));
    relocking.handle(InputEvent::Enter);
    assert!(relocking.reduce(auth_result(4, true, "viewer")).is_err());
    assert_eq!(relocking.access, AccessState::ProtocolLockout);
}

#[test]
fn lease_result_without_take_control_request_fails_closed() {
    let mut state = AppState::viewer();

    assert!(state.reduce(lease_result(1, "controller")).is_err());
    assert_eq!(state.access, AccessState::ProtocolLockout);
}
