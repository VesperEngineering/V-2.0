use ratatui::Frame;
use ratatui::layout::{Constraint, Rect};
use ratatui::text::Line;
use ratatui::widgets::{Cell, HighlightSpacing, Paragraph, Row, Table, TableState, Wrap};

use crate::contract::{AgentStage, ImpactView};
use crate::layout::{impact_panels, impact_visible_columns, is_narrow_width};
use crate::screens::{
    ScreenState, base_style, clean, content_area_with_stale_notice, palette, panel,
    table_row_height, unavailable_message,
};
use crate::widgets::sanitize_line;
use crate::widgets::timeline::timeline_line;
use crate::widgets::weights::{weight_constraints, weight_header_for, weight_row_for};

pub fn render_impact(frame: &mut Frame<'_>, area: Rect, view: &ImpactView, state: &ScreenState) {
    let area =
        content_area_with_stale_notice(frame, area, view.freshness, view.error.as_deref(), state);
    if is_narrow_width(area.width) {
        match state.narrow_panel % 3 {
            0 => render_holdings(frame, area, view, state, "HOLDINGS - PANEL 1/3"),
            1 => render_events(frame, area, view, state, "IMPACT FEED - PANEL 2/3"),
            _ => render_agents(frame, area, view, state, "AGENT WORK - PANEL 3/3"),
        }
        return;
    }

    let panels = impact_panels(area, &state.panel_sizes);
    render_holdings(frame, panels[0], view, state, "HOLDINGS");
    render_events(frame, panels[1], view, state, "IMPACT FEED");
    render_agents(frame, panels[2], view, state, "AGENT WORK");
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
    let visible = impact_visible_columns(&state.visible_columns);
    let columns = visible
        .iter()
        .copied()
        .filter(|column| matches!(*column, "symbol" | "current" | "proposed" | "approved"))
        .collect::<Vec<_>>();
    let rows = view
        .holdings
        .iter()
        .skip(state.scroll_offset)
        .take(height)
        .map(|row| weight_row_for(row, palette, &columns).height(row_height));
    let selected = state.selected_id.as_deref().and_then(|selected| {
        view.holdings
            .iter()
            .skip(state.scroll_offset)
            .take(height)
            .position(|row| row.symbol.as_str() == selected)
    });
    let mut table_state = TableState::default();
    table_state.select(selected);
    let mut table = Table::new(rows, weight_constraints(&columns))
        .highlight_symbol("> ")
        .highlight_spacing(HighlightSpacing::Always)
        .style(base_style(palette))
        .block(panel(title, palette));
    if !omit_header {
        table = table.header(weight_header_for(palette, &columns).height(row_height));
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
    let visible = impact_visible_columns(&state.visible_columns);
    let columns = visible
        .iter()
        .copied()
        .filter(|column| matches!(*column, "agent" | "task" | "stage" | "priority"))
        .collect::<Vec<_>>();
    let widths = columns
        .iter()
        .map(|column| match *column {
            "agent" => 25_u32,
            "task" => 45_u32,
            "stage" => 20_u32,
            "priority" => 10_u32,
            _ => 0,
        })
        .collect::<Vec<_>>();
    let total = widths.iter().sum::<u32>().max(1);
    let rows = view.agents.iter().map(|agent| {
        Row::new(columns.iter().map(|column| match *column {
            "agent" => Cell::from(format!(
                "{} {}",
                if agent.urgent { "[!]" } else { "[ ]" },
                sanitize_line(agent.agent.as_str())
            )),
            "task" => Cell::from(clean(&agent.title)),
            "stage" => Cell::from(stage(agent.stage).to_owned()),
            "priority" => Cell::from(agent.priority.get().to_string()),
            _ => Cell::default(),
        }))
        .height(row_height)
    });
    frame.render_widget(
        Table::new(
            rows,
            widths
                .into_iter()
                .map(|width| Constraint::Ratio(width, total)),
        )
        .header(
            Row::new(columns.iter().map(|column| match *column {
                "agent" => "Agent",
                "task" => "Task",
                "stage" => "Stage",
                "priority" => "P",
                _ => "",
            }))
            .height(row_height),
        )
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
