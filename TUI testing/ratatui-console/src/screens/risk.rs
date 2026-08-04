use crate::contract::{
    AlertSeverity, ApprovalState, Freshness, MetricRow, RiskLimitStatus, RiskView,
};
use crate::screens::{DetailKind, ScreenState};
use crate::ui::format_eastern_time;
use crate::widgets::sanitize_line;
use ratatui::Frame;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::style::Style;
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Paragraph, Wrap};

pub fn render_risk(frame: &mut Frame<'_>, area: Rect, view: &RiskView, state: &ScreenState) {
    let area = render_stale_notice(frame, area, view.freshness, view.error.as_deref(), state);
    if area.width < 120 {
        match state.narrow_panel % 4 {
            0 => render_limits(frame, area, view, state, "RISK LIMITS - PANEL 1/4", true),
            1 => render_approvals(frame, area, view, state, "APPROVALS - PANEL 2/4", true),
            2 => render_alerts(frame, area, view, state, "ALERTS - PANEL 3/4", true),
            _ => render_metrics(frame, area, view, state, "RISK METRICS - PANEL 4/4", true),
        }
        return;
    }

    let rows =
        Layout::vertical([Constraint::Percentage(50), Constraint::Percentage(50)]).split(area);
    let top =
        Layout::horizontal([Constraint::Percentage(56), Constraint::Percentage(44)]).split(rows[0]);
    let bottom =
        Layout::horizontal([Constraint::Percentage(56), Constraint::Percentage(44)]).split(rows[1]);
    let focused = state.narrow_panel % 4;
    render_limits(frame, top[0], view, state, "RISK LIMITS", focused == 0);
    render_approvals(frame, top[1], view, state, "APPROVALS", focused == 1);
    render_alerts(frame, bottom[0], view, state, "ALERTS", focused == 2);
    render_metrics(frame, bottom[1], view, state, "RISK METRICS", focused == 3);
}

fn render_limits(
    frame: &mut Frame<'_>,
    area: Rect,
    view: &RiskView,
    state: &ScreenState,
    title: &str,
    focused: bool,
) {
    let lines = source_message(view.freshness, view.error.as_deref()).map_or_else(
        || {
            let lines = view
                .limits
                .iter()
                .skip(if focused {
                    limit_offset(view, state)
                } else {
                    0
                })
                .map(|row| {
                    let (badge, style) = limit_status(row.status, state);
                    Line::from(vec![
                        Span::raw(marker(state, row.limit_id.as_str(), DetailKind::RiskLimit)),
                        Span::styled(badge, style),
                        Span::raw(format!(
                            " {} | Current {} | Proposed {}",
                            row.limit_id.as_str(),
                            row.current_value.as_str(),
                            row.proposed_value
                                .as_ref()
                                .map_or("UNAVAILABLE", |value| value.as_str())
                        )),
                    ])
                })
                .collect::<Vec<_>>();
            if lines.is_empty() {
                vec![Line::from("No risk limits reported.")]
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

fn render_approvals(
    frame: &mut Frame<'_>,
    area: Rect,
    view: &RiskView,
    state: &ScreenState,
    title: &str,
    focused: bool,
) {
    let lines = source_message(view.freshness, view.error.as_deref()).map_or_else(
        || {
            let lines = view
                .approvals
                .iter()
                .skip(if focused {
                    approval_offset(view, state)
                } else {
                    0
                })
                .map(|row| {
                    let (badge, style) = approval_status(row.state, state);
                    let reason = row
                        .reason
                        .as_deref()
                        .map(sanitize)
                        .unwrap_or_else(|| "Reason UNAVAILABLE".to_owned());
                    Line::from(vec![
                        Span::raw(marker(
                            state,
                            row.approval_id.as_str(),
                            DetailKind::Approval,
                        )),
                        Span::styled(badge, style),
                        Span::raw(format!(
                            " {} | {} | {} | Evidence {}",
                            row.approval_id.as_str(),
                            format_eastern_time(&row.requested_at_utc),
                            reason,
                            ids(&row.evidence_ids)
                        )),
                    ])
                })
                .collect::<Vec<_>>();
            if lines.is_empty() {
                vec![Line::from("No approvals reported.")]
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

fn render_alerts(
    frame: &mut Frame<'_>,
    area: Rect,
    view: &RiskView,
    state: &ScreenState,
    title: &str,
    focused: bool,
) {
    let lines = source_message(view.freshness, view.error.as_deref()).map_or_else(
        || {
            let lines = view
                .alerts
                .iter()
                .skip(if focused {
                    alert_offset(view, state)
                } else {
                    0
                })
                .map(|row| {
                    let (badge, style) = alert_status(row.severity, state);
                    let resolved = row.resolved_at_utc.as_ref().map_or_else(
                        || {
                            if row.severity == AlertSeverity::Resolved {
                                "Resolved - time unavailable".to_owned()
                            } else {
                                "Open".to_owned()
                            }
                        },
                        |time| format!("Resolved {}", format_eastern_time(time)),
                    );
                    Line::from(vec![
                        Span::raw(marker(state, row.alert_id.as_str(), DetailKind::Alert)),
                        Span::styled(badge, style),
                        Span::raw(format!(
                            " {} | {} | Created {} | {resolved}",
                            row.alert_id.as_str(),
                            sanitize(row.summary.as_str()),
                            format_eastern_time(&row.created_at_utc),
                        )),
                    ])
                })
                .collect::<Vec<_>>();
            if lines.is_empty() {
                vec![Line::from("No risk alerts reported.")]
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

fn render_metrics(
    frame: &mut Frame<'_>,
    area: Rect,
    view: &RiskView,
    state: &ScreenState,
    title: &str,
    focused: bool,
) {
    let lines = source_message(view.freshness, view.error.as_deref()).map_or_else(
        || {
            let mut lines = vec![Line::from(
                "Blocked actions + Circuit breaker: [?] UNAVAILABLE (RiskView gap)",
            )];
            lines.extend(
                view.metrics
                    .iter()
                    .skip(if focused {
                        metric_offset(view, state)
                    } else {
                        0
                    })
                    .map(|row| metric_line(row, state)),
            );
            if view.metrics.is_empty() {
                lines.push(Line::from("No risk metrics reported."));
            }
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

fn metric_line(row: &MetricRow, state: &ScreenState) -> Line<'static> {
    let (badge, style) = freshness_status(row.freshness, state);
    if matches!(row.freshness, Freshness::Loading | Freshness::Unavailable) {
        return Line::from(vec![
            Span::raw(marker(state, row.metric_id.as_str(), DetailKind::Metric)),
            Span::styled(badge, style),
            Span::raw(format!(
                " {} | {}",
                row.metric_id.as_str(),
                row.error
                    .as_deref()
                    .map(sanitize)
                    .unwrap_or_else(|| "Waiting for controller source.".to_owned())
            )),
        ]);
    }
    let value = row.value.map_or_else(
        || "UNAVAILABLE".to_owned(),
        |value| format!("{value:.2} {}", sanitize(row.unit.as_str())),
    );
    let observed = row
        .observed_at_utc
        .as_ref()
        .map_or_else(|| "Time UNAVAILABLE".to_owned(), format_eastern_time);
    let reason = row
        .error
        .as_deref()
        .map(|error| format!(" | {}", sanitize(error)))
        .unwrap_or_default();
    Line::from(vec![
        Span::raw(marker(state, row.metric_id.as_str(), DetailKind::Metric)),
        Span::styled(badge, style),
        Span::raw(format!(
            " {} | {value} | {observed}{reason}",
            row.metric_id.as_str()
        )),
    ])
}

fn limit_status(status: RiskLimitStatus, state: &ScreenState) -> (&'static str, Style) {
    let palette = state.theme.palette();
    match status {
        RiskLimitStatus::Within => ("[OK] WITHIN", palette.resolved),
        RiskLimitStatus::Violated => ("[!] VIOLATED", palette.urgent),
        RiskLimitStatus::Pending => ("[~] PENDING", palette.waiting),
        RiskLimitStatus::Unavailable => ("[?] UNAVAILABLE", base_style(state)),
    }
}

fn approval_status(status: ApprovalState, state: &ScreenState) -> (&'static str, Style) {
    let palette = state.theme.palette();
    match status {
        ApprovalState::Pending => ("[~] PENDING", palette.waiting),
        ApprovalState::Approved => ("[OK] APPROVED", palette.resolved),
        ApprovalState::Held => ("[~] HELD", palette.waiting),
        ApprovalState::Rejected => ("[!] REJECTED", palette.urgent),
        ApprovalState::Rework => ("[~] REWORK", palette.waiting),
        ApprovalState::Stale => ("[~] STALE", palette.waiting),
    }
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

fn limit_offset(view: &RiskView, state: &ScreenState) -> usize {
    selected_offset(
        state,
        DetailKind::RiskLimit,
        view.limits.iter().map(|row| row.limit_id.as_str()),
    )
}

fn approval_offset(view: &RiskView, state: &ScreenState) -> usize {
    selected_offset(
        state,
        DetailKind::Approval,
        view.approvals.iter().map(|row| row.approval_id.as_str()),
    )
}

fn alert_offset(view: &RiskView, state: &ScreenState) -> usize {
    selected_offset(
        state,
        DetailKind::Alert,
        view.alerts.iter().map(|row| row.alert_id.as_str()),
    )
}

fn metric_offset(view: &RiskView, state: &ScreenState) -> usize {
    selected_offset(
        state,
        DetailKind::Metric,
        view.metrics.iter().map(|row| row.metric_id.as_str()),
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
