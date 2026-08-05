use ratatui::style::{Color, Modifier, Style};
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Default, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum Theme {
    #[default]
    WarmWhite,
    Charcoal,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Palette {
    pub background: Color,
    pub foreground: Color,
    pub urgent: Style,
    pub waiting: Style,
    pub active: Style,
    pub resolved: Style,
}

impl Theme {
    pub fn palette(self) -> Palette {
        let (background, foreground, urgent, waiting, active, resolved) = match self {
            Self::WarmWhite => (
                Color::Rgb(250, 247, 240),
                Color::Rgb(38, 38, 38),
                Color::Rgb(155, 28, 28),
                Color::Rgb(122, 101, 0),
                Color::Rgb(0, 76, 153),
                Color::Rgb(22, 101, 52),
            ),
            Self::Charcoal => (
                Color::Rgb(38, 38, 38),
                Color::Rgb(250, 247, 240),
                Color::Rgb(255, 123, 123),
                Color::Rgb(253, 224, 71),
                Color::Rgb(108, 182, 255),
                Color::Rgb(110, 219, 143),
            ),
        };
        let status = |color| {
            Style::default()
                .fg(background)
                .bg(color)
                .add_modifier(Modifier::BOLD)
        };
        Palette {
            background,
            foreground,
            urgent: status(urgent),
            waiting: status(waiting),
            active: status(active),
            resolved: status(resolved),
        }
    }
}
