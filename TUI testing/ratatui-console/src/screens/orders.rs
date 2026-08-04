use std::cmp::Ordering;
use std::collections::BTreeMap;

use ratatui::Frame;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::text::Line;
use ratatui::widgets::{Paragraph, Wrap};

use crate::contract::{OrderReconciliation, OrderSide, OrderStatus, OrdersView, UtcTimestamp};
use crate::screens::{
    DetailKind, ScreenState, base_style, content_area_with_stale_notice, palette, panel,
    unavailable_message,
};
use crate::ui::format_eastern_time;
use crate::widgets::sanitize_line;

pub fn render_orders(frame: &mut Frame<'_>, area: Rect, view: &OrdersView, state: &ScreenState) {
    let area =
        content_area_with_stale_notice(frame, area, view.freshness, view.error.as_deref(), state);
    let palette = palette(state);
    let sections =
        Layout::vertical([Constraint::Percentage(76), Constraint::Percentage(24)]).split(area);
    if let Some(message) = unavailable_message(view.freshness, view.error.as_deref()) {
        for (title, section) in [
            ("ORDERS", sections[0]),
            ("RECONCILIATION OWNER", sections[1]),
        ] {
            frame.render_widget(
                Paragraph::new(message.clone())
                    .style(base_style(palette))
                    .wrap(Wrap { trim: true })
                    .block(panel(title, palette)),
                section,
            );
        }
        return;
    }

    let mut grouped = BTreeMap::<&str, Vec<_>>::new();
    for order in &view.rows {
        grouped
            .entry(order.symbol.as_str())
            .or_default()
            .push(order);
    }
    let mut lines = Vec::new();
    let mut selected_line = 0;
    for (symbol, mut orders) in grouped {
        orders.sort_by(|left, right| {
            newest_first(
                left.submitted_at_utc.as_ref(),
                right.submitted_at_utc.as_ref(),
            )
            .then_with(|| right.order_id.as_str().cmp(left.order_id.as_str()))
        });
        lines.push(Line::from(format!("== {symbol} ==")));
        for order in orders {
            let submitted = order
                .submitted_at_utc
                .as_ref()
                .map_or_else(|| "UNAVAILABLE".to_owned(), format_eastern_time);
            let broker = order
                .broker_order_id
                .as_ref()
                .map_or("UNAVAILABLE".to_owned(), |value| sanitize_line(value));
            if is_selected(state, order.order_id.as_str(), DetailKind::Order) {
                selected_line = lines.len();
            }
            lines.push(Line::from(format!(
                "{}{} | {} {} {} | {} | submitted {} | broker {} | {}",
                marker(state, order.order_id.as_str(), DetailKind::Order),
                order.order_id.as_str(),
                side(order.side),
                order.quantity.as_str(),
                symbol,
                status(order.status),
                submitted,
                broker,
                reconciliation(order.reconciliation),
            )));
            let expected = order
                .expected_price
                .as_ref()
                .map_or("UNAVAILABLE", |value| value.as_str());
            let actual = order
                .actual_price
                .as_ref()
                .map_or("UNAVAILABLE", |value| value.as_str());
            lines.push(Line::from(format!(
                "EXPECTED {expected} | ACTUAL {actual} | SLIPPAGE {expected} -> {actual}"
            )));
            if order.fills.is_empty() {
                lines.push(Line::from("FILLS 0 | FEE UNAVAILABLE"));
            } else {
                lines.push(Line::from(format!("FILLS {}", order.fills.len())));
                for fill in &order.fills {
                    if is_selected(state, fill.fill_id.as_str(), DetailKind::Fill) {
                        selected_line = lines.len();
                    }
                    lines.push(Line::from(format!(
                        "{}{} | quantity {} | price {} | FEE {} | {}",
                        marker(state, fill.fill_id.as_str(), DetailKind::Fill),
                        fill.fill_id.as_str(),
                        fill.quantity.as_str(),
                        fill.price.as_str(),
                        fill.fee.as_str(),
                        format_eastern_time(&fill.filled_at_utc),
                    )));
                }
            }
        }
    }
    if lines.is_empty() {
        lines.push(Line::from("No orders reported."));
    }
    frame.render_widget(
        Paragraph::new(lines)
            .style(base_style(palette))
            .wrap(Wrap { trim: false })
            .scroll((u16::try_from(selected_line).unwrap_or(u16::MAX), 0))
            .block(panel("ORDERS - GROUPED BY SYMBOL / NEWEST FIRST", palette)),
        sections[0],
    );

    let mut owner_lines = if view.reconciliation_agents.is_empty() {
        vec![Line::from("No reconciliation tasks reported.")]
    } else {
        view.reconciliation_agents
            .iter()
            .map(|agent| {
                Line::from(format!(
                    "{}{} | {} | {} | {} | priority {} | affected {}",
                    marker(state, agent.work_id.as_str(), DetailKind::Agent),
                    agent.work_id.as_str(),
                    sanitize_line(agent.agent.as_str()),
                    sanitize_line(agent.title.as_str()),
                    format!("{:?}", agent.stage).to_uppercase(),
                    agent.priority.get(),
                    agent
                        .affected_areas
                        .iter()
                        .map(|value| sanitize_line(value))
                        .collect::<Vec<_>>()
                        .join(", ")
                ))
            })
            .collect()
    };
    owner_lines.push(Line::from("HISTORY"));
    if view.history.is_empty() {
        owner_lines.push(Line::from("No order history reported."));
    } else {
        owner_lines.extend(view.history.iter().map(|event| {
            Line::from(format!(
                "{}{} | {} | {}",
                marker(state, event.event_id.as_str(), DetailKind::Event),
                event.event_id.as_str(),
                format_eastern_time(&event.occurred_at_utc),
                sanitize_line(event.summary.as_str()),
            ))
        }));
    }
    let owner_scroll = owner_lines
        .iter()
        .position(|line| line.to_string().starts_with("> "))
        .unwrap_or(0);
    frame.render_widget(
        Paragraph::new(owner_lines)
            .style(base_style(palette))
            .wrap(Wrap { trim: true })
            .scroll((u16::try_from(owner_scroll).unwrap_or(u16::MAX), 0))
            .block(panel("RECONCILIATION OWNER / HISTORY", palette)),
        sections[1],
    );
}

fn is_selected(state: &ScreenState, id: &str, kind: DetailKind) -> bool {
    state.selected_id.as_deref() == Some(id) && state.selected_kind == Some(kind)
}

fn marker(state: &ScreenState, id: &str, kind: DetailKind) -> &'static str {
    if is_selected(state, id, kind) {
        "> "
    } else {
        "  "
    }
}

fn newest_first(left: Option<&UtcTimestamp>, right: Option<&UtcTimestamp>) -> Ordering {
    match (left, right) {
        (Some(left), Some(right)) => compare_utc(right, left),
        (Some(_), None) => Ordering::Less,
        (None, Some(_)) => Ordering::Greater,
        (None, None) => Ordering::Equal,
    }
}

fn compare_utc(left: &UtcTimestamp, right: &UtcTimestamp) -> Ordering {
    let left = left.as_str();
    let right = right.as_str();
    left[..19]
        .cmp(&right[..19])
        .then_with(|| utc_fraction(left).cmp(utc_fraction(right)))
}

fn utc_fraction(timestamp: &str) -> &str {
    if timestamp.as_bytes().get(19) == Some(&b'.') {
        &timestamp[20..26]
    } else {
        "000000"
    }
}

fn side(value: OrderSide) -> &'static str {
    match value {
        OrderSide::Buy => "BUY",
        OrderSide::Sell => "SELL",
    }
}

fn status(value: OrderStatus) -> &'static str {
    match value {
        OrderStatus::Proposed => "PROPOSED",
        OrderStatus::Approved => "APPROVED",
        OrderStatus::Submitted => "SUBMITTED",
        OrderStatus::Partial => "PARTIAL",
        OrderStatus::Filled => "FILLED",
        OrderStatus::Rejected => "REJECTED",
        OrderStatus::Cancelled => "CANCELLED",
    }
}

fn reconciliation(value: OrderReconciliation) -> &'static str {
    match value {
        OrderReconciliation::Pending => "RECONCILIATION PENDING",
        OrderReconciliation::Matched => "RECONCILIATION MATCHED",
        OrderReconciliation::Mismatch => "RECONCILIATION MISMATCH",
        OrderReconciliation::Unavailable => "RECONCILIATION UNAVAILABLE",
    }
}
