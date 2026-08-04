use ratatui::style::Style;
use ratatui::widgets::{Cell, Row};

use crate::contract::{PortfolioChangeState, PortfolioRow};
use crate::theme::Palette;

pub fn weight_header(palette: Palette) -> Row<'static> {
    Row::new(["Symbol", "Current", "Proposed", "Approved"]).style(base_style(palette))
}

pub fn weight_row(row: &PortfolioRow, palette: Palette) -> Row<'static> {
    let proposed_style = match row.change_state {
        PortfolioChangeState::Proposed
        | PortfolioChangeState::Approved
        | PortfolioChangeState::Executing => palette.active,
        PortfolioChangeState::Reconciling => palette.waiting,
        PortfolioChangeState::Unchanged => base_style(palette),
    };
    let approved_style = match row.change_state {
        PortfolioChangeState::Approved | PortfolioChangeState::Executing => palette.active,
        PortfolioChangeState::Reconciling => palette.waiting,
        PortfolioChangeState::Unchanged | PortfolioChangeState::Proposed => base_style(palette),
    };
    Row::new([
        Cell::from(row.symbol.as_str().to_owned()).style(base_style(palette)),
        Cell::from(format_weight(Some(row.current_weight))).style(base_style(palette)),
        Cell::from(format_weight(row.proposed_weight)).style(proposed_style),
        Cell::from(format_weight(row.approved_weight)).style(approved_style),
    ])
}

fn format_weight(value: Option<f64>) -> String {
    value.map_or_else(
        || "-".to_owned(),
        |weight| format!("{:.2}%", weight * 100.0),
    )
}

fn base_style(palette: Palette) -> Style {
    Style::default()
        .fg(palette.foreground)
        .bg(palette.background)
}
