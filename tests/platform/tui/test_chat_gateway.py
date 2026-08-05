from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from vesper.platform.tui.contracts import (
    ChatEventPayload,
    ChatHistoryResultPayload,
    MessageType,
    ProtocolErrorPayload,
    WireEnvelope,
    decode_payload,
)
from vesper.platform.tui.conversations import ConversationStore
from vesper.platform.tui.gateway import Gateway


NOW = datetime(2026, 8, 4, tzinfo=timezone.utc)


def envelope(message_type: MessageType, sequence: int, payload: dict[str, object]) -> WireEnvelope:
    return WireEnvelope(
        schema_version=1,
        message_id=f"client:{sequence}",
        sequence=sequence,
        state_version=0,
        timestamp_utc=NOW,
        message_type=message_type,
        payload=payload,
    )


def send_one(
    gateway: Gateway,
    client_id: str,
    message_type: MessageType,
    sequence: int,
    **payload: object,
) -> WireEnvelope:
    responses = gateway.handle(client_id, envelope(message_type, sequence, payload))
    assert len(responses) == 1
    return responses[0]


def setup(gateway: Gateway, client_id: str = "operator") -> None:
    send_one(
        gateway,
        client_id,
        MessageType.CLIENT_HELLO,
        1,
        client_version="0.1.0",
        supported_schema_versions=[1],
    )
    result = send_one(
        gateway,
        client_id,
        MessageType.AUTH_SETUP,
        2,
        password="correct horse",
        confirmation="correct horse",
    )
    assert result.payload["success"] is True


def unlock(gateway: Gateway, client_id: str) -> None:
    send_one(
        gateway,
        client_id,
        MessageType.CLIENT_HELLO,
        1,
        client_version="0.1.0",
        supported_schema_versions=[1],
    )
    result = send_one(
        gateway,
        client_id,
        MessageType.AUTH_UNLOCK,
        2,
        password="correct horse",
    )
    assert result.payload["success"] is True


def drain(gateway: Gateway, client_id: str) -> tuple[WireEnvelope, ...]:
    frames: list[WireEnvelope] = []
    while (frame := gateway.poll(client_id)) is not None:
        frames.append(frame)
    return tuple(frames)


def add_interrupted_message(
    store: ConversationStore,
    text: str,
    created_at: datetime,
) -> str:
    message = store.start_message("v20-risk-review", "agent", created_at)
    store.append_chunk(message.message_id, 1, text, token_count=1)
    store.interrupt(message.message_id, created_at + timedelta(milliseconds=1))
    return message.message_id


def chat_event() -> ChatEventPayload:
    return ChatEventPayload.model_validate(
        {
            "event_id": "chat:live:1",
            "agent_id": "v20-risk-review",
            "message_id": "message:live:1",
            "role": "agent",
            "operation": "chunk",
            "chunk_sequence": 1,
            "text": "Reviewing risk.",
            "token_count": 3,
            "message_created_at_utc": NOW,
            "occurred_at_utc": None,
            "validation_receipt_id": None,
            "raw_text_sha256": None,
        }
    )


def test_gateway_requires_exact_conversation_store_type(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="conversation_store must be a ConversationStore"):
        Gateway(tmp_path, conversation_store=object())  # type: ignore[arg-type]


def test_authenticated_history_emits_newest_page_chronologically_then_cursor(
    tmp_path: Path,
) -> None:
    ids = iter(("message:old", "message:middle", "message:new"))
    store = ConversationStore(tmp_path / "conversations.sqlite3", id_factory=ids.__next__)
    old = add_interrupted_message(store, "old", NOW)
    middle = add_interrupted_message(store, "middle", NOW + timedelta(seconds=1))
    new = add_interrupted_message(store, "new", NOW + timedelta(seconds=2))
    gateway = Gateway(tmp_path / "state", conversation_store=store)
    setup(gateway)

    responses = gateway.handle(
        "operator",
        envelope(
            MessageType.CHAT_HISTORY_REQUEST,
            3,
            {"agent_id": "v20-risk-review", "limit": 2, "cursor": None},
        ),
    )

    assert [response.message_type for response in responses] == [
        MessageType.CHAT_EVENT,
        MessageType.CHAT_EVENT,
        MessageType.CHAT_EVENT,
        MessageType.CHAT_EVENT,
        MessageType.CHAT_HISTORY_RESULT,
    ]
    events = [decode_payload(response) for response in responses[:-1]]
    assert [(event.message_id, event.operation, event.text) for event in events] == [
        (middle, "chunk", "middle"),
        (middle, "interrupted", None),
        (new, "chunk", "new"),
        (new, "interrupted", None),
    ]
    assert decode_payload(responses[-1]) == ChatHistoryResultPayload(
        agent_id="v20-risk-review",
        next_cursor=middle,
    )
    assert old not in {event.message_id for event in events}
    store.close()


def test_locked_history_request_is_rejected_before_store_access(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path / "conversations.sqlite3")
    gateway = Gateway(tmp_path / "state", conversation_store=store)

    response = send_one(
        gateway,
        "locked",
        MessageType.CHAT_HISTORY_REQUEST,
        1,
        agent_id="v20-risk-review",
        limit=1,
        cursor=None,
    )

    assert decode_payload(response) == ProtocolErrorPayload(
        code="locked",
        safe_message="Console session is locked.",
    )
    store.close()


@pytest.mark.parametrize("failure", ["unavailable", "corrupt"])
def test_history_failure_is_generic_and_emits_no_chat_events(
    tmp_path: Path,
    failure: str,
) -> None:
    store: ConversationStore | None = None
    if failure == "corrupt":
        database = tmp_path / "conversations.sqlite3"
        seed = ConversationStore(database, id_factory=lambda: "message:corrupt")
        message_id = add_interrupted_message(seed, "trusted", NOW)
        seed.close()
        with sqlite3.connect(database) as connection:
            connection.execute(
                "UPDATE conversation_chunks SET text = 'tampered' WHERE message_id = ?",
                (message_id,),
            )
        store = ConversationStore(database)
    gateway = Gateway(tmp_path / "state", conversation_store=store)
    setup(gateway)

    responses = gateway.handle(
        "operator",
        envelope(
            MessageType.CHAT_HISTORY_REQUEST,
            3,
            {"agent_id": "v20-risk-review", "limit": 1, "cursor": None},
        ),
    )

    assert len(responses) == 1
    assert responses[0].message_type is MessageType.PROTOCOL_ERROR
    assert decode_payload(responses[0]) == ProtocolErrorPayload(
        code="chat-unavailable",
        safe_message="Chat history is unavailable.",
    )
    assert all(response.message_type is not MessageType.CHAT_EVENT for response in responses)
    if store is not None:
        store.close()


def test_maximum_history_event_page_stays_within_outbox_bounds(tmp_path: Path) -> None:
    store = ConversationStore(
        tmp_path / "conversations.sqlite3",
        id_factory=lambda: "message:maximum-page",
    )
    message = store.start_message("v20-risk-review", "agent", NOW)
    for sequence in range(1, 128):
        store.append_chunk(message.message_id, sequence, str(sequence))
    store.interrupt(message.message_id, NOW + timedelta(seconds=1))
    gateway = Gateway(tmp_path / "state", conversation_store=store)
    setup(gateway)

    responses = gateway.handle(
        "operator",
        envelope(
            MessageType.CHAT_HISTORY_REQUEST,
            3,
            {"agent_id": "v20-risk-review", "limit": 1, "cursor": None},
        ),
    )

    assert len(responses) == 129
    assert sum(response.message_type is MessageType.CHAT_EVENT for response in responses) == 128
    assert responses[-1].message_type is MessageType.CHAT_HISTORY_RESULT
    assert all(response.message_type is not MessageType.PROTOCOL_ERROR for response in responses)
    store.close()


def test_live_chat_event_reaches_only_authenticated_subscribers(tmp_path: Path) -> None:
    gateway = Gateway(tmp_path)
    setup(gateway, "subscriber")
    unlock(gateway, "viewer")
    send_one(gateway, "subscriber", MessageType.SNAPSHOT_REQUEST, 3)
    drain(gateway, "subscriber")
    drain(gateway, "viewer")
    event = chat_event()

    gateway.publish_chat_event(event)

    delivered = gateway.poll("subscriber")
    assert delivered is not None
    assert delivered.message_type is MessageType.CHAT_EVENT
    assert decode_payload(delivered) == event
    assert gateway.poll("subscriber") is None
    assert gateway.poll("viewer") is None


def test_live_chat_event_requires_an_exact_valid_chat_payload(tmp_path: Path) -> None:
    gateway = Gateway(tmp_path)
    with pytest.raises(TypeError, match="event must be a ChatEventPayload"):
        gateway.publish_chat_event({"event_id": "chat:not-a-model"})  # type: ignore[arg-type]

    invalid = chat_event().model_copy(update={"operation": "complete"})
    with pytest.raises(ValidationError):
        gateway.publish_chat_event(invalid)


def test_projection_runtime_attaches_and_closes_durable_chat_store(tmp_path: Path) -> None:
    from vesper.platform.persistence import PlatformPaths
    from vesper.platform.tui import cli
    from vesper.platform.tui.conversations import ConversationError

    gateway = Gateway(tmp_path / "auth")
    runtime = cli._build_projection_runtime(
        tmp_path / "state",
        gateway,
        platform_paths=PlatformPaths.below(tmp_path / "platform"),
    )
    store = runtime.conversation_store
    assert store is not None
    add_interrupted_message(store, "durable", NOW)
    setup(gateway)

    responses = gateway.handle(
        "operator",
        envelope(
            MessageType.CHAT_HISTORY_REQUEST,
            3,
            {"agent_id": "v20-risk-review", "limit": 1, "cursor": None},
        ),
    )

    assert [frame.message_type for frame in responses] == [
        MessageType.CHAT_EVENT,
        MessageType.CHAT_EVENT,
        MessageType.CHAT_HISTORY_RESULT,
    ]
    runtime.close()
    with pytest.raises(ConversationError, match="closed"):
        store.export_history("v20-risk-review", 1, None)


def test_pipe_connection_drains_multi_frame_chat_history(tmp_path: Path) -> None:
    from vesper.platform.tui.cli import _GatewayConnection, _GatewayCoordinator

    store = ConversationStore(tmp_path / "conversations.sqlite3")
    add_interrupted_message(store, "wire history", NOW)
    gateway = Gateway(tmp_path / "state", conversation_store=store)
    coordinator = _GatewayCoordinator(gateway)
    connection = _GatewayConnection(coordinator, "pipe:chat")

    def call(message_type: MessageType, sequence: int, payload: dict[str, object]) -> WireEnvelope:
        body = envelope(message_type, sequence, payload).model_dump_json().encode("utf-8")
        response = connection(body)
        assert response is not None
        return WireEnvelope.model_validate_json(response)

    try:
        assert (
            call(
                MessageType.CLIENT_HELLO,
                1,
                {"client_version": "0.1.0", "supported_schema_versions": [1]},
            ).message_type
            is MessageType.SERVER_HELLO
        )
        assert (
            call(
                MessageType.AUTH_SETUP,
                2,
                {"password": "correct horse", "confirmation": "correct horse"},
            ).message_type
            is MessageType.AUTH_RESULT
        )

        frames = [
            call(
                MessageType.CHAT_HISTORY_REQUEST,
                3,
                {"agent_id": "v20-risk-review", "limit": 1, "cursor": None},
            )
        ]
        while (raw := connection.poll()) is not None:
            frames.append(WireEnvelope.model_validate_json(raw))

        assert [frame.message_type for frame in frames] == [
            MessageType.CHAT_EVENT,
            MessageType.CHAT_EVENT,
            MessageType.CHAT_HISTORY_RESULT,
        ]
    finally:
        coordinator.stop()
        store.close()
