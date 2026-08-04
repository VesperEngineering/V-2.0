use std::fmt;
use std::future::Future;
use std::io;
use std::path::{Path, PathBuf};
use std::time::Duration;

use crossterm::event::{
    self, DisableMouseCapture, EnableMouseCapture, Event, KeyCode, KeyEvent, KeyEventKind,
    KeyModifiers,
};
use crossterm::execute;
use ratatui::DefaultTerminal;
use ratatui::widgets::{Block, Borders, Paragraph};

use crate::contract::{
    AuthSetupPayload, AuthUnlockPayload, ClientHelloPayload, Envelope, LeaseRequestPayload,
    LockAction, LockRequestPayload, Message, NonEmptyString, SnapshotRequestPayload,
    TakeControlAction, UtcTimestamp,
};
use crate::input::InputEvent;
use crate::launcher::{GatewayLauncher, LaunchError};
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
    "vesper/platform/tui/outbox.py",
    "vesper/platform/tui/pipe_security.py",
    "vesper/platform/tui/pipe_server.py",
    "vesper/platform/tui/ports.py",
    "vesper/platform/tui/process_capture.py",
    "vesper/platform/tui/protocol.py",
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
        _ => None,
    }
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
        LoopEffect::default()
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
    let mut saw_event = false;
    for _ in 0..MAX_EVENTS_PER_TICK {
        if !event::poll(Duration::ZERO)? {
            break;
        }
        saw_event = true;
        match event::read()? {
            Event::Key(key) => {
                if let Some(input) = key_to_input(key) {
                    inputs.push(input);
                }
            }
            Event::Resize(_, _) => resized = true,
            Event::Mouse(_) if client.app.state().access.is_unlocked() => {}
            _ => {}
        }
    }
    let effect = process_input_batch(client, &mut inputs.into_iter());
    if resized {
        client.app.force_redraw();
    }
    if !saw_event {
        client.app.on_idle();
    }
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
    if client.app.take_redraw() {
        terminal.draw(|frame| crate::ui::render(frame, client.app.state()))?;
    }
    Ok(())
}
