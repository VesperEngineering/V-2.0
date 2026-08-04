use std::fmt;

use crate::command::PendingCommand;
use crate::contract::{
    CommandPayload, CommandReceipt, CommandRequest, CommandSpecView, CommandType,
    ConfirmationLevel, ConfirmationProof, RawConfirmationText, ReceiptStatus, Sha256Hex,
};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Selection {
    Cancel,
    Confirm,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ConfirmationStep {
    First,
    Second,
    Complete,
}

#[derive(Clone, Debug, PartialEq)]
pub struct RestorePrerequisites {
    pub validated_preview_hash: Sha256Hex,
    pub safety_backup_receipt: CommandReceipt,
    pub safety_backup_command_type: CommandType,
    pub runtime_stopped: bool,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ConfirmationState {
    level: ConfirmationLevel,
    pending: PendingCommand,
    selection: Selection,
    first_confirmed: bool,
    second_confirmed: bool,
    typed_text: String,
    cancelled: bool,
    restore_prerequisites: Option<RestorePrerequisites>,
    invalid_spec: bool,
}

impl ConfirmationState {
    pub fn level(&self) -> ConfirmationLevel {
        self.level
    }

    pub fn initial_selection(&self) -> Selection {
        Selection::Cancel
    }

    pub fn selection(&self) -> Selection {
        self.selection
    }

    pub fn step(&self) -> ConfirmationStep {
        if self.level == ConfirmationLevel::DoubleConfirm
            && self.first_confirmed
            && !self.second_confirmed
        {
            ConfirmationStep::Second
        } else if self.is_complete() {
            ConfirmationStep::Complete
        } else {
            ConfirmationStep::First
        }
    }

    pub fn select(&mut self, selection: Selection) {
        self.selection = selection;
    }

    pub fn accept_current(&mut self) {
        if self.selection != Selection::Confirm || self.cancelled {
            return;
        }
        if self.level == ConfirmationLevel::DoubleConfirm && self.first_confirmed {
            self.second_confirmed = true;
        } else {
            self.first_confirmed = true;
            if self.level == ConfirmationLevel::DoubleConfirm {
                self.selection = Selection::Cancel;
            }
        }
    }

    pub fn replace_typed_text(&mut self, value: impl Into<String>) {
        self.typed_text = value.into().chars().take(512).collect();
    }

    pub fn typed_text(&self) -> &str {
        &self.typed_text
    }

    pub fn cancel(&mut self) {
        self.cancelled = true;
    }

    pub fn set_restore_prerequisites(&mut self, prerequisites: RestorePrerequisites) {
        self.restore_prerequisites = Some(prerequisites);
    }

    pub fn pending(&self) -> &PendingCommand {
        &self.pending
    }

    pub fn push_typed_character(&mut self, character: char) {
        if self.typed_text.chars().count() < 512 {
            self.typed_text.push(character);
        }
    }

    pub fn pop_typed_character(&mut self) {
        self.typed_text.pop();
    }

    fn is_complete(&self) -> bool {
        match self.level {
            ConfirmationLevel::None => true,
            ConfirmationLevel::Confirm => self.first_confirmed,
            ConfirmationLevel::DoubleConfirm => self.first_confirmed && self.second_confirmed,
            ConfirmationLevel::TypedLive => {
                self.first_confirmed && self.typed_text == "ENABLE LIVE"
            }
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ConfirmationError {
    SpecMismatch,
    ConfirmationRequired,
    TypedLiveMismatch,
    Cancelled,
    RestorePrerequisites,
}

impl fmt::Display for ConfirmationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::SpecMismatch => "command spec does not match the pending command",
            Self::ConfirmationRequired => "confirmation is required",
            Self::TypedLiveMismatch => "ENABLE LIVE must be typed exactly",
            Self::Cancelled => "confirmation was cancelled",
            Self::RestorePrerequisites => "restore prerequisites are not satisfied",
        })
    }
}

impl std::error::Error for ConfirmationError {}

pub fn begin_confirmation(spec: &CommandSpecView, request: PendingCommand) -> ConfirmationState {
    let invalid_spec = spec.command_type.as_str() != request.request().command_type.as_str();
    ConfirmationState {
        level: spec.confirmation_level,
        pending: request,
        selection: Selection::Cancel,
        first_confirmed: false,
        second_confirmed: false,
        typed_text: String::new(),
        cancelled: false,
        restore_prerequisites: None,
        invalid_spec,
    }
}

pub fn submit_confirmation(state: &ConfirmationState) -> Result<CommandRequest, ConfirmationError> {
    if state.invalid_spec {
        return Err(ConfirmationError::SpecMismatch);
    }
    if state.cancelled {
        return Err(ConfirmationError::Cancelled);
    }
    if state.level == ConfirmationLevel::TypedLive && state.typed_text != "ENABLE LIVE" {
        return Err(ConfirmationError::TypedLiveMismatch);
    }
    if !state.is_complete() {
        return Err(ConfirmationError::ConfirmationRequired);
    }
    let mut request = state.pending.clone().into_request();
    let bound_preview_hash = if request.command_type == CommandType::BackupRestore {
        Some(validate_restore(state, &request)?)
    } else {
        None
    };
    request.confirmation = (state.level != ConfirmationLevel::None).then_some(ConfirmationProof {
        first_confirmed: state.first_confirmed,
        second_confirmed: state.second_confirmed,
        typed_text: if state.level == ConfirmationLevel::TypedLive {
            Some(
                serde_json::from_value::<RawConfirmationText>(serde_json::Value::String(
                    state.typed_text.clone(),
                ))
                .expect("typed input was bounded before request construction"),
            )
        } else {
            None
        },
        bound_preview_hash,
    });
    Ok(request)
}

fn validate_restore(
    state: &ConfirmationState,
    request: &CommandRequest,
) -> Result<Sha256Hex, ConfirmationError> {
    let Some(prerequisites) = state.restore_prerequisites.as_ref() else {
        return Err(ConfirmationError::RestorePrerequisites);
    };
    let CommandPayload::BackupRestore(payload) = &request.payload else {
        return Err(ConfirmationError::RestorePrerequisites);
    };
    if prerequisites.safety_backup_command_type != CommandType::BackupCreate
        || !prerequisites.runtime_stopped
        || prerequisites.validated_preview_hash != payload.preview_hash
        || prerequisites.safety_backup_receipt.command_id != payload.safety_backup_receipt_id
        || prerequisites.safety_backup_receipt.status != ReceiptStatus::Completed
        || prerequisites
            .safety_backup_receipt
            .finished_at_utc
            .is_none()
    {
        return Err(ConfirmationError::RestorePrerequisites);
    }
    Ok(payload.preview_hash.clone())
}
