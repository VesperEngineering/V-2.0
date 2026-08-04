use crossterm::event::{KeyModifiers, MouseButton, MouseEvent, MouseEventKind};
use ratatui::Terminal;
use ratatui::backend::TestBackend;
use ratatui::buffer::Buffer;
use ratatui::layout::Rect;
use vesper_ratatui_console::app::{App, FoundationClient, mouse_to_input};
use vesper_ratatui_console::command::{
    CommandDraft, CommandIdGenerator, CommandTracker, PendingCommand, PrepareOutcome,
    TrackedCommandState, TrackerError,
};
use vesper_ratatui_console::confirm::begin_confirmation;
use vesper_ratatui_console::contract::CommandSpecView;
use vesper_ratatui_console::contract::{
    CapabilityView, CommandPayload, CommandReceipt, CommandReceiptPayload, CommandRequest,
    CommandType, ConsoleSnapshot, Envelope, Message, NoteTargetType, SafeId, Sha256Hex,
    UtcTimestamp,
};
use vesper_ratatui_console::controls::{
    AgentRouteDraft, ButtonState, ControlOverlay, LocalControl, button_state,
    control_definitions_for_screen, local_controls, server_button,
};
use vesper_ratatui_console::input::InputEvent;
use vesper_ratatui_console::layout::DisplayMode;
use vesper_ratatui_console::state::{AccessState, LocalMode, Screen};
use vesper_ratatui_console::state::{AppState, ClientAction, ReduceOutcome};
use vesper_ratatui_console::theme::Theme;
use vesper_ratatui_console::ui::{
    control_overlay_area, render, render_control_overlay, split_control_area,
};

fn spec() -> CommandSpecView {
    serde_json::from_value(serde_json::json!({
        "command_type": "approval.approve",
        "payload_model": "ApprovalPayload",
        "capability_id": "approval.approve",
        "reason_rule": "optional",
        "confirmation_level": "confirm"
    }))
    .expect("valid command spec")
}

fn capability(state: &str, reason: Option<&str>) -> CapabilityView {
    serde_json::from_value(serde_json::json!({
        "capability_id": "approval.approve",
        "state": state,
        "reason": reason
    }))
    .expect("valid capability")
}

fn hash() -> Sha256Hex {
    serde_json::from_value(serde_json::json!(
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    ))
    .expect("valid hash")
}

fn controls_snapshot_with_enabled_capabilities() -> ConsoleSnapshot {
    let mut snapshot: ConsoleSnapshot =
        serde_json::from_str(include_str!("../../contracts/v1/controls_snapshot.json"))
            .expect("valid shared controls fixture");
    snapshot.shell.capabilities = snapshot
        .command_specs
        .iter()
        .map(|spec| {
            serde_json::from_value::<CapabilityView>(serde_json::json!({
                "capability_id": spec.capability_id,
                "state": "enabled",
                "reason": null
            }))
            .expect("valid enabled capability")
        })
        .collect();
    snapshot
}

fn controls_snapshot_with_only_enabled(command: CommandType) -> ConsoleSnapshot {
    let mut snapshot = controls_snapshot_with_enabled_capabilities();
    snapshot.shell.capabilities = snapshot
        .command_specs
        .iter()
        .map(|spec| {
            let enabled = spec.command_type.as_str() == command.as_str();
            serde_json::from_value::<CapabilityView>(serde_json::json!({
                "capability_id": spec.capability_id,
                "state": if enabled { "enabled" } else { "disabled" },
                "reason": if enabled { None } else { Some("No reviewed adapter is configured.") }
            }))
            .expect("valid capability")
        })
        .collect();
    snapshot
}

fn approved_agent_send_snapshot() -> ConsoleSnapshot {
    let snapshot = controls_snapshot_with_only_enabled(CommandType::AgentSendMessage);
    let mut value = serde_json::to_value(snapshot).expect("serialize controls snapshot");
    value["agents"]["rows"][0]["agent"] = serde_json::json!("v20-product");
    serde_json::from_value(value).expect("approved-agent controls snapshot")
}

fn receipt(command_id: &str, status: &str, code: &str, message: &str) -> CommandReceipt {
    let terminal = matches!(status, "completed" | "failed" | "rejected" | "cancelled");
    serde_json::from_value(serde_json::json!({
        "command_id": command_id,
        "status": status,
        "code": code,
        "safe_message": message,
        "accepted_at_utc": "2026-08-04T12:00:00Z",
        "finished_at_utc": terminal.then_some("2026-08-04T12:01:00Z"),
        "result": terminal.then_some(serde_json::json!({"must_not_render": "secret-shaped"}))
    }))
    .expect("valid receipt")
}

fn safe_id(value: &str) -> SafeId {
    serde_json::from_value(serde_json::Value::String(value.to_owned())).expect("valid safe id")
}

fn timestamp(value: &str) -> UtcTimestamp {
    serde_json::from_value(serde_json::Value::String(value.to_owned())).expect("valid timestamp")
}

fn receipt_envelope(sequence: u64, receipt: CommandReceipt) -> Envelope {
    Envelope {
        schema_version: 1,
        message_id: safe_id(&format!("receipt-message-{sequence}")),
        sequence,
        state_version: 0,
        timestamp_utc: timestamp("2026-08-04T12:01:00Z"),
        message: Message::CommandReceipt(CommandReceiptPayload { receipt }),
    }
}

fn gap_pong(sequence: u64) -> Envelope {
    serde_json::from_value(serde_json::json!({
        "schema_version": 1,
        "message_id": format!("server-gap-{sequence}"),
        "sequence": sequence,
        "state_version": 0,
        "timestamp_utc": "2026-08-04T12:01:00Z",
        "message_type": "pong",
        "payload": {"nonce": "gap"}
    }))
    .expect("valid gap pong")
}

fn approval_confirmation_state() -> AppState {
    let mut state = AppState::controller();
    state.snapshot = Some(controls_snapshot_with_only_enabled(
        CommandType::ApprovalApprove,
    ));
    state.handle(InputEvent::Char('7'));
    state.handle(InputEvent::OpenBrowseRow { panel: 1, index: 0 });
    state.handle(InputEvent::Char(':'));
    let approve = state
        .control_menu()
        .expect("control menu")
        .command_index(CommandType::ApprovalApprove)
        .expect("approve button");
    state.handle(InputEvent::ActivateControl(approve));
    assert!(matches!(
        state.control_overlay(),
        Some(ControlOverlay::Confirmation { .. })
    ));
    state
}

#[test]
fn button_state_uses_server_capability_and_hides_only_irrelevant_controls() {
    assert_eq!(
        button_state(&spec(), &capability("enabled", None), true),
        ButtonState::Enabled
    );
    assert_eq!(
        button_state(
            &spec(),
            &capability("disabled", Some("Approval adapter unavailable.")),
            true,
        ),
        ButtonState::Disabled {
            reason: "Approval adapter unavailable.".to_owned(),
        }
    );
    assert_eq!(
        button_state(&spec(), &capability("enabled", None), false),
        ButtonState::Hidden
    );
}

#[test]
fn rapid_double_activation_reserves_one_unique_command_and_sends_it_once() {
    let mut tracker = CommandTracker::with_generator(CommandIdGenerator::seeded(41, 99));
    let draft = CommandDraft::new(
        CommandType::ApprovalApprove,
        serde_json::json!({"run_id": "run-1", "checkpoint_id": "checkpoint-1"}),
        None,
        "approval.approve:run-1:checkpoint-1",
    );

    let first = tracker
        .prepare(draft.clone(), 7, hash())
        .expect("valid draft");
    let PrepareOutcome::New(pending) = first else {
        panic!("first activation must create a pending command")
    };
    let second = tracker.prepare(draft, 7, hash()).expect("valid replay");
    assert_eq!(
        second,
        PrepareOutcome::Existing(pending.request().command_id.clone())
    );

    assert!(tracker.mark_sent(&pending).is_some());
    assert!(tracker.mark_sent(&pending).is_none());
    assert_eq!(pending.request().command_id.as_str(), "cmd:41:99:1");
}

#[test]
fn tracker_rejects_unknown_receipts_and_exposes_only_safe_receipt_fields() {
    let mut tracker = CommandTracker::with_generator(CommandIdGenerator::seeded(41, 99));
    assert_eq!(
        tracker.apply_receipt(receipt(
            "cmd:41:99:404",
            "running",
            "command-running",
            "Command is running."
        )),
        Err(TrackerError::UnknownReceipt)
    );

    let draft = CommandDraft::new(
        CommandType::ApprovalApprove,
        serde_json::json!({"run_id": "run-1", "checkpoint_id": "checkpoint-1"}),
        None,
        "approval.approve:run-1:checkpoint-1",
    );
    let PrepareOutcome::New(pending) = tracker.prepare(draft, 7, hash()).expect("valid draft")
    else {
        panic!("new command expected")
    };
    tracker.mark_sent(&pending).expect("first send");
    tracker
        .apply_receipt(receipt(
            pending.request().command_id.as_str(),
            "completed",
            "approval-recorded",
            "Approval was recorded.",
        ))
        .expect("known terminal receipt");

    let summary = tracker
        .summary(pending.request().command_id.as_str())
        .expect("tracked summary");
    assert_eq!(summary.state, TrackedCommandState::Completed);
    assert_eq!(summary.code.as_deref(), Some("approval-recorded"));
    assert_eq!(
        summary.safe_message.as_deref(),
        Some("Approval was recorded.")
    );
    assert!(!format!("{summary:?}").contains("must_not_render"));
    assert!(!format!("{summary:?}").contains("secret-shaped"));
}

#[test]
fn terminal_receipt_releases_only_the_in_flight_dedup_binding() {
    let mut tracker = CommandTracker::with_generator(CommandIdGenerator::seeded(41, 99));
    let draft = CommandDraft::new(
        CommandType::ApprovalApprove,
        serde_json::json!({"run_id": "run-1", "checkpoint_id": "checkpoint-1"}),
        None,
        "approval.approve:run-1:checkpoint-1",
    );
    let PrepareOutcome::New(first) = tracker
        .prepare(draft.clone(), 7, hash())
        .expect("first command")
    else {
        panic!("new command expected")
    };
    tracker.mark_sent(&first).expect("first send");
    tracker
        .apply_receipt(receipt(
            first.request().command_id.as_str(),
            "completed",
            "approval-recorded",
            "Approval was recorded.",
        ))
        .expect("terminal receipt");

    let PrepareOutcome::New(second) = tracker.prepare(draft, 8, hash()).expect("later command")
    else {
        panic!("terminal command must not block a later intentional action")
    };
    assert_ne!(first.request().command_id, second.request().command_id);
    assert!(
        tracker
            .summary(first.request().command_id.as_str())
            .is_some()
    );
}

#[test]
fn every_server_spec_keeps_its_server_confirmation_level_when_rendered() {
    let snapshot = controls_snapshot_with_enabled_capabilities();
    assert_eq!(snapshot.command_specs.len(), 31);

    for spec in &snapshot.command_specs {
        let command_type: CommandType = serde_json::from_value(serde_json::Value::String(
            spec.command_type.as_str().to_owned(),
        ))
        .expect("known command type");
        let button = server_button(&snapshot, command_type, "Control", true);
        assert_eq!(button.state, ButtonState::Enabled);
        assert_eq!(button.confirmation_level, Some(spec.confirmation_level));
    }
}

#[test]
fn required_screen_catalog_places_all_approved_command_types() {
    let mut names = [
        Screen::Impact,
        Screen::Portfolio,
        Screen::Orders,
        Screen::Agents,
        Screen::ModelsRegime,
        Screen::Timeline,
        Screen::RiskApprovals,
        Screen::DataEvidence,
        Screen::Memory,
        Screen::System,
    ]
    .into_iter()
    .flat_map(control_definitions_for_screen)
    .map(|definition| definition.command_type.as_str())
    .collect::<Vec<_>>();
    names.sort_unstable();
    names.dedup();

    assert_eq!(names.len(), 31);
}

#[test]
fn viewer_sees_take_control_and_controller_keeps_lock_and_privacy_controls() {
    let viewer = local_controls(AccessState::Viewer, Screen::System);
    assert!(viewer.contains(&LocalControl::TakeControl));
    assert!(viewer.contains(&LocalControl::LockTui));
    assert!(viewer.contains(&LocalControl::ToggleAccountPrivacy));

    let controller = local_controls(AccessState::Controller, Screen::System);
    assert!(!controller.contains(&LocalControl::TakeControl));
    assert!(controller.contains(&LocalControl::LockTui));
    assert!(controller.contains(&LocalControl::ToggleAccountPrivacy));
}

#[test]
fn routed_agent_is_visible_and_only_exact_approved_roles_can_override_it() {
    let mut route = AgentRouteDraft::for_screen(Screen::RiskApprovals);
    assert_eq!(route.selected_agent(), "v20-risk-review");
    assert_eq!(
        route.reason(),
        "Risk and approval context routes to Risk Review."
    );

    route
        .override_agent("v20-development")
        .expect("approved role can be selected before sending");
    assert_eq!(route.selected_agent(), "v20-development");
    assert!(route.override_agent("invented-agent").is_err());
    assert_eq!(route.selected_agent(), "v20-development");
}

#[test]
fn approval_button_requires_confirmation_before_emitting_one_command() {
    let mut state = AppState::controller();
    state.snapshot = Some(controls_snapshot_with_only_enabled(
        CommandType::ApprovalApprove,
    ));
    state.handle(InputEvent::Char('7'));
    state.handle(InputEvent::Right);
    state.handle(InputEvent::Down);
    state.handle(InputEvent::Char(':'));
    let approve = state
        .control_menu()
        .expect("control menu")
        .command_index(CommandType::ApprovalApprove)
        .expect("approve button");

    assert!(
        state
            .handle(InputEvent::ActivateControl(approve))
            .is_empty()
    );
    assert!(matches!(
        state.control_overlay(),
        Some(ControlOverlay::Confirmation { .. })
    ));
    assert!(state.handle(InputEvent::Right).is_empty());
    let actions = state.handle(InputEvent::Enter);
    assert_eq!(actions.len(), 1);
    let ClientAction::Command(request) = &actions[0] else {
        panic!("confirmed action must emit a command")
    };
    assert_eq!(request.command_type, CommandType::ApprovalApprove);
    assert!(
        request
            .confirmation
            .as_ref()
            .is_some_and(|proof| proof.first_confirmed)
    );
}

#[test]
fn disabled_button_opens_its_server_reason_and_emits_no_command() {
    let mut state = AppState::controller();
    state.snapshot = Some(controls_snapshot_with_only_enabled(
        CommandType::ApprovalApprove,
    ));
    state.handle(InputEvent::Char('7'));
    state.handle(InputEvent::Char(':'));
    let pause = state
        .control_menu()
        .expect("control menu")
        .command_index(CommandType::TradingPause)
        .expect("pause trading button");

    assert!(state.handle(InputEvent::ActivateControl(pause)).is_empty());
    assert!(matches!(
        state.control_overlay(),
        Some(ControlOverlay::DisabledReason { reason, .. })
            if reason == "No reviewed adapter is configured."
    ));
}

#[test]
fn viewer_take_control_and_lock_are_local_governed_actions() {
    let mut viewer = AppState::viewer();
    viewer.snapshot = Some(controls_snapshot_with_enabled_capabilities());
    viewer.handle(InputEvent::Char(':'));
    let take_control = viewer
        .control_menu()
        .expect("viewer controls")
        .local_index(LocalControl::TakeControl)
        .expect("take control button");
    assert_eq!(
        viewer.handle(InputEvent::ActivateControl(take_control)),
        vec![ClientAction::RequestLease]
    );

    let mut controller = AppState::controller();
    controller.snapshot = Some(controls_snapshot_with_enabled_capabilities());
    controller.handle(InputEvent::Char(':'));
    let lock = controller
        .control_menu()
        .expect("controller controls")
        .local_index(LocalControl::LockTui)
        .expect("lock button");
    assert_eq!(
        controller.handle(InputEvent::ActivateControl(lock)),
        vec![ClientAction::RequestLock]
    );
    assert_eq!(controller.access, AccessState::Locked);
    assert!(controller.snapshot.is_none());
}

#[test]
fn privacy_button_changes_only_local_preferences() {
    let mut state = AppState::controller();
    state.screen = Screen::System;
    state.snapshot = Some(controls_snapshot_with_enabled_capabilities());
    let snapshot_before = state.snapshot.clone();
    state.handle(InputEvent::Char(':'));
    let privacy = state
        .control_menu()
        .expect("system controls")
        .local_index(LocalControl::ToggleAccountPrivacy)
        .expect("privacy button");

    assert!(
        state
            .handle(InputEvent::ActivateControl(privacy))
            .is_empty()
    );
    assert!(state.preferences().mask_account_details);
    assert_eq!(state.snapshot, snapshot_before);
}

#[test]
fn known_receipt_updates_in_place_and_unknown_receipt_fails_closed() {
    let mut state = AppState::controller();
    state.snapshot = Some(controls_snapshot_with_only_enabled(
        CommandType::ApprovalApprove,
    ));
    state.handle(InputEvent::Char('7'));
    state.handle(InputEvent::Right);
    state.handle(InputEvent::Down);
    state.handle(InputEvent::Char(':'));
    let approve = state
        .control_menu()
        .expect("control menu")
        .command_index(CommandType::ApprovalApprove)
        .expect("approve button");
    state.handle(InputEvent::ActivateControl(approve));
    state.handle(InputEvent::Right);
    let actions = state.handle(InputEvent::Enter);
    let ClientAction::Command(command) = &actions[0] else {
        panic!("command expected")
    };

    assert_eq!(
        state.reduce(receipt_envelope(
            1,
            receipt(
                command.command_id.as_str(),
                "completed",
                "approval-recorded",
                "Approval was recorded."
            )
        )),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(
        state.command_summaries()[0].state,
        TrackedCommandState::Completed
    );

    let mut unknown = AppState::controller();
    assert!(
        unknown
            .reduce(receipt_envelope(
                1,
                receipt(
                    "cmd:1:2:3",
                    "running",
                    "command-running",
                    "Command is running."
                )
            ))
            .is_err()
    );
    assert_eq!(unknown.access, AccessState::ProtocolLockout);
}

#[test]
fn lock_hides_state_immediately_and_still_reduces_a_known_in_flight_receipt() {
    let mut state = AppState::controller();
    state.snapshot = Some(controls_snapshot_with_only_enabled(
        CommandType::ApprovalApprove,
    ));
    state.handle(InputEvent::Char('7'));
    state.handle(InputEvent::OpenBrowseRow { panel: 1, index: 0 });
    state.handle(InputEvent::Char(':'));
    let approve = state
        .control_menu()
        .expect("control menu")
        .command_index(CommandType::ApprovalApprove)
        .expect("approve button");
    state.handle(InputEvent::ActivateControl(approve));
    state.handle(InputEvent::Right);
    let actions = state.handle(InputEvent::Enter);
    let ClientAction::Command(command) = &actions[0] else {
        panic!("command expected")
    };
    let command_id = command.command_id.as_str().to_owned();

    assert_eq!(
        state.handle(InputEvent::LockTui),
        vec![ClientAction::RequestLock]
    );
    assert_eq!(state.access, AccessState::Locked);
    assert!(state.snapshot.is_none());
    assert!(state.control_overlay().is_none());
    assert_eq!(
        state.reduce(receipt_envelope(
            1,
            receipt(
                &command_id,
                "completed",
                "approval-recorded",
                "Approval was recorded."
            )
        )),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(
        state.command_summaries()[0].state,
        TrackedCommandState::Completed
    );
}

#[test]
fn reconnect_keeps_in_flight_command_ids_without_replaying_them() {
    let mut state = AppState::controller();
    state.snapshot = Some(controls_snapshot_with_only_enabled(
        CommandType::ApprovalApprove,
    ));
    state.handle(InputEvent::Char('7'));
    state.handle(InputEvent::OpenBrowseRow { panel: 1, index: 0 });
    state.handle(InputEvent::Char(':'));
    let approve = state
        .control_menu()
        .expect("control menu")
        .command_index(CommandType::ApprovalApprove)
        .expect("approve button");
    state.handle(InputEvent::ActivateControl(approve));
    state.handle(InputEvent::Right);
    let actions = state.handle(InputEvent::Enter);
    let ClientAction::Command(command) = &actions[0] else {
        panic!("command expected")
    };
    let command_id = command.command_id.as_str().to_owned();

    let mut client = FoundationClient::from_app(App::new(state));
    client.fail_connection();
    client.begin_connection();
    let summaries = client.app().state().command_summaries();
    assert_eq!(summaries.len(), 1);
    assert_eq!(summaries[0].command_id, command_id);
    assert_eq!(summaries[0].state, TrackedCommandState::InFlight);
    assert_eq!(client.app().state().access, AccessState::Locked);
}

#[test]
fn context_notes_bind_exact_selected_ids_and_never_treat_work_ids_as_events() {
    let cases = [
        (Screen::Portfolio, '2', 0, NoteTargetType::Stock, "AAPL"),
        (Screen::Orders, '3', 0, NoteTargetType::Order, "order:1"),
        (
            Screen::RiskApprovals,
            '7',
            1,
            NoteTargetType::Approval,
            "approval:1",
        ),
        (
            Screen::Timeline,
            '6',
            0,
            NoteTargetType::AgentEvent,
            "event:1",
        ),
    ];
    for (screen, key, panel, expected_type, expected_id) in cases {
        let mut state = AppState::controller();
        state.snapshot = Some(controls_snapshot_with_only_enabled(CommandType::NoteAdd));
        state.handle(InputEvent::Char(key));
        state.handle(InputEvent::OpenBrowseRow { panel, index: 0 });
        state.handle(InputEvent::Char(':'));
        let note = state
            .control_menu()
            .expect("context controls")
            .command_index(CommandType::NoteAdd)
            .unwrap_or_else(|| panic!("note button for {screen:?}"));
        state.handle(InputEvent::ActivateControl(note));
        for character in "reviewed note".chars() {
            state.handle(InputEvent::Char(character));
        }
        let actions = state.handle(InputEvent::Enter);
        let ClientAction::Command(command) = &actions[0] else {
            panic!("note command expected for {screen:?}")
        };
        let CommandPayload::NoteAdd(payload) = &command.payload else {
            panic!("note payload expected")
        };
        assert_eq!(payload.target_type, expected_type);
        assert_eq!(payload.target_id.as_str(), expected_id);
        assert_eq!(payload.body.as_str(), "reviewed note");
    }

    let mut agents = AppState::controller();
    agents.snapshot = Some(controls_snapshot_with_only_enabled(CommandType::NoteAdd));
    agents.handle(InputEvent::Char('4'));
    agents.handle(InputEvent::Down);
    agents.handle(InputEvent::Char(':'));
    assert!(
        agents
            .control_menu()
            .expect("agent controls")
            .command_index(CommandType::NoteAdd)
            .is_none(),
        "an AgentCard work_id is not an agent-event ID"
    );
}

#[test]
fn required_screen_controls_are_visible_and_the_action_bar_is_mouse_reachable() {
    let cases = [
        ('4', 1, &["Send", "Pause", "Stop", "Retry", "Priority"][..]),
        (
            '7',
            0,
            &["Edit Proposed", "Pause Trading", "Emergency Stop"][..],
        ),
        (
            '7',
            1,
            &[
                "Pause Trading",
                "Emergency Stop",
                "Approve",
                "Hold",
                "Reject",
                "Rework",
            ][..],
        ),
        (
            '5',
            1,
            &["Candidate Detail", "Request Approval", "Request Rollback"][..],
        ),
        (
            '0',
            0,
            &[
                "Pause Service",
                "Restart Service",
                "Start V20",
                "Stop Safely",
                "Force Stop",
                "Prepare PC",
                "Backup Now",
                "Restore",
                "Push",
                "Lock TUI",
            ][..],
        ),
    ];
    for (key, panel, labels) in cases {
        let mut state = AppState::controller();
        state.snapshot = Some(controls_snapshot_with_enabled_capabilities());
        state.handle(InputEvent::Char(key));
        state.handle(InputEvent::OpenBrowseRow { panel, index: 0 });
        let text = render_state(&state, 140, 42);
        assert!(text.contains("CONTROLS - click or : menu"), "{text}");
        for label in labels {
            assert!(text.contains(label), "missing {label:?}\n{text}");
        }
    }

    let mut state = AppState::controller();
    state.snapshot = Some(controls_snapshot_with_enabled_capabilities());
    state.handle(InputEvent::Char('4'));
    state.handle(InputEvent::OpenBrowseRow { panel: 1, index: 0 });
    let area = Rect::new(0, 0, 140, 42);
    let action_bar = split_control_area(
        vesper_ratatui_console::layout::shell_layout(area, state.display_mode()).body,
        state.display_mode(),
    )
    .1;
    let click = MouseEvent {
        kind: MouseEventKind::Down(MouseButton::Left),
        column: action_bar.x + 2,
        row: action_bar.y + 1,
        modifiers: KeyModifiers::NONE,
    };
    assert_eq!(
        mouse_to_input(click, area, &state),
        Some(InputEvent::ActivateControl(0))
    );

    let mut risk = AppState::controller();
    risk.snapshot = Some(controls_snapshot_with_only_enabled(
        CommandType::ApprovalApprove,
    ));
    risk.handle(InputEvent::Char('7'));
    risk.handle(InputEvent::OpenBrowseRow { panel: 1, index: 0 });
    let layout = vesper_ratatui_console::layout::shell_layout(area, risk.display_mode());
    let action_bar = split_control_area(layout.body, risk.display_mode()).1;
    let menu = risk.visible_control_menu().expect("risk controls");
    let approve = menu
        .command_index(CommandType::ApprovalApprove)
        .expect("approve button");
    let approve_click = MouseEvent {
        kind: MouseEventKind::Down(MouseButton::Left),
        column: action_bar.x + 2 + u16::try_from(approve).expect("index") * 26,
        row: action_bar.y + 1,
        modifiers: KeyModifiers::NONE,
    };
    let activation = mouse_to_input(approve_click, area, &risk).expect("button hit");
    assert!(risk.handle(activation).is_empty());
    assert!(matches!(
        risk.control_overlay(),
        Some(ControlOverlay::Confirmation { .. })
    ));
    let modal = control_overlay_area(layout.body);
    let confirm_click = MouseEvent {
        kind: MouseEventKind::Down(MouseButton::Left),
        column: modal.right() - 3,
        row: modal.bottom() - 2,
        modifiers: KeyModifiers::NONE,
    };
    let actions =
        risk.handle(mouse_to_input(confirm_click, area, &risk).expect("confirmation hit"));
    assert!(matches!(actions.as_slice(), [ClientAction::Command(_)]));
}

#[test]
fn agent_send_button_uses_chat_route_and_disabled_capability_stays_inert() {
    let area = Rect::new(0, 0, 140, 42);
    let send_click = |state: &AppState| {
        let action_bar = split_control_area(
            vesper_ratatui_console::layout::shell_layout(area, state.display_mode()).body,
            state.display_mode(),
        )
        .1;
        mouse_to_input(
            MouseEvent {
                kind: MouseEventKind::Down(MouseButton::Left),
                column: action_bar.x + 2,
                row: action_bar.y + 1,
                modifiers: KeyModifiers::NONE,
            },
            area,
            state,
        )
        .expect("Send button hit")
    };

    let mut keyboard = AppState::controller();
    keyboard.snapshot = Some(controls_snapshot_with_only_enabled(
        CommandType::AgentSendMessage,
    ));
    keyboard.handle(InputEvent::Char('4'));
    assert!(keyboard.handle(InputEvent::Char('i')).is_empty());
    assert_eq!(keyboard.mode, LocalMode::AgentSelector);

    let mut enabled = AppState::controller();
    enabled.snapshot = Some(controls_snapshot_with_only_enabled(
        CommandType::AgentSendMessage,
    ));
    enabled.handle(InputEvent::Char('4'));
    let click = send_click(&enabled);
    assert_eq!(click, InputEvent::ActivateControl(0));
    assert!(enabled.handle(click).is_empty());
    assert_eq!(enabled.mode, keyboard.mode);
    assert!(enabled.control_overlay().is_none());
    assert!(matches!(
        enabled.handle(InputEvent::SelectChatAgent(0)).as_slice(),
        [ClientAction::ChatHistoryRequest(_)]
    ));
    assert_eq!(enabled.mode, LocalMode::AgentChat);
    assert!(enabled.handle(InputEvent::FocusChatInput).is_empty());
    assert_eq!(enabled.mode, LocalMode::AgentInput);

    let mut disabled = AppState::controller();
    disabled.snapshot = Some(controls_snapshot_with_only_enabled(
        CommandType::AgentEnqueue,
    ));
    disabled.handle(InputEvent::Char('4'));
    let click = send_click(&disabled);
    assert!(disabled.handle(click).is_empty());
    assert_eq!(disabled.mode, LocalMode::Menu);
    assert!(disabled.selected_chat_agent().is_none());
    assert!(matches!(
        disabled.control_overlay(),
        Some(ControlOverlay::DisabledReason { label, reason })
            if label == "Send" && reason == "No reviewed adapter is configured."
    ));
}

#[test]
fn selected_agent_send_button_restores_exact_browse_or_open_origin() {
    for origin in [LocalMode::Browse, LocalMode::Open] {
        let mut state = AppState::controller();
        state.snapshot = Some(approved_agent_send_snapshot());
        state.handle(InputEvent::Char('4'));
        state.handle(InputEvent::OpenBrowseRow { panel: 1, index: 0 });
        if origin == LocalMode::Browse {
            state.handle(InputEvent::Escape);
        }
        assert_eq!(state.mode, origin);

        state.handle(InputEvent::Char(':'));
        let send = state
            .control_menu()
            .expect("agent controls")
            .command_index(CommandType::AgentSendMessage)
            .expect("Send button");
        assert!(matches!(
            state.handle(InputEvent::ActivateControl(send)).as_slice(),
            [ClientAction::ChatHistoryRequest(_)]
        ));
        assert_eq!(state.mode, LocalMode::AgentChat);
        assert_eq!(
            state.selected_chat_agent().map(|agent| agent.as_str()),
            Some("v20-product")
        );

        assert!(state.handle(InputEvent::Escape).is_empty());
        assert_eq!(state.mode, origin, "Esc must restore {origin:?}");
    }
}

#[test]
fn send_selector_fallback_preserves_open_origin_through_escape_or_chat() {
    for select_chat in [false, true] {
        let mut state = AppState::controller();
        state.snapshot = Some(controls_snapshot_with_only_enabled(
            CommandType::AgentSendMessage,
        ));
        state.handle(InputEvent::Char('4'));
        state.handle(InputEvent::OpenBrowseRow { panel: 1, index: 0 });
        assert_eq!(state.mode, LocalMode::Open);

        state.handle(InputEvent::Char(':'));
        let send = state
            .control_menu()
            .expect("agent controls")
            .command_index(CommandType::AgentSendMessage)
            .expect("Send button");
        assert!(state.handle(InputEvent::ActivateControl(send)).is_empty());
        assert_eq!(state.mode, LocalMode::AgentSelector);

        if select_chat {
            assert!(matches!(
                state.handle(InputEvent::SelectChatAgent(0)).as_slice(),
                [ClientAction::ChatHistoryRequest(_)]
            ));
            assert_eq!(state.mode, LocalMode::AgentChat);
        }
        assert!(state.handle(InputEvent::Escape).is_empty());
        assert_eq!(state.mode, LocalMode::Open);
    }
}

#[test]
fn constrained_action_bar_uses_stable_breakpoints_and_keeps_screen_space() {
    let (compact_body, compact_bar) =
        split_control_area(Rect::new(0, 0, 120, 16), DisplayMode::Compact);
    assert_eq!((compact_body.height, compact_bar.height), (10, 6));

    let (standard_body, standard_bar) =
        split_control_area(Rect::new(0, 0, 120, 15), DisplayMode::Standard);
    assert_eq!((standard_body.height, standard_bar.height), (11, 4));

    let (large_body, large_bar) =
        split_control_area(Rect::new(0, 0, 120, 13), DisplayMode::LargeText);
    assert_eq!((large_body.height, large_bar.height), (13, 0));

    let mut state = AppState::controller();
    state.snapshot = Some(controls_snapshot_with_enabled_capabilities());
    state.set_display_mode(DisplayMode::LargeText);
    let area = Rect::new(0, 0, 80, 24);
    let rendered = render_state(&state, area.width, area.height);
    assert!(
        rendered.contains("AAPL"),
        "primary holding must remain visible"
    );
    assert!(
        rendered.contains(": Actions"),
        "collapsed controls stay reachable"
    );
    let footer = vesper_ratatui_console::layout::shell_layout(area, state.display_mode()).footer;
    let click = MouseEvent {
        kind: MouseEventKind::Down(MouseButton::Left),
        column: footer.x + 3,
        row: footer.y + 1,
        modifiers: KeyModifiers::NONE,
    };
    assert_eq!(
        mouse_to_input(click, area, &state),
        Some(InputEvent::Char(':'))
    );
}

fn render_state(state: &AppState, width: u16, height: u16) -> String {
    let backend = TestBackend::new(width, height);
    let mut terminal = Terminal::new(backend).expect("test terminal");
    terminal
        .draw(|frame| render(frame, state))
        .expect("render succeeds");
    buffer_text(terminal.backend().buffer())
}

fn buffer_text(buffer: &Buffer) -> String {
    let area = buffer.area;
    (area.y..area.bottom())
        .map(|y| {
            (area.x..area.right())
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
                .trim_end()
                .to_owned()
        })
        .collect::<Vec<_>>()
        .join("\n")
}

#[test]
fn reviewed_payload_facts_do_not_change_after_the_menu_opens() {
    let mut state = AppState::controller();
    state.snapshot = Some(controls_snapshot_with_only_enabled(
        CommandType::ApprovalApprove,
    ));
    state.handle(InputEvent::Char('7'));
    state.handle(InputEvent::OpenBrowseRow { panel: 1, index: 0 });
    state.handle(InputEvent::Char(':'));
    let approve = state
        .control_menu()
        .expect("control menu")
        .command_index(CommandType::ApprovalApprove)
        .expect("approve button");

    state.snapshot.as_mut().expect("snapshot").risk.approvals[0].run_id = safe_id("run:new");
    state.handle(InputEvent::ActivateControl(approve));
    state.handle(InputEvent::Right);
    let actions = state.handle(InputEvent::Enter);
    let ClientAction::Command(command) = &actions[0] else {
        panic!("command expected")
    };
    let CommandPayload::Approval(payload) = &command.payload else {
        panic!("approval payload expected")
    };
    assert_eq!(payload.run_id.as_str(), "run:1");
}

#[test]
fn changed_control_pair_invalidates_the_reviewed_button() {
    let mut state = AppState::controller();
    state.snapshot = Some(controls_snapshot_with_only_enabled(
        CommandType::ApprovalApprove,
    ));
    state.handle(InputEvent::Char('7'));
    state.handle(InputEvent::OpenBrowseRow { panel: 1, index: 0 });
    state.handle(InputEvent::Char(':'));
    let approve = state
        .control_menu()
        .expect("control menu")
        .command_index(CommandType::ApprovalApprove)
        .expect("approve button");
    state.snapshot.as_mut().expect("snapshot").control_version += 1;

    assert!(
        state
            .handle(InputEvent::ActivateControl(approve))
            .is_empty()
    );
    assert!(matches!(
        state.control_overlay(),
        Some(ControlOverlay::DisabledReason { reason, .. })
            if reason == "Controller controls changed. Review the action again."
    ));
}

#[test]
fn sequence_gap_cancels_prepared_modal_and_submit_rechecks_the_current_pair() {
    let mut resync = approval_confirmation_state();
    assert_eq!(resync.command_summaries().len(), 1);
    assert_eq!(
        resync.reduce(gap_pong(2)),
        Ok(ReduceOutcome::RequestSnapshot)
    );
    assert!(resync.awaiting_snapshot());
    assert!(resync.control_overlay().is_none());
    assert!(resync.command_summaries().is_empty());
    assert!(resync.handle(InputEvent::Enter).is_empty());

    let mut changed = approval_confirmation_state();
    changed.snapshot.as_mut().expect("snapshot").control_version += 1;
    changed.handle(InputEvent::Right);
    assert!(changed.handle(InputEvent::Enter).is_empty());
    assert!(changed.command_summaries().is_empty());
    assert!(matches!(
        changed.control_overlay(),
        Some(ControlOverlay::DisabledReason { label, reason })
            if label == "Controls Updated" && reason.contains("changed")
    ));
}

#[test]
fn duplicate_receipt_sequence_requires_exact_connection_scoped_evidence() {
    let mut state = approval_confirmation_state();
    state.handle(InputEvent::Right);
    let actions = state.handle(InputEvent::Enter);
    let [ClientAction::Command(command)] = actions.as_slice() else {
        panic!("command expected")
    };
    let original = receipt(
        command.command_id.as_str(),
        "running",
        "command-running",
        "Command is running.",
    );
    assert_eq!(
        state.reduce(receipt_envelope(1, original.clone())),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(
        state.reduce(receipt_envelope(1, original.clone())),
        Ok(ReduceOutcome::Ignored)
    );

    let rewritten = receipt(
        command.command_id.as_str(),
        "running",
        "command-running",
        "Changed message.",
    );
    assert!(state.reduce(receipt_envelope(1, rewritten)).is_err());
    assert_eq!(state.access, AccessState::ProtocolLockout);

    let mut retained = approval_confirmation_state();
    retained.handle(InputEvent::Right);
    let sent = retained.handle(InputEvent::Enter);
    let [ClientAction::Command(command)] = sent.as_slice() else {
        panic!("command expected")
    };
    let prior = receipt(
        command.command_id.as_str(),
        "running",
        "command-running",
        "Command is running.",
    );
    retained
        .reduce(receipt_envelope(1, prior.clone()))
        .expect("first receipt");
    retained.fail_connection();
    assert_eq!(
        retained.reduce(receipt_envelope(1, prior.clone())),
        Ok(ReduceOutcome::Ignored),
        "connection failure must retain sequence evidence"
    );
    let mut client = FoundationClient::from_app(App::new(retained));
    client.begin_connection();
    assert!(
        client.app_mut().reduce(receipt_envelope(1, prior)).is_err(),
        "a new connection must clear prior sequence evidence"
    );
}

#[test]
fn hold_reject_and_enqueue_collect_visible_inputs_before_confirmation() {
    for command_type in [CommandType::ApprovalHold, CommandType::ApprovalReject] {
        let mut state = AppState::controller();
        state.snapshot = Some(controls_snapshot_with_only_enabled(command_type));
        state.handle(InputEvent::Char('7'));
        state.handle(InputEvent::OpenBrowseRow { panel: 1, index: 0 });
        state.handle(InputEvent::Char(':'));
        let index = state
            .control_menu()
            .expect("risk controls")
            .command_index(command_type)
            .expect("reason control");
        state.handle(InputEvent::ActivateControl(index));
        assert!(matches!(
            state.control_overlay(),
            Some(ControlOverlay::ReasonForm(_))
        ));
        for character in "operator note".chars() {
            state.handle(InputEvent::Char(character));
        }
        state.handle(InputEvent::Enter);
        state.handle(InputEvent::Right);
        let actions = state.handle(InputEvent::Enter);
        let ClientAction::Command(command) = &actions[0] else {
            panic!("review decision command expected")
        };
        assert_eq!(command.command_type, command_type);
        assert!(
            command
                .reason
                .as_ref()
                .is_some_and(|reason| reason.as_str().contains("operator note"))
        );
    }

    let mut state = AppState::controller();
    state.snapshot = Some(controls_snapshot_with_only_enabled(
        CommandType::AgentEnqueue,
    ));
    state.handle(InputEvent::Char('4'));
    state.handle(InputEvent::Char(':'));
    let enqueue = state
        .control_menu()
        .expect("agent controls")
        .command_index(CommandType::AgentEnqueue)
        .expect("enqueue control");
    state.handle(InputEvent::ActivateControl(enqueue));
    assert!(matches!(
        state.control_overlay(),
        Some(ControlOverlay::AgentEnqueueForm(_))
    ));
    state.handle(InputEvent::Right);
    state.handle(InputEvent::Up);
    for character in "Review portfolio drift".chars() {
        state.handle(InputEvent::Char(character));
    }
    state.handle(InputEvent::Enter);
    state.handle(InputEvent::Right);
    let actions = state.handle(InputEvent::Enter);
    let ClientAction::Command(command) = &actions[0] else {
        panic!("enqueue command expected")
    };
    let CommandPayload::AgentEnqueue(payload) = &command.payload else {
        panic!("enqueue payload expected")
    };
    assert_eq!(payload.agent_id.as_str(), "v20-development");
    assert_eq!(payload.title.as_str(), "Review portfolio drift");
    assert_eq!(payload.objective.as_str(), "Review portfolio drift");
    assert_eq!(payload.priority.get(), 55);
}

#[test]
fn exact_duplicate_receipts_are_idempotent_but_receipt_rewrites_fail() {
    let mut tracker = CommandTracker::with_generator(CommandIdGenerator::seeded(41, 99));
    let draft = CommandDraft::new(
        CommandType::ApprovalApprove,
        serde_json::json!({"run_id": "run-1", "checkpoint_id": "checkpoint-1"}),
        None,
        "approval.approve:run-1:checkpoint-1",
    );
    let PrepareOutcome::New(pending) = tracker.prepare(draft, 7, hash()).expect("draft") else {
        panic!("new command expected")
    };
    tracker.mark_sent(&pending).expect("sent");
    let running = receipt(
        pending.request().command_id.as_str(),
        "running",
        "command-running",
        "Command is running.",
    );
    tracker
        .apply_receipt(running.clone())
        .expect("first running receipt");
    tracker
        .apply_receipt(running)
        .expect("exact duplicate is safe");
    assert_eq!(
        tracker.apply_receipt(receipt(
            pending.request().command_id.as_str(),
            "running",
            "command-running",
            "Changed message.",
        )),
        Err(TrackerError::InvalidTransition)
    );

    let mut accepted = CommandTracker::with_generator(CommandIdGenerator::seeded(42, 100));
    let draft = CommandDraft::new(
        CommandType::ApprovalApprove,
        serde_json::json!({"run_id": "run-2", "checkpoint_id": "checkpoint-2"}),
        None,
        "approval.approve:run-2:checkpoint-2",
    );
    let PrepareOutcome::New(pending) = accepted.prepare(draft, 7, hash()).expect("draft") else {
        panic!("new command expected")
    };
    accepted.mark_sent(&pending).expect("sent");
    accepted
        .apply_receipt(receipt(
            pending.request().command_id.as_str(),
            "accepted",
            "command-accepted",
            "Command was accepted.",
        ))
        .expect("accepted");
    assert_eq!(
        accepted.apply_receipt(receipt(
            pending.request().command_id.as_str(),
            "rejected",
            "stale-state",
            "Control state changed.",
        )),
        Err(TrackerError::InvalidTransition)
    );
}

#[test]
fn control_visual_state_matrix_covers_themes_large_text_modals_receipts_and_viewer() {
    insta::assert_snapshot!(
        "controls_warm_standard",
        visual_state_matrix(Theme::WarmWhite, DisplayMode::Standard, 120, 36)
    );
    insta::assert_snapshot!(
        "controls_charcoal_standard",
        visual_state_matrix(Theme::Charcoal, DisplayMode::Standard, 120, 36)
    );
    insta::assert_snapshot!(
        "controls_warm_large_text",
        visual_state_matrix(Theme::WarmWhite, DisplayMode::LargeText, 100, 30)
    );
}

fn visual_state_matrix(theme: Theme, display_mode: DisplayMode, width: u16, height: u16) -> String {
    let snapshot = controls_snapshot_with_enabled_capabilities();
    let overlays = [
        (
            "NONE",
            confirmation_overlay(&snapshot, CommandType::NoteAdd),
        ),
        (
            "CONFIRM",
            confirmation_overlay(&snapshot, CommandType::ApprovalApprove),
        ),
        (
            "DOUBLE CONFIRM",
            confirmation_overlay(&snapshot, CommandType::TradingEmergencyStop),
        ),
        (
            "TYPED LIVE",
            confirmation_overlay(&snapshot, CommandType::ModeEnableLive),
        ),
        (
            "DISABLED REASON",
            ControlOverlay::DisabledReason {
                label: "Restore".to_owned(),
                reason: "Validated restore preview is unavailable.".to_owned(),
            },
        ),
        (
            "STALE REJECTED",
            ControlOverlay::DisabledReason {
                label: "Controls Updated".to_owned(),
                reason: "Controller controls changed. Review the action again.".to_owned(),
            },
        ),
    ];
    let mut sections = vec![format!("THEME {theme:?} | MODE {display_mode:?}")];
    for (label, overlay) in overlays {
        sections.push(format!(
            "=== {label} ===\n{}",
            render_overlay_text(&overlay, theme, width, 18)
        ));
    }
    for (status, code, message) in [
        ("rejected", "stale-state", "Control state changed."),
        ("running", "command-running", "Command is running."),
        ("completed", "approval-recorded", "Approval was recorded."),
        ("failed", "command-failed", "Command failed safely."),
    ] {
        let mut state = state_with_receipt(status, code, message);
        state.set_theme(theme);
        state.set_display_mode(display_mode);
        sections.push(format!(
            "=== RECEIPT {} ===\n{}",
            status.to_uppercase(),
            render_state(&state, width, height)
        ));
    }
    let mut viewer = AppState::viewer();
    viewer.snapshot = Some(snapshot);
    viewer.set_theme(theme);
    viewer.set_display_mode(display_mode);
    sections.push(format!(
        "=== VIEWER ===\n{}",
        render_state(&viewer, width, height)
    ));
    normalize_command_ids(sections.join("\n"))
}

fn normalize_command_ids(mut text: String) -> String {
    let mut start = 0;
    while let Some(relative) = text[start..].find("cmd:") {
        let command_start = start + relative;
        let command_end = text[command_start..]
            .char_indices()
            .take_while(|(_, character)| {
                character.is_ascii_digit()
                    || *character == ':'
                    || *character == 'c'
                    || *character == 'm'
                    || *character == 'd'
            })
            .last()
            .map_or(command_start + 4, |(index, character)| {
                command_start + index + character.len_utf8()
            });
        text.replace_range(command_start..command_end, "cmd:PID:TICKS:COUNT");
        start = command_start + "cmd:PID:TICKS:COUNT".len();
    }
    text
}

fn confirmation_overlay(snapshot: &ConsoleSnapshot, command_type: CommandType) -> ControlOverlay {
    let spec = snapshot
        .command_specs
        .iter()
        .find(|spec| spec.command_type.as_str() == command_type.as_str())
        .expect("command spec");
    let payload = match command_type {
        CommandType::NoteAdd => serde_json::json!({
            "target_type": "stock",
            "target_id": "AAPL",
            "body": "Reviewed note",
            "visibility": "private",
        }),
        CommandType::ApprovalApprove => {
            serde_json::json!({"run_id": "run:1", "checkpoint_id": "checkpoint:1"})
        }
        CommandType::TradingEmergencyStop => serde_json::json!({}),
        CommandType::ModeEnableLive => {
            serde_json::json!({"desired_portfolio_id": "portfolio:candidate"})
        }
        _ => unreachable!("visual confirmation cases are explicit"),
    };
    let reason = (command_type != CommandType::NoteAdd).then_some("Reviewed action");
    let request: CommandRequest = serde_json::from_value(serde_json::json!({
        "command_id": format!("cmd:7:8:{}", command_type.as_str().len()),
        "command_type": command_type,
        "reviewed_control_version": snapshot.control_version,
        "reviewed_control_hash": snapshot.control_hash,
        "reason": reason,
        "confirmation": null,
        "payload": payload,
    }))
    .expect("valid visual command");
    ControlOverlay::Confirmation {
        label: command_type.as_str().to_owned(),
        state: Box::new(begin_confirmation(
            spec,
            PendingCommand::new(request, command_type.as_str()),
        )),
    }
}

fn render_overlay_text(overlay: &ControlOverlay, theme: Theme, width: u16, height: u16) -> String {
    let backend = TestBackend::new(width, height);
    let mut terminal = Terminal::new(backend).expect("test terminal");
    terminal
        .draw(|frame| render_control_overlay(frame, frame.area(), overlay, theme.palette()))
        .expect("overlay renders");
    buffer_text(terminal.backend().buffer())
}

fn state_with_receipt(status: &str, code: &str, message: &str) -> AppState {
    let mut state = AppState::controller();
    state.snapshot = Some(controls_snapshot_with_only_enabled(
        CommandType::ApprovalApprove,
    ));
    state.handle(InputEvent::Char('7'));
    state.handle(InputEvent::OpenBrowseRow { panel: 1, index: 0 });
    state.handle(InputEvent::Char(':'));
    let approve = state
        .control_menu()
        .expect("control menu")
        .command_index(CommandType::ApprovalApprove)
        .expect("approve button");
    state.handle(InputEvent::ActivateControl(approve));
    state.handle(InputEvent::Right);
    let actions = state.handle(InputEvent::Enter);
    let ClientAction::Command(command) = &actions[0] else {
        panic!("command expected")
    };
    state
        .reduce(receipt_envelope(
            1,
            receipt(command.command_id.as_str(), status, code, message),
        ))
        .expect("receipt reduces");
    state
}
