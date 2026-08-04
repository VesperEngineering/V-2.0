use ratatui::style::Style;
use ratatui::text::{Line, Span};

use crate::contract::TimelineRow;
use crate::theme::Palette;
use crate::ui::format_eastern_time;
use crate::widgets::sanitize_line;
use crate::widgets::status::alert_badge;

pub fn timeline_rows(rows: &[TimelineRow], show_all: bool) -> impl Iterator<Item = &TimelineRow> {
    rows.iter().filter(move |row| show_all || row.impact)
}

pub fn timeline_line(row: &TimelineRow, palette: Palette) -> Line<'static> {
    Line::from(vec![
        alert_badge(row.severity, palette),
        Span::styled(
            format!(
                " {}  {}",
                format_eastern_time(&row.occurred_at_utc),
                sanitize_line(row.summary.as_str())
            ),
            base_style(palette),
        ),
    ])
}

fn base_style(palette: Palette) -> Style {
    Style::default()
        .fg(palette.foreground)
        .bg(palette.background)
}
