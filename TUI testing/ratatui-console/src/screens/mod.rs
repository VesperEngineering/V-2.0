pub mod impact;
pub mod orders;
pub mod portfolio;

use ratatui::Frame;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::style::Style;
use ratatui::text::Line;
use ratatui::widgets::{Block, Borders, Paragraph, Wrap};
use serde::{Deserialize, Serialize};

use crate::contract::{Freshness, NonEmptyString};
use crate::layout::DisplayMode;
use crate::theme::{Palette, Theme};
use crate::widgets::sanitize_line;

#[derive(Clone, Copy, Debug, Default, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum PerformancePeriod {
    #[default]
    Today,
    SinceRebalance,
    SinceStart,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ScreenState {
    pub theme: Theme,
    pub display_mode: DisplayMode,
    pub performance_period: PerformancePeriod,
    pub scroll_offset: usize,
    pub selected_id: Option<String>,
    pub detail_open: bool,
    pub show_all_events: bool,
    pub narrow_panel: usize,
}

impl Default for ScreenState {
    fn default() -> Self {
        Self {
            theme: Theme::WarmWhite,
            display_mode: DisplayMode::Standard,
            performance_period: PerformancePeriod::Today,
            scroll_offset: 0,
            selected_id: None,
            detail_open: false,
            show_all_events: false,
            narrow_panel: 0,
        }
    }
}

pub(crate) fn palette(state: &ScreenState) -> Palette {
    state.theme.palette()
}

pub(crate) fn base_style(palette: Palette) -> Style {
    Style::default()
        .fg(palette.foreground)
        .bg(palette.background)
}

pub(crate) fn table_row_height(state: &ScreenState) -> u16 {
    match state.display_mode {
        DisplayMode::LargeText => 2,
        DisplayMode::Compact | DisplayMode::Standard => 1,
    }
}

pub(crate) fn panel<'a>(title: impl Into<Line<'a>>, palette: Palette) -> Block<'a> {
    Block::default()
        .borders(Borders::ALL)
        .title(title)
        .style(base_style(palette))
}

pub(crate) fn unavailable_message(freshness: Freshness, error: Option<&str>) -> Option<String> {
    let state = match freshness {
        Freshness::Loading => "LOADING",
        Freshness::Fresh | Freshness::Stale => return None,
        Freshness::Unavailable => "UNAVAILABLE",
    };
    let reason = error
        .map(sanitize_line)
        .unwrap_or_else(|| "Source reason is unavailable.".to_owned());
    Some(format!("[?] {state} - {reason}"))
}

pub(crate) fn content_area_with_stale_notice(
    frame: &mut Frame<'_>,
    area: Rect,
    freshness: Freshness,
    error: Option<&str>,
    state: &ScreenState,
) -> Rect {
    if freshness != Freshness::Stale {
        return area;
    }
    let palette = palette(state);
    let reason = error
        .map(sanitize_line)
        .unwrap_or_else(|| "The controller retained the last valid sample.".to_owned());
    let sections = Layout::vertical([Constraint::Length(3), Constraint::Min(0)]).split(area);
    frame.render_widget(
        Paragraph::new(format!("[~] STALE - {reason}"))
            .style(base_style(palette))
            .wrap(Wrap { trim: true })
            .block(panel("SOURCE STATUS", palette)),
        sections[0],
    );
    sections[1]
}

pub(crate) fn clean(value: &NonEmptyString) -> String {
    sanitize_line(value.as_str())
}
