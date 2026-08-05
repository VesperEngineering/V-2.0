use std::convert::Infallible;
use std::error::Error;
use std::fmt;

use ratatui::Terminal;
use ratatui::backend::{Backend, ClearType, TestBackend, WindowSize};
use ratatui::buffer::{Buffer, Cell};
use ratatui::layout::{Position, Rect, Size};
use serde_json::{Value, json};
use vesper_ratatui_console::app::draw_with_one_recovery;
use vesper_ratatui_console::contract::{ConsoleSnapshot, Envelope, EventTarget};
use vesper_ratatui_console::controls::ControlOverlay;
use vesper_ratatui_console::input::InputEvent;
use vesper_ratatui_console::layout::{DisplayMode, shell_layout};
use vesper_ratatui_console::render_plan::{RenderPlan, ShellRegion, region_for_target};
use vesper_ratatui_console::renderer::{RenderKind, Renderer};
use vesper_ratatui_console::search::SEARCH_DEBOUNCE;
use vesper_ratatui_console::state::{AppState, ClientAction, ReduceOutcome, Screen};
use vesper_ratatui_console::theme::Theme;

const WIDTH: u16 = 140;
const HEIGHT: u16 = 42;

#[test]
fn every_event_target_maps_to_one_shell_region() {
    use EventTarget::*;
    let cases = [
        (ShellAlerts, ShellRegion::Alerts),
        (ImpactHoldings, ShellRegion::Body),
        (ImpactEvents, ShellRegion::Body),
        (ImpactAgents, ShellRegion::Body),
        (PortfolioRows, ShellRegion::Body),
        (PortfolioReturnsToday, ShellRegion::Body),
        (PortfolioReturnsSinceRebalance, ShellRegion::Body),
        (PortfolioReturnsSinceStart, ShellRegion::Body),
        (PortfolioMetrics, ShellRegion::Body),
        (PortfolioHistory, ShellRegion::Body),
        (OrdersRows, ShellRegion::Body),
        (OrdersReconciliationAgents, ShellRegion::Body),
        (OrdersHistory, ShellRegion::Body),
        (AgentsRows, ShellRegion::Body),
        (AgentsHistory, ShellRegion::Body),
        (ModelsOpinions, ShellRegion::Body),
        (ModelsCandidates, ShellRegion::Body),
        (ModelsMetrics, ShellRegion::Body),
        (ModelsEvidence, ShellRegion::Body),
        (TimelineRows, ShellRegion::Body),
        (RiskLimits, ShellRegion::Body),
        (RiskApprovals, ShellRegion::Body),
        (RiskAlerts, ShellRegion::Body),
        (RiskMetrics, ShellRegion::Body),
        (DataSources, ShellRegion::Body),
        (DataEvidence, ShellRegion::Body),
        (MemoryRows, ShellRegion::Body),
        (MemoryHistory, ShellRegion::Body),
        (SystemServices, ShellRegion::Body),
        (SystemMetrics, ShellRegion::Body),
        (SystemRepositories, ShellRegion::Body),
    ];
    for (target, expected) in cases {
        assert_eq!(region_for_target(target), expected, "{target:?}");
    }
    assert_eq!(
        RenderPlan::for_event_targets([TimelineRows]),
        RenderPlan::partial([ShellRegion::Body])
    );
}

#[test]
fn timeline_event_state_invalidation_is_partial_without_unchanged_header_or_alerts() {
    let mut state = AppState::controller();
    assert_eq!(
        state.reduce(snapshot_envelope(1, 1)),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(state.take_render_plan(), Some(RenderPlan::Full));
    assert_eq!(
        state.reduce(timeline_event_envelope(2, 2)),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(
        state.take_render_plan(),
        Some(RenderPlan::partial([ShellRegion::Body]))
    );
}

#[test]
fn event_fingerprints_add_header_only_when_header_changes() {
    let mut state = AppState::controller();
    state.reduce(snapshot_envelope(1, 1)).unwrap();
    state.take_render_plan();
    state
        .reduce(timeline_event_with_header(2, 2, Some("CHANGED REGIME")))
        .unwrap();
    assert_eq!(
        state.take_render_plan(),
        Some(RenderPlan::partial([
            ShellRegion::Header,
            ShellRegion::Body,
        ]))
    );
}

#[test]
fn alert_event_repaints_alert_strip_and_header_alert_fingerprint() {
    let mut state = AppState::controller();
    state.reduce(snapshot_envelope(1, 1)).unwrap();
    state.take_render_plan();
    state.reduce(alert_event_envelope(2, 2)).unwrap();
    assert_eq!(
        state.take_render_plan(),
        Some(RenderPlan::partial([
            ShellRegion::Header,
            ShellRegion::Alerts,
        ]))
    );
}

#[test]
fn cross_target_presentation_change_repaints_current_screen_and_matches_full() {
    let mut snapshot = snapshot_value(1);
    let mut state = AppState::controller();
    state
        .reduce(snapshot_envelope_from_value(1, 1, snapshot.clone()))
        .unwrap();
    let mut terminal = Terminal::new(ProbeBackend::new(WIDTH, HEIGHT)).unwrap();
    let mut renderer = Renderer::new();
    let initial_plan = state.take_render_plan().unwrap();
    renderer.draw(&mut terminal, &state, initial_plan).unwrap();

    snapshot["impact"]["freshness"] = json!("unavailable");
    snapshot["impact"]["as_of_utc"] = Value::Null;
    snapshot["impact"]["error"] = json!("Impact projection unavailable.");
    state
        .reduce(alert_event_from_snapshot(2, 2, &snapshot))
        .unwrap();
    let plan = state.take_render_plan().unwrap();
    assert_eq!(
        plan,
        RenderPlan::partial([ShellRegion::Header, ShellRegion::Alerts, ShellRegion::Body,])
    );
    renderer.draw(&mut terminal, &state, plan).unwrap();
    let partial = renderer.committed_buffer().unwrap().clone();

    let mut full_terminal = Terminal::new(TestBackend::new(WIDTH, HEIGHT)).unwrap();
    let mut full_renderer = Renderer::new();
    full_renderer
        .draw(&mut full_terminal, &state, RenderPlan::Full)
        .unwrap();
    assert_eq!(&partial, full_renderer.committed_buffer().unwrap());
    assert!(buffer_text(&partial).contains("Impact projection unavailable."));
}

#[test]
fn event_that_invalidates_a_reviewed_control_also_repaints_the_body() {
    let mut snapshot = controls_snapshot_value(1);
    let mut state = AppState::controller();
    state
        .reduce(snapshot_envelope_from_value(1, 1, snapshot.clone()))
        .unwrap();
    state.handle(InputEvent::Char('7'));
    state.handle(InputEvent::OpenBrowseRow { panel: 1, index: 0 });
    state.handle(InputEvent::Char(':'));
    assert!(matches!(
        state.control_overlay(),
        Some(ControlOverlay::Menu(_))
    ));
    state.take_render_plan();

    snapshot["control_version"] = json!(2);
    snapshot["control_hash"] =
        json!("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
    state
        .reduce(alert_event_from_snapshot(2, 2, &snapshot))
        .unwrap();

    assert!(matches!(
        state.control_overlay(),
        Some(ControlOverlay::DisabledReason { label, .. }) if label == "Controls Updated"
    ));
    assert_eq!(
        state.take_render_plan(),
        Some(RenderPlan::partial([
            ShellRegion::Header,
            ShellRegion::Alerts,
            ShellRegion::Body,
        ]))
    );
}

#[test]
fn alert_event_that_closes_search_detail_repaints_body_and_footer() {
    let snapshot = snapshot_value(1);
    let mut state = AppState::controller();
    state
        .reduce(snapshot_envelope_from_value(1, 1, snapshot.clone()))
        .unwrap();
    state.handle(InputEvent::Char('/'));
    for character in "AAPL".chars() {
        state.handle(InputEvent::Char(character));
    }
    let actions = state.handle(InputEvent::Tick(SEARCH_DEBOUNCE));
    let [ClientAction::Search(request)] = actions.as_slice() else {
        panic!("search request expected")
    };
    state
        .reduce(search_results_envelope(2, 1, request.request_id.get()))
        .unwrap();
    state.handle(InputEvent::Enter);
    assert!(state.search_detail().is_some());
    state.take_render_plan();

    state
        .reduce(alert_event_from_snapshot(3, 2, &snapshot))
        .unwrap();

    assert!(state.search_detail().is_none());
    assert_eq!(
        state.take_render_plan(),
        Some(RenderPlan::partial([
            ShellRegion::Header,
            ShellRegion::Alerts,
            ShellRegion::Body,
            ShellRegion::Footer,
        ]))
    );
}

#[test]
fn agents_event_that_changes_chat_availability_also_repaints_the_footer() {
    let mut snapshot = controls_snapshot_value(1);
    snapshot["agents"]["rows"][0]["agent"] = json!("v20-product");
    snapshot["agents"]["rows"][0]["chat_agent_id"] = json!("v20-product");
    let mut state = AppState::controller();
    state
        .reduce(snapshot_envelope_from_value(1, 1, snapshot.clone()))
        .unwrap();
    state.handle(InputEvent::Char('4'));
    state.handle(InputEvent::OpenBrowseRow { panel: 1, index: 0 });
    assert!(state.can_open_selected_chat());
    state.take_render_plan();

    snapshot["agents"]["rows"][0]["agent"] = json!("portfolio-research");
    snapshot["agents"]["rows"][0]["chat_agent_id"] = json!("portfolio-research");
    state
        .reduce(agent_event_from_snapshot(2, 2, &snapshot))
        .unwrap();

    assert!(!state.can_open_selected_chat());
    assert_eq!(
        state.take_render_plan(),
        Some(RenderPlan::partial([
            ShellRegion::Body,
            ShellRegion::Footer,
        ]))
    );
}

#[test]
fn pending_partial_then_input_or_full_trigger_promotes_to_full() {
    let mut state = AppState::controller();
    state.reduce(snapshot_envelope(1, 1)).unwrap();
    state.take_render_plan();
    state.reduce(timeline_event_envelope(2, 2)).unwrap();
    state.handle(InputEvent::Char('6'));
    assert_eq!(state.take_render_plan(), Some(RenderPlan::Full));

    state.set_theme(Theme::Charcoal);
    assert_eq!(state.take_render_plan(), Some(RenderPlan::Full));
    state.set_display_mode(DisplayMode::Compact);
    assert_eq!(state.take_render_plan(), Some(RenderPlan::Full));
    state.fail_connection();
    assert_eq!(state.take_render_plan(), Some(RenderPlan::Full));

    let mut replacement = AppState::controller();
    replacement.reduce(snapshot_envelope(1, 1)).unwrap();
    assert_eq!(replacement.take_render_plan(), Some(RenderPlan::Full));
    replacement.reduce(snapshot_envelope(2, 2)).unwrap();
    assert_eq!(replacement.take_render_plan(), Some(RenderPlan::Full));
}

#[test]
fn partial_render_matches_full_and_clears_stale_cells() {
    let mut state = timeline_state();
    set_first_timeline_summary(&mut state, "STALE-CELL-MARKER");
    let mut terminal = Terminal::new(ProbeBackend::new(WIDTH, HEIGHT)).unwrap();
    let mut renderer = Renderer::new();
    renderer
        .draw(&mut terminal, &state, RenderPlan::Full)
        .unwrap();
    assert!(buffer_text(renderer.committed_buffer().unwrap()).contains("STALE-CELL-MARKER"));

    state.snapshot.as_mut().unwrap().timeline.rows.clear();
    let receipt = renderer
        .draw(
            &mut terminal,
            &state,
            RenderPlan::partial([ShellRegion::Body]),
        )
        .unwrap();
    assert_eq!(receipt.kind, RenderKind::Partial);
    let partial = renderer.committed_buffer().unwrap().clone();
    assert!(!buffer_text(&partial).contains("STALE-CELL-MARKER"));

    let mut full_terminal = Terminal::new(TestBackend::new(WIDTH, HEIGHT)).unwrap();
    let mut full_renderer = Renderer::new();
    full_renderer
        .draw(&mut full_terminal, &state, RenderPlan::Full)
        .unwrap();
    assert_eq!(&partial, full_renderer.committed_buffer().unwrap());
}

#[test]
fn wide_cells_cannot_leak_across_partial_shell_regions() {
    let mut state = timeline_state();
    set_first_timeline_summary(&mut state, "界界界 newest wide event");
    let mut terminal = Terminal::new(ProbeBackend::new(WIDTH, HEIGHT)).unwrap();
    let mut renderer = Renderer::new();
    renderer
        .draw(&mut terminal, &state, RenderPlan::Full)
        .unwrap();

    set_first_timeline_summary(&mut state, "x");
    renderer
        .draw(
            &mut terminal,
            &state,
            RenderPlan::partial([ShellRegion::Body]),
        )
        .unwrap();
    let partial = renderer.committed_buffer().unwrap().clone();

    let mut full_terminal = Terminal::new(TestBackend::new(WIDTH, HEIGHT)).unwrap();
    let mut full_renderer = Renderer::new();
    full_renderer
        .draw(&mut full_terminal, &state, RenderPlan::Full)
        .unwrap();
    assert_eq!(&partial, full_renderer.committed_buffer().unwrap());
}

#[test]
fn cache_mismatch_and_resize_promote_partial_to_full() {
    let state = timeline_state();
    let mut terminal = Terminal::new(ProbeBackend::new(WIDTH, HEIGHT)).unwrap();
    let mut renderer = Renderer::new();
    renderer
        .draw(&mut terminal, &state, RenderPlan::Full)
        .unwrap();
    terminal.backend_mut().resize(WIDTH + 7, HEIGHT + 3);
    let receipt = renderer
        .draw(
            &mut terminal,
            &state,
            RenderPlan::partial([ShellRegion::Body]),
        )
        .unwrap();
    assert_eq!(receipt.kind, RenderKind::Full);
    assert_eq!(
        renderer.committed_buffer().unwrap().area,
        Rect::new(0, 0, WIDTH + 7, HEIGHT + 3)
    );
}

#[test]
fn backend_draw_or_flush_failure_invalidates_cache_and_recovers_with_full_clear() {
    for failure in [FailurePoint::Draw, FailurePoint::Flush] {
        let mut state = timeline_state();
        let mut terminal = Terminal::new(ProbeBackend::new(WIDTH, HEIGHT)).unwrap();
        let mut renderer = Renderer::new();
        renderer
            .draw(&mut terminal, &state, RenderPlan::Full)
            .unwrap();
        state.snapshot.as_mut().unwrap().timeline.rows.clear();
        terminal.backend_mut().fail_once(failure);
        assert!(
            renderer
                .draw(
                    &mut terminal,
                    &state,
                    RenderPlan::partial([ShellRegion::Body]),
                )
                .is_err()
        );
        assert!(renderer.committed_buffer().is_none());
        assert!(renderer.needs_recovery());

        let receipt = renderer
            .draw(
                &mut terminal,
                &state,
                RenderPlan::partial([ShellRegion::Body]),
            )
            .unwrap();
        assert_eq!(receipt.kind, RenderKind::Full);
        assert!(!renderer.needs_recovery());
        assert!(terminal.backend().clear_calls > 0);
        assert_eq!(
            renderer.committed_buffer().unwrap(),
            terminal.backend().buffer()
        );
    }
}

#[test]
fn runtime_draw_retries_once_with_full_recovery_then_stops() {
    for failure in [FailurePoint::Draw, FailurePoint::Flush] {
        let mut state = timeline_state();
        let mut terminal = Terminal::new(ProbeBackend::new(WIDTH, HEIGHT)).unwrap();
        let mut renderer = Renderer::new();
        renderer
            .draw(&mut terminal, &state, RenderPlan::Full)
            .unwrap();

        terminal.backend_mut().reset_probe();
        terminal.backend_mut().fail_times(failure, 1);
        let receipt = draw_with_one_recovery(
            &mut terminal,
            &mut state,
            &mut renderer,
            RenderPlan::partial([ShellRegion::Body]),
        )
        .unwrap();
        assert_eq!(receipt.kind, RenderKind::Full);
        assert_eq!(terminal.backend().draw_attempts, 2);
        assert_eq!(terminal.backend().clear_calls, 1);
        assert!(!renderer.needs_recovery());

        terminal.backend_mut().reset_probe();
        terminal.backend_mut().fail_times(failure, 2);
        assert!(
            draw_with_one_recovery(
                &mut terminal,
                &mut state,
                &mut renderer,
                RenderPlan::partial([ShellRegion::Body]),
            )
            .is_err()
        );
        assert_eq!(terminal.backend().draw_attempts, 2);
        assert_eq!(terminal.backend().clear_calls, 1);
        assert!(renderer.needs_recovery());
    }
}

#[test]
fn timeline_partial_writes_real_backend_cells_only_inside_full_width_body_strip() {
    let mut state = timeline_state();
    let mut terminal = Terminal::new(ProbeBackend::new(WIDTH, HEIGHT)).unwrap();
    let mut renderer = Renderer::new();
    renderer
        .draw(&mut terminal, &state, RenderPlan::Full)
        .unwrap();
    state.snapshot.as_mut().unwrap().timeline.rows.clear();
    terminal.backend_mut().reset_probe();
    let receipt = renderer
        .draw(
            &mut terminal,
            &state,
            RenderPlan::for_event_targets([EventTarget::TimelineRows]),
        )
        .unwrap();

    assert_eq!(receipt.kind, RenderKind::Partial);
    assert!(!terminal.backend().writes.is_empty());
    let body = shell_layout(Rect::new(0, 0, WIDTH, HEIGHT), state.display_mode()).body;
    assert!(
        terminal
            .backend()
            .writes
            .iter()
            .all(|(x, y)| *x < WIDTH && body.top() <= *y && *y < body.bottom())
    );
    assert_eq!(terminal.backend().clear_calls, 0);
}

fn timeline_state() -> AppState {
    let snapshot: ConsoleSnapshot = serde_json::from_str(include_str!(
        "../../contracts/v1/console_snapshot_empty_command_specs.json"
    ))
    .unwrap();
    let mut state = AppState::controller();
    state.snapshot = Some(snapshot);
    state.screen = Screen::Timeline;
    state
}

fn snapshot_value(state_version: u64) -> Value {
    let mut snapshot: Value = serde_json::from_str(include_str!(
        "../../contracts/v1/console_snapshot_empty_command_specs.json"
    ))
    .unwrap();
    snapshot["shell"]["state_version"] = json!(state_version);
    snapshot
}

fn controls_snapshot_value(state_version: u64) -> Value {
    let mut snapshot: Value =
        serde_json::from_str(include_str!("../../contracts/v1/controls_snapshot.json")).unwrap();
    snapshot["shell"]["state_version"] = json!(state_version);
    snapshot
}

fn wire_envelope(
    sequence: u64,
    state_version: u64,
    message_type: &str,
    payload: Value,
) -> Envelope {
    serde_json::from_value(json!({
        "schema_version": 1,
        "message_id": format!("server:{sequence}"),
        "sequence": sequence,
        "state_version": state_version,
        "timestamp_utc": "2026-08-03T00:00:00Z",
        "message_type": message_type,
        "payload": payload,
    }))
    .unwrap()
}

fn search_results_envelope(sequence: u64, state_version: u64, request_id: u64) -> Envelope {
    wire_envelope(
        sequence,
        state_version,
        "search-results",
        json!({
            "request_id": request_id,
            "indexed_state_version": state_version,
            "results": [{
                "kind": "stock",
                "record_type": "portfolio-row",
                "record_id": "AAPL",
                "label": "AAPL",
                "summary": "Current holding",
                "occurred_at_utc": "2026-08-03T00:00:00Z",
                "source": "fixture",
                "screen": "portfolio",
                "context_only": null,
            }],
            "error": null,
        }),
    )
}

fn snapshot_envelope(sequence: u64, state_version: u64) -> Envelope {
    snapshot_envelope_from_value(sequence, state_version, snapshot_value(state_version))
}

fn snapshot_envelope_from_value(sequence: u64, state_version: u64, snapshot: Value) -> Envelope {
    wire_envelope(
        sequence,
        state_version,
        "snapshot",
        json!({"snapshot": snapshot}),
    )
}

fn event_presentation(snapshot: &Value) -> Value {
    let screen_meta = |name: &str| {
        json!({
            "freshness": snapshot[name]["freshness"].clone(),
            "as_of_utc": snapshot[name]["as_of_utc"].clone(),
            "source": snapshot[name]["source"].clone(),
            "error": snapshot[name]["error"].clone(),
        })
    };
    json!({
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
    })
}

fn timeline_event_envelope(sequence: u64, state_version: u64) -> Envelope {
    timeline_event_with_header(sequence, state_version, None)
}

fn timeline_event_with_header(sequence: u64, state_version: u64, regime: Option<&str>) -> Envelope {
    let mut snapshot = snapshot_value(1);
    if let Some(regime) = regime {
        snapshot["shell"]["header"]["regime_label"] = json!(regime);
    }
    let mut row = snapshot["timeline"]["rows"][0].clone();
    row["summary"] = json!("production partial event");
    wire_envelope(
        sequence,
        state_version,
        "event",
        json!({
            "entity_type": "timeline-row",
            "entity_id": row["event_id"].clone(),
            "operation": "upsert",
            "entity": row,
            "targets": ["timeline.rows"],
            "presentation": event_presentation(&snapshot),
        }),
    )
}

fn alert_event_envelope(sequence: u64, state_version: u64) -> Envelope {
    let snapshot = snapshot_value(1);
    alert_event_from_snapshot(sequence, state_version, &snapshot)
}

fn alert_event_from_snapshot(sequence: u64, state_version: u64, snapshot: &Value) -> Envelope {
    wire_envelope(
        sequence,
        state_version,
        "event",
        json!({
            "entity_type": "alert-row",
            "entity_id": "alert:render-cache",
            "operation": "upsert",
            "entity": {
                "alert_id": "alert:render-cache",
                "severity": "waiting",
                "summary": "Render cache alert",
                "created_at_utc": "2026-08-03T00:00:00Z",
                "resolved_at_utc": null,
            },
            "targets": ["shell.alerts"],
            "presentation": event_presentation(snapshot),
        }),
    )
}

fn agent_event_from_snapshot(sequence: u64, state_version: u64, snapshot: &Value) -> Envelope {
    let row = snapshot["agents"]["rows"][0].clone();
    wire_envelope(
        sequence,
        state_version,
        "event",
        json!({
            "entity_type": "agent-card",
            "entity_id": row["work_id"].clone(),
            "operation": "upsert",
            "entity": row,
            "targets": ["agents.rows"],
            "presentation": event_presentation(snapshot),
        }),
    )
}

fn set_first_timeline_summary(state: &mut AppState, summary: &str) {
    let mut value = serde_json::to_value(state.snapshot.take().unwrap()).unwrap();
    value["timeline"]["rows"][0]["summary"] = json!(summary);
    state.snapshot = Some(serde_json::from_value(value).unwrap());
}

fn buffer_text(buffer: &Buffer) -> String {
    buffer.content.iter().map(|cell| cell.symbol()).collect()
}

#[derive(Clone, Copy, Debug)]
enum FailurePoint {
    Draw,
    Flush,
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct ProbeError(&'static str);

impl fmt::Display for ProbeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.0)
    }
}

impl Error for ProbeError {}

#[derive(Debug)]
struct ProbeBackend {
    inner: TestBackend,
    fail_draws_remaining: usize,
    fail_flushes_remaining: usize,
    clear_calls: usize,
    draw_attempts: usize,
    writes: Vec<(u16, u16)>,
}

impl ProbeBackend {
    fn new(width: u16, height: u16) -> Self {
        Self {
            inner: TestBackend::new(width, height),
            fail_draws_remaining: 0,
            fail_flushes_remaining: 0,
            clear_calls: 0,
            draw_attempts: 0,
            writes: Vec::new(),
        }
    }

    fn buffer(&self) -> &Buffer {
        self.inner.buffer()
    }

    fn resize(&mut self, width: u16, height: u16) {
        self.inner.resize(width, height);
    }

    fn fail_once(&mut self, point: FailurePoint) {
        self.fail_times(point, 1);
    }

    fn fail_times(&mut self, point: FailurePoint, count: usize) {
        match point {
            FailurePoint::Draw => self.fail_draws_remaining = count,
            FailurePoint::Flush => self.fail_flushes_remaining = count,
        }
    }

    fn reset_probe(&mut self) {
        self.clear_calls = 0;
        self.draw_attempts = 0;
        self.writes.clear();
    }
}

impl Backend for ProbeBackend {
    type Error = ProbeError;

    fn draw<'a, I>(&mut self, content: I) -> Result<(), Self::Error>
    where
        I: Iterator<Item = (u16, u16, &'a Cell)>,
    {
        self.draw_attempts += 1;
        if self.fail_draws_remaining > 0 {
            self.fail_draws_remaining -= 1;
            return Err(ProbeError("draw"));
        }
        let cells = content.collect::<Vec<_>>();
        self.writes.extend(cells.iter().map(|(x, y, _)| (*x, *y)));
        infallible(self.inner.draw(cells.into_iter()));
        Ok(())
    }

    fn hide_cursor(&mut self) -> Result<(), Self::Error> {
        infallible(self.inner.hide_cursor());
        Ok(())
    }

    fn show_cursor(&mut self) -> Result<(), Self::Error> {
        infallible(self.inner.show_cursor());
        Ok(())
    }

    fn get_cursor_position(&mut self) -> Result<Position, Self::Error> {
        Ok(infallible(self.inner.get_cursor_position()))
    }

    fn set_cursor_position<P: Into<Position>>(&mut self, position: P) -> Result<(), Self::Error> {
        infallible(self.inner.set_cursor_position(position));
        Ok(())
    }

    fn clear(&mut self) -> Result<(), Self::Error> {
        self.clear_calls += 1;
        infallible(self.inner.clear());
        Ok(())
    }

    fn clear_region(&mut self, clear_type: ClearType) -> Result<(), Self::Error> {
        self.clear_calls += 1;
        infallible(self.inner.clear_region(clear_type));
        Ok(())
    }

    fn size(&self) -> Result<Size, Self::Error> {
        Ok(infallible(self.inner.size()))
    }

    fn window_size(&mut self) -> Result<WindowSize, Self::Error> {
        Ok(infallible(self.inner.window_size()))
    }

    fn flush(&mut self) -> Result<(), Self::Error> {
        if self.fail_flushes_remaining > 0 {
            self.fail_flushes_remaining -= 1;
            return Err(ProbeError("flush"));
        }
        infallible(self.inner.flush());
        Ok(())
    }
}

fn infallible<T>(result: Result<T, Infallible>) -> T {
    match result {
        Ok(value) => value,
        Err(error) => match error {},
    }
}
