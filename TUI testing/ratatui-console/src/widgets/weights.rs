use ratatui::layout::Constraint;
use ratatui::style::Style;
use ratatui::widgets::{Cell, Row};

use crate::contract::{PortfolioChangeState, PortfolioRow};
use crate::theme::Palette;

pub fn weight_header(palette: Palette) -> Row<'static> {
    weight_header_for(palette, &["symbol", "current", "proposed", "approved"])
}

pub fn weight_row(row: &PortfolioRow, palette: Palette) -> Row<'static> {
    weight_row_for(row, palette, &["symbol", "current", "proposed", "approved"])
}

pub fn weight_constraints(columns: &[&str]) -> Vec<Constraint> {
    let widths = columns
        .iter()
        .filter_map(|column| match *column {
            "symbol" => Some(28_u32),
            "current" | "proposed" | "approved" => Some(24_u32),
            _ => None,
        })
        .collect::<Vec<_>>();
    let total = widths.iter().sum::<u32>().max(1);
    widths
        .into_iter()
        .map(|width| Constraint::Ratio(width, total))
        .collect()
}

pub fn weight_header_for(palette: Palette, columns: &[&str]) -> Row<'static> {
    Row::new(columns.iter().filter_map(|column| match *column {
        "symbol" => Some("Symbol"),
        "current" => Some("Current"),
        "proposed" => Some("Proposed"),
        "approved" => Some("Approved"),
        _ => None,
    }))
    .style(base_style(palette))
}

pub fn weight_row_for(row: &PortfolioRow, palette: Palette, columns: &[&str]) -> Row<'static> {
    if matches!(
        row.change_state,
        PortfolioChangeState::Executing | PortfolioChangeState::Reconciling
    ) {
        let style = if row.change_state == PortfolioChangeState::Executing {
            palette.active
        } else {
            palette.waiting
        };
        return Row::new(weight_cells(row, columns)).style(style);
    }
    let proposed_style = match row.change_state {
        PortfolioChangeState::Proposed | PortfolioChangeState::Approved => palette.active,
        PortfolioChangeState::Executing | PortfolioChangeState::Reconciling => unreachable!(),
        PortfolioChangeState::Unchanged => base_style(palette),
    };
    let approved_style = match row.change_state {
        PortfolioChangeState::Approved => palette.active,
        PortfolioChangeState::Executing | PortfolioChangeState::Reconciling => unreachable!(),
        PortfolioChangeState::Unchanged | PortfolioChangeState::Proposed => base_style(palette),
    };
    Row::new(columns.iter().filter_map(|column| match *column {
        "symbol" => Some(Cell::from(row.symbol.as_str().to_owned()).style(base_style(palette))),
        "current" => {
            Some(Cell::from(format_weight(Some(row.current_weight))).style(base_style(palette)))
        }
        "proposed" => Some(Cell::from(format_weight(row.proposed_weight)).style(proposed_style)),
        "approved" => Some(Cell::from(format_weight(row.approved_weight)).style(approved_style)),
        _ => None,
    }))
}

fn weight_cells(row: &PortfolioRow, columns: &[&str]) -> Vec<Cell<'static>> {
    columns
        .iter()
        .filter_map(|column| match *column {
            "symbol" => Some(Cell::from(row.symbol.as_str().to_owned())),
            "current" => Some(Cell::from(format_weight(Some(row.current_weight)))),
            "proposed" => Some(Cell::from(format_weight(row.proposed_weight))),
            "approved" => Some(Cell::from(format_weight(row.approved_weight))),
            _ => None,
        })
        .collect()
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
