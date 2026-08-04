use std::sync::OnceLock;

use ratatui::Frame;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::style::{Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Paragraph, Wrap};
use unicode_width::{UnicodeWidthChar, UnicodeWidthStr};
use windows_sys::Win32::Foundation::{ERROR_NO_MORE_ITEMS, ERROR_SUCCESS, FILETIME, SYSTEMTIME};
use windows_sys::Win32::System::Time::{
    DYNAMIC_TIME_ZONE_INFORMATION, EnumDynamicTimeZoneInformation, SystemTimeToFileTime,
    SystemTimeToTzSpecificLocalTimeEx,
};

use crate::contract::{AlertSeverity, Freshness, OperatingMode, UtcTimestamp};
use crate::layout::{ViewportClass, shell_layout};
use crate::screens::agents::render_agents;
use crate::screens::data::render_data;
use crate::screens::detail::render_direct_detail;
use crate::screens::impact::render_impact;
use crate::screens::memory::render_memory;
use crate::screens::models::render_models;
use crate::screens::orders::render_orders;
use crate::screens::portfolio::render_portfolio;
use crate::screens::risk::render_risk;
use crate::screens::system::render_system;
use crate::screens::timeline::render_timeline;
use crate::search::{SearchKind, SearchStatus, format_filter_expression};
use crate::state::{AccessState, AppState, AuthFeedback, AuthStage, LocalMode, Screen};
use crate::theme::Palette;

const EASTERN_TIME_ZONE: &str = "Eastern Standard Time";
const AGENT_INPUT_UNAVAILABLE: &str =
    "UNAVAILABLE - Agent input is not connected to the controller yet.";
static EASTERN_ZONE: OnceLock<Option<DYNAMIC_TIME_ZONE_INFORMATION>> = OnceLock::new();

pub fn render(frame: &mut Frame<'_>, state: &AppState) {
    let palette = state.theme().palette();
    let area = frame.area();
    frame.render_widget(Block::default().style(base_style(palette)), area);

    if !state.access.is_unlocked() {
        render_authentication(frame, area, state, palette);
        return;
    }

    let layout = shell_layout(area, state.display_mode());
    render_header(frame, layout.header, state, palette);
    render_navigation(frame, layout.navigation, state, palette);
    render_alerts(frame, layout.alerts, state, palette);
    if state.mode == LocalMode::Search {
        render_search(frame, layout.body, state, palette);
    } else if state.mode == LocalMode::Filter {
        render_filter(frame, layout.body, state, palette);
    } else if state.mode == LocalMode::NoteEditor {
        render_note_editor(frame, layout.body, state, palette);
    } else if let Some(result) = state.search_detail() {
        render_search_detail(frame, layout.body, state, result, palette);
    } else if state.mode == LocalMode::Open
        && state.screen_state().detail_open
        && matches!(
            state.screen,
            Screen::Orders
                | Screen::ModelsRegime
                | Screen::RiskApprovals
                | Screen::DataEvidence
                | Screen::Memory
                | Screen::System
        )
    {
        if let Some(snapshot) = state.snapshot.as_ref() {
            render_direct_detail(
                frame,
                layout.body,
                snapshot,
                state.screen,
                &state.screen_state(),
            );
        } else {
            render_screen(frame, layout.body, layout.viewport, state, palette);
        }
    } else {
        render_screen(frame, layout.body, layout.viewport, state, palette);
    }
    render_agent_input(frame, layout.input, palette);
    render_footer(frame, layout.footer, state, palette);
}

pub fn format_eastern_time(timestamp: &UtcTimestamp) -> String {
    let zone = EASTERN_ZONE
        .get_or_init(|| find_time_zone(EASTERN_TIME_ZONE))
        .as_ref();
    format_with_zone(timestamp, zone)
}

#[doc(hidden)]
pub fn format_eastern_time_for_zone(timestamp: &UtcTimestamp, zone_key: &str) -> String {
    let zone = find_time_zone(zone_key);
    format_with_zone(timestamp, zone.as_ref())
}

fn render_authentication(frame: &mut Frame<'_>, area: Rect, state: &AppState, palette: Palette) {
    let mut lines = match state.access {
        AccessState::Locked => vec![
            Line::from("V20 CONSOLE LOCKED"),
            Line::from("Authentication required. Dashboard hidden until unlock."),
            Line::from(format!("Password: {}", state.masked_auth_input())),
        ],
        AccessState::FirstRun => vec![
            Line::from("V20 CONSOLE FIRST RUN"),
            Line::from(match state.auth_stage() {
                AuthStage::Password => "Create console password.",
                AuthStage::Confirmation => "Confirm console password.",
            }),
            Line::from(format!("Password: {}", state.masked_auth_input())),
        ],
        AccessState::ProtocolLockout => vec![
            Line::from("V20 CONSOLE LOCKED"),
            Line::from("Connection unavailable. Reconnecting safely."),
        ],
        AccessState::Controller | AccessState::Viewer => unreachable!("unlocked rendered above"),
    };
    let feedback = match state.auth_feedback() {
        AuthFeedback::None => None,
        AuthFeedback::Pending => Some("Authentication pending."),
        AuthFeedback::Failed => Some("Authentication failed. Try again."),
        AuthFeedback::PasswordMismatch => Some("Passwords do not match. Re-enter confirmation."),
    };
    if let Some(feedback) = feedback {
        lines.push(Line::from(feedback));
    }
    frame.render_widget(
        Paragraph::new(lines)
            .style(base_style(palette))
            .wrap(Wrap { trim: true })
            .block(panel("Vesper v20 - Authentication", palette)),
        area,
    );
}

fn render_header(frame: &mut Frame<'_>, area: Rect, state: &AppState, palette: Palette) {
    let role = match state.access {
        AccessState::Controller => "CONTROLLER",
        AccessState::Viewer => "READ ONLY",
        _ => unreachable!("authentication rendered separately"),
    };
    let lines = if let Some(snapshot) = &state.snapshot {
        let shell = &snapshot.shell;
        let header = &shell.header;
        let mode = operating_mode(header.operating_mode);
        let mode_freshness = freshness(header.operating_mode_freshness);
        let data_freshness = freshness(header.data_freshness);
        let age = header.data_age_seconds.map_or_else(
            || "UNAVAILABLE".to_owned(),
            |value| format_number(value, "s"),
        );
        let regime = bounded_text(&available_text(&header.regime_label), 14);
        let confidence = header.regime_confidence.map_or_else(
            || "UNAVAILABLE".to_owned(),
            |value| format_number(value * 100.0, "%"),
        );
        let portfolio = header
            .portfolio_value
            .map_or_else(|| "UNAVAILABLE".to_owned(), format_currency);
        let agent = header.active_agent.as_deref().map_or_else(
            || "UNAVAILABLE".to_owned(),
            |agent| match header.agent_queue_length {
                Some(queue) => format!("{} / queue {queue}", sanitize_text(agent)),
                None => format!("{} / queue UNAVAILABLE", sanitize_text(agent)),
            },
        );
        let agent = bounded_text(&agent, 14);
        let qwen = if header.qwen_state.trim().is_empty() {
            "UNAVAILABLE".to_owned()
        } else {
            header.qwen_context_percent.map_or_else(
                || {
                    format!(
                        "{} / context UNAVAILABLE",
                        sanitize_text(&header.qwen_state)
                    )
                },
                |percent| format!("{} / {percent:.1}%", sanitize_text(&header.qwen_state)),
            )
        };
        let qwen = bounded_text(&qwen, 14);
        let rebalance = header
            .next_rebalance_at_utc
            .as_ref()
            .map_or_else(|| "UNAVAILABLE".to_owned(), format_eastern_time);
        let blockers = header.rebalance_blockers.as_ref().map_or_else(
            || "UNAVAILABLE".to_owned(),
            |items| {
                if items.is_empty() {
                    "NONE".to_owned()
                } else {
                    items
                        .iter()
                        .map(|item| sanitize_text(item))
                        .collect::<Vec<_>>()
                        .join(", ")
                }
            },
        );
        let blockers = bounded_text(&blockers, 28);
        let market_session = bounded_text(&available_text(&header.market_session), 18);
        let alerts = alert_header_status(shell.alerts.as_deref());
        let primary = Line::from(format!(
            "MODE {mode} / {mode_freshness} | DATA {data_freshness} | AGE {age}"
        ));
        vec![
            primary,
            Line::from(format!(
                "TIME {} | MARKET {market_session}",
                format_eastern_time(&header.current_time_utc)
            )),
            Line::from(format!(
                "REGIME {regime} | CONFIDENCE {confidence} | PORTFOLIO {portfolio}"
            )),
            Line::from(format!("REBALANCE {rebalance} | BLOCKERS {blockers}")),
            Line::from(format!("ALERTS {alerts} | AGENT {agent} | QWEN {qwen}")),
        ]
    } else {
        vec![
            Line::from("MODE UNKNOWN / UNAVAILABLE | DATA UNAVAILABLE | AGE UNAVAILABLE"),
            Line::from("TIME UNAVAILABLE - Eastern time unavailable | MARKET UNAVAILABLE"),
            Line::from("REGIME UNAVAILABLE | CONFIDENCE UNAVAILABLE | PORTFOLIO UNAVAILABLE"),
            Line::from("REBALANCE UNAVAILABLE | BLOCKERS UNAVAILABLE"),
            Line::from("ALERTS UNAVAILABLE | AGENT UNAVAILABLE | QWEN UNAVAILABLE"),
        ]
    };
    frame.render_widget(
        Paragraph::new(lines)
            .style(base_style(palette))
            .block(panel(format!("RUNTIME & MARKET - {role}"), palette)),
        area,
    );
}

fn render_navigation(frame: &mut Frame<'_>, area: Rect, state: &AppState, palette: Palette) {
    let narrow = area.width < 120;
    let entries = [
        ('1', Screen::Impact, "Impact", "Imp"),
        ('2', Screen::Portfolio, "Portfolio", "Port"),
        ('3', Screen::Orders, "Orders", "Ord"),
        ('4', Screen::Agents, "Agents", "Agt"),
        ('5', Screen::ModelsRegime, "Models & Regime", "Mod"),
        ('6', Screen::Timeline, "Timeline", "Time"),
        ('7', Screen::RiskApprovals, "Risk & Approvals", "Risk"),
        ('8', Screen::DataEvidence, "Data & Evidence", "Data"),
        ('9', Screen::Memory, "Memory", "Mem"),
        ('0', Screen::System, "System", "Sys"),
    ];
    let mut spans = Vec::new();
    for (index, (key, screen, wide_name, narrow_name)) in entries.into_iter().enumerate() {
        if index > 0 {
            spans.push(Span::raw(" | "));
        }
        let name = if narrow { narrow_name } else { wide_name };
        let label = if state.screen == screen {
            format!("[{key} {name}]")
        } else {
            format!("{key} {name}")
        };
        let style = if state.screen == screen {
            base_style(palette).add_modifier(Modifier::BOLD)
        } else {
            base_style(palette)
        };
        spans.push(Span::styled(label, style));
    }
    frame.render_widget(
        Paragraph::new(Line::from(spans))
            .style(base_style(palette))
            .wrap(Wrap { trim: false })
            .block(panel("NAVIGATION", palette)),
        area,
    );
}

fn render_alerts(frame: &mut Frame<'_>, area: Rect, state: &AppState, palette: Palette) {
    let content_width = usize::from(area.width.saturating_sub(2));
    let lines = match state
        .snapshot
        .as_ref()
        .and_then(|snapshot| snapshot.shell.alerts.as_ref())
    {
        None => vec![Line::from("[?] ALERTS UNAVAILABLE")],
        Some(alerts) if alerts.is_empty() => vec![Line::from(Span::styled(
            "[OK] HEALTHY - No active alerts.",
            palette.resolved,
        ))],
        Some(alerts) => {
            let mut alerts = alerts.iter().collect::<Vec<_>>();
            alerts.sort_by_key(|alert| alert_priority(alert.severity));
            alerts
                .into_iter()
                .map(|alert| {
                    let (label, style) = match alert.severity {
                        AlertSeverity::Info => ("[i] INFO", base_style(palette)),
                        AlertSeverity::Active => ("[>] ACTIVE", palette.active),
                        AlertSeverity::Waiting => ("[~] WAITING", palette.waiting),
                        AlertSeverity::Urgent => ("[!] URGENT", palette.urgent),
                        AlertSeverity::Resolved => ("[OK] RESOLVED", palette.resolved),
                    };
                    let summary_width = content_width
                        .saturating_sub(UnicodeWidthStr::width(label))
                        .saturating_sub(3);
                    let text = format!(
                        "{label} - {}",
                        bounded_text(alert.summary.as_str(), summary_width)
                    );
                    Line::from(Span::styled(pad_to_width(text, content_width), style))
                })
                .collect()
        }
    };
    frame.render_widget(
        Paragraph::new(lines)
            .style(base_style(palette))
            .block(panel("ALERTS", palette)),
        area,
    );
}

fn render_screen(
    frame: &mut Frame<'_>,
    area: Rect,
    viewport: ViewportClass,
    state: &AppState,
    palette: Palette,
) {
    if let Some(snapshot) = state.snapshot.as_ref() {
        let screen_state = state.screen_state();
        match state.screen {
            Screen::Impact => {
                render_impact(frame, area, &snapshot.impact, &screen_state);
                return;
            }
            Screen::Portfolio => {
                render_portfolio(frame, area, &snapshot.portfolio, &screen_state);
                return;
            }
            Screen::Orders => {
                render_orders(frame, area, &snapshot.orders, &screen_state);
                return;
            }
            Screen::Agents => {
                render_agents(frame, area, &snapshot.agents, &screen_state);
                return;
            }
            Screen::ModelsRegime => {
                render_models(frame, area, &snapshot.models, &screen_state);
                return;
            }
            Screen::Timeline => {
                render_timeline(frame, area, &snapshot.timeline, &screen_state);
                return;
            }
            Screen::RiskApprovals => {
                render_risk(frame, area, &snapshot.risk, &screen_state);
                return;
            }
            Screen::DataEvidence => {
                render_data(frame, area, &snapshot.data, &screen_state);
                return;
            }
            Screen::Memory => {
                render_memory(frame, area, &snapshot.memory, &screen_state);
                return;
            }
            Screen::System => {
                render_system(frame, area, &snapshot.system, &screen_state);
                return;
            }
        }
    }

    let title = format!("SCREEN: {}", screen_name(state.screen));
    let message = "UNAVAILABLE - Controller snapshot has not arrived.";
    let content = Paragraph::new(message)
        .style(base_style(palette))
        .wrap(Wrap { trim: true });
    if viewport == ViewportClass::Narrow {
        frame.render_widget(content.block(panel(title, palette)), area);
        return;
    }

    let columns =
        Layout::horizontal([Constraint::Percentage(65), Constraint::Percentage(35)]).split(area);
    frame.render_widget(content.block(panel(title, palette)), columns[0]);
    frame.render_widget(
        Paragraph::new(message)
            .style(base_style(palette))
            .wrap(Wrap { trim: true })
            .block(panel("SOURCE AVAILABILITY", palette)),
        columns[1],
    );
}

fn render_search(frame: &mut Frame<'_>, area: Rect, state: &AppState, palette: Palette) {
    let search = state.search_state();
    let mut lines = vec![
        Line::from(format!("Query: {}", sanitize_text(search.query()))),
        Line::from(format!(
            "Filters: {}",
            sanitize_text(&format_filter_expression(search.filters(state.screen)))
        )),
    ];
    let show_rows = match search.status() {
        SearchStatus::Idle => {
            lines.push(Line::from("Type to search all supported V20 records."));
            false
        }
        SearchStatus::Debouncing | SearchStatus::Loading => {
            lines.push(Line::from("LOADING - Searching controller history."));
            false
        }
        SearchStatus::StaleRefreshing => {
            lines.push(Line::from(
                "STALE / REFRESHING - State changed; searching again.",
            ));
            false
        }
        SearchStatus::Unavailable => {
            let error = search.server_error().map_or_else(
                || {
                    search.query_error().map_or_else(
                        || "Search is unavailable.".to_owned(),
                        |error| error.to_string(),
                    )
                },
                str::to_owned,
            );
            lines.push(Line::from(format!(
                "[!] UNAVAILABLE - {}",
                sanitize_text(&error)
            )));
            false
        }
        SearchStatus::Incomplete => {
            let error = search
                .server_error()
                .unwrap_or("Some search sources failed.");
            lines.push(Line::from(format!(
                "[!] INCOMPLETE - {}",
                sanitize_text(error)
            )));
            true
        }
        SearchStatus::Fresh => true,
    };
    if show_rows {
        if search.results().is_empty() {
            lines.push(Line::from("No matching records."));
        } else {
            let available_rows = usize::from(area.height.saturating_sub(6)).max(1);
            let start = search
                .selected_index()
                .saturating_sub(available_rows.saturating_sub(1))
                .min(search.results().len().saturating_sub(available_rows));
            for (index, row) in search
                .results()
                .iter()
                .enumerate()
                .skip(start)
                .take(available_rows)
            {
                let marker = if index == search.selected_index() {
                    ">"
                } else {
                    " "
                };
                let timestamp = format_search_time(row.timestamp_utc.as_deref());
                let context = if row.context_only {
                    " | CONTEXT ONLY"
                } else {
                    ""
                };
                lines.push(Line::from(format!(
                    "{marker} [{}] {} | {} | {} | source {}{context}",
                    search_kind(row.kind),
                    sanitize_text(&row.title),
                    sanitize_text(&row.text),
                    sanitize_text(&timestamp),
                    sanitize_text(&row.source),
                )));
            }
        }
    }
    lines.push(Line::from("Enter Open | Up/Down Select | Esc Close"));
    frame.render_widget(
        Paragraph::new(lines)
            .style(base_style(palette))
            .block(panel("SEARCH ALL V20", palette)),
        area,
    );
}

fn render_filter(frame: &mut Frame<'_>, area: Rect, state: &AppState, palette: Palette) {
    let mut lines = vec![
        Line::from(format!("Filter: {}", sanitize_text(state.filter_input()))),
        Line::from("scope:screen|all"),
        Line::from("kind:stock,agent,model,order,approval,event,evidence,memory,source,note"),
        Line::from("source:<exact-source-id>"),
        Line::from("Enter Apply | Esc Cancel"),
    ];
    if let Some(error) = state.filter_error() {
        lines.insert(1, Line::from(format!("[!] {}", sanitize_text(error))));
    }
    frame.render_widget(
        Paragraph::new(lines)
            .style(base_style(palette))
            .wrap(Wrap { trim: true })
            .block(panel("FILTER CURRENT SCREEN SEARCH", palette)),
        area,
    );
}

fn render_note_editor(frame: &mut Frame<'_>, area: Rect, state: &AppState, palette: Palette) {
    let (target_type, target_id) = state
        .note_editor_target()
        .unwrap_or(("unsupported", "UNAVAILABLE"));
    let lines = vec![
        Line::from(format!(
            "Target: {} {}",
            sanitize_text(target_type),
            sanitize_text(target_id)
        )),
        Line::from(format!("Visibility: {}", state.note_visibility().as_str())),
        Line::from("Shared means agents may read it as context only."),
        Line::from("This note never becomes an agent command."),
        Line::default(),
        Line::from(format!("Note: {}", sanitize_text(state.note_input()))),
        Line::default(),
        Line::from("Left/Right Private/Shared | Enter Keep Draft | Esc Cancel"),
    ];
    frame.render_widget(
        Paragraph::new(lines)
            .style(base_style(palette))
            .wrap(Wrap { trim: true })
            .block(panel("CONTEXT NOTE", palette)),
        area,
    );
}

fn search_kind(kind: SearchKind) -> &'static str {
    match kind {
        SearchKind::Stock => "STOCK",
        SearchKind::Agent => "AGENT",
        SearchKind::Model => "MODEL",
        SearchKind::Order => "ORDER",
        SearchKind::Approval => "APPROVAL",
        SearchKind::Event => "EVENT",
        SearchKind::Evidence => "EVIDENCE",
        SearchKind::Memory => "MEMORY",
        SearchKind::Source => "SOURCE",
        SearchKind::Note => "NOTE",
    }
}

fn render_search_detail(
    frame: &mut Frame<'_>,
    area: Rect,
    state: &AppState,
    result: &crate::search::SearchResult,
    palette: Palette,
) {
    let lines = search_detail_lines(state, result);
    frame.render_widget(
        Paragraph::new(lines)
            .style(base_style(palette))
            .wrap(Wrap { trim: true })
            .scroll((
                u16::try_from(state.screen_state().scroll_offset).unwrap_or(u16::MAX),
                0,
            ))
            .block(panel("SEARCH RESULT DETAIL", palette)),
        area,
    );
}

pub(crate) fn search_detail_line_count(
    state: &AppState,
    result: &crate::search::SearchResult,
    width: u16,
) -> usize {
    Paragraph::new(search_detail_lines(state, result))
        .wrap(Wrap { trim: true })
        .line_count(width)
}

fn search_detail_lines(
    state: &AppState,
    result: &crate::search::SearchResult,
) -> Vec<Line<'static>> {
    let timestamp = format_search_time(result.timestamp_utc.as_deref());
    let mut lines = vec![
        Line::from(format!(
            "[{}] ENTITY {}",
            search_kind(result.kind),
            sanitize_text(&result.entity_id)
        )),
        Line::from(format!("TITLE {}", sanitize_text(&result.title))),
        Line::from(format!("DETAIL {}", sanitize_text(&result.text))),
        Line::from(format!("TIME {}", sanitize_text(&timestamp))),
        Line::from(format!("SOURCE {}", sanitize_text(&result.source))),
        Line::default(),
    ];
    if state.note_editor_target().is_some() {
        lines.push(Line::from(
            "n Add Private/Shared note - context only; never an agent command.",
        ));
    }
    if result.context_only {
        lines.push(Line::from(
            "CONTEXT ONLY - This note is not an agent command.",
        ));
    }
    lines.push(Line::from("Esc Back"));
    lines
}

fn format_search_time(value: Option<&str>) -> String {
    value
        .and_then(|value| {
            serde_json::from_value::<UtcTimestamp>(serde_json::Value::String(value.to_owned())).ok()
        })
        .map_or_else(
            || "TIME UNAVAILABLE".to_owned(),
            |value| format_eastern_time(&value),
        )
}

fn render_agent_input(frame: &mut Frame<'_>, area: Rect, palette: Palette) {
    frame.render_widget(
        Paragraph::new(AGENT_INPUT_UNAVAILABLE)
            .style(base_style(palette))
            .block(panel("AGENT INPUT - DISABLED", palette)),
        area,
    );
}

fn render_footer(frame: &mut Frame<'_>, area: Rect, state: &AppState, palette: Palette) {
    let text = if state.mode == LocalMode::Search {
        "Search | Type Query | Up/Down Select | Enter Open | Esc Close"
    } else if state.mode == LocalMode::Filter {
        "Filter Search on Current Screen | Enter Apply | Esc Cancel"
    } else if state.mode == LocalMode::NoteEditor {
        "Context Note | Left/Right Visibility | Enter Keep Draft | Esc Cancel"
    } else if state.mode == LocalMode::Open {
        "Detail | Up/Down Scroll | Esc Back"
    } else if state.preferences_unavailable() {
        "1-9,0 Screens | q Close TUI only | PREFERENCES UNAVAILABLE"
    } else if state.snapshot.is_some() {
        match state.screen {
            Screen::Impact if area.width < 120 => "Up/Down Holdings | o Open | q Close | f Filter",
            Screen::Impact => "Up/Down Holdings | o Open | q Close | f Filter",
            Screen::Portfolio => {
                "Up/Down Holdings | Left/Right Period | o Open | q Close | f Filter"
            }
            Screen::Orders => "Up/Down Rows | o Open | q Close | f Filter",
            Screen::Agents => "Up/Down Tasks | Left/Right Stages | o Open | q Close | f Filter",
            Screen::ModelsRegime => {
                "Left/Right Panels | Up/Down Rows | o Open | q Close | f Filter"
            }
            Screen::Timeline => "Up/Down Events | e Impact/All | o Open | q Close | f Filter",
            Screen::RiskApprovals => {
                "Up/Down Rows | Left/Right Panels | o Open | q Close | f Filter"
            }
            Screen::DataEvidence => {
                "Up/Down Rows | Left/Right Panels | o Open | q Close | f Filter"
            }
            Screen::Memory => "Up/Down Rows | Left/Right Panels | o Open | q Close | f Filter",
            Screen::System => "Up/Down Rows | Left/Right Panels | o Open | q Close | f Filter",
        }
    } else {
        "1-9,0 Screens | / Search | q Close TUI only"
    };
    frame.render_widget(
        Paragraph::new(text)
            .style(base_style(palette))
            .block(panel("KEYS & STATUS", palette)),
        area,
    );
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

fn operating_mode(mode: OperatingMode) -> &'static str {
    match mode {
        OperatingMode::Unknown => "UNKNOWN",
        OperatingMode::Stopped => "STOPPED",
        OperatingMode::Shadow => "SHADOW",
        OperatingMode::Paper => "PAPER",
        OperatingMode::Live => "LIVE",
    }
}

fn freshness(value: Freshness) -> &'static str {
    match value {
        Freshness::Loading => "LOADING",
        Freshness::Fresh => "FRESH",
        Freshness::Stale => "STALE",
        Freshness::Unavailable => "UNAVAILABLE",
    }
}

fn screen_name(screen: Screen) -> &'static str {
    match screen {
        Screen::Impact => "Impact",
        Screen::Portfolio => "Portfolio",
        Screen::Orders => "Orders",
        Screen::Agents => "Agents",
        Screen::ModelsRegime => "Models & Regime",
        Screen::Timeline => "Timeline",
        Screen::RiskApprovals => "Risk & Approvals",
        Screen::DataEvidence => "Data & Evidence",
        Screen::Memory => "Memory",
        Screen::System => "System",
    }
}

fn available_text(value: &str) -> String {
    if value.trim().is_empty() {
        "UNAVAILABLE".to_owned()
    } else {
        sanitize_text(value)
    }
}

fn sanitize_text(value: &str) -> String {
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

fn bounded_text(value: &str, max_width: usize) -> String {
    let sanitized = sanitize_text(value);
    if UnicodeWidthStr::width(sanitized.as_str()) <= max_width {
        return sanitized;
    }
    let ellipsis = ".".repeat(max_width.min(3));
    let content_width = max_width.saturating_sub(ellipsis.len());
    let mut bounded = String::new();
    let mut used = 0;
    for character in sanitized.chars() {
        let width = character.width().unwrap_or(1);
        if used + width > content_width {
            break;
        }
        bounded.push(character);
        used += width;
    }
    bounded.push_str(&ellipsis);
    bounded
}

fn pad_to_width(mut value: String, width: usize) -> String {
    let used = UnicodeWidthStr::width(value.as_str());
    value.extend(std::iter::repeat_n(' ', width.saturating_sub(used)));
    value
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

fn alert_priority(severity: AlertSeverity) -> u8 {
    match severity {
        AlertSeverity::Urgent => 0,
        AlertSeverity::Waiting => 1,
        AlertSeverity::Active => 2,
        AlertSeverity::Info => 3,
        AlertSeverity::Resolved => 4,
    }
}

fn alert_header_status(alerts: Option<&[crate::contract::AlertView]>) -> String {
    let Some(alerts) = alerts else {
        return "UNAVAILABLE".to_owned();
    };
    let open = alerts
        .iter()
        .filter(|alert| alert.severity != AlertSeverity::Resolved)
        .collect::<Vec<_>>();
    if open.is_empty() {
        return "NONE / OPEN 0".to_owned();
    }
    for (severity, label) in [
        (AlertSeverity::Urgent, "URGENT"),
        (AlertSeverity::Waiting, "WAITING"),
        (AlertSeverity::Active, "ACTIVE"),
        (AlertSeverity::Info, "INFO"),
    ] {
        let count = open
            .iter()
            .filter(|alert| alert.severity == severity)
            .count();
        if count > 0 {
            return format!("{label} {count} / OPEN {}", open.len());
        }
    }
    unreachable!("open alerts use one of the non-resolved severities")
}

fn format_number(value: f64, suffix: &str) -> String {
    if value.abs() < 1_000_000_000.0 {
        format!("{value:.1}{suffix}")
    } else {
        format!("{value:.2e}{suffix}")
    }
}

fn format_currency(value: f64) -> String {
    if value.abs() < 1_000_000_000_000.0 {
        format!("${value:.2}")
    } else {
        format!("${value:.2e}")
    }
}

fn format_with_zone(
    timestamp: &UtcTimestamp,
    zone: Option<&DYNAMIC_TIME_ZONE_INFORMATION>,
) -> String {
    zone.and_then(|zone| try_format_eastern(timestamp, zone))
        .unwrap_or_else(|| format!("{} UTC | Eastern time unavailable", timestamp.as_str()))
}

fn try_format_eastern(
    timestamp: &UtcTimestamp,
    zone: &DYNAMIC_TIME_ZONE_INFORMATION,
) -> Option<String> {
    let utc = parse_system_time(timestamp)?;
    let mut local = SYSTEMTIME::default();
    // SAFETY: zone and utc are valid immutable values and local is writable for this call.
    if unsafe { SystemTimeToTzSpecificLocalTimeEx(zone, &raw const utc, &raw mut local) } == 0 {
        return None;
    }
    let utc_ticks = system_time_ticks(&utc)?;
    let local_ticks = system_time_ticks(&local)?;
    let offset_minutes = (i128::from(local_ticks) - i128::from(utc_ticks)) / 600_000_000;
    let suffix = match offset_minutes {
        -300 => "EST",
        -240 => "EDT",
        _ => "ET",
    };
    Some(format!(
        "{:04}-{:02}-{:02} {:02}:{:02}:{:02} {suffix}",
        local.wYear, local.wMonth, local.wDay, local.wHour, local.wMinute, local.wSecond
    ))
}

fn find_time_zone(key: &str) -> Option<DYNAMIC_TIME_ZONE_INFORMATION> {
    let expected = key.encode_utf16().collect::<Vec<_>>();
    let mut index = 0_u32;
    loop {
        let mut zone = DYNAMIC_TIME_ZONE_INFORMATION::default();
        // SAFETY: zone is a valid writable value and index is advanced one entry at a time.
        let result = unsafe { EnumDynamicTimeZoneInformation(index, &raw mut zone) };
        match result {
            ERROR_SUCCESS => {
                let length = zone
                    .TimeZoneKeyName
                    .iter()
                    .position(|unit| *unit == 0)
                    .unwrap_or(zone.TimeZoneKeyName.len());
                if zone.TimeZoneKeyName[..length] == expected {
                    return Some(zone);
                }
                index = index.checked_add(1)?;
            }
            ERROR_NO_MORE_ITEMS => return None,
            _ => return None,
        }
    }
}

fn parse_system_time(timestamp: &UtcTimestamp) -> Option<SYSTEMTIME> {
    let body = timestamp.as_str().strip_suffix('Z')?;
    let number = |start: usize, end: usize| body.get(start..end)?.parse::<u16>().ok();
    let milliseconds = body
        .get(20..)
        .map(|fraction| {
            let digits = fraction.chars().take(3).collect::<String>();
            format!("{digits:0<3}").parse::<u16>().ok()
        })
        .unwrap_or(Some(0))?;
    Some(SYSTEMTIME {
        wYear: number(0, 4)?,
        wMonth: number(5, 7)?,
        wDayOfWeek: 0,
        wDay: number(8, 10)?,
        wHour: number(11, 13)?,
        wMinute: number(14, 16)?,
        wSecond: number(17, 19)?,
        wMilliseconds: milliseconds,
    })
}

fn system_time_ticks(system_time: &SYSTEMTIME) -> Option<u64> {
    let mut file_time = FILETIME::default();
    // SAFETY: system_time is a valid immutable value and file_time is writable for this call.
    if unsafe { SystemTimeToFileTime(system_time, &raw mut file_time) } == 0 {
        return None;
    }
    Some((u64::from(file_time.dwHighDateTime) << 32) | u64::from(file_time.dwLowDateTime))
}
