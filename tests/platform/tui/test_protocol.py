"""Tests for the bounded, strict V20 console wire framing."""

from __future__ import annotations

import struct
import sys
from datetime import datetime, timezone

import pytest

from vesper.platform.tui.contracts import MessageType, UntrustedProtocolDiagnostic, WireEnvelope
from vesper.platform.tui.protocol import FrameDecoder, ProtocolViolation, encode_frame


@pytest.fixture
def server_hello() -> WireEnvelope:
    return WireEnvelope(
        schema_version=1,
        message_id="server:1",
        sequence=1,
        state_version=0,
        timestamp_utc=datetime(2026, 8, 3, tzinfo=timezone.utc),
        message_type=MessageType.SERVER_HELLO,
        payload={"server_version": "0.1.0", "requires_setup": True},
    )


@pytest.fixture
def ping() -> WireEnvelope:
    return WireEnvelope(
        schema_version=1,
        message_id="ping:2",
        sequence=2,
        state_version=0,
        timestamp_utc=datetime(2026, 8, 3, tzinfo=timezone.utc),
        message_type=MessageType.PING,
        payload={"nonce": "nonce:2"},
    )


def test_decoder_handles_split_and_joined_frames(
    server_hello: WireEnvelope,
    ping: WireEnvelope,
) -> None:
    body = encode_frame(server_hello) + encode_frame(ping)
    decoder = FrameDecoder()

    assert decoder.feed(body[:3]) == ()
    assert decoder.feed(body[3:11]) == ()
    assert decoder.feed(body[11:]) == (server_hello, ping)


@pytest.mark.parametrize(
    ("frame", "code"),
    [
        (struct.pack(">I", 0), "frame-size"),
        (struct.pack(">I", 1_048_577), "frame-size"),
        (struct.pack(">I", 1) + b"\xff", "invalid-utf8"),
        (struct.pack(">I", 1) + b"{", "invalid-json"),
        (
            struct.pack(">I", len(b'{"schema_version":2}'))
            + b'{"schema_version":2}',
            "schema-version",
        ),
        (
            struct.pack(
                ">I",
                len(
                    b'{"schema_version":1,"message_id":"server:1","sequence":1,'
                    b'"state_version":0,"timestamp_utc":"2026-08-03T00:00:00Z",'
                    b'"message_type":"server-hello","payload":{}}'
                ),
            )
            + b'{"schema_version":1,"message_id":"server:1","sequence":1,'
            + b'"state_version":0,"timestamp_utc":"2026-08-03T00:00:00Z",'
            + b'"message_type":"server-hello","payload":{}}',
            "invalid-payload",
        ),
    ],
)
def test_decoder_rejects_bad_frames_with_safe_errors(frame: bytes, code: str) -> None:
    decoder = FrameDecoder()

    with pytest.raises(ProtocolViolation) as raised:
        decoder.feed(frame)

    assert raised.value.code == code
    assert "{" not in raised.value.safe_message
    assert "ff" not in raised.value.safe_message.lower()
    assert raised.value.safe_message


def test_decoder_clears_buffer_after_a_fatal_violation(server_hello: WireEnvelope) -> None:
    decoder = FrameDecoder()

    with pytest.raises(ProtocolViolation, match="Frame size is invalid"):
        decoder.feed(struct.pack(">I", 1_048_577) + encode_frame(server_hello))

    assert decoder.feed(encode_frame(server_hello)) == (server_hello,)


def test_decoder_reports_unknown_fields_only_during_callback() -> None:
    raw = (
        b'{"schema_version":1,"message_id":"lease:1","sequence":1,'
        b'"state_version":0,"timestamp_utc":"2026-08-03T00:00:00Z",'
        b'"message_type":"lease-request",'
        b'"payload":{"action":"take-control","secret":"x"}}'
    )
    seen: list[bool] = []
    active_exceptions: list[BaseException | None] = []
    retained: list[UntrustedProtocolDiagnostic] = []

    def receive(diagnostic: UntrustedProtocolDiagnostic) -> None:
        seen.append(diagnostic.unknown_fields["secret"] == "x")
        active_exceptions.append(sys.exception())
        retained.append(diagnostic)

    decoder = FrameDecoder(on_untrusted=receive)
    with pytest.raises(ProtocolViolation) as raised:
        decoder.feed(struct.pack(">I", len(raw)) + raw)

    assert raised.value.code == "unknown-field"
    assert seen == [True]
    assert active_exceptions == [None]
    assert retained[0].unknown_fields == {}
