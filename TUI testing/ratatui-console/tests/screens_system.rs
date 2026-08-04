use ratatui::backend::TestBackend;
use ratatui::buffer::Buffer;
use ratatui::{Frame, Terminal};
use serde_json::json;
use vesper_ratatui_console::contract::{
    ConsoleSnapshot, DataView, Freshness, MemoryView, RiskView, SystemView,
};
use vesper_ratatui_console::screens::data::render_data;
use vesper_ratatui_console::screens::memory::render_memory;
use vesper_ratatui_console::screens::risk::render_risk;
use vesper_ratatui_console::screens::system::render_system;
use vesper_ratatui_console::screens::{DetailKind, ScreenState};

#[test]
fn wide_views_render_contract_facts_with_words_not_color_only() {
    let snapshot = fixture();
    let state = ScreenState::default();

    let risk = render_text(120, 32, |frame| {
        render_risk(frame, frame.area(), &snapshot.risk, &state)
    });
    for expected in [
        "RISK LIMITS",
        "APPROVALS",
        "ALERTS",
        "RISK METRICS",
        "limit:concentration",
        "Current 0.10",
        "Proposed",
        "0.12",
        "[~] PENDING",
        "[~] STALE",
        "[OK] RESOLVED",
        "metric:drawdown",
        "Blocked actions + Circuit breaker: [?] UNAVAILABLE",
    ] {
        assert!(risk.contains(expected), "missing {expected:?}\n{risk}");
    }

    let data = render_text(120, 28, |frame| {
        render_data(frame, frame.area(), &snapshot.data, &state)
    });
    for expected in [
        "DATA SOURCES",
        "EVIDENCE",
        "source:massive",
        "[~] STALE",
        "Age 12.5s",
        "Coverage S&P 500",
        "Consumers",
        "ml_model, momentum",
        "Dependencies [?] UNAVAILABLE",
        "evidence:1",
    ] {
        assert!(data.contains(expected), "missing {expected:?}\n{data}");
    }

    let memory = render_text(120, 28, |frame| {
        render_memory(frame, frame.area(), &snapshot.memory, &state)
    });
    for expected in [
        "CORE MEMORY",
        "ARCHIVE",
        "CHANGE HISTORY",
        "[OK] CORE",
        "[A] ARCHIVED",
        "controller?truth.",
        "Older",
        "reviewed note.",
        "Memory archived?with review",
        "Reasons/agent use: [?] UNAVAILABLE",
    ] {
        assert!(memory.contains(expected), "missing {expected:?}\n{memory}");
    }

    let system = render_text(120, 32, |frame| {
        render_system(frame, frame.area(), &snapshot.system, &state)
    });
    for expected in [
        "SERVICES",
        "SYSTEM METRICS",
        "SOURCE CONTROL",
        "UNSUPPORTED FACTS",
        "[>] RUNNING",
        "[!] FAILED",
        "Branch",
        "codex/vesper/ratatui-console",
        "DIRTY",
        "Unpushed 2",
        "Backup status: [?] UNAVAILABLE",
        "Recovery status: [?] UNAVAILABLE",
        "Notification status: [?] UNAVAILABLE",
    ] {
        assert!(system.contains(expected), "missing {expected:?}\n{system}");
    }
}

#[test]
fn risk_selection_marks_the_typed_row_and_scrolls_only_the_focused_panel() {
    let snapshot = fixture();
    let state = ScreenState {
        scroll_offset: 1,
        selected_id: Some("limit:drawdown".to_owned()),
        selected_kind: Some(DetailKind::RiskLimit),
        narrow_panel: 0,
        ..ScreenState::default()
    };

    let text = render_text(120, 32, |frame| {
        render_risk(frame, frame.area(), &snapshot.risk, &state)
    });

    assert!(text.contains("> RISK LIMITS"), "{text}");
    assert!(text.contains("> [!] VIOLATED limit:drawdown"), "{text}");
    assert!(text.contains("approval:stale"), "{text}");
    assert!(text.contains("alert:resolved"), "{text}");
    assert!(text.contains("metric:drawdown"), "{text}");
}

#[test]
fn data_selection_marks_the_typed_row_and_keeps_unfocused_evidence_at_the_top() {
    let snapshot = fixture();
    let state = ScreenState {
        scroll_offset: 1,
        selected_id: Some("source:missing".to_owned()),
        selected_kind: Some(DetailKind::Source),
        narrow_panel: 0,
        ..ScreenState::default()
    };

    let text = render_text(120, 28, |frame| {
        render_data(frame, frame.area(), &snapshot.data, &state)
    });

    assert!(text.contains("> DATA SOURCES"), "{text}");
    assert!(text.contains("> [?] UNAVAILABLE source:missing"), "{text}");
    assert!(text.contains("evidence:1"), "{text}");
}

#[test]
fn memory_selection_marks_the_typed_row_and_keeps_other_panels_at_the_top() {
    let mut snapshot = fixture();
    snapshot.memory.rows.push(
        serde_json::from_value(json!({
            "memory_id":"memory:second",
            "status":"core",
            "summary":"Second core note.",
            "evidence_ids":[],
            "updated_at_utc":"2026-07-16T12:34:56Z"
        }))
        .expect("valid memory row"),
    );
    let state = ScreenState {
        scroll_offset: 1,
        selected_id: Some("memory:second".to_owned()),
        selected_kind: Some(DetailKind::Memory),
        narrow_panel: 0,
        ..ScreenState::default()
    };

    let text = render_text(120, 28, |frame| {
        render_memory(frame, frame.area(), &snapshot.memory, &state)
    });

    assert!(text.contains("> CORE MEMORY"), "{text}");
    assert!(text.contains("> [OK] CORE memory:second"), "{text}");
    assert!(text.contains("memory:archive"), "{text}");
    assert!(text.contains("Memory archived?with review"), "{text}");
}

#[test]
fn system_selection_marks_the_typed_row_and_scrolls_only_the_focused_panel() {
    let snapshot = fixture();
    let state = ScreenState {
        scroll_offset: 1,
        selected_id: Some("service:worker".to_owned()),
        selected_kind: Some(DetailKind::Service),
        narrow_panel: 0,
        ..ScreenState::default()
    };

    let text = render_text(120, 32, |frame| {
        render_system(frame, frame.area(), &snapshot.system, &state)
    });

    assert!(text.contains("> SERVICES"), "{text}");
    assert!(text.contains("> [!] FAILED service:worker"), "{text}");
    assert!(text.contains("metric:cpu"), "{text}");
    assert!(text.contains("repository:v20"), "{text}");
}

#[test]
fn narrow_panel_focus_uses_screen_state_and_hides_other_panels() {
    let snapshot = fixture();
    let cases: Vec<(usize, &str, &str, String)> = vec![
        (
            1,
            "APPROVALS - PANEL 2/4",
            "RISK LIMITS",
            render_risk_narrow(&snapshot.risk, 1),
        ),
        (
            1,
            "EVIDENCE - PANEL 2/2",
            "DATA SOURCES",
            render_data_narrow(&snapshot.data, 1),
        ),
        (
            2,
            "CHANGE HISTORY - PANEL 3/3",
            "CORE MEMORY",
            render_memory_narrow(&snapshot.memory, 2),
        ),
        (
            3,
            "UNSUPPORTED FACTS - PANEL 4/4",
            "SERVICES",
            render_system_narrow(&snapshot.system, 3),
        ),
    ];
    for (panel, expected, absent, text) in cases {
        assert!(text.contains(expected), "panel {panel}\n{text}");
        assert!(!text.contains(absent), "panel {panel}\n{text}");
    }

    let state = ScreenState {
        narrow_panel: 1,
        ..ScreenState::default()
    };
    let at_shell_breakpoint = render_text(110, 22, |frame| {
        render_data(frame, frame.area(), &snapshot.data, &state)
    });
    assert!(at_shell_breakpoint.contains("EVIDENCE - PANEL 2/2"));
    assert!(!at_shell_breakpoint.contains("DATA SOURCES"));
}

#[test]
fn stale_keeps_last_sample_and_exact_reason_while_unavailable_and_loading_hide_values() {
    let snapshot = fixture();
    let state = ScreenState::default();

    let stale = render_text(100, 24, |frame| {
        render_data(frame, frame.area(), &snapshot.data, &state)
    });
    assert!(
        stale.contains("[~] STALE - Refresh delayed?retrying"),
        "{stale}"
    );
    assert!(stale.contains("Coverage S&P 500"), "{stale}");

    let mut unavailable = snapshot.system.clone();
    unavailable.freshness = Freshness::Unavailable;
    unavailable.as_of_utc = None;
    unavailable.error = Some("System adapter offline\nno cache".to_owned());
    let text = render_text(120, 30, |frame| {
        render_system(frame, frame.area(), &unavailable, &state)
    });
    for panel in [
        "SERVICES",
        "SYSTEM METRICS",
        "SOURCE CONTROL",
        "UNSUPPORTED FACTS",
    ] {
        assert!(text.contains(panel), "{text}");
    }
    assert!(
        text.contains("[?] UNAVAILABLE - System adapter offline?no cache"),
        "{text}"
    );
    assert!(
        !text.contains("service:qwen"),
        "prior values leaked\n{text}"
    );
    assert!(
        !text.contains("codex/vesper/ratatui-console"),
        "prior values leaked\n{text}"
    );

    let mut loading = snapshot.risk.clone();
    loading.freshness = Freshness::Loading;
    loading.as_of_utc = None;
    loading.error = None;
    let text = render_text(120, 30, |frame| {
        render_risk(frame, frame.area(), &loading, &state)
    });
    assert!(
        text.contains("[..] LOADING - Waiting for controller source."),
        "{text}"
    );
    assert!(
        !text.contains("limit:concentration"),
        "prior values leaked\n{text}"
    );
}

#[test]
fn server_text_is_sanitized_and_utc_times_render_in_eastern_time() {
    let snapshot = fixture();
    let state = ScreenState::default();
    let risk = render_text(120, 32, |frame| {
        render_risk(frame, frame.area(), &snapshot.risk, &state)
    });
    assert!(risk.contains("Approval?reason"), "{risk}");
    assert!(risk.contains("2026-01-15 07:34:56 EST"), "{risk}");
    assert!(!risk.contains('\u{202e}'));

    let memory = render_text(120, 28, |frame| {
        render_memory(frame, frame.area(), &snapshot.memory, &state)
    });
    assert!(memory.contains("2026-07-15 08:34:56 EDT"), "{memory}");
    assert!(!memory.contains('\u{2066}'));
    assert!(!memory.contains('\u{fff9}'));
    assert!(memory.contains("controller?truth."), "{memory}");
}

macro_rules! screen_snapshot {
    ($name:ident, $snapshot_name:literal, $width:expr, $height:expr, $body:expr) => {
        #[test]
        fn $name() {
            insta::assert_snapshot!($snapshot_name, $body($width, $height));
        }
    };
}

screen_snapshot!(
    risk_wide_snapshot,
    "screens_system_risk_wide",
    120,
    32,
    |w, h| {
        let snapshot = fixture();
        let state = ScreenState::default();
        render_text(w, h, |frame| {
            render_risk(frame, frame.area(), &snapshot.risk, &state)
        })
    }
);
screen_snapshot!(
    risk_narrow_snapshot,
    "screens_system_risk_narrow",
    78,
    22,
    |_, _| { render_risk_narrow(&fixture().risk, 1) }
);
screen_snapshot!(
    data_wide_snapshot,
    "screens_system_data_wide",
    120,
    28,
    |w, h| {
        let snapshot = fixture();
        let state = ScreenState::default();
        render_text(w, h, |frame| {
            render_data(frame, frame.area(), &snapshot.data, &state)
        })
    }
);
screen_snapshot!(
    data_narrow_snapshot,
    "screens_system_data_narrow",
    78,
    22,
    |_, _| { render_data_narrow(&fixture().data, 0) }
);
screen_snapshot!(
    memory_wide_snapshot,
    "screens_system_memory_wide",
    120,
    28,
    |w, h| {
        let snapshot = fixture();
        let state = ScreenState::default();
        render_text(w, h, |frame| {
            render_memory(frame, frame.area(), &snapshot.memory, &state)
        })
    }
);
screen_snapshot!(
    memory_narrow_snapshot,
    "screens_system_memory_narrow",
    78,
    22,
    |_, _| { render_memory_narrow(&fixture().memory, 2) }
);
screen_snapshot!(
    system_wide_snapshot,
    "screens_system_system_wide",
    120,
    32,
    |w, h| {
        let snapshot = fixture();
        let state = ScreenState::default();
        render_text(w, h, |frame| {
            render_system(frame, frame.area(), &snapshot.system, &state)
        })
    }
);
screen_snapshot!(
    system_narrow_snapshot,
    "screens_system_system_narrow",
    78,
    22,
    |_, _| { render_system_narrow(&fixture().system, 3) }
);

fn render_risk_narrow(view: &RiskView, panel: usize) -> String {
    let state = ScreenState {
        narrow_panel: panel,
        ..ScreenState::default()
    };
    render_text(78, 22, |frame| {
        render_risk(frame, frame.area(), view, &state)
    })
}

fn render_data_narrow(view: &DataView, panel: usize) -> String {
    let state = ScreenState {
        narrow_panel: panel,
        ..ScreenState::default()
    };
    render_text(78, 22, |frame| {
        render_data(frame, frame.area(), view, &state)
    })
}

fn render_memory_narrow(view: &MemoryView, panel: usize) -> String {
    let state = ScreenState {
        narrow_panel: panel,
        ..ScreenState::default()
    };
    render_text(78, 22, |frame| {
        render_memory(frame, frame.area(), view, &state)
    })
}

fn render_system_narrow(view: &SystemView, panel: usize) -> String {
    let state = ScreenState {
        narrow_panel: panel,
        ..ScreenState::default()
    };
    render_text(78, 22, |frame| {
        render_system(frame, frame.area(), view, &state)
    })
}

fn render_text(width: u16, height: u16, draw: impl FnOnce(&mut Frame<'_>)) -> String {
    let backend = TestBackend::new(width, height);
    let mut terminal = Terminal::new(backend).expect("test terminal");
    terminal.draw(draw).expect("render succeeds");
    normalized(terminal.backend().buffer())
}

fn normalized(buffer: &Buffer) -> String {
    let mut lines = Vec::new();
    for y in buffer.area.y..buffer.area.bottom() {
        let mut line = String::new();
        for x in buffer.area.x..buffer.area.right() {
            line.push_str(buffer[(x, y)].symbol());
        }
        lines.push(line.trim_end().to_owned());
    }
    while lines.last().is_some_and(String::is_empty) {
        lines.pop();
    }
    lines.join("\n")
}

fn fixture() -> ConsoleSnapshot {
    let mut value: serde_json::Value = serde_json::from_slice(include_bytes!(
        "../../contracts/v1/console_snapshot_empty_command_specs.json"
    ))
    .expect("shared fixture JSON");
    value["risk"] = json!({
        "freshness": "fresh", "as_of_utc": "2026-01-15T12:34:56Z", "source": "controller-risk", "error": null,
        "limits": [
            {"limit_id":"limit:concentration","current_value":"0.10","proposed_value":"0.12","status":"pending"},
            {"limit_id":"limit:drawdown","current_value":"0.08","proposed_value":null,"status":"violated"}
        ],
        "approvals": [
            {"approval_id":"approval:stale","state":"stale","reason":"Approval\u{202e}reason","evidence_ids":["evidence:1"],"requested_at_utc":"2026-01-15T12:34:56Z"}
        ],
        "alerts": [
            {"alert_id":"alert:resolved","severity":"resolved","summary":"Mismatch repaired","created_at_utc":"2026-01-15T12:00:00Z","resolved_at_utc":"2026-01-15T12:34:56Z"}
        ],
        "metrics": [
            {"metric_id":"metric:drawdown","value":8.0,"unit":"percent","freshness":"stale","observed_at_utc":"2026-01-15T12:34:56Z","error":"Risk refresh delayed"}
        ]
    });
    value["data"] = json!({
        "freshness":"stale","as_of_utc":"2026-07-15T12:34:56Z","source":"controller-data","error":"Refresh delayed\nretrying",
        "sources":[
            {"source_id":"source:massive","freshness":"stale","as_of_utc":"2026-07-15T12:34:56Z","age_seconds":12.5,"coverage":"S&P 500","error":"Late sample","consumers":["ml_model","momentum"]},
            {"source_id":"source:missing","freshness":"unavailable","as_of_utc":null,"age_seconds":null,"coverage":null,"error":"No reviewed adapter","consumers":[]}
        ],
        "evidence":[{"evidence_id":"evidence:1","evidence_type":"receipt","source":"controller","created_at_utc":"2026-07-15T12:34:56Z","sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}]
    });
    value["memory"] = json!({
        "freshness":"fresh","as_of_utc":"2026-07-15T12:34:56Z","source":"controller-memory","error":null,
        "rows":[
            {"memory_id":"memory:core","status":"core","summary":"Use controller\u{fff9}truth.","evidence_ids":["evidence:1"],"updated_at_utc":"2026-07-15T12:34:56Z"},
            {"memory_id":"memory:archive","status":"archived","summary":"Older reviewed note.","evidence_ids":[],"updated_at_utc":"2026-01-15T12:34:56Z"}
        ],
        "history":[{"event_id":"event:memory","occurred_at_utc":"2026-07-15T12:34:56Z","impact":true,"severity":"info","summary":"Memory archived\u{2066}with review","agent_id":null,"symbol":null,"model_id":null,"approval_id":null,"order_id":null,"evidence_ids":["evidence:1"]}]
    });
    value["system"] = json!({
        "freshness":"fresh","as_of_utc":"2026-07-15T12:34:56Z","source":"controller-system","error":null,
        "services":[
            {"service_id":"service:qwen","state":"running","health_reason":null,"observed_at_utc":"2026-07-15T12:34:56Z"},
            {"service_id":"service:worker","state":"failed","health_reason":"Worker\nstopped","observed_at_utc":"2026-01-15T12:34:56Z"}
        ],
        "metrics":[
            {"metric_id":"metric:cpu","value":12.5,"unit":"percent","freshness":"fresh","observed_at_utc":"2026-07-15T12:34:56Z","error":null},
            {"metric_id":"metric:gpu","value":42.0,"unit":"percent","freshness":"stale","observed_at_utc":"2026-07-15T12:34:56Z","error":"Sensor delayed"}
        ],
        "repositories":[
            {"repository_id":"repository:v20","freshness":"fresh","as_of_utc":"2026-07-15T12:34:56Z","source":"git","error":null,"branch":"codex/vesper/ratatui-console","revision":"0123456789abcdef","clean":false,"worktrees":["C:/Users/bgonn/Desktop/v20","C:/tmp/worktree"],"unpushed_commit_count":2},
            {"repository_id":"repository:missing","freshness":"unavailable","as_of_utc":null,"source":"git","error":"Repository unavailable","branch":null,"revision":null,"clean":null,"worktrees":[],"unpushed_commit_count":null}
        ]
    });
    serde_json::from_value(value).expect("valid system screen fixture")
}
