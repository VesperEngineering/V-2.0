use std::path::PathBuf;

use ratatui::Terminal;
use ratatui::backend::TestBackend;
use ratatui::buffer::Buffer;
use serde_json::{Value, json};
use vesper_ratatui_console::ConsoleSnapshot;
use vesper_ratatui_console::layout::DisplayMode;
use vesper_ratatui_console::screens::ScreenState;
use vesper_ratatui_console::screens::agents::render_agents;
use vesper_ratatui_console::screens::models::render_models;
use vesper_ratatui_console::screens::timeline::render_timeline;
use vesper_ratatui_console::theme::Theme;

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

fn rich_snapshot_value() -> Value {
    let mut value = snapshot_value();
    value["agents"]["rows"] = json!([
        agent(
            "work:queued-normal",
            "agent:queue",
            "normal queued",
            "queued",
            90,
            false
        ),
        agent(
            "work:running-urgent",
            "agent:run",
            "urgent running",
            "running",
            5,
            true
        ),
        agent(
            "work:queued-urgent",
            "agent:queue",
            "urgent queued",
            "queued",
            1,
            true
        ),
        agent(
            "work:waiting",
            "agent:wait",
            "waiting task",
            "waiting",
            30,
            false
        ),
        agent(
            "work:done",
            "agent:done",
            "completed task",
            "done",
            20,
            false
        ),
        agent(
            "work:failed",
            "agent:failed",
            "failed task",
            "failed",
            100,
            true
        ),
        agent(
            "work:backlog",
            "agent:backlog",
            "backlog task",
            "backlog",
            10,
            false
        )
    ]);
    value["agents"]["history"] = json!([
        event(
            "event:queue",
            true,
            "active",
            "Queued task accepted",
            Some("agent:queue"),
            &["evidence:queue"]
        ),
        event(
            "event:failed",
            true,
            "urgent",
            "Task failed validation",
            Some("agent:failed"),
            &["evidence:failed"]
        )
    ]);
    value["models"]["opinions"] = json!([
        {
            "model_id": "model:macro",
            "regime": "risk-on",
            "confidence": 0.8,
            "as_of_utc": "2026-08-03T00:00:00Z"
        },
        {
            "model_id": "model:micro",
            "regime": "risk-off",
            "confidence": 0.6,
            "as_of_utc": "2026-08-03T00:00:00Z"
        }
    ]);
    value["models"]["candidates"] = json!([
        candidate(
            "candidate:evaluating",
            "evaluating",
            &["evidence:evaluating"]
        ),
        candidate("candidate:failed", "failed", &["evidence:failed"]),
        candidate("candidate:passed", "passed", &["evidence:passed"]),
        candidate("candidate:active", "active", &["evidence:active"])
    ]);
    value["models"]["evidence"] = json!([
        {
            "evidence_id": "evidence:evaluating",
            "evidence_type": "evaluation-receipt",
            "source": "controller",
            "created_at_utc": "2026-08-03T00:00:00Z",
            "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        },
        {
            "evidence_id": "evidence:failed",
            "evidence_type": "gate-receipt",
            "source": "controller",
            "created_at_utc": "2026-08-03T00:00:00Z",
            "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        }
    ]);
    value["timeline"]["rows"] = json!([
        event(
            "event:impact",
            true,
            "urgent",
            "Portfolio impact detected",
            Some("agent:queue"),
            &["evidence:impact"]
        ),
        event(
            "event:routine",
            false,
            "info",
            "Routine health sample",
            None,
            &["evidence:routine"]
        )
    ]);
    value["timeline"]["hidden_event_count"] = json!(7);
    value
}

fn agent(
    work_id: &str,
    agent_id: &str,
    title: &str,
    stage: &str,
    priority: u64,
    urgent: bool,
) -> Value {
    json!({
        "work_id": work_id,
        "agent": agent_id,
        "title": title,
        "stage": stage,
        "priority": priority,
        "urgent": urgent,
        "elapsed_seconds": 65.0,
        "model": "qwen:64k",
        "affected_areas": ["portfolio", "evidence"]
    })
}

fn candidate(candidate_id: &str, status: &str, evidence_ids: &[&str]) -> Value {
    json!({
        "candidate_id": candidate_id,
        "family": "approved-family",
        "strategy": "ml_model",
        "status": status,
        "evidence_ids": evidence_ids,
        "created_at_utc": "2026-08-03T00:00:00Z"
    })
}

fn event(
    event_id: &str,
    impact: bool,
    severity: &str,
    summary: &str,
    agent_id: Option<&str>,
    evidence_ids: &[&str],
) -> Value {
    json!({
        "event_id": event_id,
        "occurred_at_utc": "2026-08-03T00:00:00Z",
        "impact": impact,
        "severity": severity,
        "summary": summary,
        "agent_id": agent_id,
        "symbol": "AAPL",
        "model_id": "model:macro",
        "approval_id": null,
        "order_id": "order:1",
        "evidence_ids": evidence_ids
    })
}

fn snapshot(value: Value) -> ConsoleSnapshot {
    serde_json::from_value(value).expect("strict console snapshot")
}

fn state() -> ScreenState {
    ScreenState {
        theme: Theme::WarmWhite,
        display_mode: DisplayMode::Standard,
        ..ScreenState::default()
    }
}

fn render(width: u16, height: u16, draw: impl FnOnce(&mut ratatui::Frame<'_>)) -> Buffer {
    let backend = TestBackend::new(width, height);
    let mut terminal = Terminal::new(backend).expect("test terminal");
    terminal.draw(draw).expect("draw Task 7 screen");
    terminal.backend().buffer().clone()
}

fn buffer_text(buffer: &Buffer) -> String {
    let area = buffer.area;
    (area.y..area.bottom())
        .map(|y| {
            (area.x..area.right())
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
                .trim_end()
                .to_owned()
        })
        .collect::<Vec<_>>()
        .join("\n")
        .trim_end()
        .to_owned()
}

fn text_position(buffer: &Buffer, needle: &str) -> Option<(u16, u16)> {
    let width = u16::try_from(needle.chars().count()).ok()?;
    for y in buffer.area.y..buffer.area.bottom() {
        for x in buffer.area.x..buffer.area.right().saturating_sub(width) {
            let candidate = (0..width)
                .map(|offset| buffer[(x + offset, y)].symbol())
                .collect::<String>();
            if candidate == needle {
                return Some((x, y));
            }
        }
    }
    None
}

#[test]
fn agents_use_fixed_stage_columns_and_order_urgent_only_inside_real_stage() {
    let snapshot = snapshot(rich_snapshot_value());
    let buffer = render(160, 34, |frame| {
        render_agents(frame, frame.area(), &snapshot.agents, &state());
    });
    let text = buffer_text(&buffer);

    let headings = ["QUEUED", "RUNNING", "WAITING", "DONE"]
        .map(|heading| text_position(&buffer, heading).expect("stage heading"));
    assert!(headings.windows(2).all(|pair| pair[0].0 < pair[1].0));
    let widths = headings
        .windows(2)
        .map(|pair| pair[1].0 - pair[0].0)
        .collect::<Vec<_>>();
    assert!(widths.windows(2).all(|pair| pair[0].abs_diff(pair[1]) <= 1));

    assert!(text.find("urgent queued").unwrap() < text.find("normal queued").unwrap());
    let queued = text_position(&buffer, "urgent queued").unwrap();
    assert!(queued.0 >= headings[0].0 && queued.0 < headings[1].0);
    let running = text_position(&buffer, "urgent running").unwrap();
    assert!(running.0 >= headings[1].0 && running.0 < headings[2].0);

    let failed = text_position(&buffer, "failed task").unwrap();
    assert!(failed.0 >= headings[3].0);
    assert!(
        text.contains("! FAILED"),
        "failed needs a non-color marker\n{text}"
    );
    assert!(text.contains("BACKLOG"));
    assert!(text.contains("backlog task"));
}

#[test]
fn agents_narrow_mode_uses_only_the_selected_stage_panel() {
    let snapshot = snapshot(rich_snapshot_value());
    let narrow = ScreenState {
        narrow_panel: 2,
        ..state()
    };
    let text = buffer_text(&render(76, 24, |frame| {
        render_agents(frame, frame.area(), &snapshot.agents, &narrow);
    }));
    assert!(text.contains("WAITING - PANEL 3/5"));
    assert!(text.contains("waiting task"));
    assert!(!text.contains("urgent running"));
    assert!(!text.contains("failed task"));
    assert!(!text.contains("backlog task"));
}

#[test]
fn task7_screens_follow_the_shell_narrow_breakpoint() {
    let snapshot = snapshot(rich_snapshot_value());
    let agents_state = ScreenState {
        narrow_panel: 4,
        ..state()
    };
    let agents = buffer_text(&render(110, 30, |frame| {
        render_agents(frame, frame.area(), &snapshot.agents, &agents_state);
    }));
    assert!(agents.contains("BACKLOG - PANEL 5/5"));
    assert!(!agents.contains("QUEUED"));

    let models_state = ScreenState {
        narrow_panel: 1,
        ..state()
    };
    let models = buffer_text(&render(110, 32, |frame| {
        render_models(frame, frame.area(), &snapshot.models, &models_state);
    }));
    assert!(models.contains("CANDIDATES - PANEL 2/3"));
    assert!(!models.contains("MODEL OPINIONS"));
}

#[test]
fn agent_chat_and_plan_are_hidden_until_truthful_detail_is_opened() {
    let snapshot = snapshot(rich_snapshot_value());
    let closed = buffer_text(&render(140, 32, |frame| {
        render_agents(frame, frame.area(), &snapshot.agents, &state());
    }));
    assert!(!closed.contains("CHAT"));
    assert!(!closed.contains("PLAN"));

    let detail = ScreenState {
        detail_open: true,
        selected_id: Some("work:queued-urgent".to_owned()),
        ..state()
    };
    let open = buffer_text(&render(120, 28, |frame| {
        render_agents(frame, frame.area(), &snapshot.agents, &detail);
    }));
    for expected in [
        "work:queued-urgent",
        "ELAPSED: 1m 05s",
        "WORK-LINKED HISTORY: UNAVAILABLE",
        "no work_id field",
        "PLAN UNAVAILABLE",
        "CHAT UNAVAILABLE",
    ] {
        assert!(open.contains(expected), "missing {expected}\n{open}");
    }
    for leaked in ["event:queue", "evidence:queue", "Queued task accepted"] {
        assert!(!open.contains(leaked), "leaked {leaked}\n{open}");
    }
    assert!(!open.contains("TASK HISTORY"));
    assert!(!open.contains("tool call"));
    assert!(!open.contains("private reasoning"));
}

#[test]
fn models_keep_final_regime_unavailable_and_label_opinion_consensus() {
    let mut value = rich_snapshot_value();
    let disagree = snapshot(value.clone());
    let text = buffer_text(&render(140, 30, |frame| {
        render_models(frame, frame.area(), &disagree.models, &state());
    }));
    for expected in ["model:macro", "model:micro", "risk-on", "risk-off"] {
        assert!(text.contains(expected), "missing {expected}\n{text}");
    }
    assert!(text.contains("FINAL REGIME: UNAVAILABLE"));
    assert!(text.contains("OPINION CONSENSUS: UNCERTAIN"));

    value["models"]["opinions"][1]["regime"] = json!("risk-on");
    let agree = snapshot(value);
    let text = buffer_text(&render(140, 30, |frame| {
        render_models(frame, frame.area(), &agree.models, &state());
    }));
    assert!(text.contains("FINAL REGIME: UNAVAILABLE"));
    assert!(text.contains("OPINION CONSENSUS: risk-on"));
    assert!(!text.contains("OPINION CONSENSUS: UNCERTAIN"));
}

#[test]
fn models_narrow_mode_focuses_one_complete_selected_panel() {
    let snapshot = snapshot(rich_snapshot_value());
    let candidates = ScreenState {
        narrow_panel: 1,
        ..state()
    };
    let candidates = buffer_text(&render(76, 32, |frame| {
        render_models(frame, frame.area(), &snapshot.models, &candidates);
    }));
    assert!(candidates.contains("CANDIDATES - PANEL 2/3"));
    assert!(candidates.contains("candidate:evaluating"));
    assert!(candidates.contains("candidate:active"));
    assert!(!candidates.contains("MODEL OPINIONS"));
    assert!(!candidates.contains("EVIDENCE & METRICS"));

    let evidence = ScreenState {
        narrow_panel: 2,
        ..state()
    };
    let evidence = buffer_text(&render(76, 32, |frame| {
        render_models(frame, frame.area(), &snapshot.models, &evidence);
    }));
    assert!(evidence.contains("EVIDENCE & METRICS - PANEL 3/3"));
    assert!(evidence.contains("evidence:evaluating"));
    assert!(evidence.contains("evidence:failed"));
    assert!(!evidence.contains("CANDIDATES"));
}

#[test]
fn candidate_rows_show_status_retention_and_real_evidence_ids() {
    let mut value = rich_snapshot_value();
    value["models"]["candidates"] = json!([
        candidate("candidate:training", "training", &["evidence:training"]),
        candidate(
            "candidate:evaluating",
            "evaluating",
            &["evidence:evaluating"]
        ),
        candidate("candidate:failed", "failed", &["evidence:failed"]),
        candidate("candidate:rejected", "rejected", &["evidence:rejected"]),
        candidate("candidate:passed", "passed", &["evidence:passed"]),
        candidate("candidate:active", "active", &["evidence:active"]),
        candidate("candidate:rollback", "rollback", &["evidence:rollback"])
    ]);
    let snapshot = snapshot(value);
    let text = buffer_text(&render(170, 46, |frame| {
        render_models(frame, frame.area(), &snapshot.models, &state());
    }));
    for expected in [
        "STATUS TRAINING | RETENTION POLICY UNAVAILABLE",
        "STATUS EVALUATING | RETENTION POLICY UNAVAILABLE",
        "STATUS FAILED | RETENTION POLICY 30 DAYS",
        "STATUS REJECTED | RETENTION POLICY 30 DAYS",
        "STATUS PASSED | RETENTION POLICY 90 DAYS",
        "STATUS ACTIVE | RETENTION POLICY PERMANENT",
        "STATUS ROLLBACK | RETENTION POLICY PERMANENT",
        "evidence:training",
        "evidence:rollback",
    ] {
        assert!(text.contains(expected), "missing {expected}\n{text}");
    }
}

#[test]
fn timeline_defaults_to_impact_and_reports_filter_and_source_omissions() {
    let snapshot = snapshot(rich_snapshot_value());
    let impact = buffer_text(&render(120, 20, |frame| {
        render_timeline(frame, frame.area(), &snapshot.timeline, &state());
    }));
    assert!(impact.contains("Portfolio impact detected"));
    assert!(!impact.contains("Routine health sample"));
    assert!(impact.contains("EXCLUDED BY FILTER 1"));
    assert!(impact.contains("HIDDEN BY SOURCE 7"));

    let all = ScreenState {
        show_all_events: true,
        ..state()
    };
    let all = buffer_text(&render(120, 20, |frame| {
        render_timeline(frame, frame.area(), &snapshot.timeline, &all);
    }));
    assert!(all.contains("Portfolio impact detected"));
    assert!(all.contains("Routine health sample"));
    assert!(all.contains("EXCLUDED BY FILTER 0"));
    assert!(all.contains("HIDDEN BY SOURCE 7"));
}

#[test]
fn timeline_clamps_an_outdated_scroll_offset_to_retained_rows() {
    let snapshot = snapshot(rich_snapshot_value());
    let scrolled = ScreenState {
        scroll_offset: usize::MAX,
        ..state()
    };
    let text = buffer_text(&render(120, 20, |frame| {
        render_timeline(frame, frame.area(), &snapshot.timeline, &scrolled);
    }));
    assert!(text.contains("Portfolio impact detected"));
    assert!(!text.contains("No impact events reported."));
}

#[test]
fn stale_views_keep_rows_and_exact_reason() {
    let mut value = rich_snapshot_value();
    for view in ["agents", "models", "timeline"] {
        value[view]["freshness"] = json!("stale");
        value[view]["error"] = json!("Last refresh failed; retained prior sample.");
    }
    let snapshot = snapshot(value);
    for (text, retained) in [
        (
            buffer_text(&render(160, 32, |frame| {
                render_agents(frame, frame.area(), &snapshot.agents, &state());
            })),
            "urgent queued",
        ),
        (
            buffer_text(&render(140, 32, |frame| {
                render_models(frame, frame.area(), &snapshot.models, &state());
            })),
            "model:macro",
        ),
        (
            buffer_text(&render(140, 20, |frame| {
                render_timeline(frame, frame.area(), &snapshot.timeline, &state());
            })),
            "Portfolio impact detected",
        ),
    ] {
        assert!(text.contains("STALE"));
        assert!(text.contains("Last refresh failed; retained prior sample."));
        assert!(text.contains(retained));
    }
}

#[test]
fn loading_and_unavailable_keep_panels_but_hide_prior_rows() {
    for freshness in ["loading", "unavailable"] {
        let mut value = rich_snapshot_value();
        for view in ["agents", "models", "timeline"] {
            value[view]["freshness"] = json!(freshness);
            value[view]["as_of_utc"] = Value::Null;
            value[view]["error"] = if freshness == "unavailable" {
                json!("Controller source is unavailable.")
            } else {
                Value::Null
            };
        }
        let snapshot = snapshot(value);
        let agents = buffer_text(&render(140, 30, |frame| {
            render_agents(frame, frame.area(), &snapshot.agents, &state());
        }));
        let models = buffer_text(&render(140, 30, |frame| {
            render_models(frame, frame.area(), &snapshot.models, &state());
        }));
        let timeline = buffer_text(&render(140, 20, |frame| {
            render_timeline(frame, frame.area(), &snapshot.timeline, &state());
        }));

        for title in ["QUEUED", "RUNNING", "WAITING", "DONE", "BACKLOG"] {
            assert!(agents.contains(title), "missing {title}\n{agents}");
        }
        assert!(models.contains("MODEL OPINIONS"));
        assert!(models.contains("CANDIDATES"));
        assert!(models.contains("EVIDENCE & METRICS"));
        assert!(timeline.contains("TIMELINE"));
        for text in [&agents, &models, &timeline] {
            assert!(text.contains(if freshness == "loading" {
                "LOADING"
            } else {
                "UNAVAILABLE"
            }));
        }
        assert!(!agents.contains("urgent queued"));
        assert!(!models.contains("model:macro"));
        assert!(!timeline.contains("Portfolio impact detected"));
        if freshness == "unavailable" {
            assert!(agents.contains("Controller source is unavailable."));
            assert!(models.contains("Controller source is unavailable."));
            assert!(timeline.contains("Controller source is unavailable."));
        }
    }
}

#[test]
fn server_text_is_sanitized_and_times_are_eastern() {
    let mut value = rich_snapshot_value();
    value["agents"]["rows"][0]["title"] = json!("queue\nspoof\u{202e}");
    value["models"]["opinions"][0]["regime"] = json!("risk\tmode\u{2066}");
    value["timeline"]["rows"][0]["summary"] = json!("impact\rspoof\u{200b}");
    let snapshot = snapshot(value);
    let agents = buffer_text(&render(140, 30, |frame| {
        render_agents(frame, frame.area(), &snapshot.agents, &state());
    }));
    let models = buffer_text(&render(140, 30, |frame| {
        render_models(frame, frame.area(), &snapshot.models, &state());
    }));
    let timeline = buffer_text(&render(140, 20, |frame| {
        render_timeline(frame, frame.area(), &snapshot.timeline, &state());
    }));
    assert!(agents.contains("queue?spoof?"));
    assert!(models.contains("risk?mode?"));
    assert!(timeline.contains("impact?spoof?"));
    for text in [&agents, &models, &timeline] {
        assert!(!text.contains('\u{202e}'));
        assert!(!text.contains('\u{2066}'));
        assert!(!text.contains('\u{200b}'));
    }
    assert!(models.contains("2026-08-02 20:00:00 EDT"));
    assert!(timeline.contains("2026-08-02 20:00:00 EDT"));
}

fn composite_snapshot(width: u16, theme: Theme, display_mode: DisplayMode) -> String {
    let snapshot = snapshot(rich_snapshot_value());
    let narrow_panel = if width < 100 {
        match display_mode {
            DisplayMode::Compact => 0,
            DisplayMode::Standard => 1,
            DisplayMode::LargeText => 2,
        }
    } else {
        0
    };
    let state = ScreenState {
        theme,
        display_mode,
        narrow_panel,
        ..ScreenState::default()
    };
    let agents = buffer_text(&render(width, 30, |frame| {
        render_agents(frame, frame.area(), &snapshot.agents, &state);
    }));
    let models = buffer_text(&render(width, 32, |frame| {
        render_models(frame, frame.area(), &snapshot.models, &state);
    }));
    let timeline = buffer_text(&render(width, 18, |frame| {
        render_timeline(frame, frame.area(), &snapshot.timeline, &state);
    }));
    format!("AGENTS\n{agents}\n\nMODELS & REGIME\n{models}\n\nTIMELINE\n{timeline}")
}

macro_rules! task7_snapshot {
    ($test:ident, $name:literal, $width:expr, $theme:expr, $mode:expr) => {
        #[test]
        fn $test() {
            insta::assert_snapshot!($name, composite_snapshot($width, $theme, $mode));
        }
    };
}

task7_snapshot!(
    task7_review_wide_compact_warm,
    "task7_wide_compact_warm",
    150,
    Theme::WarmWhite,
    DisplayMode::Compact
);
task7_snapshot!(
    task7_review_narrow_compact_charcoal,
    "task7_narrow_compact_charcoal",
    76,
    Theme::Charcoal,
    DisplayMode::Compact
);
task7_snapshot!(
    task7_review_wide_standard_charcoal,
    "task7_wide_standard_charcoal",
    150,
    Theme::Charcoal,
    DisplayMode::Standard
);
task7_snapshot!(
    task7_review_narrow_standard_warm,
    "task7_narrow_standard_warm",
    76,
    Theme::WarmWhite,
    DisplayMode::Standard
);
task7_snapshot!(
    task7_review_wide_large_warm,
    "task7_wide_large_warm",
    150,
    Theme::WarmWhite,
    DisplayMode::LargeText
);
task7_snapshot!(
    task7_review_narrow_large_charcoal,
    "task7_narrow_large_charcoal",
    76,
    Theme::Charcoal,
    DisplayMode::LargeText
);
