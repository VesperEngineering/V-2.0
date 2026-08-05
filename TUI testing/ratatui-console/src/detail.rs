use ratatui::buffer::Buffer;
use ratatui::layout::Rect;
use ratatui::style::Style;
use ratatui::text::Line;
use ratatui::widgets::{Block, Borders, Clear, Paragraph, Widget, Wrap};

use crate::theme::Palette;
use crate::widgets::sanitize_line;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DetailOverlay {
    title: String,
    lines: Vec<String>,
    palette: Palette,
    scroll_offset: u16,
}

impl DetailOverlay {
    pub fn new(title: impl Into<String>, lines: Vec<String>, palette: Palette) -> Self {
        Self {
            title: title.into(),
            lines,
            palette,
            scroll_offset: 0,
        }
    }

    pub fn scroll(mut self, offset: usize) -> Self {
        self.scroll_offset = u16::try_from(offset).unwrap_or(u16::MAX);
        self
    }
}

impl Widget for DetailOverlay {
    fn render(self, area: Rect, buffer: &mut Buffer) {
        Clear.render(area, buffer);
        let style = base_style(self.palette);
        let lines = self
            .lines
            .into_iter()
            .map(|line| Line::from(sanitize_line(&line)))
            .collect::<Vec<_>>();
        Paragraph::new(lines)
            .style(style)
            .wrap(Wrap { trim: false })
            .scroll((self.scroll_offset, 0))
            .block(
                Block::default()
                    .borders(Borders::ALL)
                    .title(sanitize_line(&self.title))
                    .style(style),
            )
            .render(area, buffer);
    }
}

pub fn detail_area(area: Rect) -> Rect {
    let horizontal = u16::from(area.width > 8) * 2;
    let vertical = u16::from(area.height > 4);
    Rect::new(
        area.x.saturating_add(horizontal),
        area.y.saturating_add(vertical),
        area.width.saturating_sub(horizontal.saturating_mul(2)),
        area.height.saturating_sub(vertical.saturating_mul(2)),
    )
}

fn base_style(palette: Palette) -> Style {
    Style::default()
        .fg(palette.foreground)
        .bg(palette.background)
}
