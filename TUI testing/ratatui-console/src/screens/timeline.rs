use ratatui::Frame;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::style::Style;
use ratatui::text::Line;
use ratatui::widgets::{Block, Borders, Paragraph, Wrap};
use unicode_width::UnicodeWidthChar;

use crate::contract::{AlertSeverity, Freshness, TimelineRow, TimelineView};
use crate::layout::DisplayMode;
use crate::screens::ScreenState;
use crate::theme::Palette;
use crate::ui::format_eastern_time;

pub fn render_timeline(
    frame: &mut Frame<'_>,
    area: Rect,
    view: &TimelineView,
    state: &ScreenState,
) {
    let area = render_stale_notice(frame, area, view, state);
    let palette = state.theme.palette();
    if state.detail_open {
        render_detail(frame, area, view, state, palette);
        return;
    }
    let title = if state.show_all_events {
        "TIMELINE - ALL EVENTS"
    } else {
        "TIMELINE - IMPACT ONLY"
    };
    let lines = unavailable_message(view.freshness, view.error.as_deref()).map_or_else(
        || timeline_lines(view, state),
        |message| vec![Line::from(message)],
    );
    frame.render_widget(
        Paragraph::new(lines)
            .style(base_style(palette))
            .wrap(Wrap { trim: false })
            .block(panel(title, palette)),
        area,
    );
}

fn render_detail(
    frame: &mut Frame<'_>,
    area: Rect,
    view: &TimelineView,
    state: &ScreenState,
    palette: Palette,
) {
    let lines = detail_content(view, state);
    frame.render_widget(
        Paragraph::new(lines)
            .style(base_style(palette))
            .wrap(Wrap { trim: false })
            .scroll((u16::try_from(state.scroll_offset).unwrap_or(u16::MAX), 0))
            .block(panel("EVENT DETAIL", palette)),
        area,
    );
}

pub(crate) fn timeline_detail_line_count(
    view: &TimelineView,
    state: &ScreenState,
    width: u16,
) -> usize {
    Paragraph::new(detail_content(view, state))
        .wrap(Wrap { trim: false })
        .line_count(width)
}

fn detail_content(view: &TimelineView, state: &ScreenState) -> Vec<Line<'static>> {
    if let Some(message) = unavailable_message(view.freshness, view.error.as_deref()) {
        vec![Line::from(message)]
    } else if let Some(row) = state.selected_id.as_deref().and_then(|selected| {
        view.rows
            .iter()
            .find(|row| row.event_id.as_str() == selected)
    }) {
        vec![
            Line::from(format!("EVENT ID: {}", safe_text(row.event_id.as_str()))),
            Line::from(format!(
                "TIME: {}",
                format_eastern_time(&row.occurred_at_utc)
            )),
            Line::from(format!("STATUS: {}", severity_label(row.severity))),
            Line::from(format!(
                "IMPACTS V20: {}",
                if row.impact { "YES" } else { "NO" }
            )),
            Line::from(format!("SUMMARY: {}", safe_text(row.summary.as_str()))),
            Line::from(format!("AGENT: {}", optional_id(row.agent_id.as_ref()))),
            Line::from(format!("SYMBOL: {}", optional_id(row.symbol.as_ref()))),
            Line::from(format!("MODEL: {}", optional_id(row.model_id.as_ref()))),
            Line::from(format!(
                "APPROVAL: {}",
                optional_id(row.approval_id.as_ref())
            )),
            Line::from(format!("ORDER: {}", optional_id(row.order_id.as_ref()))),
            Line::from(format!("EVIDENCE: {}", evidence_list(&row.evidence_ids))),
            Line::from(format!("SOURCE: {}", safe_text(view.source.as_str()))),
            Line::default(),
            Line::from("Esc Back | n Add Private/Shared context note"),
        ]
    } else {
        vec![Line::from(
            "EVENT DETAIL UNAVAILABLE - Selected event was not reported.",
        )]
    }
}

fn optional_id(value: Option<&crate::contract::SafeId>) -> String {
    value
        .map(|value| safe_text(value.as_str()))
        .unwrap_or_else(|| "NONE REPORTED".to_owned())
}

fn timeline_lines(view: &TimelineView, state: &ScreenState) -> Vec<Line<'static>> {
    let excluded = if state.show_all_events {
        0
    } else {
        view.rows.iter().filter(|event| !event.impact).count()
    };
    let mut lines = vec![Line::from(format!(
        "EXCLUDED BY FILTER {excluded} | HIDDEN BY SOURCE {}",
        view.hidden_event_count
    ))];
    let rows = view
        .rows
        .iter()
        .filter(|event| state.show_all_events || event.impact)
        .collect::<Vec<_>>();
    if rows.is_empty() {
        lines.push(Line::from(if state.show_all_events {
            "No timeline events reported."
        } else {
            "No impact events reported."
        }));
        return lines;
    }
    let start = state.scroll_offset.min(rows.len() - 1);
    lines.push(Line::default());
    for row in rows.into_iter().skip(start) {
        lines.extend(event_lines(row));
        add_spacing(&mut lines, state.display_mode);
    }
    lines
}

fn event_lines(row: &TimelineRow) -> [Line<'static>; 2] {
    let mut links = vec![format!("ID {}", safe_text(row.event_id.as_str()))];
    if let Some(agent_id) = &row.agent_id {
        links.push(format!("AGENT {}", safe_text(agent_id.as_str())));
    }
    if let Some(symbol) = &row.symbol {
        links.push(format!("SYMBOL {}", safe_text(symbol.as_str())));
    }
    if let Some(model_id) = &row.model_id {
        links.push(format!("MODEL {}", safe_text(model_id.as_str())));
    }
    if let Some(approval_id) = &row.approval_id {
        links.push(format!("APPROVAL {}", safe_text(approval_id.as_str())));
    }
    if let Some(order_id) = &row.order_id {
        links.push(format!("ORDER {}", safe_text(order_id.as_str())));
    }
    links.push(format!("EVIDENCE {}", evidence_list(&row.evidence_ids)));
    [
        Line::from(format!(
            "{} | {} | {}",
            severity_label(row.severity),
            format_eastern_time(&row.occurred_at_utc),
            safe_text(row.summary.as_str())
        )),
        Line::from(links.join(" | ")),
    ]
}

fn add_spacing(lines: &mut Vec<Line<'static>>, display_mode: DisplayMode) {
    match display_mode {
        DisplayMode::Compact => {}
        DisplayMode::Standard => lines.push(Line::default()),
        DisplayMode::LargeText => {
            lines.push(Line::default());
            lines.push(Line::default());
        }
    }
}

fn render_stale_notice(
    frame: &mut Frame<'_>,
    area: Rect,
    view: &TimelineView,
    state: &ScreenState,
) -> Rect {
    if view.freshness != Freshness::Stale {
        return area;
    }
    let palette = state.theme.palette();
    let reason = view
        .error
        .as_deref()
        .map_or_else(|| "Reason unavailable.".to_owned(), safe_text);
    let sections = Layout::vertical([Constraint::Length(3), Constraint::Min(0)]).split(area);
    frame.render_widget(
        Paragraph::new(format!("[~] STALE - {reason}"))
            .style(base_style(palette))
            .wrap(Wrap { trim: true })
            .block(panel("SOURCE STATUS", palette)),
        sections[0],
    );
    sections[1]
}

fn unavailable_message(freshness: Freshness, error: Option<&str>) -> Option<String> {
    match freshness {
        Freshness::Fresh | Freshness::Stale => None,
        Freshness::Loading => Some("[..] LOADING - Waiting for controller data.".to_owned()),
        Freshness::Unavailable => Some(format!(
            "[?] UNAVAILABLE - {}",
            error.map_or_else(|| "Source reason unavailable.".to_owned(), safe_text)
        )),
    }
}

fn severity_label(severity: AlertSeverity) -> &'static str {
    match severity {
        AlertSeverity::Info => "[i] INFO",
        AlertSeverity::Active => "[>] ACTIVE",
        AlertSeverity::Waiting => "[~] WAITING",
        AlertSeverity::Urgent => "[!] URGENT",
        AlertSeverity::Resolved => "[OK] RESOLVED",
    }
}

fn evidence_list(ids: &[crate::contract::SafeId]) -> String {
    if ids.is_empty() {
        "NONE REPORTED".to_owned()
    } else {
        ids.iter()
            .map(|value| safe_text(value.as_str()))
            .collect::<Vec<_>>()
            .join(", ")
    }
}

fn panel<'a>(title: impl Into<Line<'a>>, palette: Palette) -> Block<'a> {
    Block::default()
        .borders(Borders::ALL)
        .title(title)
        .style(base_style(palette))
}

fn base_style(palette: Palette) -> Style {
    Style::default()
        .fg(palette.foreground)
        .bg(palette.background)
}

fn safe_text(value: &str) -> String {
    value
        .chars()
        .map(|character| {
            if character.is_control()
                || is_unicode_format(character)
                || character.width().unwrap_or(0) == 0
            {
                '?'
            } else {
                character
            }
        })
        .collect()
}

fn is_unicode_format(character: char) -> bool {
    matches!(
        character as u32,
        0x00AD
            | 0x0600..=0x0605
            | 0x061C
            | 0x06DD
            | 0x070F
            | 0x0890..=0x0891
            | 0x08E2
            | 0x180E
            | 0x200B..=0x200F
            | 0x202A..=0x202E
            | 0x2060..=0x2064
            | 0x2066..=0x206F
            | 0xFEFF
            | 0xFFF9..=0xFFFB
            | 0x110BD
            | 0x110CD
            | 0x13430..=0x1343F
            | 0x1BCA0..=0x1BCA3
            | 0x1D173..=0x1D17A
            | 0xE0001
            | 0xE0020..=0xE007F
    )
}
