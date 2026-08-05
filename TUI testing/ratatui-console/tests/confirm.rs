use vesper_ratatui_console::command::PendingCommand;
use vesper_ratatui_console::confirm::{
    ConfirmationError, ConfirmationStep, RestorePrerequisites, Selection, begin_confirmation,
    submit_confirmation,
};
use vesper_ratatui_console::contract::{
    CommandReceipt, CommandRequest, CommandSpecView, CommandType, Sha256Hex,
};

fn spec(level: &str) -> CommandSpecView {
    serde_json::from_value(serde_json::json!({
        "command_type": "approval.approve",
        "payload_model": "ApprovalPayload",
        "capability_id": "approval.approve",
        "reason_rule": "optional",
        "confirmation_level": level
    }))
    .expect("valid command spec")
}

fn request() -> CommandRequest {
    serde_json::from_value(serde_json::json!({
        "command_id": "cmd:11:22:1",
        "command_type": "approval.approve",
        "reviewed_control_version": 7,
        "reviewed_control_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "reason": null,
        "confirmation": null,
        "payload": {"run_id": "run-1", "checkpoint_id": "checkpoint-1"}
    }))
    .expect("valid command request")
}

fn restore_spec() -> CommandSpecView {
    serde_json::from_value(serde_json::json!({
        "command_type": "backup.restore",
        "payload_model": "BackupRestorePayload",
        "capability_id": "backup.restore",
        "reason_rule": "required",
        "confirmation_level": "double-confirm"
    }))
    .expect("valid restore spec")
}

fn restore_request() -> CommandRequest {
    serde_json::from_value(serde_json::json!({
        "command_id": "cmd:11:22:2",
        "command_type": "backup.restore",
        "reviewed_control_version": 7,
        "reviewed_control_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "reason": "Restore the validated archive.",
        "confirmation": null,
        "payload": {
            "archive": "C:\\backups\\v20.zip",
            "preview_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "safety_backup_receipt_id": "backup-receipt-1"
        }
    }))
    .expect("valid restore command")
}

fn completed_backup_receipt() -> CommandReceipt {
    serde_json::from_value(serde_json::json!({
        "command_id": "backup-receipt-1",
        "status": "completed",
        "code": "backup-created",
        "safe_message": "Safety backup completed.",
        "accepted_at_utc": "2026-08-04T12:00:00Z",
        "finished_at_utc": "2026-08-04T12:01:00Z",
        "result": null
    }))
    .expect("valid completed backup receipt")
}

fn hash(value: &str) -> Sha256Hex {
    serde_json::from_value(serde_json::Value::String(value.to_owned())).expect("valid hash")
}

#[test]
fn confirm_starts_on_cancel_and_requires_an_explicit_confirm_selection() {
    let mut state = begin_confirmation(
        &spec("confirm"),
        PendingCommand::new(request(), "approval.approve:run-1"),
    );

    assert_eq!(state.initial_selection(), Selection::Cancel);
    assert!(submit_confirmation(&state).is_err());

    state.select(Selection::Confirm);
    state.accept_current();
    let command = submit_confirmation(&state).expect("explicit confirmation is accepted");
    assert!(command.confirmation.expect("proof").first_confirmed);
}

#[test]
fn no_confirmation_submits_immediately_without_a_proof() {
    let state = begin_confirmation(
        &spec("none"),
        PendingCommand::new(request(), "approval.approve:run-1"),
    );

    let command = submit_confirmation(&state).expect("safe command submits immediately");
    assert!(command.confirmation.is_none());
}

#[test]
fn double_confirmation_resets_to_cancel_for_the_second_step() {
    let mut state = begin_confirmation(
        &spec("double-confirm"),
        PendingCommand::new(request(), "approval.approve:run-1"),
    );
    state.select(Selection::Confirm);
    state.accept_current();

    assert_eq!(state.step(), ConfirmationStep::Second);
    assert_eq!(state.selection(), Selection::Cancel);
    assert_eq!(
        submit_confirmation(&state),
        Err(ConfirmationError::ConfirmationRequired)
    );

    state.select(Selection::Confirm);
    state.accept_current();
    let proof = submit_confirmation(&state)
        .expect("both confirmations are accepted")
        .confirmation
        .expect("proof");
    assert!(proof.first_confirmed);
    assert!(proof.second_confirmed);
}

#[test]
fn typed_live_requires_the_exact_phrase() {
    let mut state = begin_confirmation(
        &spec("typed-live"),
        PendingCommand::new(request(), "approval.approve:run-1"),
    );
    state.replace_typed_text("enable live");
    assert_eq!(
        submit_confirmation(&state),
        Err(ConfirmationError::TypedLiveMismatch)
    );

    state.replace_typed_text("ENABLE LIVE");
    assert_eq!(
        submit_confirmation(&state),
        Err(ConfirmationError::ConfirmationRequired)
    );
    state.select(Selection::Confirm);
    state.accept_current();
    let proof = submit_confirmation(&state)
        .expect("explicit confirmation plus the exact typed phrase is accepted")
        .confirmation
        .expect("proof");
    assert!(proof.first_confirmed);
    assert_eq!(
        proof.typed_text.expect("typed proof").as_str(),
        "ENABLE LIVE"
    );
}

#[test]
fn escape_cancels_a_confirmation() {
    let mut state = begin_confirmation(
        &spec("confirm"),
        PendingCommand::new(request(), "approval.approve:run-1"),
    );
    state.cancel();
    assert_eq!(
        submit_confirmation(&state),
        Err(ConfirmationError::Cancelled)
    );
}

#[test]
fn restore_requires_preview_safety_backup_runtime_stop_and_bound_double_confirmation() {
    let mut state = begin_confirmation(
        &restore_spec(),
        PendingCommand::new(restore_request(), "backup.restore:preview"),
    );
    assert!(submit_confirmation(&state).is_err());
    assert_eq!(state.initial_selection(), Selection::Cancel);

    state.set_restore_prerequisites(RestorePrerequisites {
        validated_preview_hash: hash(
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ),
        safety_backup_receipt: completed_backup_receipt(),
        safety_backup_command_type: CommandType::BackupCreate,
        runtime_stopped: true,
    });
    state.select(Selection::Confirm);
    state.accept_current();
    state.select(Selection::Confirm);
    state.accept_current();

    let proof = submit_confirmation(&state)
        .expect("validated restore is accepted")
        .confirmation
        .expect("proof");
    assert_eq!(
        serde_json::to_value(proof.bound_preview_hash.expect("bound hash")).expect("serialize"),
        serde_json::json!("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
    );
}
