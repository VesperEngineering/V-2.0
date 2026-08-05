use crate::contract::{DataView, Freshness, SourceRow};
use crate::screens::{DetailKind, ScreenState};
use crate::ui::format_eastern_time;
use crate::widgets::sanitize_line;
use ratatui::Frame;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::style::Style;
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Paragraph, Wrap};

pub fn render_data(frame: &mut Frame<'_>, area: Rect, view: &DataView, state: &ScreenState) {
    let area = render_stale_notice(frame, area, view.freshness, view.error.as_deref(), state);
    if area.width < 120 {
        match state.narrow_panel % 2 {
            0 => render_sources(frame, area, view, state, "DATA SOURCES - PANEL 1/2", true),
            _ => render_evidence(frame, area, view, state, "EVIDENCE - PANEL 2/2", true),
        }
        return;
    }
    let columns =
        Layout::horizontal([Constraint::Percentage(60), Constraint::Percentage(40)]).split(area);
    let focused = state.narrow_panel % 2;
    render_sources(frame, columns[0], view, state, "DATA SOURCES", focused == 0);
    render_evidence(frame, columns[1], view, state, "EVIDENCE", focused == 1);
}

fn render_sources(
    frame: &mut Frame<'_>,
    area: Rect,
    view: &DataView,
    state: &ScreenState,
    title: &str,
    focused: bool,
) {
    let lines = source_message(view.freshness, view.error.as_deref()).map_or_else(
        || {
            let lines = view
                .sources
                .iter()
                .skip(if focused {
                    source_offset(view, state)
                } else {
                    0
                })
                .flat_map(|row| source_lines(row, state))
                .collect::<Vec<_>>();
            if lines.is_empty() {
                vec![Line::from("No data sources reported.")]
            } else {
                lines
            }
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

fn source_lines(row: &SourceRow, state: &ScreenState) -> Vec<Line<'static>> {
    let (badge, style) = freshness_status(row.freshness, state);
    let dependencies = if row.dependencies.is_empty() {
        "NONE".to_owned()
    } else {
        row.dependencies
            .iter()
            .map(|value| sanitize(value.as_str()))
            .collect::<Vec<_>>()
            .join(", ")
    };
    if matches!(row.freshness, Freshness::Loading | Freshness::Unavailable) {
        return vec![
            Line::from(vec![
                Span::raw(marker(state, row.source_id.as_str(), DetailKind::Source)),
                Span::styled(badge, style),
                Span::raw(format!(
                    " {} | {}",
                    row.source_id.as_str(),
                    row.error
                        .as_deref()
                        .map(sanitize)
                        .unwrap_or_else(|| "Waiting for controller source.".to_owned())
                )),
            ]),
            Line::from(format!("Dependencies {dependencies}")),
        ];
    }
    let age = row.age_seconds.map_or_else(
        || "Age UNAVAILABLE".to_owned(),
        |value| format!("Age {value:.1}s"),
    );
    let coverage = row
        .coverage
        .as_deref()
        .map(sanitize)
        .unwrap_or_else(|| "UNAVAILABLE".to_owned());
    let consumers = if row.consumers.is_empty() {
        "NONE".to_owned()
    } else {
        row.consumers
            .iter()
            .map(|value| sanitize(value.as_str()))
            .collect::<Vec<_>>()
            .join(", ")
    };
    let observed = row
        .as_of_utc
        .as_ref()
        .map_or_else(|| "Time UNAVAILABLE".to_owned(), format_eastern_time);
    let reason = row
        .error
        .as_deref()
        .map(|value| format!(" | {}", sanitize(value)))
        .unwrap_or_default();
    vec![
        Line::from(vec![
            Span::raw(marker(state, row.source_id.as_str(), DetailKind::Source)),
            Span::styled(badge, style),
            Span::raw(format!(
                " {} | {age} | Coverage {coverage} | Consumers {consumers} | {observed}{reason}",
                row.source_id.as_str()
            )),
        ]),
        Line::from(format!("Dependencies {dependencies}")),
    ]
}

fn render_evidence(
    frame: &mut Frame<'_>,
    area: Rect,
    view: &DataView,
    state: &ScreenState,
    title: &str,
    focused: bool,
) {
    let lines = source_message(view.freshness, view.error.as_deref()).map_or_else(
        || {
            let mut lines = Vec::new();
            for row in view.evidence.iter().skip(if focused {
                evidence_offset(view, state)
            } else {
                0
            }) {
                lines.push(Line::from(format!(
                    "{}[E] {} | {} | Source {} | {} | SHA-256 {}",
                    marker(state, row.evidence_id.as_str(), DetailKind::Evidence),
                    row.evidence_id.as_str(),
                    sanitize(row.evidence_type.as_str()),
                    sanitize(row.source.as_str()),
                    format_eastern_time(&row.created_at_utc),
                    sha256_text(&row.sha256)
                )));
                lines.push(Line::from(format!(
                    "SYMBOLS {} | AGENTS {} | MODELS {}",
                    ids(&row.symbols),
                    ids(&row.agent_ids),
                    ids(&row.model_ids)
                )));
                lines.push(Line::from(format!(
                    "ORDERS {} | APPROVALS {} | SOURCES {}",
                    ids(&row.order_ids),
                    ids(&row.approval_ids),
                    ids(&row.source_ids)
                )));
                let raw_log = row.raw_log_id.as_ref().map_or_else(
                    || "UNAVAILABLE".to_owned(),
                    |value| format!("{} [o open]", value.as_str()),
                );
                let next = row
                    .raw_log_next_cursor
                    .as_ref()
                    .map_or_else(|| "NONE".to_owned(), |value| sanitize(value.as_str()));
                lines.push(Line::from(format!(
                    "RAW LOG {raw_log} | TRUNCATED {} | NEXT {next}",
                    if row.raw_log_truncated { "YES" } else { "NO" }
                )));
            }
            if lines.is_empty() {
                vec![Line::from("No evidence reported.")]
            } else {
                lines
            }
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

fn freshness_status(status: Freshness, state: &ScreenState) -> (&'static str, Style) {
    let palette = state.theme.palette();
    match status {
        Freshness::Loading => ("[..] LOADING", palette.active),
        Freshness::Fresh => ("[OK] FRESH", palette.resolved),
        Freshness::Stale => ("[~] STALE", palette.waiting),
        Freshness::Unavailable => ("[?] UNAVAILABLE", base_style(state)),
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

fn source_offset(view: &DataView, state: &ScreenState) -> usize {
    selected_offset(
        state,
        DetailKind::Source,
        view.sources.iter().map(|row| row.source_id.as_str()),
    )
}

fn evidence_offset(view: &DataView, state: &ScreenState) -> usize {
    selected_offset(
        state,
        DetailKind::Evidence,
        view.evidence.iter().map(|row| row.evidence_id.as_str()),
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

fn sha256_text(value: &crate::contract::Sha256Hex) -> String {
    serde_json::to_value(value)
        .ok()
        .and_then(|value| value.as_str().map(str::to_owned))
        .unwrap_or_else(|| "UNAVAILABLE".to_owned())
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

fn sanitize(value: &str) -> String {
    sanitize_line(value)
}
