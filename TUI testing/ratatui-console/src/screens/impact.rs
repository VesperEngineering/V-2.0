use ratatui::Frame;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::text::Line;
use ratatui::widgets::{HighlightSpacing, Paragraph, Row, Table, TableState, Wrap};

use crate::contract::{AgentStage, ImpactView};
use crate::screens::{
    ScreenState, base_style, clean, content_area_with_stale_notice, palette, panel,
    table_row_height, unavailable_message,
};
use crate::widgets::sanitize_line;
use crate::widgets::timeline::timeline_line;
use crate::widgets::weights::{weight_header, weight_row};

pub fn render_impact(frame: &mut Frame<'_>, area: Rect, view: &ImpactView, state: &ScreenState) {
    let area =
        content_area_with_stale_notice(frame, area, view.freshness, view.error.as_deref(), state);
    if area.width < 100 {
        match state.narrow_panel % 3 {
            0 => render_holdings(frame, area, view, state, "HOLDINGS - PANEL 1/3"),
            1 => render_events(frame, area, view, state, "IMPACT FEED - PANEL 2/3"),
            _ => render_agents(frame, area, view, state, "AGENT WORK - PANEL 3/3"),
        }
        return;
    }

    let columns =
        Layout::horizontal([Constraint::Percentage(65), Constraint::Percentage(35)]).split(area);
    let right = Layout::vertical([Constraint::Percentage(60), Constraint::Percentage(40)])
        .split(columns[1]);
    render_holdings(frame, columns[0], view, state, "HOLDINGS");
    render_events(frame, right[0], view, state, "IMPACT FEED");
    render_agents(frame, right[1], view, state, "AGENT WORK");
}

fn render_holdings(
    frame: &mut Frame<'_>,
    area: Rect,
    view: &ImpactView,
    state: &ScreenState,
    title: &str,
) {
    let palette = palette(state);
    if let Some(message) = unavailable_message(view.freshness, view.error.as_deref()) {
        frame.render_widget(
            Paragraph::new(message)
                .style(base_style(palette))
                .wrap(Wrap { trim: true })
                .block(panel(title, palette)),
            area,
        );
        return;
    }
    if view.holdings.is_empty() {
        frame.render_widget(
            Paragraph::new("No holdings reported.")
                .style(base_style(palette))
                .block(panel(title, palette)),
            area,
        );
        return;
    }
    let omit_header = area.height <= 3;
    let row_height = if omit_header {
        1
    } else {
        table_row_height(state)
    };
    let table_rows = if omit_header {
        area.height.saturating_sub(2)
    } else {
        area.height.saturating_sub(3) / row_height
    };
    let height = usize::from(table_rows);
    let rows = view
        .holdings
        .iter()
        .skip(state.scroll_offset)
        .take(height)
        .map(|row| weight_row(row, palette).height(row_height));
    let selected = state.selected_id.as_deref().and_then(|selected| {
        view.holdings
            .iter()
            .skip(state.scroll_offset)
            .take(height)
            .position(|row| row.symbol.as_str() == selected)
    });
    let mut table_state = TableState::default();
    table_state.select(selected);
    let mut table = Table::new(
        rows,
        [
            Constraint::Percentage(28),
            Constraint::Percentage(24),
            Constraint::Percentage(24),
            Constraint::Percentage(24),
        ],
    )
    .highlight_symbol("> ")
    .highlight_spacing(HighlightSpacing::Always)
    .style(base_style(palette))
    .block(panel(title, palette));
    if !omit_header {
        table = table.header(weight_header(palette).height(row_height));
    }
    frame.render_stateful_widget(table, area, &mut table_state);
}

fn render_events(
    frame: &mut Frame<'_>,
    area: Rect,
    view: &ImpactView,
    state: &ScreenState,
    title: &str,
) {
    let palette = palette(state);
    let lines = unavailable_message(view.freshness, view.error.as_deref()).map_or_else(
        || {
            let lines = view
                .events
                .iter()
                .skip(state.scroll_offset)
                .map(|row| timeline_line(row, palette))
                .collect::<Vec<_>>();
            if lines.is_empty() {
                vec![Line::from("No impact events reported.")]
            } else {
                lines
            }
        },
        |message| vec![Line::from(message)],
    );
    frame.render_widget(
        Paragraph::new(lines)
            .style(base_style(palette))
            .wrap(Wrap { trim: true })
            .block(panel(title, palette)),
        area,
    );
}

fn render_agents(
    frame: &mut Frame<'_>,
    area: Rect,
    view: &ImpactView,
    state: &ScreenState,
    title: &str,
) {
    let palette = palette(state);
    if let Some(message) = unavailable_message(view.freshness, view.error.as_deref()) {
        frame.render_widget(
            Paragraph::new(message)
                .style(base_style(palette))
                .block(panel(title, palette)),
            area,
        );
        return;
    }
    if view.agents.is_empty() {
        frame.render_widget(
            Paragraph::new("No agent work reported.")
                .style(base_style(palette))
                .block(panel(title, palette)),
            area,
        );
        return;
    }
    let row_height = table_row_height(state);
    let rows = view.agents.iter().map(|agent| {
        Row::new([
            format!(
                "{} {}",
                if agent.urgent { "[!]" } else { "[ ]" },
                sanitize_line(agent.agent.as_str())
            ),
            clean(&agent.title),
            stage(agent.stage).to_owned(),
            agent.priority.get().to_string(),
        ])
        .height(row_height)
    });
    frame.render_widget(
        Table::new(
            rows,
            [
                Constraint::Percentage(25),
                Constraint::Percentage(45),
                Constraint::Percentage(20),
                Constraint::Percentage(10),
            ],
        )
        .header(Row::new(["Agent", "Task", "Stage", "P"]).height(row_height))
        .style(base_style(palette))
        .block(panel(title, palette)),
        area,
    );
}

fn stage(value: AgentStage) -> &'static str {
    match value {
        AgentStage::Backlog => "BACKLOG",
        AgentStage::Queued => "QUEUED",
        AgentStage::Running => "RUNNING",
        AgentStage::Waiting => "WAITING",
        AgentStage::Done => "DONE",
        AgentStage::Failed => "FAILED",
    }
}
