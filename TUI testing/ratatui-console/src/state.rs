use std::fmt;

use crate::contract::{
    AccessState as WireAccessState, ConsoleSnapshot, Envelope, LeaseStatus, Message, PasswordString,
};
use crate::input::InputEvent;
use crate::layout::DisplayMode;
use crate::preferences::{LoadedPreferences, ScreenId, ScreenPreferences, UiPreferences};
use crate::theme::Theme;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Screen {
    #[default]
    Impact,
    Portfolio,
    Orders,
    Agents,
    ModelsRegime,
    Timeline,
    RiskApprovals,
    DataEvidence,
    Memory,
    System,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AccessState {
    Locked,
    FirstRun,
    Controller,
    Viewer,
    ProtocolLockout,
}

impl AccessState {
    pub fn is_unlocked(self) -> bool {
        matches!(self, Self::Controller | Self::Viewer)
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum LocalMode {
    #[default]
    Browse,
    Open,
    Search,
    Filter,
    Menu,
    Help,
    AgentInput,
}

impl LocalMode {
    fn captures_text(self) -> bool {
        matches!(
            self,
            Self::Search | Self::Filter | Self::Menu | Self::AgentInput
        )
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum AuthStage {
    #[default]
    Password,
    Confirmation,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum AuthFeedback {
    #[default]
    None,
    Pending,
    Failed,
    PasswordMismatch,
}

#[derive(Debug, PartialEq, Eq)]
pub enum AuthRequest {
    Setup {
        password: PasswordString,
        confirmation: PasswordString,
    },
    Unlock {
        password: PasswordString,
    },
}

#[derive(Debug, PartialEq, Eq)]
pub enum ClientAction {
    Authenticate(AuthRequest),
    RequestLease,
    RequestLock,
    RequestSnapshot,
    SubmitInput(String),
    CloseTui,
    Reconnect,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ReduceOutcome {
    Changed,
    Ignored,
    RequestSnapshot,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ProtocolError {
    pub code: String,
    pub safe_message: String,
}

#[derive(Default)]
struct SecretBuffer(String);

impl SecretBuffer {
    fn push(&mut self, character: char) {
        if self.0.len() + character.len_utf8() <= 1024 {
            self.0.push(character);
        }
    }

    fn pop(&mut self) {
        self.0.pop();
    }

    fn clear(&mut self) {
        self.0.clear();
    }

    fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    fn masked(&self) -> String {
        "*".repeat(self.0.chars().count())
    }

    fn matches(&self, other: &Self) -> bool {
        self.0 == other.0
    }

    fn take_password(&mut self) -> Option<PasswordString> {
        PasswordString::from_input(std::mem::take(&mut self.0)).ok()
    }
}

impl fmt::Debug for SecretBuffer {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("<redacted>")
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum SessionPhase {
    AwaitingServerHello,
    AwaitingAuth { first_run: bool },
    AwaitingAuthResult { first_run: bool },
    Authenticated,
    ProtocolLockout,
}

#[derive(Debug, PartialEq, Eq)]
struct ViewKey {
    access: AccessState,
    screen: Screen,
    mode: LocalMode,
    snapshot_version: Option<u64>,
    auth_stage: AuthStage,
    password_characters: usize,
    confirmation_characters: usize,
    auth_feedback: AuthFeedback,
    local_input: String,
    state_version: u64,
    awaiting_snapshot: bool,
    lock_pending: bool,
    lease_pending: bool,
    phase: SessionPhase,
    theme: Theme,
    display_mode: DisplayMode,
    preferences_unavailable: bool,
}

#[derive(Debug)]
pub struct AppState {
    pub access: AccessState,
    pub screen: Screen,
    pub mode: LocalMode,
    pub snapshot: Option<ConsoleSnapshot>,
    auth_stage: AuthStage,
    password: SecretBuffer,
    confirmation: SecretBuffer,
    auth_feedback: AuthFeedback,
    local_input: String,
    state_version: u64,
    last_sequence: u64,
    awaiting_snapshot: bool,
    lock_pending: bool,
    lease_pending: bool,
    phase: SessionPhase,
    dirty: bool,
    preferences: UiPreferences,
    preferences_unavailable: bool,
    preferences_save_pending: bool,
}

impl AppState {
    pub fn locked() -> Self {
        Self::new(AccessState::Locked)
    }

    pub fn first_run() -> Self {
        Self::new(AccessState::FirstRun)
    }

    pub fn controller() -> Self {
        Self::new(AccessState::Controller)
    }

    pub fn viewer() -> Self {
        Self::new(AccessState::Viewer)
    }

    fn new(access: AccessState) -> Self {
        let phase = match access {
            AccessState::Locked => SessionPhase::AwaitingServerHello,
            AccessState::FirstRun => SessionPhase::AwaitingServerHello,
            AccessState::Controller | AccessState::Viewer => SessionPhase::Authenticated,
            AccessState::ProtocolLockout => SessionPhase::ProtocolLockout,
        };
        Self {
            access,
            screen: Screen::Impact,
            mode: LocalMode::Browse,
            snapshot: None,
            auth_stage: AuthStage::Password,
            password: SecretBuffer::default(),
            confirmation: SecretBuffer::default(),
            auth_feedback: AuthFeedback::None,
            local_input: String::new(),
            state_version: 0,
            last_sequence: 0,
            awaiting_snapshot: false,
            lock_pending: false,
            lease_pending: false,
            phase,
            dirty: true,
            preferences: UiPreferences::default(),
            preferences_unavailable: false,
            preferences_save_pending: false,
        }
    }

    pub fn auth_stage(&self) -> AuthStage {
        self.auth_stage
    }

    pub fn masked_auth_input(&self) -> String {
        match self.auth_stage {
            AuthStage::Password => self.password.masked(),
            AuthStage::Confirmation => self.confirmation.masked(),
        }
    }

    pub fn auth_feedback(&self) -> AuthFeedback {
        self.auth_feedback
    }

    pub fn state_version(&self) -> u64 {
        self.state_version
    }

    pub fn awaiting_snapshot(&self) -> bool {
        self.awaiting_snapshot
    }

    pub fn lock_pending(&self) -> bool {
        self.lock_pending
    }

    pub fn auth_pending(&self) -> bool {
        matches!(self.phase, SessionPhase::AwaitingAuthResult { .. })
    }

    pub fn theme(&self) -> Theme {
        self.preferences.theme
    }

    pub fn display_mode(&self) -> DisplayMode {
        self.preferences.display_mode
    }

    pub fn preferences(&self) -> &UiPreferences {
        &self.preferences
    }

    pub fn preferences_unavailable(&self) -> bool {
        self.preferences_unavailable
    }

    pub fn apply_loaded_preferences(&mut self, loaded: LoadedPreferences) {
        self.preferences = loaded.preferences;
        self.preferences_unavailable = loaded.unavailable_reason.is_some();
        self.preferences_save_pending = false;
        self.dirty = true;
    }

    pub fn set_theme(&mut self, theme: Theme) {
        if self.preferences.theme != theme {
            self.preferences.theme = theme;
            self.preferences_save_pending = true;
            self.dirty = true;
        }
    }

    pub fn set_display_mode(&mut self, display_mode: DisplayMode) {
        if self.preferences.display_mode != display_mode {
            self.preferences.display_mode = display_mode;
            self.preferences_save_pending = true;
            self.dirty = true;
        }
    }

    pub fn set_screen_preferences(&mut self, screen: ScreenId, preferences: ScreenPreferences) {
        if self.preferences.screens.get(&screen) != Some(&preferences) {
            self.preferences.screens.insert(screen, preferences);
            self.preferences_save_pending = true;
            self.dirty = true;
        }
    }

    pub(crate) fn pending_preferences(&self) -> Option<&UiPreferences> {
        self.preferences_save_pending.then_some(&self.preferences)
    }

    pub(crate) fn finish_preferences_save(&mut self, succeeded: bool) {
        self.preferences_save_pending = false;
        let unavailable = !succeeded;
        if self.preferences_unavailable != unavailable {
            self.preferences_unavailable = unavailable;
            self.dirty = true;
        }
    }

    pub fn reduce(&mut self, envelope: Envelope) -> Result<ReduceOutcome, ProtocolError> {
        let before = self.view_key();
        let result = self.reduce_inner(envelope);
        if self.view_key() != before {
            self.dirty = true;
        }
        result
    }

    fn reduce_inner(&mut self, envelope: Envelope) -> Result<ReduceOutcome, ProtocolError> {
        if envelope.sequence == 0 {
            return Err(self.fail_closed("sequence", "Server sequence must start at one."));
        }
        let Some(expected_sequence) = self.last_sequence.checked_add(1) else {
            return Err(self.fail_closed("sequence", "Server sequence is exhausted."));
        };
        if envelope.sequence < expected_sequence {
            return Ok(ReduceOutcome::Ignored);
        }
        if envelope.sequence != expected_sequence {
            self.last_sequence = envelope.sequence;
            if matches!(&envelope.message, Message::ProtocolError(_)) {
                return Err(self.fail_closed(
                    "protocol",
                    "Protocol error followed a sequence gap; reconnect required.",
                ));
            }
            if self.phase != SessionPhase::Authenticated || self.lock_pending || self.lease_pending
            {
                return Err(self.fail_closed(
                    "sequence",
                    "Message sequence gap requires reconnect during a control transition.",
                ));
            }
            return match &envelope.message {
                Message::Snapshot(_) | Message::Event(_) | Message::Pong(_) => {
                    self.awaiting_snapshot = true;
                    self.snapshot = None;
                    Ok(ReduceOutcome::RequestSnapshot)
                }
                _ => Err(self.fail_closed(
                    "sequence",
                    "Message sequence gap cannot be recovered by a presentation snapshot.",
                )),
            };
        }
        self.last_sequence = envelope.sequence;

        if self.lock_pending {
            return match envelope.message {
                Message::Snapshot(payload) if self.awaiting_snapshot => {
                    if payload.snapshot.shell.state_version != envelope.state_version {
                        return Err(
                            self.fail_closed("state-version", "Snapshot version is invalid.")
                        );
                    }
                    self.awaiting_snapshot = false;
                    Ok(ReduceOutcome::Ignored)
                }
                Message::LeaseResult(_) if self.lease_pending => {
                    self.lease_pending = false;
                    Ok(ReduceOutcome::Ignored)
                }
                Message::Pong(_) => Ok(ReduceOutcome::Ignored),
                Message::LockResult(_) => {
                    self.enter_manual_lock();
                    Ok(ReduceOutcome::Changed)
                }
                Message::ProtocolError(payload) => {
                    let error = ProtocolError {
                        code: payload.code.as_str().to_owned(),
                        safe_message: payload.safe_message.as_str().to_owned(),
                    };
                    self.enter_protocol_lockout();
                    Err(error)
                }
                _ => Err(self.fail_closed("state", "Message is out of order while locking.")),
            };
        }

        match envelope.message {
            Message::ServerHello(payload) => {
                if self.phase != SessionPhase::AwaitingServerHello {
                    return Err(self.fail_closed("state", "Server hello is out of order."));
                }
                self.clear_auth();
                self.access = if payload.requires_setup {
                    AccessState::FirstRun
                } else {
                    AccessState::Locked
                };
                self.phase = SessionPhase::AwaitingAuth {
                    first_run: payload.requires_setup,
                };
                Ok(ReduceOutcome::Changed)
            }
            Message::AuthResult(payload) => {
                let SessionPhase::AwaitingAuthResult { first_run } = self.phase else {
                    return Err(self.fail_closed("state", "Authentication result is out of order."));
                };
                self.clear_auth();
                if payload.success {
                    self.auth_feedback = AuthFeedback::None;
                    self.access = match payload.access_state {
                        WireAccessState::Viewer => AccessState::Viewer,
                        WireAccessState::Controller => {
                            return Err(self.fail_closed(
                                "auth-result",
                                "Authentication cannot grant controller authority.",
                            ));
                        }
                        WireAccessState::Locked => {
                            return Err(self.fail_closed(
                                "auth-result",
                                "Successful authentication returned a locked role.",
                            ));
                        }
                    };
                    self.phase = SessionPhase::Authenticated;
                    self.lease_pending = false;
                    self.snapshot = None;
                    self.awaiting_snapshot = true;
                    Ok(ReduceOutcome::RequestSnapshot)
                } else {
                    if payload.access_state != WireAccessState::Locked {
                        return Err(self.fail_closed(
                            "auth-result",
                            "Failed authentication returned an unlocked role.",
                        ));
                    }
                    self.access = if first_run {
                        AccessState::FirstRun
                    } else {
                        AccessState::Locked
                    };
                    self.auth_feedback = AuthFeedback::Failed;
                    self.phase = SessionPhase::AwaitingAuth { first_run };
                    self.awaiting_snapshot = false;
                    Ok(ReduceOutcome::Changed)
                }
            }
            Message::LeaseResult(payload) => {
                if self.phase != SessionPhase::Authenticated || !self.lease_pending {
                    return Err(self.fail_closed("state", "Lease result is out of order."));
                }
                self.lease_pending = false;
                let access = match payload.status {
                    LeaseStatus::Controller | LeaseStatus::Transferred => AccessState::Controller,
                    LeaseStatus::Viewer | LeaseStatus::LeaseHeld => AccessState::Viewer,
                };
                let outcome = if self.access == access {
                    ReduceOutcome::Ignored
                } else {
                    ReduceOutcome::Changed
                };
                self.access = access;
                Ok(outcome)
            }
            Message::Snapshot(payload) => {
                if self.phase != SessionPhase::Authenticated || !self.access.is_unlocked() {
                    return Err(
                        self.fail_closed("state", "Snapshot arrived before authentication.")
                    );
                }
                if payload.snapshot.shell.state_version != envelope.state_version {
                    return Err(self.fail_closed("state-version", "Snapshot version is invalid."));
                }
                if envelope.state_version < self.state_version {
                    if self.awaiting_snapshot {
                        return Err(self
                            .fail_closed("state-version", "Resynchronization snapshot is stale."));
                    }
                    return Ok(ReduceOutcome::Ignored);
                }
                if envelope.state_version == self.state_version
                    && let Some(current) = &self.snapshot
                {
                    if current == &payload.snapshot {
                        self.awaiting_snapshot = false;
                        return Ok(ReduceOutcome::Ignored);
                    }
                    return Err(self.fail_closed(
                        "state-version",
                        "Equal snapshot versions contain different state.",
                    ));
                }
                self.state_version = envelope.state_version;
                self.snapshot = Some(payload.snapshot);
                self.awaiting_snapshot = false;
                Ok(ReduceOutcome::Changed)
            }
            Message::Event(_) => {
                if self.phase != SessionPhase::Authenticated || !self.access.is_unlocked() {
                    return Err(self.fail_closed("state", "Event arrived before authentication."));
                }
                self.state_version = self.state_version.max(envelope.state_version);
                self.snapshot = None;
                self.awaiting_snapshot = true;
                Ok(ReduceOutcome::RequestSnapshot)
            }
            Message::LockResult(_) => {
                if self.phase != SessionPhase::Authenticated || !self.lock_pending {
                    return Err(self.fail_closed("state", "Lock result is out of order."));
                }
                self.enter_manual_lock();
                Ok(ReduceOutcome::Changed)
            }
            Message::ProtocolError(payload) => {
                let error = ProtocolError {
                    code: payload.code.as_str().to_owned(),
                    safe_message: payload.safe_message.as_str().to_owned(),
                };
                self.enter_protocol_lockout();
                Err(error)
            }
            Message::Pong(_) => {
                if self.phase != SessionPhase::Authenticated {
                    return Err(self.fail_closed("state", "Pong arrived before authentication."));
                }
                Ok(ReduceOutcome::Ignored)
            }
            Message::ClientHello(_)
            | Message::AuthSetup(_)
            | Message::AuthUnlock(_)
            | Message::LeaseRequest(_)
            | Message::LockRequest(_)
            | Message::SnapshotRequest(_)
            | Message::Ping(_) => {
                Err(self.fail_closed("direction", "Server message direction is invalid."))
            }
        }
    }

    pub fn handle(&mut self, event: InputEvent) -> Vec<ClientAction> {
        let before = self.view_key();
        let actions = self.handle_inner(event);
        if self.view_key() != before {
            self.dirty = true;
        }
        actions
    }

    fn handle_inner(&mut self, event: InputEvent) -> Vec<ClientAction> {
        if event == InputEvent::CloseTui {
            return vec![ClientAction::CloseTui];
        }
        if self.phase == SessionPhase::ProtocolLockout {
            return match event {
                InputEvent::Char('q') => vec![ClientAction::CloseTui],
                InputEvent::Reconnect => vec![ClientAction::Reconnect],
                _ => Vec::new(),
            };
        }
        if matches!(event, InputEvent::Tick(_)) {
            return Vec::new();
        }
        if !self.access.is_unlocked() {
            return if matches!(self.phase, SessionPhase::AwaitingAuth { .. }) {
                self.handle_auth(event)
            } else {
                Vec::new()
            };
        }

        match event {
            InputEvent::TakeControl
                if self.access == AccessState::Viewer && !self.lease_pending =>
            {
                self.lease_pending = true;
                return vec![ClientAction::RequestLease];
            }
            InputEvent::LockTui if !self.lock_pending => {
                self.begin_manual_lock();
                return vec![ClientAction::RequestLock];
            }
            InputEvent::TakeControl | InputEvent::LockTui => return Vec::new(),
            _ => {}
        }

        self.route_unlocked_input(event)
    }

    pub fn take_dirty(&mut self) -> bool {
        std::mem::take(&mut self.dirty)
    }

    pub fn mark_dirty(&mut self) {
        self.dirty = true;
    }

    pub fn fail_connection(&mut self) {
        self.enter_protocol_lockout();
        self.dirty = true;
    }

    fn view_key(&self) -> ViewKey {
        ViewKey {
            access: self.access,
            screen: self.screen,
            mode: self.mode,
            snapshot_version: self
                .snapshot
                .as_ref()
                .map(|snapshot| snapshot.shell.state_version),
            auth_stage: self.auth_stage,
            password_characters: self.password.0.chars().count(),
            confirmation_characters: self.confirmation.0.chars().count(),
            auth_feedback: self.auth_feedback,
            local_input: self.local_input.clone(),
            state_version: self.state_version,
            awaiting_snapshot: self.awaiting_snapshot,
            lock_pending: self.lock_pending,
            lease_pending: self.lease_pending,
            phase: self.phase,
            theme: self.theme(),
            display_mode: self.display_mode(),
            preferences_unavailable: self.preferences_unavailable,
        }
    }

    fn handle_auth(&mut self, event: InputEvent) -> Vec<ClientAction> {
        match event {
            InputEvent::Char(character) => {
                self.auth_feedback = AuthFeedback::None;
                match self.auth_stage {
                    AuthStage::Password => self.password.push(character),
                    AuthStage::Confirmation => self.confirmation.push(character),
                }
            }
            InputEvent::Backspace => {
                self.auth_feedback = AuthFeedback::None;
                match self.auth_stage {
                    AuthStage::Password => self.password.pop(),
                    AuthStage::Confirmation => self.confirmation.pop(),
                }
            }
            InputEvent::Escape => {
                self.auth_feedback = AuthFeedback::None;
                if self.auth_stage == AuthStage::Confirmation {
                    self.confirmation.clear();
                    self.auth_stage = AuthStage::Password;
                } else {
                    self.password.clear();
                }
            }
            InputEvent::Enter if self.access == AccessState::FirstRun => {
                if self.auth_stage == AuthStage::Password {
                    if !self.password.is_empty() {
                        self.auth_stage = AuthStage::Confirmation;
                    }
                } else if !self.confirmation.is_empty() {
                    if !self.password.matches(&self.confirmation) {
                        self.confirmation.clear();
                        self.auth_feedback = AuthFeedback::PasswordMismatch;
                    } else if let (Some(password), Some(confirmation)) = (
                        self.password.take_password(),
                        self.confirmation.take_password(),
                    ) {
                        self.auth_stage = AuthStage::Password;
                        self.auth_feedback = AuthFeedback::Pending;
                        self.phase = SessionPhase::AwaitingAuthResult { first_run: true };
                        return vec![ClientAction::Authenticate(AuthRequest::Setup {
                            password,
                            confirmation,
                        })];
                    }
                }
            }
            InputEvent::Enter if !self.password.is_empty() => {
                if let Some(password) = self.password.take_password() {
                    self.auth_feedback = AuthFeedback::Pending;
                    self.phase = SessionPhase::AwaitingAuthResult { first_run: false };
                    return vec![ClientAction::Authenticate(AuthRequest::Unlock { password })];
                }
            }
            _ => {}
        }
        Vec::new()
    }

    fn route_unlocked_input(&mut self, event: InputEvent) -> Vec<ClientAction> {
        if event == InputEvent::Escape {
            self.mode = LocalMode::Browse;
            self.local_input.clear();
            return Vec::new();
        }

        if self.mode.captures_text() {
            return match event {
                InputEvent::Char(character) => {
                    self.local_input.push(character);
                    Vec::new()
                }
                InputEvent::Backspace => {
                    self.local_input.pop();
                    Vec::new()
                }
                InputEvent::Enter if self.mode == LocalMode::AgentInput => {
                    let input = std::mem::take(&mut self.local_input);
                    if input.is_empty() {
                        Vec::new()
                    } else {
                        vec![ClientAction::SubmitInput(input)]
                    }
                }
                _ => Vec::new(),
            };
        }

        let InputEvent::Char(key) = event else {
            return Vec::new();
        };
        match key {
            '1' => self.screen = Screen::Impact,
            '2' => self.screen = Screen::Portfolio,
            '3' => self.screen = Screen::Orders,
            '4' => self.screen = Screen::Agents,
            '5' => self.screen = Screen::ModelsRegime,
            '6' => self.screen = Screen::Timeline,
            '7' => self.screen = Screen::RiskApprovals,
            '8' => self.screen = Screen::DataEvidence,
            '9' => self.screen = Screen::Memory,
            '0' => self.screen = Screen::System,
            'o' => self.mode = LocalMode::Open,
            '/' => self.mode = LocalMode::Search,
            'f' => self.mode = LocalMode::Filter,
            ':' => self.mode = LocalMode::Menu,
            '?' => self.mode = LocalMode::Help,
            'i' => self.mode = LocalMode::AgentInput,
            'q' => return vec![ClientAction::CloseTui],
            _ => {}
        }
        Vec::new()
    }

    fn clear_auth(&mut self) {
        self.auth_stage = AuthStage::Password;
        self.password.clear();
        self.confirmation.clear();
        self.auth_feedback = AuthFeedback::None;
    }

    fn begin_manual_lock(&mut self) {
        self.access = AccessState::Locked;
        self.snapshot = None;
        self.mode = LocalMode::Browse;
        self.clear_auth();
        self.local_input.clear();
        self.lock_pending = true;
    }

    fn enter_manual_lock(&mut self) {
        self.access = AccessState::Locked;
        self.phase = SessionPhase::AwaitingAuth { first_run: false };
        self.snapshot = None;
        self.mode = LocalMode::Browse;
        self.clear_auth();
        self.local_input.clear();
        self.awaiting_snapshot = false;
        self.lock_pending = false;
        self.lease_pending = false;
    }

    fn enter_protocol_lockout(&mut self) {
        self.access = AccessState::ProtocolLockout;
        self.phase = SessionPhase::ProtocolLockout;
        self.snapshot = None;
        self.mode = LocalMode::Browse;
        self.clear_auth();
        self.local_input.clear();
        self.awaiting_snapshot = false;
        self.lock_pending = false;
        self.lease_pending = false;
    }

    fn fail_closed(&mut self, code: &str, safe_message: &str) -> ProtocolError {
        self.enter_protocol_lockout();
        ProtocolError {
            code: code.to_owned(),
            safe_message: safe_message.to_owned(),
        }
    }
}
