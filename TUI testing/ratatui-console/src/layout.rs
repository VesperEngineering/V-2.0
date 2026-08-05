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

pub const IMPACT_DEFAULT_COLUMNS: [&str; 8] = [
    "symbol", "current", "proposed", "approved", "agent", "task", "stage", "priority",
];
pub const IMPACT_COMPACT_COLUMNS: [&str; 4] = ["symbol", "current", "agent", "task"];
pub const PORTFOLIO_DEFAULT_COLUMNS: [&str; 4] = ["symbol", "current", "proposed", "approved"];
pub const PORTFOLIO_COMPACT_COLUMNS: [&str; 2] = ["symbol", "current"];
pub const IMPACT_DEFAULT_PANELS: [u16; 2] = [65, 35];
pub const PORTFOLIO_DEFAULT_PANELS: [u16; 3] = [58, 22, 20];
pub const NARROW_VIEWPORT_WIDTH: u16 = 120;
const MIN_PANEL_PERCENT: u16 = 15;
const PANEL_STEP: u16 = 5;

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
    shell_layout_with_input(area, mode, false)
}

pub fn chat_shell_layout(area: Rect, mode: DisplayMode) -> ShellLayout {
    shell_layout_with_input(area, mode, true)
}

pub fn impact_visible_columns(candidate: &[String]) -> Vec<&'static str> {
    normalized_columns(candidate, &IMPACT_DEFAULT_COLUMNS, &["symbol", "agent"])
}

pub fn portfolio_visible_columns(candidate: &[String]) -> Vec<&'static str> {
    normalized_columns(candidate, &PORTFOLIO_DEFAULT_COLUMNS, &["symbol"])
}

pub fn impact_panel_sizes(candidate: &[u16]) -> Vec<u16> {
    normalized_panel_sizes(candidate, &IMPACT_DEFAULT_PANELS)
}

pub fn portfolio_panel_sizes(candidate: &[u16]) -> Vec<u16> {
    normalized_panel_sizes(candidate, &PORTFOLIO_DEFAULT_PANELS)
}

pub const fn is_narrow_width(width: u16) -> bool {
    width < NARROW_VIEWPORT_WIDTH
}

pub fn impact_panels(area: Rect, candidate: &[u16]) -> [Rect; 3] {
    if is_narrow_width(area.width) {
        return [area; 3];
    }
    let sizes = impact_panel_sizes(candidate);
    let columns = Layout::horizontal([
        Constraint::Percentage(sizes[0]),
        Constraint::Percentage(sizes[1]),
    ])
    .split(area);
    let secondary = Layout::vertical([Constraint::Percentage(60), Constraint::Percentage(40)])
        .split(columns[1]);
    [columns[0], secondary[0], secondary[1]]
}

pub fn portfolio_panels(area: Rect, candidate: &[u16]) -> [Rect; 3] {
    if is_narrow_width(area.width) {
        return [area; 3];
    }
    let sizes = portfolio_panel_sizes(candidate);
    let sections = Layout::vertical(sizes.into_iter().map(Constraint::Percentage)).split(area);
    [sections[0], sections[1], sections[2]]
}

pub fn resize_primary_panel(candidate: &[u16], defaults: &[u16], grow: bool) -> Vec<u16> {
    let mut sizes = normalized_panel_sizes(candidate, defaults);
    if sizes.len() < 2 {
        return sizes;
    }
    if grow {
        let donor = (1..sizes.len())
            .rev()
            .find(|index| {
                sizes[*index] >= MIN_PANEL_PERCENT + PANEL_STEP && sizes[*index] > defaults[*index]
            })
            .or_else(|| {
                (1..sizes.len())
                    .rev()
                    .find(|index| sizes[*index] >= MIN_PANEL_PERCENT + PANEL_STEP)
            });
        if let Some(donor) = donor {
            sizes[0] += PANEL_STEP;
            sizes[donor] -= PANEL_STEP;
        }
    } else if sizes[0] >= MIN_PANEL_PERCENT + PANEL_STEP {
        let recipient = (1..sizes.len())
            .find(|index| sizes[*index] + PANEL_STEP <= defaults[*index])
            .unwrap_or(sizes.len() - 1);
        sizes[0] -= PANEL_STEP;
        sizes[recipient] += PANEL_STEP;
    }
    sizes
}

fn normalized_columns(
    candidate: &[String],
    defaults: &'static [&'static str],
    required: &[&str],
) -> Vec<&'static str> {
    if candidate.is_empty() {
        return defaults.to_vec();
    }
    let valid = candidate.iter().enumerate().all(|(index, column)| {
        defaults.contains(&column.as_str()) && !candidate[..index].iter().any(|seen| seen == column)
    }) && required
        .iter()
        .all(|required| candidate.iter().any(|column| column == required));
    if !valid {
        return defaults.to_vec();
    }
    defaults
        .iter()
        .copied()
        .filter(|column| candidate.iter().any(|candidate| candidate == column))
        .collect()
}

fn normalized_panel_sizes(candidate: &[u16], defaults: &[u16]) -> Vec<u16> {
    let valid = candidate.len() == defaults.len()
        && candidate.iter().all(|size| *size >= MIN_PANEL_PERCENT)
        && candidate.iter().copied().map(u32::from).sum::<u32>() == 100;
    if valid {
        candidate.to_vec()
    } else {
        defaults.to_vec()
    }
}

fn shell_layout_with_input(area: Rect, mode: DisplayMode, show_input: bool) -> ShellLayout {
    let narrow = is_narrow_width(area.width);
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
        Constraint::Length(if show_input { input } else { 0 }),
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
