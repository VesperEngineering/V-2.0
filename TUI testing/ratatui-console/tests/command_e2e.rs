use std::collections::VecDeque;
use std::future::{Future, ready};

use serde_json::json;
use vesper_ratatui_console::app::{App, FoundationClient, FoundationSession, SessionError};
use vesper_ratatui_console::contract::{
    CapabilityView, CommandRequest, CommandType, ConsoleSnapshot, Envelope, Message, MessageType,
};
use vesper_ratatui_console::input::InputEvent;
use vesper_ratatui_console::state::{AppState, ClientAction};

#[derive(Default)]
struct FakeSession {
    incoming: VecDeque<Envelope>,
    sent: Vec<Envelope>,
}

impl FoundationSession for FakeSession {
    fn send<'a>(
        &'a mut self,
        envelope: &'a Envelope,
    ) -> impl Future<Output = Result<(), SessionError>> + Send + 'a {
        self.sent.push(envelope.clone());
        ready(Ok(()))
    }

    fn recv(&mut self) -> impl Future<Output = Result<Envelope, SessionError>> + Send + '_ {
        ready(self.incoming.pop_front().ok_or(SessionError::Disconnected))
    }
}

fn envelope(sequence: u64, message_type: &str, payload: serde_json::Value) -> Envelope {
    serde_json::from_value(json!({
        "schema_version": 1,
        "message_id": format!("server:{sequence}"),
        "sequence": sequence,
        "state_version": 0,
        "timestamp_utc": "2026-08-04T12:00:00Z",
        "message_type": message_type,
        "payload": payload
    }))
    .expect("valid envelope")
}

fn server_hello() -> Envelope {
    envelope(
        1,
        "server-hello",
        json!({"server_version": "0.1.0", "requires_setup": false}),
    )
}

fn auth_result() -> Envelope {
    envelope(
        2,
        "auth-result",
        json!({"success": true, "access_state": "viewer", "reason": null}),
    )
}

fn snapshot(sequence: u64, qwen_state: &str) -> Envelope {
    let mut snapshot: serde_json::Value = serde_json::from_slice(include_bytes!(
        "../../contracts/v1/console_snapshot_empty_command_specs.json"
    ))
    .expect("valid snapshot fixture");
    snapshot["shell"]["state_version"] = json!(0);
    snapshot["shell"]["header"]["qwen_state"] = json!(qwen_state);
    if qwen_state == "STALE CACHE" {
        snapshot["command_specs"] = json!([]);
        for capability in snapshot["shell"]["capabilities"]
            .as_array_mut()
            .expect("capability array")
        {
            capability["state"] = json!("disabled");
            capability["reason"] = json!("Cached state cannot authorize actions.");
        }
    }
    envelope(sequence, "snapshot", json!({"snapshot": snapshot}))
}

fn lease_result(sequence: u64) -> Envelope {
    envelope(
        sequence,
        "lease-result",
        json!({"status": "controller", "reason": null}),
    )
}

fn pong(sequence: u64) -> Envelope {
    envelope(sequence, "pong", json!({"nonce": "still-connected"}))
}

fn state_with_sent_approval() -> (AppState, CommandRequest) {
    let mut snapshot: ConsoleSnapshot =
        serde_json::from_str(include_str!("../../contracts/v1/controls_snapshot.json"))
            .expect("valid controls fixture");
    snapshot.shell.capabilities = snapshot
        .command_specs
        .iter()
        .map(|spec| {
            let enabled = spec.command_type.as_str() == CommandType::ApprovalApprove.as_str();
            serde_json::from_value::<CapabilityView>(json!({
                "capability_id": spec.capability_id,
                "state": if enabled { "enabled" } else { "disabled" },
                "reason": if enabled { None } else { Some("Disabled for replay test.") }
            }))
            .expect("valid capability")
        })
        .collect();

    let mut state = AppState::controller();
    state.snapshot = Some(snapshot);
    state.handle(InputEvent::Char('7'));
    state.handle(InputEvent::OpenBrowseRow { panel: 1, index: 0 });
    state.handle(InputEvent::Char(':'));
    let approve = state
        .control_menu()
        .expect("control menu")
        .command_index(CommandType::ApprovalApprove)
        .expect("approval control");
    state.handle(InputEvent::ActivateControl(approve));
    state.handle(InputEvent::Right);
    let actions = state.handle(InputEvent::Enter);
    let [ClientAction::Command(request)] = actions.as_slice() else {
        panic!("command expected")
    };
    (state, request.clone())
}

async fn reauthenticate(client: &mut FoundationClient, session: &mut FakeSession) {
    client.start(session).await.unwrap();
    session.incoming.push_back(server_hello());
    client.receive(session).await.unwrap();
    client
        .handle_input(InputEvent::Char('p'), session)
        .await
        .unwrap();
    client
        .handle_input(InputEvent::Enter, session)
        .await
        .unwrap();
    session.incoming.push_back(auth_result());
    client.receive(session).await.unwrap();
}

fn sent_commands(session: &FakeSession) -> Vec<CommandRequest> {
    session
        .sent
        .iter()
        .filter_map(|envelope| match &envelope.message {
            Message::Command(payload) => Some(payload.request.clone()),
            _ => None,
        })
        .collect()
}

#[tokio::test]
async fn reconnect_replays_the_exact_request_once_after_fresh_snapshot_and_take_control() {
    let (state, original) = state_with_sent_approval();
    let mut client = FoundationClient::from_app(App::new(state));
    client.fail_connection();
    client.begin_connection();
    let mut session = FakeSession::default();

    reauthenticate(&mut client, &mut session).await;
    session.incoming.push_back(snapshot(3, "READY"));
    client.receive(&mut session).await.unwrap();

    assert!(sent_commands(&session).is_empty());
    assert!(
        !session
            .sent
            .iter()
            .any(|envelope| envelope.message_type() == MessageType::LeaseRequest)
    );

    client
        .handle_input(InputEvent::TakeControl, &mut session)
        .await
        .unwrap();
    session.incoming.push_back(lease_result(4));
    client.receive(&mut session).await.unwrap();

    assert_eq!(sent_commands(&session), vec![original.clone()]);
    session.incoming.push_back(pong(5));
    client.receive(&mut session).await.unwrap();
    assert_eq!(sent_commands(&session), vec![original]);
}

#[tokio::test]
async fn stale_cache_never_enables_replay_but_equal_version_fresh_projection_does() {
    let (state, original) = state_with_sent_approval();
    let mut client = FoundationClient::from_app(App::new(state));
    client.fail_connection();
    client.begin_connection();
    let mut session = FakeSession::default();

    reauthenticate(&mut client, &mut session).await;
    session.incoming.push_back(snapshot(3, "STALE CACHE"));
    client.receive(&mut session).await.unwrap();
    client
        .handle_input(InputEvent::TakeControl, &mut session)
        .await
        .unwrap();
    session.incoming.push_back(lease_result(4));
    client.receive(&mut session).await.unwrap();

    assert!(sent_commands(&session).is_empty());

    session.incoming.push_back(snapshot(5, "READY"));
    client.receive(&mut session).await.unwrap();
    assert_eq!(sent_commands(&session), vec![original]);
}
