use crate::contract::{AlertSeverity, Freshness, MemoryStatus, MemoryView};
use crate::screens::{DetailKind, ScreenState};
use crate::ui::format_eastern_time;
use crate::widgets::sanitize_line;
use ratatui::Frame;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::style::Style;
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Paragraph, Wrap};

pub fn render_memory(frame: &mut Frame<'_>, area: Rect, view: &MemoryView, state: &ScreenState) {
    let area = render_stale_notice(frame, area, view.freshness, view.error.as_deref(), state);
    if area.width < 120 {
        match state.narrow_panel % 3 {
            0 => render_rows(
                frame,
                area,
                view,
                state,
                MemoryStatus::Core,
                "CORE MEMORY - PANEL 1/3",
                true,
            ),
            1 => render_rows(
                frame,
                area,
                view,
                state,
                MemoryStatus::Archived,
                "ARCHIVE - PANEL 2/3",
                true,
            ),
            _ => render_history(frame, area, view, state, "CHANGE HISTORY - PANEL 3/3", true),
        }
        return;
    }
    let columns = Layout::horizontal([
        Constraint::Percentage(35),
        Constraint::Percentage(35),
        Constraint::Percentage(30),
    ])
    .split(area);
    render_rows(
        frame,
        columns[0],
        view,
        state,
        MemoryStatus::Core,
        "CORE MEMORY",
        state.narrow_panel.is_multiple_of(3),
    );
    render_rows(
        frame,
        columns[1],
        view,
        state,
        MemoryStatus::Archived,
        "ARCHIVE",
        state.narrow_panel % 3 == 1,
    );
    render_history(
        frame,
        columns[2],
        view,
        state,
        "CHANGE HISTORY",
        state.narrow_panel % 3 == 2,
    );
}

fn render_rows(
    frame: &mut Frame<'_>,
    area: Rect,
    view: &MemoryView,
    state: &ScreenState,
    wanted: MemoryStatus,
    title: &str,
    focused: bool,
) {
    let lines = source_message(view.freshness, view.error.as_deref()).map_or_else(
        || {
            view.rows
                .iter()
                .filter(|row| row.status == wanted)
                .skip(if focused {
                    memory_offset(view, state, wanted)
                } else {
                    0
                })
                .map(|row| {
                    let (badge, style) = match row.status {
                        MemoryStatus::Core => ("[OK] CORE", state.theme.palette().resolved),
                        MemoryStatus::Archived => ("[A] ARCHIVED", base_style(state)),
                    };
                    Line::from(vec![
                        Span::raw(marker(state, row.memory_id.as_str(), DetailKind::Memory)),
                        Span::styled(badge, style),
                        Span::raw(format!(
                            " {} | {} | {} | Evidence {}",
                            row.memory_id.as_str(),
                            sanitize(row.summary.as_str()),
                            format_eastern_time(&row.updated_at_utc),
                            ids(&row.evidence_ids)
                        )),
                    ])
                })
                .collect()
        },
        |message| vec![Line::from(message)],
    );
    frame.render_widget(
        Paragraph::new(lines)
            .style(base_style(state))
            .wrap(Wrap { trim: true })
            .block(panel(focus_title(title, focused), state)),
        area,
    );
}

fn render_history(
    frame: &mut Frame<'_>,
    area: Rect,
    view: &MemoryView,
    state: &ScreenState,
    title: &str,
    focused: bool,
) {
    let lines = source_message(view.freshness, view.error.as_deref()).map_or_else(
        || {
            let mut lines = vec![Line::from("Reasons/agent use: [?] UNAVAILABLE")];
            lines.extend(
                view.history
                    .iter()
                    .skip(if focused {
                        history_offset(view, state)
                    } else {
                        0
                    })
                    .map(|row| {
                        let (badge, style) = alert_status(row.severity, state);
                        Line::from(vec![
                            Span::raw(selected_event_marker(state, row.event_id.as_str())),
                            Span::styled(badge, style),
                            Span::raw(format!(
                                " {} | {} | Evidence {}",
                                format_eastern_time(&row.occurred_at_utc),
                                sanitize(row.summary.as_str()),
                                ids(&row.evidence_ids)
                            )),
                        ])
                    }),
            );
            lines
        },
        |message| vec![Line::from(message)],
    );
    frame.render_widget(
        Paragraph::new(lines)
            .style(base_style(state))
            .wrap(Wrap { trim: true })
            .block(panel(focus_title(title, focused), state)),
        area,
    );
}

fn alert_status(status: AlertSeverity, state: &ScreenState) -> (&'static str, Style) {
    let palette = state.theme.palette();
    match status {
        AlertSeverity::Info => ("[i] INFO", base_style(state)),
        AlertSeverity::Active => ("[>] ACTIVE", palette.active),
        AlertSeverity::Waiting => ("[~] WAITING", palette.waiting),
        AlertSeverity::Urgent => ("[!] URGENT", palette.urgent),
        AlertSeverity::Resolved => ("[OK] RESOLVED", palette.resolved),
    }
}

fn source_message(freshness: Freshness, error: Option<&str>) -> Option<String> {
    match freshness {
        Freshness::Loading => Some("[..] LOADING - Waiting for controller source.".to_owned()),
        Freshness::Unavailable => Some(format!(
            "[?] UNAVAILABLE - {}",
            error
                .map(sanitize)
                .unwrap_or_else(|| "Source reason unavailable.".to_owned())
        )),
        Freshness::Fresh | Freshness::Stale => None,
    }
}

fn render_stale_notice(
    frame: &mut Frame<'_>,
    area: Rect,
    freshness: Freshness,
    error: Option<&str>,
    state: &ScreenState,
) -> Rect {
    if freshness != Freshness::Stale {
        return area;
    }
    let sections = Layout::vertical([Constraint::Length(3), Constraint::Min(0)]).split(area);
    frame.render_widget(
        Paragraph::new(format!(
            "[~] STALE - {}",
            error
                .map(sanitize)
                .unwrap_or_else(|| "Last valid sample retained.".to_owned())
        ))
        .style(base_style(state))
        .block(panel("SOURCE STATUS", state)),
        sections[0],
    );
    sections[1]
}

fn ids(values: &[crate::contract::SafeId]) -> String {
    if values.is_empty() {
        "NONE".to_owned()
    } else {
        values
            .iter()
            .map(|value| value.as_str())
            .collect::<Vec<_>>()
            .join(", ")
    }
}

fn panel<'a>(title: impl Into<Line<'a>>, state: &ScreenState) -> Block<'a> {
    Block::default()
        .borders(Borders::ALL)
        .title(title)
        .style(base_style(state))
}

fn focus_title(title: &str, focused: bool) -> String {
    if focused {
        format!("> {title}")
    } else {
        title.to_owned()
    }
}

fn marker(state: &ScreenState, id: &str, kind: DetailKind) -> &'static str {
    if state.selected_id.as_deref() == Some(id) && state.selected_kind == Some(kind) {
        "> "
    } else {
        ""
    }
}

fn selected_event_marker(state: &ScreenState, id: &str) -> String {
    if state.selected_id.as_deref() == Some(id) && state.selected_kind == Some(DetailKind::Event) {
        format!("> {id} ")
    } else {
        String::new()
    }
}

fn memory_offset(view: &MemoryView, state: &ScreenState, status: MemoryStatus) -> usize {
    selected_offset(
        state,
        DetailKind::Memory,
        view.rows
            .iter()
            .filter(|row| row.status == status)
            .map(|row| row.memory_id.as_str()),
    )
}

fn history_offset(view: &MemoryView, state: &ScreenState) -> usize {
    selected_offset(
        state,
        DetailKind::Event,
        view.history.iter().map(|row| row.event_id.as_str()),
    )
}

fn selected_offset<'a>(
    state: &ScreenState,
    kind: DetailKind,
    mut ids: impl Iterator<Item = &'a str>,
) -> usize {
    if state.selected_kind != Some(kind) {
        return 0;
    }
    let Some(selected_id) = state.selected_id.as_deref() else {
        return 0;
    };
    ids.position(|id| id == selected_id).unwrap_or(0)
}

fn base_style(state: &ScreenState) -> Style {
    let palette = state.theme.palette();
    Style::default()
        .fg(palette.foreground)
        .bg(palette.background)
}

fn sanitize(value: &str) -> String {
    sanitize_line(value)
}
