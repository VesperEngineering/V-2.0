"""Tests for the bounded, strict V20 console wire framing."""

from __future__ import annotations

from hashlib import sha256
import json
import struct
import sys
from datetime import datetime, timezone

import pytest

import vesper.platform.tui.protocol as protocol
from vesper.platform.tui.contracts import MessageType, UntrustedProtocolDiagnostic, WireEnvelope
from vesper.platform.tui.protocol import (
    MAX_FRAME_BYTES,
    FrameDecoder,
    ProtocolViolation,
    encode_frame,
)


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


@pytest.mark.parametrize(
    "raw",
    [
        b"[" * 1_500 + b"0" + b"]" * 1_500,
        b"9" * 4_301,
    ],
    ids=("deep-json", "long-integer"),
)
def test_decoder_normalizes_parser_resource_errors(raw: bytes) -> None:
    decoder = FrameDecoder()

    with pytest.raises(ProtocolViolation) as raised:
        decoder.feed(struct.pack(">I", len(raw)) + raw)

    assert raised.value.code == "invalid-json"
    assert raw[:16].decode("ascii") not in raised.value.safe_message


@pytest.mark.parametrize(
    "failure",
    [
        RecursionError("second parser exhausted"),
        ValueError("second parser rejected a number"),
        json.JSONDecodeError("second parser invalid JSON", "{}", 0),
    ],
    ids=("recursion", "value", "json"),
)
def test_decoder_normalizes_second_contract_parser_failure(
    monkeypatch: pytest.MonkeyPatch,
    server_hello: WireEnvelope,
    failure: Exception,
) -> None:
    raw = server_hello.model_dump_json().encode("utf-8")

    def raise_recursion(*_: object) -> WireEnvelope:
        raise failure

    monkeypatch.setattr(protocol, "decode_envelope_json", raise_recursion)
    decoder = FrameDecoder()

    with pytest.raises(ProtocolViolation) as raised:
        decoder.feed(struct.pack(">I", len(raw)) + raw)

    assert raised.value.code == "invalid-json"
    assert "server-hello" not in raised.value.safe_message


def test_callback_reentry_then_failure_clears_the_outer_decoder(
    server_hello: WireEnvelope,
) -> None:
    raw = (
        b'{"schema_version":1,"message_id":"lease:1","sequence":1,'
        b'"state_version":0,"timestamp_utc":"2026-08-03T00:00:00Z",'
        b'"message_type":"lease-request",'
        b'"payload":{"action":"take-control","secret":"x"}}'
    )
    decoder = FrameDecoder()

    def receive(_: UntrustedProtocolDiagnostic) -> None:
        assert decoder.feed(b"\x00\x00") == ()
        raise RuntimeError("callback failure")

    decoder = FrameDecoder(on_untrusted=receive)
    with pytest.raises(RuntimeError, match="callback failure"):
        decoder.feed(struct.pack(">I", len(raw)) + raw)

    assert decoder.feed(encode_frame(server_hello)) == (server_hello,)


def test_unknown_field_diagnostic_has_the_complete_frame_hash() -> None:
    raw = (
        b'{"schema_version":1,"message_id":"lease:1","sequence":1,'
        b'"state_version":0,"timestamp_utc":"2026-08-03T00:00:00Z",'
        b'"message_type":"lease-request",'
        b'"payload":{"action":"take-control","secret":"x"}}'
    )
    seen: list[str] = []
    decoder = FrameDecoder(on_untrusted=lambda diagnostic: seen.append(diagnostic.frame_sha256))

    with pytest.raises(ProtocolViolation, match="unsupported fields"):
        decoder.feed(struct.pack(">I", len(raw)) + raw)

    assert seen == [sha256(raw).hexdigest()]


def test_encode_frame_rejects_an_oversized_body(server_hello: WireEnvelope) -> None:
    oversized = server_hello.model_copy(
        update={
            "payload": {
                "server_version": "x" * MAX_FRAME_BYTES,
                "requires_setup": True,
            }
        }
    )

    with pytest.raises(ProtocolViolation) as raised:
        encode_frame(oversized)

    assert raised.value.code == "frame-size"
