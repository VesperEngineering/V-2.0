use ratatui::Terminal;
use ratatui::backend::TestBackend;
use ratatui::buffer::Buffer;
use serde_json::{Value, json};

mod contract {
    pub use vesper_ratatui_console::contract::*;
}

mod screens {
    pub use vesper_ratatui_console::screens::{DetailKind, ScreenState};
}

mod state {
    pub use vesper_ratatui_console::state::Screen;
}

mod ui {
    pub use vesper_ratatui_console::ui::format_eastern_time;
}

#[path = "../src/screens/detail.rs"]
mod detail;

use contract::ConsoleSnapshot;
use detail::render_direct_detail;
use screens::{DetailKind, ScreenState};
use state::Screen;

fn snapshot_value() -> Value {
    serde_json::from_slice(include_bytes!(
        "../../contracts/v1/console_snapshot_empty_command_specs.json"
    ))
    .expect("valid shared console snapshot")
}

fn snapshot(value: Value) -> ConsoleSnapshot {
    serde_json::from_value(value).expect("valid detail snapshot")
}

fn render(snapshot: &ConsoleSnapshot, screen: Screen, selected_id: &str) -> Buffer {
    let state = ScreenState {
        selected_id: Some(selected_id.to_owned()),
        detail_open: true,
        ..ScreenState::default()
    };
    let backend = TestBackend::new(140, 40);
    let mut terminal = Terminal::new(backend).expect("detail terminal");
    terminal
        .draw(|frame| render_direct_detail(frame, frame.area(), snapshot, screen, &state))
        .expect("draw direct detail");
    terminal.backend().buffer().clone()
}

fn render_typed(
    snapshot: &ConsoleSnapshot,
    screen: Screen,
    selected_id: &str,
    selected_kind: DetailKind,
) -> Buffer {
    let state = ScreenState {
        selected_id: Some(selected_id.to_owned()),
        selected_kind: Some(selected_kind),
        detail_open: true,
        ..ScreenState::default()
    };
    let backend = TestBackend::new(140, 40);
    let mut terminal = Terminal::new(backend).expect("detail terminal");
    terminal
        .draw(|frame| render_direct_detail(frame, frame.area(), snapshot, screen, &state))
        .expect("draw typed direct detail");
    terminal.backend().buffer().clone()
}

fn buffer_text(buffer: &Buffer) -> String {
    let area = buffer.area;
    (0..area.height)
        .map(|y| {
            (0..area.width)
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n")
}

#[test]
fn direct_detail_resolves_every_selectable_row_type() {
    let snapshot = snapshot(snapshot_value());
    let cases = [
        (
            Screen::Orders,
            "order:1",
            "ORDER DETAIL",
            "BROKER ORDER ID: paper-order-1",
        ),
        (
            Screen::Orders,
            "fill:1",
            "ORDER FILL DETAIL",
            "PRICE: 100.25",
        ),
        (
            Screen::Orders,
            "work:1",
            "RECONCILIATION AGENT DETAIL",
            "AGENT: portfolio-research",
        ),
        (
            Screen::Orders,
            "event:1",
            "ORDER HISTORY DETAIL",
            "SUMMARY: AAPL review started",
        ),
        (
            Screen::ModelsRegime,
            "model:active",
            "MODEL OPINION DETAIL",
            "REGIME: risk-on",
        ),
        (
            Screen::ModelsRegime,
            "candidate:1",
            "MODEL CANDIDATE DETAIL",
            "FAMILY: approved-family",
        ),
        (
            Screen::ModelsRegime,
            "metric:cpu",
            "MODEL METRIC DETAIL",
            "VALUE: 12.5000 percent",
        ),
        (
            Screen::ModelsRegime,
            "evidence:1",
            "MODEL EVIDENCE DETAIL",
            "SHA256: aaaaaaaaaaaa",
        ),
        (
            Screen::RiskApprovals,
            "limit:concentration",
            "RISK LIMIT DETAIL",
            "CURRENT: 0.10",
        ),
        (
            Screen::RiskApprovals,
            "approval:1",
            "APPROVAL DETAIL",
            "REASON: Review required",
        ),
        (
            Screen::RiskApprovals,
            "alert:1",
            "RISK ALERT DETAIL",
            "SUMMARY: Approval waiting",
        ),
        (
            Screen::RiskApprovals,
            "metric:cpu",
            "RISK METRIC DETAIL",
            "VALUE: 12.5000 percent",
        ),
        (
            Screen::DataEvidence,
            "source:massive",
            "DATA SOURCE DETAIL",
            "COVERAGE: S&P 500",
        ),
        (
            Screen::DataEvidence,
            "evidence:1",
            "DATA EVIDENCE DETAIL",
            "SHA256: aaaaaaaaaaaa",
        ),
        (
            Screen::Memory,
            "memory:1",
            "MEMORY DETAIL",
            "SUMMARY: Use controller truth.",
        ),
        (
            Screen::Memory,
            "event:1",
            "MEMORY HISTORY DETAIL",
            "SUMMARY: AAPL review started",
        ),
        (
            Screen::System,
            "service:qwen",
            "SERVICE DETAIL",
            "STATE: RUNNING",
        ),
        (
            Screen::System,
            "metric:cpu",
            "SYSTEM METRIC DETAIL",
            "VALUE: 12.5000 percent",
        ),
        (
            Screen::System,
            "repository:v20",
            "REPOSITORY DETAIL",
            "BRANCH: codex/vesper/ratatui-console",
        ),
    ];

    for (screen, selected_id, title, fact) in cases {
        let text = buffer_text(&render(&snapshot, screen, selected_id));
        assert!(
            text.contains(title),
            "missing title {title} for {selected_id}\n{text}"
        );
        assert!(
            text.contains(fact),
            "missing fact {fact} for {selected_id}\n{text}"
        );
        assert!(
            text.contains("SCREEN SOURCE: fixture"),
            "missing source for {selected_id}\n{text}"
        );
        assert!(
            text.contains("SCREEN FRESHNESS: FRESH"),
            "missing freshness for {selected_id}\n{text}"
        );
        assert!(
            text.contains("SCREEN ERROR: NONE"),
            "missing error state for {selected_id}\n{text}"
        );
    }
}

#[test]
fn direct_detail_sanitizes_server_text_and_formats_eastern_time() {
    let mut value = snapshot_value();
    value["risk"]["source"] = json!("fixture\rspoof\u{200b}");
    value["risk"]["approvals"][0]["reason"] = json!("Review\rspoof\u{2066}");
    let snapshot = snapshot(value);

    let text = buffer_text(&render(&snapshot, Screen::RiskApprovals, "approval:1"));

    assert!(text.contains("SCREEN SOURCE: fixture?spoof?"), "{text}");
    assert!(text.contains("REASON: Review?spoof?"), "{text}");
    assert!(text.contains("2026-08-02 20:00:00 EDT"), "{text}");
    assert!(!text.contains('\r'), "{text}");
    assert!(!text.contains('\u{200b}'), "{text}");
    assert!(!text.contains('\u{2066}'), "{text}");
}

#[test]
fn direct_detail_bounds_collection_output_and_reports_omissions() {
    let mut value = snapshot_value();
    value["data"]["sources"][0]["consumers"] = Value::Array(
        (0..12)
            .map(|index| json!(format!("consumer-{index}")))
            .collect(),
    );
    let snapshot = snapshot(value);

    let text = buffer_text(&render(&snapshot, Screen::DataEvidence, "source:massive"));

    assert!(text.contains("consumer-0"), "{text}");
    assert!(text.contains("+4 more"), "{text}");
    assert!(!text.contains("consumer-8"), "{text}");
}

#[test]
fn direct_detail_fails_visibly_when_selected_id_is_missing() {
    let snapshot = snapshot(snapshot_value());
    let text = buffer_text(&render(&snapshot, Screen::System, "service:missing"));

    assert!(text.contains("DIRECT DETAIL UNAVAILABLE"), "{text}");
    assert!(text.contains("service:missing"), "{text}");
    assert!(
        text.contains("not present in the current SYSTEM snapshot"),
        "{text}"
    );
}

#[test]
fn resolved_alert_without_timestamp_reports_unavailable_resolution_time() {
    let mut value = snapshot_value();
    value["risk"]["alerts"][0]["severity"] = json!("resolved");
    value["risk"]["alerts"][0]["resolved_at_utc"] = Value::Null;
    let snapshot = snapshot(value);

    let text = buffer_text(&render(&snapshot, Screen::RiskApprovals, "alert:1"));

    assert!(
        text.contains("RESOLVED: RESOLUTION TIME UNAVAILABLE"),
        "{text}"
    );
    assert!(!text.contains("NOT RESOLVED"), "{text}");
}

#[test]
fn direct_detail_uses_the_typed_target_when_safe_ids_collide() {
    let mut value = snapshot_value();
    value["risk"]["approvals"][0]["approval_id"] = json!("duplicate:1");
    value["risk"]["limits"][0]["limit_id"] = json!("duplicate:1");
    let snapshot = snapshot(value);

    let text = buffer_text(&render_typed(
        &snapshot,
        Screen::RiskApprovals,
        "duplicate:1",
        DetailKind::Approval,
    ));

    assert!(text.contains("APPROVAL DETAIL"), "{text}");
    assert!(!text.contains("RISK LIMIT DETAIL"), "{text}");
}

#[test]
fn direct_detail_exposes_deep_audit_fields_and_bounded_raw_logs() {
    let mut value = snapshot_value();
    value["risk"]["limits"][0]["proposed_value"] = json!("0.12");
    value["risk"]["limits"][0]["proposal_reason"] = json!("Reviewed concentration change.");
    value["risk"]["limits"][0]["review_state"] = json!("pending");
    value["risk"]["limits"][0]["evidence_ids"] = json!(["evidence:1"]);
    value["data"]["evidence"][0]["raw_log_id"] = json!("log:data");
    value["data"]["evidence"][0]["raw_log_excerpt"] = Value::Array(
        (0..10)
            .map(|index| json!(format!("bounded raw line {index}")))
            .collect(),
    );
    value["data"]["evidence"][0]["raw_log_truncated"] = json!(true);
    value["data"]["evidence"][0]["raw_log_next_cursor"] = json!("cursor:raw-next");
    let snapshot = snapshot(value);

    let agent = buffer_text(&render(&snapshot, Screen::Orders, "work:1"));
    for expected in [
        "SESSION ID: session:1",
        "CONTEXT: 25.0%",
        "PLAN STEPS (2)",
        "1. Inspect evidence",
        "ACTIVITY (1)",
        "[STAGE] Review started",
        "EVIDENCE: evidence:1",
        "CHAT AGENT: portfolio-research",
        "WORK-LINKED HISTORY (1)",
        "event:1 | AAPL review started",
    ] {
        assert!(agent.contains(expected), "missing {expected:?}\n{agent}");
    }

    let candidate = buffer_text(&render(&snapshot, Screen::ModelsRegime, "candidate:1"));
    for expected in [
        "FEATURE SET: features:v1",
        "DATA IDENTITY: aaaaaaaaaaaa",
        "EVALUATION CONTRACT: bbbbbbbbbbbb",
        "STATUS REASON: Evaluation is running.",
        "STATUS AT: 2026-08-02 20:00:00 EDT",
    ] {
        assert!(
            candidate.contains(expected),
            "missing {expected:?}\n{candidate}"
        );
    }

    let limit = buffer_text(&render(
        &snapshot,
        Screen::RiskApprovals,
        "limit:concentration",
    ));
    for expected in [
        "PROPOSAL REASON: Reviewed concentration change.",
        "REVIEW: PENDING",
        "EVIDENCE: evidence:1",
    ] {
        assert!(limit.contains(expected), "missing {expected:?}\n{limit}");
    }

    let approval = buffer_text(&render(&snapshot, Screen::RiskApprovals, "approval:1"));
    for expected in [
        "AFFECTED SYMBOLS: AAPL",
        "AAPL: 10.0% -> 11.0%",
        "RISKS: Concentration increases.",
        "EXPECTED CONSEQUENCES: AAPL allocation rises.",
        "BASIS SHA256: cccccccccccc",
        "STALE REASON: NONE",
    ] {
        assert!(
            approval.contains(expected),
            "missing {expected:?}\n{approval}"
        );
    }

    let source = buffer_text(&render(&snapshot, Screen::DataEvidence, "source:massive"));
    assert!(
        source.contains("DEPENDENCIES: split adjustments"),
        "{source}"
    );

    let evidence = buffer_text(&render(&snapshot, Screen::DataEvidence, "evidence:1"));
    for expected in [
        "SYMBOLS: AAPL",
        "AGENTS: portfolio-research",
        "MODELS: model:active",
        "ORDERS: order:1",
        "APPROVALS: approval:1",
        "SOURCES: source:massive",
        "RAW LOG ID: log:data",
        "RAW LOG EXCERPT (10)",
        "bounded raw line 0",
        "RAW LOG LINES OMITTED: 2",
        "TRUNCATED: YES",
        "NEXT CURSOR: cursor:raw-next",
    ] {
        assert!(
            evidence.contains(expected),
            "missing {expected:?}\n{evidence}"
        );
    }
    assert!(
        !evidence.contains("bounded raw line 8"),
        "unbounded raw log\n{evidence}"
    );

    let memory = buffer_text(&render(&snapshot, Screen::Memory, "memory:1"));
    for expected in [
        "USED BY AGENTS: portfolio-research",
        "CHANGE REASON: Retained controller authority rule.",
    ] {
        assert!(memory.contains(expected), "missing {expected:?}\n{memory}");
    }

    let repository = buffer_text(&render(&snapshot, Screen::System, "repository:v20"));
    for expected in [
        "REPOSITORY CHECKS (1)",
        "check:tests | PASS",
        "2026-08-02 20:00:00 EDT",
    ] {
        assert!(
            repository.contains(expected),
            "missing {expected:?}\n{repository}"
        );
    }
}
