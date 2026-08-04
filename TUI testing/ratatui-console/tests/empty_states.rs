use ratatui::Terminal;
use ratatui::backend::TestBackend;
use serde_json::{Value, json};
use vesper_ratatui_console::contract::ConsoleSnapshot;
use vesper_ratatui_console::state::{AppState, Screen};
use vesper_ratatui_console::ui::render;

#[test]
fn every_fresh_empty_screen_explains_that_no_rows_were_reported() {
    let snapshot = fresh_empty_snapshot();
    let cases: &[(Screen, &[&str])] = &[
        (
            Screen::Impact,
            &[
                "No holdings reported.",
                "No impact events reported.",
                "No agent work reported.",
            ],
        ),
        (
            Screen::Portfolio,
            &[
                "No holdings reported.",
                "No return components reported.",
                "No portfolio metrics reported.",
            ],
        ),
        (
            Screen::Orders,
            &[
                "No orders reported.",
                "No reconciliation tasks reported.",
                "No order history reported.",
            ],
        ),
        (Screen::Agents, &["No tasks reported."]),
        (
            Screen::ModelsRegime,
            &[
                "No model opinions reported.",
                "No model candidates reported.",
                "No metrics reported.",
                "No evidence reported.",
            ],
        ),
        (Screen::Timeline, &["No impact events reported."]),
        (
            Screen::RiskApprovals,
            &[
                "No risk limits reported.",
                "No approvals reported.",
                "No risk alerts reported.",
                "No risk metrics reported.",
            ],
        ),
        (
            Screen::DataEvidence,
            &["No data sources reported.", "No evidence reported."],
        ),
        (
            Screen::Memory,
            &[
                "No core memories reported.",
                "No archived memories reported.",
                "No memory changes reported.",
            ],
        ),
        (
            Screen::System,
            &[
                "No services reported.",
                "No system metrics reported.",
                "No repositories reported.",
            ],
        ),
    ];

    for (screen, expected) in cases {
        let mut state = AppState::controller();
        state.screen = *screen;
        state.snapshot = Some(snapshot.clone());
        let text = render_text(&state);
        for message in *expected {
            assert!(
                text.contains(message),
                "{screen:?} missing {message:?}\n{text}"
            );
        }
    }
}

#[test]
fn fresh_empty_impact_screen_has_a_stable_full_frame() {
    let mut state = AppState::controller();
    state.screen = Screen::Impact;
    state.snapshot = Some(fresh_empty_snapshot());

    insta::assert_snapshot!("fresh_empty_impact_standard_warm", render_text(&state));
}

fn fresh_empty_snapshot() -> ConsoleSnapshot {
    let mut value: Value = serde_json::from_slice(include_bytes!(
        "../../contracts/v1/console_snapshot_empty_command_specs.json"
    ))
    .expect("valid shared console fixture");
    for (view, arrays) in [
        ("impact", &["holdings", "events", "agents"][..]),
        (
            "portfolio",
            &[
                "rows",
                "returns_today",
                "returns_since_rebalance",
                "returns_since_start",
                "metrics",
                "history",
            ][..],
        ),
        ("orders", &["rows", "reconciliation_agents", "history"]),
        ("agents", &["rows", "history"]),
        ("models", &["opinions", "candidates", "metrics", "evidence"]),
        ("timeline", &["rows"]),
        ("risk", &["limits", "approvals", "alerts", "metrics"]),
        ("data", &["sources", "evidence"]),
        ("memory", &["rows", "history"]),
        ("system", &["services", "metrics", "repositories"]),
    ] {
        value[view]["freshness"] = json!("fresh");
        value[view]["error"] = Value::Null;
        for field in arrays {
            value[view][*field] = json!([]);
        }
    }
    value["timeline"]["hidden_event_count"] = json!(0);
    serde_json::from_value(value).expect("valid fresh empty console snapshot")
}

fn render_text(state: &AppState) -> String {
    let backend = TestBackend::new(160, 48);
    let mut terminal = Terminal::new(backend).expect("test terminal");
    terminal
        .draw(|frame| render(frame, state))
        .expect("render succeeds");
    let buffer = terminal.backend().buffer();
    let mut lines = Vec::new();
    for y in buffer.area.y..buffer.area.bottom() {
        let mut line = String::new();
        for x in buffer.area.x..buffer.area.right() {
            line.push_str(buffer[(x, y)].symbol());
        }
        lines.push(line.trim_end().to_owned());
    }
    lines.join("\n")
}
