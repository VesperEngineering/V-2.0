use ratatui::Frame;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::text::Line;
use ratatui::widgets::{HighlightSpacing, Paragraph, Table, TableState, Wrap};

use crate::contract::{AssetType, MetricRow, PortfolioView, ReturnComponent, ReturnComponentRow};
use crate::detail::{DetailOverlay, detail_area};
use crate::screens::{
    PerformancePeriod, ScreenState, base_style, content_area_with_stale_notice, palette, panel,
    table_row_height, unavailable_message,
};
use crate::widgets::sanitize_line;
use crate::widgets::weights::{weight_header, weight_row};

pub fn render_portfolio(
    frame: &mut Frame<'_>,
    area: Rect,
    view: &PortfolioView,
    state: &ScreenState,
) {
    let area =
        content_area_with_stale_notice(frame, area, view.freshness, view.error.as_deref(), state);
    let palette = palette(state);
    let sections = if area.width < 100 {
        Layout::vertical([
            Constraint::Percentage(52),
            Constraint::Percentage(26),
            Constraint::Percentage(22),
        ])
        .split(area)
    } else {
        Layout::vertical([
            Constraint::Percentage(58),
            Constraint::Percentage(22),
            Constraint::Percentage(20),
        ])
        .split(area)
    };
    render_weights(frame, sections[0], view, state);
    render_returns(frame, sections[1], view, state);
    render_metrics(frame, sections[2], view, state);

    if unavailable_message(view.freshness, view.error.as_deref()).is_none()
        && state.detail_open
        && let Some(symbol) = state.selected_id.as_deref()
    {
        let lines = portfolio_detail_lines(view, symbol);
        frame.render_widget(
            DetailOverlay::new(format!("{symbol} HISTORY"), lines, palette)
                .scroll(state.scroll_offset),
            detail_area(area),
        );
    }
}

pub(crate) fn portfolio_detail_line_count(
    view: &PortfolioView,
    state: &ScreenState,
    width: u16,
) -> usize {
    let lines = state
        .selected_id
        .as_deref()
        .map_or_else(Vec::new, |symbol| portfolio_detail_lines(view, symbol));
    Paragraph::new(
        lines
            .into_iter()
            .map(|line| Line::from(sanitize_line(&line)))
            .collect::<Vec<_>>(),
    )
    .wrap(Wrap { trim: false })
    .line_count(width)
}

fn portfolio_detail_lines(view: &PortfolioView, symbol: &str) -> Vec<String> {
    let current = view.rows.iter().find(|row| row.symbol.as_str() == symbol);
    let mut lines = Vec::new();
    if let Some(row) = current {
        lines.push(format!(
            "PINNED {} | {} | quantity {} | price {} | value {}",
            row.symbol.as_str(),
            asset_type(row.asset_type),
            row.quantity.as_str(),
            row.price
                .as_ref()
                .map_or("UNAVAILABLE", |value| value.as_str()),
            row.market_value
                .as_ref()
                .map_or("UNAVAILABLE", |value| value.as_str()),
        ));
        lines.push(format!(
            "CURRENT {:.2}% | PROPOSED {} | APPROVED {} | RECONCILIATION {:?}",
            row.current_weight * 100.0,
            format_optional_weight(row.proposed_weight),
            format_optional_weight(row.approved_weight),
            row.reconciliation
        ));
    } else {
        lines.push("Current position facts are unavailable.".to_owned());
    }
    lines.extend(
        view.history
            .iter()
            .filter(|event| {
                event
                    .symbol
                    .as_ref()
                    .is_some_and(|value| value.as_str() == symbol)
            })
            .map(|event| {
                format!(
                    "{} | {}",
                    event.occurred_at_utc.as_str(),
                    sanitize_line(event.summary.as_str())
                )
            }),
    );
    lines
}

fn render_weights(frame: &mut Frame<'_>, area: Rect, view: &PortfolioView, state: &ScreenState) {
    let palette = palette(state);
    let rank = view
        .rank_source
        .as_ref()
        .map_or("RANK UNAVAILABLE".to_owned(), |value| {
            format!("EXECUTED RANK: {}", sanitize_line(value.as_str()))
        });
    if let Some(message) = unavailable_message(view.freshness, view.error.as_deref()) {
        frame.render_widget(
            Paragraph::new(message)
                .style(base_style(palette))
                .wrap(Wrap { trim: true })
                .block(panel(format!("PORTFOLIO WEIGHTS | {rank}"), palette)),
            area,
        );
        return;
    }
    let row_height = table_row_height(state);
    let height = usize::from(area.height.saturating_sub(3) / row_height);
    let rows = view
        .rows
        .iter()
        .skip(state.scroll_offset)
        .take(height)
        .map(|row| weight_row(row, palette).height(row_height));
    let selected = state.selected_id.as_deref().and_then(|selected| {
        view.rows
            .iter()
            .skip(state.scroll_offset)
            .take(height)
            .position(|row| row.symbol.as_str() == selected)
    });
    let mut table_state = TableState::default();
    table_state.select(selected);
    frame.render_stateful_widget(
        Table::new(
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
        .header(weight_header(palette).height(row_height))
        .style(base_style(palette))
        .block(panel(format!("PORTFOLIO WEIGHTS | {rank}"), palette)),
        area,
        &mut table_state,
    );
}

fn render_returns(frame: &mut Frame<'_>, area: Rect, view: &PortfolioView, state: &ScreenState) {
    let palette = palette(state);
    let (label, rows) = match state.performance_period {
        PerformancePeriod::Today => ("TODAY", &view.returns_today),
        PerformancePeriod::SinceRebalance => ("SINCE REBALANCE", &view.returns_since_rebalance),
        PerformancePeriod::SinceStart => ("SINCE START", &view.returns_since_start),
    };
    let lines = if let Some(message) = unavailable_message(view.freshness, view.error.as_deref()) {
        vec![Line::from(message)]
    } else if rows.is_empty() {
        vec![Line::from(
            "[?] UNAVAILABLE - Return components are unavailable.",
        )]
    } else {
        rows.iter().map(return_line).collect()
    };
    frame.render_widget(
        Paragraph::new(lines)
            .style(base_style(palette))
            .block(panel(format!("PERFORMANCE | {label}"), palette)),
        area,
    );
}

fn return_line(row: &ReturnComponentRow) -> Line<'static> {
    let label = match row.component {
        ReturnComponent::Price => "PRICE",
        ReturnComponent::Dividends => "DIVIDENDS",
        ReturnComponent::CashInterest => "CASH INTEREST",
        ReturnComponent::Fees => "FEES",
        ReturnComponent::Sp500TotalReturn => "S&P 500 TOTAL RETURN",
    };
    Line::from(format!("{label}: {}", row.value.as_str()))
}

fn render_metrics(frame: &mut Frame<'_>, area: Rect, view: &PortfolioView, state: &ScreenState) {
    let palette = palette(state);
    let lines = if let Some(message) = unavailable_message(view.freshness, view.error.as_deref()) {
        vec![Line::from(message)]
    } else if view.metrics.is_empty() {
        vec![Line::from(
            "[?] UNAVAILABLE - Portfolio metrics are unavailable.",
        )]
    } else {
        view.metrics.iter().map(metric_line).collect()
    };
    frame.render_widget(
        Paragraph::new(lines)
            .style(base_style(palette))
            .block(panel("PORTFOLIO METRICS - EQUAL WEIGHT", palette)),
        area,
    );
}

fn metric_line(row: &MetricRow) -> Line<'static> {
    let value = row
        .value
        .map_or("UNAVAILABLE".to_owned(), |value| format!("{value:.4}"));
    Line::from(format!(
        "{}: {} {} [{}]",
        row.metric_id.as_str(),
        value,
        sanitize_line(row.unit.as_str()),
        format!("{:?}", row.freshness).to_uppercase()
    ))
}

fn asset_type(value: AssetType) -> &'static str {
    match value {
        AssetType::Stock => "STOCK",
        AssetType::Etf => "ETF",
        AssetType::Cash => "CASH",
    }
}

fn format_optional_weight(value: Option<f64>) -> String {
    value.map_or_else(
        || "-".to_owned(),
        |weight| format!("{:.2}%", weight * 100.0),
    )
}
