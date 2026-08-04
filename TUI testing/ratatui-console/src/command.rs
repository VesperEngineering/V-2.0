use std::collections::BTreeMap;
use std::fmt;
use std::time::{SystemTime, UNIX_EPOCH};

use crate::contract::{
    CommandReceipt, CommandRequest, CommandType, ReceiptStatus, SafeId, Sha256Hex,
};

#[derive(Clone, Debug, PartialEq)]
pub struct PendingCommand {
    request: CommandRequest,
    dedup_key: String,
}

impl PendingCommand {
    pub fn new(request: CommandRequest, dedup_key: impl Into<String>) -> Self {
        Self {
            request,
            dedup_key: dedup_key.into(),
        }
    }

    pub fn request(&self) -> &CommandRequest {
        &self.request
    }

    pub fn dedup_key(&self) -> &str {
        &self.dedup_key
    }

    pub(crate) fn into_request(self) -> CommandRequest {
        self.request
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct CommandDraft {
    command_type: CommandType,
    payload: serde_json::Value,
    reason: Option<String>,
    dedup_key: String,
}

impl CommandDraft {
    pub fn new(
        command_type: CommandType,
        payload: serde_json::Value,
        reason: Option<String>,
        dedup_key: impl Into<String>,
    ) -> Self {
        Self {
            command_type,
            payload,
            reason,
            dedup_key: dedup_key.into(),
        }
    }
}

#[derive(Clone, Debug)]
pub struct CommandIdGenerator {
    process_id: u32,
    ticks: u128,
    counter: u64,
}

impl CommandIdGenerator {
    pub fn seeded(process_id: u32, ticks: u128) -> Self {
        Self {
            process_id,
            ticks,
            counter: 0,
        }
    }

    fn system() -> Self {
        let ticks = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_or(0, |duration| duration.as_nanos());
        Self::seeded(std::process::id(), ticks)
    }

    fn next(&mut self) -> Result<SafeId, CommandBuildError> {
        self.counter = self
            .counter
            .checked_add(1)
            .ok_or(CommandBuildError::IdExhausted)?;
        serde_json::from_value(serde_json::Value::String(format!(
            "cmd:{}:{}:{}",
            self.process_id, self.ticks, self.counter
        )))
        .map_err(|_| CommandBuildError::IdInvalid)
    }
}

impl Default for CommandIdGenerator {
    fn default() -> Self {
        Self::system()
    }
}

#[derive(Clone, Debug, PartialEq)]
pub enum PrepareOutcome {
    New(Box<PendingCommand>),
    Existing(SafeId),
}

#[derive(Clone, Debug)]
struct TrackedCommand {
    pending: PendingCommand,
    sent: bool,
    state: TrackedCommandState,
    code: Option<String>,
    safe_message: Option<String>,
    last_receipt: Option<CommandReceipt>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TrackedCommandState {
    Prepared,
    InFlight,
    Accepted,
    Running,
    Completed,
    Rejected,
    Failed,
    Cancelled,
}

impl TrackedCommandState {
    fn is_terminal(self) -> bool {
        matches!(
            self,
            Self::Completed | Self::Rejected | Self::Failed | Self::Cancelled
        )
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct TrackedCommandSummary {
    pub command_id: String,
    pub state: TrackedCommandState,
    pub code: Option<String>,
    pub safe_message: Option<String>,
}

#[derive(Debug, Default)]
pub struct CommandTracker {
    generator: CommandIdGenerator,
    by_id: BTreeMap<String, TrackedCommand>,
    by_dedup_key: BTreeMap<String, String>,
}

impl CommandTracker {
    pub fn with_generator(generator: CommandIdGenerator) -> Self {
        Self {
            generator,
            by_id: BTreeMap::new(),
            by_dedup_key: BTreeMap::new(),
        }
    }

    pub fn prepare(
        &mut self,
        draft: CommandDraft,
        control_version: u64,
        control_hash: Sha256Hex,
    ) -> Result<PrepareOutcome, CommandBuildError> {
        if draft.dedup_key.is_empty() {
            return Err(CommandBuildError::EmptyDedupKey);
        }
        if let Some(command_id) = self.by_dedup_key.get(&draft.dedup_key) {
            let id = serde_json::from_value(serde_json::Value::String(command_id.clone()))
                .map_err(|_| CommandBuildError::IdInvalid)?;
            return Ok(PrepareOutcome::Existing(id));
        }
        let command_id = self.generator.next()?;
        let request = serde_json::from_value::<CommandRequest>(serde_json::json!({
            "command_id": command_id,
            "command_type": draft.command_type,
            "reviewed_control_version": control_version,
            "reviewed_control_hash": control_hash,
            "reason": draft.reason,
            "confirmation": null,
            "payload": draft.payload,
        }))
        .map_err(|error| CommandBuildError::InvalidRequest(error.to_string()))?;
        let pending = PendingCommand::new(request, draft.dedup_key.clone());
        let id = pending.request.command_id.as_str().to_owned();
        self.by_dedup_key.insert(draft.dedup_key, id.clone());
        self.by_id.insert(
            id,
            TrackedCommand {
                pending: pending.clone(),
                sent: false,
                state: TrackedCommandState::Prepared,
                code: None,
                safe_message: None,
                last_receipt: None,
            },
        );
        Ok(PrepareOutcome::New(Box::new(pending)))
    }

    pub fn mark_sent(&mut self, pending: &PendingCommand) -> Option<CommandRequest> {
        let tracked = self.by_id.get_mut(pending.request.command_id.as_str())?;
        if tracked.sent || tracked.pending != *pending {
            return None;
        }
        tracked.sent = true;
        tracked.state = TrackedCommandState::InFlight;
        Some(tracked.pending.request.clone())
    }

    pub fn mark_confirmed_sent(&mut self, request: CommandRequest) -> Option<CommandRequest> {
        let tracked = self.by_id.get_mut(request.command_id.as_str())?;
        if tracked.sent
            || tracked.pending.request.command_type != request.command_type
            || tracked.pending.request.reviewed_control_version != request.reviewed_control_version
            || tracked.pending.request.reviewed_control_hash != request.reviewed_control_hash
            || tracked.pending.request.reason != request.reason
            || tracked.pending.request.payload != request.payload
        {
            return None;
        }
        tracked.pending.request = request.clone();
        tracked.sent = true;
        tracked.state = TrackedCommandState::InFlight;
        Some(request)
    }

    pub fn cancel_prepared(&mut self, command_id: &str) -> bool {
        let Some(tracked) = self.by_id.get(command_id) else {
            return false;
        };
        if tracked.sent {
            return false;
        }
        let dedup_key = tracked.pending.dedup_key.clone();
        let command_id = tracked.pending.request.command_id.as_str().to_owned();
        self.by_id.remove(&command_id);
        if self.by_dedup_key.get(&dedup_key) == Some(&command_id) {
            self.by_dedup_key.remove(&dedup_key);
        }
        true
    }

    pub fn cancel_prepared_commands(&mut self) {
        let command_ids = self
            .by_id
            .iter()
            .filter_map(|(command_id, tracked)| (!tracked.sent).then_some(command_id.clone()))
            .collect::<Vec<_>>();
        for command_id in command_ids {
            self.cancel_prepared(&command_id);
        }
    }

    pub fn apply_receipt(&mut self, receipt: CommandReceipt) -> Result<(), TrackerError> {
        let tracked = self
            .by_id
            .get_mut(receipt.command_id.as_str())
            .ok_or(TrackerError::UnknownReceipt)?;
        if !tracked.sent {
            return Err(TrackerError::UnexpectedReceipt);
        }
        if tracked.last_receipt.as_ref() == Some(&receipt) {
            return Ok(());
        }
        let next = match receipt.status {
            ReceiptStatus::Accepted => TrackedCommandState::Accepted,
            ReceiptStatus::Rejected => TrackedCommandState::Rejected,
            ReceiptStatus::Running => TrackedCommandState::Running,
            ReceiptStatus::Completed => TrackedCommandState::Completed,
            ReceiptStatus::Failed => TrackedCommandState::Failed,
            ReceiptStatus::Cancelled => TrackedCommandState::Cancelled,
        };
        if !valid_receipt_transition(tracked.state, next) {
            return Err(TrackerError::InvalidTransition);
        }
        tracked.state = next;
        tracked.code = Some(receipt.code.as_str().to_owned());
        tracked.safe_message = Some(receipt.safe_message.as_str().to_owned());
        tracked.last_receipt = Some(receipt);
        if next.is_terminal() {
            let dedup_key = tracked.pending.dedup_key.clone();
            let command_id = tracked.pending.request.command_id.as_str().to_owned();
            if self.by_dedup_key.get(&dedup_key) == Some(&command_id) {
                self.by_dedup_key.remove(&dedup_key);
            }
        }
        Ok(())
    }

    pub fn summary(&self, command_id: &str) -> Option<TrackedCommandSummary> {
        let tracked = self.by_id.get(command_id)?;
        Some(TrackedCommandSummary {
            command_id: tracked.pending.request.command_id.as_str().to_owned(),
            state: tracked.state,
            code: tracked.code.clone(),
            safe_message: tracked.safe_message.clone(),
        })
    }

    pub fn summaries(&self) -> Vec<TrackedCommandSummary> {
        self.by_id
            .keys()
            .filter_map(|command_id| self.summary(command_id))
            .collect()
    }
}

fn valid_receipt_transition(current: TrackedCommandState, next: TrackedCommandState) -> bool {
    if current.is_terminal() {
        return false;
    }
    match current {
        TrackedCommandState::Prepared => false,
        TrackedCommandState::InFlight => next != TrackedCommandState::Prepared,
        TrackedCommandState::Accepted => matches!(
            next,
            TrackedCommandState::Running
                | TrackedCommandState::Completed
                | TrackedCommandState::Failed
                | TrackedCommandState::Cancelled
        ),
        TrackedCommandState::Running => matches!(
            next,
            TrackedCommandState::Completed
                | TrackedCommandState::Failed
                | TrackedCommandState::Cancelled
        ),
        TrackedCommandState::Completed
        | TrackedCommandState::Rejected
        | TrackedCommandState::Failed
        | TrackedCommandState::Cancelled => false,
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TrackerError {
    UnknownReceipt,
    UnexpectedReceipt,
    InvalidTransition,
}

impl fmt::Display for TrackerError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::UnknownReceipt => "receipt command ID is unknown",
            Self::UnexpectedReceipt => "receipt arrived before the command was sent",
            Self::InvalidTransition => "receipt state transition is invalid",
        })
    }
}

impl std::error::Error for TrackerError {}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum CommandBuildError {
    EmptyDedupKey,
    IdExhausted,
    IdInvalid,
    InvalidRequest(String),
}

impl fmt::Display for CommandBuildError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::EmptyDedupKey => formatter.write_str("command deduplication key is empty"),
            Self::IdExhausted => formatter.write_str("command ID counter is exhausted"),
            Self::IdInvalid => formatter.write_str("generated command ID is invalid"),
            Self::InvalidRequest(error) => write!(formatter, "command request is invalid: {error}"),
        }
    }
}

impl std::error::Error for CommandBuildError {}
