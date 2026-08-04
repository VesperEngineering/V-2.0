use crate::contract::{
    Freshness, MetricRow, OrderSide, ReadinessGate, ReadinessState, RepositoryRow, ServiceState,
    SystemView,
};
use crate::screens::{DetailKind, ScreenState};
use crate::ui::format_eastern_time;
use crate::widgets::sanitize_line;
use ratatui::Frame;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::style::Style;
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Paragraph, Wrap};

pub fn render_system(frame: &mut Frame<'_>, area: Rect, view: &SystemView, state: &ScreenState) {
    let area = render_stale_notice(frame, area, view.freshness, view.error.as_deref(), state);
    if area.width < 120 {
        match state.narrow_panel % 4 {
            0 => render_services(frame, area, view, state, "SERVICES - PANEL 1/4", true),
            1 => render_metrics(frame, area, view, state, "SYSTEM METRICS - PANEL 2/4", true),
            2 => render_repositories(frame, area, view, state, "SOURCE CONTROL - PANEL 3/4", true),
            _ => {
                render_live_readiness(frame, area, view, state, "LIVE READINESS - PANEL 4/4", true)
            }
        }
        return;
    }
    let rows =
        Layout::vertical([Constraint::Percentage(50), Constraint::Percentage(50)]).split(area);
    let top =
        Layout::horizontal([Constraint::Percentage(50), Constraint::Percentage(50)]).split(rows[0]);
    let bottom =
        Layout::horizontal([Constraint::Percentage(45), Constraint::Percentage(55)]).split(rows[1]);
    let focused = state.narrow_panel % 4;
    render_services(frame, top[0], view, state, "SERVICES", focused == 0);
    render_metrics(frame, top[1], view, state, "SYSTEM METRICS", focused == 1);
    render_repositories(
        frame,
        bottom[0],
        view,
        state,
        "SOURCE CONTROL",
        focused == 2,
    );
    render_live_readiness(
        frame,
        bottom[1],
        view,
        state,
        "LIVE READINESS",
        focused == 3,
    );
}

fn render_services(
    frame: &mut Frame<'_>,
    area: Rect,
    view: &SystemView,
    state: &ScreenState,
    title: &str,
    focused: bool,
) {
    let lines = source_message(view.freshness, view.error.as_deref()).map_or_else(
        || {
            let lines = view
                .services
                .iter()
                .skip(if focused {
                    service_offset(view, state)
                } else {
                    0
                })
                .map(|row| {
                    let (badge, style) = service_status(row.state, state);
                    let reason = row
                        .health_reason
                        .as_deref()
                        .map(|value| format!(" | {}", sanitize(value)))
                        .unwrap_or_default();
                    Line::from(vec![
                        Span::raw(marker(state, row.service_id.as_str(), DetailKind::Service)),
                        Span::styled(badge, style),
                        Span::raw(format!(
                            " {} | {}{reason}",
                            row.service_id.as_str(),
                            format_eastern_time(&row.observed_at_utc)
                        )),
                    ])
                })
                .collect::<Vec<_>>();
            if lines.is_empty() {
                vec![Line::from("No services reported.")]
            } else {
                lines
            }
        },
        |message| vec![Line::from(message)],
    );
    render_lines(frame, area, title, state, focused, lines);
}

fn render_metrics(
    frame: &mut Frame<'_>,
    area: Rect,
    view: &SystemView,
    state: &ScreenState,
    title: &str,
    focused: bool,
) {
    let lines = source_message(view.freshness, view.error.as_deref()).map_or_else(
        || {
            let lines = view
                .metrics
                .iter()
                .skip(if focused {
                    metric_offset(view, state)
                } else {
                    0
                })
                .map(|row| metric_line(row, state))
                .collect::<Vec<_>>();
            if lines.is_empty() {
                vec![Line::from("No system metrics reported.")]
            } else {
                lines
            }
        },
        |message| vec![Line::from(message)],
    );
    render_lines(frame, area, title, state, focused, lines);
}

fn render_repositories(
    frame: &mut Frame<'_>,
    area: Rect,
    view: &SystemView,
    state: &ScreenState,
    title: &str,
    focused: bool,
) {
    let lines = source_message(view.freshness, view.error.as_deref()).map_or_else(
        || {
            let lines = view
                .repositories
                .iter()
                .skip(if focused {
                    repository_offset(view, state)
                } else {
                    0
                })
                .map(|row| repository_line(row, state))
                .collect::<Vec<_>>();
            if lines.is_empty() {
                vec![Line::from("No repositories reported.")]
            } else {
                lines
            }
        },
        |message| vec![Line::from(message)],
    );
    render_lines(frame, area, title, state, focused, lines);
}

fn render_live_readiness(
    frame: &mut Frame<'_>,
    area: Rect,
    view: &SystemView,
    state: &ScreenState,
    title: &str,
    focused: bool,
) {
    let palette = state.theme.palette();
    let mut lines = Vec::with_capacity(
        14 + view
            .live_transition_plan
            .as_ref()
            .map_or(0, |plan| plan.orders.len()),
    );
    let gates = [
        ("BROKER", &view.live_readiness.broker),
        ("ACCOUNT", &view.live_readiness.account),
        ("DATA", &view.live_readiness.data),
        ("MODEL", &view.live_readiness.model),
        ("STRATEGY", &view.live_readiness.strategy),
        ("RISK", &view.live_readiness.risk),
        ("RECONCILIATION", &view.live_readiness.reconciliation),
        ("INCIDENT", &view.live_readiness.incident),
        ("AUTHORITY", &view.live_readiness.authority),
    ];
    let (live_badge, live_style) = if view.live_readiness.enabled {
        ("[OK] READY", palette.resolved)
    } else if gates
        .iter()
        .any(|(_, gate)| gate.state == ReadinessState::Blocked)
    {
        ("[!] BLOCKED", palette.urgent)
    } else if gates
        .iter()
        .any(|(_, gate)| gate.state == ReadinessState::Stale)
    {
        ("[~] STALE", palette.waiting)
    } else {
        ("[?] UNAVAILABLE", base_style(state))
    };
    lines.push(Line::from(vec![
        Span::raw("LIVE: "),
        Span::styled(live_badge, live_style),
    ]));
    for (name, gate) in gates {
        lines.push(readiness_line(name, gate, state));
    }
    if let Some(account) = &view.live_account {
        if state.mask_account_details {
            lines.push(Line::from(
                "Privacy: MASKED [p show] | Name HIDDEN | Number HIDDEN",
            ));
            lines.push(Line::from("Funds | Balance HIDDEN | Capital HIDDEN"));
        } else {
            lines.push(Line::from(format!(
                "Privacy: SHOWN [p hide] | {} | {}",
                sanitize(account.name.as_str()),
                sanitize(account.number.as_str())
            )));
            lines.push(Line::from(format!(
                "Funds | Balance {} | Capital {}",
                account.balance.as_str(),
                account.capital.as_str()
            )));
        }
    } else {
        lines.push(Line::from("Account: [?] UNAVAILABLE"));
    }
    if let Some(plan) = &view.live_transition_plan {
        lines.push(Line::from(format!(
            "Transition {} | {} | Orders {}",
            plan.desired_portfolio_id.as_str(),
            format_eastern_time(&plan.broker_positions_as_of_utc),
            plan.orders.len()
        )));
        for order in &plan.orders {
            let side = match order.side {
                OrderSide::Buy => "BUY",
                OrderSide::Sell => "SELL",
            };
            lines.push(Line::from(format!(
                "{side} {} {} | APPROVAL REQUIRED",
                order.symbol.as_str(),
                order.quantity.as_str()
            )));
        }
    } else {
        lines.push(Line::from(
            "Transition: [?] UNAVAILABLE - No broker-backed plan.",
        ));
    }
    frame.render_widget(
        Paragraph::new(lines)
            .style(base_style(state))
            .scroll((
                if focused {
                    u16::try_from(state.scroll_offset).unwrap_or(u16::MAX)
                } else {
                    0
                },
                0,
            ))
            .block(panel(focus_title(title, focused), state)),
        area,
    );
}

fn readiness_line(name: &'static str, gate: &ReadinessGate, state: &ScreenState) -> Line<'static> {
    let palette = state.theme.palette();
    let (badge, style) = match gate.state {
        ReadinessState::Ready => ("[OK] READY", palette.resolved),
        ReadinessState::Blocked => ("[!] BLOCKED", palette.urgent),
        ReadinessState::Unavailable => ("[?] UNAVAILABLE", base_style(state)),
        ReadinessState::Stale => ("[~] STALE", palette.waiting),
    };
    Line::from(vec![
        Span::raw(format!("{name}: ")),
        Span::styled(badge, style),
        Span::raw(format!(" | {}", sanitize(gate.reason.as_str()))),
    ])
}

fn render_lines(
    frame: &mut Frame<'_>,
    area: Rect,
    title: &str,
    state: &ScreenState,
    focused: bool,
    lines: Vec<Line<'static>>,
) {
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
        .map(|value| format!(" | {}", sanitize(value)))
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

fn repository_line(row: &RepositoryRow, state: &ScreenState) -> Line<'static> {
    let (badge, style) = freshness_status(row.freshness, state);
    if matches!(row.freshness, Freshness::Loading | Freshness::Unavailable) {
        return Line::from(vec![
            Span::raw(marker(
                state,
                row.repository_id.as_str(),
                DetailKind::Repository,
            )),
            Span::styled(badge, style),
            Span::raw(format!(
                " {} | {}",
                row.repository_id.as_str(),
                row.error
                    .as_deref()
                    .map(sanitize)
                    .unwrap_or_else(|| "Waiting for controller source.".to_owned())
            )),
        ]);
    }
    let branch = row.branch.as_ref().map_or_else(
        || "UNAVAILABLE".to_owned(),
        |value| sanitize(value.as_str()),
    );
    let revision = row.revision.as_ref().map_or_else(
        || "UNAVAILABLE".to_owned(),
        |value| sanitize(value.as_str()),
    );
    let clean = match row.clean {
        Some(true) => "[OK] CLEAN",
        Some(false) => "[!] DIRTY",
        None => "[?] CLEANLINESS UNAVAILABLE",
    };
    let worktrees = if row.worktrees.is_empty() {
        "NONE".to_owned()
    } else {
        row.worktrees
            .iter()
            .map(|value| sanitize(value.as_str()))
            .collect::<Vec<_>>()
            .join(", ")
    };
    let unpushed = row
        .unpushed_commit_count
        .map_or_else(|| "UNAVAILABLE".to_owned(), |count| count.to_string());
    let observed = row
        .as_of_utc
        .as_ref()
        .map_or_else(|| "Time UNAVAILABLE".to_owned(), format_eastern_time);
    let reason = row
        .error
        .as_deref()
        .map(|value| format!(" | {}", sanitize(value)))
        .unwrap_or_default();
    Line::from(vec![
        Span::raw(marker(
            state,
            row.repository_id.as_str(),
            DetailKind::Repository,
        )),
        Span::styled(badge, style),
        Span::raw(format!(
            " {} | Source {} | Branch {branch} | Revision {revision} | {clean} | Worktrees {worktrees} | Unpushed {unpushed} | {observed}{reason}",
            row.repository_id.as_str(),
            sanitize(row.source.as_str())
        )),
    ])
}

fn service_status(status: ServiceState, state: &ScreenState) -> (&'static str, Style) {
    let palette = state.theme.palette();
    match status {
        ServiceState::Running => ("[>] RUNNING", palette.active),
        ServiceState::Paused => ("[~] PAUSED", palette.waiting),
        ServiceState::Stopped => ("[ ] STOPPED", base_style(state)),
        ServiceState::Failed => ("[!] FAILED", palette.urgent),
        ServiceState::Unavailable => ("[?] UNAVAILABLE", base_style(state)),
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

fn service_offset(view: &SystemView, state: &ScreenState) -> usize {
    selected_offset(
        state,
        DetailKind::Service,
        view.services.iter().map(|row| row.service_id.as_str()),
    )
}

fn metric_offset(view: &SystemView, state: &ScreenState) -> usize {
    selected_offset(
        state,
        DetailKind::Metric,
        view.metrics.iter().map(|row| row.metric_id.as_str()),
    )
}

fn repository_offset(view: &SystemView, state: &ScreenState) -> usize {
    selected_offset(
        state,
        DetailKind::Repository,
        view.repositories
            .iter()
            .map(|row| row.repository_id.as_str()),
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
