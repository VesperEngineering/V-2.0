"""Tests for the strict Python/Rust console wire contract."""

from __future__ import annotations

import hashlib
import json
import math
import pickle
import sys
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from vesper.platform.tui.contracts import (
    CANONICAL_WIRE_FIXTURE,
    CANONICAL_WIRE_FIXTURE_SHA256,
    ClientHelloPayload,
    Freshness,
    HeaderView,
    LeaseRequestPayload,
    MessageType,
    OperatingMode,
    SnapshotRequestPayload,
    UntrustedProtocolDiagnostic,
    WIRE_SCHEMA_RECEIPT,
    WIRE_SCHEMA_RECEIPT_SHA256,
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


def _header(**changes: object) -> HeaderView:
    values: dict[str, object] = {
        "operating_mode": OperatingMode.UNKNOWN,
        "operating_mode_freshness": Freshness.LOADING,
        "operating_mode_reason": None,
        "data_freshness": Freshness.LOADING,
        "data_age_seconds": None,
        "regime_label": "unknown",
        "regime_confidence": None,
        "portfolio_value": None,
        "next_rebalance_at_utc": None,
        "rebalance_blockers": (),
        "active_agent": None,
        "agent_queue_length": 0,
        "qwen_state": "stopped",
        "qwen_context_percent": None,
        "current_time_utc": datetime(2026, 8, 3, tzinfo=timezone.utc),
        "market_session": "closed",
    }
    values.update(changes)
    return HeaderView(**values)


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


def test_untrusted_diagnostic_scrubs_retained_references_and_cannot_serialize() -> None:
    wire = (
        b'{"schema_version":1,"message_id":"server:1","sequence":1,'
        b'"state_version":0,"timestamp_utc":"2026-08-03T00:00:00Z",'
        b'"message_type":"lease-request",'
        b'"payload":{"action":"take-control","secret":"x"}}'
    )
    seen_during_callback: list[bool] = []
    retained_exceptions: list[BaseException | None] = []
    retained: list[UntrustedProtocolDiagnostic] = []

    def receive(diagnostic: UntrustedProtocolDiagnostic) -> None:
        seen_during_callback.append(diagnostic.unknown_fields["secret"] == "x")
        retained_exceptions.append(sys.exception())
        retained.append(diagnostic)

    with pytest.raises(ValidationError):
        decode_envelope_json(wire, receive)

    assert seen_during_callback == [True]
    assert retained_exceptions == [None]
    assert retained[0].unknown_fields == {}
    with pytest.raises(TypeError):
        json.dumps(retained[0])
    with pytest.raises(TypeError):
        pickle.dumps(retained[0])


def test_top_level_unknown_callback_has_no_active_validation_error() -> None:
    wire = (
        b'{"schema_version":1,"message_id":"server:1","sequence":1,'
        b'"state_version":0,"timestamp_utc":"2026-08-03T00:00:00Z",'
        b'"message_type":"server-hello",'
        b'"payload":{"server_version":"0.1.0","requires_setup":true},'
        b'"secret":"x"}'
    )
    retained_exceptions: list[BaseException | None] = []

    with pytest.raises(ValidationError):
        decode_envelope_json(wire, lambda diagnostic: retained_exceptions.append(sys.exception()))

    assert retained_exceptions == [None]


def test_retained_unknown_field_view_is_empty_after_callback() -> None:
    wire = (
        b'{"schema_version":1,"message_id":"server:1","sequence":1,'
        b'"state_version":0,"timestamp_utc":"2026-08-03T00:00:00Z",'
        b'"message_type":"lease-request",'
        b'"payload":{"action":"take-control","secret":"x"}}'
    )
    retained_views: list[object] = []

    with pytest.raises(ValidationError):
        decode_envelope_json(wire, lambda diagnostic: retained_views.append(diagnostic.unknown_fields))

    assert retained_views == [{}]


def test_retained_unknown_scalar_view_is_inaccessible_after_callback() -> None:
    wire = (
        b'{"schema_version":1,"message_id":"server:1","sequence":1,'
        b'"state_version":0,"timestamp_utc":"2026-08-03T00:00:00Z",'
        b'"message_type":"lease-request",'
        b'"payload":{"action":"take-control","secret":"x"}}'
    )
    retained_scalars: list[object] = []

    with pytest.raises(ValidationError):
        decode_envelope_json(
            wire,
            lambda diagnostic: retained_scalars.append(diagnostic.unknown_fields["secret"]),
        )

    with pytest.raises(RuntimeError, match="expired"):
        str(retained_scalars[0])


def test_retained_unknown_iterators_and_views_are_revoked_after_callback() -> None:
    wire = (
        b'{"schema_version":1,"message_id":"server:1","sequence":1,'
        b'"state_version":0,"timestamp_utc":"2026-08-03T00:00:00Z",'
        b'"message_type":"lease-request",'
        b'"payload":{"action":"take-control","secret":"x",'
        b'"nested":{"secret":"y"},"entries":["z"]}}'
    )
    retained: dict[str, object] = {}

    def receive(diagnostic: UntrustedProtocolDiagnostic) -> None:
        root = diagnostic.unknown_fields
        nested = root["nested"]
        entries = root["entries"]
        retained.update(
            root_iterator=iter(root),
            nested_view=nested,
            nested_iterator=iter(nested),
            list_view=entries,
            list_iterator=iter(entries),
            list_slice=entries[:],
            list_item=entries[0],
            keys_iterator=iter(root.keys()),
            values_iterator=iter(root.values()),
            items_iterator=iter(root.items()),
        )

    with pytest.raises(ValidationError):
        decode_envelope_json(wire, receive)

    for name in (
        "root_iterator",
        "nested_iterator",
        "list_iterator",
        "keys_iterator",
        "values_iterator",
        "items_iterator",
    ):
        assert list(retained[name]) == []
        with pytest.raises(TypeError):
            pickle.dumps(retained[name])
    assert retained["nested_view"] == {}
    assert list(retained["list_view"]) == []
    assert list(retained["list_slice"]) == []
    with pytest.raises(RuntimeError, match="expired"):
        str(retained["list_item"])


def test_nested_unknown_fields_are_reported_without_decoding_the_message() -> None:
    wire = json.dumps(
        {
            "schema_version": 1,
            "message_id": "server:1",
            "sequence": 1,
            "state_version": 0,
            "timestamp_utc": "2026-08-03T00:00:00Z",
            "message_type": "snapshot",
            "payload": {
                "snapshot": {
                    "state_version": 0,
                    "generated_at_utc": "2026-08-03T00:00:00Z",
                    "header": {
                        "operating_mode": "unknown",
                        "operating_mode_freshness": "loading",
                        "operating_mode_reason": None,
                        "data_freshness": "loading",
                        "data_age_seconds": None,
                        "regime_label": "unknown",
                        "regime_confidence": None,
                        "portfolio_value": None,
                        "next_rebalance_at_utc": None,
                        "rebalance_blockers": [],
                        "active_agent": None,
                        "agent_queue_length": 0,
                        "qwen_state": "stopped",
                        "qwen_context_percent": None,
                        "current_time_utc": "2026-08-03T00:00:00Z",
                        "market_session": "closed",
                        "secret": "x",
                    },
                    "alerts": [],
                    "capabilities": [],
                }
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")
    seen_during_callback: list[bool] = []

    def receive(diagnostic: UntrustedProtocolDiagnostic) -> None:
        seen_during_callback.append(
            diagnostic.unknown_fields["snapshot"]["header"]["secret"] == "x"
        )

    with pytest.raises(ValidationError):
        decode_envelope_json(wire, receive)

    assert seen_during_callback == [True]


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_floats_are_rejected_in_shell_models_and_wire_json(value: float) -> None:
    with pytest.raises(ValidationError):
        _header(data_age_seconds=value)
    with pytest.raises(ValidationError):
        _envelope(payload={"value": value})
    with pytest.raises(ValidationError):
        _envelope(payload={"value": [{"nested": value}]})


def test_canonical_fixture_and_schema_receipt_have_exact_bytes_and_hashes() -> None:
    expected_fixture = (
        b'{"schema_version":1,"message_id":"server:1","sequence":1,'
        b'"state_version":0,"timestamp_utc":"2026-08-03T00:00:00Z",'
        b'"message_type":"server-hello",'
        b'"payload":{"server_version":"0.1.0","requires_setup":true}}'
    )

    assert CANONICAL_WIRE_FIXTURE == expected_fixture
    assert CANONICAL_WIRE_FIXTURE_SHA256 == "791c289ab55ac2183712e2305d3d6652b274592f86b72c25508b02a48bfa050d"
    assert hashlib.sha256(CANONICAL_WIRE_FIXTURE).hexdigest() == CANONICAL_WIRE_FIXTURE_SHA256
    assert WIRE_SCHEMA_RECEIPT == json.dumps(
        WireEnvelope.model_json_schema(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert WIRE_SCHEMA_RECEIPT_SHA256 == "ab1d90e0538558b0f13f7c18c96539ae602a01c36639791b324a649ae7f1361e"
    assert hashlib.sha256(WIRE_SCHEMA_RECEIPT).hexdigest() == WIRE_SCHEMA_RECEIPT_SHA256
