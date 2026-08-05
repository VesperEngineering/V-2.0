"""Tests for the strict Python/Rust console wire contract."""

from __future__ import annotations

import hashlib
import json
import math
import pickle
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from vesper.platform.tui.contracts import (
    CANONICAL_WIRE_FIXTURE,
    CANONICAL_WIRE_FIXTURE_SHA256,
    CANONICAL_WIRE_FIXTURES,
    ChatEventPayload,
    ChatHistoryRequestPayload,
    ChatHistoryResultPayload,
    ClientHelloPayload,
    Freshness,
    HeaderView,
    LeaseRequestPayload,
    MemoryContentRequestPayload,
    MemoryContentResultPayload,
    MessageType,
    OperatingMode,
    SearchRequestPayload,
    SearchResultsPayload,
    SnapshotRequestPayload,
    UntrustedProtocolDiagnostic,
    WIRE_SCHEMA_RECEIPT,
    WIRE_SCHEMA_RECEIPT_SHA256,
    WIRE_CONTRACT_DESCRIPTOR,
    WireEnvelope,
    decode_envelope_json,
    decode_payload,
)
from vesper.platform.tui.protocol import MAX_FRAME_BYTES, encode_frame
from vesper.platform.tui.search import (
    SearchFilters,
    SearchKind,
    SearchRecordType,
    SearchResult,
    SearchScreen,
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
        "rebalance_blockers": None,
        "active_agent": None,
        "agent_queue_length": None,
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


def test_chat_history_request_is_strict_and_agent_scoped() -> None:
    payload = ChatHistoryRequestPayload.model_validate_json(
        '{"agent_id":"v20-risk-review","limit":20,"cursor":null}'
    )

    assert payload.agent_id == "v20-risk-review"
    assert payload.limit == 20
    assert payload.cursor is None
    for agent_id in ("AAPL", "", "v20-risk-review "):
        with pytest.raises(ValidationError):
            ChatHistoryRequestPayload.model_validate(
                {"agent_id": agent_id, "limit": 1, "cursor": None}
            )
    for limit in (0, 21, True):
        with pytest.raises(ValidationError):
            ChatHistoryRequestPayload.model_validate(
                {"agent_id": "v20-risk-review", "limit": limit, "cursor": None}
            )
    with pytest.raises(ValidationError):
        ChatHistoryRequestPayload.model_validate(
            {
                "agent_id": "v20-risk-review",
                "limit": 1,
                "cursor": None,
                "extra": "forbidden",
            }
        )


def test_chat_event_enforces_chunk_and_terminal_shapes() -> None:
    chunk = ChatEventPayload.model_validate(
        {
            "event_id": "chat:event:1",
            "agent_id": "v20-risk-review",
            "message_id": "message:1",
            "role": "agent",
            "operation": "chunk",
            "chunk_sequence": 1,
            "text": "raw output",
            "token_count": None,
            "message_created_at_utc": datetime(2026, 8, 4, tzinfo=timezone.utc),
            "occurred_at_utc": None,
            "validation_receipt_id": None,
            "raw_text_sha256": None,
        }
    )
    complete = ChatEventPayload.model_validate(
        {
            "event_id": "chat:event:2",
            "agent_id": "v20-risk-review",
            "message_id": "message:1",
            "role": "agent",
            "operation": "complete",
            "chunk_sequence": None,
            "text": None,
            "token_count": None,
            "message_created_at_utc": datetime(2026, 8, 4, tzinfo=timezone.utc),
            "occurred_at_utc": datetime(2026, 8, 4, 0, 0, 1, tzinfo=timezone.utc),
            "validation_receipt_id": "validation:1",
            "raw_text_sha256": "a" * 64,
        }
    )
    interrupted = complete.model_copy(
        update={
            "event_id": "chat:event:3",
            "operation": "interrupted",
            "validation_receipt_id": None,
            "raw_text_sha256": None,
        }
    )

    assert chunk.operation == "chunk"
    assert complete.operation == "complete"
    assert ChatEventPayload.model_validate(interrupted.model_dump()).operation == "interrupted"

    invalid_updates = (
        {"chunk_sequence": None},
        {"text": None},
        {"text": ""},
        {"occurred_at_utc": datetime(2026, 8, 4, tzinfo=timezone.utc)},
        {"validation_receipt_id": "validation:unexpected"},
        {"raw_text_sha256": "b" * 64},
    )
    for update in invalid_updates:
        with pytest.raises(ValidationError):
            ChatEventPayload.model_validate({**chunk.model_dump(), **update})

    for update in (
        {"occurred_at_utc": None},
        {"validation_receipt_id": None},
        {"raw_text_sha256": None},
        {"chunk_sequence": 1},
        {"text": "not-terminal"},
        {"token_count": 1},
    ):
        with pytest.raises(ValidationError):
            ChatEventPayload.model_validate({**complete.model_dump(), **update})

    with pytest.raises(ValidationError):
        ChatEventPayload.model_validate(
            {**interrupted.model_dump(), "validation_receipt_id": "validation:unexpected"}
        )


def test_chat_event_text_limit_is_measured_in_utf8_bytes() -> None:
    values = {
        "event_id": "chat:event:utf8",
        "agent_id": "v20-product",
        "message_id": "message:utf8",
        "role": "human",
        "operation": "chunk",
        "chunk_sequence": 1,
        "token_count": 1,
        "message_created_at_utc": datetime(2026, 8, 4, tzinfo=timezone.utc),
        "occurred_at_utc": None,
        "validation_receipt_id": None,
        "raw_text_sha256": None,
    }

    assert (
        len(ChatEventPayload.model_validate({**values, "text": "🚀" * 16_384}).text.encode())
        == 65_536
    )
    with pytest.raises(ValidationError):
        ChatEventPayload.model_validate({**values, "text": "🚀" * 16_385})
    with pytest.raises(ValidationError):
        ChatEventPayload.model_validate({**values, "text": "\ud800"})


def test_chat_history_result_has_only_agent_and_cursor() -> None:
    result = ChatHistoryResultPayload.model_validate(
        {"agent_id": "v20-development", "next_cursor": "message:older"}
    )

    assert result.next_cursor == "message:older"
    with pytest.raises(ValidationError):
        ChatHistoryResultPayload.model_validate(
            {"agent_id": "v20-development", "next_cursor": None, "events": []}
        )


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


def test_search_wire_payloads_are_strict_bounded_and_echo_the_request() -> None:
    request = decode_payload(
        _envelope(
            message_type=MessageType.SEARCH_REQUEST,
            payload={
                "request_id": 7,
                "query": "AAPL",
                "filters": {
                    "kinds": ["stock"],
                    "screens": ["portfolio"],
                    "source": "fixture",
                },
                "limit": 100,
            },
        )
    )
    assert request == SearchRequestPayload(
        request_id=7,
        query="AAPL",
        filters=SearchFilters(
            kinds=(SearchKind.STOCK,),
            screens=(SearchScreen.PORTFOLIO,),
            source="fixture",
        ),
        limit=100,
    )

    result = SearchResult(
        kind=SearchKind.NOTE,
        record_type=SearchRecordType.NOTE,
        record_id="note:1",
        label="AAPL note",
        summary="Review concentration risk.",
        occurred_at_utc=None,
        source="operator",
        screen=SearchScreen.PORTFOLIO,
    )
    response = decode_payload(
        _envelope(
            message_type=MessageType.SEARCH_RESULTS,
            payload={
                "request_id": 7,
                "indexed_state_version": 12,
                "results": [result.model_dump(mode="json")],
                "error": None,
            },
        )
    )
    assert response == SearchResultsPayload(
        request_id=7,
        indexed_state_version=12,
        results=(result,),
        error=None,
    )

    valid_request = {
        "request_id": 7,
        "query": "AAPL",
        "filters": {"kinds": [], "screens": [], "source": None},
        "limit": 100,
    }
    for changes in (
        {"request_id": True},
        {"request_id": -1},
        {"request_id": 0},
        {"query": ""},
        {"query": " "},
        {"query": "x" * 257},
        {"limit": True},
        {"limit": 0},
        {"limit": 101},
        {
            "filters": {
                "kinds": ["stock"] * 11,
                "screens": [],
                "source": None,
            }
        },
        {
            "filters": {
                "kinds": [],
                "screens": ["portfolio"] * 10,
                "source": None,
            }
        },
        {"unknown": "field"},
    ):
        with pytest.raises(ValidationError):
            decode_payload(
                _envelope(
                    message_type=MessageType.SEARCH_REQUEST,
                    payload={**valid_request, **changes},
                )
            )

    with pytest.raises(ValidationError):
        SearchResultsPayload(
            request_id=7,
            indexed_state_version=12,
            results=tuple(result for _ in range(101)),
            error=None,
        )
    with pytest.raises(ValidationError):
        SearchResultsPayload(
            request_id=7,
            indexed_state_version=12,
            results=(),
            error="x" * 513,
        )
    result_payload = result.model_dump(mode="json")
    missing_record_type = dict(result_payload)
    missing_record_type.pop("record_type")
    unknown_record_type = {**result_payload, "record_type": "unknown-row"}
    for invalid_result in (missing_record_type, unknown_record_type):
        with pytest.raises(ValidationError):
            decode_payload(
                _envelope(
                    message_type=MessageType.SEARCH_RESULTS,
                    payload={
                        "request_id": 7,
                        "indexed_state_version": 12,
                        "results": [invalid_result],
                        "error": None,
                    },
                )
            )


def test_memory_content_wire_is_exact_bounded_and_has_success_error_invariants() -> None:
    reviewed_at = "2026-08-04T14:30:00Z"
    request = decode_payload(
        _envelope(
            message_type=MessageType.MEMORY_CONTENT_REQUEST,
            payload={
                "request_id": 9,
                "memory_id": "memory:deep-archive",
                "reviewed_updated_at_utc": reviewed_at,
            },
        )
    )
    assert request == MemoryContentRequestPayload(
        request_id=9,
        memory_id="memory:deep-archive",
        reviewed_updated_at_utc=reviewed_at,
    )

    content = "x" * 100_000
    success = MemoryContentResultPayload(
        request_id=9,
        memory_id="memory:deep-archive",
        reviewed_updated_at_utc=reviewed_at,
        status="success",
        content=content,
        error=None,
    )
    decoded = decode_payload(
        _envelope(
            message_type=MessageType.MEMORY_CONTENT_RESULT,
            payload=success.model_dump(mode="json"),
        )
    )
    assert decoded == success
    assert (
        len(
            encode_frame(
                _envelope(
                    message_type=MessageType.MEMORY_CONTENT_RESULT,
                    payload=success.model_dump(mode="json"),
                )
            )
        )
        - 4
        <= MAX_FRAME_BYTES
    )

    error = MemoryContentResultPayload(
        request_id=9,
        memory_id="memory:deep-archive",
        reviewed_updated_at_utc=reviewed_at,
        status="error",
        content=None,
        error="Memory changed. Search again.",
    )
    assert error.error == "Memory changed. Search again."

    request_payload = request.model_dump(mode="json")
    result_payload = success.model_dump(mode="json")
    for invalid in (
        {**request_payload, "unknown": "forbidden"},
        {**request_payload, "request_id": 0},
        {**request_payload, "memory_id": ""},
        {**request_payload, "reviewed_updated_at_utc": "2026-08-04T10:30:00-04:00"},
    ):
        with pytest.raises(ValidationError):
            MemoryContentRequestPayload.model_validate(invalid)
    for invalid in (
        {**result_payload, "unknown": "forbidden"},
        {**result_payload, "content": "x" * 100_001},
        {**result_payload, "status": "success", "content": None, "error": None},
        {**result_payload, "status": "success", "error": "Not allowed."},
        {**result_payload, "status": "error", "content": content, "error": "Failed."},
        {**result_payload, "status": "error", "content": None, "error": None},
    ):
        with pytest.raises(ValidationError):
            MemoryContentResultPayload.model_validate(invalid)


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
        decode_envelope_json(
            wire, lambda diagnostic: retained_views.append(diagnostic.unknown_fields)
        )

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
                    "shell": {
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
                    },
                    "control_version": 0,
                    "control_hash": "a" * 64,
                    "command_specs": [],
                }
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")
    seen_during_callback: list[bool] = []

    def receive(diagnostic: UntrustedProtocolDiagnostic) -> None:
        seen_during_callback.append(
            diagnostic.unknown_fields["snapshot"]["shell"]["header"]["secret"] == "x"
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
    assert (
        CANONICAL_WIRE_FIXTURE_SHA256
        == "791c289ab55ac2183712e2305d3d6652b274592f86b72c25508b02a48bfa050d"
    )
    assert hashlib.sha256(CANONICAL_WIRE_FIXTURE).hexdigest() == CANONICAL_WIRE_FIXTURE_SHA256
    assert WIRE_SCHEMA_RECEIPT == json.dumps(
        WireEnvelope.model_json_schema(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert (
        WIRE_SCHEMA_RECEIPT_SHA256
        == "57c48547644cab9499199b31eaf902aa48344d854b565307652afb746744d3ba"
    )
    assert hashlib.sha256(WIRE_SCHEMA_RECEIPT).hexdigest() == WIRE_SCHEMA_RECEIPT_SHA256


def test_all_message_fixtures_and_language_neutral_descriptor_are_canonical() -> None:
    assert len(CANONICAL_WIRE_FIXTURES) == len(MessageType) == 24
    assert {decode_envelope_json(frame).message_type for frame in CANONICAL_WIRE_FIXTURES} == set(
        MessageType
    )
    for frame in CANONICAL_WIRE_FIXTURES:
        envelope = decode_envelope_json(frame)
        decode_payload(envelope)
        assert envelope.model_dump_json().encode("utf-8") == frame
    descriptor = json.loads(WIRE_CONTRACT_DESCRIPTOR)
    assert descriptor["schema_version"] == 1
    assert set(descriptor["messages"]) == {message.value for message in MessageType}
    assert "snapshot.shell.header.agent_queue_length" in descriptor["nullable_required"]
    assert "snapshot.system.live_account" in descriptor["nullable_required"]
    assert "snapshot.system.live_transition_plan" in descriptor["nullable_required"]
    assert "live-readiness" in descriptor["field_catalog_scope"]
    assert "agent-chat" in descriptor["field_catalog_scope"]
    assert "chat-event.raw_text_sha256" in descriptor["nullable_required"]
    assert descriptor["optional_default"] == [
        "capability.reason",
        "command.request.confirmation",
        "command.request.confirmation.first_confirmed",
        "command.request.confirmation.second_confirmed",
        "command.request.confirmation.typed_text",
        "command.request.confirmation.bound_preview_hash",
    ]


@pytest.mark.parametrize("value", [-1, 2**64])
def test_wire_unsigned_integers_reject_out_of_range(value: int) -> None:
    with pytest.raises(ValidationError):
        _envelope(sequence=value)
    with pytest.raises(ValidationError):
        _envelope(state_version=value)
    with pytest.raises(ValidationError):
        _header(agent_queue_length=value)
    snapshot_wire = next(
        json.loads(frame)
        for frame in CANONICAL_WIRE_FIXTURES
        if json.loads(frame)["message_type"] == "snapshot"
    )
    snapshot_wire["payload"]["snapshot"]["shell"]["state_version"] = value
    envelope = WireEnvelope.model_validate_json(json.dumps(snapshot_wire))
    with pytest.raises(ValidationError):
        decode_payload(envelope)


def test_wire_unsigned_integers_accept_u64_max() -> None:
    maximum = 2**64 - 1
    assert _envelope(sequence=maximum, state_version=maximum).sequence == maximum
    assert _header(agent_queue_length=maximum).agent_queue_length == maximum
    snapshot_wire = next(
        json.loads(frame)
        for frame in CANONICAL_WIRE_FIXTURES
        if json.loads(frame)["message_type"] == "snapshot"
    )
    snapshot_wire["payload"]["snapshot"]["shell"]["state_version"] = maximum
    assert (
        decode_payload(
            WireEnvelope.model_validate_json(json.dumps(snapshot_wire))
        ).snapshot.shell.state_version
        == maximum
    )


def test_bounded_snapshot_envelope_stays_below_the_existing_frame_limit() -> None:
    frame = next(
        frame
        for frame in CANONICAL_WIRE_FIXTURES
        if json.loads(frame)["message_type"] == "snapshot"
    )
    envelope = WireEnvelope.model_validate_json(frame)

    assert len(encode_frame(envelope)) - 4 == len(frame)
    assert len(frame) <= MAX_FRAME_BYTES


def test_event_nested_unknown_field_is_reported_and_rejected() -> None:
    value = next(
        json.loads(frame)
        for frame in CANONICAL_WIRE_FIXTURES
        if json.loads(frame)["message_type"] == "event"
    )
    value["payload"]["entity"]["secret"] = "x"
    wire = json.dumps(value, separators=(",", ":")).encode()
    seen: list[bool] = []

    with pytest.raises(ValidationError):
        decode_envelope_json(
            wire,
            lambda diagnostic: seen.append(diagnostic.unknown_fields["entity"]["secret"] == "x"),
        )

    assert seen == [True]


def test_event_presentation_unknown_field_is_reported_and_rejected() -> None:
    value = next(
        json.loads(frame)
        for frame in CANONICAL_WIRE_FIXTURES
        if json.loads(frame)["message_type"] == "event"
    )
    value["payload"]["presentation"]["secret"] = "x"
    wire = json.dumps(value, separators=(",", ":")).encode()
    seen: list[bool] = []

    with pytest.raises(ValidationError):
        decode_envelope_json(
            wire,
            lambda diagnostic: seen.append(
                diagnostic.unknown_fields["presentation"]["secret"] == "x"
            ),
        )

    assert seen == [True]


def test_event_untrusted_diagnostic_has_one_shared_unknown_leaf_budget() -> None:
    value = next(
        json.loads(frame)
        for frame in CANONICAL_WIRE_FIXTURES
        if json.loads(frame)["message_type"] == "event"
    )
    for index in range(16):
        value["payload"][f"top_extra_{index}"] = index
        value["payload"]["entity"][f"entity_extra_{index}"] = index
    wire = json.dumps(value, separators=(",", ":")).encode()
    leaf_counts: list[int] = []

    def count_leaves(item: object) -> int:
        if isinstance(item, Mapping):
            return sum(count_leaves(child) for child in item.values()) or 1
        if isinstance(item, Sequence) and not isinstance(item, str):
            return sum(count_leaves(child) for child in item) or 1
        return 1

    with pytest.raises(ValidationError):
        decode_envelope_json(
            wire,
            lambda diagnostic: leaf_counts.append(count_leaves(diagnostic.unknown_fields)),
        )

    assert leaf_counts == [16]
