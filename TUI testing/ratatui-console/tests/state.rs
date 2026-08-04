use serde_json::{Value, json};

use vesper_ratatui_console::contract::Envelope;
use vesper_ratatui_console::input::InputEvent;
use vesper_ratatui_console::state::{
    AccessState, AppState, AuthFeedback, ClientAction, ReduceOutcome, Screen,
};

fn envelope(sequence: u64, state_version: u64, message_type: &str, payload: Value) -> Envelope {
    serde_json::from_value(json!({
        "schema_version": 1,
        "message_id": format!("server:{sequence}"),
        "sequence": sequence,
        "state_version": state_version,
        "timestamp_utc": "2026-08-03T00:00:00Z",
        "message_type": message_type,
        "payload": payload,
    }))
    .expect("valid test envelope")
}

fn snapshot(sequence: u64, state_version: u64, regime: &str) -> Envelope {
    let mut snapshot: Value = serde_json::from_slice(include_bytes!(
        "../../contracts/v1/console_snapshot_empty_command_specs.json"
    ))
    .expect("valid shared console snapshot");
    snapshot["shell"]["state_version"] = json!(state_version);
    snapshot["shell"]["header"]["regime_label"] = json!(regime);
    envelope(
        sequence,
        state_version,
        "snapshot",
        json!({"snapshot": snapshot}),
    )
}

fn server_hello(sequence: u64, requires_setup: bool) -> Envelope {
    envelope(
        sequence,
        0,
        "server-hello",
        json!({
            "server_version": "0.1.0",
            "requires_setup": requires_setup
        }),
    )
}

fn auth_result(sequence: u64, success: bool, access_state: &str) -> Envelope {
    envelope(
        sequence,
        0,
        "auth-result",
        json!({
            "success": success,
            "access_state": access_state,
            "reason": if success { Value::Null } else { json!("Unlock failed.") }
        }),
    )
}

fn lease_result(sequence: u64, status: &str) -> Envelope {
    envelope(
        sequence,
        0,
        "lease-result",
        json!({
            "status": status,
            "reason": if status == "lease-held" {
                json!("Another authenticated session has control.")
            } else {
                Value::Null
            }
        }),
    )
}

fn lock_result(sequence: u64, state_version: u64) -> Envelope {
    envelope(
        sequence,
        state_version,
        "lock-result",
        json!({ "locked": true }),
    )
}

fn pong(sequence: u64, state_version: u64, nonce: &str) -> Envelope {
    envelope(sequence, state_version, "pong", json!({ "nonce": nonce }))
}

fn event(sequence: u64, state_version: u64) -> Envelope {
    let snapshot: Value = serde_json::from_slice(include_bytes!(
        "../../contracts/v1/console_snapshot_empty_command_specs.json"
    ))
    .expect("valid shared console snapshot");
    let screen_meta = |name: &str| {
        json!({
            "freshness": snapshot[name]["freshness"].clone(),
            "as_of_utc": snapshot[name]["as_of_utc"].clone(),
            "source": snapshot[name]["source"].clone(),
            "error": snapshot[name]["error"].clone(),
        })
    };
    envelope(
        sequence,
        state_version,
        "event",
        json!({
            "entity_type": "alert-row",
            "entity_id": "alert:1",
            "operation": "remove",
            "entity": null,
            "targets": ["shell.alerts"],
            "presentation": {
                "generated_at_utc": snapshot["shell"]["generated_at_utc"].clone(),
                "header": snapshot["shell"]["header"].clone(),
                "control_version": snapshot["control_version"].clone(),
                "control_hash": snapshot["control_hash"].clone(),
                "window_omissions": snapshot["window_omissions"].clone(),
                "impact": screen_meta("impact"),
                "portfolio": screen_meta("portfolio"),
                "orders": screen_meta("orders"),
                "agents": screen_meta("agents"),
                "models": screen_meta("models"),
                "timeline": screen_meta("timeline"),
                "risk": screen_meta("risk"),
                "data": screen_meta("data"),
                "memory": screen_meta("memory"),
                "system": screen_meta("system"),
                "portfolio_rank_source": snapshot["portfolio"]["rank_source"].clone(),
                "timeline_hidden_event_count": snapshot["timeline"]["hidden_event_count"].clone(),
            }
        }),
    )
}

#[test]
fn events_request_a_full_snapshot_without_applying_partial_state() {
    let mut state = AppState::controller();
    assert_eq!(
        state.reduce(snapshot(1, 1, "Before")),
        Ok(ReduceOutcome::Changed)
    );

    assert_eq!(
        state.reduce(event(2, 2)),
        Ok(ReduceOutcome::RequestSnapshot)
    );
    assert!(state.snapshot.is_none());
    assert_eq!(
        state.reduce(snapshot(3, 2, "After")),
        Ok(ReduceOutcome::Changed)
    );
    assert!(state.snapshot.is_some());
}

#[test]
fn gapped_and_stale_events_both_request_a_full_snapshot() {
    let mut state = AppState::controller();
    assert_eq!(
        state.reduce(snapshot(1, 2, "Current")),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(
        state.reduce(event(2, 1)),
        Ok(ReduceOutcome::RequestSnapshot)
    );
    assert!(state.snapshot.is_none());

    let mut state = AppState::controller();
    assert_eq!(
        state.reduce(snapshot(1, 2, "Current")),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(
        state.reduce(event(3, 3)),
        Ok(ReduceOutcome::RequestSnapshot)
    );
    assert!(state.snapshot.is_none());
}

#[test]
fn events_before_authentication_fail_closed() {
    let mut state = AppState::locked();
    let error = state
        .reduce(event(1, 1))
        .expect_err("event must fail closed");

    assert_eq!(error.code, "state");
    assert_eq!(state.access, AccessState::ProtocolLockout);
    assert!(state.snapshot.is_none());
}

#[test]
fn number_keys_select_all_ten_screens_after_unlock() {
    let mut state = AppState::controller();

    for (key, expected) in [
        ('1', Screen::Impact),
        ('2', Screen::Portfolio),
        ('3', Screen::Orders),
        ('4', Screen::Agents),
        ('5', Screen::ModelsRegime),
        ('6', Screen::Timeline),
        ('7', Screen::RiskApprovals),
        ('8', Screen::DataEvidence),
        ('9', Screen::Memory),
        ('0', Screen::System),
    ] {
        state.handle(InputEvent::Char(key));
        assert_eq!(state.screen, expected);
    }
}

#[test]
fn manual_lock_hides_content_and_blocks_auth_until_lock_result() {
    let mut state = AppState::controller();
    assert_eq!(
        state.reduce(snapshot(1, 7, "First")),
        Ok(ReduceOutcome::Changed)
    );

    assert_eq!(
        state.handle(InputEvent::LockTui),
        vec![ClientAction::RequestLock]
    );
    assert_eq!(state.access, AccessState::Locked);
    assert!(state.snapshot.is_none());
    assert!(state.lock_pending());
    state.handle(InputEvent::Char('p'));
    assert!(state.handle(InputEvent::Enter).is_empty());
    assert_eq!(state.masked_auth_input(), "");

    let result = state.reduce(envelope(2, 7, "lock-result", json!({ "locked": true })));
    assert_eq!(result, Ok(ReduceOutcome::Changed));
    assert_eq!(state.access, AccessState::Locked);
    assert!(state.snapshot.is_none());
    assert!(!state.lock_pending());
}

#[test]
fn manual_lock_ignores_an_expected_snapshot_until_lock_result() {
    let mut state = AppState::locked();
    state.reduce(server_hello(1, false)).unwrap();
    state.handle(InputEvent::Char('p'));
    state.handle(InputEvent::Enter);
    assert_eq!(
        state.reduce(auth_result(2, true, "viewer")),
        Ok(ReduceOutcome::RequestSnapshot)
    );
    state.handle(InputEvent::LockTui);

    assert_eq!(
        state.reduce(snapshot(3, 1, "In flight")),
        Ok(ReduceOutcome::Ignored)
    );
    assert_eq!(state.access, AccessState::Locked);
    assert!(state.snapshot.is_none());
    assert!(state.lock_pending());
    assert_eq!(state.reduce(lock_result(4, 1)), Ok(ReduceOutcome::Changed));
}

#[test]
fn manual_lock_rejects_an_in_flight_snapshot_with_mismatched_versions() {
    let mut state = AppState::locked();
    state.reduce(server_hello(1, false)).unwrap();
    state.handle(InputEvent::Char('p'));
    state.handle(InputEvent::Enter);
    state.reduce(auth_result(2, true, "viewer")).unwrap();
    state.handle(InputEvent::LockTui);
    let mut mismatch = snapshot(3, 1, "Mismatch");
    mismatch.state_version = 2;

    assert!(state.reduce(mismatch).is_err());
    assert_eq!(state.access, AccessState::ProtocolLockout);
    assert!(state.snapshot.is_none());
}

#[test]
fn manual_lock_ignores_an_expected_lease_result_and_pong_until_lock_result() {
    let mut lease = AppState::viewer();
    lease.handle(InputEvent::TakeControl);
    lease.handle(InputEvent::LockTui);
    assert_eq!(
        lease.reduce(lease_result(1, "controller")),
        Ok(ReduceOutcome::Ignored)
    );
    assert_eq!(lease.access, AccessState::Locked);
    assert!(lease.lock_pending());
    assert_eq!(lease.reduce(lock_result(2, 0)), Ok(ReduceOutcome::Changed));

    let mut pong_state = AppState::viewer();
    pong_state.handle(InputEvent::LockTui);
    assert_eq!(
        pong_state.reduce(pong(1, 0, "in-flight")),
        Ok(ReduceOutcome::Ignored)
    );
    assert_eq!(pong_state.access, AccessState::Locked);
    assert_eq!(
        pong_state.reduce(lock_result(2, 0)),
        Ok(ReduceOutcome::Changed)
    );
}

#[test]
fn manual_lock_consumes_each_expected_in_flight_reply_only_once() {
    let mut snapshot_state = AppState::locked();
    snapshot_state.reduce(server_hello(1, false)).unwrap();
    snapshot_state.handle(InputEvent::Char('p'));
    snapshot_state.handle(InputEvent::Enter);
    snapshot_state
        .reduce(auth_result(2, true, "viewer"))
        .unwrap();
    snapshot_state.handle(InputEvent::LockTui);
    assert_eq!(
        snapshot_state.reduce(snapshot(3, 1, "First")),
        Ok(ReduceOutcome::Ignored)
    );
    assert!(snapshot_state.reduce(snapshot(4, 1, "Duplicate")).is_err());
    assert_eq!(snapshot_state.access, AccessState::ProtocolLockout);

    let mut lease_state = AppState::viewer();
    lease_state.handle(InputEvent::TakeControl);
    lease_state.handle(InputEvent::LockTui);
    assert_eq!(
        lease_state.reduce(lease_result(1, "controller")),
        Ok(ReduceOutcome::Ignored)
    );
    assert!(lease_state.reduce(lease_result(2, "controller")).is_err());
    assert_eq!(lease_state.access, AccessState::ProtocolLockout);
}

#[test]
fn control_transition_gaps_and_gapped_fatal_messages_require_reconnect() {
    let mut lock = AppState::viewer();
    lock.handle(InputEvent::LockTui);
    assert!(lock.reduce(pong(2, 0, "gap")).is_err());
    assert_eq!(lock.access, AccessState::ProtocolLockout);

    let mut lease = AppState::viewer();
    lease.handle(InputEvent::TakeControl);
    assert!(lease.reduce(lease_result(2, "controller")).is_err());
    assert_eq!(lease.access, AccessState::ProtocolLockout);

    let mut fatal = AppState::viewer();
    assert!(
        fatal
            .reduce(envelope(
                2,
                0,
                "protocol-error",
                json!({ "code": "fatal", "safe_message": "Reconnect." }),
            ))
            .is_err()
    );
    assert_eq!(fatal.access, AccessState::ProtocolLockout);

    let mut wrong_direction = AppState::viewer();
    assert!(
        wrong_direction
            .reduce(envelope(
                2,
                0,
                "lease-request",
                json!({ "action": "take-control" }),
            ))
            .is_err()
    );
    assert_eq!(wrong_direction.access, AccessState::ProtocolLockout);
}

#[test]
fn newer_snapshot_replaces_state_and_duplicate_sequence_is_ignored() {
    let mut state = AppState::controller();

    assert_eq!(
        state.reduce(snapshot(1, 7, "First")),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(state.state_version(), 7);
    assert_eq!(
        state.reduce(snapshot(2, 8, "Second")),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(state.state_version(), 8);

    assert_eq!(
        state.reduce(snapshot(2, 99, "Duplicate")),
        Ok(ReduceOutcome::Ignored)
    );
    assert_eq!(state.state_version(), 8);
}

#[test]
fn sequence_gap_requests_a_fresh_snapshot() {
    let mut state = AppState::controller();
    assert_eq!(
        state.reduce(snapshot(1, 7, "First")),
        Ok(ReduceOutcome::Changed)
    );

    let outcome = state.reduce(envelope(3, 7, "pong", json!({ "nonce": "gap" })));

    assert_eq!(outcome, Ok(ReduceOutcome::RequestSnapshot));
    assert!(state.awaiting_snapshot());
}

#[test]
fn stale_snapshot_during_resync_fails_closed_instead_of_leaving_a_blank_wait() {
    let mut state = AppState::controller();
    state.reduce(snapshot(1, 7, "Current")).unwrap();
    assert_eq!(
        state.reduce(pong(3, 7, "gap")),
        Ok(ReduceOutcome::RequestSnapshot)
    );

    assert!(state.reduce(snapshot(4, 6, "Stale")).is_err());
    assert_eq!(state.access, AccessState::ProtocolLockout);
    assert!(state.snapshot.is_none());
}

#[test]
fn server_hello_selects_setup_or_unlock_only_as_the_first_server_message() {
    let mut setup = AppState::locked();
    assert_eq!(
        setup.reduce(server_hello(1, true)),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(setup.access, AccessState::FirstRun);

    let mut unlock = AppState::locked();
    assert_eq!(
        unlock.reduce(server_hello(1, false)),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(unlock.access, AccessState::Locked);

    assert!(unlock.reduce(server_hello(2, false)).is_err());
    assert_eq!(unlock.access, AccessState::ProtocolLockout);
}

#[test]
fn server_sequence_zero_is_never_treated_as_a_duplicate() {
    let mut state = AppState::locked();

    assert!(state.reduce(server_hello(0, false)).is_err());
    assert_eq!(state.access, AccessState::ProtocolLockout);
}

#[test]
fn auth_success_becomes_viewer_clears_secret_and_requests_snapshot() {
    let mut state = AppState::locked();
    state.reduce(server_hello(1, false)).unwrap();
    for character in "SENSITIVE".chars() {
        state.handle(InputEvent::Char(character));
    }
    assert!(matches!(
        state.handle(InputEvent::Enter).as_slice(),
        [ClientAction::Authenticate(_)]
    ));

    assert_eq!(
        state.reduce(auth_result(2, true, "viewer")),
        Ok(ReduceOutcome::RequestSnapshot)
    );
    assert_eq!(state.access, AccessState::Viewer);
    assert_eq!(state.masked_auth_input(), "");
    assert!(state.awaiting_snapshot());
}

#[test]
fn auth_success_cannot_grant_controller_without_an_explicit_lease() {
    let mut state = AppState::locked();
    state.reduce(server_hello(1, false)).unwrap();
    state.handle(InputEvent::Char('p'));
    state.handle(InputEvent::Enter);

    assert!(state.reduce(auth_result(2, true, "controller")).is_err());
    assert_eq!(state.access, AccessState::ProtocolLockout);
    assert!(state.snapshot.is_none());
}

#[test]
fn pong_is_rejected_before_server_hello_and_during_authentication() {
    let mut before_hello = AppState::locked();
    assert!(before_hello.reduce(pong(1, 0, "early")).is_err());
    assert_eq!(before_hello.access, AccessState::ProtocolLockout);

    let mut awaiting_password = AppState::locked();
    awaiting_password.reduce(server_hello(1, false)).unwrap();
    assert!(awaiting_password.reduce(pong(2, 0, "during-auth")).is_err());
    assert_eq!(awaiting_password.access, AccessState::ProtocolLockout);

    let mut awaiting_result = AppState::locked();
    awaiting_result.reduce(server_hello(1, false)).unwrap();
    awaiting_result.handle(InputEvent::Char('p'));
    awaiting_result.handle(InputEvent::Enter);
    assert!(awaiting_result.reduce(pong(2, 0, "during-result")).is_err());
    assert_eq!(awaiting_result.access, AccessState::ProtocolLockout);
}

#[test]
fn auth_failure_clears_secret_and_remains_in_the_current_auth_flow() {
    let mut unlock = AppState::locked();
    unlock.reduce(server_hello(1, false)).unwrap();
    unlock.handle(InputEvent::Char('x'));
    assert!(matches!(
        unlock.handle(InputEvent::Enter).as_slice(),
        [ClientAction::Authenticate(_)]
    ));
    assert_eq!(
        unlock.reduce(auth_result(2, false, "locked")),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(unlock.access, AccessState::Locked);
    assert_eq!(unlock.masked_auth_input(), "");

    let mut setup = AppState::locked();
    setup.reduce(server_hello(1, true)).unwrap();
    setup.handle(InputEvent::Char('x'));
    setup.handle(InputEvent::Enter);
    setup.handle(InputEvent::Char('x'));
    assert!(matches!(
        setup.handle(InputEvent::Enter).as_slice(),
        [ClientAction::Authenticate(_)]
    ));
    assert_eq!(
        setup.reduce(auth_result(2, false, "locked")),
        Ok(ReduceOutcome::Changed)
    );
    assert_eq!(setup.access, AccessState::FirstRun);
    assert_eq!(setup.masked_auth_input(), "");
}

#[test]
fn authentication_feedback_tracks_pending_failure_and_first_run_mismatch() {
    let mut unlock = AppState::locked();
    unlock.reduce(server_hello(1, false)).unwrap();
    unlock.handle(InputEvent::Char('x'));
    unlock.handle(InputEvent::Enter);
    assert_eq!(unlock.auth_feedback(), AuthFeedback::Pending);
    unlock
        .reduce(envelope(
            2,
            0,
            "auth-result",
            json!({
                "success": false,
                "access_state": "locked",
                "reason": "SENSITIVE SERVER DETAIL"
            }),
        ))
        .unwrap();
    assert_eq!(unlock.auth_feedback(), AuthFeedback::Failed);

    let mut setup = AppState::locked();
    setup.reduce(server_hello(1, true)).unwrap();
    setup.handle(InputEvent::Char('a'));
    setup.handle(InputEvent::Enter);
    setup.handle(InputEvent::Char('b'));
    setup.handle(InputEvent::Enter);
    assert_eq!(setup.auth_feedback(), AuthFeedback::PasswordMismatch);
}

#[test]
fn lease_results_control_only_the_foundation_access_role() {
    for status in ["controller", "transferred"] {
        let mut state = AppState::viewer();
        assert_eq!(
            state.handle(InputEvent::TakeControl),
            vec![ClientAction::RequestLease]
        );
        state.reduce(lease_result(1, status)).unwrap();
        assert_eq!(state.access, AccessState::Controller);
    }

    for status in ["viewer", "lease-held"] {
        let mut state = AppState::viewer();
        assert_eq!(
            state.handle(InputEvent::TakeControl),
            vec![ClientAction::RequestLease]
        );
        state.reduce(lease_result(1, status)).unwrap();
        assert_eq!(state.access, AccessState::Viewer);
    }
}

#[test]
fn protocol_error_is_a_fatal_lockout_that_requires_reconnect() {
    let mut state = AppState::controller();
    state.reduce(snapshot(1, 7, "First")).unwrap();

    let error = state
        .reduce(envelope(
            2,
            7,
            "protocol-error",
            json!({ "code": "schema", "safe_message": "Protocol mismatch." }),
        ))
        .expect_err("protocol error must fail closed");

    assert_eq!(error.code, "schema");
    assert_eq!(state.access, AccessState::ProtocolLockout);
    assert!(state.snapshot.is_none());
    state.handle(InputEvent::Char('p'));
    assert!(state.handle(InputEvent::Enter).is_empty());
    assert_eq!(state.masked_auth_input(), "");
    assert_eq!(
        state.handle(InputEvent::Char('q')),
        vec![ClientAction::CloseTui]
    );
    assert_eq!(
        state.handle(InputEvent::Reconnect),
        vec![ClientAction::Reconnect]
    );
}

#[test]
fn resync_rebases_to_observed_sequence_and_only_next_exact_snapshot_clears_it() {
    let mut state = AppState::controller();
    state.reduce(snapshot(1, 7, "First")).unwrap();

    assert_eq!(
        state.reduce(snapshot(3, 8, "Gap snapshot")),
        Ok(ReduceOutcome::RequestSnapshot)
    );
    assert!(state.awaiting_snapshot());
    assert_eq!(state.state_version(), 7);

    assert_eq!(
        state.reduce(pong(4, 7, "still-waiting")),
        Ok(ReduceOutcome::Ignored)
    );
    assert!(state.awaiting_snapshot());

    assert_eq!(
        state.reduce(snapshot(5, 8, "Fresh")),
        Ok(ReduceOutcome::Changed)
    );
    assert!(!state.awaiting_snapshot());
    assert_eq!(state.state_version(), 8);
}

#[test]
fn snapshot_versions_reject_mismatch_stale_and_equal_divergence() {
    let mut mismatch = AppState::controller();
    assert!(mismatch.reduce(snapshot(1, 7, "First")).is_ok());
    let mut mismatched = serde_json::to_value(snapshot(2, 8, "Mismatch")).unwrap();
    mismatched["state_version"] = json!(9);
    assert!(
        mismatch
            .reduce(serde_json::from_value(mismatched).unwrap())
            .is_err()
    );
    assert_eq!(mismatch.access, AccessState::ProtocolLockout);

    let mut versions = AppState::controller();
    versions.reduce(snapshot(1, 7, "First")).unwrap();
    assert_eq!(
        versions.reduce(snapshot(2, 6, "Older")),
        Ok(ReduceOutcome::Ignored)
    );
    assert_eq!(versions.state_version(), 7);
    assert_eq!(
        versions.reduce(snapshot(3, 7, "First")),
        Ok(ReduceOutcome::Ignored)
    );
    assert!(versions.reduce(snapshot(4, 7, "Divergent")).is_err());
    assert_eq!(versions.access, AccessState::ProtocolLockout);
}

#[test]
fn manual_lock_reauthenticates_on_the_same_sequence_and_returns_as_viewer() {
    let mut state = AppState::controller();
    state.reduce(snapshot(1, 7, "First")).unwrap();
    assert_eq!(
        state.handle(InputEvent::LockTui),
        vec![ClientAction::RequestLock]
    );
    assert_eq!(state.access, AccessState::Locked);
    assert!(state.snapshot.is_none());
    assert!(state.lock_pending());

    assert_eq!(state.reduce(lock_result(2, 7)), Ok(ReduceOutcome::Changed));
    assert_eq!(state.access, AccessState::Locked);
    assert!(state.snapshot.is_none());
    state.handle(InputEvent::Char('p'));
    assert!(matches!(
        state.handle(InputEvent::Enter).as_slice(),
        [ClientAction::Authenticate(_)]
    ));

    assert_eq!(
        state.reduce(auth_result(3, true, "viewer")),
        Ok(ReduceOutcome::RequestSnapshot)
    );
    assert_eq!(state.access, AccessState::Viewer);
}

#[test]
fn snapshot_before_authentication_fails_closed() {
    let mut state = AppState::locked();
    state.reduce(server_hello(1, false)).unwrap();

    assert!(state.reduce(snapshot(2, 1, "Forbidden")).is_err());
    assert_eq!(state.access, AccessState::ProtocolLockout);
    assert!(state.snapshot.is_none());
}

#[test]
fn wrong_direction_message_fails_closed_but_old_messages_are_ignored() {
    let mut state = AppState::viewer();
    state.reduce(pong(1, 0, "first")).unwrap();
    assert_eq!(
        state.reduce(envelope(
            1,
            0,
            "protocol-error",
            json!({ "code": "old", "safe_message": "Old message." }),
        )),
        Ok(ReduceOutcome::Ignored)
    );
    assert_eq!(state.access, AccessState::Viewer);

    assert!(
        state
            .reduce(envelope(
                2,
                0,
                "lease-request",
                json!({ "action": "take-control" }),
            ))
            .is_err()
    );
    assert_eq!(state.access, AccessState::ProtocolLockout);
}

#[test]
fn auth_result_without_a_submitted_request_fails_closed() {
    let mut state = AppState::locked();
    state.reduce(server_hello(1, false)).unwrap();

    assert!(state.reduce(auth_result(2, true, "viewer")).is_err());
    assert_eq!(state.access, AccessState::ProtocolLockout);
}

#[test]
fn auth_failure_returns_to_retry_and_accepts_one_new_submission() {
    let mut state = AppState::locked();
    state.reduce(server_hello(1, false)).unwrap();
    state.handle(InputEvent::Char('x'));
    assert!(matches!(
        state.handle(InputEvent::Enter).as_slice(),
        [ClientAction::Authenticate(_)]
    ));

    state.reduce(auth_result(2, false, "locked")).unwrap();
    assert!(!state.auth_pending());
    state.handle(InputEvent::Char('y'));
    assert!(matches!(
        state.handle(InputEvent::Enter).as_slice(),
        [ClientAction::Authenticate(_)]
    ));
    assert!(state.auth_pending());
}

#[test]
fn sequence_gap_during_auth_or_manual_reauth_requires_reconnect() {
    let mut initial = AppState::locked();
    assert!(initial.reduce(server_hello(2, false)).is_err());
    assert_eq!(initial.access, AccessState::ProtocolLockout);

    let mut authenticating = AppState::locked();
    authenticating.reduce(server_hello(1, false)).unwrap();
    authenticating.handle(InputEvent::Char('p'));
    authenticating.handle(InputEvent::Enter);
    assert!(
        authenticating
            .reduce(auth_result(3, true, "viewer"))
            .is_err()
    );
    assert_eq!(authenticating.access, AccessState::ProtocolLockout);

    let mut relocking = AppState::controller();
    relocking.reduce(snapshot(1, 7, "First")).unwrap();
    relocking.handle(InputEvent::LockTui);
    relocking.reduce(lock_result(2, 7)).unwrap();
    relocking.handle(InputEvent::Char('p'));
    relocking.handle(InputEvent::Enter);
    assert!(relocking.reduce(auth_result(4, true, "viewer")).is_err());
    assert_eq!(relocking.access, AccessState::ProtocolLockout);
}

#[test]
fn lease_result_without_take_control_request_fails_closed() {
    let mut state = AppState::viewer();

    assert!(state.reduce(lease_result(1, "controller")).is_err());
    assert_eq!(state.access, AccessState::ProtocolLockout);
}
