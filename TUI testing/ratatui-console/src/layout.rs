use ratatui::layout::{Constraint, Layout, Rect};
use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Default, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum DisplayMode {
    Compact,
    #[default]
    Standard,
    LargeText,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ViewportClass {
    Wide,
    Narrow,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ShellLayout {
    pub viewport: ViewportClass,
    pub header: Rect,
    pub navigation: Rect,
    pub alerts: Rect,
    pub body: Rect,
    pub input: Rect,
    pub footer: Rect,
}

pub fn shell_layout(area: Rect, mode: DisplayMode) -> ShellLayout {
    let narrow = area.width < 120;
    let (header, navigation, alerts, input, footer) = match (narrow, mode) {
        (true, DisplayMode::Compact) => (7, 4, 3, 3, 3),
        (true, DisplayMode::Standard) => (7, 4, 4, 3, 3),
        (true, DisplayMode::LargeText) => (7, 4, 3, 4, 3),
        (false, DisplayMode::Compact) => (7, 4, 3, 3, 3),
        (false, DisplayMode::Standard) => (7, 4, 4, 3, 3),
        (false, DisplayMode::LargeText) => (7, 5, 4, 4, 3),
    };
    let regions = Layout::vertical([
        Constraint::Length(header),
        Constraint::Length(navigation),
        Constraint::Length(alerts),
        Constraint::Min(1),
        Constraint::Length(input),
        Constraint::Length(footer),
    ])
    .split(area);

    ShellLayout {
        viewport: if !narrow {
            ViewportClass::Wide
        } else {
            ViewportClass::Narrow
        },
        header: regions[0],
        navigation: regions[1],
        alerts: regions[2],
        body: regions[3],
        input: regions[4],
        footer: regions[5],
    }
}
