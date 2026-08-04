use std::ops::Range;
use std::path::PathBuf;

use ratatui::buffer::Buffer;
use ratatui::layout::{Constraint, Rect};
use ratatui::widgets::{Paragraph, Table, Widget};
use serde_json::Value;
use vesper_ratatui_console::contract::{AgentStage, AlertSeverity, ConsoleSnapshot, Freshness};
use vesper_ratatui_console::detail::{DetailOverlay, detail_area};
use vesper_ratatui_console::theme::Theme;
use vesper_ratatui_console::virtual_table::VirtualTable;
use vesper_ratatui_console::widgets::cards::{CardView, board_columns, card};
use vesper_ratatui_console::widgets::status::{agent_stage_badge, alert_badge, freshness_badge};
use vesper_ratatui_console::widgets::timeline::{timeline_line, timeline_rows};
use vesper_ratatui_console::widgets::weights::{weight_header, weight_row};

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .expect("crate is nested two levels under the repository")
        .to_path_buf()
}

fn snapshot() -> ConsoleSnapshot {
    serde_json::from_slice(
        &std::fs::read(
            repo_root().join("TUI testing/contracts/v1/console_snapshot_empty_command_specs.json"),
        )
        .expect("read shared snapshot fixture"),
    )
    .expect("strict snapshot")
}

fn buffer_text(buffer: &Buffer) -> String {
    let area = buffer.area;
    (area.y..area.y + area.height)
        .map(|y| {
            (area.x..area.x + area.width)
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n")
}

#[test]
fn ten_thousand_rows_render_only_viewport_plus_two_overscan_rows() {
    let mut table = VirtualTable::new((0..10_000).collect::<Vec<_>>());
    table.set_offset(5_000);

    assert_eq!(
        table.visible_range(20),
        Range {
            start: 4_999,
            end: 5_021
        }
    );
    assert_eq!(table.visible_rows(20).count(), 22);
    assert_eq!(table.visible_rows(20).next(), Some(&4_999));
}

#[test]
fn overscan_stays_bounded_at_both_ends() {
    let mut table = VirtualTable::new((0..100).collect::<Vec<_>>());
    assert_eq!(table.visible_range(10), 0..12);

    table.set_offset(95);
    assert_eq!(table.visible_range(10), 88..100);
    table.set_offset(10_000);
    assert_eq!(table.visible_range(10), 88..100);
}

#[test]
fn sorting_changes_display_order_without_mutating_source_rows() {
    let mut table = VirtualTable::new(vec![3, 1, 2]);
    table.sort_by(|left, right| left.cmp(right));

    assert_eq!(table.rows(), &[3, 1, 2]);
    assert_eq!(
        table.visible_rows(3).copied().collect::<Vec<_>>(),
        [1, 2, 3]
    );

    table.filter_by(|value| *value >= 2);
    table.sort_by(|left, right| right.cmp(left));
    assert_eq!(table.rows(), &[3, 1, 2]);
    assert_eq!(table.visible_rows(3).copied().collect::<Vec<_>>(), [3, 2]);
}

#[test]
fn zero_height_or_empty_data_has_no_visible_rows() {
    let table = VirtualTable::new(vec![1, 2, 3]);
    assert_eq!(table.visible_range(0), 0..0);
    assert_eq!(
        VirtualTable::<usize>::new(Vec::new()).visible_range(5),
        0..0
    );
}

#[test]
fn every_status_badge_has_a_symbol_word_and_color() {
    let palette = Theme::Charcoal.palette();
    for (severity, expected, expected_style) in [
        (AlertSeverity::Info, "[i] INFO", None),
        (AlertSeverity::Active, "[>] ACTIVE", Some(palette.active)),
        (AlertSeverity::Waiting, "[~] WAITING", Some(palette.waiting)),
        (AlertSeverity::Urgent, "[!] URGENT", Some(palette.urgent)),
        (
            AlertSeverity::Resolved,
            "[OK] RESOLVED",
            Some(palette.resolved),
        ),
    ] {
        let badge = alert_badge(severity, palette);
        assert_eq!(badge.content.as_ref(), expected);
        if let Some(style) = expected_style {
            assert_eq!(badge.style, style);
        } else {
            assert_eq!(badge.style.fg, Some(palette.foreground));
        }
    }

    let shared_badges = [
        freshness_badge(Freshness::Loading, palette),
        freshness_badge(Freshness::Fresh, palette),
        freshness_badge(Freshness::Stale, palette),
        freshness_badge(Freshness::Unavailable, palette),
        agent_stage_badge(AgentStage::Backlog, palette),
        agent_stage_badge(AgentStage::Queued, palette),
        agent_stage_badge(AgentStage::Running, palette),
        agent_stage_badge(AgentStage::Waiting, palette),
        agent_stage_badge(AgentStage::Done, palette),
        agent_stage_badge(AgentStage::Failed, palette),
    ];
    for badge in shared_badges {
        let text = badge.content.as_ref();
        assert!(text.starts_with('[') && text.contains("] "));
        assert!(text.split_whitespace().count() >= 2);
        assert!(badge.style.fg.is_some());
        assert!(badge.style.bg.is_some());
    }
}

#[test]
fn shared_card_weight_timeline_and_detail_widgets_render_real_values() {
    let snapshot = snapshot();
    let palette = Theme::WarmWhite.palette();
    let area = Rect::new(0, 0, 72, 12);

    let card_view = CardView::new(
        "Review AAPL",
        AlertSeverity::Urgent,
        vec!["portfolio-research".to_owned(), "qwen:64k".to_owned()],
    );
    let mut card_buffer = Buffer::empty(area);
    card(&card_view, palette).render(area, &mut card_buffer);
    let card_text = buffer_text(&card_buffer);
    assert!(card_text.contains("Review AAPL"));
    assert!(card_text.contains("[!] URGENT"));
    assert!(card_text.contains("portfolio-research"));

    let mut weight_buffer = Buffer::empty(area);
    Table::new(
        [weight_row(&snapshot.portfolio.rows[0], palette)],
        [
            Constraint::Length(12),
            Constraint::Length(12),
            Constraint::Length(12),
            Constraint::Length(12),
        ],
    )
    .header(weight_header(palette))
    .render(area, &mut weight_buffer);
    let weight_text = buffer_text(&weight_buffer);
    assert!(weight_text.contains("Current"));
    assert!(weight_text.contains("Proposed"));
    assert!(weight_text.contains("Approved"));
    assert!(weight_text.contains("10.00%"));
    assert!(weight_text.contains("11.00%"));
    let proposed_x = (0..area.width)
        .find(|x| {
            (0..6).all(|offset| {
                weight_buffer[(*x + offset, 1)].symbol()
                    == "11.00%"
                        .chars()
                        .nth(usize::from(offset))
                        .unwrap()
                        .to_string()
            })
        })
        .expect("proposed weight position");
    assert_eq!(
        weight_buffer[(proposed_x, 1)].fg,
        palette.active.fg.expect("active foreground")
    );
    assert_eq!(
        weight_buffer[(proposed_x, 1)].bg,
        palette.active.bg.expect("active background")
    );

    let impact_rows = timeline_rows(&snapshot.timeline.rows, false).collect::<Vec<_>>();
    assert_eq!(impact_rows.len(), 1);
    let mut timeline_buffer = Buffer::empty(area);
    Paragraph::new(timeline_line(impact_rows[0], palette)).render(area, &mut timeline_buffer);
    assert!(buffer_text(&timeline_buffer).contains("AAPL review started"));

    let mut detail_buffer = Buffer::empty(area);
    let overlay = detail_area(area);
    DetailOverlay::new(
        "Event detail",
        vec!["AAPL review started".to_owned()],
        palette,
    )
    .render(overlay, &mut detail_buffer);
    let detail_text = buffer_text(&detail_buffer);
    assert!(detail_text.contains("Event detail"));
    assert!(detail_text.contains("AAPL review started"));
    assert!(overlay.x > area.x && overlay.y > area.y);
}

#[test]
fn card_board_uses_fixed_non_overlapping_columns() {
    let area = Rect::new(3, 2, 80, 20);
    let columns = board_columns(area, 4);

    assert_eq!(columns.len(), 4);
    assert_eq!(columns.first().unwrap().x, area.x);
    assert_eq!(columns.last().unwrap().right(), area.right());
    assert!(columns.windows(2).all(|pair| pair[0].right() == pair[1].x));
    assert!(
        columns
            .iter()
            .all(|column| column.y == area.y && column.height == area.height)
    );
}

#[test]
fn shared_widgets_remove_terminal_controls_and_bidi_formatting() {
    let palette = Theme::Charcoal.palette();
    let area = Rect::new(0, 0, 48, 8);
    let poisoned = "\u{202e}HIDDEN\u{1b}[31m";

    let mut card_buffer = Buffer::empty(area);
    card(
        &CardView::new(poisoned, AlertSeverity::Info, vec![poisoned.to_owned()]),
        palette,
    )
    .render(area, &mut card_buffer);
    let card_text = buffer_text(&card_buffer);
    assert!(!card_text.contains('\u{202e}'));
    assert!(!card_text.contains('\u{1b}'));

    let mut detail_buffer = Buffer::empty(area);
    DetailOverlay::new(poisoned, vec![poisoned.to_owned()], palette)
        .render(area, &mut detail_buffer);
    let detail_text = buffer_text(&detail_buffer);
    assert!(!detail_text.contains('\u{202e}'));
    assert!(!detail_text.contains('\u{1b}'));

    let mut value = serde_json::to_value(snapshot()).unwrap();
    value["timeline"]["rows"][0]["summary"] = serde_json::json!(poisoned);
    let snapshot: ConsoleSnapshot = serde_json::from_value(value).unwrap();
    let mut timeline_buffer = Buffer::empty(area);
    Paragraph::new(timeline_line(&snapshot.timeline.rows[0], palette))
        .render(area, &mut timeline_buffer);
    let timeline_text = buffer_text(&timeline_buffer);
    assert!(!timeline_text.contains('\u{202e}'));
    assert!(!timeline_text.contains('\u{1b}'));
}

#[test]
fn timeline_renders_winter_and_summer_timestamps_in_eastern_time() {
    let palette = Theme::Charcoal.palette();
    for (utc, expected) in [
        ("2026-01-15T12:34:56Z", "2026-01-15 07:34:56 EST"),
        ("2026-07-15T12:34:56Z", "2026-07-15 08:34:56 EDT"),
    ] {
        let mut value = serde_json::to_value(snapshot()).unwrap();
        value["timeline"]["rows"][0]["occurred_at_utc"] = serde_json::json!(utc);
        let snapshot: ConsoleSnapshot = serde_json::from_value(value).unwrap();

        let line = timeline_line(&snapshot.timeline.rows[0], palette);
        assert!(line.to_string().contains(expected));
        assert!(!line.to_string().contains(utc));
    }
}

#[test]
fn timeline_filter_does_not_clone_or_reorder_source_rows() {
    let mut value: Value = serde_json::to_value(snapshot()).unwrap();
    let mut routine = value["timeline"]["rows"][0].clone();
    routine["event_id"] = serde_json::json!("event:2");
    routine["impact"] = serde_json::json!(false);
    routine["summary"] = serde_json::json!("Routine refresh");
    value["timeline"]["rows"]
        .as_array_mut()
        .unwrap()
        .push(routine);
    let snapshot: ConsoleSnapshot = serde_json::from_value(value).unwrap();

    assert_eq!(
        timeline_rows(&snapshot.timeline.rows, false)
            .map(|row| row.event_id.as_str())
            .collect::<Vec<_>>(),
        ["event:1"]
    );
    assert_eq!(
        timeline_rows(&snapshot.timeline.rows, true)
            .map(|row| row.event_id.as_str())
            .collect::<Vec<_>>(),
        ["event:1", "event:2"]
    );
    assert_eq!(snapshot.timeline.rows[0].event_id.as_str(), "event:1");
}
