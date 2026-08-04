use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::style::Style;
use ratatui::text::Line;
use ratatui::widgets::{Block, Borders, Paragraph, Wrap};

use crate::contract::AlertSeverity;
use crate::theme::Palette;
use crate::widgets::sanitize_line;
use crate::widgets::status::alert_badge;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CardView {
    pub title: String,
    pub severity: AlertSeverity,
    pub lines: Vec<String>,
}

impl CardView {
    pub fn new(title: impl Into<String>, severity: AlertSeverity, lines: Vec<String>) -> Self {
        Self {
            title: title.into(),
            severity,
            lines,
        }
    }
}

pub fn card(view: &CardView, palette: Palette) -> Paragraph<'static> {
    let mut lines = vec![Line::from(alert_badge(view.severity, palette))];
    lines.extend(
        view.lines
            .iter()
            .map(|line| Line::from(sanitize_line(line))),
    );
    Paragraph::new(lines)
        .style(base_style(palette))
        .wrap(Wrap { trim: true })
        .block(
            Block::default()
                .borders(Borders::ALL)
                .title(sanitize_line(&view.title))
                .style(base_style(palette)),
        )
}

pub fn board_columns(area: Rect, count: usize) -> Vec<Rect> {
    if count == 0 {
        return Vec::new();
    }
    let denominator = u32::try_from(count).unwrap_or(u32::MAX);
    Layout::horizontal(vec![Constraint::Ratio(1, denominator); count])
        .split(area)
        .to_vec()
}

fn base_style(palette: Palette) -> Style {
    Style::default()
        .fg(palette.foreground)
        .bg(palette.background)
}
