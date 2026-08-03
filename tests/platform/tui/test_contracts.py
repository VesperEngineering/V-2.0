"""Tests for the strict Python/Rust console wire contract."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from vesper.platform.tui.contracts import (
    ClientHelloPayload,
    LeaseRequestPayload,
    MessageType,
    SnapshotRequestPayload,
    UntrustedProtocolDiagnostic,
    WireEnvelope,
    decode_envelope_json,
    decode_payload,
)


def _envelope(**changes: object) -> WireEnvelope:
    values: dict[str, object] = {
        "schema_version": 1,
        "message_id": "server:1",
        "sequence": 1,
        "state_version": 0,
        "timestamp_utc": datetime(2026, 8, 3, tzinfo=timezone.utc),
        "message_type": MessageType.SERVER_HELLO,
        "payload": {"server_version": "0.1.0", "requires_setup": True},
    }
    values.update(changes)
    return WireEnvelope(**values)


def test_envelope_round_trips_and_rejects_unknown_fields() -> None:
    value = _envelope()

    assert WireEnvelope.model_validate_json(value.model_dump_json()) == value
    with pytest.raises(ValidationError):
        WireEnvelope.model_validate({**value.model_dump(), "secret": "x"})


@pytest.mark.parametrize(
    "timestamp",
    [
        datetime(2026, 8, 3),
        datetime(2026, 8, 3, tzinfo=timezone(timedelta(hours=-4))),
    ],
)
def test_envelope_rejects_non_utc_timestamps(timestamp: datetime) -> None:
    with pytest.raises(ValidationError):
        _envelope(timestamp_utc=timestamp)


def test_z_timestamp_round_trips_in_canonical_python_and_rust_wire_form() -> None:
    wire = (
        '{"schema_version":1,"message_id":"server:1","sequence":1,'
        '"state_version":0,"timestamp_utc":"2026-08-03T00:00:00Z",'
        '"message_type":"server-hello",'
        '"payload":{"server_version":"0.1.0","requires_setup":true}}'
    )

    assert WireEnvelope.model_validate_json(wire).model_dump_json() == wire


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("message_id", ""),
        ("message_id", "."),
        ("message_id", ".."),
        ("message_id", "not valid"),
        ("sequence", -1),
        ("state_version", -1),
        ("schema_version", 2),
        ("message_type", "unknown"),
    ],
)
def test_envelope_rejects_invalid_wire_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        _envelope(**{field: value})


def test_decode_payload_maps_only_the_matching_exact_model() -> None:
    assert isinstance(
        decode_payload(
            _envelope(
                message_type=MessageType.CLIENT_HELLO,
                payload={"client_version": "0.1.0", "supported_schema_versions": [1]},
            )
        ),
        ClientHelloPayload,
    )
    assert isinstance(
        decode_payload(_envelope(message_type=MessageType.SNAPSHOT_REQUEST, payload={})),
        SnapshotRequestPayload,
    )
    with pytest.raises(ValidationError):
        decode_payload(
            _envelope(
                message_type=MessageType.LEASE_REQUEST,
                payload={"action": "take-control", "operator_id": "secret"},
            )
        )
    with pytest.raises(ValidationError):
        LeaseRequestPayload(action="release")


def test_unknown_fields_only_reach_a_synchronous_untrusted_callback() -> None:
    wire = (
        b'{"schema_version":1,"message_id":"server:1","sequence":1,'
        b'"state_version":0,"timestamp_utc":"2026-08-03T00:00:00Z",'
        b'"message_type":"lease-request",'
        b'"payload":{"action":"take-control","secret":"x"}}'
    )
    diagnostics: list[UntrustedProtocolDiagnostic] = []

    with pytest.raises(ValidationError):
        decode_envelope_json(wire, diagnostics.append)

    assert len(diagnostics) == 1
    assert diagnostics[0].unknown_fields == {"secret": "x"}
    assert len(diagnostics[0].frame_sha256) == 64
