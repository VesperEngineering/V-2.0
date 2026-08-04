use std::collections::BTreeMap;
use std::fmt;
use std::time::Instant;

use ratatui::layout::Rect;

use crate::command::{CommandDraft, CommandTracker, PrepareOutcome, TrackedCommandSummary};
use crate::confirm::{Selection, begin_confirmation, submit_confirmation};
use crate::contract::{
    AccessState as WireAccessState, AgentStage, CommandReceipt, CommandRequest, CommandType,
    ConsoleSnapshot, Envelope, Freshness, LeaseStatus, MemoryStatus, Message, PasswordString,
    SearchRequestPayload,
};
use crate::controls::{
    AgentEnqueueForm, AgentRouteDraft, ButtonState, ControlButton, ControlContext, ControlMenu,
    ControlMenuEntry, ControlOverlay, LocalControl, ReasonForm, build_control_menu,
};
use crate::detail::detail_area;
use crate::input::InputEvent;
use crate::layout::{DisplayMode, shell_layout};
use crate::preferences::{LoadedPreferences, ScreenId, ScreenPreferences, UiPreferences};
use crate::reducer::{EventEnvelope, ReduceOutcome as SnapshotReduceOutcome, SnapshotReducer};
use crate::screens::{DetailKind, PerformancePeriod, ScreenState};
use crate::search::{
    ContextNoteDraft, NoteVisibility, SEARCH_DEBOUNCE, SearchResponseDisposition, SearchResult,
    SearchState, format_filter_expression, parse_filter_expression,
};
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
    NoteEditor,
}

impl LocalMode {
    fn captures_text(self) -> bool {
        matches!(
            self,
            Self::Search | Self::Filter | Self::Menu | Self::AgentInput | Self::NoteEditor
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

#[derive(Debug, PartialEq)]
pub enum ClientAction {
    Authenticate(AuthRequest),
    RequestLease,
    RequestLock,
    RequestSnapshot,
    Search(SearchRequestPayload),
    Command(CommandRequest),
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
    screen_state: ScreenState,
    search_state: SearchState,
    filter_error: Option<String>,
    note_visibility: NoteVisibility,
    pending_note: Option<ContextNoteDraft>,
    show_search_detail: bool,
    search_return_screen: Option<Screen>,
    control_epoch: u64,
}

struct ReceiptSequenceEvidence(CommandReceipt);

impl fmt::Debug for ReceiptSequenceEvidence {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("<redacted receipt sequence evidence>")
    }
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
    screen_state: ScreenState,
    snapshot_reducer: SnapshotReducer,
    search_state: SearchState,
    local_now: Instant,
    filter_error: Option<String>,
    note_visibility: NoteVisibility,
    pending_note: Option<ContextNoteDraft>,
    show_search_detail: bool,
    search_return_screen: Option<Screen>,
    detail_viewport: Option<Rect>,
    control_overlay: Option<ControlOverlay>,
    note_command: Option<ControlButton>,
    command_tracker: CommandTracker,
    receipt_sequence_evidence: BTreeMap<u64, ReceiptSequenceEvidence>,
    control_epoch: u64,
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
            screen_state: ScreenState::default(),
            snapshot_reducer: SnapshotReducer::default(),
            search_state: SearchState::default(),
            local_now: Instant::now(),
            filter_error: None,
            note_visibility: NoteVisibility::Private,
            pending_note: None,
            show_search_detail: false,
            search_return_screen: None,
            detail_viewport: None,
            control_overlay: None,
            note_command: None,
            command_tracker: CommandTracker::default(),
            receipt_sequence_evidence: BTreeMap::new(),
            control_epoch: 0,
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

    pub fn set_terminal_area(&mut self, area: Rect) {
        let shell_body = shell_layout(area, self.display_mode()).body;
        let viewport = if self.snapshot.is_some()
            && self.search_detail().is_none()
            && matches!(
                self.mode,
                LocalMode::Browse | LocalMode::Open | LocalMode::Menu
            ) {
            crate::ui::split_control_area(shell_body, self.display_mode()).0
        } else {
            shell_body
        };
        if self.detail_viewport != Some(viewport) {
            self.detail_viewport = Some(viewport);
            if self.mode == LocalMode::Open && self.screen_state.detail_open {
                self.screen_state.scroll_offset = self
                    .screen_state
                    .scroll_offset
                    .min(self.detail_scroll_maximum());
            }
            self.dirty = true;
        }
    }

    pub fn screen_state(&self) -> ScreenState {
        let mut state = self.screen_state.clone();
        state.theme = self.theme();
        state.display_mode = self.display_mode();
        state.mask_account_details = self.preferences.mask_account_details;
        state
    }

    pub fn search_state(&self) -> &SearchState {
        &self.search_state
    }

    pub fn search_detail(&self) -> Option<&SearchResult> {
        if self.mode != LocalMode::Open || !self.show_search_detail {
            return None;
        }
        let entity_id = self.screen_state.selected_id.as_deref()?;
        let detail_kind = self.screen_state.selected_kind?;
        self.search_state
            .result_for(self.screen, detail_kind, entity_id)
    }

    pub fn filter_input(&self) -> &str {
        &self.local_input
    }

    pub fn filter_error(&self) -> Option<&str> {
        self.filter_error.as_deref()
    }

    pub fn note_visibility(&self) -> NoteVisibility {
        self.note_visibility
    }

    pub fn pending_note(&self) -> Option<&ContextNoteDraft> {
        self.pending_note.as_ref()
    }

    pub fn note_editor_target(&self) -> Option<(&'static str, &str)> {
        self.current_note_target()
    }

    pub fn note_input(&self) -> &str {
        &self.local_input
    }

    pub fn set_performance_period(&mut self, period: PerformancePeriod) {
        if self.screen_state.performance_period != period {
            self.screen_state.performance_period = period;
            self.preferences
                .screens
                .entry(ScreenId::Portfolio)
                .or_default()
                .performance_period = Some(period);
            self.preferences_save_pending = true;
            self.dirty = true;
        }
    }

    pub fn preferences(&self) -> &UiPreferences {
        &self.preferences
    }

    pub fn preferences_unavailable(&self) -> bool {
        self.preferences_unavailable
    }

    pub fn control_overlay(&self) -> Option<&ControlOverlay> {
        self.control_overlay.as_ref()
    }

    pub fn control_menu(&self) -> Option<&ControlMenu> {
        match self.control_overlay.as_ref() {
            Some(ControlOverlay::Menu(menu)) => Some(menu),
            _ => None,
        }
    }

    pub fn visible_control_menu(&self) -> Option<ControlMenu> {
        let snapshot = self.snapshot.as_ref()?;
        Some(build_control_menu(
            snapshot,
            self.access,
            self.screen,
            self.screen_state.selected_kind,
            self.screen_state.selected_id.as_deref(),
        ))
    }

    pub fn command_summaries(&self) -> Vec<TrackedCommandSummary> {
        self.command_tracker.summaries()
    }

    pub fn apply_loaded_preferences(&mut self, loaded: LoadedPreferences) {
        self.preferences = loaded.preferences;
        self.screen_state.performance_period = self
            .preferences
            .screens
            .get(&ScreenId::Portfolio)
            .and_then(|preferences| preferences.performance_period)
            .unwrap_or_default();
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

    pub fn toggle_account_details_mask(&mut self) {
        self.preferences.mask_account_details = !self.preferences.mask_account_details;
        self.preferences_save_pending = true;
        self.dirty = true;
    }

    pub fn set_screen_preferences(&mut self, screen: ScreenId, mut preferences: ScreenPreferences) {
        if screen == ScreenId::Portfolio {
            if let Some(period) = preferences.performance_period {
                self.screen_state.performance_period = period;
            } else {
                preferences.performance_period = self
                    .preferences
                    .screens
                    .get(&screen)
                    .and_then(|current| current.performance_period);
            }
        }
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
        if let Message::CommandReceipt(payload) = &envelope.message
            && let Some(previous) = self.receipt_sequence_evidence.get(&envelope.sequence)
        {
            if previous.0 == payload.receipt {
                return Ok(ReduceOutcome::Ignored);
            }
            return Err(self.fail_closed(
                "command-receipt",
                "Duplicate receipt sequence differs from the reduced receipt.",
            ));
        }
        let Some(expected_sequence) = self.last_sequence.checked_add(1) else {
            return Err(self.fail_closed("sequence", "Server sequence is exhausted."));
        };
        if envelope.sequence < expected_sequence {
            if matches!(&envelope.message, Message::CommandReceipt(_)) {
                return Err(self.fail_closed(
                    "command-receipt",
                    "Duplicate receipt sequence has no exact reduced evidence.",
                ));
            }
            return Ok(ReduceOutcome::Ignored);
        }
        if envelope.sequence != expected_sequence {
            self.last_sequence = envelope.sequence;
            if self.snapshot_reducer.state_opt().is_some() {
                let _ = self.snapshot_reducer.observe_sequence(envelope.sequence);
            }
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
                Message::Snapshot(_)
                | Message::SearchResults(_)
                | Message::Event(_)
                | Message::Pong(_) => {
                    self.cancel_unsent_controls_for_resync();
                    self.awaiting_snapshot = true;
                    self.snapshot = None;
                    self.search_state.clear_results();
                    Ok(ReduceOutcome::RequestSnapshot)
                }
                _ => Err(self.fail_closed(
                    "sequence",
                    "Message sequence gap cannot be recovered by a presentation snapshot.",
                )),
            };
        }
        self.last_sequence = envelope.sequence;

        if (self.lock_pending || matches!(self.phase, SessionPhase::AwaitingAuth { .. }))
            && let Message::CommandReceipt(payload) = &envelope.message
        {
            let receipt = payload.receipt.clone();
            if self.command_tracker.apply_receipt(receipt.clone()).is_err() {
                return Err(self.fail_closed(
                    "command-receipt",
                    "Command receipt does not match an in-flight command.",
                ));
            }
            self.receipt_sequence_evidence
                .insert(envelope.sequence, ReceiptSequenceEvidence(receipt));
            self.control_epoch = self.control_epoch.saturating_add(1);
            return Ok(ReduceOutcome::Changed);
        }

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
                Message::SearchResults(payload) => {
                    let request_id = payload.request_id.get();
                    if envelope.state_version != payload.indexed_state_version {
                        return Err(
                            self.fail_closed("state-version", "Search result version is invalid.")
                        );
                    }
                    if self.search_state.response_disposition(request_id)
                        == SearchResponseDisposition::Unknown
                    {
                        return Err(self.fail_closed(
                            "search-request",
                            "Search result request ID was not issued.",
                        ));
                    }
                    self.search_state.complete_without_results(request_id);
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
                    self.snapshot_reducer = SnapshotReducer::default();
                    self.search_state.clear_results();
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
                self.observe_presentation_sequence(envelope.sequence)?;
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
                    self.observe_presentation_sequence(envelope.sequence)?;
                    return Ok(ReduceOutcome::Ignored);
                }
                let outcome = self.snapshot_reducer.apply_snapshot(payload.snapshot);
                if outcome == SnapshotReduceOutcome::ResnapshotRequired {
                    return Err(self.fail_closed(
                        "state-version",
                        "Snapshot cannot safely replace current presentation state.",
                    ));
                }
                if self
                    .snapshot_reducer
                    .observe_sequence(envelope.sequence)
                    .is_err()
                {
                    return Err(self.fail_closed(
                        "sequence",
                        "Snapshot sequence cannot rebase presentation state.",
                    ));
                }
                let reduced = self.snapshot_reducer.state();
                self.state_version = reduced.snapshot.shell.state_version;
                let snapshot = reduced.snapshot.clone();
                self.snapshot = Some(snapshot);
                self.invalidate_stale_control_review();
                if outcome == SnapshotReduceOutcome::Changed {
                    self.invalidate_search_results();
                }
                self.show_search_detail = false;
                self.awaiting_snapshot = false;
                Ok(match outcome {
                    SnapshotReduceOutcome::Changed => ReduceOutcome::Changed,
                    SnapshotReduceOutcome::Ignored => ReduceOutcome::Ignored,
                    SnapshotReduceOutcome::ResnapshotRequired => unreachable!("handled above"),
                })
            }
            Message::Event(payload) => {
                if self.phase != SessionPhase::Authenticated || !self.access.is_unlocked() {
                    return Err(self.fail_closed("state", "Event arrived before authentication."));
                }
                let event = EventEnvelope {
                    sequence: envelope.sequence,
                    state_version: envelope.state_version,
                    payload: *payload,
                };
                match self.snapshot_reducer.apply_event(event) {
                    Ok(SnapshotReduceOutcome::Changed) => {
                        let reduced = self.snapshot_reducer.state();
                        self.state_version = reduced.snapshot.shell.state_version;
                        let snapshot = reduced.snapshot.clone();
                        self.snapshot = Some(snapshot);
                        self.invalidate_stale_control_review();
                        self.invalidate_search_results();
                        self.show_search_detail = false;
                        self.awaiting_snapshot = false;
                        Ok(ReduceOutcome::Changed)
                    }
                    Ok(SnapshotReduceOutcome::Ignored) => Ok(ReduceOutcome::Ignored),
                    Ok(SnapshotReduceOutcome::ResnapshotRequired) | Err(_) => {
                        self.cancel_unsent_controls_for_resync();
                        self.snapshot = None;
                        self.search_state.clear_results();
                        self.awaiting_snapshot = true;
                        Ok(ReduceOutcome::RequestSnapshot)
                    }
                }
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
                self.observe_presentation_sequence(envelope.sequence)?;
                Ok(ReduceOutcome::Ignored)
            }
            Message::SearchResults(payload) => {
                if self.phase != SessionPhase::Authenticated || !self.access.is_unlocked() {
                    return Err(
                        self.fail_closed("state", "Search results arrived before authentication.")
                    );
                }
                let request_id = payload.request_id.get();
                if envelope.state_version != payload.indexed_state_version {
                    return Err(
                        self.fail_closed("state-version", "Search result version is invalid.")
                    );
                }
                let disposition = self.search_state.response_disposition(request_id);
                if disposition == SearchResponseDisposition::Unknown {
                    return Err(self.fail_closed(
                        "search-request",
                        "Search result request ID was not issued.",
                    ));
                }
                self.observe_presentation_sequence(envelope.sequence)?;
                if disposition == SearchResponseDisposition::Superseded {
                    self.search_state.complete_without_results(request_id);
                    return Ok(ReduceOutcome::Ignored);
                }
                if payload.indexed_state_version < self.state_version {
                    self.search_state.complete_without_results(request_id);
                    self.search_state.invalidate_for_refresh(self.local_now);
                    self.show_search_detail = false;
                    return Ok(ReduceOutcome::Changed);
                }
                if payload.indexed_state_version > self.state_version {
                    self.search_state.await_resnapshot(request_id);
                    self.cancel_unsent_controls_for_resync();
                    self.snapshot = None;
                    self.show_search_detail = false;
                    self.awaiting_snapshot = true;
                    return Ok(ReduceOutcome::RequestSnapshot);
                }
                let mut rows = Vec::with_capacity(payload.results.len());
                for result in payload.results {
                    match SearchResult::try_from(result) {
                        Ok(result) => rows.push(result),
                        Err(_) => {
                            self.search_state.apply_gateway_results(
                                request_id,
                                Vec::new(),
                                Some("Search results were rejected.".to_owned()),
                            );
                            self.show_search_detail = false;
                            return Ok(ReduceOutcome::Changed);
                        }
                    }
                }
                let error = payload.error.map(|value| value.as_str().to_owned());
                if self
                    .search_state
                    .apply_gateway_results(request_id, rows, error)
                {
                    Ok(ReduceOutcome::Changed)
                } else {
                    Ok(ReduceOutcome::Ignored)
                }
            }
            Message::CommandReceipt(payload) => {
                if self.phase != SessionPhase::Authenticated || !self.access.is_unlocked() {
                    return Err(
                        self.fail_closed("state", "Command receipt arrived before authentication.")
                    );
                }
                self.observe_presentation_sequence(envelope.sequence)?;
                let receipt = payload.receipt;
                if self.command_tracker.apply_receipt(receipt.clone()).is_err() {
                    return Err(self.fail_closed(
                        "command-receipt",
                        "Command receipt does not match an in-flight command.",
                    ));
                }
                self.receipt_sequence_evidence
                    .insert(envelope.sequence, ReceiptSequenceEvidence(receipt));
                self.control_epoch = self.control_epoch.saturating_add(1);
                Ok(ReduceOutcome::Changed)
            }
            Message::ClientHello(_)
            | Message::AuthSetup(_)
            | Message::AuthUnlock(_)
            | Message::LeaseRequest(_)
            | Message::LockRequest(_)
            | Message::SnapshotRequest(_)
            | Message::SearchRequest(_)
            | Message::Command(_)
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
        if let InputEvent::Tick(elapsed) = event {
            self.local_now = self
                .local_now
                .checked_add(elapsed)
                .or_else(|| self.local_now.checked_add(SEARCH_DEBOUNCE))
                .unwrap_or(self.local_now);
            if self.access.is_unlocked()
                && self.mode == LocalMode::Search
                && let Some(request) = self.search_state.take_due_request(self.local_now)
            {
                let request_id = request.request_id;
                return match request.to_wire() {
                    Ok(payload) => vec![ClientAction::Search(payload)],
                    Err(error) => {
                        self.search_state.apply_gateway_results(
                            request_id,
                            Vec::new(),
                            Some(error.to_string()),
                        );
                        Vec::new()
                    }
                };
            }
            return Vec::new();
        }
        if !self.access.is_unlocked() {
            return if matches!(self.phase, SessionPhase::AwaitingAuth { .. }) {
                self.handle_auth(event)
            } else {
                Vec::new()
            };
        }
        if self.control_overlay.is_some() {
            return self.handle_control_input(event);
        }

        match event {
            InputEvent::ActivateControl(index) => {
                self.open_control_menu();
                return self.activate_control(index);
            }
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

    pub(crate) fn begin_connection(&mut self) {
        self.access = AccessState::Locked;
        self.phase = SessionPhase::AwaitingServerHello;
        self.snapshot = None;
        self.snapshot_reducer = SnapshotReducer::default();
        self.search_state = SearchState::default();
        self.state_version = 0;
        self.last_sequence = 0;
        self.receipt_sequence_evidence.clear();
        self.awaiting_snapshot = false;
        self.lock_pending = false;
        self.lease_pending = false;
        self.mode = LocalMode::Browse;
        self.clear_auth();
        self.local_input.clear();
        self.filter_error = None;
        self.pending_note = None;
        self.control_overlay = None;
        self.note_command = None;
        self.command_tracker.cancel_prepared_commands();
        self.show_search_detail = false;
        self.search_return_screen = None;
        self.control_epoch = self.control_epoch.saturating_add(1);
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
            screen_state: self.screen_state.clone(),
            search_state: self.search_state.clone(),
            filter_error: self.filter_error.clone(),
            note_visibility: self.note_visibility,
            pending_note: self.pending_note.clone(),
            show_search_detail: self.show_search_detail,
            search_return_screen: self.search_return_screen,
            control_epoch: self.control_epoch,
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
            if self.mode == LocalMode::NoteEditor {
                self.mode = LocalMode::Open;
                self.local_input.clear();
                self.note_command = None;
            } else if self.mode == LocalMode::Open
                && let Some(search_screen) = self.search_return_screen.take()
            {
                self.screen = search_screen;
                self.mode = LocalMode::Search;
                self.local_input = self.search_state.query().to_owned();
                self.search_state.set_active_screen(search_screen);
                self.show_search_detail = false;
            } else {
                self.mode = LocalMode::Browse;
                self.local_input.clear();
                self.show_search_detail = false;
                self.search_return_screen = None;
            }
            self.filter_error = None;
            if self.mode == LocalMode::Browse {
                self.screen_state.detail_open = false;
            }
            self.screen_state.scroll_offset = 0;
            return Vec::new();
        }

        if self.mode.captures_text() {
            return match event {
                InputEvent::Up if self.mode == LocalMode::Search => {
                    self.search_state.move_selection(false);
                    Vec::new()
                }
                InputEvent::Down if self.mode == LocalMode::Search => {
                    self.search_state.move_selection(true);
                    Vec::new()
                }
                InputEvent::OpenSearchResult(index) if self.mode == LocalMode::Search => {
                    self.search_state.select_index(index);
                    self.open_search_selected();
                    Vec::new()
                }
                InputEvent::Left | InputEvent::Right if self.mode == LocalMode::NoteEditor => {
                    self.note_visibility = match self.note_visibility {
                        NoteVisibility::Private => NoteVisibility::Shared,
                        NoteVisibility::Shared => NoteVisibility::Private,
                    };
                    Vec::new()
                }
                InputEvent::Enter if self.mode == LocalMode::Search => {
                    self.open_search_selected();
                    Vec::new()
                }
                InputEvent::Enter if self.mode == LocalMode::Filter => {
                    match parse_filter_expression(self.screen, &self.local_input) {
                        Ok(filters) => {
                            self.search_state.set_filters(self.screen, filters);
                            self.filter_error = None;
                            self.local_input.clear();
                            self.mode = LocalMode::Browse;
                        }
                        Err(error) => self.filter_error = Some(error.message().to_owned()),
                    }
                    Vec::new()
                }
                InputEvent::Enter if self.mode == LocalMode::NoteEditor => {
                    return self.submit_note();
                }
                InputEvent::Enter if self.mode == LocalMode::AgentInput => {
                    let input = std::mem::take(&mut self.local_input);
                    if input.is_empty() {
                        Vec::new()
                    } else {
                        vec![ClientAction::SubmitInput(input)]
                    }
                }
                InputEvent::Char(character) => {
                    let limit = match self.mode {
                        LocalMode::Search => 256,
                        LocalMode::Filter => 512,
                        LocalMode::NoteEditor | LocalMode::AgentInput => 8_000,
                        _ => 2_000,
                    };
                    if self.local_input.chars().count() < limit {
                        self.local_input.push(character);
                        if self.mode == LocalMode::Search {
                            self.search_state
                                .update_query(self.local_input.clone(), self.local_now);
                        } else if self.mode == LocalMode::Filter {
                            self.filter_error = None;
                        }
                    }
                    Vec::new()
                }
                InputEvent::Backspace => {
                    self.local_input.pop();
                    if self.mode == LocalMode::Search {
                        self.search_state
                            .update_query(self.local_input.clone(), self.local_now);
                    }
                    Vec::new()
                }
                _ => Vec::new(),
            };
        }

        match event {
            InputEvent::OpenBrowseRow { panel, index } => {
                self.open_browse_row(panel, index);
                return Vec::new();
            }
            InputEvent::FocusBrowsePanel { panel } => {
                self.focus_browse_panel(panel);
                return Vec::new();
            }
            InputEvent::Up => {
                self.move_vertical(false);
                return Vec::new();
            }
            InputEvent::Down => {
                self.move_vertical(true);
                return Vec::new();
            }
            InputEvent::Left => {
                self.move_horizontal(false);
                return Vec::new();
            }
            InputEvent::Right => {
                self.move_horizontal(true);
                return Vec::new();
            }
            _ => {}
        }

        let InputEvent::Char(key) = event else {
            return Vec::new();
        };
        match key {
            '1' => self.select_screen(Screen::Impact),
            '2' => self.select_screen(Screen::Portfolio),
            '3' => self.select_screen(Screen::Orders),
            '4' => self.select_screen(Screen::Agents),
            '5' => self.select_screen(Screen::ModelsRegime),
            '6' => self.select_screen(Screen::Timeline),
            '7' => self.select_screen(Screen::RiskApprovals),
            '8' => self.select_screen(Screen::DataEvidence),
            '9' => self.select_screen(Screen::Memory),
            '0' => self.select_screen(Screen::System),
            'p' if self.screen == Screen::System => self.toggle_account_details_mask(),
            'o' => self.open_selected(),
            'n' if self.mode == LocalMode::Open && self.current_note_target().is_some() => {
                self.open_control_menu();
                if let Some(index) = self
                    .control_menu()
                    .and_then(|menu| menu.command_index(CommandType::NoteAdd))
                {
                    return self.activate_control(index);
                }
            }
            'e' if self.screen == Screen::Timeline => {
                self.screen_state.show_all_events = !self.screen_state.show_all_events;
                self.screen_state.scroll_offset = 0;
                self.screen_state.selected_id = None;
                self.screen_state.selected_kind = None;
            }
            '/' => {
                self.mode = LocalMode::Search;
                self.local_input.clear();
                self.show_search_detail = false;
                self.search_return_screen = None;
                self.search_state.set_active_screen(self.screen);
                self.search_state
                    .update_query(String::new(), self.local_now);
            }
            'f' => {
                self.mode = LocalMode::Filter;
                self.local_input = format_filter_expression(self.search_state.filters(self.screen));
                self.filter_error = None;
            }
            ':' => self.open_control_menu(),
            '?' => self.mode = LocalMode::Help,
            'i' => self.mode = LocalMode::AgentInput,
            'q' => return vec![ClientAction::CloseTui],
            _ => {}
        }
        Vec::new()
    }

    fn open_control_menu(&mut self) {
        let Some(snapshot) = self.snapshot.as_ref() else {
            return;
        };
        self.control_overlay = Some(ControlOverlay::Menu(build_control_menu(
            snapshot,
            self.access,
            self.screen,
            self.screen_state.selected_kind,
            self.screen_state.selected_id.as_deref(),
        )));
        self.mode = LocalMode::Menu;
        self.control_epoch = self.control_epoch.saturating_add(1);
    }

    fn handle_control_input(&mut self, event: InputEvent) -> Vec<ClientAction> {
        if event == InputEvent::CancelControl {
            return self.handle_control_input(InputEvent::Escape);
        }
        if event == InputEvent::ConfirmControl {
            return match self.control_overlay.as_ref() {
                Some(ControlOverlay::Confirmation { .. }) => {
                    self.select_confirmation(Selection::Confirm);
                    self.accept_confirmation()
                }
                Some(ControlOverlay::ReasonForm(_)) => self.submit_reason_form(),
                Some(ControlOverlay::AgentEnqueueForm(_)) => self.submit_agent_form(),
                Some(ControlOverlay::DisabledReason { .. }) => {
                    self.close_control_overlay();
                    Vec::new()
                }
                Some(ControlOverlay::Menu(_)) | None => Vec::new(),
            };
        }
        match self.control_overlay.clone() {
            Some(ControlOverlay::Menu(_)) => match event {
                InputEvent::Escape => self.close_control_overlay(),
                InputEvent::Up => self.move_control_selection(false),
                InputEvent::Down => self.move_control_selection(true),
                InputEvent::ActivateControl(index) => return self.activate_control(index),
                InputEvent::Enter => {
                    if let Some(index) = self.control_menu().map(ControlMenu::selected) {
                        return self.activate_control(index);
                    }
                }
                _ => {}
            },
            Some(ControlOverlay::DisabledReason { .. }) => {
                if matches!(event, InputEvent::Escape | InputEvent::Enter) {
                    self.close_control_overlay();
                }
            }
            Some(ControlOverlay::ReasonForm(_)) => match event {
                InputEvent::Escape => self.close_control_overlay(),
                InputEvent::Up | InputEvent::Left => self.move_reason_selection(false),
                InputEvent::Down | InputEvent::Right => self.move_reason_selection(true),
                InputEvent::Char(character) => self.push_reason_note(character),
                InputEvent::Backspace => self.pop_reason_note(),
                InputEvent::Enter => return self.submit_reason_form(),
                _ => {}
            },
            Some(ControlOverlay::AgentEnqueueForm(_)) => match event {
                InputEvent::Escape => self.close_control_overlay(),
                InputEvent::Left => self.cycle_agent_route(false),
                InputEvent::Right => self.cycle_agent_route(true),
                InputEvent::Up => self.change_agent_priority(true),
                InputEvent::Down => self.change_agent_priority(false),
                InputEvent::Char(character) => self.push_agent_objective(character),
                InputEvent::Backspace => self.pop_agent_objective(),
                InputEvent::Enter => return self.submit_agent_form(),
                _ => {}
            },
            Some(ControlOverlay::Confirmation { .. }) => match event {
                InputEvent::Escape => {
                    if let Some(ControlOverlay::Confirmation { state, .. }) =
                        self.control_overlay.as_ref()
                    {
                        let command_id = state.pending().request().command_id.as_str().to_owned();
                        self.command_tracker.cancel_prepared(&command_id);
                    }
                    self.close_control_overlay();
                }
                InputEvent::Left => self.select_confirmation(Selection::Cancel),
                InputEvent::Right => self.select_confirmation(Selection::Confirm),
                InputEvent::Char(character) => {
                    if let Some(ControlOverlay::Confirmation { state, .. }) =
                        self.control_overlay.as_mut()
                    {
                        state.push_typed_character(character);
                        self.control_epoch = self.control_epoch.saturating_add(1);
                    }
                }
                InputEvent::Backspace => {
                    if let Some(ControlOverlay::Confirmation { state, .. }) =
                        self.control_overlay.as_mut()
                    {
                        state.pop_typed_character();
                        self.control_epoch = self.control_epoch.saturating_add(1);
                    }
                }
                InputEvent::Enter => return self.accept_confirmation(),
                _ => {}
            },
            None => {}
        }
        Vec::new()
    }

    fn close_control_overlay(&mut self) {
        self.control_overlay = None;
        if self.mode == LocalMode::Menu {
            self.mode = LocalMode::Browse;
        }
        self.control_epoch = self.control_epoch.saturating_add(1);
    }

    fn move_control_selection(&mut self, forward: bool) {
        if let Some(ControlOverlay::Menu(menu)) = self.control_overlay.as_mut() {
            menu.move_selection(forward);
            self.control_epoch = self.control_epoch.saturating_add(1);
        }
    }

    fn select_confirmation(&mut self, selection: Selection) {
        if let Some(ControlOverlay::Confirmation { state, .. }) = self.control_overlay.as_mut() {
            state.select(selection);
            self.control_epoch = self.control_epoch.saturating_add(1);
        }
    }

    fn activate_control(&mut self, index: usize) -> Vec<ClientAction> {
        let Some(ControlOverlay::Menu(menu)) = self.control_overlay.as_mut() else {
            return Vec::new();
        };
        menu.select(index);
        let Some(entry) = menu.selected_entry().cloned() else {
            return Vec::new();
        };
        match entry {
            ControlMenuEntry::Local { control, .. } => self.activate_local_control(control),
            ControlMenuEntry::Command(button) => match button.state {
                ButtonState::Disabled { reason } => {
                    self.control_overlay = Some(ControlOverlay::DisabledReason {
                        label: button.label,
                        reason,
                    });
                    self.control_epoch = self.control_epoch.saturating_add(1);
                    Vec::new()
                }
                ButtonState::Hidden => Vec::new(),
                ButtonState::Enabled => self.begin_command(button),
            },
        }
    }

    fn activate_local_control(&mut self, control: LocalControl) -> Vec<ClientAction> {
        match control {
            LocalControl::TakeControl
                if self.access == AccessState::Viewer && !self.lease_pending =>
            {
                self.close_control_overlay();
                self.lease_pending = true;
                vec![ClientAction::RequestLease]
            }
            LocalControl::LockTui if !self.lock_pending => {
                self.begin_manual_lock();
                vec![ClientAction::RequestLock]
            }
            LocalControl::ToggleAccountPrivacy => {
                self.close_control_overlay();
                self.toggle_account_details_mask();
                Vec::new()
            }
            LocalControl::OpenCandidateDetail => {
                self.close_control_overlay();
                self.open_selected();
                Vec::new()
            }
            LocalControl::TakeControl | LocalControl::LockTui => Vec::new(),
        }
    }

    fn begin_command(&mut self, button: crate::controls::ControlButton) -> Vec<ClientAction> {
        if button.command_type == CommandType::NoteAdd {
            if !matches!(button.context.as_ref(), Some(ControlContext::Note { .. })) {
                self.control_overlay = Some(ControlOverlay::DisabledReason {
                    label: button.label,
                    reason: "Select an exact stock, order, approval, or timeline event first."
                        .to_owned(),
                });
                self.control_epoch = self.control_epoch.saturating_add(1);
                return Vec::new();
            }
            if !self.control_pair_matches(&button) {
                return self.reject_stale_control(button.label);
            }
            self.close_control_overlay();
            self.note_command = Some(button);
            self.mode = LocalMode::NoteEditor;
            self.local_input.clear();
            self.note_visibility = NoteVisibility::Private;
            return Vec::new();
        }
        if !self.control_pair_matches(&button) {
            return self.reject_stale_control(button.label);
        }
        if matches!(
            button.command_type,
            CommandType::ApprovalHold | CommandType::ApprovalReject
        ) {
            return self.open_reason_form(button);
        }
        if button.command_type == CommandType::AgentEnqueue {
            self.control_overlay = Some(ControlOverlay::AgentEnqueueForm(AgentEnqueueForm {
                button,
                route: AgentRouteDraft::for_screen(self.screen),
                objective: String::new(),
                priority: 50,
            }));
            self.control_epoch = self.control_epoch.saturating_add(1);
            return Vec::new();
        }
        let draft = match self.command_draft(&button) {
            Ok(draft) => draft,
            Err(reason) => {
                self.control_overlay = Some(ControlOverlay::DisabledReason {
                    label: button.label,
                    reason,
                });
                self.control_epoch = self.control_epoch.saturating_add(1);
                return Vec::new();
            }
        };
        self.start_draft(button, draft)
    }

    fn start_draft(&mut self, button: ControlButton, draft: CommandDraft) -> Vec<ClientAction> {
        if !self.control_pair_matches(&button) {
            return self.reject_stale_control(button.label);
        }
        let Some(spec) = self.snapshot.as_ref().and_then(|snapshot| {
            snapshot
                .command_specs
                .iter()
                .find(|spec| spec.command_type.as_str() == button.command_type.as_str())
                .cloned()
        }) else {
            return self.show_control_reason(
                button.label,
                "Controller command spec is unavailable.".to_owned(),
            );
        };
        let pending = match self.command_tracker.prepare(
            draft,
            button.reviewed_control_version,
            button.reviewed_control_hash.clone(),
        ) {
            Ok(PrepareOutcome::New(pending)) => *pending,
            Ok(PrepareOutcome::Existing(_)) => {
                self.control_overlay = Some(ControlOverlay::DisabledReason {
                    label: button.label,
                    reason: "This action is already awaiting a receipt.".to_owned(),
                });
                self.control_epoch = self.control_epoch.saturating_add(1);
                return Vec::new();
            }
            Err(_) => {
                self.control_overlay = Some(ControlOverlay::DisabledReason {
                    label: button.label,
                    reason: "The command request could not be built safely.".to_owned(),
                });
                self.control_epoch = self.control_epoch.saturating_add(1);
                return Vec::new();
            }
        };
        let confirmation = begin_confirmation(&spec, pending);
        if button.confirmation_level == Some(crate::contract::ConfirmationLevel::None) {
            return self.submit_confirmed(confirmation);
        }
        self.control_overlay = Some(ControlOverlay::Confirmation {
            label: button.label,
            state: Box::new(confirmation),
        });
        self.control_epoch = self.control_epoch.saturating_add(1);
        Vec::new()
    }

    fn open_reason_form(&mut self, button: ControlButton) -> Vec<ClientAction> {
        let Some(ControlContext::Approval {
            run_id,
            checkpoint_id,
            ..
        }) = button.context.as_ref()
        else {
            return self
                .show_control_reason(button.label, "Select an exact approval first.".to_owned());
        };
        let run_id = run_id.clone();
        let checkpoint_id = checkpoint_id.clone();
        let quick_reasons = if button.command_type == CommandType::ApprovalHold {
            ["Need more evidence", "Waiting for data", "Review later"]
        } else {
            [
                "Evidence does not support",
                "Risk is too high",
                "Request is invalid",
            ]
        };
        self.control_overlay = Some(ControlOverlay::ReasonForm(ReasonForm {
            button,
            run_id,
            checkpoint_id,
            quick_reasons,
            selected: 0,
            note: String::new(),
        }));
        self.control_epoch = self.control_epoch.saturating_add(1);
        Vec::new()
    }

    fn move_reason_selection(&mut self, forward: bool) {
        if let Some(ControlOverlay::ReasonForm(form)) = self.control_overlay.as_mut() {
            form.move_selection(forward);
            self.control_epoch = self.control_epoch.saturating_add(1);
        }
    }

    fn push_reason_note(&mut self, character: char) {
        if let Some(ControlOverlay::ReasonForm(form)) = self.control_overlay.as_mut() {
            form.push(character);
            self.control_epoch = self.control_epoch.saturating_add(1);
        }
    }

    fn pop_reason_note(&mut self) {
        if let Some(ControlOverlay::ReasonForm(form)) = self.control_overlay.as_mut() {
            form.pop();
            self.control_epoch = self.control_epoch.saturating_add(1);
        }
    }

    fn submit_reason_form(&mut self) -> Vec<ClientAction> {
        let Some(ControlOverlay::ReasonForm(form)) = self.control_overlay.clone() else {
            return Vec::new();
        };
        let reason = form.reason();
        let draft = CommandDraft::new(
            form.button.command_type,
            serde_json::json!({
                "run_id": form.run_id,
                "checkpoint_id": form.checkpoint_id,
            }),
            Some(reason),
            format!(
                "{}:{}:{}",
                form.button.command_type.as_str(),
                form.run_id,
                form.checkpoint_id
            ),
        );
        self.start_draft(form.button, draft)
    }

    fn cycle_agent_route(&mut self, forward: bool) {
        if let Some(ControlOverlay::AgentEnqueueForm(form)) = self.control_overlay.as_mut() {
            form.route.cycle_override(forward);
            self.control_epoch = self.control_epoch.saturating_add(1);
        }
    }

    fn change_agent_priority(&mut self, increase: bool) {
        if let Some(ControlOverlay::AgentEnqueueForm(form)) = self.control_overlay.as_mut() {
            form.change_priority(increase);
            self.control_epoch = self.control_epoch.saturating_add(1);
        }
    }

    fn push_agent_objective(&mut self, character: char) {
        if let Some(ControlOverlay::AgentEnqueueForm(form)) = self.control_overlay.as_mut() {
            form.push(character);
            self.control_epoch = self.control_epoch.saturating_add(1);
        }
    }

    fn pop_agent_objective(&mut self) {
        if let Some(ControlOverlay::AgentEnqueueForm(form)) = self.control_overlay.as_mut() {
            form.pop();
            self.control_epoch = self.control_epoch.saturating_add(1);
        }
    }

    fn submit_agent_form(&mut self) -> Vec<ClientAction> {
        let Some(ControlOverlay::AgentEnqueueForm(form)) = self.control_overlay.clone() else {
            return Vec::new();
        };
        if form.objective.trim().is_empty() {
            return Vec::new();
        }
        let title = form.title();
        let draft = CommandDraft::new(
            CommandType::AgentEnqueue,
            serde_json::json!({
                "agent_id": form.route.selected_agent(),
                "title": title,
                "objective": form.objective,
                "priority": form.priority,
            }),
            Some(form.reason()),
            format!("agent.enqueue:{}:{title}", form.route.selected_agent()),
        );
        self.start_draft(form.button, draft)
    }

    fn accept_confirmation(&mut self) -> Vec<ClientAction> {
        if matches!(
            self.control_overlay.as_ref(),
            Some(ControlOverlay::Confirmation { state, .. })
                if state.selection() == Selection::Cancel
        ) {
            if let Some(ControlOverlay::Confirmation { state, .. }) = self.control_overlay.as_ref()
            {
                let command_id = state.pending().request().command_id.as_str().to_owned();
                self.command_tracker.cancel_prepared(&command_id);
            }
            self.close_control_overlay();
            return Vec::new();
        }
        let Some(ControlOverlay::Confirmation { state, .. }) = self.control_overlay.as_mut() else {
            return Vec::new();
        };
        state.accept_current();
        let confirmation = (**state).clone();
        self.control_epoch = self.control_epoch.saturating_add(1);
        self.submit_confirmed(confirmation)
    }

    fn submit_confirmed(
        &mut self,
        confirmation: crate::confirm::ConfirmationState,
    ) -> Vec<ClientAction> {
        let Ok(request) = submit_confirmation(&confirmation) else {
            return Vec::new();
        };
        let pair_matches = !self.awaiting_snapshot
            && self.snapshot.as_ref().is_some_and(|snapshot| {
                snapshot.control_version == request.reviewed_control_version
                    && snapshot.control_hash == request.reviewed_control_hash
            });
        if !pair_matches {
            self.command_tracker
                .cancel_prepared(request.command_id.as_str());
            return self.show_control_reason(
                "Controls Updated".to_owned(),
                "Controller controls changed. Review the action again.".to_owned(),
            );
        }
        let Some(request) = self.command_tracker.mark_confirmed_sent(request) else {
            self.control_overlay = Some(ControlOverlay::DisabledReason {
                label: "Command".to_owned(),
                reason: "The command is already in flight.".to_owned(),
            });
            self.control_epoch = self.control_epoch.saturating_add(1);
            return Vec::new();
        };
        self.close_control_overlay();
        vec![ClientAction::Command(request)]
    }

    fn cancel_unsent_controls_for_resync(&mut self) {
        self.command_tracker.cancel_prepared_commands();
        self.control_overlay = None;
        self.note_command = None;
        self.pending_note = None;
        self.local_input.clear();
        if matches!(self.mode, LocalMode::Menu | LocalMode::NoteEditor) {
            self.mode = LocalMode::Browse;
        }
        self.control_epoch = self.control_epoch.saturating_add(1);
    }

    fn command_draft(&self, button: &ControlButton) -> Result<CommandDraft, String> {
        match button.command_type {
            CommandType::ApprovalApprove => {
                let Some(ControlContext::Approval {
                    run_id,
                    checkpoint_id,
                    ..
                }) = button.context.as_ref()
                else {
                    return Err("Select an exact approval first.".to_owned());
                };
                Ok(CommandDraft::new(
                    button.command_type,
                    serde_json::json!({
                        "run_id": run_id,
                        "checkpoint_id": checkpoint_id,
                    }),
                    None,
                    format!("approval.approve:{run_id}:{checkpoint_id}"),
                ))
            }
            _ => Err("This control needs a reviewed input form before it can run.".to_owned()),
        }
    }

    fn submit_note(&mut self) -> Vec<ClientAction> {
        if self.local_input.trim().is_empty() {
            return Vec::new();
        }
        let Some(button) = self.note_command.clone() else {
            return Vec::new();
        };
        if !self.control_pair_matches(&button) {
            self.note_command = None;
            self.local_input.clear();
            return self.reject_stale_control(button.label);
        }
        let Some(ControlContext::Note {
            target_type,
            target_id,
        }) = button.context.as_ref()
        else {
            self.note_command = None;
            self.local_input.clear();
            self.mode = LocalMode::Browse;
            return Vec::new();
        };
        let target_type = *target_type;
        let target_id = target_id.clone();
        let visibility = match self.note_visibility {
            NoteVisibility::Private => "private",
            NoteVisibility::Shared => "shared",
        };
        let body = std::mem::take(&mut self.local_input);
        let draft = CommandDraft::new(
            CommandType::NoteAdd,
            serde_json::json!({
                "target_type": target_type,
                "target_id": target_id,
                "body": body,
                "visibility": visibility,
            }),
            None,
            format!("note.add:{target_type}:{target_id}"),
        );
        let Some(snapshot) = self.snapshot.as_ref() else {
            return Vec::new();
        };
        let Some(spec) = snapshot
            .command_specs
            .iter()
            .find(|spec| spec.command_type.as_str() == CommandType::NoteAdd.as_str())
            .cloned()
        else {
            return Vec::new();
        };
        let pending = match self.command_tracker.prepare(
            draft,
            button.reviewed_control_version,
            button.reviewed_control_hash,
        ) {
            Ok(PrepareOutcome::New(pending)) => *pending,
            Ok(PrepareOutcome::Existing(_)) => {
                return self.show_control_reason(
                    "Add Note".to_owned(),
                    "This note is already awaiting a receipt.".to_owned(),
                );
            }
            Err(_) => {
                return self.show_control_reason(
                    "Add Note".to_owned(),
                    "The note command could not be built safely.".to_owned(),
                );
            }
        };
        self.note_command = None;
        self.mode = LocalMode::Browse;
        self.submit_confirmed(begin_confirmation(&spec, pending))
    }

    fn control_pair_matches(&self, button: &ControlButton) -> bool {
        self.snapshot.as_ref().is_some_and(|snapshot| {
            snapshot.control_version == button.reviewed_control_version
                && snapshot.control_hash == button.reviewed_control_hash
        })
    }

    fn invalidate_stale_control_review(&mut self) {
        let Some(snapshot) = self.snapshot.as_ref() else {
            return;
        };
        let current_version = snapshot.control_version;
        let current_hash = snapshot.control_hash.clone();
        let reviewed_pair = match self.control_overlay.as_ref() {
            Some(ControlOverlay::Menu(menu)) => {
                let (version, hash) = menu.reviewed_control_pair();
                Some((version, hash.clone()))
            }
            Some(ControlOverlay::Confirmation { state, .. }) => Some((
                state.pending().request().reviewed_control_version,
                state.pending().request().reviewed_control_hash.clone(),
            )),
            Some(ControlOverlay::ReasonForm(form)) => Some((
                form.button.reviewed_control_version,
                form.button.reviewed_control_hash.clone(),
            )),
            Some(ControlOverlay::AgentEnqueueForm(form)) => Some((
                form.button.reviewed_control_version,
                form.button.reviewed_control_hash.clone(),
            )),
            Some(ControlOverlay::DisabledReason { .. }) | None => {
                self.note_command.as_ref().map(|button| {
                    (
                        button.reviewed_control_version,
                        button.reviewed_control_hash.clone(),
                    )
                })
            }
        };
        if reviewed_pair
            .is_some_and(|(version, hash)| version != current_version || hash != current_hash)
        {
            if let Some(ControlOverlay::Confirmation { state, .. }) = self.control_overlay.as_ref()
            {
                let command_id = state.pending().request().command_id.as_str().to_owned();
                self.command_tracker.cancel_prepared(&command_id);
            }
            self.note_command = None;
            self.local_input.clear();
            self.mode = LocalMode::Menu;
            self.control_overlay = Some(ControlOverlay::DisabledReason {
                label: "Controls Updated".to_owned(),
                reason: "Controller controls changed. Review the action again.".to_owned(),
            });
            self.control_epoch = self.control_epoch.saturating_add(1);
        }
    }

    fn reject_stale_control(&mut self, label: String) -> Vec<ClientAction> {
        self.show_control_reason(
            label,
            "Controller controls changed. Review the action again.".to_owned(),
        )
    }

    fn show_control_reason(&mut self, label: String, reason: String) -> Vec<ClientAction> {
        self.control_overlay = Some(ControlOverlay::DisabledReason { label, reason });
        self.mode = LocalMode::Menu;
        self.control_epoch = self.control_epoch.saturating_add(1);
        Vec::new()
    }

    fn select_screen(&mut self, screen: Screen) {
        if self.screen == screen {
            return;
        }
        self.screen = screen;
        self.control_overlay = None;
        self.note_command = None;
        self.mode = LocalMode::Browse;
        self.screen_state.scroll_offset = 0;
        self.screen_state.selected_id = None;
        self.screen_state.selected_kind = None;
        self.screen_state.detail_open = false;
        self.screen_state.narrow_panel = 0;
        self.show_search_detail = false;
        self.search_return_screen = None;
    }

    fn move_vertical(&mut self, forward: bool) {
        if self.mode == LocalMode::Open && self.screen_state.detail_open {
            let maximum = self.detail_scroll_maximum();
            self.screen_state.scroll_offset = if forward {
                self.screen_state
                    .scroll_offset
                    .saturating_add(1)
                    .min(maximum)
            } else {
                self.screen_state.scroll_offset.saturating_sub(1)
            };
            return;
        }
        if self.screen == Screen::Agents {
            let stage = match self.screen_state.narrow_panel % 5 {
                0 => AgentStage::Queued,
                1 => AgentStage::Running,
                2 => AgentStage::Waiting,
                3 => AgentStage::Done,
                _ => AgentStage::Backlog,
            };
            let mut rows = self.snapshot.as_ref().map_or_else(Vec::new, |snapshot| {
                snapshot
                    .agents
                    .rows
                    .iter()
                    .filter(|row| match stage {
                        AgentStage::Done => {
                            matches!(row.stage, AgentStage::Done | AgentStage::Failed)
                        }
                        _ => row.stage == stage,
                    })
                    .collect::<Vec<_>>()
            });
            rows.sort_by(|left, right| {
                right
                    .urgent
                    .cmp(&left.urgent)
                    .then_with(|| right.priority.get().cmp(&left.priority.get()))
                    .then_with(|| left.work_id.as_str().cmp(right.work_id.as_str()))
            });
            let ids = rows
                .into_iter()
                .map(|row| row.work_id.as_str().to_owned())
                .collect();
            self.move_selection_in(ids, DetailKind::Agent, forward);
            return;
        }
        if self.screen == Screen::ModelsRegime {
            let targets = self.panel_entity_targets().unwrap_or_default();
            self.move_selection_in_targets(targets, forward);
            return;
        }
        if let Some(targets) = self.panel_entity_targets() {
            self.move_selection_in_targets(targets, forward);
            return;
        }
        let ids = self
            .snapshot
            .as_ref()
            .map_or_else(Vec::new, |snapshot| match self.screen {
                Screen::Impact => snapshot
                    .impact
                    .holdings
                    .iter()
                    .map(|row| row.symbol.as_str().to_owned())
                    .collect(),
                Screen::Portfolio => snapshot
                    .portfolio
                    .rows
                    .iter()
                    .map(|row| row.symbol.as_str().to_owned())
                    .collect(),
                Screen::Timeline => snapshot
                    .timeline
                    .rows
                    .iter()
                    .filter(|row| self.screen_state.show_all_events || row.impact)
                    .map(|row| row.event_id.as_str().to_owned())
                    .collect(),
                _ => Vec::new(),
            });
        if !ids.is_empty() {
            let kind = match self.screen {
                Screen::Impact | Screen::Portfolio => DetailKind::Stock,
                Screen::Timeline => DetailKind::Event,
                _ => return,
            };
            self.move_selection_in(ids, kind, forward);
            return;
        }
        let maximum = self.snapshot.as_ref().map_or(0, |snapshot| {
            let count = match self.screen {
                Screen::RiskApprovals => match self.screen_state.narrow_panel % 4 {
                    0 => snapshot.risk.limits.len(),
                    1 => snapshot.risk.approvals.len(),
                    2 => snapshot.risk.alerts.len(),
                    _ => snapshot.risk.metrics.len(),
                },
                Screen::DataEvidence => match self.screen_state.narrow_panel % 2 {
                    0 => snapshot.data.sources.len(),
                    _ => snapshot.data.evidence.len(),
                },
                Screen::Memory => match self.screen_state.narrow_panel % 3 {
                    0 => snapshot
                        .memory
                        .rows
                        .iter()
                        .filter(|row| row.status == MemoryStatus::Core)
                        .count(),
                    1 => snapshot
                        .memory
                        .rows
                        .iter()
                        .filter(|row| row.status == MemoryStatus::Archived)
                        .count(),
                    _ => snapshot.memory.history.len(),
                },
                Screen::System => match self.screen_state.narrow_panel % 4 {
                    0 => snapshot.system.services.len(),
                    1 => snapshot.system.metrics.len(),
                    2 => snapshot.system.repositories.len(),
                    _ => {
                        12 + usize::from(snapshot.system.live_account.is_some())
                            + snapshot
                                .system
                                .live_transition_plan
                                .as_ref()
                                .map_or(0, |plan| plan.orders.len())
                    }
                },
                Screen::ModelsRegime => {
                    let spacing = match self.display_mode() {
                        DisplayMode::Compact => 0,
                        DisplayMode::Standard => 1,
                        DisplayMode::LargeText => 2,
                    };
                    match self.screen_state.narrow_panel % 3 {
                        0 => 2 + snapshot.models.opinions.len() * (2 + spacing),
                        1 => snapshot.models.candidates.len() * (2 + spacing),
                        _ => {
                            2 + snapshot.models.metrics.len() * (1 + spacing)
                                + snapshot.models.evidence.len() * (2 + spacing)
                        }
                    }
                }
                _ => 0,
            };
            count.saturating_sub(1)
        });
        self.screen_state.scroll_offset = if forward {
            self.screen_state
                .scroll_offset
                .saturating_add(1)
                .min(maximum)
        } else {
            self.screen_state.scroll_offset.saturating_sub(1)
        };
    }

    fn move_selection_in(&mut self, ids: Vec<String>, kind: DetailKind, forward: bool) {
        let targets = ids.into_iter().map(|id| (id, kind)).collect();
        self.move_selection_in_targets(targets, forward);
    }

    fn move_selection_in_targets(&mut self, targets: Vec<(String, DetailKind)>, forward: bool) {
        if targets.is_empty() {
            self.screen_state.selected_id = None;
            self.screen_state.selected_kind = None;
            self.screen_state.scroll_offset = 0;
            return;
        }
        let current = self
            .screen_state
            .selected_id
            .as_deref()
            .zip(self.screen_state.selected_kind)
            .and_then(|(selected_id, selected_kind)| {
                targets
                    .iter()
                    .position(|(id, kind)| id == selected_id && *kind == selected_kind)
            })
            .unwrap_or_else(|| self.screen_state.scroll_offset.min(targets.len() - 1));
        let next = if forward {
            current.saturating_add(1).min(targets.len() - 1)
        } else {
            current.saturating_sub(1)
        };
        self.screen_state.selected_id = Some(targets[next].0.clone());
        self.screen_state.selected_kind = Some(targets[next].1);
        self.screen_state.scroll_offset = next;
    }

    fn panel_entity_targets(&self) -> Option<Vec<(String, DetailKind)>> {
        self.browse_targets_for_panel(self.screen_state.narrow_panel)
    }

    pub(crate) fn browse_targets_for_panel(
        &self,
        panel: usize,
    ) -> Option<Vec<(String, DetailKind)>> {
        let snapshot = self.snapshot.as_ref()?;
        let targets = match self.screen {
            Screen::Orders => snapshot
                .orders
                .rows
                .iter()
                .flat_map(|row| {
                    std::iter::once((row.order_id.as_str().to_owned(), DetailKind::Order)).chain(
                        row.fills
                            .iter()
                            .map(|fill| (fill.fill_id.as_str().to_owned(), DetailKind::Fill)),
                    )
                })
                .chain(
                    snapshot
                        .orders
                        .reconciliation_agents
                        .iter()
                        .map(|row| (row.work_id.as_str().to_owned(), DetailKind::Agent)),
                )
                .chain(
                    snapshot
                        .orders
                        .history
                        .iter()
                        .map(|row| (row.event_id.as_str().to_owned(), DetailKind::Event)),
                )
                .collect(),
            Screen::Agents => {
                let stage = match panel % 5 {
                    0 => AgentStage::Queued,
                    1 => AgentStage::Running,
                    2 => AgentStage::Waiting,
                    3 => AgentStage::Done,
                    _ => AgentStage::Backlog,
                };
                let mut rows = snapshot
                    .agents
                    .rows
                    .iter()
                    .filter(|row| match stage {
                        AgentStage::Done => {
                            matches!(row.stage, AgentStage::Done | AgentStage::Failed)
                        }
                        _ => row.stage == stage,
                    })
                    .collect::<Vec<_>>();
                rows.sort_by(|left, right| {
                    right
                        .urgent
                        .cmp(&left.urgent)
                        .then_with(|| right.priority.get().cmp(&left.priority.get()))
                        .then_with(|| left.work_id.as_str().cmp(right.work_id.as_str()))
                });
                rows.into_iter()
                    .map(|row| (row.work_id.as_str().to_owned(), DetailKind::Agent))
                    .collect()
            }
            Screen::ModelsRegime => {
                match panel % 3 {
                    0 => snapshot
                        .models
                        .opinions
                        .iter()
                        .map(|row| (row.model_id.as_str().to_owned(), DetailKind::ModelOpinion))
                        .collect(),
                    1 => snapshot
                        .models
                        .candidates
                        .iter()
                        .map(|row| {
                            (
                                row.candidate_id.as_str().to_owned(),
                                DetailKind::ModelCandidate,
                            )
                        })
                        .collect(),
                    _ => {
                        snapshot
                            .models
                            .metrics
                            .iter()
                            .map(|row| (row.metric_id.as_str().to_owned(), DetailKind::Metric))
                            .chain(snapshot.models.evidence.iter().map(|row| {
                                (row.evidence_id.as_str().to_owned(), DetailKind::Evidence)
                            }))
                            .collect()
                    }
                }
            }
            Screen::RiskApprovals => match panel % 4 {
                0 => snapshot
                    .risk
                    .limits
                    .iter()
                    .map(|row| (row.limit_id.as_str().to_owned(), DetailKind::RiskLimit))
                    .collect(),
                1 => snapshot
                    .risk
                    .approvals
                    .iter()
                    .map(|row| (row.approval_id.as_str().to_owned(), DetailKind::Approval))
                    .collect(),
                2 => snapshot
                    .risk
                    .alerts
                    .iter()
                    .map(|row| (row.alert_id.as_str().to_owned(), DetailKind::Alert))
                    .collect(),
                _ => snapshot
                    .risk
                    .metrics
                    .iter()
                    .map(|row| (row.metric_id.as_str().to_owned(), DetailKind::Metric))
                    .collect(),
            },
            Screen::DataEvidence => match panel % 2 {
                0 => snapshot
                    .data
                    .sources
                    .iter()
                    .map(|row| (row.source_id.as_str().to_owned(), DetailKind::Source))
                    .collect(),
                _ => snapshot
                    .data
                    .evidence
                    .iter()
                    .map(|row| (row.evidence_id.as_str().to_owned(), DetailKind::Evidence))
                    .collect(),
            },
            Screen::Memory => match panel % 3 {
                0 => snapshot
                    .memory
                    .rows
                    .iter()
                    .filter(|row| row.status == MemoryStatus::Core)
                    .map(|row| (row.memory_id.as_str().to_owned(), DetailKind::Memory))
                    .collect(),
                1 => snapshot
                    .memory
                    .rows
                    .iter()
                    .filter(|row| row.status == MemoryStatus::Archived)
                    .map(|row| (row.memory_id.as_str().to_owned(), DetailKind::Memory))
                    .collect(),
                _ => snapshot
                    .memory
                    .history
                    .iter()
                    .map(|row| (row.event_id.as_str().to_owned(), DetailKind::Event))
                    .collect(),
            },
            Screen::System => match panel % 4 {
                0 => snapshot
                    .system
                    .services
                    .iter()
                    .map(|row| (row.service_id.as_str().to_owned(), DetailKind::Service))
                    .collect(),
                1 => snapshot
                    .system
                    .metrics
                    .iter()
                    .map(|row| (row.metric_id.as_str().to_owned(), DetailKind::Metric))
                    .collect(),
                2 => snapshot
                    .system
                    .repositories
                    .iter()
                    .map(|row| {
                        (
                            row.repository_id.as_str().to_owned(),
                            DetailKind::Repository,
                        )
                    })
                    .collect(),
                _ => return None,
            },
            Screen::Timeline => snapshot
                .timeline
                .rows
                .iter()
                .filter(|row| self.screen_state.show_all_events || row.impact)
                .map(|row| (row.event_id.as_str().to_owned(), DetailKind::Event))
                .collect(),
            Screen::Impact | Screen::Portfolio => return None,
        };
        Some(targets)
    }

    fn detail_scroll_maximum(&self) -> usize {
        let Some(snapshot) = self.snapshot.as_ref() else {
            return 0;
        };
        let mut area = self
            .detail_viewport
            .unwrap_or_else(|| Rect::new(0, 0, 80, 3));
        let state = self.screen_state();
        if let Some(result) = self.search_detail() {
            let line_count = crate::ui::search_detail_line_count(
                self,
                result,
                area.width.saturating_sub(2).max(1),
            );
            return line_count.saturating_sub(usize::from(area.height.saturating_sub(2).max(1)));
        }
        let line_count = match self.screen {
            Screen::Agents => {
                if snapshot.agents.freshness == Freshness::Stale {
                    area.y = area.y.saturating_add(3);
                    area.height = area.height.saturating_sub(3);
                }
                crate::screens::agents::agent_detail_line_count(
                    &snapshot.agents,
                    &state,
                    area.width.saturating_sub(2).max(1),
                )
            }
            Screen::Timeline => {
                if snapshot.timeline.freshness == Freshness::Stale {
                    area.y = area.y.saturating_add(3);
                    area.height = area.height.saturating_sub(3);
                }
                crate::screens::timeline::timeline_detail_line_count(
                    &snapshot.timeline,
                    &state,
                    area.width.saturating_sub(2).max(1),
                )
            }
            Screen::Portfolio => {
                if snapshot.portfolio.freshness == Freshness::Stale {
                    area.y = area.y.saturating_add(3);
                    area.height = area.height.saturating_sub(3);
                }
                area = detail_area(area);
                crate::screens::portfolio::portfolio_detail_line_count(
                    &snapshot.portfolio,
                    &state,
                    area.width.saturating_sub(2).max(1),
                )
            }
            Screen::Orders
            | Screen::ModelsRegime
            | Screen::RiskApprovals
            | Screen::DataEvidence
            | Screen::Memory
            | Screen::System => crate::screens::detail::direct_detail_line_count(
                snapshot,
                self.screen,
                &state,
                area.width.saturating_sub(2).max(1),
            ),
            Screen::Impact => 0,
        };
        line_count.saturating_sub(usize::from(area.height.saturating_sub(2).max(1)))
    }

    fn move_horizontal(&mut self, forward: bool) {
        match self.screen {
            Screen::Impact => {
                self.screen_state.narrow_panel = if forward {
                    (self.screen_state.narrow_panel + 1) % 3
                } else {
                    (self.screen_state.narrow_panel + 2) % 3
                };
            }
            Screen::Portfolio => {
                let period = match (self.screen_state.performance_period, forward) {
                    (PerformancePeriod::Today, true) | (PerformancePeriod::SinceStart, false) => {
                        PerformancePeriod::SinceRebalance
                    }
                    (PerformancePeriod::SinceRebalance, true)
                    | (PerformancePeriod::Today, false) => PerformancePeriod::SinceStart,
                    (PerformancePeriod::SinceStart, true)
                    | (PerformancePeriod::SinceRebalance, false) => PerformancePeriod::Today,
                };
                self.set_performance_period(period);
            }
            Screen::Agents => self.cycle_narrow_panel(forward, 5),
            Screen::ModelsRegime => self.cycle_narrow_panel(forward, 3),
            Screen::RiskApprovals => self.cycle_narrow_panel(forward, 4),
            Screen::DataEvidence => self.cycle_narrow_panel(forward, 2),
            Screen::Memory => self.cycle_narrow_panel(forward, 3),
            Screen::System => self.cycle_narrow_panel(forward, 4),
            _ => {}
        }
    }

    fn cycle_narrow_panel(&mut self, forward: bool, count: usize) {
        self.screen_state.narrow_panel = if forward {
            (self.screen_state.narrow_panel + 1) % count
        } else {
            (self.screen_state.narrow_panel + count - 1) % count
        };
        self.screen_state.scroll_offset = 0;
        self.screen_state.selected_id = None;
        self.screen_state.selected_kind = None;
    }

    fn focus_browse_panel(&mut self, panel: usize) {
        if self.screen != Screen::System || panel != 3 {
            return;
        }
        self.screen_state.narrow_panel = panel;
        self.screen_state.scroll_offset = 0;
        self.screen_state.selected_id = None;
        self.screen_state.selected_kind = None;
    }

    fn open_search_selected(&mut self) {
        let Some(target) = self.search_state.open_selected() else {
            return;
        };
        let return_screen = self.screen;
        self.screen = target.screen;
        self.mode = LocalMode::Open;
        self.local_input.clear();
        self.screen_state.scroll_offset = 0;
        self.screen_state.selected_id = Some(target.entity_id);
        self.screen_state.selected_kind = Some(target.detail_kind);
        self.screen_state.detail_open = true;
        self.screen_state.narrow_panel = 0;
        self.show_search_detail = true;
        self.search_return_screen = Some(return_screen);
    }

    fn invalidate_search_results(&mut self) {
        self.search_state.invalidate_for_refresh(self.local_now);
    }

    fn open_browse_row(&mut self, panel: usize, index: usize) {
        let selected = self
            .snapshot
            .as_ref()
            .and_then(|snapshot| match self.screen {
                Screen::Impact if panel == 0 => snapshot
                    .impact
                    .holdings
                    .get(index)
                    .map(|row| (row.symbol.as_str().to_owned(), DetailKind::Stock)),
                Screen::Portfolio if panel == 0 => snapshot
                    .portfolio
                    .rows
                    .get(index)
                    .map(|row| (row.symbol.as_str().to_owned(), DetailKind::Stock)),
                _ => self
                    .browse_targets_for_panel(panel)
                    .and_then(|targets| targets.get(index).cloned()),
            });
        let Some((selected_id, selected_kind)) = selected else {
            return;
        };
        self.screen_state.narrow_panel = panel;
        self.screen_state.selected_id = Some(selected_id);
        self.screen_state.selected_kind = Some(selected_kind);
        self.open_selected();
    }

    fn open_selected(&mut self) {
        self.mode = LocalMode::Open;
        self.show_search_detail = false;
        self.search_return_screen = None;
        let selected = if let Some(targets) = self.panel_entity_targets() {
            self.screen_state
                .selected_id
                .as_deref()
                .zip(self.screen_state.selected_kind)
                .and_then(|(selected_id, selected_kind)| {
                    targets
                        .iter()
                        .find(|(id, kind)| id == selected_id && *kind == selected_kind)
                        .cloned()
                })
                .or_else(|| targets.get(self.screen_state.scroll_offset).cloned())
        } else {
            self.snapshot
                .as_ref()
                .and_then(|snapshot| match self.screen {
                    Screen::Impact | Screen::Portfolio => {
                        let rows = if self.screen == Screen::Impact {
                            &snapshot.impact.holdings
                        } else {
                            &snapshot.portfolio.rows
                        };
                        self.screen_state
                            .selected_id
                            .as_deref()
                            .and_then(|selected| {
                                rows.iter()
                                    .find(|row| row.symbol.as_str() == selected)
                                    .map(|row| (row.symbol.as_str().to_owned(), DetailKind::Stock))
                            })
                            .or_else(|| {
                                rows.get(self.screen_state.scroll_offset)
                                    .map(|row| (row.symbol.as_str().to_owned(), DetailKind::Stock))
                            })
                    }
                    Screen::Agents => self
                        .screen_state
                        .selected_id
                        .clone()
                        .map(|id| (id, DetailKind::Agent))
                        .or_else(|| {
                            snapshot
                                .agents
                                .rows
                                .first()
                                .map(|row| (row.work_id.as_str().to_owned(), DetailKind::Agent))
                        }),
                    Screen::Timeline => self
                        .screen_state
                        .selected_id
                        .clone()
                        .map(|id| (id, DetailKind::Event))
                        .or_else(|| {
                            snapshot
                                .timeline
                                .rows
                                .iter()
                                .find(|row| self.screen_state.show_all_events || row.impact)
                                .map(|row| (row.event_id.as_str().to_owned(), DetailKind::Event))
                        }),
                    Screen::Orders
                    | Screen::ModelsRegime
                    | Screen::RiskApprovals
                    | Screen::DataEvidence
                    | Screen::Memory
                    | Screen::System => None,
                })
        };
        if let Some((selected_id, selected_kind)) = selected {
            if matches!(self.screen, Screen::Impact | Screen::Portfolio) {
                self.screen = Screen::Portfolio;
            }
            self.screen_state.selected_id = Some(selected_id);
            self.screen_state.selected_kind = Some(selected_kind);
            self.screen_state.detail_open = true;
            self.screen_state.scroll_offset = 0;
        }
    }

    fn current_note_target(&self) -> Option<(&'static str, &str)> {
        let entity_id = self.screen_state.selected_id.as_deref()?;
        let target_type = match self.screen_state.selected_kind? {
            DetailKind::Stock => "stock",
            DetailKind::Order => "order",
            DetailKind::Approval => "approval",
            DetailKind::Event => "agent-event",
            DetailKind::Agent
            | DetailKind::Fill
            | DetailKind::ModelOpinion
            | DetailKind::ModelCandidate
            | DetailKind::Metric
            | DetailKind::Evidence
            | DetailKind::RiskLimit
            | DetailKind::Alert
            | DetailKind::Source
            | DetailKind::Memory
            | DetailKind::Note
            | DetailKind::Service
            | DetailKind::Repository => return None,
        };
        Some((target_type, entity_id))
    }

    fn observe_presentation_sequence(&mut self, sequence: u64) -> Result<(), ProtocolError> {
        if self.awaiting_snapshot || self.snapshot_reducer.state_opt().is_none() {
            return Ok(());
        }
        if self.snapshot_reducer.observe_sequence(sequence).is_err() {
            return Err(self.fail_closed(
                "sequence",
                "Presentation sequence cannot be reduced safely.",
            ));
        }
        Ok(())
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
        self.snapshot_reducer = SnapshotReducer::default();
        self.search_state.clear_results();
        self.mode = LocalMode::Browse;
        self.clear_auth();
        self.local_input.clear();
        self.filter_error = None;
        self.pending_note = None;
        self.control_overlay = None;
        self.note_command = None;
        self.command_tracker.cancel_prepared_commands();
        self.show_search_detail = false;
        self.search_return_screen = None;
        self.lock_pending = true;
    }

    fn enter_manual_lock(&mut self) {
        self.access = AccessState::Locked;
        self.phase = SessionPhase::AwaitingAuth { first_run: false };
        self.snapshot = None;
        self.snapshot_reducer = SnapshotReducer::default();
        self.search_state = SearchState::default();
        self.mode = LocalMode::Browse;
        self.clear_auth();
        self.local_input.clear();
        self.filter_error = None;
        self.pending_note = None;
        self.control_overlay = None;
        self.note_command = None;
        self.command_tracker.cancel_prepared_commands();
        self.show_search_detail = false;
        self.search_return_screen = None;
        self.awaiting_snapshot = false;
        self.lock_pending = false;
        self.lease_pending = false;
    }

    fn enter_protocol_lockout(&mut self) {
        self.access = AccessState::ProtocolLockout;
        self.phase = SessionPhase::ProtocolLockout;
        self.snapshot = None;
        self.snapshot_reducer = SnapshotReducer::default();
        self.search_state = SearchState::default();
        self.mode = LocalMode::Browse;
        self.clear_auth();
        self.local_input.clear();
        self.filter_error = None;
        self.pending_note = None;
        self.control_overlay = None;
        self.note_command = None;
        self.command_tracker.cancel_prepared_commands();
        self.show_search_detail = false;
        self.search_return_screen = None;
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
