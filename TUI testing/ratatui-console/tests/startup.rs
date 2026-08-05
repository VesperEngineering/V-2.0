use std::ffi::OsString;
use std::os::windows::ffi::OsStringExt;
use std::process::Command;

use serde_json::{Value, json};
use vesper_ratatui_console::app::App;
use vesper_ratatui_console::contract::Envelope;
use vesper_ratatui_console::controls::ControlOverlay;
use vesper_ratatui_console::input::InputEvent;
use vesper_ratatui_console::screens::DetailKind;
use vesper_ratatui_console::startup::{StartupIntent, parse_startup_args};
use vesper_ratatui_console::state::{
    AccessState, AppState, ClientAction, LocalMode, ReduceOutcome, Screen,
};

fn parse(arguments: &[&str]) -> Result<StartupIntent, impl std::fmt::Debug + std::fmt::Display> {
    parse_startup_args(arguments.iter().map(OsString::from))
}

fn envelope(sequence: u64, message_type: &str, payload: Value) -> Envelope {
    serde_json::from_value(json!({
        "schema_version": 1,
        "message_id": format!("server:{sequence}"),
        "sequence": sequence,
        "state_version": 0,
        "timestamp_utc": "2026-08-03T00:00:00Z",
        "message_type": message_type,
        "payload": payload,
    }))
    .expect("valid startup test envelope")
}

fn server_hello() -> Envelope {
    envelope(
        1,
        "server-hello",
        json!({"server_version":"0.1.0", "requires_setup":false}),
    )
}

fn auth_result() -> Envelope {
    envelope(
        2,
        "auth-result",
        json!({"success":true, "access_state":"viewer", "reason":null}),
    )
}

fn snapshot(sequence: u64, alert_id: Option<&str>, severity: &str) -> Envelope {
    let mut snapshot: Value = serde_json::from_slice(include_bytes!(
        "../../contracts/v1/console_snapshot_empty_command_specs.json"
    ))
    .expect("valid shared snapshot fixture");
    snapshot["risk"]["alerts"] = match alert_id {
        Some(alert_id) => json!([{
            "alert_id": alert_id,
            "severity": severity,
            "summary": "Startup alert detail",
            "created_at_utc": "2026-08-03T00:00:00Z",
            "resolved_at_utc": if severity == "resolved" {
                json!("2026-08-03T00:01:00Z")
            } else {
                Value::Null
            }
        }]),
        None => json!([]),
    };
    envelope(sequence, "snapshot", json!({"snapshot":snapshot}))
}

fn stale_cache_snapshot(sequence: u64, alert_id: &str) -> Envelope {
    let mut value = serde_json::to_value(snapshot(sequence, Some(alert_id), "urgent")).unwrap();
    let snapshot = &mut value["payload"]["snapshot"];
    snapshot["shell"]["header"]["qwen_state"] = json!("STALE CACHE");
    snapshot["command_specs"] = json!([]);
    for capability in snapshot["shell"]["capabilities"]
        .as_array_mut()
        .expect("capability array")
    {
        capability["state"] = json!("disabled");
        capability["reason"] = json!("Cached state cannot authorize actions.");
    }
    serde_json::from_value(value).unwrap()
}

fn unavailable_snapshot(sequence: u64) -> Envelope {
    let mut value = serde_json::to_value(snapshot(sequence, None, "urgent")).unwrap();
    let risk = &mut value["payload"]["snapshot"]["risk"];
    risk["freshness"] = json!("unavailable");
    risk["as_of_utc"] = Value::Null;
    risk["error"] = json!("Risk source unavailable.");
    serde_json::from_value(value).unwrap()
}

fn omitted_alert_snapshot(sequence: u64) -> Envelope {
    let mut value = serde_json::to_value(snapshot(sequence, None, "urgent")).unwrap();
    value["payload"]["snapshot"]["window_omissions"] = json!([{
        "target": "risk.alerts",
        "omitted_count": 1
    }]);
    serde_json::from_value(value).unwrap()
}

fn alert_app(alert_id: &str) -> App {
    let intent = parse(&["--alert-id", alert_id]).unwrap();
    App::new_with_startup_intent(AppState::locked(), intent)
}

fn authenticate(app: &mut App) {
    assert_eq!(app.reduce(server_hello()), Ok(ReduceOutcome::Changed));
    assert!(
        app.handle_input(InputEvent::Char('p'))
            .foundation_actions
            .is_empty()
    );
    let effect = app.handle_input(InputEvent::Enter);
    assert!(matches!(
        effect.foundation_actions.as_slice(),
        [ClientAction::Authenticate(_)]
    ));
    assert_eq!(
        app.reduce(auth_result()),
        Ok(ReduceOutcome::RequestSnapshot)
    );
}

#[test]
fn startup_accepts_only_dashboard_or_one_safe_alert_id() {
    assert_eq!(parse(&[]).unwrap(), StartupIntent::Dashboard);

    let StartupIntent::Alert(alert_id) = parse(&["--alert-id", "alert:high-1"]).unwrap() else {
        panic!("expected alert launch intent");
    };
    assert_eq!(alert_id.as_str(), "alert:high-1");
}

#[test]
fn startup_rejects_every_other_argument_shape_without_echoing_values() {
    for arguments in [
        vec!["--alert-id"],
        vec!["--alert-id=alert:1"],
        vec!["--other", "alert:1"],
        vec!["--alert-id", ""],
        vec!["--alert-id", " alert:1"],
        vec!["--alert-id", "alert/1"],
        vec!["--alert-id", "SENSITIVE value"],
        vec!["--alert-id", "alert:1", "extra"],
        vec!["--alert-id", "alert:1", "--alert-id", "alert:2"],
    ] {
        let error = parse(&arguments).expect_err("invalid startup arguments must fail closed");
        let rendered = format!("{error:?} {error}");
        assert!(!rendered.contains("SENSITIVE"));
        assert!(!rendered.contains("alert:1"));
        assert!(!rendered.contains("alert:2"));
    }

    let oversized = format!("a{}", "x".repeat(128));
    assert!(
        parse_startup_args([OsString::from("--alert-id"), OsString::from(oversized),]).is_err()
    );

    let non_unicode = OsString::from_wide(&[0xD800]);
    assert!(parse_startup_args([OsString::from("--alert-id"), non_unicode]).is_err());
}

#[test]
fn binary_entrypoint_parses_the_local_intent_before_running_the_console() {
    let source = include_str!("../src/main.rs");

    assert!(source.contains("parse_startup_args("));
    assert!(source.contains("std::env::args_os().skip(1)"));
    assert!(source.contains("run_with_startup_intent(intent)"));
}

#[test]
fn binary_rejects_invalid_startup_arguments_without_echoing_them() {
    let output = Command::new(env!("CARGO_BIN_EXE_vesper-ratatui-console"))
        .args(["--alert-id", "alert:SENSITIVE", "extra"])
        .output()
        .expect("run console entrypoint");

    assert!(!output.status.success());
    assert!(output.stdout.is_empty());
    let stderr = String::from_utf8(output.stderr).expect("UTF-8 startup error");
    assert_eq!(
        stderr.trim_end(),
        "V20 console did not start: invalid startup request"
    );
    assert!(!stderr.contains("alert:SENSITIVE"));
}

#[test]
fn startup_alert_stays_redacted_and_locked_until_authentication_and_snapshot() {
    let mut app = alert_app("alert:SENSITIVE");

    assert!(!format!("{app:?}").contains("alert:SENSITIVE"));
    assert_eq!(app.state().access, AccessState::Locked);
    assert_eq!(app.state().screen, Screen::Impact);
    authenticate(&mut app);

    assert_eq!(app.state().access, AccessState::Viewer);
    assert!(app.state().snapshot.is_none());
    assert_eq!(app.state().screen, Screen::Impact);
    assert_eq!(app.state().mode, LocalMode::Browse);
}

#[test]
fn startup_alert_waits_through_cache_then_opens_the_exact_fresh_alert_as_viewer() {
    let mut app = alert_app("alert:exact");
    authenticate(&mut app);

    assert_eq!(
        app.reduce(stale_cache_snapshot(3, "alert:exact")),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(app.state().screen, Screen::Impact);
    assert_eq!(app.state().mode, LocalMode::Browse);

    assert_eq!(
        app.reduce(snapshot(4, Some("alert:exact"), "urgent")),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(app.state().access, AccessState::Viewer);
    assert_eq!(app.state().screen, Screen::RiskApprovals);
    assert_eq!(app.state().mode, LocalMode::Open);
    let screen = app.state().screen_state();
    assert_eq!(screen.narrow_panel, 2);
    assert_eq!(screen.selected_id.as_deref(), Some("alert:exact"));
    assert_eq!(screen.selected_kind, Some(DetailKind::Alert));
    assert!(screen.detail_open);
    assert!(
        app.handle_input(InputEvent::Tick(std::time::Duration::ZERO))
            .foundation_actions
            .is_empty()
    );
}

#[test]
fn startup_alert_opens_a_resolved_row_without_dismissing_or_taking_control() {
    let mut app = alert_app("alert:resolved");
    authenticate(&mut app);

    assert_eq!(
        app.reduce(snapshot(3, Some("alert:resolved"), "resolved")),
        Ok(ReduceOutcome::Changed)
    );

    assert_eq!(app.state().access, AccessState::Viewer);
    assert_eq!(
        app.state().screen_state().selected_id.as_deref(),
        Some("alert:resolved")
    );
    assert_eq!(app.state().mode, LocalMode::Open);
}

#[test]
fn missing_or_unavailable_startup_alert_shows_a_generic_persistent_notice() {
    for snapshot in [snapshot(3, None, "urgent"), unavailable_snapshot(3)] {
        let mut app = alert_app("alert:not-present");
        authenticate(&mut app);

        assert_eq!(app.reduce(snapshot), Ok(ReduceOutcome::Changed));
        assert_eq!(app.state().access, AccessState::Viewer);
        assert_eq!(app.state().mode, LocalMode::Menu);
        let Some(ControlOverlay::DisabledReason { label, reason }) = app.state().control_overlay()
        else {
            panic!("missing alert must show a persistent local notice");
        };
        assert_eq!(label, "Notification target unavailable");
        assert!(!label.contains("not-present"));
        assert!(!reason.contains("not-present"));
        assert!(
            app.handle_input(InputEvent::Tick(std::time::Duration::ZERO))
                .foundation_actions
                .is_empty()
        );
        assert!(app.state().control_overlay().is_some());
    }
}

#[test]
fn omitted_startup_alert_is_not_misreported_as_absent() {
    let mut app = alert_app("alert:outside-window");
    authenticate(&mut app);

    assert_eq!(
        app.reduce(omitted_alert_snapshot(3)),
        Ok(ReduceOutcome::Changed)
    );
    let Some(ControlOverlay::DisabledReason { reason, .. }) = app.state().control_overlay() else {
        panic!("omitted alert must show a local notice");
    };
    assert_eq!(reason, "The alert is outside the current dashboard window.");
}
