use std::cmp::Ordering;

use ratatui::Frame;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::style::Style;
use ratatui::text::Line;
use ratatui::widgets::{Block, Borders, Paragraph, Wrap};
use unicode_width::UnicodeWidthChar;

use crate::contract::{
    AgentActivityKind, AgentCard, AgentStage, AgentsView, Freshness, TimelineRow,
};
use crate::layout::DisplayMode;
use crate::screens::ScreenState;
use crate::theme::Palette;
use crate::ui::format_eastern_time;

const MAIN_STAGES: [(AgentStage, &str); 4] = [
    (AgentStage::Queued, "QUEUED"),
    (AgentStage::Running, "RUNNING"),
    (AgentStage::Waiting, "WAITING"),
    (AgentStage::Done, "DONE"),
];
const NARROW_STAGES: [(AgentStage, &str); 5] = [
    (AgentStage::Queued, "QUEUED"),
    (AgentStage::Running, "RUNNING"),
    (AgentStage::Waiting, "WAITING"),
    (AgentStage::Done, "DONE"),
    (AgentStage::Backlog, "BACKLOG"),
];

pub fn render_agents(frame: &mut Frame<'_>, area: Rect, view: &AgentsView, state: &ScreenState) {
    let area = render_stale_notice(frame, area, view, state);
    if state.detail_open {
        render_detail(frame, area, view, state);
        return;
    }
    if area.width < 120 {
        let index = state.narrow_panel % NARROW_STAGES.len();
        let (stage, label) = NARROW_STAGES[index];
        render_stage(
            frame,
            area,
            view,
            state,
            stage,
            &format!("{label} - PANEL {}/{}", index + 1, NARROW_STAGES.len()),
        );
        return;
    }

    let backlog_height = match state.display_mode {
        DisplayMode::Compact => 6,
        DisplayMode::Standard => 8,
        DisplayMode::LargeText => 10,
    };
    let sections =
        Layout::vertical([Constraint::Min(0), Constraint::Length(backlog_height)]).split(area);
    let columns = Layout::horizontal([
        Constraint::Percentage(25),
        Constraint::Percentage(25),
        Constraint::Percentage(25),
        Constraint::Percentage(25),
    ])
    .split(sections[0]);
    for (index, ((stage, label), column)) in MAIN_STAGES
        .into_iter()
        .zip(columns.iter().copied())
        .enumerate()
    {
        let title = if state.narrow_panel % NARROW_STAGES.len() == index {
            format!("{label} <")
        } else {
            label.to_owned()
        };
        render_stage(frame, column, view, state, stage, &title);
    }
    let backlog_title = if state.narrow_panel % NARROW_STAGES.len() == 4 {
        "BACKLOG <"
    } else {
        "BACKLOG"
    };
    render_stage(
        frame,
        sections[1],
        view,
        state,
        AgentStage::Backlog,
        backlog_title,
    );
}

fn render_stage(
    frame: &mut Frame<'_>,
    area: Rect,
    view: &AgentsView,
    state: &ScreenState,
    stage: AgentStage,
    title: &str,
) {
    let palette = state.theme.palette();
    let lines = if let Some(message) = unavailable_message(view.freshness, view.error.as_deref()) {
        vec![Line::from(message)]
    } else {
        let mut cards = view
            .rows
            .iter()
            .filter(|card| card_belongs_to_stage(card, stage))
            .collect::<Vec<_>>();
        cards.sort_by(|left, right| {
            right
                .urgent
                .cmp(&left.urgent)
                .then_with(|| right.priority.get().cmp(&left.priority.get()))
                .then_with(|| left.work_id.as_str().cmp(right.work_id.as_str()))
        });
        if cards.is_empty() {
            vec![Line::from("No tasks reported.")]
        } else {
            let focused_stage = NARROW_STAGES[state.narrow_panel % NARROW_STAGES.len()].0;
            let start = if stage == focused_stage {
                state.scroll_offset.min(cards.len() - 1)
            } else {
                0
            };
            cards
                .into_iter()
                .skip(start)
                .flat_map(|card| {
                    card_lines(
                        card,
                        state.display_mode,
                        state.selected_id.as_deref() == Some(card.work_id.as_str()),
                    )
                })
                .collect()
        }
    };
    frame.render_widget(
        Paragraph::new(lines)
            .style(base_style(palette))
            .wrap(Wrap { trim: false })
            .block(panel(title, palette)),
        area,
    );
}

fn card_belongs_to_stage(card: &AgentCard, stage: AgentStage) -> bool {
    match stage {
        AgentStage::Done => matches!(card.stage, AgentStage::Done | AgentStage::Failed),
        _ => card.stage == stage,
    }
}

fn card_lines(card: &AgentCard, display_mode: DisplayMode, selected: bool) -> Vec<Line<'static>> {
    let marker = if selected { "> " } else { "" };
    let status = card_status(card);
    let task = safe_text(card.title.as_str());
    let agent = safe_text(card.agent.as_str());
    let work_id = safe_text(card.work_id.as_str());
    let elapsed = card
        .elapsed_seconds
        .map_or_else(|| "UNAVAILABLE".to_owned(), format_elapsed);
    let model = card
        .model
        .as_deref()
        .map_or_else(|| "UNAVAILABLE".to_owned(), safe_text);
    let affected = if card.affected_areas.is_empty() {
        "NONE REPORTED".to_owned()
    } else {
        card.affected_areas
            .iter()
            .map(|value| safe_text(value))
            .collect::<Vec<_>>()
            .join(", ")
    };
    let mut lines = match display_mode {
        DisplayMode::Compact => vec![Line::from(format!(
            "{marker}{status} | {task} | {agent} | P{} | {elapsed} | {model} | {affected} | {work_id}",
            card.priority.get()
        ))],
        DisplayMode::Standard => vec![
            Line::from(format!("{marker}{status} | {task}")),
            Line::from(format!(
                "{agent} | P{} | {elapsed} | {work_id}",
                card.priority.get()
            )),
            Line::from(format!("MODEL {model} | AREA {affected}")),
        ],
        DisplayMode::LargeText => vec![
            Line::from(format!("{marker}TASK {task}")),
            Line::from(format!("STATUS {status}")),
            Line::from(format!("AGENT {agent}")),
            Line::from(format!(
                "PRIORITY {} | ELAPSED {elapsed}",
                card.priority.get()
            )),
            Line::from(format!("MODEL {model}")),
            Line::from(format!("AREA {affected} | ID {work_id}")),
        ],
    };
    lines.push(Line::default());
    lines
}

fn card_status(card: &AgentCard) -> String {
    if card.stage == AgentStage::Failed {
        return "! FAILED".to_owned();
    }
    let stage = stage_label(card.stage);
    if card.urgent {
        format!("[!] URGENT | {stage}")
    } else {
        format!("[ ] {stage}")
    }
}

fn render_detail(frame: &mut Frame<'_>, area: Rect, view: &AgentsView, state: &ScreenState) {
    let palette = state.theme.palette();
    let lines = detail_content(view, state);
    frame.render_widget(
        Paragraph::new(lines)
            .style(base_style(palette))
            .wrap(Wrap { trim: false })
            .scroll((u16::try_from(state.scroll_offset).unwrap_or(u16::MAX), 0))
            .block(panel("TASK DETAIL", palette)),
        area,
    );
}

pub(crate) fn agent_detail_line_count(view: &AgentsView, state: &ScreenState, width: u16) -> usize {
    Paragraph::new(detail_content(view, state))
        .wrap(Wrap { trim: false })
        .line_count(width)
}

fn detail_content(view: &AgentsView, state: &ScreenState) -> Vec<Line<'static>> {
    if let Some(message) = unavailable_message(view.freshness, view.error.as_deref()) {
        vec![Line::from(message)]
    } else if let Some(card) = selected_card(view, state) {
        detail_lines(card, &view.history)
    } else {
        vec![Line::from(
            "TASK DETAIL UNAVAILABLE - No selected task was reported.",
        )]
    }
}

fn selected_card<'a>(view: &'a AgentsView, state: &ScreenState) -> Option<&'a AgentCard> {
    let selected = state.selected_id.as_deref()?;
    view.rows
        .iter()
        .find(|card| card.work_id.as_str() == selected)
}

fn detail_lines(card: &AgentCard, history: &[TimelineRow]) -> Vec<Line<'static>> {
    let model = card
        .model
        .as_deref()
        .map_or_else(|| "UNAVAILABLE".to_owned(), safe_text);
    let affected = if card.affected_areas.is_empty() {
        "NONE REPORTED".to_owned()
    } else {
        card.affected_areas
            .iter()
            .map(|value| safe_text(value))
            .collect::<Vec<_>>()
            .join(", ")
    };
    let elapsed = card
        .elapsed_seconds
        .map_or_else(|| "UNAVAILABLE".to_owned(), format_elapsed);
    let session = card.session_id.as_ref().map_or_else(
        || "UNAVAILABLE".to_owned(),
        |value| safe_text(value.as_str()),
    );
    let context = card
        .context_percent
        .map_or_else(|| "UNAVAILABLE".to_owned(), |value| format!("{value:.1}%"));
    let cursor = card
        .detail_next_cursor
        .as_ref()
        .map_or_else(|| "NONE".to_owned(), |value| safe_text(value.as_str()));
    let mut lines = vec![
        Line::from(format!("TASK ID: {}", safe_text(card.work_id.as_str()))),
        Line::from(format!("AGENT: {}", safe_text(card.agent.as_str()))),
        Line::from(format!("TITLE: {}", safe_text(card.title.as_str()))),
        Line::from(format!("STATUS: {}", card_status(card))),
        Line::from(format!("ELAPSED: {elapsed}")),
        Line::from(format!("MODEL: {model}")),
        Line::from(format!("AFFECTED: {affected}")),
        Line::from(format!("SESSION: {session}")),
        Line::from(format!("CONTEXT: {context}")),
        Line::from(format!("NEXT CURSOR: {cursor}")),
    ];
    lines.push(Line::from("PLAN"));
    if card.plan_steps.is_empty() {
        lines.push(Line::from("[?] UNAVAILABLE - No plan steps reported."));
    } else {
        lines.extend(card.plan_steps.iter().enumerate().map(|(index, step)| {
            Line::from(format!("{}. {}", index + 1, safe_text(step.as_str())))
        }));
    }
    lines.push(Line::from("ACTIVITY"));
    if card.activity.is_empty() {
        lines.push(Line::from("[?] UNAVAILABLE - No activity reported."));
    } else {
        lines.extend(card.activity.iter().map(|activity| {
            Line::from(format!(
                "[{}] {} | {} | EVIDENCE {}",
                activity_kind_label(activity.kind),
                safe_text(activity.summary.as_str()),
                format_eastern_time(&activity.occurred_at_utc),
                evidence_list(&activity.evidence_ids)
            ))
        }));
    }
    lines.push(Line::from(format!(
        "EVIDENCE: {}",
        evidence_list(&card.evidence_ids)
    )));
    lines.push(Line::from(card.chat_agent_id.as_ref().map_or_else(
        || "CHAT: [?] UNAVAILABLE - No approved chat binding.".to_owned(),
        |agent_id| {
            format!(
                "CHAT: press i to open approved separate chat {}",
                safe_text(agent_id.as_str())
            )
        },
    )));
    lines.push(Line::default());
    lines.push(Line::from("WORK-LINKED HISTORY"));
    let linked = history
        .iter()
        .filter(|row| row.work_id.as_ref() == Some(&card.work_id))
        .collect::<Vec<_>>();
    if linked.is_empty() {
        lines.push(Line::from("[?] UNAVAILABLE - No linked history reported."));
    } else {
        lines.extend(linked.into_iter().map(|row| {
            Line::from(format!(
                "{} | {} | {} | EVIDENCE {}",
                safe_text(row.event_id.as_str()),
                format_eastern_time(&row.occurred_at_utc),
                safe_text(row.summary.as_str()),
                evidence_list(&row.evidence_ids)
            ))
        }));
    }
    lines
}

fn activity_kind_label(kind: AgentActivityKind) -> &'static str {
    match kind {
        AgentActivityKind::Stage => "STAGE",
        AgentActivityKind::Tool => "TOOL",
        AgentActivityKind::File => "FILE",
        AgentActivityKind::Decision => "DECISION",
        AgentActivityKind::Error => "ERROR",
        AgentActivityKind::Result => "RESULT",
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

fn render_stale_notice(
    frame: &mut Frame<'_>,
    area: Rect,
    view: &AgentsView,
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

fn stage_label(stage: AgentStage) -> &'static str {
    match stage {
        AgentStage::Backlog => "BACKLOG",
        AgentStage::Queued => "QUEUED",
        AgentStage::Running => "RUNNING",
        AgentStage::Waiting => "WAITING",
        AgentStage::Done => "DONE",
        AgentStage::Failed => "FAILED",
    }
}

fn format_elapsed(seconds: f64) -> String {
    let total = seconds.round() as u64;
    match total.cmp(&60) {
        Ordering::Less => format!("{total}s"),
        _ => format!("{}m {:02}s", total / 60, total % 60),
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
