use std::cmp::Ordering;
use std::collections::BTreeMap;
use std::fmt;
use std::future::Future;
use std::io;
use std::path::{Path, PathBuf};
use std::time::Duration;

use crossterm::event::{
    self, DisableMouseCapture, EnableMouseCapture, Event, KeyCode, KeyEvent, KeyEventKind,
    KeyModifiers, MouseButton, MouseEvent, MouseEventKind,
};
use crossterm::execute;
use ratatui::DefaultTerminal;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::widgets::{Block, Borders, Paragraph};

use crate::contract::{
    AuthSetupPayload, AuthUnlockPayload, ClientHelloPayload, Envelope, LeaseRequestPayload,
    LockAction, LockRequestPayload, Message, NonEmptyString, SnapshotRequestPayload,
    TakeControlAction, UtcTimestamp,
};
use crate::input::InputEvent;
use crate::launcher::{GatewayLauncher, LaunchError};
use crate::layout::shell_layout;
use crate::preferences::{
    LoadedPreferences, load_preferences, preferences_path, save_preferences_to,
};
use crate::state::{AccessState, AppState, ClientAction, ProtocolError, ReduceOutcome};
use crate::transport::{PipeTransport, TransportError};

pub const POLL_INTERVAL: Duration = Duration::from_millis(10);
pub const SEND_TIMEOUT: Duration = Duration::from_millis(50);
pub const MAX_EVENTS_PER_TICK: usize = 32;
const INITIAL_RETRY_DELAY: Duration = Duration::from_millis(50);
const MAX_RETRY_DELAY: Duration = Duration::from_secs(1);
const REQUIRED_GATEWAY_RUNTIME_FILES: &[&str] = &[
    "vesper/__init__.py",
    "vesper/platform/__init__.py",
    "vesper/platform/agent_profiles.py",
    "vesper/platform/contracts.py",
    "vesper/platform/tui/__init__.py",
    "vesper/platform/tui/auth.py",
    "vesper/platform/tui/cli.py",
    "vesper/platform/tui/contracts.py",
    "vesper/platform/tui/event_store.py",
    "vesper/platform/tui/gateway.py",
    "vesper/platform/tui/notes.py",
    "vesper/platform/tui/outbox.py",
    "vesper/platform/tui/pipe_security.py",
    "vesper/platform/tui/pipe_server.py",
    "vesper/platform/tui/ports.py",
    "vesper/platform/tui/process_capture.py",
    "vesper/platform/tui/protocol.py",
    "vesper/platform/tui/search.py",
    "vesper/platform/tui/snapshot.py",
    "vesper/platform/tui/sqlite_ledger.py",
    "vesper/platform/tui/stream.py",
    "vesper/platform/tui/views.py",
    "vesper/platform/tui/projections/__init__.py",
    "vesper/platform/tui/projections/legacy_state.py",
    "vesper/platform/tui/projections/native_platform.py",
    "vesper/platform/tui/projections/repository.py",
    "vesper/platform/tui/projections/timeline.py",
    "vesper/platform/tui/projections/windows_system.py",
];

pub fn key_to_input(key: KeyEvent) -> Option<InputEvent> {
    if key.kind != KeyEventKind::Press {
        return None;
    }
    if key.code == KeyCode::Char('c') && key.modifiers == KeyModifiers::CONTROL {
        return Some(InputEvent::CloseTui);
    }
    let forbidden = KeyModifiers::CONTROL
        | KeyModifiers::ALT
        | KeyModifiers::SUPER
        | KeyModifiers::HYPER
        | KeyModifiers::META;
    if key.modifiers.intersects(forbidden) {
        return None;
    }
    match key.code {
        KeyCode::Char(character) => Some(InputEvent::Char(character)),
        KeyCode::Enter => Some(InputEvent::Enter),
        KeyCode::Esc => Some(InputEvent::Escape),
        KeyCode::Backspace => Some(InputEvent::Backspace),
        KeyCode::Up => Some(InputEvent::Up),
        KeyCode::Down => Some(InputEvent::Down),
        KeyCode::Left => Some(InputEvent::Left),
        KeyCode::Right => Some(InputEvent::Right),
        _ => None,
    }
}

pub fn mouse_to_input(mouse: MouseEvent, area: Rect, state: &AppState) -> Option<InputEvent> {
    match mouse.kind {
        MouseEventKind::ScrollUp => return Some(InputEvent::Up),
        MouseEventKind::ScrollDown => return Some(InputEvent::Down),
        MouseEventKind::Down(MouseButton::Left) => {}
        _ => return None,
    }
    let layout = shell_layout(area, state.display_mode());
    if contains(layout.footer, mouse.column, mouse.row) {
        let left_half = mouse.column < layout.footer.x.saturating_add(layout.footer.width / 2);
        match state.mode {
            crate::state::LocalMode::Filter | crate::state::LocalMode::NoteEditor => {
                return Some(if left_half {
                    InputEvent::Enter
                } else {
                    InputEvent::Escape
                });
            }
            crate::state::LocalMode::Open => return Some(InputEvent::Escape),
            crate::state::LocalMode::Search if !left_half => return Some(InputEvent::Escape),
            crate::state::LocalMode::Browse
                if state.snapshot.is_some()
                    && mouse.column
                        >= layout
                            .footer
                            .x
                            .saturating_add(layout.footer.width.saturating_sub(10)) =>
            {
                return Some(InputEvent::Char('f'));
            }
            _ => {}
        }
    }
    if state.mode == crate::state::LocalMode::NoteEditor
        && mouse.row == layout.body.y.saturating_add(2)
        && contains(layout.body, mouse.column, mouse.row)
    {
        return Some(
            if mouse.column < layout.body.x.saturating_add(layout.body.width / 2) {
                InputEvent::Left
            } else {
                InputEvent::Right
            },
        );
    }
    if state.mode == crate::state::LocalMode::Search
        && contains(layout.body, mouse.column, mouse.row)
    {
        let first_result_row = layout.body.y.saturating_add(3);
        if mouse.row < first_result_row {
            return None;
        }
        let available_rows = usize::from(layout.body.height.saturating_sub(6)).max(1);
        let search = state.search_state();
        let start = search
            .selected_index()
            .saturating_sub(available_rows.saturating_sub(1))
            .min(search.results().len().saturating_sub(available_rows));
        let index = start + usize::from(mouse.row - first_result_row);
        return (index < search.results().len()).then_some(InputEvent::OpenSearchResult(index));
    }
    if state.mode == crate::state::LocalMode::Browse
        && contains(layout.body, mouse.column, mouse.row)
    {
        return browse_click_to_input(mouse.column, mouse.row, layout.body, state);
    }
    if mouse.row == layout.navigation.y.saturating_add(1)
        && contains(layout.navigation, mouse.column, mouse.row)
    {
        let narrow = layout.navigation.width < 120;
        let entries = [
            ('1', crate::state::Screen::Impact, "Impact", "Imp"),
            ('2', crate::state::Screen::Portfolio, "Portfolio", "Port"),
            ('3', crate::state::Screen::Orders, "Orders", "Ord"),
            ('4', crate::state::Screen::Agents, "Agents", "Agt"),
            (
                '5',
                crate::state::Screen::ModelsRegime,
                "Models & Regime",
                "Mod",
            ),
            ('6', crate::state::Screen::Timeline, "Timeline", "Time"),
            (
                '7',
                crate::state::Screen::RiskApprovals,
                "Risk & Approvals",
                "Risk",
            ),
            (
                '8',
                crate::state::Screen::DataEvidence,
                "Data & Evidence",
                "Data",
            ),
            ('9', crate::state::Screen::Memory, "Memory", "Mem"),
            ('0', crate::state::Screen::System, "System", "Sys"),
        ];
        let mut start = layout.navigation.x.saturating_add(1);
        for (index, (key, screen, wide, compact)) in entries.into_iter().enumerate() {
            if index > 0 {
                start = start.saturating_add(3);
            }
            let name = if narrow { compact } else { wide };
            let width = u16::try_from(2 + name.len() + usize::from(state.screen == screen) * 2)
                .unwrap_or(u16::MAX);
            if mouse.column >= start && mouse.column < start.saturating_add(width) {
                return Some(InputEvent::Char(key));
            }
            start = start.saturating_add(width);
        }
    }
    None
}

fn browse_click_to_input(
    column: u16,
    row: u16,
    area: Rect,
    state: &AppState,
) -> Option<InputEvent> {
    let snapshot = state.snapshot.as_ref()?;
    match state.screen {
        crate::state::Screen::Impact => impact_click_to_input(column, row, area, state),
        crate::state::Screen::Portfolio => portfolio_click_to_input(column, row, area, state),
        crate::state::Screen::Orders => orders_click_to_input(column, row, area, state),
        crate::state::Screen::Agents => agents_click_to_input(column, row, area, state),
        crate::state::Screen::ModelsRegime => models_click_to_input(column, row, area, state),
        crate::state::Screen::Timeline => timeline_click_to_input(column, row, area, state),
        crate::state::Screen::RiskApprovals
        | crate::state::Screen::DataEvidence
        | crate::state::Screen::Memory
        | crate::state::Screen::System => {
            let freshness = match state.screen {
                crate::state::Screen::RiskApprovals => snapshot.risk.freshness,
                crate::state::Screen::DataEvidence => snapshot.data.freshness,
                crate::state::Screen::Memory => snapshot.memory.freshness,
                crate::state::Screen::System => snapshot.system.freshness,
                _ => unreachable!("screen is narrowed above"),
            };
            if !browse_rows_available(freshness) {
                return None;
            }
            panel_click_to_input(column, row, content_area(area, freshness), state)
        }
    }
}

fn impact_click_to_input(
    column: u16,
    row: u16,
    area: Rect,
    state: &AppState,
) -> Option<InputEvent> {
    let snapshot = state.snapshot.as_ref()?;
    if !browse_rows_available(snapshot.impact.freshness) {
        return None;
    }
    let area = content_area(area, snapshot.impact.freshness);
    let screen_state = state.screen_state();
    let holdings = if area.width < 100 {
        if !screen_state.narrow_panel.is_multiple_of(3) {
            return None;
        }
        area
    } else {
        Layout::horizontal([Constraint::Percentage(65), Constraint::Percentage(35)]).split(area)[0]
    };
    if !contains(holdings, column, row) {
        return None;
    }
    let omit_header = holdings.height <= 3;
    let row_height = if omit_header {
        1
    } else {
        crate::screens::table_row_height(&screen_state)
    };
    let first_row =
        holdings
            .y
            .saturating_add(1)
            .saturating_add(if omit_header { 0 } else { row_height });
    if row < first_row || column <= holdings.x || column >= holdings.right().saturating_sub(1) {
        return None;
    }
    let visible_index = usize::from((row - first_row) / row_height.max(1));
    let index = screen_state.scroll_offset.saturating_add(visible_index);
    (index < snapshot.impact.holdings.len())
        .then_some(InputEvent::OpenBrowseRow { panel: 0, index })
}

fn agents_click_to_input(
    column: u16,
    row: u16,
    area: Rect,
    state: &AppState,
) -> Option<InputEvent> {
    let snapshot = state.snapshot.as_ref()?;
    if !browse_rows_available(snapshot.agents.freshness) {
        return None;
    }
    let area = content_area(area, snapshot.agents.freshness);
    let screen_state = state.screen_state();
    let (panel, panel_area) = if area.width < 120 {
        (screen_state.narrow_panel % 5, area)
    } else {
        let backlog_height = match screen_state.display_mode {
            crate::layout::DisplayMode::Compact => 6,
            crate::layout::DisplayMode::Standard => 8,
            crate::layout::DisplayMode::LargeText => 10,
        };
        let sections =
            Layout::vertical([Constraint::Min(0), Constraint::Length(backlog_height)]).split(area);
        let columns = Layout::horizontal([
            Constraint::Percentage(25),
            Constraint::Percentage(25),
            Constraint::Percentage(25),
            Constraint::Percentage(25),
        ])
        .split(sections[0]);
        if let Some((index, panel)) = columns
            .iter()
            .copied()
            .enumerate()
            .find(|(_, panel)| contains(*panel, column, row))
        {
            (index, panel)
        } else if contains(sections[1], column, row) {
            (4, sections[1])
        } else {
            return None;
        }
    };
    if !inside_panel(panel_area, column, row) {
        return None;
    }
    let targets = state.browse_targets_for_panel(panel)?;
    let start = selected_target_start(state, panel, 5, &targets);
    let card_height = match screen_state.display_mode {
        crate::layout::DisplayMode::Compact => 2,
        crate::layout::DisplayMode::Standard => 4,
        crate::layout::DisplayMode::LargeText => 7,
    };
    let visible_line = usize::from(row - panel_area.y - 1);
    let index = start.saturating_add(visible_line / card_height);
    (index < targets.len()).then_some(InputEvent::OpenBrowseRow { panel, index })
}

fn timeline_click_to_input(
    column: u16,
    row: u16,
    area: Rect,
    state: &AppState,
) -> Option<InputEvent> {
    let snapshot = state.snapshot.as_ref()?;
    if !browse_rows_available(snapshot.timeline.freshness) {
        return None;
    }
    let area = content_area(area, snapshot.timeline.freshness);
    if !inside_panel(area, column, row) {
        return None;
    }
    let screen_state = state.screen_state();
    let spacing = match screen_state.display_mode {
        crate::layout::DisplayMode::Compact => 0,
        crate::layout::DisplayMode::Standard => 1,
        crate::layout::DisplayMode::LargeText => 2,
    };
    let relative = usize::from(row - area.y - 1).checked_sub(2)?;
    let stride = 2 + spacing;
    if relative % stride >= 2 {
        return None;
    }
    let targets = state.browse_targets_for_panel(0)?;
    let index = screen_state.scroll_offset.saturating_add(relative / stride);
    (index < targets.len()).then_some(InputEvent::OpenBrowseRow { panel: 0, index })
}

fn models_click_to_input(
    column: u16,
    row: u16,
    area: Rect,
    state: &AppState,
) -> Option<InputEvent> {
    let snapshot = state.snapshot.as_ref()?;
    if !browse_rows_available(snapshot.models.freshness) {
        return None;
    }
    let area = content_area(area, snapshot.models.freshness);
    let screen_state = state.screen_state();
    let (panel, panel_area) = if area.width < 120 {
        (screen_state.narrow_panel % 3, area)
    } else {
        let panels = Layout::horizontal([
            Constraint::Percentage(32),
            Constraint::Percentage(43),
            Constraint::Percentage(25),
        ])
        .split(area);
        panels
            .iter()
            .copied()
            .enumerate()
            .find(|(_, panel)| contains(*panel, column, row))?
    };
    if !inside_panel(panel_area, column, row) {
        return None;
    }
    let targets = state.browse_targets_for_panel(panel)?;
    let spacing = match screen_state.display_mode {
        crate::layout::DisplayMode::Compact => 0,
        crate::layout::DisplayMode::Standard => 1,
        crate::layout::DisplayMode::LargeText => 2,
    };
    let selected_index = screen_state
        .selected_id
        .as_deref()
        .zip(screen_state.selected_kind)
        .and_then(|(selected_id, selected_kind)| {
            targets
                .iter()
                .position(|(id, kind)| id == selected_id && *kind == selected_kind)
        });
    let line_offset = if screen_state.narrow_panel % 3 == panel {
        selected_index.map_or(0, |index| {
            models_target_line(&snapshot.models, panel, index, spacing)
        })
    } else {
        0
    };
    let visible_line = usize::from(row - panel_area.y - 1);
    let target_index = models_line_target(
        &snapshot.models,
        panel,
        line_offset.saturating_add(visible_line),
        spacing,
    )?;
    (target_index < targets.len()).then_some(InputEvent::OpenBrowseRow {
        panel,
        index: target_index,
    })
}

fn models_target_line(
    view: &crate::contract::ModelsView,
    panel: usize,
    index: usize,
    spacing: usize,
) -> usize {
    match panel {
        0 => 3 + index * (2 + spacing),
        1 => index * (2 + spacing),
        _ if index < view.metrics.len() => 1 + index * (1 + spacing),
        _ => {
            let evidence_start = if view.metrics.is_empty() {
                3
            } else {
                2 + view.metrics.len() * (1 + spacing)
            };
            evidence_start + index.saturating_sub(view.metrics.len()) * (2 + spacing)
        }
    }
}

fn models_line_target(
    view: &crate::contract::ModelsView,
    panel: usize,
    line: usize,
    spacing: usize,
) -> Option<usize> {
    match panel {
        0 => line
            .checked_sub(3)
            .filter(|relative| relative % (2 + spacing) < 2)
            .map(|relative| relative / (2 + spacing)),
        1 => (line % (2 + spacing) < 2).then_some(line / (2 + spacing)),
        _ => {
            let metric_stride = 1 + spacing;
            let metrics_end = 1 + view.metrics.len() * metric_stride;
            if line >= 1 && line < metrics_end {
                let relative = line - 1;
                return relative
                    .is_multiple_of(metric_stride)
                    .then_some(relative / metric_stride);
            }
            let evidence_start = if view.metrics.is_empty() {
                3
            } else {
                2 + view.metrics.len() * metric_stride
            };
            let relative = line.checked_sub(evidence_start)?;
            (relative % (2 + spacing) < 2).then_some(view.metrics.len() + relative / (2 + spacing))
        }
    }
}

fn orders_click_to_input(
    column: u16,
    row: u16,
    area: Rect,
    state: &AppState,
) -> Option<InputEvent> {
    let snapshot = state.snapshot.as_ref()?;
    if !browse_rows_available(snapshot.orders.freshness) {
        return None;
    }
    let area = content_area(area, snapshot.orders.freshness);
    let sections =
        Layout::vertical([Constraint::Percentage(76), Constraint::Percentage(24)]).split(area);
    let targets = state.browse_targets_for_panel(0)?;
    let (panel, panel_area, lines) = if contains(sections[0], column, row) {
        (0, sections[0], order_lines(&snapshot.orders))
    } else if contains(sections[1], column, row) {
        (1, sections[1], order_owner_lines(&snapshot.orders))
    } else {
        return None;
    };
    if !inside_panel(panel_area, column, row) {
        return None;
    }
    let screen_state = state.screen_state();
    let selected_scroll = lines
        .iter()
        .position(|target| {
            target.as_ref().is_some_and(|(id, kind)| {
                screen_state.selected_id.as_deref() == Some(id.as_str())
                    && screen_state.selected_kind == Some(*kind)
            })
        })
        .unwrap_or(0);
    let line = selected_scroll.saturating_add(usize::from(row - panel_area.y - 1));
    let (id, kind) = lines.get(line)?.as_ref()?;
    let index = targets
        .iter()
        .position(|(candidate_id, candidate_kind)| candidate_id == id && candidate_kind == kind)?;
    Some(InputEvent::OpenBrowseRow { panel, index })
}

fn order_lines(
    view: &crate::contract::OrdersView,
) -> Vec<Option<(String, crate::screens::DetailKind)>> {
    let mut grouped = BTreeMap::<&str, Vec<_>>::new();
    for order in &view.rows {
        grouped
            .entry(order.symbol.as_str())
            .or_default()
            .push(order);
    }
    let mut lines = Vec::new();
    for (_, mut orders) in grouped {
        orders.sort_by(|left, right| {
            newest_order_first(
                left.submitted_at_utc.as_ref(),
                right.submitted_at_utc.as_ref(),
            )
            .then_with(|| right.order_id.as_str().cmp(left.order_id.as_str()))
        });
        lines.push(None);
        for order in orders {
            lines.push(Some((
                order.order_id.as_str().to_owned(),
                crate::screens::DetailKind::Order,
            )));
            lines.push(None);
            lines.push(None);
            lines.extend(order.fills.iter().map(|fill| {
                Some((
                    fill.fill_id.as_str().to_owned(),
                    crate::screens::DetailKind::Fill,
                ))
            }));
        }
    }
    lines
}

fn order_owner_lines(
    view: &crate::contract::OrdersView,
) -> Vec<Option<(String, crate::screens::DetailKind)>> {
    let mut lines = view
        .reconciliation_agents
        .iter()
        .map(|agent| {
            Some((
                agent.work_id.as_str().to_owned(),
                crate::screens::DetailKind::Agent,
            ))
        })
        .collect::<Vec<_>>();
    lines.push(None);
    lines.extend(view.history.iter().map(|event| {
        Some((
            event.event_id.as_str().to_owned(),
            crate::screens::DetailKind::Event,
        ))
    }));
    lines
}

fn newest_order_first(
    left: Option<&crate::contract::UtcTimestamp>,
    right: Option<&crate::contract::UtcTimestamp>,
) -> Ordering {
    match (left, right) {
        (Some(left), Some(right)) => right.as_str().cmp(left.as_str()),
        (Some(_), None) => Ordering::Less,
        (None, Some(_)) => Ordering::Greater,
        (None, None) => Ordering::Equal,
    }
}

fn portfolio_click_to_input(
    column: u16,
    row: u16,
    area: Rect,
    state: &AppState,
) -> Option<InputEvent> {
    let snapshot = state.snapshot.as_ref()?;
    if !browse_rows_available(snapshot.portfolio.freshness) {
        return None;
    }
    let area = content_area(area, snapshot.portfolio.freshness);
    let weights = Layout::vertical(if area.width < 100 {
        [
            Constraint::Percentage(52),
            Constraint::Percentage(26),
            Constraint::Percentage(22),
        ]
    } else {
        [
            Constraint::Percentage(58),
            Constraint::Percentage(22),
            Constraint::Percentage(20),
        ]
    })
    .split(area)[0];
    if !contains(weights, column, row) {
        return None;
    }
    let screen_state = state.screen_state();
    let row_height = crate::screens::table_row_height(&screen_state);
    let first_row = weights.y.saturating_add(1).saturating_add(row_height);
    if row < first_row || column <= weights.x || column >= weights.right().saturating_sub(1) {
        return None;
    }
    let visible_index = usize::from((row - first_row) / row_height.max(1));
    let index = screen_state.scroll_offset.saturating_add(visible_index);
    (index < snapshot.portfolio.rows.len()).then_some(InputEvent::OpenBrowseRow { panel: 0, index })
}

fn panel_click_to_input(column: u16, row: u16, area: Rect, state: &AppState) -> Option<InputEvent> {
    let (panel, panel_area, leading_lines, panel_count) = panel_at(
        column,
        row,
        area,
        state.screen,
        state.screen_state().narrow_panel,
    )?;
    if column <= panel_area.x
        || column >= panel_area.right().saturating_sub(1)
        || row <= panel_area.y
        || row >= panel_area.bottom().saturating_sub(1)
    {
        return None;
    }
    let targets = state.browse_targets_for_panel(panel)?;
    let screen_state = state.screen_state();
    let start = if screen_state.narrow_panel % panel_count == panel {
        screen_state
            .selected_id
            .as_deref()
            .zip(screen_state.selected_kind)
            .and_then(|(selected_id, selected_kind)| {
                targets
                    .iter()
                    .position(|(id, kind)| id == selected_id && *kind == selected_kind)
            })
            .unwrap_or(0)
    } else {
        0
    };
    let visible_line = usize::from(row.saturating_sub(panel_area.y.saturating_add(1)));
    let visible_index = visible_line.checked_sub(leading_lines)?;
    let index = start.saturating_add(visible_index);
    (index < targets.len()).then_some(InputEvent::OpenBrowseRow { panel, index })
}

fn panel_at(
    column: u16,
    row: u16,
    area: Rect,
    screen: crate::state::Screen,
    focused_panel: usize,
) -> Option<(usize, Rect, usize, usize)> {
    let panels = match screen {
        crate::state::Screen::RiskApprovals if area.width >= 120 => {
            let rows = Layout::vertical([Constraint::Percentage(50), Constraint::Percentage(50)])
                .split(area);
            let top = Layout::horizontal([Constraint::Percentage(56), Constraint::Percentage(44)])
                .split(rows[0]);
            let bottom =
                Layout::horizontal([Constraint::Percentage(56), Constraint::Percentage(44)])
                    .split(rows[1]);
            vec![(top[0], 0), (top[1], 0), (bottom[0], 0), (bottom[1], 1)]
        }
        crate::state::Screen::DataEvidence if area.width >= 120 => {
            let columns =
                Layout::horizontal([Constraint::Percentage(60), Constraint::Percentage(40)])
                    .split(area);
            vec![(columns[0], 0), (columns[1], 0)]
        }
        crate::state::Screen::Memory if area.width >= 120 => {
            let columns = Layout::horizontal([
                Constraint::Percentage(35),
                Constraint::Percentage(35),
                Constraint::Percentage(30),
            ])
            .split(area);
            vec![(columns[0], 0), (columns[1], 0), (columns[2], 1)]
        }
        crate::state::Screen::System if area.width >= 120 => {
            let rows = Layout::vertical([Constraint::Percentage(50), Constraint::Percentage(50)])
                .split(area);
            let top = Layout::horizontal([Constraint::Percentage(50), Constraint::Percentage(50)])
                .split(rows[0]);
            let bottom =
                Layout::horizontal([Constraint::Percentage(60), Constraint::Percentage(40)])
                    .split(rows[1]);
            vec![(top[0], 0), (top[1], 0), (bottom[0], 0), (bottom[1], 0)]
        }
        crate::state::Screen::RiskApprovals => {
            vec![(area, usize::from(focused_panel % 4 == 3))]
        }
        crate::state::Screen::DataEvidence => vec![(area, 0)],
        crate::state::Screen::Memory => {
            vec![(area, usize::from(focused_panel % 3 == 2))]
        }
        crate::state::Screen::System => vec![(area, 0)],
        _ => return None,
    };
    let panel_count = match screen {
        crate::state::Screen::RiskApprovals | crate::state::Screen::System => 4,
        crate::state::Screen::DataEvidence => 2,
        crate::state::Screen::Memory => 3,
        _ => return None,
    };
    panels
        .into_iter()
        .enumerate()
        .find(|(_, (panel, _))| contains(*panel, column, row))
        .map(|(visible_index, (panel_area, leading_lines))| {
            let panel = if area.width < 120 {
                focused_panel % panel_count
            } else {
                visible_index
            };
            (panel, panel_area, leading_lines, panel_count)
        })
}

fn browse_rows_available(freshness: crate::contract::Freshness) -> bool {
    matches!(
        freshness,
        crate::contract::Freshness::Fresh | crate::contract::Freshness::Stale
    )
}

fn selected_target_start(
    state: &AppState,
    panel: usize,
    panel_count: usize,
    targets: &[(String, crate::screens::DetailKind)],
) -> usize {
    let screen_state = state.screen_state();
    if screen_state.narrow_panel % panel_count != panel {
        return 0;
    }
    screen_state
        .selected_id
        .as_deref()
        .zip(screen_state.selected_kind)
        .and_then(|(selected_id, selected_kind)| {
            targets
                .iter()
                .position(|(id, kind)| id == selected_id && *kind == selected_kind)
        })
        .unwrap_or(0)
}

fn inside_panel(area: Rect, column: u16, row: u16) -> bool {
    contains(area, column, row)
        && column > area.x
        && column < area.right().saturating_sub(1)
        && row > area.y
        && row < area.bottom().saturating_sub(1)
}

fn content_area(mut area: Rect, freshness: crate::contract::Freshness) -> Rect {
    if freshness == crate::contract::Freshness::Stale {
        area.y = area.y.saturating_add(3);
        area.height = area.height.saturating_sub(3);
    }
    area
}

fn contains(area: Rect, column: u16, row: u16) -> bool {
    column >= area.x
        && column < area.x.saturating_add(area.width)
        && row >= area.y
        && row < area.y.saturating_add(area.height)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum MouseCaptureChange {
    Enable,
    Disable,
}

#[derive(Debug, Default)]
pub struct MouseCaptureTracker {
    enabled: bool,
}

impl MouseCaptureTracker {
    pub fn sync(&mut self, access: AccessState) -> Option<MouseCaptureChange> {
        let wanted = access.is_unlocked();
        if wanted == self.enabled {
            return None;
        }
        self.enabled = wanted;
        Some(if wanted {
            MouseCaptureChange::Enable
        } else {
            MouseCaptureChange::Disable
        })
    }

    pub fn on_exit(&mut self) -> Option<MouseCaptureChange> {
        if self.enabled {
            self.enabled = false;
            Some(MouseCaptureChange::Disable)
        } else {
            None
        }
    }

    fn undo(&mut self, change: MouseCaptureChange) {
        self.enabled = change == MouseCaptureChange::Disable;
    }
}

#[derive(Debug, Default, PartialEq, Eq)]
pub struct LoopEffect {
    pub exit: bool,
    pub foundation_actions: Vec<ClientAction>,
}

impl LoopEffect {
    pub fn merge(&mut self, mut other: Self) {
        self.exit |= other.exit;
        self.foundation_actions
            .append(&mut other.foundation_actions);
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PreferencePersistence {
    Idle,
    Saved,
    Unavailable,
}

#[doc(hidden)]
pub fn persist_pending_preferences_to(state: &mut AppState, path: &Path) -> PreferencePersistence {
    let Some(preferences) = state.pending_preferences().cloned() else {
        return PreferencePersistence::Idle;
    };
    let succeeded = save_preferences_to(path, &preferences).is_ok();
    state.finish_preferences_save(succeeded);
    if succeeded {
        PreferencePersistence::Saved
    } else {
        PreferencePersistence::Unavailable
    }
}

fn persist_pending_preferences(state: &mut AppState) -> PreferencePersistence {
    if state.pending_preferences().is_none() {
        return PreferencePersistence::Idle;
    }
    let Ok(path) = preferences_path() else {
        state.finish_preferences_save(false);
        return PreferencePersistence::Unavailable;
    };
    persist_pending_preferences_to(state, &path)
}

#[derive(Debug)]
pub struct App {
    state: AppState,
}

impl App {
    pub fn new(state: AppState) -> Self {
        Self { state }
    }

    pub fn state(&self) -> &AppState {
        &self.state
    }

    pub fn take_redraw(&mut self) -> bool {
        self.state.take_dirty()
    }

    pub fn force_redraw(&mut self) {
        self.state.mark_dirty();
    }

    pub fn on_idle(&mut self) -> LoopEffect {
        self.handle_input(InputEvent::Tick(POLL_INTERVAL))
    }

    pub fn handle_input(&mut self, input: InputEvent) -> LoopEffect {
        let mut effect = LoopEffect::default();
        for action in self.state.handle(input) {
            match action {
                ClientAction::CloseTui => effect.exit = true,
                ClientAction::SubmitInput(_) => {}
                action => effect.foundation_actions.push(action),
            }
        }
        effect
    }

    pub fn reduce(&mut self, envelope: Envelope) -> Result<ReduceOutcome, ProtocolError> {
        self.state.reduce(envelope)
    }
}

#[doc(hidden)]
pub fn process_input_batch<I>(client: &mut FoundationClient, inputs: &mut I) -> LoopEffect
where
    I: Iterator<Item = InputEvent>,
{
    let mut batch = LoopEffect::default();
    for input in inputs.by_ref().take(MAX_EVENTS_PER_TICK) {
        let mut effect = client.apply_input(input);
        batch
            .foundation_actions
            .append(&mut effect.foundation_actions);
        if effect.exit {
            batch.exit = true;
            batch.foundation_actions.clear();
            break;
        }
    }
    batch
}

#[derive(Debug)]
pub enum SessionError {
    Transport(TransportError),
    Disconnected,
    SendTimeout,
}

impl fmt::Display for SessionError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Transport(error) => write!(formatter, "foundation transport failed: {error}"),
            Self::Disconnected => formatter.write_str("foundation session disconnected"),
            Self::SendTimeout => formatter.write_str("foundation send timed out"),
        }
    }
}

impl std::error::Error for SessionError {}

impl From<TransportError> for SessionError {
    fn from(error: TransportError) -> Self {
        Self::Transport(error)
    }
}

pub trait FoundationSession {
    fn send<'a>(
        &'a mut self,
        envelope: &'a Envelope,
    ) -> impl Future<Output = Result<(), SessionError>> + Send + 'a;

    fn recv(&mut self) -> impl Future<Output = Result<Envelope, SessionError>> + Send + '_;
}

impl FoundationSession for PipeTransport {
    async fn send<'a>(&'a mut self, envelope: &'a Envelope) -> Result<(), SessionError> {
        PipeTransport::send(self, envelope)
            .await
            .map_err(Into::into)
    }

    async fn recv(&mut self) -> Result<Envelope, SessionError> {
        PipeTransport::recv(self).await.map_err(Into::into)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SessionStep {
    Continue,
    Exit,
    Reconnect,
}

#[derive(Debug)]
pub struct FoundationClient {
    app: App,
    next_sequence: u64,
    connection_failed: bool,
}

impl FoundationClient {
    pub fn new() -> Self {
        Self::from_app(App::new(AppState::locked()))
    }

    pub fn from_app(app: App) -> Self {
        Self {
            app,
            next_sequence: 0,
            connection_failed: false,
        }
    }

    pub fn app(&self) -> &App {
        &self.app
    }

    pub fn app_mut(&mut self) -> &mut App {
        &mut self.app
    }

    pub fn fail_connection(&mut self) {
        self.connection_failed = true;
        self.app.state.fail_connection();
    }

    pub async fn start<S: FoundationSession>(
        &mut self,
        session: &mut S,
    ) -> Result<(), SessionError> {
        self.send_message(
            session,
            Message::ClientHello(ClientHelloPayload {
                client_version: NonEmptyString::literal(env!("CARGO_PKG_VERSION")),
                supported_schema_versions: vec![1],
            }),
        )
        .await
    }

    pub async fn receive<S: FoundationSession>(
        &mut self,
        session: &mut S,
    ) -> Result<SessionStep, SessionError> {
        let envelope = match session.recv().await {
            Ok(envelope) => envelope,
            Err(error) => {
                self.fail_connection();
                return Err(error);
            }
        };
        self.accept(envelope, session).await
    }

    async fn accept<S: FoundationSession>(
        &mut self,
        envelope: Envelope,
        session: &mut S,
    ) -> Result<SessionStep, SessionError> {
        match self.app.reduce(envelope) {
            Ok(ReduceOutcome::RequestSnapshot) => {
                self.send_action(session, ClientAction::RequestSnapshot)
                    .await
            }
            Ok(ReduceOutcome::Changed | ReduceOutcome::Ignored) => Ok(SessionStep::Continue),
            Err(_) => {
                self.fail_connection();
                Ok(SessionStep::Reconnect)
            }
        }
    }

    pub async fn handle_input<S: FoundationSession>(
        &mut self,
        input: InputEvent,
        session: &mut S,
    ) -> Result<SessionStep, SessionError> {
        let effect = self.apply_input(input);
        self.dispatch(effect, session).await
    }

    pub fn apply_input(&mut self, input: InputEvent) -> LoopEffect {
        self.app.handle_input(input)
    }

    pub async fn dispatch<S: FoundationSession>(
        &mut self,
        effect: LoopEffect,
        session: &mut S,
    ) -> Result<SessionStep, SessionError> {
        if effect.exit {
            return Ok(SessionStep::Exit);
        }
        for action in effect.foundation_actions {
            let step = self.send_action(session, action).await?;
            if step != SessionStep::Continue {
                return Ok(step);
            }
        }
        Ok(SessionStep::Continue)
    }

    async fn send_action<S: FoundationSession>(
        &mut self,
        session: &mut S,
        action: ClientAction,
    ) -> Result<SessionStep, SessionError> {
        let message = match action {
            ClientAction::Authenticate(crate::state::AuthRequest::Setup {
                password,
                confirmation,
            }) => Message::AuthSetup(AuthSetupPayload {
                password,
                confirmation,
            }),
            ClientAction::Authenticate(crate::state::AuthRequest::Unlock { password }) => {
                Message::AuthUnlock(AuthUnlockPayload { password })
            }
            ClientAction::RequestLease => Message::LeaseRequest(LeaseRequestPayload {
                action: TakeControlAction::TakeControl,
            }),
            ClientAction::RequestLock => Message::LockRequest(LockRequestPayload {
                action: LockAction::Lock,
            }),
            ClientAction::RequestSnapshot => Message::SnapshotRequest(SnapshotRequestPayload {}),
            ClientAction::Search(payload) => Message::SearchRequest(payload),
            ClientAction::Reconnect => return Ok(SessionStep::Reconnect),
            ClientAction::CloseTui => return Ok(SessionStep::Exit),
            ClientAction::SubmitInput(_) => return Ok(SessionStep::Continue),
        };
        self.send_message(session, message).await?;
        Ok(SessionStep::Continue)
    }

    async fn send_message<S: FoundationSession>(
        &mut self,
        session: &mut S,
        message: Message,
    ) -> Result<(), SessionError> {
        if self.connection_failed {
            return Err(SessionError::Disconnected);
        }
        let Some(next_sequence) = self.next_sequence.checked_add(1) else {
            self.fail_connection();
            return Err(SessionError::Disconnected);
        };
        self.next_sequence = next_sequence;
        let envelope = Envelope {
            schema_version: 1,
            message_id: crate::contract::SafeId::client_message(self.next_sequence),
            sequence: self.next_sequence,
            state_version: self.app.state().state_version(),
            timestamp_utc: UtcTimestamp::now_utc(),
            message,
        };
        match tokio::time::timeout(SEND_TIMEOUT, session.send(&envelope)).await {
            Ok(Ok(())) => Ok(()),
            Ok(Err(error)) => {
                self.fail_connection();
                Err(error)
            }
            Err(_) => {
                self.fail_connection();
                Err(SessionError::SendTimeout)
            }
        }
    }
}

impl Default for FoundationClient {
    fn default() -> Self {
        Self::new()
    }
}

struct RestoreGuard<Restore: FnOnce()> {
    restore: Option<Restore>,
}

impl<Restore: FnOnce()> RestoreGuard<Restore> {
    fn new(restore: Restore) -> Self {
        Self {
            restore: Some(restore),
        }
    }
}

impl<Restore: FnOnce()> Drop for RestoreGuard<Restore> {
    fn drop(&mut self) {
        if let Some(restore) = self.restore.take() {
            restore();
        }
    }
}

pub fn with_restore<T, E, Run, Restore>(run: Run, restore: Restore) -> Result<T, E>
where
    Run: FnOnce() -> Result<T, E>,
    Restore: FnOnce(),
{
    let _guard = RestoreGuard::new(restore);
    run()
}

struct TerminalMouseCapture {
    tracker: MouseCaptureTracker,
}

impl TerminalMouseCapture {
    fn new() -> Self {
        Self {
            tracker: MouseCaptureTracker::default(),
        }
    }

    fn sync(&mut self, access: AccessState) -> io::Result<()> {
        let Some(change) = self.tracker.sync(access) else {
            return Ok(());
        };
        if let Err(error) = apply_mouse_change(change) {
            self.tracker.undo(change);
            return Err(error);
        }
        Ok(())
    }
}

impl Drop for TerminalMouseCapture {
    fn drop(&mut self) {
        if let Some(change) = self.tracker.on_exit() {
            let _ = apply_mouse_change(change);
        }
    }
}

fn apply_mouse_change(change: MouseCaptureChange) -> io::Result<()> {
    match change {
        MouseCaptureChange::Enable => execute!(io::stdout(), EnableMouseCapture),
        MouseCaptureChange::Disable => execute!(io::stdout(), DisableMouseCapture),
    }
}

pub trait GatewayConnector {
    type Session: FoundationSession;
    type Error;

    fn connect<'a>(
        &'a mut self,
        repo_root: &'a Path,
    ) -> impl Future<Output = Result<Self::Session, Self::Error>> + 'a;
}

pub trait ConnectionControl {
    fn draw_connecting(&mut self) -> io::Result<()>;

    fn wait_for_exit(&mut self) -> impl Future<Output = io::Result<()>> + '_;

    fn wait_retry(&mut self, delay: Duration) -> impl Future<Output = io::Result<bool>> + '_;
}

struct LauncherConnector;

impl GatewayConnector for LauncherConnector {
    type Session = PipeTransport;
    type Error = LaunchError;

    async fn connect(&mut self, repo_root: &Path) -> Result<Self::Session, Self::Error> {
        GatewayLauncher::connect_or_start(repo_root).await
    }
}

struct RetryBackoff {
    next: Duration,
}

impl RetryBackoff {
    fn new() -> Self {
        Self {
            next: INITIAL_RETRY_DELAY,
        }
    }

    fn take(&mut self) -> Duration {
        let delay = self.next;
        self.next = self.next.saturating_mul(2).min(MAX_RETRY_DELAY);
        delay
    }
}

#[doc(hidden)]
pub async fn connect_with_retry<C, Control>(
    connector: &mut C,
    repo_root: &Path,
    control: &mut Control,
) -> io::Result<Option<C::Session>>
where
    C: GatewayConnector,
    Control: ConnectionControl,
{
    control.draw_connecting()?;
    let mut backoff = RetryBackoff::new();
    loop {
        let result = tokio::select! {
            biased;
            exit = control.wait_for_exit() => {
                exit?;
                return Ok(None);
            }
            result = connector.connect(repo_root) => result,
        };
        match result {
            Ok(session) => return Ok(Some(session)),
            Err(_) => {
                if control.wait_retry(backoff.take()).await? {
                    return Ok(None);
                }
            }
        }
    }
}

struct TerminalConnectionControl<'a> {
    terminal: &'a mut DefaultTerminal,
}

impl<'a> TerminalConnectionControl<'a> {
    fn new(terminal: &'a mut DefaultTerminal) -> Self {
        Self { terminal }
    }
}

impl ConnectionControl for TerminalConnectionControl<'_> {
    fn draw_connecting(&mut self) -> io::Result<()> {
        draw_connecting(self.terminal)
    }

    async fn wait_for_exit(&mut self) -> io::Result<()> {
        let mut input_poll = tokio::time::interval(POLL_INTERVAL);
        input_poll.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
        loop {
            input_poll.tick().await;
            if drain_connecting_events(self.terminal)? {
                return Ok(());
            }
        }
    }

    async fn wait_retry(&mut self, delay: Duration) -> io::Result<bool> {
        tokio::select! {
            biased;
            result = self.wait_for_exit() => {
                result?;
                Ok(true)
            }
            () = tokio::time::sleep(delay) => Ok(false),
        }
    }
}

pub async fn run() -> io::Result<()> {
    let mut terminal = ratatui::init();
    let _restore = RestoreGuard::new(ratatui::restore);
    let repo_root = repository_root()?;
    run_terminal_loop(&mut terminal, &repo_root).await
}

fn repository_root() -> io::Result<PathBuf> {
    let executable = std::env::current_exe()
        .ok()
        .and_then(|path| path.parent().map(Path::to_path_buf))
        .unwrap_or_default();
    let runtime = std::env::current_dir().unwrap_or_default();
    resolve_repo_root_from(&executable, &runtime)
}

#[doc(hidden)]
pub fn resolve_repo_root_from(
    executable_start: &Path,
    runtime_start: &Path,
) -> io::Result<PathBuf> {
    find_repo_root(executable_start)
        .or_else(|| find_repo_root(runtime_start))
        .ok_or_else(|| io::Error::other("V20 repository root is unavailable"))
}

fn find_repo_root(start: &Path) -> Option<PathBuf> {
    start.ancestors().find_map(|candidate| {
        let canonical = candidate.canonicalize().ok()?;
        is_v20_repo_root(&canonical).then_some(canonical)
    })
}

fn is_v20_repo_root(candidate: &Path) -> bool {
    if !candidate.join("uv.lock").is_file() {
        return false;
    }
    let Ok(pyproject) = std::fs::read_to_string(candidate.join("pyproject.toml")) else {
        return false;
    };
    if pyproject.contains("\"\"\"") || pyproject.contains("'''") {
        return false;
    }
    if !has_exact_declaration(&pyproject, "[project]", "name = \"vesper\"")
        || !has_exact_declaration(
            &pyproject,
            "[project.scripts]",
            "vesper-tui-gateway = \"vesper.platform.tui.cli:main\"",
        )
    {
        return false;
    }
    REQUIRED_GATEWAY_RUNTIME_FILES
        .iter()
        .all(|file| candidate.join(file).is_file())
}

fn has_exact_declaration(document: &str, section: &str, declaration: &str) -> bool {
    let mut in_section = false;
    for line in document.lines().map(str::trim) {
        if line.starts_with('[') {
            in_section = line == section;
        } else if in_section && line == declaration {
            return true;
        }
    }
    false
}

pub async fn run_terminal_loop(terminal: &mut DefaultTerminal, repo_root: &Path) -> io::Result<()> {
    let mut connector = LauncherConnector;
    loop {
        let transport = {
            let mut control = TerminalConnectionControl::new(terminal);
            let Some(transport) =
                connect_with_retry(&mut connector, repo_root, &mut control).await?
            else {
                return Ok(());
            };
            transport
        };
        let loaded_preferences = load_preferences();
        match run_connected_loop(terminal, transport, loaded_preferences).await? {
            SessionStep::Exit => return Ok(()),
            SessionStep::Reconnect => {
                let mut control = TerminalConnectionControl::new(terminal);
                control.draw_connecting()?;
                if control.wait_retry(INITIAL_RETRY_DELAY).await? {
                    return Ok(());
                }
            }
            SessionStep::Continue => unreachable!("connected loop returns only exit or reconnect"),
        }
    }
}

async fn run_connected_loop<S: FoundationSession>(
    terminal: &mut DefaultTerminal,
    mut session: S,
    loaded_preferences: LoadedPreferences,
) -> io::Result<SessionStep> {
    let mut state = AppState::locked();
    state.apply_loaded_preferences(loaded_preferences);
    let mut client = FoundationClient::from_app(App::new(state));
    let mut mouse = TerminalMouseCapture::new();
    if client.start(&mut session).await.is_err() {
        prepare_reconnect(terminal, &mut client, &mut mouse)?;
        return Ok(SessionStep::Reconnect);
    }
    let mut input_poll = tokio::time::interval(POLL_INTERVAL);
    input_poll.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);

    loop {
        refresh_terminal(terminal, &mut client, &mut mouse)?;

        let step = tokio::select! {
            biased;
            _ = input_poll.tick() => {
                drain_terminal_events(terminal, &mut client, &mut mouse, &mut session).await?
            }
            inbound = session.recv() => {
                match inbound {
                    Ok(envelope) => client.accept(envelope, &mut session).await
                        .unwrap_or(SessionStep::Reconnect),
                    Err(_) => {
                        client.fail_connection();
                        SessionStep::Reconnect
                    }
                }
            }
        };
        if step != SessionStep::Continue {
            if step == SessionStep::Reconnect {
                prepare_reconnect(terminal, &mut client, &mut mouse)?;
            }
            return Ok(step);
        }
    }
}

async fn drain_terminal_events<S: FoundationSession>(
    terminal: &mut DefaultTerminal,
    client: &mut FoundationClient,
    mouse: &mut TerminalMouseCapture,
    session: &mut S,
) -> io::Result<SessionStep> {
    let mut inputs = Vec::with_capacity(MAX_EVENTS_PER_TICK);
    let mut resized = false;
    for _ in 0..MAX_EVENTS_PER_TICK {
        if !event::poll(Duration::ZERO)? {
            break;
        }
        match event::read()? {
            Event::Key(key) => {
                if let Some(input) = key_to_input(key) {
                    inputs.push(input);
                }
            }
            Event::Resize(_, _) => resized = true,
            Event::Mouse(mouse_event) if client.app.state().access.is_unlocked() => {
                if let Some(input) =
                    mouse_to_input(mouse_event, terminal.size()?.into(), client.app.state())
                {
                    inputs.push(input);
                }
            }
            _ => {}
        }
    }
    let mut effect = process_input_batch(client, &mut inputs.into_iter());
    if resized {
        client.app.force_redraw();
    }
    effect.merge(client.app.on_idle());
    refresh_terminal(terminal, client, mouse)?;
    Ok(client
        .dispatch(effect, session)
        .await
        .unwrap_or(SessionStep::Reconnect))
}

fn drain_connecting_events(terminal: &mut DefaultTerminal) -> io::Result<bool> {
    let mut close = false;
    let mut resized = false;
    for _ in 0..MAX_EVENTS_PER_TICK {
        if !event::poll(Duration::ZERO)? {
            break;
        }
        match event::read()? {
            Event::Key(key)
                if matches!(
                    key_to_input(key),
                    Some(InputEvent::CloseTui | InputEvent::Char('q'))
                ) =>
            {
                close = true;
                break;
            }
            Event::Resize(_, _) => resized = true,
            _ => {}
        }
    }
    if resized {
        draw_connecting(terminal)?;
    }
    Ok(close)
}

fn draw_connecting(terminal: &mut DefaultTerminal) -> io::Result<()> {
    terminal.draw(|frame| {
        frame.render_widget(
            Paragraph::new("V20 console locked. Connecting to Foundation. Ctrl+C closes.")
                .block(Block::default().borders(Borders::ALL).title("Vesper v20")),
            frame.area(),
        );
    })?;
    Ok(())
}

fn prepare_reconnect(
    terminal: &mut DefaultTerminal,
    client: &mut FoundationClient,
    mouse: &mut TerminalMouseCapture,
) -> io::Result<()> {
    if client.app.state().access != AccessState::ProtocolLockout {
        client.fail_connection();
    }
    refresh_terminal(terminal, client, mouse)
}

fn refresh_terminal(
    terminal: &mut DefaultTerminal,
    client: &mut FoundationClient,
    mouse: &mut TerminalMouseCapture,
) -> io::Result<()> {
    let _ = persist_pending_preferences(&mut client.app.state);
    mouse.sync(client.app.state().access)?;
    let area: Rect = terminal.size()?.into();
    client.app.state.set_terminal_area(area);
    if client.app.take_redraw() {
        terminal.draw(|frame| crate::ui::render(frame, client.app.state()))?;
    }
    Ok(())
}
