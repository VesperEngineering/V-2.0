from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import BaseModel

from vesper.platform.tui.contracts import (
    MessageType,
    PongPayload,
    ProtocolErrorPayload,
    WireEnvelope,
    decode_payload,
)
from vesper.platform.tui.outbox import MAX_OUTBOX_BYTES, OutboundQueue
from vesper.platform.tui.protocol import MAX_FRAME_BYTES


NOW = datetime(2026, 8, 3, tzinfo=timezone.utc)


class _BlobPayload(BaseModel):
    blob: str


def test_exact_total_byte_budget_overflow_resets_to_terminal_sequence() -> None:
    payload = PongPayload(nonce="one")
    expected = WireEnvelope(
        schema_version=1,
        message_id="server:1",
        sequence=1,
        state_version=0,
        timestamp_utc=NOW,
        message_type=MessageType.PONG,
        payload=payload.model_dump(mode="json"),
    )
    one_frame_bytes = len(expected.model_dump_json().encode("utf-8"))
    outbox = OutboundQueue(max_bytes=one_frame_bytes * 2 - 1)

    admitted = outbox.admit(MessageType.PONG, payload, 0, NOW)
    assert admitted == expected
    overflow = outbox.admit(MessageType.PONG, payload, 0, NOW)

    assert overflow.sequence == 1
    assert decode_payload(overflow) == ProtocolErrorPayload(
        code="resnapshot-required",
        safe_message="Outbound state was not preserved; request a new snapshot.",
    )
    assert outbox.pop() == overflow
    with pytest.raises(ConnectionAbortedError, match="resnapshot-required"):
        outbox.pop()


def test_envelope_over_one_mib_is_never_queued() -> None:
    outbox = OutboundQueue(max_bytes=MAX_OUTBOX_BYTES)
    payload = _BlobPayload(blob="x" * MAX_FRAME_BYTES)

    overflow = outbox.admit(MessageType.PONG, payload, 0, NOW)

    assert overflow.sequence == 1
    assert overflow.message_type is MessageType.PROTOCOL_ERROR
    assert len(overflow.model_dump_json().encode("utf-8")) <= MAX_FRAME_BYTES
    assert outbox.pop() == overflow
    with pytest.raises(ConnectionAbortedError, match="resnapshot-required"):
        outbox.pop()


def test_replacement_only_coalesces_at_tail_to_preserve_state_order() -> None:
    outbox = OutboundQueue()
    old_metric = outbox.admit(
        MessageType.PONG,
        PongPayload(nonce="old-metric"),
        1,
        NOW,
        replace_key=("metric", "cpu"),
    )
    required = outbox.admit(
        MessageType.PONG,
        PongPayload(nonce="required"),
        1,
        NOW,
    )
    new_metric = outbox.admit(
        MessageType.PONG,
        PongPayload(nonce="new-metric"),
        2,
        NOW,
        replace_key=("metric", "cpu"),
    )

    assert [old_metric.sequence, required.sequence, new_metric.sequence] == [1, 2, 3]
    assert [outbox.pop(), outbox.pop(), outbox.pop()] == [
        old_metric,
        required,
        new_metric,
    ]
