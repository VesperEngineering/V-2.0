use ratatui::Terminal;
use ratatui::backend::TestBackend;
use ratatui::buffer::Buffer;
use ratatui::layout::Rect;
use ratatui::style::{Color, Modifier};
use serde_json::json;
use vesper_ratatui_console::contract::{Envelope, ShellSnapshot, UtcTimestamp};
use vesper_ratatui_console::input::InputEvent;
use vesper_ratatui_console::layout::{DisplayMode, ViewportClass, shell_layout};
use vesper_ratatui_console::preferences::{LoadedPreferences, UiPreferences};
use vesper_ratatui_console::state::{AppState, Screen};
use vesper_ratatui_console::theme::Theme;
use vesper_ratatui_console::ui::{format_eastern_time, format_eastern_time_for_zone, render};

#[test]
fn shell_layout_is_ordered_bounded_and_uses_the_120_column_breakpoint() {
    let cases = [
        (160, 48, ViewportClass::Wide),
        (120, 36, ViewportClass::Wide),
        (100, 30, ViewportClass::Narrow),
        (80, 24, ViewportClass::Narrow),
    ];

    for mode in [
        DisplayMode::Compact,
        DisplayMode::Standard,
        DisplayMode::LargeText,
    ] {
        for (width, height, expected_viewport) in cases {
            let area = Rect::new(0, 0, width, height);
            let layout = shell_layout(area, mode);

            assert_eq!(layout.viewport, expected_viewport);
            assert_eq!(layout.header.y, area.y);
            assert_eq!(layout.navigation.y, layout.header.bottom());
            assert_eq!(layout.alerts.y, layout.navigation.bottom());
            assert_eq!(layout.body.y, layout.alerts.bottom());
            assert_eq!(layout.input.y, layout.body.bottom());
            assert_eq!(layout.footer.y, layout.input.bottom());
            assert_eq!(layout.footer.bottom(), area.bottom());
            assert!(layout.body.height > 0, "{width}x{height} {mode:?}");

            for region in [
                layout.header,
                layout.navigation,
                layout.alerts,
                layout.body,
                layout.input,
                layout.footer,
            ] {
                assert!(region.x >= area.x);
                assert!(region.y >= area.y);
                assert!(region.right() <= area.right());
                assert!(region.bottom() <= area.bottom());
            }
        }
    }
}

#[test]
fn themes_use_warm_white_charcoal_and_labeled_status_colors_without_blink() {
    let warm = Theme::WarmWhite.palette();
    let charcoal = Theme::Charcoal.palette();

    assert_eq!(warm.background, Color::Rgb(250, 247, 240));
    assert_eq!(warm.foreground, Color::Rgb(38, 38, 38));
    assert_eq!(charcoal.background, Color::Rgb(38, 38, 38));
    assert_eq!(charcoal.foreground, Color::Rgb(250, 247, 240));

    for (foreground, style, color) in [
        (warm.background, warm.urgent, Color::Rgb(155, 28, 28)),
        (warm.background, warm.waiting, Color::Rgb(122, 101, 0)),
        (warm.background, warm.active, Color::Rgb(0, 76, 153)),
        (warm.background, warm.resolved, Color::Rgb(22, 101, 52)),
        (
            charcoal.background,
            charcoal.urgent,
            Color::Rgb(255, 123, 123),
        ),
        (
            charcoal.background,
            charcoal.waiting,
            Color::Rgb(253, 224, 71),
        ),
        (
            charcoal.background,
            charcoal.active,
            Color::Rgb(108, 182, 255),
        ),
        (
            charcoal.background,
            charcoal.resolved,
            Color::Rgb(110, 219, 143),
        ),
    ] {
        assert_eq!(style.fg, Some(foreground));
        assert_eq!(style.bg, Some(color));
        assert!(contrast_ratio(foreground, color) >= 4.5);
        assert!(
            !style
                .add_modifier
                .intersects(Modifier::SLOW_BLINK | Modifier::RAPID_BLINK)
        );
    }
}

#[test]
fn locked_render_hides_a_poisoned_dashboard_snapshot() {
    let mut state = AppState::locked();
    state.snapshot = Some(poisoned_snapshot());

    let text = render_text(80, 24, &state);

    assert!(text.contains("LOCKED"));
    assert!(!text.contains("POISON-SNAPSHOT"));
    assert!(!text.contains("Portfolio"));
    assert!(!text.contains("URGENT"));
}

#[test]
fn eastern_time_uses_windows_zone_rules_across_2026_dst_boundaries() {
    let cases = [
        ("2026-01-15T12:34:56Z", "2026-01-15 07:34:56 EST"),
        ("2026-07-15T12:34:56Z", "2026-07-15 08:34:56 EDT"),
        ("2026-03-08T06:59:59Z", "2026-03-08 01:59:59 EST"),
        ("2026-03-08T07:00:00Z", "2026-03-08 03:00:00 EDT"),
        ("2026-11-01T05:59:59Z", "2026-11-01 01:59:59 EDT"),
        ("2026-11-01T06:00:00Z", "2026-11-01 01:00:00 EST"),
    ];

    for (utc, expected) in cases {
        assert_eq!(format_eastern_time(&timestamp(utc)), expected);
    }
}

#[test]
fn eastern_time_lookup_failure_keeps_canonical_utc_and_is_visible() {
    let utc = timestamp("2026-01-15T12:34:56Z");
    assert_eq!(
        format_eastern_time_for_zone(&utc, "V20 Missing Test Zone"),
        "2026-01-15T12:34:56Z UTC | Eastern time unavailable"
    );
}

#[test]
fn unlocked_shell_has_six_sections_in_exact_order_and_truthful_phase_one_content() {
    let state = AppState::controller();
    let text = normalized_render(120, 36, &state);
    let labels = [
        "┌RUNTIME & MARKET - CONTROLLER",
        "┌NAVIGATION",
        "┌ALERTS",
        "┌SCREEN: Impact",
        "┌AGENT INPUT - DISABLED",
        "┌KEYS & STATUS",
    ];
    let positions = labels.map(|label| {
        text.find(label)
            .unwrap_or_else(|| panic!("missing shell label {label:?}\n{text}"))
    });

    assert!(positions.windows(2).all(|pair| pair[0] < pair[1]));
    assert!(text.contains("MODE UNKNOWN"));
    assert!(text.contains("UNAVAILABLE"));
    assert!(!text.contains("STOPPED"));
    assert!(text.contains("UNAVAILABLE - Phase 1 provides the secure console shell only."));
}

#[test]
fn every_header_field_remains_visible_in_wide_compact_and_narrow_large_text() {
    for (width, height, mode) in [
        (120, 36, DisplayMode::Compact),
        (80, 24, DisplayMode::LargeText),
    ] {
        let mut state = AppState::controller();
        state.snapshot = Some(alert_snapshot("active", "Work remains active."));
        state.set_display_mode(mode);
        let text = normalized_render(width, height, &state);

        for field in [
            "AGE UNAVAILABLE",
            "MARKET Closed",
            "REGIME UNAVAILABLE",
            "CONFIDENCE UNAVAILABLE",
            "PORTFOLIO UNAVAILABLE",
            "REBALANCE UNAVAILABLE",
            "BLOCKERS UNAVAILABLE",
            "AGENT UNAVAILABLE",
            "QWEN UNAVAILABLE",
            "ALERTS ACTIVE 1 / OPEN 1",
        ] {
            assert!(
                text.contains(field),
                "{width}x{height} {mode:?}: {field}\n{text}"
            );
        }

        let missing = normalized_render(width, height, &{
            let mut missing = AppState::controller();
            missing.set_display_mode(mode);
            missing
        });
        for field in [
            "MODE UNKNOWN / UNAVAILABLE",
            "DATA UNAVAILABLE",
            "AGE UNAVAILABLE",
            "MARKET UNAVAILABLE",
            "REGIME UNAVAILABLE",
            "CONFIDENCE UNAVAILABLE",
            "PORTFOLIO UNAVAILABLE",
            "REBALANCE UNAVAILABLE",
            "BLOCKERS UNAVAILABLE",
            "AGENT UNAVAILABLE",
            "QWEN UNAVAILABLE",
            "ALERTS UNAVAILABLE",
        ] {
            assert!(
                missing.contains(field),
                "{width}x{height} missing: {field}\n{missing}"
            );
        }
    }
}

#[test]
fn oversized_header_text_is_bounded_so_later_labels_stay_visible() {
    let mut state = AppState::controller();
    state.snapshot = Some(long_header_snapshot());
    state.set_display_mode(DisplayMode::LargeText);

    let text = normalized_render(80, 24, &state);

    for label in [
        "AGE ",
        "MARKET ",
        "REGIME ",
        "CONFIDENCE ",
        "PORTFOLIO ",
        "REBALANCE ",
        "BLOCKERS ",
        "AGENT ",
        "QWEN ",
    ] {
        assert!(
            text.contains(label),
            "missing bounded label {label:?}\n{text}"
        );
    }
    assert!(text.contains("CONFIDENCE 87.5%"), "{text}");
}

#[test]
fn all_ten_screens_are_truthful_placeholders_in_wide_and_narrow_views() {
    let screens = [
        (Screen::Impact, "Impact"),
        (Screen::Portfolio, "Portfolio"),
        (Screen::Orders, "Orders"),
        (Screen::Agents, "Agents"),
        (Screen::ModelsRegime, "Models & Regime"),
        (Screen::Timeline, "Timeline"),
        (Screen::RiskApprovals, "Risk & Approvals"),
        (Screen::DataEvidence, "Data & Evidence"),
        (Screen::Memory, "Memory"),
        (Screen::System, "System"),
    ];

    for width in [120, 80] {
        for (screen, name) in screens {
            let mut state = AppState::controller();
            state.screen = screen;
            let text = normalized_render(width, if width == 120 { 36 } else { 24 }, &state);
            assert!(text.contains(&format!("SCREEN: {name}")), "{width} {name}");
            assert!(
                text.contains("UNAVAILABLE - Phase 1 provides the secure console shell only."),
                "{width} {name}"
            );
        }
    }
}

#[test]
fn controller_viewer_and_disabled_input_are_explicit() {
    let controller = normalized_render(80, 24, &AppState::controller());
    let viewer = normalized_render(80, 24, &AppState::viewer());

    assert!(controller.contains("CONTROLLER"));
    assert!(!controller.contains("READ ONLY"));
    assert!(viewer.contains("READ ONLY"));
    assert!(!viewer.contains("CONTROLLER"));
    assert!(controller.contains("AGENT INPUT - DISABLED"));
    assert!(viewer.contains("AGENT INPUT - DISABLED"));
    assert!(!controller.contains("Take Control"));
    assert!(!viewer.contains("Take Control"));
    assert!(!controller.contains("Lock TUI"));
    assert!(!viewer.contains("Lock TUI"));
}

#[test]
fn corrupt_preference_state_is_visible_without_rendering_error_details() {
    let mut state = AppState::controller();
    state.apply_loaded_preferences(LoadedPreferences {
        preferences: UiPreferences::default(),
        unavailable_reason: Some("C:\\secret\\preferences.json: corrupt".to_owned()),
    });

    let text = normalized_render(80, 24, &state);

    assert!(text.contains("PREFERENCES UNAVAILABLE"));
    assert!(!text.contains("secret"));
    assert!(!text.contains("corrupt"));
}

#[test]
fn locked_and_first_run_views_defer_preference_warnings_until_unlock() {
    for mut state in [AppState::locked(), AppState::first_run()] {
        state.apply_loaded_preferences(LoadedPreferences {
            preferences: UiPreferences::default(),
            unavailable_reason: Some("corrupt".to_owned()),
        });
        let text = normalized_render(80, 24, &state);
        assert!(!text.contains("PREFERENCES UNAVAILABLE"));
        assert!(!text.contains("NAVIGATION"));
    }
}

#[test]
fn authentication_renders_only_fixed_pending_failed_and_mismatch_feedback() {
    let mut pending = AppState::locked();
    pending.reduce(auth_server_hello(1, false)).unwrap();
    for character in "SENSITIVE".chars() {
        pending.handle(InputEvent::Char(character));
    }
    pending.handle(InputEvent::Enter);
    let pending_text = normalized_render(80, 24, &pending);
    assert!(pending_text.contains("Authentication pending."));
    assert!(!pending_text.contains("SENSITIVE"));

    pending
        .reduce(auth_failure(2, "SERVER-DETAIL-POISON"))
        .unwrap();
    let failed_text = normalized_render(80, 24, &pending);
    assert!(failed_text.contains("Authentication failed. Try again."));
    assert!(!failed_text.contains("SERVER-DETAIL-POISON"));

    let mut mismatch = AppState::locked();
    mismatch.reduce(auth_server_hello(1, true)).unwrap();
    mismatch.handle(InputEvent::Char('a'));
    mismatch.handle(InputEvent::Enter);
    mismatch.handle(InputEvent::Char('b'));
    mismatch.handle(InputEvent::Enter);
    let mismatch_text = normalized_render(80, 24, &mismatch);
    assert!(mismatch_text.contains("Passwords do not match. Re-enter confirmation."));
    assert!(!mismatch_text.contains("Password: a"));
    assert!(!mismatch_text.contains("Password: b"));
}

#[test]
fn narrow_compact_navigation_keeps_all_ten_numbered_entries_visible() {
    let mut state = AppState::controller();
    state.set_display_mode(DisplayMode::Compact);
    let text = normalized_render(80, 24, &state);

    for entry in [
        "1 Imp", "2 Port", "3 Ord", "4 Agt", "5 Mod", "6 Time", "7 Risk", "8 Data", "9 Mem",
        "0 Sys",
    ] {
        assert!(
            text.contains(entry),
            "missing narrow entry {entry:?}\n{text}"
        );
    }
}

#[test]
fn server_text_control_characters_are_sanitized_before_rendering() {
    let mut state = AppState::controller();
    state.snapshot = Some(control_character_snapshot());

    let text = normalized_render(160, 48, &state);

    assert!(!text.contains('\x1b'));
    assert!(!text.contains('\r'));
    assert!(!text.contains('\t'));
    assert!(text.contains("REGIME?RED"));
    assert!(text.contains("AGENT?NAME"));
    assert!(text.contains("ALERT?SUMMARY"));
}

#[test]
fn narrow_alerts_prioritize_urgent_and_header_summarizes_open_alerts() {
    let mut state = AppState::controller();
    state.snapshot = Some(resolved_then_urgent_snapshot());
    state.set_display_mode(DisplayMode::LargeText);

    let text = normalized_render(80, 24, &state);

    assert!(text.contains("ALERTS URGENT 1 / OPEN 1"), "{text}");
    assert!(
        text.contains("[!] URGENT - Immediate review required."),
        "{text}"
    );
    assert!(
        !text.contains("[OK] RESOLVED - Earlier issue repaired."),
        "only one alert row fits, and urgent must occupy it\n{text}"
    );
}

#[test]
fn cjk_and_bidi_server_text_is_cell_bounded_and_cannot_hide_later_labels() {
    let mut state = AppState::controller();
    state.snapshot = Some(wide_and_bidi_snapshot());
    state.set_display_mode(DisplayMode::LargeText);

    let text = normalized_render(80, 24, &state);

    assert!(!text.contains('\u{202e}'));
    assert!(!text.contains('\u{2066}'));
    for label in [
        "MARKET ",
        "CONFIDENCE ",
        "PORTFOLIO ",
        "BLOCKERS ",
        "QWEN ",
        "ALERTS URGENT 1 / OPEN 1",
    ] {
        assert!(
            text.contains(label),
            "missing cell-safe label {label:?}\n{text}"
        );
    }
}

#[test]
fn full_144_combination_matrix_is_bounded_truthful_accessible_and_static() {
    let sizes = [(160, 48), (120, 36), (100, 30), (80, 24)];
    let scenarios = [
        Scenario::Locked,
        Scenario::FirstRun,
        Scenario::Controller,
        Scenario::Viewer,
        Scenario::Urgent,
        Scenario::Resolved,
    ];
    let themes = [Theme::WarmWhite, Theme::Charcoal];
    let modes = [
        DisplayMode::Compact,
        DisplayMode::Standard,
        DisplayMode::LargeText,
    ];
    let mut rendered = 0;

    for (width, height) in sizes {
        for scenario in scenarios {
            for theme in themes {
                for mode in modes {
                    let mut state = scenario.state();
                    state.set_theme(theme);
                    state.set_display_mode(mode);
                    let buffer = render_buffer(width, height, &state);
                    let text = normalized_buffer(&buffer);

                    scenario.assert_semantics(&text);
                    assert_accessible_static_palette(&buffer);
                    assert_eq!(buffer, render_buffer(width, height, &state));
                    rendered += 1;
                }
            }
        }
    }

    assert_eq!(rendered, 144);
}

#[test]
fn status_labels_keep_their_required_palette_colors() {
    let cases = [
        (
            Theme::WarmWhite,
            "urgent",
            "[!] URGENT",
            Color::Rgb(250, 247, 240),
            Color::Rgb(155, 28, 28),
        ),
        (
            Theme::WarmWhite,
            "waiting",
            "[~] WAITING",
            Color::Rgb(250, 247, 240),
            Color::Rgb(122, 101, 0),
        ),
        (
            Theme::WarmWhite,
            "active",
            "[>] ACTIVE",
            Color::Rgb(250, 247, 240),
            Color::Rgb(0, 76, 153),
        ),
        (
            Theme::WarmWhite,
            "resolved",
            "[OK] RESOLVED",
            Color::Rgb(250, 247, 240),
            Color::Rgb(22, 101, 52),
        ),
        (
            Theme::Charcoal,
            "urgent",
            "[!] URGENT",
            Color::Rgb(38, 38, 38),
            Color::Rgb(255, 123, 123),
        ),
    ];
    for (theme, severity, label, foreground, background) in cases {
        let mut state = AppState::controller();
        state.snapshot = Some(alert_snapshot(severity, "Status remains visible."));
        state.set_theme(theme);
        let buffer = render_buffer(120, 36, &state);
        assert_eq!(label_style(&buffer, label), (foreground, background));
        assert_eq!(
            label_style(&buffer, "Status remains visible."),
            (foreground, background),
            "the summary must use the same semantic banner style"
        );
    }
}

macro_rules! golden_test {
    ($function:ident, $name:literal, $scenario:expr, $width:expr, $height:expr, $theme:expr, $mode:expr) => {
        #[test]
        fn $function() {
            let mut state = $scenario.state();
            state.set_theme($theme);
            state.set_display_mode($mode);
            insta::assert_snapshot!($name, normalized_render($width, $height, &state));
        }
    };
}

golden_test!(
    shell_review_locked_wide,
    "locked_wide_compact_warm",
    Scenario::Locked,
    120,
    36,
    Theme::WarmWhite,
    DisplayMode::Compact
);
golden_test!(
    shell_review_locked_narrow,
    "locked_narrow_standard_charcoal",
    Scenario::Locked,
    80,
    24,
    Theme::Charcoal,
    DisplayMode::Standard
);
golden_test!(
    shell_review_first_run_wide,
    "first_run_wide_large_charcoal",
    Scenario::FirstRun,
    120,
    36,
    Theme::Charcoal,
    DisplayMode::LargeText
);
golden_test!(
    shell_review_first_run_narrow,
    "first_run_narrow_compact_warm",
    Scenario::FirstRun,
    80,
    24,
    Theme::WarmWhite,
    DisplayMode::Compact
);
golden_test!(
    shell_review_controller_wide,
    "controller_wide_standard_warm",
    Scenario::Controller,
    120,
    36,
    Theme::WarmWhite,
    DisplayMode::Standard
);
golden_test!(
    shell_review_controller_narrow,
    "controller_narrow_large_charcoal",
    Scenario::Controller,
    80,
    24,
    Theme::Charcoal,
    DisplayMode::LargeText
);
golden_test!(
    shell_review_viewer_wide,
    "viewer_wide_compact_charcoal",
    Scenario::Viewer,
    120,
    36,
    Theme::Charcoal,
    DisplayMode::Compact
);
golden_test!(
    shell_review_viewer_narrow,
    "viewer_narrow_standard_warm",
    Scenario::Viewer,
    80,
    24,
    Theme::WarmWhite,
    DisplayMode::Standard
);
golden_test!(
    shell_review_urgent_wide,
    "urgent_wide_large_warm",
    Scenario::Urgent,
    120,
    36,
    Theme::WarmWhite,
    DisplayMode::LargeText
);
golden_test!(
    shell_review_urgent_narrow,
    "urgent_narrow_compact_charcoal",
    Scenario::Urgent,
    80,
    24,
    Theme::Charcoal,
    DisplayMode::Compact
);
golden_test!(
    shell_review_resolved_wide,
    "resolved_wide_standard_charcoal",
    Scenario::Resolved,
    120,
    36,
    Theme::Charcoal,
    DisplayMode::Standard
);
golden_test!(
    shell_review_resolved_narrow,
    "resolved_narrow_large_warm",
    Scenario::Resolved,
    80,
    24,
    Theme::WarmWhite,
    DisplayMode::LargeText
);

fn render_text(width: u16, height: u16, state: &AppState) -> String {
    normalized_buffer(&render_buffer(width, height, state))
}

fn normalized_render(width: u16, height: u16, state: &AppState) -> String {
    normalized_buffer(&render_buffer(width, height, state))
}

fn render_buffer(width: u16, height: u16, state: &AppState) -> Buffer {
    let backend = TestBackend::new(width, height);
    let mut terminal = Terminal::new(backend).expect("test terminal");
    terminal
        .draw(|frame| render(frame, state))
        .expect("render succeeds");
    terminal.backend().buffer().clone()
}

fn normalized_buffer(buffer: &Buffer) -> String {
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

fn poisoned_snapshot() -> ShellSnapshot {
    serde_json::from_value(json!({
        "state_version": 99,
        "generated_at_utc": "2026-08-03T12:00:00Z",
        "header": {
            "operating_mode": "live",
            "operating_mode_freshness": "fresh",
            "operating_mode_reason": null,
            "data_freshness": "fresh",
            "data_age_seconds": 1.0,
            "regime_label": "POISON-SNAPSHOT",
            "regime_confidence": 0.99,
            "portfolio_value": 999999.0,
            "next_rebalance_at_utc": null,
            "rebalance_blockers": null,
            "active_agent": "POISON-SNAPSHOT",
            "agent_queue_length": 9,
            "qwen_state": "POISON-SNAPSHOT",
            "qwen_context_percent": 90.0,
            "current_time_utc": "2026-08-03T12:00:00Z",
            "market_session": "POISON-SNAPSHOT"
        },
        "alerts": [{
            "alert_id": "poison-alert",
            "severity": "urgent",
            "summary": "POISON-SNAPSHOT",
            "created_at_utc": "2026-08-03T12:00:00Z",
            "resolved_at_utc": null
        }],
        "capabilities": []
    }))
    .expect("valid poisoned snapshot")
}

fn alert_snapshot(severity: &str, summary: &str) -> ShellSnapshot {
    serde_json::from_value(json!({
        "state_version": 7,
        "generated_at_utc": "2026-01-15T12:34:56Z",
        "header": {
            "operating_mode": "unknown",
            "operating_mode_freshness": "unavailable",
            "operating_mode_reason": "No reviewed runtime-status adapter is configured.",
            "data_freshness": "unavailable",
            "data_age_seconds": null,
            "regime_label": "",
            "regime_confidence": null,
            "portfolio_value": null,
            "next_rebalance_at_utc": null,
            "rebalance_blockers": null,
            "active_agent": null,
            "agent_queue_length": null,
            "qwen_state": "",
            "qwen_context_percent": null,
            "current_time_utc": "2026-01-15T12:34:56Z",
            "market_session": "Closed"
        },
        "alerts": [{
            "alert_id": "phase-one-alert",
            "severity": severity,
            "summary": summary,
            "created_at_utc": "2026-01-15T12:34:56Z",
            "resolved_at_utc": if severity == "resolved" {
                Some("2026-01-15T12:35:56Z")
            } else {
                None
            }
        }],
        "capabilities": []
    }))
    .expect("valid alert snapshot")
}

fn control_character_snapshot() -> ShellSnapshot {
    serde_json::from_value(json!({
        "state_version": 8,
        "generated_at_utc": "2026-01-15T12:34:56Z",
        "header": {
            "operating_mode": "unknown",
            "operating_mode_freshness": "unavailable",
            "operating_mode_reason": "REASON\u{001b}RED",
            "data_freshness": "unavailable",
            "data_age_seconds": null,
            "regime_label": "REGIME\u{001b}RED",
            "regime_confidence": null,
            "portfolio_value": null,
            "next_rebalance_at_utc": null,
            "rebalance_blockers": ["BLOCK\nLINE"],
            "active_agent": "AGENT\rNAME",
            "agent_queue_length": 1,
            "qwen_state": "QWEN\tSTATE",
            "qwen_context_percent": null,
            "current_time_utc": "2026-01-15T12:34:56Z",
            "market_session": "CLOSED\nINJECTED"
        },
        "alerts": [{
            "alert_id": "control-alert",
            "severity": "urgent",
            "summary": "ALERT\u{001b}SUMMARY",
            "created_at_utc": "2026-01-15T12:34:56Z",
            "resolved_at_utc": null
        }],
        "capabilities": []
    }))
    .expect("valid control-character snapshot")
}

fn resolved_then_urgent_snapshot() -> ShellSnapshot {
    let mut snapshot = alert_snapshot("resolved", "Earlier issue repaired.");
    let urgent = alert_snapshot("urgent", "Immediate review required.")
        .alerts
        .expect("urgent fixture alerts")
        .remove(0);
    snapshot
        .alerts
        .as_mut()
        .expect("resolved fixture alerts")
        .push(urgent);
    snapshot
}

fn wide_and_bidi_snapshot() -> ShellSnapshot {
    let wide = "市場".repeat(32);
    let mut snapshot = alert_snapshot("urgent", &format!("{wide}\u{2066}alert"));
    snapshot.header.market_session = format!("{wide}\u{202e}market");
    snapshot.header.regime_label = format!("{wide}\u{2066}regime");
    snapshot.header.regime_confidence = Some(0.875);
    snapshot.header.portfolio_value = Some(123_456.78);
    snapshot.header.rebalance_blockers = Some(vec![format!("{wide}\u{202e}blocker")]);
    snapshot.header.active_agent = Some(format!("{wide}\u{2066}agent"));
    snapshot.header.agent_queue_length = Some(2);
    snapshot.header.qwen_state = format!("{wide}\u{202e}qwen");
    snapshot.header.qwen_context_percent = Some(42.0);
    snapshot
}

fn long_header_snapshot() -> ShellSnapshot {
    let long = "X".repeat(512);
    serde_json::from_value(json!({
        "state_version": 9,
        "generated_at_utc": "2026-01-15T12:34:56Z",
        "header": {
            "operating_mode": "unknown",
            "operating_mode_freshness": "unavailable",
            "operating_mode_reason": long,
            "data_freshness": "stale",
            "data_age_seconds": 123.5,
            "regime_label": long,
            "regime_confidence": 0.875,
            "portfolio_value": 123456.78,
            "next_rebalance_at_utc": "2026-01-16T12:34:56Z",
            "rebalance_blockers": [long, long],
            "active_agent": long,
            "agent_queue_length": 12,
            "qwen_state": long,
            "qwen_context_percent": 42.0,
            "current_time_utc": "2026-01-15T12:34:56Z",
            "market_session": long
        },
        "alerts": [],
        "capabilities": []
    }))
    .expect("valid long header snapshot")
}

fn timestamp(value: &str) -> UtcTimestamp {
    serde_json::from_value(json!(value)).expect("valid UTC timestamp")
}

fn auth_server_hello(sequence: u64, requires_setup: bool) -> Envelope {
    auth_envelope(
        sequence,
        "server-hello",
        json!({
            "server_version": "0.1.0",
            "requires_setup": requires_setup
        }),
    )
}

fn auth_failure(sequence: u64, reason: &str) -> Envelope {
    auth_envelope(
        sequence,
        "auth-result",
        json!({
            "success": false,
            "access_state": "locked",
            "reason": reason
        }),
    )
}

fn auth_envelope(sequence: u64, message_type: &str, payload: serde_json::Value) -> Envelope {
    serde_json::from_value(json!({
        "schema_version": 1,
        "message_id": format!("server:{sequence}"),
        "sequence": sequence,
        "state_version": 0,
        "timestamp_utc": "2026-08-03T00:00:00Z",
        "message_type": message_type,
        "payload": payload
    }))
    .expect("valid authentication envelope")
}

#[derive(Clone, Copy, Debug)]
enum Scenario {
    Locked,
    FirstRun,
    Controller,
    Viewer,
    Urgent,
    Resolved,
}

impl Scenario {
    fn state(self) -> AppState {
        match self {
            Self::Locked => AppState::locked(),
            Self::FirstRun => AppState::first_run(),
            Self::Controller => AppState::controller(),
            Self::Viewer => AppState::viewer(),
            Self::Urgent => {
                let mut state = AppState::controller();
                state.snapshot = Some(alert_snapshot("urgent", "Immediate review required."));
                state
            }
            Self::Resolved => {
                let mut state = AppState::controller();
                state.snapshot = Some(alert_snapshot("resolved", "Issue repaired."));
                state
            }
        }
    }

    fn assert_semantics(self, text: &str) {
        match self {
            Self::Locked => {
                assert!(text.contains("LOCKED"));
                assert!(!text.contains("NAVIGATION"));
            }
            Self::FirstRun => {
                assert!(text.contains("FIRST RUN"));
                assert!(!text.contains("NAVIGATION"));
            }
            Self::Controller => {
                assert!(text.contains("CONTROLLER"));
                assert!(text.contains("MODE UNKNOWN"));
            }
            Self::Viewer => {
                assert!(text.contains("READ ONLY"));
                assert!(text.contains("MODE UNKNOWN"));
            }
            Self::Urgent => assert!(text.contains("[!] URGENT")),
            Self::Resolved => assert!(text.contains("[OK] RESOLVED")),
        }
        assert!(!text.contains("STOPPED"));
    }
}

fn assert_accessible_static_palette(buffer: &Buffer) {
    let allowed = [
        Color::Reset,
        Color::Rgb(250, 247, 240),
        Color::Rgb(38, 38, 38),
        Color::Rgb(155, 28, 28),
        Color::Rgb(122, 101, 0),
        Color::Rgb(0, 76, 153),
        Color::Rgb(22, 101, 52),
        Color::Rgb(255, 123, 123),
        Color::Rgb(253, 224, 71),
        Color::Rgb(108, 182, 255),
        Color::Rgb(110, 219, 143),
    ];
    for cell in buffer.content() {
        assert!(
            !cell
                .modifier
                .intersects(Modifier::SLOW_BLINK | Modifier::RAPID_BLINK)
        );
        assert!(allowed.contains(&cell.fg), "unexpected fg {:?}", cell.fg);
        assert!(allowed.contains(&cell.bg), "unexpected bg {:?}", cell.bg);
    }
}

fn contrast_ratio(foreground: Color, background: Color) -> f64 {
    let luminance = |color| {
        let Color::Rgb(red, green, blue) = color else {
            panic!("contrast fixtures must use RGB colors")
        };
        let channel = |value: u8| {
            let value = f64::from(value) / 255.0;
            if value <= 0.04045 {
                value / 12.92
            } else {
                ((value + 0.055) / 1.055).powf(2.4)
            }
        };
        0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)
    };
    let foreground = luminance(foreground);
    let background = luminance(background);
    (foreground.max(background) + 0.05) / (foreground.min(background) + 0.05)
}

fn label_style(buffer: &Buffer, label: &str) -> (Color, Color) {
    let symbols = label
        .chars()
        .map(|character| character.to_string())
        .collect::<Vec<_>>();
    for y in buffer.area.y..buffer.area.bottom() {
        for x in buffer.area.x..buffer.area.right() {
            if x + symbols.len() as u16 > buffer.area.right() {
                break;
            }
            if symbols
                .iter()
                .enumerate()
                .all(|(offset, symbol)| buffer[(x + offset as u16, y)].symbol() == symbol)
            {
                return (buffer[(x, y)].fg, buffer[(x, y)].bg);
            }
        }
    }
    panic!("label {label:?} not found in buffer");
}
