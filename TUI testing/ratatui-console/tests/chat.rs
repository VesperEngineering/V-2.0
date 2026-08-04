use crossterm::event::{KeyModifiers, MouseButton, MouseEvent, MouseEventKind};
use ratatui::Terminal;
use ratatui::backend::TestBackend;
use ratatui::buffer::Buffer;
use ratatui::layout::Rect;
use serde_json::json;
use sha2::{Digest, Sha256};
use std::future::{Future, ready};
use vesper_ratatui_console::app::{
    App, FoundationClient, FoundationSession, SessionError, SessionStep, mouse_to_input,
};
use vesper_ratatui_console::chat::{
    AgentId, ChatApplyError, ChatApplyOutcome, ChatEvent, ChatHistoryStatus, ChatMessageStatus,
    ChatRole, ChatStore, MAX_REPLAY_EVENTS, MAX_RETAINED_CHAT_BYTES,
    MAX_VISIBLE_MESSAGES_PER_AGENT,
};
use vesper_ratatui_console::contract::{
    CapabilityView, ChatOperation, CommandPayload, CommandType, ConsoleSnapshot, Envelope, Message,
    MessageType,
};
use vesper_ratatui_console::controls::APPROVED_AGENT_ROLES;
use vesper_ratatui_console::input::InputEvent;
use vesper_ratatui_console::layout::{DisplayMode, chat_shell_layout, shell_layout};
use vesper_ratatui_console::state::{
    AccessState, AppState, ClientAction, LocalMode, ReduceOutcome, Screen,
};
use vesper_ratatui_console::theme::Theme;
use vesper_ratatui_console::ui::{chat_selector_start, render};

fn agent(value: &str) -> AgentId {
    AgentId::parse(value).expect("approved V20 agent")
}

fn strict_chat_event(
    event_id: &str,
    agent_id: AgentId,
    message_id: &str,
    role: ChatRole,
    operation: &str,
    chunk_sequence: Option<u64>,
    text: Option<&str>,
) -> ChatEvent {
    let role = match role {
        ChatRole::Human => "human",
        ChatRole::Agent => "agent",
    };
    let Message::ChatEvent(payload) = chat_envelope(
        1,
        event_id,
        agent_id.as_str(),
        message_id,
        role,
        (operation, chunk_sequence, text),
    )
    .message
    else {
        unreachable!("chat_envelope always creates a chat event")
    };
    ChatEvent::try_from(payload).expect("strict approved chat event")
}

fn chunk_event(
    event_id: &str,
    agent_id: AgentId,
    message_id: &str,
    role: ChatRole,
    chunk_sequence: u64,
    text: &str,
) -> ChatEvent {
    strict_chat_event(
        event_id,
        agent_id,
        message_id,
        role,
        "chunk",
        Some(chunk_sequence),
        Some(text),
    )
}

fn terminal_event(
    event_id: &str,
    agent_id: AgentId,
    message_id: &str,
    role: ChatRole,
    operation: &str,
    content: &str,
) -> ChatEvent {
    let mut value = serde_json::to_value(chat_envelope(
        1,
        event_id,
        agent_id.as_str(),
        message_id,
        match role {
            ChatRole::Human => "human",
            ChatRole::Agent => "agent",
        },
        (operation, None, None),
    ))
    .unwrap();
    if operation == "complete" {
        value["payload"]["raw_text_sha256"] = json!(sha256_hex(content));
    }
    let envelope: Envelope = serde_json::from_value(value).unwrap();
    let Message::ChatEvent(payload) = envelope.message else {
        unreachable!("complete envelope always creates a chat event")
    };
    ChatEvent::try_from(payload).expect("strict approved terminal event")
}

fn sha256_hex(content: &str) -> String {
    format!("{:x}", Sha256::digest(content.as_bytes()))
}

fn complete_chat_envelope(
    sequence: u64,
    event_id: &str,
    agent_id: &str,
    message_id: &str,
    role: &str,
    content: &str,
) -> Envelope {
    let mut value = serde_json::to_value(chat_envelope(
        sequence,
        event_id,
        agent_id,
        message_id,
        role,
        ("complete", None, None),
    ))
    .unwrap();
    value["payload"]["raw_text_sha256"] = json!(sha256_hex(content));
    serde_json::from_value(value).unwrap()
}

#[test]
fn only_the_existing_approved_v20_agents_can_own_chat_threads() {
    for approved in APPROVED_AGENT_ROLES {
        assert_eq!(
            AgentId::parse(approved).map(AgentId::as_str),
            Some(approved)
        );
    }
    for rejected in ["AAPL", "order:1", "portfolio-research", ""] {
        assert_eq!(AgentId::parse(rejected), None);
    }
}

#[test]
fn human_and_agent_messages_stay_in_separate_agent_threads() {
    let product = agent("v20-product");
    let development = agent("v20-development");
    let mut store = ChatStore::default();

    store
        .apply(chunk_event(
            "event:product:1",
            product,
            "message:product:1",
            ChatRole::Human,
            1,
            "Review impact",
        ))
        .unwrap();
    store
        .apply(chunk_event(
            "event:development:1",
            development,
            "message:development:1",
            ChatRole::Agent,
            1,
            "Checking runtime",
        ))
        .unwrap();

    let product_messages = store.thread(product).messages();
    assert_eq!(product_messages.len(), 1);
    assert_eq!(product_messages[0].role(), ChatRole::Human);
    assert_eq!(product_messages[0].content(), "Review impact");
    let development_messages = store.thread(development).messages();
    assert_eq!(development_messages.len(), 1);
    assert_eq!(development_messages[0].role(), ChatRole::Agent);
    assert_eq!(development_messages[0].content(), "Checking runtime");
}

#[test]
fn streamed_chunks_remain_draft_until_complete_without_changing_content() {
    let product = agent("v20-product");
    let mut store = ChatStore::default();

    store
        .apply(chunk_event(
            "event:1",
            product,
            "message:1",
            ChatRole::Agent,
            1,
            "first ",
        ))
        .unwrap();
    store
        .apply(chunk_event(
            "event:2",
            product,
            "message:1",
            ChatRole::Agent,
            2,
            "second",
        ))
        .unwrap();
    assert_eq!(
        store.thread(product).messages()[0].content(),
        "first second"
    );
    assert_eq!(
        store.thread(product).messages()[0].status(),
        ChatMessageStatus::Draft
    );

    assert_eq!(
        store.apply(terminal_event(
            "event:3",
            product,
            "message:1",
            ChatRole::Agent,
            "complete",
            "first second",
        )),
        Ok(ChatApplyOutcome::Changed)
    );
    assert_eq!(
        store.thread(product).messages()[0].content(),
        "first second"
    );
    assert_eq!(
        store.thread(product).messages()[0].status(),
        ChatMessageStatus::Complete
    );
}

#[test]
fn chunk_sequences_are_contiguous_and_rejection_preserves_verified_text() {
    let product = agent("v20-product");
    let mut store = ChatStore::default();
    store
        .apply(chunk_event(
            "event:1",
            product,
            "message:1",
            ChatRole::Agent,
            1,
            "first",
        ))
        .unwrap();

    assert_eq!(
        store.apply(chunk_event(
            "event:3",
            product,
            "message:1",
            ChatRole::Agent,
            3,
            "skipped",
        )),
        Err(ChatApplyError::InvalidChunkSequence)
    );
    assert_eq!(store.thread(product).messages()[0].content(), "first");
}

#[test]
fn interrupted_is_the_only_other_terminal_message_state() {
    let risk = agent("v20-risk-review");
    let mut store = ChatStore::default();
    store
        .apply(chunk_event(
            "event:1",
            risk,
            "message:1",
            ChatRole::Agent,
            1,
            "Risk review paused",
        ))
        .unwrap();

    store
        .apply(terminal_event(
            "event:2",
            risk,
            "message:1",
            ChatRole::Agent,
            "interrupted",
            "Risk review paused",
        ))
        .unwrap();

    assert_eq!(
        store.thread(risk).messages()[0].status(),
        ChatMessageStatus::Interrupted
    );
    assert_eq!(
        store.thread(risk).messages()[0].content(),
        "Risk review paused"
    );
}

#[test]
fn exact_duplicate_events_are_idempotent_but_rewrites_conflict() {
    let product = agent("v20-product");
    let mut store = ChatStore::default();
    let original = chunk_event("event:1", product, "message:1", ChatRole::Human, 1, "hello");

    assert_eq!(store.apply(original.clone()), Ok(ChatApplyOutcome::Changed));
    assert_eq!(store.apply(original), Ok(ChatApplyOutcome::Ignored));
    assert_eq!(store.thread(product).messages()[0].content(), "hello");

    let rewritten = chunk_event(
        "event:1",
        product,
        "message:1",
        ChatRole::Human,
        1,
        "rewritten",
    );
    assert_eq!(
        store.apply(rewritten),
        Err(ChatApplyError::ConflictingEvent)
    );
    assert_eq!(store.thread(product).messages()[0].content(), "hello");
}

#[test]
fn terminal_content_is_immutable_and_invalid_events_do_not_mutate_it() {
    let product = agent("v20-product");
    let mut store = ChatStore::default();
    store
        .apply(chunk_event(
            "event:1",
            product,
            "message:1",
            ChatRole::Agent,
            1,
            "final text",
        ))
        .unwrap();
    store
        .apply(terminal_event(
            "event:2",
            product,
            "message:1",
            ChatRole::Agent,
            "complete",
            "final text",
        ))
        .unwrap();

    assert_eq!(
        store.apply(chunk_event(
            "event:3",
            product,
            "message:1",
            ChatRole::Agent,
            2,
            " changed",
        )),
        Err(ChatApplyError::TerminalMessageImmutable)
    );
    let message = &store.thread(product).messages()[0];
    assert_eq!(message.content(), "final text");
    assert_eq!(message.status(), ChatMessageStatus::Complete);
}

#[test]
fn terminal_events_cannot_fabricate_missing_history() {
    let product = agent("v20-product");
    let mut store = ChatStore::default();

    assert_eq!(
        store.apply(terminal_event(
            "event:1",
            product,
            "message:missing",
            ChatRole::Agent,
            "complete",
            "",
        )),
        Err(ChatApplyError::UnknownMessage)
    );
    assert!(store.thread(product).messages().is_empty());
}

#[test]
fn complete_verifies_accumulated_utf8_hash_and_keeps_receipt_binding() {
    let product = agent("v20-product");
    let mut store = ChatStore::default();
    store
        .apply(chunk_event(
            "event:hash:1",
            product,
            "message:hash",
            ChatRole::Agent,
            1,
            "trusted text",
        ))
        .unwrap();

    let mismatched = strict_chat_event(
        "event:hash:bad",
        product,
        "message:hash",
        ChatRole::Agent,
        "complete",
        None,
        None,
    );
    assert_eq!(
        store.apply(mismatched),
        Err(ChatApplyError::InvalidContentHash)
    );
    let draft = &store.thread(product).messages()[0];
    assert_eq!(draft.status(), ChatMessageStatus::Draft);
    assert_eq!(draft.content(), "trusted text");
    assert_eq!(draft.validation_receipt_id(), None);

    store
        .apply(terminal_event(
            "event:hash:good",
            product,
            "message:hash",
            ChatRole::Agent,
            "complete",
            "trusted text",
        ))
        .unwrap();
    let complete = &store.thread(product).messages()[0];
    assert_eq!(complete.status(), ChatMessageStatus::Complete);
    assert_eq!(complete.validation_receipt_id(), Some("receipt:chat:1"));
    assert_eq!(
        complete.raw_text_sha256(),
        Some(sha256_hex("trusted text").as_str())
    );
}

#[test]
fn message_ids_are_unique_across_agent_threads() {
    let product = agent("v20-product");
    let risk = agent("v20-risk-review");
    let mut store = ChatStore::default();
    store
        .apply(chunk_event(
            "event:product",
            product,
            "message:shared",
            ChatRole::Human,
            1,
            "product",
        ))
        .unwrap();

    assert_eq!(
        store.apply(chunk_event(
            "event:risk",
            risk,
            "message:shared",
            ChatRole::Agent,
            1,
            "risk",
        )),
        Err(ChatApplyError::ConflictingMessage)
    );
    assert!(store.thread(risk).messages().is_empty());
}

#[test]
fn one_hour_style_terminal_stream_plateaus_at_bounded_visible_and_evidence_windows() {
    let product = agent("v20-product");
    let mut store = ChatStore::default();
    store.mark_history_loading(product, false);
    store.finish_history(
        product,
        Some(serde_json::from_value(json!("message:durable-cursor")).unwrap()),
    );

    for index in 0..1_000 {
        let message_id = format!("message:{index:04}");
        store
            .apply(chunk_event(
                &format!("event:{index:04}:chunk"),
                product,
                &message_id,
                ChatRole::Agent,
                1,
                "x",
            ))
            .unwrap();
        store
            .apply(terminal_event(
                &format!("event:{index:04}:complete"),
                product,
                &message_id,
                ChatRole::Agent,
                "complete",
                "x",
            ))
            .unwrap();
    }

    let messages = store.thread(product).messages();
    assert_eq!(messages.len(), MAX_VISIBLE_MESSAGES_PER_AGENT);
    assert_eq!(messages.first().unwrap().message_id(), "message:0760");
    assert_eq!(messages.last().unwrap().message_id(), "message:0999");
    assert!(store.event_evidence_len() <= MAX_REPLAY_EVENTS);
    assert!(store.retained_text_bytes() <= MAX_RETAINED_CHAT_BYTES);
    assert_eq!(
        store.next_cursor(product).map(|cursor| cursor.as_str()),
        Some("message:durable-cursor")
    );
    assert!(!store.can_request_older_page(product));
}

#[test]
fn global_content_cap_evicts_terminals_but_never_drafts() {
    let product = agent("v20-product");
    let risk = agent("v20-risk-review");
    let block = "x".repeat(64 * 1024);
    let mut store = ChatStore::default();
    for (agent_id, prefix) in [(product, "product"), (risk, "risk")] {
        let message_id = format!("message:{prefix}:draft");
        for sequence in 1..=32 {
            store
                .apply(chunk_event(
                    &format!("event:{prefix}:{sequence}"),
                    agent_id,
                    &message_id,
                    ChatRole::Agent,
                    sequence,
                    &block,
                ))
                .unwrap();
        }
    }
    assert_eq!(store.retained_text_bytes(), MAX_RETAINED_CHAT_BYTES);
    let before = store.thread(product).messages()[0].content().len();
    assert_eq!(
        store.apply(chunk_event(
            "event:over-cap",
            product,
            "message:product:draft",
            ChatRole::Agent,
            33,
            "y",
        )),
        Err(ChatApplyError::RetentionLimitExceeded)
    );
    assert_eq!(store.retained_text_bytes(), MAX_RETAINED_CHAT_BYTES);
    assert_eq!(store.thread(product).messages()[0].content().len(), before);
    assert_eq!(
        store.thread(product).messages()[0].status(),
        ChatMessageStatus::Draft
    );

    let product_text = store.thread(product).messages()[0].content().to_owned();
    store
        .apply(terminal_event(
            "event:product:complete",
            product,
            "message:product:draft",
            ChatRole::Agent,
            "complete",
            &product_text,
        ))
        .unwrap();
    assert_eq!(
        store.apply(chunk_event(
            "event:risk:33",
            risk,
            "message:risk:draft",
            ChatRole::Agent,
            33,
            "y",
        )),
        Ok(ChatApplyOutcome::Changed)
    );
    assert!(store.thread(product).messages().is_empty());
    assert!(store.retained_text_bytes() < MAX_RETAINED_CHAT_BYTES);
}

#[test]
fn replay_evidence_cap_fails_closed_when_only_a_draft_can_be_removed() {
    let product = agent("v20-product");
    let mut store = ChatStore::default();
    for sequence in 1..=MAX_REPLAY_EVENTS as u64 {
        store
            .apply(chunk_event(
                &format!("event:evidence:{sequence}"),
                product,
                "message:evidence:draft",
                ChatRole::Agent,
                sequence,
                "x",
            ))
            .unwrap();
    }
    let before = store.thread(product).messages()[0].content().len();
    assert_eq!(store.event_evidence_len(), MAX_REPLAY_EVENTS);
    assert_eq!(
        store.apply(chunk_event(
            "event:evidence:overflow",
            product,
            "message:evidence:draft",
            ChatRole::Agent,
            MAX_REPLAY_EVENTS as u64 + 1,
            "x",
        )),
        Err(ChatApplyError::RetentionLimitExceeded)
    );
    assert_eq!(store.event_evidence_len(), MAX_REPLAY_EVENTS);
    assert_eq!(store.thread(product).messages()[0].content().len(), before);
}

fn chat_snapshot(agent_id: &str) -> ConsoleSnapshot {
    let mut value: serde_json::Value =
        serde_json::from_str(include_str!("../../contracts/v1/controls_snapshot.json"))
            .expect("valid shared controls snapshot");
    value["agents"]["rows"][0]["agent"] = json!(agent_id);
    let mut snapshot: ConsoleSnapshot = serde_json::from_value(value).expect("valid chat snapshot");
    snapshot.shell.capabilities = snapshot
        .command_specs
        .iter()
        .map(|spec| {
            serde_json::from_value::<CapabilityView>(json!({
                "capability_id": spec.capability_id,
                "state": if spec.command_type.as_str() == CommandType::AgentSendMessage.as_str() {
                    "enabled"
                } else {
                    "disabled"
                },
                "reason": if spec.command_type.as_str() == CommandType::AgentSendMessage.as_str() {
                    None
                } else {
                    Some("Not needed by this test.")
                }
            }))
            .expect("valid capability")
        })
        .collect();
    snapshot
}

fn open_agent_selector(state: &mut AppState) {
    state.handle(InputEvent::Char('4'));
    assert_eq!(state.screen, Screen::Agents);
    state.handle(InputEvent::Char('i'));
    assert_eq!(state.mode, LocalMode::AgentSelector);
}

fn open_first_agent_card_chat(state: &mut AppState) {
    state.handle(InputEvent::Char('4'));
    state.handle(InputEvent::OpenBrowseRow { panel: 1, index: 0 });
    assert_eq!(state.mode, LocalMode::Open);
    state.handle(InputEvent::Char('i'));
    assert_eq!(state.mode, LocalMode::AgentChat);
}

fn focus_chat_input(state: &mut AppState) {
    state.handle(InputEvent::Char('i'));
    assert_eq!(state.mode, LocalMode::AgentInput);
}

#[test]
fn chat_is_hidden_except_for_agent_card_or_explicit_agent_selector() {
    let mut state = AppState::controller();
    state.snapshot = Some(chat_snapshot("v20-product"));

    state.handle(InputEvent::Char('i'));
    assert_eq!(state.mode, LocalMode::Browse);
    let outside_agents = render_state(&state, 120, 38);
    assert!(!outside_agents.contains("CHAT INPUT"));
    assert!(!outside_agents.contains("SELECT AGENT CHAT"));

    open_agent_selector(&mut state);
    assert_eq!(state.selected_chat_agent(), None);
    let actions = state.handle(InputEvent::Enter);
    assert!(matches!(
        actions.as_slice(),
        [ClientAction::ChatHistoryRequest(_)]
    ));
    assert_eq!(state.mode, LocalMode::AgentChat);
    assert_eq!(
        state.selected_chat_agent().map(AgentId::as_str),
        Some("v20-product")
    );

    state.handle(InputEvent::Escape);
    assert_eq!(state.mode, LocalMode::Browse);
    open_first_agent_card_chat(&mut state);
    assert_eq!(
        state.selected_chat_agent().map(AgentId::as_str),
        Some("v20-product")
    );

    let mut unapproved = AppState::controller();
    unapproved.snapshot = Some(chat_snapshot("portfolio-research"));
    unapproved.handle(InputEvent::Char('4'));
    unapproved.handle(InputEvent::OpenBrowseRow { panel: 1, index: 0 });
    unapproved.handle(InputEvent::Char('i'));
    assert_eq!(unapproved.mode, LocalMode::Open);
}

#[test]
fn enter_sends_only_from_chat_input_to_the_selected_agent_without_entity_context() {
    let mut state = AppState::controller();
    state.snapshot = Some(chat_snapshot("v20-product"));
    assert!(state.handle(InputEvent::Enter).is_empty());
    open_agent_selector(&mut state);
    assert!(matches!(
        state.handle(InputEvent::Enter).as_slice(),
        [ClientAction::ChatHistoryRequest(_)]
    ));
    assert_eq!(state.mode, LocalMode::AgentChat);
    assert!(state.handle(InputEvent::Enter).is_empty());
    focus_chat_input(&mut state);
    for character in "Review runtime safety".chars() {
        state.handle(InputEvent::Char(character));
    }

    let actions = state.handle(InputEvent::Enter);
    let [ClientAction::Command(command)] = actions.as_slice() else {
        panic!("chat input should emit one reviewed command")
    };
    assert_eq!(command.command_type, CommandType::AgentSendMessage);
    let CommandPayload::AgentMessage(payload) = &command.payload else {
        panic!("agent message payload expected")
    };
    assert_eq!(payload.agent_id.as_str(), "v20-product");
    assert_eq!(payload.text.as_str(), "Review runtime safety");
    assert_eq!(payload.selected_entity_type, None);
    assert_eq!(payload.selected_entity_id, None);
    assert_eq!(state.chat_input(), "");
    assert!(
        state
            .chat_store()
            .thread(agent("v20-product"))
            .messages()
            .is_empty()
    );
}

#[test]
fn chat_input_is_bounded_and_disabled_send_keeps_the_operator_draft() {
    let mut controller = AppState::controller();
    controller.snapshot = Some(chat_snapshot("v20-product"));
    open_agent_selector(&mut controller);
    controller.handle(InputEvent::Enter);
    focus_chat_input(&mut controller);
    for _ in 0..8_001 {
        controller.handle(InputEvent::Char('x'));
    }
    assert_eq!(controller.chat_input().chars().count(), 8_000);

    let mut viewer = AppState::viewer();
    viewer.snapshot = Some(chat_snapshot("v20-product"));
    open_agent_selector(&mut viewer);
    viewer.handle(InputEvent::Enter);
    focus_chat_input(&mut viewer);
    for character in "keep this draft".chars() {
        viewer.handle(InputEvent::Char(character));
    }
    assert!(viewer.handle(InputEvent::Enter).is_empty());
    assert_eq!(viewer.chat_input(), "keep this draft");
    assert_eq!(
        viewer.chat_send_reason().as_deref(),
        Some("Take Control is required.")
    );
}

#[test]
fn send_requires_one_exact_reviewed_spec_and_capability() {
    let base = chat_snapshot("v20-product");
    let spec = base
        .command_specs
        .iter()
        .find(|spec| spec.command_type.as_str() == CommandType::AgentSendMessage.as_str())
        .cloned()
        .expect("chat spec");
    let capability = base
        .shell
        .capabilities
        .iter()
        .find(|capability| capability.capability_id.as_str() == spec.capability_id.as_str())
        .cloned()
        .expect("chat capability");
    let cases = [
        {
            let mut snapshot = base.clone();
            snapshot.command_specs.retain(|candidate| {
                candidate.command_type.as_str() != CommandType::AgentSendMessage.as_str()
            });
            snapshot
        },
        {
            let mut snapshot = base.clone();
            snapshot.command_specs.push(spec);
            snapshot
        },
        {
            let mut snapshot = base;
            snapshot.shell.capabilities.push(capability);
            snapshot
        },
        {
            let mut value = serde_json::to_value(chat_snapshot("v20-product")).unwrap();
            let specs = value["command_specs"].as_array_mut().unwrap();
            let chat = specs
                .iter_mut()
                .find(|candidate| candidate["command_type"] == "agent.send-message")
                .unwrap();
            chat["payload_model"] = json!("WrongPayload");
            serde_json::from_value(value).unwrap()
        },
        {
            let mut value = serde_json::to_value(chat_snapshot("v20-product")).unwrap();
            let specs = value["command_specs"].as_array_mut().unwrap();
            let chat = specs
                .iter_mut()
                .find(|candidate| candidate["command_type"] == "agent.send-message")
                .unwrap();
            chat["confirmation_level"] = json!("confirm");
            serde_json::from_value(value).unwrap()
        },
    ];

    for snapshot in cases {
        let mut state = AppState::controller();
        state.snapshot = Some(snapshot);
        open_agent_selector(&mut state);
        state.handle(InputEvent::Enter);
        focus_chat_input(&mut state);
        state.handle(InputEvent::Char('x'));
        assert!(state.handle(InputEvent::Enter).is_empty());
        assert_eq!(state.chat_input(), "x");
        assert!(state.chat_send_reason().is_some());
    }
}

#[test]
fn conflicting_chat_evidence_locks_the_console_without_rewriting_history() {
    let mut state = AppState::controller();
    let product = agent("v20-product");
    state
        .reduce(chat_envelope(
            1,
            "event:1",
            "v20-product",
            "message:1",
            "agent",
            ("chunk", Some(1), Some("trusted")),
        ))
        .unwrap();

    assert!(
        state
            .reduce(chat_envelope(
                1,
                "event:1",
                "v20-product",
                "message:1",
                "agent",
                ("chunk", Some(1), Some("rewritten")),
            ))
            .is_err()
    );
    assert_eq!(state.access, AccessState::ProtocolLockout);
    assert_eq!(
        state.chat_store().thread(product).messages()[0].content(),
        "trusted"
    );
}

#[test]
fn chat_rendering_has_no_fabricated_history_and_covers_both_themes_and_large_text() {
    for (theme, display_mode) in [
        (Theme::WarmWhite, DisplayMode::Standard),
        (Theme::Charcoal, DisplayMode::Standard),
        (Theme::WarmWhite, DisplayMode::LargeText),
    ] {
        let mut state = AppState::controller();
        state.snapshot = Some(chat_snapshot("v20-product"));
        state.set_theme(theme);
        state.set_display_mode(display_mode);
        open_first_agent_card_chat(&mut state);
        state
            .reduce(chat_history_result_envelope(1, "v20-product", None))
            .unwrap();

        let buffer = render_buffer(&state, 120, 38);
        let layout = chat_shell_layout(Rect::new(0, 0, 120, 38), display_mode);
        let body = buffer_region(&buffer, layout.body);
        let input = buffer_region(&buffer, layout.input);
        assert!(body.contains("CHAT - v20-product"));
        assert!(body.contains("NO CHAT HISTORY"));
        assert!(!body.contains("Review AAPL"));
        assert!(!body.contains("order:1"));
        assert!(input.contains("CHAT INPUT - v20-product"));
        assert_eq!(buffer[(0, 0)].bg, theme.palette().background);
    }
}

#[test]
fn rendered_stream_status_changes_only_after_terminal_event() {
    let mut state = AppState::controller();
    state.snapshot = Some(chat_snapshot("v20-product"));
    open_first_agent_card_chat(&mut state);
    state
        .reduce(chat_envelope(
            1,
            "event:1",
            "v20-product",
            "message:1",
            "agent",
            ("chunk", Some(1), Some("Working")),
        ))
        .unwrap();
    state
        .reduce(chat_history_result_envelope(2, "v20-product", None))
        .unwrap();
    let draft = render_state(&state, 120, 38);
    assert!(draft.contains("AGENT DRAFT"));
    assert!(!draft.contains("AGENT COMPLETE"));

    state
        .reduce(complete_chat_envelope(
            3,
            "event:2",
            "v20-product",
            "message:1",
            "agent",
            "Working",
        ))
        .unwrap();
    let complete = render_state(&state, 120, 38);
    assert!(complete.contains("AGENT COMPLETE"));
    assert!(!complete.contains("AGENT DRAFT"));
}

#[test]
fn mouse_can_open_select_send_and_close_chat_like_the_keyboard() {
    let area = Rect::new(0, 0, 120, 38);
    let mut state = AppState::controller();
    state.snapshot = Some(chat_snapshot("v20-product"));
    state.handle(InputEvent::Char('4'));
    let layout = shell_layout(area, state.display_mode());
    let click = |column, row| MouseEvent {
        kind: MouseEventKind::Down(MouseButton::Left),
        column,
        row,
        modifiers: KeyModifiers::NONE,
    };

    let open = mouse_to_input(
        click(layout.footer.x + 3, layout.footer.y + 1),
        area,
        &state,
    );
    assert_eq!(open, Some(InputEvent::Char('i')));
    state.handle(open.unwrap());
    assert_eq!(state.mode, LocalMode::AgentSelector);

    let select = mouse_to_input(click(layout.body.x + 3, layout.body.y + 3), area, &state);
    assert_eq!(select, Some(InputEvent::SelectChatAgent(2)));
    state.handle(select.unwrap());
    assert_eq!(state.mode, LocalMode::AgentChat);
    assert_eq!(
        state.selected_chat_agent().map(AgentId::as_str),
        Some("v20-risk-review")
    );
    let layout = chat_shell_layout(area, state.display_mode());
    let scroll = MouseEvent {
        kind: MouseEventKind::ScrollUp,
        column: layout.body.x + 3,
        row: layout.body.y + 1,
        modifiers: KeyModifiers::NONE,
    };
    assert_eq!(mouse_to_input(scroll, area, &state), Some(InputEvent::Up));
    assert_eq!(
        mouse_to_input(click(layout.input.x + 3, layout.input.y + 1), area, &state),
        Some(InputEvent::FocusChatInput)
    );

    let focus = mouse_to_input(
        click(layout.footer.x + 3, layout.footer.y + 1),
        area,
        &state,
    );
    assert_eq!(focus, Some(InputEvent::FocusChatInput));
    state.handle(focus.unwrap());
    assert_eq!(state.mode, LocalMode::AgentInput);
    let scroll_in_input = mouse_to_input(scroll, area, &state).unwrap();
    assert!(state.handle(scroll_in_input).is_empty());
    assert_eq!(state.mode, LocalMode::AgentInput);
    let send = mouse_to_input(
        click(layout.footer.x + 3, layout.footer.y + 1),
        area,
        &state,
    );
    assert_eq!(send, Some(InputEvent::Enter));
    let close = mouse_to_input(
        click(layout.footer.right() - 3, layout.footer.y + 1),
        area,
        &state,
    );
    assert_eq!(close, Some(InputEvent::Escape));
}

#[test]
fn small_agent_selector_keeps_the_selected_role_visible_and_mouse_aligned() {
    let area = Rect::new(0, 0, 80, 24);
    let mut state = AppState::controller();
    state.snapshot = Some(chat_snapshot("v20-product"));
    open_agent_selector(&mut state);
    for _ in 0..7 {
        state.handle(InputEvent::Down);
    }

    let layout = shell_layout(area, state.display_mode());
    let body = buffer_region(&render_buffer(&state, area.width, area.height), layout.body);
    assert!(body.contains("v20-execution-performance-analyst"), "{body}");
    let start = chat_selector_start(&state, layout.body);
    let click = MouseEvent {
        kind: MouseEventKind::Down(MouseButton::Left),
        column: layout.body.x + 2,
        row: layout.body.y + 1 + u16::try_from(7 - start).unwrap(),
        modifiers: KeyModifiers::NONE,
    };
    assert_eq!(
        mouse_to_input(click, area, &state),
        Some(InputEvent::SelectChatAgent(7))
    );
}

fn render_buffer(state: &AppState, width: u16, height: u16) -> Buffer {
    let backend = TestBackend::new(width, height);
    let mut terminal = Terminal::new(backend).expect("test terminal");
    terminal
        .draw(|frame| render(frame, state))
        .expect("chat renders");
    terminal.backend().buffer().clone()
}

fn render_state(state: &AppState, width: u16, height: u16) -> String {
    let buffer = render_buffer(state, width, height);
    let area = buffer.area;
    buffer_region(&buffer, area)
}

fn buffer_region(buffer: &Buffer, area: Rect) -> String {
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

fn chat_envelope(
    sequence: u64,
    event_id: &str,
    agent_id: &str,
    message_id: &str,
    role: &str,
    fields: (&str, Option<u64>, Option<&str>),
) -> Envelope {
    let (operation, chunk_sequence, text) = fields;
    let terminal = operation != "chunk";
    serde_json::from_value(json!({
        "schema_version": 1,
        "message_id": format!("server:{sequence}"),
        "sequence": sequence,
        "state_version": 0,
        "timestamp_utc": "2026-08-04T12:00:00Z",
        "message_type": "chat-event",
        "payload": {
            "event_id": event_id,
            "agent_id": agent_id,
            "message_id": message_id,
            "role": role,
            "operation": operation,
            "chunk_sequence": chunk_sequence,
            "text": text,
            "token_count": if operation == "chunk" { Some(3_u64) } else { None },
            "message_created_at_utc": "2026-08-04T11:59:00Z",
            "occurred_at_utc": terminal.then_some("2026-08-04T12:00:00Z"),
            "validation_receipt_id": (operation == "complete").then_some("receipt:chat:1"),
            "raw_text_sha256": (operation == "complete").then_some(
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            )
        }
    }))
    .expect("strict chat envelope")
}

fn chat_chunk_envelope_at(
    sequence: u64,
    event_id: &str,
    agent_id: &str,
    message_id: &str,
    text: &str,
    created_at_utc: &str,
) -> Envelope {
    let mut value = serde_json::to_value(chat_envelope(
        sequence,
        event_id,
        agent_id,
        message_id,
        "agent",
        ("chunk", Some(1), Some(text)),
    ))
    .unwrap();
    value["payload"]["message_created_at_utc"] = json!(created_at_utc);
    serde_json::from_value(value).unwrap()
}

fn chat_history_result_envelope(
    sequence: u64,
    agent_id: &str,
    next_cursor: Option<&str>,
) -> Envelope {
    serde_json::from_value(json!({
        "schema_version": 1,
        "message_id": format!("server:{sequence}"),
        "sequence": sequence,
        "state_version": 0,
        "timestamp_utc": "2026-08-04T12:00:00Z",
        "message_type": "chat-history-result",
        "payload": {
            "agent_id": agent_id,
            "next_cursor": next_cursor
        }
    }))
    .expect("strict chat history result envelope")
}

#[test]
fn strict_wire_chat_payload_rejects_invalid_operation_shapes() {
    let valid = chat_envelope(
        1,
        "event:1",
        "v20-product",
        "message:1",
        "agent",
        ("chunk", Some(1), Some("hello")),
    );
    assert_eq!(valid.message_type(), MessageType::ChatEvent);
    let Message::ChatEvent(payload) = &valid.message else {
        panic!("chat event payload expected")
    };
    assert_eq!(payload.operation(), ChatOperation::Chunk);
    assert_eq!(payload.text(), Some("hello"));

    let mut base = serde_json::to_value(valid).unwrap();
    for mutate in [
        |value: &mut serde_json::Value| value["payload"]["text"] = json!(null),
        |value: &mut serde_json::Value| {
            value["payload"]["operation"] = json!("complete");
        },
        |value: &mut serde_json::Value| {
            value["payload"]["unknown"] = json!(true);
        },
    ] {
        let mut invalid = base.clone();
        mutate(&mut invalid);
        assert!(serde_json::from_value::<Envelope>(invalid).is_err());
    }
    let mut unapproved_agent = base.clone();
    unapproved_agent["payload"]["agent_id"] = json!("AAPL");
    assert!(serde_json::from_value::<Envelope>(unapproved_agent).is_err());
    base["payload"]["text"] = json!("x".repeat(65_537));
    assert!(serde_json::from_value::<Envelope>(base).is_err());

    let terminal = chat_envelope(
        2,
        "event:2",
        "v20-product",
        "message:1",
        "agent",
        ("complete", None, None),
    );
    assert_eq!(
        serde_json::from_value::<Envelope>(serde_json::to_value(&terminal).unwrap()).unwrap(),
        terminal
    );
}

#[test]
fn real_wire_events_reduce_and_conflicting_replay_fails_closed() {
    let product = agent("v20-product");
    let original = chat_envelope(
        1,
        "event:1",
        "v20-product",
        "message:1",
        "agent",
        ("chunk", Some(1), Some("trusted")),
    );
    let mut state = AppState::controller();
    assert!(state.take_dirty());
    assert_eq!(state.reduce(original.clone()), Ok(ReduceOutcome::Changed));
    assert!(state.take_dirty());
    assert_eq!(state.reduce(original), Ok(ReduceOutcome::Ignored));
    assert!(!state.take_dirty());
    assert_eq!(
        state.chat_store().thread(product).messages()[0].content(),
        "trusted"
    );

    let conflict = chat_envelope(
        1,
        "event:1",
        "v20-product",
        "message:1",
        "agent",
        ("chunk", Some(1), Some("rewritten")),
    );
    assert!(state.reduce(conflict).is_err());
    assert_eq!(state.access, AccessState::ProtocolLockout);
    assert_eq!(
        state.chat_store().thread(product).messages()[0].content(),
        "trusted"
    );
}

#[test]
fn wire_terminal_states_and_reconnect_retain_last_verified_history() {
    let product = agent("v20-product");
    let mut state = AppState::controller();
    state
        .reduce(chat_envelope(
            1,
            "event:1",
            "v20-product",
            "message:1",
            "human",
            ("chunk", Some(1), Some("operator message")),
        ))
        .unwrap();
    state
        .reduce(complete_chat_envelope(
            2,
            "event:2",
            "v20-product",
            "message:1",
            "human",
            "operator message",
        ))
        .unwrap();
    assert_eq!(
        state.chat_store().thread(product).messages()[0].status(),
        ChatMessageStatus::Complete
    );

    let mut client = FoundationClient::from_app(App::new(state));
    client.begin_connection();
    assert_eq!(
        client.app().state().chat_store().thread(product).messages()[0].content(),
        "operator message"
    );
}

#[derive(Default)]
struct SentSession {
    sent: Vec<Envelope>,
}

impl FoundationSession for SentSession {
    fn send<'a>(
        &'a mut self,
        envelope: &'a Envelope,
    ) -> impl Future<Output = Result<(), SessionError>> + Send + 'a {
        self.sent.push(envelope.clone());
        ready(Ok(()))
    }

    fn recv(&mut self) -> impl Future<Output = Result<Envelope, SessionError>> + Send + '_ {
        ready(Err(SessionError::Disconnected))
    }
}

#[tokio::test]
async fn opening_an_agent_emits_and_dispatches_one_strict_history_request() {
    let mut state = AppState::controller();
    state.snapshot = Some(chat_snapshot("v20-product"));
    state.handle(InputEvent::Char('4'));
    state.handle(InputEvent::Char('i'));
    let actions = state.handle(InputEvent::Enter);
    let [ClientAction::ChatHistoryRequest(payload)] = actions.as_slice() else {
        panic!("opening chat must request controller history")
    };
    assert_eq!(payload.agent_id().as_str(), "v20-product");
    assert_eq!(payload.limit(), 20);
    assert_eq!(payload.cursor(), None);
    assert_eq!(state.mode, LocalMode::AgentChat);

    let mut client = FoundationClient::from_app(App::new(state));
    let mut session = SentSession::default();
    let effect = vesper_ratatui_console::app::LoopEffect {
        exit: false,
        foundation_actions: actions,
    };
    assert_eq!(
        client.dispatch(effect, &mut session).await.unwrap(),
        SessionStep::Continue
    );
    assert_eq!(session.sent.len(), 1);
    assert_eq!(
        session.sent[0].message_type(),
        MessageType::ChatHistoryRequest
    );
    let wire = serde_json::to_value(&session.sent[0]).unwrap();
    assert_eq!(wire["payload"]["agent_id"], "v20-product");
    assert_eq!(wire["payload"]["limit"], 20);
    assert_eq!(wire["payload"]["cursor"], serde_json::Value::Null);

    for invalid_limit in [0, 21] {
        let mut invalid = wire.clone();
        invalid["payload"]["limit"] = json!(invalid_limit);
        assert!(serde_json::from_value::<Envelope>(invalid).is_err());
    }
    let mut unapproved_agent = wire.clone();
    unapproved_agent["payload"]["agent_id"] = json!("order:1");
    assert!(serde_json::from_value::<Envelope>(unapproved_agent).is_err());
    let mut missing_cursor = wire;
    missing_cursor["payload"]
        .as_object_mut()
        .unwrap()
        .remove("cursor");
    assert!(serde_json::from_value::<Envelope>(missing_cursor).is_err());
}

#[tokio::test]
async fn page_up_requests_one_older_cursor_and_dispatches_it_through_the_client() {
    let product = agent("v20-product");
    let mut state = AppState::controller();
    state.snapshot = Some(chat_snapshot("v20-product"));
    open_agent_selector(&mut state);
    state.handle(InputEvent::Enter);
    state
        .reduce(chat_envelope(
            1,
            "event:newest:1",
            "v20-product",
            "message:newest",
            "agent",
            ("chunk", Some(1), Some("newest verified")),
        ))
        .unwrap();
    state
        .reduce(chat_history_result_envelope(
            2,
            "v20-product",
            Some("message:newest"),
        ))
        .unwrap();
    state.set_terminal_area(Rect::new(0, 0, 120, 50));
    state.handle(InputEvent::Char('i'));
    assert_eq!(state.mode, LocalMode::AgentInput);

    let actions = state.handle(InputEvent::PageUp);
    let [ClientAction::ChatHistoryRequest(payload)] = actions.as_slice() else {
        panic!("PageUp at the oldest loaded row must request the next page")
    };
    assert_eq!(payload.agent_id().as_str(), "v20-product");
    assert_eq!(
        payload.cursor().map(|cursor| cursor.as_str()),
        Some("message:newest")
    );
    assert!(state.handle(InputEvent::PageUp).is_empty());
    assert_eq!(
        state.chat_store().history_status(product),
        ChatHistoryStatus::Loading
    );
    assert_eq!(
        state.chat_store().thread(product).messages()[0].content(),
        "newest verified"
    );

    let mut client = FoundationClient::from_app(App::new(state));
    let mut session = SentSession::default();
    let effect = vesper_ratatui_console::app::LoopEffect {
        exit: false,
        foundation_actions: actions,
    };
    assert_eq!(
        client.dispatch(effect, &mut session).await.unwrap(),
        SessionStep::Continue
    );
    assert_eq!(session.sent.len(), 1);
    let Message::ChatHistoryRequest(sent) = &session.sent[0].message else {
        panic!("strict history request expected")
    };
    assert_eq!(
        sent.cursor().map(|cursor| cursor.as_str()),
        Some("message:newest")
    );
}

#[test]
fn older_pages_merge_before_newer_messages_and_none_ends_pagination() {
    let product = agent("v20-product");
    let area = Rect::new(0, 0, 120, 50);
    let mut state = AppState::controller();
    state.snapshot = Some(chat_snapshot("v20-product"));
    open_agent_selector(&mut state);
    state.handle(InputEvent::Enter);
    for (sequence, event_id, message_id, text) in [
        (1, "event:middle:1", "message:middle", "middle"),
        (2, "event:newest:1", "message:newest", "newest"),
    ] {
        state
            .reduce(chat_envelope(
                sequence,
                event_id,
                "v20-product",
                message_id,
                "agent",
                ("chunk", Some(1), Some(text)),
            ))
            .unwrap();
    }
    state
        .reduce(chat_history_result_envelope(
            3,
            "v20-product",
            Some("message:middle"),
        ))
        .unwrap();
    state.set_terminal_area(area);
    assert!(matches!(
        state.handle(InputEvent::PageUp).as_slice(),
        [ClientAction::ChatHistoryRequest(_)]
    ));
    let oldest = chat_envelope(
        4,
        "event:oldest:1",
        "v20-product",
        "message:oldest",
        "human",
        ("chunk", Some(1), Some("oldest")),
    );
    state.reduce(oldest.clone()).unwrap();
    assert_eq!(state.reduce(oldest), Ok(ReduceOutcome::Ignored));
    state
        .reduce(chat_history_result_envelope(5, "v20-product", None))
        .unwrap();

    let messages = state.chat_store().thread(product).messages();
    assert_eq!(
        messages
            .iter()
            .map(|message| message.content())
            .collect::<Vec<_>>(),
        ["oldest", "middle", "newest"]
    );
    assert_eq!(state.chat_store().next_cursor(product), None);
    assert!(state.handle(InputEvent::PageUp).is_empty());
    let rendered = render_state(&state, area.width, area.height);
    let oldest = rendered.find("oldest").unwrap();
    let middle = rendered.find("middle").unwrap();
    let newest = rendered.find("newest").unwrap();
    assert!(oldest < middle && middle < newest, "{rendered}");
}

#[test]
fn initial_history_merges_around_retained_live_messages_in_utc_order() {
    let product = agent("v20-product");
    let mut retained_newest = AppState::controller();
    retained_newest
        .reduce(chat_chunk_envelope_at(
            1,
            "event:live-newest",
            "v20-product",
            "message:live-newest",
            "live newest",
            "2026-08-04T12:00:01Z",
        ))
        .unwrap();
    retained_newest.snapshot = Some(chat_snapshot("v20-product"));
    open_agent_selector(&mut retained_newest);
    retained_newest.handle(InputEvent::Enter);
    retained_newest
        .reduce(chat_chunk_envelope_at(
            2,
            "event:history-older",
            "v20-product",
            "message:history-older",
            "history older",
            "2026-08-04T12:00:00.100000Z",
        ))
        .unwrap();
    retained_newest
        .reduce(chat_history_result_envelope(3, "v20-product", None))
        .unwrap();
    assert_eq!(
        retained_newest
            .chat_store()
            .thread(product)
            .messages()
            .iter()
            .map(|message| message.content())
            .collect::<Vec<_>>(),
        ["history older", "live newest"]
    );

    let mut retained_oldest = AppState::controller();
    retained_oldest
        .reduce(chat_chunk_envelope_at(
            1,
            "event:retained-old",
            "v20-product",
            "message:retained-old",
            "retained old",
            "2026-08-04T12:00:00Z",
        ))
        .unwrap();
    retained_oldest.snapshot = Some(chat_snapshot("v20-product"));
    open_agent_selector(&mut retained_oldest);
    retained_oldest.handle(InputEvent::Enter);
    retained_oldest
        .reduce(chat_chunk_envelope_at(
            2,
            "event:latest-new",
            "v20-product",
            "message:latest-new",
            "latest new",
            "2026-08-04T12:00:00.100000Z",
        ))
        .unwrap();
    retained_oldest
        .reduce(chat_history_result_envelope(3, "v20-product", None))
        .unwrap();
    assert_eq!(
        retained_oldest
            .chat_store()
            .thread(product)
            .messages()
            .iter()
            .map(|message| message.content())
            .collect::<Vec<_>>(),
        ["retained old", "latest new"]
    );
}

#[test]
fn initial_history_preserves_authoritative_page_order_for_equal_timestamps() {
    let product = agent("v20-product");
    let mut state = AppState::controller();
    state.snapshot = Some(chat_snapshot("v20-product"));
    open_agent_selector(&mut state);
    state.handle(InputEvent::Enter);
    for (sequence, event_id, message_id, text) in [
        (1, "event:equal:first", "message:z", "first from page"),
        (2, "event:equal:second", "message:a", "second from page"),
    ] {
        state
            .reduce(chat_chunk_envelope_at(
                sequence,
                event_id,
                "v20-product",
                message_id,
                text,
                "2026-08-04T12:00:00.100000Z",
            ))
            .unwrap();
    }
    state
        .reduce(chat_history_result_envelope(3, "v20-product", None))
        .unwrap();
    assert_eq!(
        state
            .chat_store()
            .thread(product)
            .messages()
            .iter()
            .map(|message| message.content())
            .collect::<Vec<_>>(),
        ["first from page", "second from page"]
    );
}

#[test]
fn older_paging_stops_cleanly_before_the_bounded_window_would_become_non_contiguous() {
    let product = agent("v20-product");
    let mut state = AppState::controller();
    state.snapshot = Some(chat_snapshot("v20-product"));
    open_agent_selector(&mut state);
    state.handle(InputEvent::Enter);
    let mut sequence = 1;
    for index in 0..MAX_VISIBLE_MESSAGES_PER_AGENT {
        let message_id = format!("message:cap:{index:03}");
        state
            .reduce(chat_envelope(
                sequence,
                &format!("event:cap:{index:03}:chunk"),
                "v20-product",
                &message_id,
                "agent",
                ("chunk", Some(1), Some("x")),
            ))
            .unwrap();
        sequence += 1;
        state
            .reduce(complete_chat_envelope(
                sequence,
                &format!("event:cap:{index:03}:complete"),
                "v20-product",
                &message_id,
                "agent",
                "x",
            ))
            .unwrap();
        sequence += 1;
    }
    state
        .reduce(chat_history_result_envelope(
            sequence,
            "v20-product",
            Some("message:older-durable"),
        ))
        .unwrap();
    state.set_terminal_area(Rect::new(0, 0, 120, 50));
    assert!(state.handle(InputEvent::PageUp).is_empty());
    assert_eq!(
        state.chat_store().thread(product).messages().len(),
        MAX_VISIBLE_MESSAGES_PER_AGENT
    );
    assert_eq!(
        state
            .chat_store()
            .next_cursor(product)
            .map(|cursor| cursor.as_str()),
        Some("message:older-durable")
    );
}

#[test]
fn older_page_near_byte_cap_fails_closed_without_mutating_the_verified_window() {
    let product = agent("v20-product");
    let mut state = AppState::controller();
    state.snapshot = Some(chat_snapshot("v20-product"));
    open_agent_selector(&mut state);
    state.handle(InputEvent::Enter);
    let block = "x".repeat(64 * 1024);
    let mut full_text = String::new();
    let mut sequence = 1;
    for chunk_sequence in 1..=64 {
        let content = if chunk_sequence == 64 {
            "x".repeat(64 * 1024 - 1)
        } else {
            block.clone()
        };
        full_text.push_str(&content);
        state
            .reduce(chat_envelope(
                sequence,
                &format!("event:large:{chunk_sequence}"),
                "v20-product",
                "message:large",
                "agent",
                ("chunk", Some(chunk_sequence), Some(&content)),
            ))
            .unwrap();
        sequence += 1;
    }
    state
        .reduce(complete_chat_envelope(
            sequence,
            "event:large:complete",
            "v20-product",
            "message:large",
            "agent",
            &full_text,
        ))
        .unwrap();
    sequence += 1;
    state
        .reduce(chat_history_result_envelope(
            sequence,
            "v20-product",
            Some("message:older"),
        ))
        .unwrap();
    state.set_terminal_area(Rect::new(0, 0, u16::MAX, u16::MAX));
    assert!(matches!(
        state.handle(InputEvent::PageUp).as_slice(),
        [ClientAction::ChatHistoryRequest(_)]
    ));

    let rejected = state.reduce(chat_envelope(
        sequence + 1,
        "event:older:too-large",
        "v20-product",
        "message:older",
        "agent",
        ("chunk", Some(1), Some("yy")),
    ));
    assert!(rejected.is_err());
    assert_eq!(state.access, AccessState::ProtocolLockout);
    let messages = state.chat_store().thread(product).messages();
    assert_eq!(messages.len(), 1);
    assert_eq!(messages[0].message_id(), "message:large");
    assert_eq!(messages[0].content().len(), MAX_RETAINED_CHAT_BYTES - 1);
    assert_eq!(
        state.chat_store().retained_text_bytes(),
        MAX_RETAINED_CHAT_BYTES - 1
    );
}

#[test]
fn concurrent_other_agent_traffic_cannot_overfill_or_resurrect_at_page_commit() {
    let product = agent("v20-product");
    let risk = agent("v20-risk-review");
    let mut state = AppState::controller();
    state.snapshot = Some(chat_snapshot("v20-product"));
    open_agent_selector(&mut state);
    state.handle(InputEvent::Enter);
    state
        .reduce(chat_envelope(
            1,
            "event:product:chunk",
            "v20-product",
            "message:product",
            "agent",
            ("chunk", Some(1), Some("product")),
        ))
        .unwrap();
    state
        .reduce(complete_chat_envelope(
            2,
            "event:product:complete",
            "v20-product",
            "message:product",
            "agent",
            "product",
        ))
        .unwrap();
    state
        .reduce(chat_history_result_envelope(
            3,
            "v20-product",
            Some("message:older"),
        ))
        .unwrap();
    state.set_terminal_area(Rect::new(0, 0, u16::MAX, u16::MAX));
    assert!(matches!(
        state.handle(InputEvent::PageUp).as_slice(),
        [ClientAction::ChatHistoryRequest(_)]
    ));

    let mut sequence = 4_u64;
    for index in 0..=MAX_VISIBLE_MESSAGES_PER_AGENT {
        let message_id = format!("message:risk:{index:03}");
        state
            .reduce(chat_envelope(
                sequence,
                &format!("event:risk:{index:03}:chunk"),
                "v20-risk-review",
                &message_id,
                "agent",
                ("chunk", Some(1), Some("risk")),
            ))
            .unwrap();
        sequence += 1;
        state
            .reduce(complete_chat_envelope(
                sequence,
                &format!("event:risk:{index:03}:complete"),
                "v20-risk-review",
                &message_id,
                "agent",
                "risk",
            ))
            .unwrap();
        sequence += 1;
    }
    assert!(state.chat_store().thread(product).messages().is_empty());
    assert_eq!(
        state.chat_store().thread(risk).messages().len(),
        MAX_VISIBLE_MESSAGES_PER_AGENT
    );
    assert!(
        state
            .reduce(chat_history_result_envelope(sequence, "v20-product", None))
            .is_err()
    );
    assert_eq!(state.access, AccessState::ProtocolLockout);
    assert!(state.chat_store().thread(product).messages().is_empty());
}

#[test]
fn history_result_requires_a_matching_request_and_preserves_the_cursor() {
    let mut unsolicited = AppState::controller();
    assert!(
        unsolicited
            .reduce(chat_history_result_envelope(1, "v20-product", None))
            .is_err()
    );
    assert_eq!(unsolicited.access, AccessState::ProtocolLockout);

    let mut wrong_agent = AppState::controller();
    wrong_agent.snapshot = Some(chat_snapshot("v20-product"));
    open_agent_selector(&mut wrong_agent);
    wrong_agent.handle(InputEvent::Enter);
    assert!(
        wrong_agent
            .reduce(chat_history_result_envelope(1, "v20-risk-review", None))
            .is_err()
    );
    assert_eq!(wrong_agent.access, AccessState::ProtocolLockout);

    let product = agent("v20-product");
    let mut state = AppState::controller();
    state.snapshot = Some(chat_snapshot("v20-product"));
    state.handle(InputEvent::Char('4'));
    state.handle(InputEvent::Char('i'));
    state.handle(InputEvent::Enter);
    assert!(state.take_dirty());
    assert_eq!(
        state.chat_store().history_status(product),
        ChatHistoryStatus::Loading
    );
    assert_eq!(
        state.reduce(chat_history_result_envelope(
            1,
            "v20-product",
            Some("message:older")
        )),
        Ok(ReduceOutcome::Changed)
    );
    assert!(state.take_dirty());
    assert_eq!(
        state.chat_store().history_status(product),
        ChatHistoryStatus::Available
    );
    assert_eq!(
        state
            .chat_store()
            .next_cursor(product)
            .map(|cursor| cursor.as_str()),
        Some("message:older")
    );

    let mut missing_cursor =
        serde_json::to_value(chat_history_result_envelope(2, "v20-product", None)).unwrap();
    missing_cursor["payload"]
        .as_object_mut()
        .unwrap()
        .remove("next_cursor");
    assert!(serde_json::from_value::<Envelope>(missing_cursor).is_err());
    let mut unapproved =
        serde_json::to_value(chat_history_result_envelope(2, "v20-product", None)).unwrap();
    unapproved["payload"]["agent_id"] = json!("portfolio-research");
    assert!(serde_json::from_value::<Envelope>(unapproved).is_err());
}

#[test]
fn chat_history_focus_follows_tail_and_pages_without_sending() {
    let area = Rect::new(0, 0, 80, 40);
    let mut state = AppState::controller();
    state.snapshot = Some(chat_snapshot("v20-product"));
    state.handle(InputEvent::Char('4'));
    state.handle(InputEvent::Char('i'));
    state.handle(InputEvent::Enter);
    assert_eq!(state.mode, LocalMode::AgentChat);
    for index in 0..24_u64 {
        state
            .reduce(chat_envelope(
                index + 1,
                &format!("event:{index}"),
                "v20-product",
                &format!("message:{index}"),
                "agent",
                ("chunk", Some(1), Some(&format!("history line {index:02}"))),
            ))
            .unwrap();
    }
    state
        .reduce(chat_history_result_envelope(25, "v20-product", None))
        .unwrap();
    state.set_terminal_area(area);
    let tail = render_state(&state, area.width, area.height);
    assert!(tail.contains("history line 23"), "{tail}");
    assert!(state.handle(InputEvent::Enter).is_empty());

    state.handle(InputEvent::PageUp);
    let earlier = render_state(&state, area.width, area.height);
    assert!(earlier.contains("history line 00"), "{earlier}");
    assert!(!earlier.contains("history line 23"), "{earlier}");
    state
        .reduce(chat_envelope(
            26,
            "event:24",
            "v20-product",
            "message:24",
            "agent",
            ("chunk", Some(1), Some("new live tail")),
        ))
        .unwrap();
    assert!(!render_state(&state, area.width, area.height).contains("new live tail"));

    state.handle(InputEvent::PageDown);
    state.handle(InputEvent::PageDown);
    let resumed = render_state(&state, area.width, area.height);
    assert!(resumed.contains("new live tail"), "{resumed}");
    state.handle(InputEvent::Char('i'));
    assert_eq!(state.mode, LocalMode::AgentInput);
    for character in format!("{}VISIBLE-TAIL", "x".repeat(200)).chars() {
        state.handle(InputEvent::Char(character));
    }
    let input = buffer_region(
        &render_buffer(&state, area.width, area.height),
        chat_shell_layout(area, state.display_mode()).input,
    );
    assert!(input.contains("VISIBLE-TAIL"), "{input}");
}

#[test]
fn maximum_size_chat_uses_a_bounded_narrow_tail_window() {
    const RENDER_WINDOW_ROWS: usize = 4_096;
    const CHUNK_BYTES: usize = 64 * 1024;
    const CHUNK_COUNT: usize = MAX_RETAINED_CHAT_BYTES / CHUNK_BYTES;
    const NEWEST_TAIL: &str = "4MIB-TAIL";

    let product = agent("v20-product");
    let mut state = AppState::controller();
    state.snapshot = Some(chat_snapshot(product.as_str()));
    open_agent_selector(&mut state);
    state.handle(InputEvent::Enter);

    let ordinary_chunk = "x".repeat(CHUNK_BYTES);
    let final_chunk = format!(
        "{}{}",
        "x".repeat(CHUNK_BYTES - NEWEST_TAIL.len()),
        NEWEST_TAIL
    );
    let mut complete_content = String::with_capacity(MAX_RETAINED_CHAT_BYTES);
    for chunk_index in 0..CHUNK_COUNT {
        let chunk = if chunk_index + 1 == CHUNK_COUNT {
            &final_chunk
        } else {
            &ordinary_chunk
        };
        complete_content.push_str(chunk);
        state
            .reduce(chat_envelope(
                u64::try_from(chunk_index + 1).unwrap(),
                &format!("event:max:{chunk_index}:chunk"),
                product.as_str(),
                "message:max",
                "agent",
                (
                    "chunk",
                    Some(u64::try_from(chunk_index + 1).unwrap()),
                    Some(chunk),
                ),
            ))
            .unwrap();
    }
    assert_eq!(complete_content.len(), MAX_RETAINED_CHAT_BYTES);
    state
        .reduce(complete_chat_envelope(
            u64::try_from(CHUNK_COUNT + 1).unwrap(),
            "event:max:complete",
            product.as_str(),
            "message:max",
            "agent",
            &complete_content,
        ))
        .unwrap();
    state
        .reduce(chat_history_result_envelope(
            u64::try_from(CHUNK_COUNT + 2).unwrap(),
            product.as_str(),
            None,
        ))
        .unwrap();

    let area = Rect::new(0, 0, 34, 30);
    state.set_terminal_area(area);
    let rendered = render_state(&state, area.width, area.height);
    assert!(
        rendered.contains(NEWEST_TAIL),
        "newest tail must be visible:\n{rendered}"
    );
    assert!(
        rendered.contains("TAIL WINDOW"),
        "bounded tail must be labeled"
    );

    state.handle(InputEvent::PageUp);
    assert!(!state.chat_follows_tail(product));
    assert!(
        state.chat_scroll_offset(product) <= RENDER_WINDOW_ROWS,
        "scroll offset must stay within the bounded render window"
    );
    assert_eq!(
        state.chat_store().thread(product).messages()[0]
            .content()
            .len(),
        MAX_RETAINED_CHAT_BYTES,
        "render virtualization must not truncate durable chat state"
    );
}
