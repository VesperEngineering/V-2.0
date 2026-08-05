use std::cell::Cell;
use std::collections::VecDeque;
use std::fs;
use std::future::{Future, pending, ready};
use std::io;
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::path::{Path, PathBuf};
use std::time::Duration;

use crossterm::event::{
    KeyCode, KeyEvent, KeyEventKind, KeyModifiers, MouseButton, MouseEvent, MouseEventKind,
};
use ratatui::Terminal;
use ratatui::backend::TestBackend;
use ratatui::layout::{Constraint, Layout, Rect};
use serde_json::json;

use vesper_ratatui_console::app::{
    App, ConnectionControl, FoundationClient, FoundationSession, GatewayConnector,
    MAX_EVENTS_PER_TICK, MouseCaptureChange, MouseCaptureTracker, POLL_INTERVAL, SEND_TIMEOUT,
    SessionError, SessionStep, connect_with_retry, key_to_input, mouse_to_input,
    process_input_batch, required_gateway_runtime_files, resolve_repo_root_from, with_restore,
};
use vesper_ratatui_console::contract::{Envelope, Message, MessageType, UtcTimestamp};
use vesper_ratatui_console::input::InputEvent;
use vesper_ratatui_console::layout::{impact_panels, portfolio_panels, shell_layout};
use vesper_ratatui_console::preferences::{ScreenId, ScreenPreferences};
use vesper_ratatui_console::state::{
    AccessState, AppState, AuthRequest, AuthStage, ClientAction, LocalMode, ReduceOutcome, Screen,
};
use vesper_ratatui_console::ui::split_control_area;

fn receive_server_hello(state: &mut AppState, requires_setup: bool) {
    let envelope = server_hello_envelope(requires_setup);
    assert_eq!(state.reduce(envelope), Ok(ReduceOutcome::Changed));
}

fn server_hello_envelope(requires_setup: bool) -> Envelope {
    serde_json::from_value(json!({
        "schema_version": 1,
        "message_id": "server:1",
        "sequence": 1,
        "state_version": 0,
        "timestamp_utc": "2026-08-03T00:00:00Z",
        "message_type": "server-hello",
        "payload": {
            "server_version": "0.1.0",
            "requires_setup": requires_setup
        }
    }))
    .unwrap()
}

fn inbound_envelope(sequence: u64, message_type: &str, payload: serde_json::Value) -> Envelope {
    serde_json::from_value(json!({
        "schema_version": 1,
        "message_id": format!("server:{sequence}"),
        "sequence": sequence,
        "state_version": 0,
        "timestamp_utc": "2026-08-03T00:00:00Z",
        "message_type": message_type,
        "payload": payload
    }))
    .unwrap()
}

fn snapshot_envelope(sequence: u64) -> Envelope {
    let snapshot: serde_json::Value = serde_json::from_slice(include_bytes!(
        "../../contracts/v1/console_snapshot_empty_command_specs.json"
    ))
    .expect("valid shared console snapshot");
    inbound_envelope(sequence, "snapshot", json!({"snapshot": snapshot}))
}

#[derive(Default)]
struct FakeSession {
    incoming: VecDeque<Envelope>,
    sent: Vec<Envelope>,
    fail_send: bool,
    fail_recv: bool,
}

impl FoundationSession for FakeSession {
    fn send<'a>(
        &'a mut self,
        envelope: &'a Envelope,
    ) -> impl Future<Output = Result<(), SessionError>> + Send + 'a {
        if self.fail_send {
            return ready(Err(SessionError::Disconnected));
        }
        self.sent.push(envelope.clone());
        ready(Ok(()))
    }

    fn recv(&mut self) -> impl Future<Output = Result<Envelope, SessionError>> + Send + '_ {
        if self.fail_recv {
            return ready(Err(SessionError::Disconnected));
        }
        ready(self.incoming.pop_front().ok_or(SessionError::Disconnected))
    }
}

#[derive(Default)]
struct HangingSendSession {
    sends: usize,
}

impl FoundationSession for HangingSendSession {
    async fn send(&mut self, _envelope: &Envelope) -> Result<(), SessionError> {
        self.sends += 1;
        pending().await
    }

    async fn recv(&mut self) -> Result<Envelope, SessionError> {
        Err(SessionError::Disconnected)
    }
}

#[derive(Default)]
struct RetryConnector {
    attempts: usize,
    failures_remaining: usize,
}

impl GatewayConnector for RetryConnector {
    type Session = FakeSession;
    type Error = ();

    fn connect<'a>(
        &'a mut self,
        _repo_root: &'a Path,
    ) -> impl Future<Output = Result<Self::Session, ()>> + 'a {
        self.attempts += 1;
        let result = if self.failures_remaining == 0 {
            Ok(FakeSession::default())
        } else {
            self.failures_remaining -= 1;
            Err(())
        };
        ready(result)
    }
}

#[derive(Default)]
struct RetryControl {
    draws: usize,
    delays: Vec<Duration>,
}

impl ConnectionControl for RetryControl {
    fn draw_connecting(&mut self) -> io::Result<()> {
        self.draws += 1;
        Ok(())
    }

    fn wait_for_exit(&mut self) -> impl Future<Output = io::Result<()>> + '_ {
        pending()
    }

    fn wait_retry(&mut self, delay: Duration) -> impl Future<Output = io::Result<bool>> + '_ {
        self.delays.push(delay);
        ready(Ok(false))
    }
}

struct TempCheckout {
    root: PathBuf,
}

impl TempCheckout {
    fn new(label: &str, valid: bool) -> Self {
        let root = std::env::temp_dir().join(format!(
            "v20-ratatui-{label}-{}-{:?}",
            std::process::id(),
            std::thread::current().id()
        ));
        if root.exists() {
            fs::remove_dir_all(&root).unwrap();
        }
        fs::create_dir_all(root.join("nested/deeper")).unwrap();
        if valid {
            Self::write_identity(&root, false);
        }
        Self { root }
    }

    fn lookalike(label: &str) -> Self {
        let checkout = Self::new(label, false);
        Self::write_identity(&checkout.root, true);
        checkout
    }

    fn multiline_lookalike(label: &str) -> Self {
        let checkout = Self::new(label, true);
        fs::write(
            checkout.root.join("pyproject.toml"),
            "[project]\nname = \"attacker\"\ndescription = \"\"\"\n[project]\nname = \"vesper\"\n[project.scripts]\nvesper-tui-gateway = \"vesper.platform.tui.cli:main\"\n\"\"\"\n[project.scripts]\nvesper-tui-gateway = \"attacker:main\"\n",
        )
        .unwrap();
        checkout
    }

    fn write_identity(root: &Path, comments_only: bool) {
        let prefix = if comments_only { "# " } else { "" };
        fs::write(
            root.join("pyproject.toml"),
            format!(
                "{prefix}[project]\n{prefix}name = \"vesper\"\n{prefix}[project.scripts]\n{prefix}vesper-tui-gateway = \"vesper.platform.tui.cli:main\"\n"
            ),
        )
        .unwrap();
        fs::write(root.join("uv.lock"), "version = 1\n").unwrap();
        for file in required_gateway_runtime_files() {
            let path = root.join(file);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, "# test module\n").unwrap();
        }
    }
}

impl Drop for TempCheckout {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}

#[test]
fn locked_input_cannot_reveal_or_navigate_the_console() {
    let mut state = AppState::locked();

    let actions = state.handle(InputEvent::Char('2'));

    assert!(actions.is_empty());
    assert_eq!(state.screen, Screen::Impact);
    assert!(state.snapshot.is_none());
    assert_eq!(state.masked_auth_input(), "");
}

#[test]
fn password_entry_is_masked_for_setup_and_unlock() {
    let mut first_run = AppState::locked();
    receive_server_hello(&mut first_run, true);
    first_run.handle(InputEvent::Char('s'));
    first_run.handle(InputEvent::Char('3'));

    assert_eq!(first_run.masked_auth_input(), "**");
    assert!(!format!("{first_run:?}").contains("s3"));

    first_run.handle(InputEvent::Enter);
    assert_eq!(first_run.auth_stage(), AuthStage::Confirmation);
    assert_eq!(first_run.masked_auth_input(), "");

    let mut locked = AppState::locked();
    receive_server_hello(&mut locked, false);
    locked.handle(InputEvent::Char('p'));
    locked.handle(InputEvent::Char('w'));
    assert_eq!(locked.masked_auth_input(), "**");
    assert!(!format!("{locked:?}").contains("pw"));
}

#[test]
fn backspace_removes_one_password_character_without_revealing_it() {
    let mut state = AppState::locked();
    receive_server_hello(&mut state, false);
    for character in "SENSITIVE7".chars() {
        state.handle(InputEvent::Char(character));
    }

    assert!(state.handle(InputEvent::Backspace).is_empty());
    assert_eq!(state.masked_auth_input(), "*********");
    assert!(!format!("{state:?}").contains("SENSITIVE"));
}

#[test]
fn first_run_setup_requires_matching_confirmation() {
    let mut state = AppState::locked();
    receive_server_hello(&mut state, true);
    state.handle(InputEvent::Char('p'));
    state.handle(InputEvent::Char('w'));
    assert!(state.handle(InputEvent::Enter).is_empty());
    state.handle(InputEvent::Char('n'));
    state.handle(InputEvent::Char('o'));

    assert!(state.handle(InputEvent::Enter).is_empty());
    assert_eq!(state.access, AccessState::FirstRun);
    assert_eq!(state.auth_stage(), AuthStage::Confirmation);

    state.handle(InputEvent::Char('p'));
    state.handle(InputEvent::Char('w'));
    let actions = state.handle(InputEvent::Enter);
    assert!(matches!(
        actions.as_slice(),
        [ClientAction::Authenticate(AuthRequest::Setup { .. })]
    ));
}

#[test]
fn locked_enter_emits_only_an_unlock_request() {
    let mut state = AppState::locked();
    receive_server_hello(&mut state, false);
    for character in "SENSITIVE".chars() {
        state.handle(InputEvent::Char(character));
    }

    let actions = state.handle(InputEvent::Enter);

    assert!(matches!(
        actions.as_slice(),
        [ClientAction::Authenticate(AuthRequest::Unlock { .. })]
    ));
    assert!(state.auth_pending());
    assert!(format!("{actions:?}").contains("<redacted>"));
    assert!(!format!("{actions:?}").contains("SENSITIVE"));
    assert_eq!(state.access, AccessState::Locked);
}

#[test]
fn viewer_take_control_emits_the_foundation_lease_request() {
    let mut state = AppState::viewer();

    assert_eq!(
        state.handle(InputEvent::TakeControl),
        vec![ClientAction::RequestLease]
    );
    assert_eq!(state.access, AccessState::Viewer);
}

#[test]
fn local_modes_follow_global_keys_and_escape_returns_to_browse() {
    let mut state = AppState::controller();
    state.reduce(snapshot_envelope(1)).unwrap();

    for (key, expected) in [
        ('o', LocalMode::Open),
        ('/', LocalMode::Search),
        ('f', LocalMode::Filter),
        (':', LocalMode::Menu),
        ('?', LocalMode::Help),
    ] {
        state.handle(InputEvent::Char(key));
        assert_eq!(state.mode, expected);
        state.handle(InputEvent::Escape);
        assert_eq!(state.mode, LocalMode::Browse);
    }
}

#[test]
fn generic_agent_input_cannot_open_outside_the_agents_screen() {
    let mut state = AppState::controller();
    assert!(state.handle(InputEvent::Enter).is_empty());
    assert_eq!(
        state.handle(InputEvent::Char('q')),
        vec![ClientAction::CloseTui]
    );

    state.handle(InputEvent::Char('i'));
    assert_eq!(state.mode, LocalMode::Browse);
    assert!(state.handle(InputEvent::Enter).is_empty());
}

#[test]
fn password_input_is_bounded_by_utf8_bytes_and_rejects_empty_submission() {
    let mut empty = AppState::locked();
    receive_server_hello(&mut empty, false);
    assert!(empty.handle(InputEvent::Enter).is_empty());

    let mut bounded = AppState::locked();
    receive_server_hello(&mut bounded, false);
    for _ in 0..513 {
        bounded.handle(InputEvent::Char('é'));
    }
    assert_eq!(bounded.masked_auth_input().chars().count(), 512);
    assert!(matches!(
        bounded.handle(InputEvent::Enter).as_slice(),
        [ClientAction::Authenticate(AuthRequest::Unlock { .. })]
    ));
}

#[test]
fn backspace_and_escape_handle_unicode_text_without_leaking_or_submitting() {
    let mut password = AppState::locked();
    receive_server_hello(&mut password, false);
    password.handle(InputEvent::Char('é'));
    password.handle(InputEvent::Char('🙂'));
    password.handle(InputEvent::Backspace);
    assert_eq!(password.masked_auth_input(), "*");
    assert!(password.handle(InputEvent::Escape).is_empty());
    assert_eq!(password.masked_auth_input(), "");

    let mut input = AppState::controller();
    input.reduce(snapshot_envelope(1)).unwrap();
    input.handle(InputEvent::Char('4'));
    input.handle(InputEvent::Char('i'));
    input.handle(InputEvent::Enter);
    assert_eq!(input.mode, LocalMode::AgentChat);
    input.handle(InputEvent::Char('i'));
    assert_eq!(input.mode, LocalMode::AgentInput);
    input.handle(InputEvent::Char('é'));
    input.handle(InputEvent::Char('🙂'));
    input.handle(InputEvent::Backspace);
    assert!(input.handle(InputEvent::Enter).is_empty());
    assert_eq!(input.chat_input(), "é");
    input.handle(InputEvent::Escape);
    assert_eq!(input.mode, LocalMode::AgentChat);
    input.handle(InputEvent::Escape);
    assert_eq!(input.mode, LocalMode::Browse);
    input.handle(InputEvent::Char('i'));
    input.handle(InputEvent::Enter);
    input.handle(InputEvent::Char('i'));
    assert!(input.handle(InputEvent::Enter).is_empty());
    assert_eq!(input.chat_input(), "");
}

#[test]
fn arbitrarily_long_idle_does_not_lock_or_emit_an_action() {
    let mut state = AppState::controller();

    assert!(
        state
            .handle(InputEvent::Tick(Duration::from_secs(u64::MAX)))
            .is_empty()
    );
    assert_eq!(state.access, AccessState::Controller);
}

#[test]
fn authentication_submission_requires_server_hello_and_allows_only_one_pending_request() {
    let mut state = AppState::locked();
    state.handle(InputEvent::Char('p'));
    assert!(state.handle(InputEvent::Enter).is_empty());
    assert_eq!(state.masked_auth_input(), "");
    assert!(!state.auth_pending());

    receive_server_hello(&mut state, false);
    state.handle(InputEvent::Char('p'));
    assert!(matches!(
        state.handle(InputEvent::Enter).as_slice(),
        [ClientAction::Authenticate(AuthRequest::Unlock { .. })]
    ));
    assert!(state.auth_pending());
    state.handle(InputEvent::Char('x'));
    assert!(state.handle(InputEvent::Enter).is_empty());
    assert_eq!(state.masked_auth_input(), "");
}

#[test]
fn crossterm_conversion_accepts_press_only_and_blocks_modified_character_leakage() {
    assert_eq!(
        key_to_input(KeyEvent::new_with_kind(
            KeyCode::Char('x'),
            KeyModifiers::NONE,
            KeyEventKind::Press,
        )),
        Some(InputEvent::Char('x'))
    );
    for kind in [KeyEventKind::Repeat, KeyEventKind::Release] {
        assert_eq!(
            key_to_input(KeyEvent::new_with_kind(
                KeyCode::Char('x'),
                KeyModifiers::NONE,
                kind,
            )),
            None
        );
    }
    for modifier in [
        KeyModifiers::ALT,
        KeyModifiers::SUPER,
        KeyModifiers::HYPER,
        KeyModifiers::META,
    ] {
        assert_eq!(
            key_to_input(KeyEvent::new_with_kind(
                KeyCode::Char('x'),
                modifier,
                KeyEventKind::Press,
            )),
            None
        );
    }
    assert_eq!(
        key_to_input(KeyEvent::new_with_kind(
            KeyCode::Char('X'),
            KeyModifiers::SHIFT,
            KeyEventKind::Press,
        )),
        Some(InputEvent::Char('X'))
    );
    assert_eq!(
        key_to_input(KeyEvent::new_with_kind(
            KeyCode::Char('c'),
            KeyModifiers::CONTROL,
            KeyEventKind::Press,
        )),
        Some(InputEvent::CloseTui)
    );
    assert_eq!(
        key_to_input(KeyEvent::new_with_kind(
            KeyCode::Char('x'),
            KeyModifiers::CONTROL,
            KeyEventKind::Press,
        )),
        None
    );
    for (code, expected) in [
        (KeyCode::Up, InputEvent::Up),
        (KeyCode::Down, InputEvent::Down),
        (KeyCode::PageUp, InputEvent::PageUp),
        (KeyCode::PageDown, InputEvent::PageDown),
        (KeyCode::Left, InputEvent::Left),
        (KeyCode::Right, InputEvent::Right),
    ] {
        assert_eq!(
            key_to_input(KeyEvent::new_with_kind(
                code,
                KeyModifiers::NONE,
                KeyEventKind::Press,
            )),
            Some(expected)
        );
    }
}

#[test]
fn polling_is_exactly_ten_milliseconds() {
    assert_eq!(POLL_INTERVAL, Duration::from_millis(10));
    assert_eq!(SEND_TIMEOUT, Duration::from_millis(50));
}

#[tokio::test]
async fn due_search_from_merged_idle_effect_is_dispatched_to_the_session() {
    let mut client = FoundationClient::from_app(App::new(AppState::controller()));
    let mut inputs = [
        InputEvent::Char('/'),
        InputEvent::Char('A'),
        InputEvent::Char('A'),
        InputEvent::Char('P'),
        InputEvent::Char('L'),
    ]
    .into_iter();
    let mut effect = process_input_batch(&mut client, &mut inputs);

    for _ in 0..9 {
        effect.merge(client.app_mut().on_idle());
        assert!(effect.foundation_actions.is_empty());
    }
    effect.merge(client.app_mut().on_idle());
    assert_eq!(effect.foundation_actions.len(), 1);

    let mut session = FakeSession::default();
    assert_eq!(
        client.dispatch(effect, &mut session).await.unwrap(),
        SessionStep::Continue
    );
    assert_eq!(session.sent.len(), 1);
    assert_eq!(session.sent[0].message_type(), MessageType::SearchRequest);
    let Message::SearchRequest(payload) = &session.sent[0].message else {
        panic!("search action must serialize as search-request");
    };
    assert_eq!(payload.request_id.get(), 4);
    assert_eq!(payload.query.as_str(), "AAPL");
}

#[tokio::test]
async fn direct_memory_open_dispatches_one_exact_content_request() {
    let mut client = FoundationClient::from_app(App::new(AppState::controller()));
    client.app_mut().reduce(snapshot_envelope(1)).unwrap();
    let mut inputs = [InputEvent::Char('9'), InputEvent::Char('o')].into_iter();
    let effect = process_input_batch(&mut client, &mut inputs);

    let mut session = FakeSession::default();
    assert_eq!(
        client.dispatch(effect, &mut session).await.unwrap(),
        SessionStep::Continue
    );
    assert_eq!(session.sent.len(), 1);
    assert_eq!(
        session.sent[0].message_type(),
        MessageType::MemoryContentRequest
    );
    let Message::MemoryContentRequest(payload) = &session.sent[0].message else {
        panic!("memory action must serialize as memory-content-request");
    };
    assert_eq!(payload.request_id.get(), 1);
    assert_eq!(payload.memory_id.as_str(), "memory:1");
    assert_eq!(
        payload.reviewed_updated_at_utc.as_str(),
        "2026-08-03T00:00:00Z"
    );
}

#[test]
fn models_header_click_without_typed_selection_does_not_open_a_detail() {
    let mut state = AppState::controller();
    state.reduce(snapshot_envelope(1)).unwrap();
    state.handle(InputEvent::Char('5'));
    assert!(state.screen_state().selected_id.is_none());
    assert!(state.screen_state().selected_kind.is_none());

    let area = Rect::new(0, 0, 140, 40);
    let body = split_control_area(
        shell_layout(area, state.display_mode()).body,
        state.display_mode(),
    )
    .0;
    let opinion_header = MouseEvent {
        kind: MouseEventKind::Down(MouseButton::Left),
        column: body.x + 2,
        row: body.y + 1,
        modifiers: KeyModifiers::NONE,
    };

    assert_eq!(mouse_to_input(opinion_header, area, &state), None);
    assert_eq!(state.mode, LocalMode::Browse);
}

#[test]
fn system_mouse_boundary_matches_the_rendered_source_and_live_panel_split() {
    let mut state = AppState::controller();
    state.reduce(snapshot_envelope(1)).unwrap();
    state.handle(InputEvent::Char('0'));
    let area = Rect::new(0, 0, 140, 40);
    let body = split_control_area(
        shell_layout(area, state.display_mode()).body,
        state.display_mode(),
    )
    .0;
    let rows =
        Layout::vertical([Constraint::Percentage(50), Constraint::Percentage(50)]).split(body);
    let bottom =
        Layout::horizontal([Constraint::Percentage(45), Constraint::Percentage(55)]).split(rows[1]);
    let click = |column| MouseEvent {
        kind: MouseEventKind::Down(MouseButton::Left),
        column,
        row: bottom[0].y + 1,
        modifiers: KeyModifiers::NONE,
    };

    assert_eq!(
        mouse_to_input(click(bottom[0].right() - 2), area, &state),
        Some(InputEvent::OpenBrowseRow { panel: 2, index: 0 })
    );
    assert_eq!(mouse_to_input(click(bottom[1].x), area, &state), None);
}

#[test]
fn market_mouse_hitboxes_use_the_same_preference_aware_panel_boundaries() {
    let mut state = AppState::controller();
    state.reduce(snapshot_envelope(1)).unwrap();
    state.set_screen_preferences(
        ScreenId::Impact,
        ScreenPreferences {
            visible_columns: Vec::new(),
            panel_sizes: vec![70, 30],
            performance_period: None,
        },
    );
    let area = Rect::new(0, 0, 140, 40);
    let body = split_control_area(
        shell_layout(area, state.display_mode()).body,
        state.display_mode(),
    )
    .0;
    let impact = impact_panels(body, &state.screen_state().panel_sizes);
    let click = |column, row| MouseEvent {
        kind: MouseEventKind::Down(MouseButton::Left),
        column,
        row,
        modifiers: KeyModifiers::NONE,
    };
    assert_eq!(
        mouse_to_input(click(impact[0].right() - 2, impact[0].y + 2), area, &state),
        Some(InputEvent::OpenBrowseRow { panel: 0, index: 0 })
    );
    assert_eq!(
        mouse_to_input(click(impact[1].x + 1, impact[1].y + 2), area, &state),
        None
    );

    state.handle(InputEvent::Char('2'));
    state.set_screen_preferences(
        ScreenId::Portfolio,
        ScreenPreferences {
            visible_columns: Vec::new(),
            panel_sizes: vec![63, 22, 15],
            performance_period: None,
        },
    );
    let portfolio = portfolio_panels(body, &state.screen_state().panel_sizes);
    assert_eq!(
        mouse_to_input(click(portfolio[0].x + 2, portfolio[0].y + 2), area, &state),
        Some(InputEvent::OpenBrowseRow { panel: 0, index: 0 })
    );
    assert_eq!(
        mouse_to_input(click(portfolio[1].x + 2, portfolio[1].y + 1), area, &state),
        None
    );
}

#[test]
fn narrow_market_footer_exposes_mouse_reachable_panel_focus_controls() {
    let mut state = AppState::controller();
    state.reduce(snapshot_envelope(1)).unwrap();
    state.handle(InputEvent::Char('2'));
    let area = Rect::new(0, 0, 100, 30);
    let footer = shell_layout(area, state.display_mode()).footer;
    let click = |column| MouseEvent {
        kind: MouseEventKind::Down(MouseButton::Left),
        column,
        row: footer.y + 1,
        modifiers: KeyModifiers::NONE,
    };

    assert_eq!(
        mouse_to_input(click(footer.x + 2), area, &state),
        Some(InputEvent::Char('['))
    );
    assert_eq!(
        mouse_to_input(click(footer.x + 11), area, &state),
        Some(InputEvent::Char(']'))
    );
}

#[test]
fn system_live_panel_background_click_then_mouse_wheel_reaches_the_final_order() {
    let mut snapshot: serde_json::Value = serde_json::from_slice(include_bytes!(
        "../../contracts/v1/console_snapshot_empty_command_specs.json"
    ))
    .expect("valid shared console snapshot");
    snapshot["system"]["live_transition_plan"] = json!({
        "broker_positions_as_of_utc": "2026-08-04T12:00:00Z",
        "desired_portfolio_id": "portfolio:candidate",
        "orders": (0..8).map(|index| json!({
            "symbol": format!("SYM{index}"),
            "side": "buy",
            "quantity": "1",
            "approval_required": true
        })).collect::<Vec<_>>()
    });
    let mut state = AppState::controller();
    state
        .reduce(inbound_envelope(
            1,
            "snapshot",
            json!({"snapshot": snapshot}),
        ))
        .unwrap();
    state.handle(InputEvent::Char('0'));

    let area = Rect::new(0, 0, 140, 40);
    let body = split_control_area(
        shell_layout(area, state.display_mode()).body,
        state.display_mode(),
    )
    .0;
    let rows =
        Layout::vertical([Constraint::Percentage(50), Constraint::Percentage(50)]).split(body);
    let bottom =
        Layout::horizontal([Constraint::Percentage(45), Constraint::Percentage(55)]).split(rows[1]);
    let live_column = bottom[1].x + 2;
    let live_row = bottom[1].y + 1;
    let click = MouseEvent {
        kind: MouseEventKind::Down(MouseButton::Left),
        column: live_column,
        row: live_row,
        modifiers: KeyModifiers::NONE,
    };

    let focus = mouse_to_input(click, area, &state);
    assert_eq!(focus, Some(InputEvent::FocusBrowsePanel { panel: 3 }));
    state.handle(focus.unwrap());
    for _ in 0..20 {
        let wheel = MouseEvent {
            kind: MouseEventKind::ScrollDown,
            column: live_column,
            row: live_row,
            modifiers: KeyModifiers::NONE,
        };
        state.handle(mouse_to_input(wheel, area, &state).unwrap());
    }

    assert_eq!(state.screen_state().narrow_panel, 3);
    assert!(state.screen_state().scroll_offset >= 8);
    let backend = TestBackend::new(area.width, area.height);
    let mut terminal = Terminal::new(backend).unwrap();
    terminal
        .draw(|frame| vesper_ratatui_console::ui::render(frame, &state))
        .unwrap();
    let text: String = terminal
        .backend()
        .buffer()
        .content
        .iter()
        .map(|cell| cell.symbol())
        .collect();
    assert!(text.contains("SYM7"), "{text}");
}

#[test]
fn terminal_input_batches_are_bounded_and_keep_key_order() {
    let mut client = FoundationClient::from_app(App::new(AppState::controller()));
    let mut inputs = (0..MAX_EVENTS_PER_TICK)
        .map(|index| InputEvent::Char(if index % 2 == 0 { '2' } else { '3' }))
        .chain([InputEvent::Char('q')])
        .peekable();

    let effect = process_input_batch(&mut client, &mut inputs);

    assert!(!effect.exit);
    assert!(effect.foundation_actions.is_empty());
    assert_eq!(client.app().state().screen, Screen::Orders);
    assert_eq!(inputs.next(), Some(InputEvent::Char('q')));
}

#[tokio::test]
async fn local_close_drops_earlier_batched_foundation_actions() {
    let mut client = FoundationClient::from_app(App::new(AppState::viewer()));
    let mut inputs = [InputEvent::TakeControl, InputEvent::CloseTui].into_iter();
    let effect = process_input_batch(&mut client, &mut inputs);
    let mut session = HangingSendSession::default();

    assert!(effect.exit);
    assert!(effect.foundation_actions.is_empty());
    assert_eq!(
        tokio::time::timeout(
            Duration::from_millis(10),
            client.dispatch(effect, &mut session),
        )
        .await
        .expect("close must not wait for a send")
        .unwrap(),
        SessionStep::Exit
    );
    assert_eq!(session.sends, 0);
}

#[test]
fn executable_checkout_ancestor_wins_over_runtime_checkout() {
    let executable = TempCheckout::new("executable-root", true);
    let runtime = TempCheckout::new("runtime-root", true);

    let resolved = resolve_repo_root_from(
        &executable.root.join("nested/deeper"),
        &runtime.root.join("nested/deeper"),
    )
    .unwrap();

    assert_eq!(resolved, executable.root.canonicalize().unwrap());
}

#[test]
fn runtime_checkout_is_used_only_when_executable_ancestors_are_invalid() {
    let executable = TempCheckout::new("executable-invalid", false);
    let runtime = TempCheckout::new("runtime-fallback", true);

    let resolved = resolve_repo_root_from(
        &executable.root.join("nested/deeper"),
        &runtime.root.join("nested/deeper"),
    )
    .unwrap();

    assert_eq!(resolved, runtime.root.canonicalize().unwrap());
}

#[test]
fn repository_root_resolution_fails_closed_without_checkout_markers() {
    let executable = TempCheckout::new("executable-missing", false);
    let runtime = TempCheckout::new("runtime-missing", false);

    assert!(
        resolve_repo_root_from(
            &executable.root.join("nested/deeper"),
            &runtime.root.join("nested/deeper"),
        )
        .is_err()
    );
}

#[test]
fn repository_root_rejects_marker_only_or_incomplete_lookalikes() {
    let lookalike = TempCheckout::lookalike("commented-lookalike");
    let missing = TempCheckout::new("missing-fallback", false);
    assert!(
        resolve_repo_root_from(
            &lookalike.root.join("nested/deeper"),
            &missing.root.join("nested/deeper"),
        )
        .is_err()
    );

    let incomplete = TempCheckout::new("incomplete-package", true);
    fs::remove_file(incomplete.root.join("vesper/platform/tui/protocol.py")).unwrap();
    assert!(
        resolve_repo_root_from(
            &incomplete.root.join("nested/deeper"),
            &missing.root.join("nested/deeper"),
        )
        .is_err()
    );

    let multiline = TempCheckout::multiline_lookalike("multiline-lookalike");
    assert!(
        resolve_repo_root_from(
            &multiline.root.join("nested/deeper"),
            &missing.root.join("nested/deeper"),
        )
        .is_err()
    );
}

#[test]
fn repository_root_rejects_every_missing_gateway_runtime_dependency() {
    let fallback = TempCheckout::new("dependency-missing-fallback", false);
    let checkout = TempCheckout::new("dependency-missing", true);
    for required in required_gateway_runtime_files() {
        fs::remove_file(checkout.root.join(required)).unwrap();
        assert!(
            resolve_repo_root_from(
                &checkout.root.join("nested/deeper"),
                &fallback.root.join("nested/deeper"),
            )
            .is_err(),
            "accepted checkout missing {required}"
        );
        fs::write(checkout.root.join(required), "# test module\n").unwrap();
    }
}

#[test]
fn gateway_runtime_dependency_closure_includes_all_new_transitive_imports() {
    let required = required_gateway_runtime_files();
    for dependency in [
        "vesper/platform/ops/__init__.py",
        "vesper/platform/ops/activation.py",
        "vesper/platform/ops/alerts.py",
        "vesper/platform/ops/notification_health.py",
        "vesper/platform/ops/policy.py",
        "vesper/platform/ops/services.py",
        "vesper/platform/ops/supervisor.py",
        "vesper/platform/ops/training.py",
        "vesper/platform/paths.py",
        "vesper/platform/tui/alert_dismissals.py",
        "vesper/platform/tui/backup.py",
        "vesper/platform/tui/git_port.py",
        "vesper/platform/tui/notifications.py",
        "vesper/platform/tui/recovery.py",
        "vesper/platform/tui/snapshot_cache.py",
        "vesper/platform/tui/working_memory.py",
        "vesper/platform/tui/projections/managed_memory.py",
        "vesper/platform/tui/projections/operations_status.py",
    ] {
        assert!(required.contains(&dependency), "missing {dependency}");
    }
    let unique = required
        .iter()
        .copied()
        .collect::<std::collections::BTreeSet<_>>();
    assert_eq!(
        unique.len(),
        required.len(),
        "runtime closure has duplicates"
    );
}

#[test]
fn idle_does_not_redraw_but_input_and_reducer_changes_do() {
    let mut app = App::new(AppState::controller());
    assert!(app.take_redraw());
    assert!(!app.take_redraw());

    let idle = app.on_idle();
    assert!(!idle.exit);
    assert!(idle.foundation_actions.is_empty());
    assert!(!app.take_redraw());

    app.handle_input(InputEvent::Char('2'));
    assert!(app.take_redraw());
    assert!(!app.take_redraw());

    let mut locked = App::new(AppState::locked());
    locked.take_redraw();
    assert_eq!(
        locked.reduce(server_hello_envelope(false)),
        Ok(ReduceOutcome::Changed)
    );
    assert!(locked.take_redraw());
}

#[test]
fn mouse_capture_toggles_only_for_unlocked_access_and_turns_off_on_exit() {
    let mut mouse = MouseCaptureTracker::default();
    assert_eq!(mouse.sync(AccessState::Locked), None);
    assert_eq!(
        mouse.sync(AccessState::Viewer),
        Some(MouseCaptureChange::Enable)
    );
    assert_eq!(mouse.sync(AccessState::Controller), None);
    assert_eq!(
        mouse.sync(AccessState::Locked),
        Some(MouseCaptureChange::Disable)
    );
    assert_eq!(
        mouse.sync(AccessState::Controller),
        Some(MouseCaptureChange::Enable)
    );
    assert_eq!(mouse.on_exit(), Some(MouseCaptureChange::Disable));
    assert_eq!(mouse.on_exit(), None);
}

#[test]
fn q_exits_without_a_foundation_or_runtime_action() {
    let mut app = App::new(AppState::controller());

    let effect = app.handle_input(InputEvent::Char('q'));

    assert!(effect.exit);
    assert!(effect.foundation_actions.is_empty());
}

#[test]
fn foundation_loop_never_forwards_agent_input() {
    let mut app = App::new(AppState::controller());
    app.handle_input(InputEvent::Char('i'));
    app.handle_input(InputEvent::Char('x'));

    let effect = app.handle_input(InputEvent::Enter);

    assert!(!effect.exit);
    assert!(effect.foundation_actions.is_empty());
}

#[test]
fn restoration_runs_once_after_normal_return() {
    let calls = Cell::new(0);
    let result: Result<(), &'static str> = with_restore(|| Ok(()), || calls.set(calls.get() + 1));

    assert_eq!(result, Ok(()));
    assert_eq!(calls.get(), 1);
}

#[test]
fn restoration_runs_once_after_early_error() {
    let calls = Cell::new(0);
    let result: Result<(), &'static str> =
        with_restore(|| Err("early"), || calls.set(calls.get() + 1));

    assert_eq!(result, Err("early"));
    assert_eq!(calls.get(), 1);
}

#[test]
fn restoration_runs_once_during_panic_unwind() {
    let calls = Cell::new(0);
    let unwind = catch_unwind(AssertUnwindSafe(|| {
        let _: Result<(), ()> =
            with_restore(|| panic!("test panic"), || calls.set(calls.get() + 1));
    }));

    assert!(unwind.is_err());
    assert_eq!(calls.get(), 1);
}

#[tokio::test]
async fn foundation_session_runs_typed_hello_auth_snapshot_lease_and_lock_flow() {
    let mut session = FakeSession::default();
    let mut client = FoundationClient::new();

    client.start(&mut session).await.unwrap();
    assert_eq!(session.sent[0].message_type(), MessageType::ClientHello);
    assert_eq!(session.sent[0].schema_version, 1);
    assert_eq!(session.sent[0].message_id.as_str(), "client:1");
    assert_eq!(session.sent[0].sequence, 1);
    assert_eq!(session.sent[0].state_version, 0);
    let outbound_timestamp = session.sent[0].timestamp_utc.as_str();
    assert!(outbound_timestamp.ends_with('Z'));
    assert!(matches!(outbound_timestamp.len(), 20 | 27));
    if outbound_timestamp.len() == 27 {
        assert_eq!(outbound_timestamp.as_bytes()[19], b'.');
        assert!(
            outbound_timestamp.as_bytes()[20..26]
                .iter()
                .all(u8::is_ascii_digit)
        );
    }
    assert!(
        serde_json::from_value::<UtcTimestamp>(json!(session.sent[0].timestamp_utc.as_str()))
            .is_ok()
    );
    let hello = serde_json::to_value(&session.sent[0]).unwrap();
    assert_eq!(
        hello["payload"]["client_version"],
        env!("CARGO_PKG_VERSION")
    );
    assert_eq!(hello["payload"]["supported_schema_versions"], json!([1]));

    session.incoming.push_back(server_hello_envelope(false));
    assert_eq!(
        client.receive(&mut session).await.unwrap(),
        SessionStep::Continue
    );
    client
        .handle_input(InputEvent::Char('p'), &mut session)
        .await
        .unwrap();
    assert_eq!(
        client
            .handle_input(InputEvent::Enter, &mut session)
            .await
            .unwrap(),
        SessionStep::Continue
    );
    assert_eq!(
        session.sent.last().unwrap().message_type(),
        MessageType::AuthUnlock
    );

    session.incoming.push_back(inbound_envelope(
        2,
        "auth-result",
        json!({ "success": true, "access_state": "viewer", "reason": null }),
    ));
    assert_eq!(
        client.receive(&mut session).await.unwrap(),
        SessionStep::Continue
    );
    assert_eq!(
        session.sent.last().unwrap().message_type(),
        MessageType::SnapshotRequest
    );

    session.incoming.push_back(snapshot_envelope(3));
    client.receive(&mut session).await.unwrap();
    client
        .handle_input(InputEvent::TakeControl, &mut session)
        .await
        .unwrap();
    assert_eq!(
        session.sent.last().unwrap().message_type(),
        MessageType::LeaseRequest
    );
    session.incoming.push_back(inbound_envelope(
        4,
        "lease-result",
        json!({ "status": "controller", "reason": null }),
    ));
    client.receive(&mut session).await.unwrap();

    client
        .handle_input(InputEvent::LockTui, &mut session)
        .await
        .unwrap();
    assert_eq!(client.app().state().access, AccessState::Locked);
    assert!(client.app().state().snapshot.is_none());
    assert!(client.app().state().lock_pending());
    assert_eq!(
        session.sent.last().unwrap().message_type(),
        MessageType::LockRequest
    );
    session.incoming.push_back(inbound_envelope(
        5,
        "lock-result",
        json!({ "locked": true }),
    ));
    client.receive(&mut session).await.unwrap();
    assert_eq!(client.app().state().access, AccessState::Locked);
    assert_eq!(
        session
            .sent
            .iter()
            .map(|envelope| envelope.sequence)
            .collect::<Vec<_>>(),
        vec![1, 2, 3, 4, 5]
    );

    let mut fresh_session = FakeSession::default();
    FoundationClient::new()
        .start(&mut fresh_session)
        .await
        .unwrap();
    assert_eq!(fresh_session.sent[0].sequence, 1);
}

#[tokio::test]
async fn outbound_sequence_is_independent_from_a_high_gapped_server_sequence() {
    let mut client = FoundationClient::from_app(App::new(AppState::viewer()));
    let mut session = FakeSession::default();
    session
        .incoming
        .push_back(inbound_envelope(99, "pong", json!({ "nonce": "gap" })));

    assert_eq!(
        client.receive(&mut session).await.unwrap(),
        SessionStep::Continue
    );

    assert_eq!(session.sent.len(), 1);
    assert_eq!(session.sent[0].sequence, 1);
    assert_eq!(session.sent[0].message_id.as_str(), "client:1");
    assert_eq!(session.sent[0].message_type(), MessageType::SnapshotRequest);
}

#[tokio::test]
async fn foundation_session_resnapshots_reconnects_and_never_sends_local_input_or_q() {
    let mut session = FakeSession::default();
    let mut client = FoundationClient::new();
    client.start(&mut session).await.unwrap();
    session.incoming.push_back(server_hello_envelope(false));
    client.receive(&mut session).await.unwrap();
    client
        .handle_input(InputEvent::Char('p'), &mut session)
        .await
        .unwrap();
    client
        .handle_input(InputEvent::Enter, &mut session)
        .await
        .unwrap();
    session.incoming.push_back(inbound_envelope(
        2,
        "auth-result",
        json!({ "success": true, "access_state": "viewer", "reason": null }),
    ));
    client.receive(&mut session).await.unwrap();
    session.incoming.push_back(snapshot_envelope(3));
    client.receive(&mut session).await.unwrap();

    let before_local = session.sent.len();
    client
        .handle_input(InputEvent::Char('i'), &mut session)
        .await
        .unwrap();
    client
        .handle_input(InputEvent::Char('x'), &mut session)
        .await
        .unwrap();
    client
        .handle_input(InputEvent::Enter, &mut session)
        .await
        .unwrap();
    assert_eq!(session.sent.len(), before_local);
    client
        .handle_input(InputEvent::Escape, &mut session)
        .await
        .unwrap();
    assert_eq!(
        client
            .handle_input(InputEvent::Char('q'), &mut session)
            .await
            .unwrap(),
        SessionStep::Exit
    );
    assert_eq!(session.sent.len(), before_local);

    let mut resync = FoundationClient::from_app(App::new(AppState::viewer()));
    let mut resync_session = FakeSession::default();
    resync_session
        .incoming
        .push_back(inbound_envelope(2, "pong", json!({ "nonce": "gap" })));
    assert_eq!(
        resync.receive(&mut resync_session).await.unwrap(),
        SessionStep::Continue
    );
    assert_eq!(
        resync_session.sent.last().unwrap().message_type(),
        MessageType::SnapshotRequest
    );
    resync_session.incoming.push_back(inbound_envelope(
        3,
        "protocol-error",
        json!({ "code": "schema", "safe_message": "Protocol mismatch." }),
    ));
    assert_eq!(
        resync.receive(&mut resync_session).await.unwrap(),
        SessionStep::Reconnect
    );
}

#[tokio::test]
async fn foundation_session_failures_clear_content_mark_redraw_and_disable_mouse() {
    let mut state = AppState::viewer();
    state.reduce(snapshot_envelope(1)).unwrap();
    let mut client = FoundationClient::from_app(App::new(state));
    client.app_mut().take_redraw();
    let mut mouse = MouseCaptureTracker::default();
    assert_eq!(
        mouse.sync(client.app().state().access),
        Some(MouseCaptureChange::Enable)
    );

    let mut recv_failure = FakeSession {
        fail_recv: true,
        ..FakeSession::default()
    };
    assert!(client.receive(&mut recv_failure).await.is_err());
    assert_eq!(client.app().state().access, AccessState::ProtocolLockout);
    assert!(client.app().state().snapshot.is_none());
    assert!(client.app_mut().take_redraw());
    assert_eq!(
        mouse.sync(client.app().state().access),
        Some(MouseCaptureChange::Disable)
    );

    let mut send_state = AppState::viewer();
    send_state.reduce(snapshot_envelope(1)).unwrap();
    let mut send_client = FoundationClient::from_app(App::new(send_state));
    let mut send_failure = FakeSession {
        fail_send: true,
        ..FakeSession::default()
    };
    assert!(
        send_client
            .handle_input(InputEvent::TakeControl, &mut send_failure)
            .await
            .is_err()
    );
    assert_eq!(
        send_client.app().state().access,
        AccessState::ProtocolLockout
    );
    assert!(send_client.app().state().snapshot.is_none());
}

#[tokio::test]
async fn inbound_protocol_error_clears_content_before_requesting_reconnect() {
    let mut state = AppState::viewer();
    state.reduce(snapshot_envelope(1)).unwrap();
    let mut client = FoundationClient::from_app(App::new(state));
    client.app_mut().take_redraw();
    let mut session = FakeSession::default();
    session.incoming.push_back(inbound_envelope(
        2,
        "protocol-error",
        json!({ "code": "schema", "safe_message": "Protocol mismatch." }),
    ));

    assert_eq!(
        client.receive(&mut session).await.unwrap(),
        SessionStep::Reconnect
    );
    assert_eq!(client.app().state().access, AccessState::ProtocolLockout);
    assert!(client.app().state().snapshot.is_none());
    assert!(client.app_mut().take_redraw());
}

#[test]
fn q_is_preserved_as_password_text_after_server_hello() {
    let mut state = AppState::locked();
    receive_server_hello(&mut state, false);

    assert!(state.handle(InputEvent::Char('q')).is_empty());
    assert_eq!(state.masked_auth_input(), "*");
}

#[tokio::test]
async fn stalled_send_times_out_and_forces_a_fresh_connection() {
    let mut client = FoundationClient::from_app(App::new(AppState::viewer()));
    let mut session = HangingSendSession::default();
    let result = tokio::time::timeout(
        Duration::from_secs(1),
        client.handle_input(InputEvent::TakeControl, &mut session),
    )
    .await
    .expect("foundation send must have its own shorter timeout");

    assert!(matches!(result, Err(SessionError::SendTimeout)));
    assert_eq!(client.app().state().access, AccessState::ProtocolLockout);
    assert_eq!(session.sends, 1);
    assert!(matches!(
        client.start(&mut session).await,
        Err(SessionError::Disconnected)
    ));
    assert_eq!(session.sends, 1, "failed pipes must never be reused");
}

#[tokio::test]
async fn connector_retries_twice_then_succeeds_with_capped_backoff() {
    let mut connector = RetryConnector {
        failures_remaining: 2,
        ..RetryConnector::default()
    };
    let mut control = RetryControl::default();

    let mut session = connect_with_retry(&mut connector, Path::new("."), &mut control)
        .await
        .unwrap()
        .expect("third attempt succeeds");

    assert_eq!(connector.attempts, 3);
    assert_eq!(control.draws, 1);
    assert_eq!(
        control.delays,
        vec![Duration::from_millis(50), Duration::from_millis(100)]
    );
    let mut client = FoundationClient::new();
    client.start(&mut session).await.unwrap();
    assert_eq!(session.sent[0].sequence, 1);
}
