from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from vesper.platform.tui.command_contracts import (
    COMMAND_SPECS,
    PAYLOAD_MODELS,
    CommandReceipt,
    CommandRequest,
    ConfirmationProof,
    ReceiptStatus,
)
from vesper.platform.tui.contracts import (
    CANONICAL_WIRE_FIXTURES,
    WIRE_CONTRACT_DESCRIPTOR,
    MessageType,
    WireEnvelope,
    decode_payload,
)
from vesper.platform.tui.views import ConsoleSnapshot


CONTROL_HASH = "7c222fb2927d828af22f592134e8932480637c0d1a3a6c9f5d6f0f975f6e3f43"
CATALOG = (
    ("note.add", "NoteAddPayload", "forbidden", "none"),
    ("alert.dismiss", "AlertDismissPayload", "forbidden", "none"),
    ("layout.reset", "LayoutResetPayload", "forbidden", "none"),
    ("approval.approve", "ApprovalPayload", "optional", "confirm"),
    ("approval.hold", "ApprovalPayload", "required", "confirm"),
    ("approval.reject", "ApprovalPayload", "required", "confirm"),
    ("approval.rework", "ApprovalReworkPayload", "required", "confirm"),
    ("agent.send-message", "AgentMessagePayload", "forbidden", "none"),
    ("agent.enqueue", "AgentEnqueuePayload", "required", "confirm"),
    ("agent.pause", "AgentWorkPayload", "required", "confirm"),
    ("agent.stop", "AgentStopPayload", "required", "confirm"),
    ("agent.retry", "AgentWorkPayload", "required", "confirm"),
    ("agent.set-priority", "AgentPriorityPayload", "required", "confirm"),
    ("risk.propose-limit", "RiskLimitPayload", "required", "confirm"),
    ("trading.pause", "EmptyPayload", "required", "confirm"),
    ("trading.emergency-stop", "EmptyPayload", "required", "double-confirm"),
    ("service.pause", "ServicePayload", "required", "confirm"),
    ("service.restart", "ServicePayload", "required", "confirm"),
    ("runtime.start", "RuntimeStartPayload", "required", "confirm"),
    ("runtime.stop-safe", "EmptyPayload", "required", "confirm"),
    ("runtime.stop-force", "EmptyPayload", "required", "double-confirm"),
    ("runtime.prepare-shutdown", "EmptyPayload", "required", "confirm"),
    ("mode.switch", "ModeSwitchPayload", "required", "confirm"),
    ("mode.leave-live", "ModeSwitchPayload", "required", "confirm"),
    ("mode.enable-live", "EnableLivePayload", "required", "typed-live"),
    ("model.request-promotion", "ModelDecisionPayload", "required", "confirm"),
    ("model.request-rollback", "ModelDecisionPayload", "required", "confirm"),
    ("memory.compress-now", "CompressMemoryPayload", "forbidden", "none"),
    ("backup.create", "BackupCreatePayload", "optional", "confirm"),
    ("backup.restore", "BackupRestorePayload", "required", "double-confirm"),
    ("source-control.push", "SourceControlPushPayload", "required", "confirm"),
)
VALID_PAYLOADS = {
    "note.add": {
        "target_type": "stock",
        "target_id": "AAPL",
        "body": "Review concentration.",
        "visibility": "private",
    },
    "alert.dismiss": {"alert_id": "alert:1"},
    "layout.reset": {"screen": "impact"},
    "approval.approve": {"run_id": "run:1", "checkpoint_id": "checkpoint:1"},
    "approval.hold": {"run_id": "run:1", "checkpoint_id": "checkpoint:1"},
    "approval.reject": {"run_id": "run:1", "checkpoint_id": "checkpoint:1"},
    "approval.rework": {
        "run_id": "run:1",
        "checkpoint_id": "checkpoint:1",
        "evidence_ids": ["evidence:1"],
    },
    "agent.send-message": {
        "agent_id": "agent:risk",
        "text": "Review this.",
        "selected_entity_type": "stock",
        "selected_entity_id": "AAPL",
    },
    "agent.enqueue": {
        "agent_id": "agent:risk",
        "title": "Review risk",
        "objective": "Review the evidence.",
        "priority": 75,
    },
    "agent.pause": {"work_id": "work:1"},
    "agent.stop": {"work_id": "work:1", "workflow_run_id": "workflow:1"},
    "agent.retry": {"work_id": "work:1"},
    "agent.set-priority": {"work_id": "work:1", "priority": 90},
    "risk.propose-limit": {
        "limit_id": "limit:1",
        "proposed_value": "0.05",
        "evidence_ids": ["evidence:1"],
    },
    "trading.pause": {},
    "trading.emergency-stop": {},
    "service.pause": {"service_id": "service:qwen"},
    "service.restart": {"service_id": "service:qwen"},
    "runtime.start": {"mode": "paper", "activation_receipt_id": "receipt:1"},
    "runtime.stop-safe": {},
    "runtime.stop-force": {},
    "runtime.prepare-shutdown": {},
    "mode.switch": {"target_mode": "shadow"},
    "mode.leave-live": {"target_mode": "paper"},
    "mode.enable-live": {"desired_portfolio_id": "portfolio:1"},
    "model.request-promotion": {
        "candidate_id": "candidate:1",
        "evidence_ids": ["evidence:1"],
    },
    "model.request-rollback": {
        "candidate_id": "candidate:1",
        "evidence_ids": ["evidence:1"],
    },
    "memory.compress-now": {"agent_id": "agent:risk"},
    "backup.create": {"destination": "C:\\backups\\v20.zip"},
    "backup.restore": {
        "archive": "C:\\backups\\v20.zip",
        "preview_hash": CONTROL_HASH,
        "safety_backup_receipt_id": "receipt:backup",
    },
    "source-control.push": {"expected_revision": "a" * 40},
}


def request_data(command_type: str, payload: object | None = None) -> dict[str, object]:
    reason_rule = next(row[2] for row in CATALOG if row[0] == command_type)
    return {
        "command_id": f"client-1:{command_type}",
        "command_type": command_type,
        "reviewed_control_version": 19,
        "reviewed_control_hash": CONTROL_HASH,
        "reason": "Required rationale" if reason_rule == "required" else None,
        "confirmation": None,
        "payload": VALID_PAYLOADS[command_type] if payload is None else payload,
    }


def test_catalog_has_exact_order_models_and_decisions() -> None:
    assert tuple(PAYLOAD_MODELS) == tuple(row[0] for row in CATALOG)
    assert tuple(
        (
            spec.command_type,
            spec.payload_model,
            spec.reason_rule,
            spec.confirmation_level,
        )
        for spec in COMMAND_SPECS
    ) == CATALOG
    assert tuple(spec.capability_id for spec in COMMAND_SPECS) == tuple(
        row[0] for row in CATALOG
    )


@pytest.mark.parametrize("command_type", tuple(VALID_PAYLOADS))
def test_each_command_binds_only_its_exact_payload_model(command_type: str) -> None:
    request = CommandRequest.model_validate(request_data(command_type))
    assert type(request.payload) is PAYLOAD_MODELS[command_type]
    assert "operator_id" not in type(request).model_fields


@pytest.mark.parametrize("command_type", tuple(VALID_PAYLOADS))
def test_each_command_rejects_a_different_payload_model(command_type: str) -> None:
    expected = PAYLOAD_MODELS[command_type]
    wrong_type = next(name for name, model in PAYLOAD_MODELS.items() if model is not expected)
    wrong_payload = PAYLOAD_MODELS[wrong_type].model_validate(VALID_PAYLOADS[wrong_type])
    with pytest.raises(ValidationError, match="payload-model-mismatch"):
        CommandRequest.model_validate(request_data(command_type, wrong_payload))


def test_required_null_reason_reaches_policy_but_blank_reason_is_invalid() -> None:
    data = request_data("approval.reject")
    data["reason"] = None
    assert CommandRequest.model_validate(data).reason is None
    data["reason"] = "   "
    with pytest.raises(ValidationError):
        CommandRequest.model_validate(data)


def test_forbidden_reason_must_be_null() -> None:
    data = request_data("note.add")
    data["reason"] = "not allowed"
    with pytest.raises(ValidationError, match="reason-forbidden"):
        CommandRequest.model_validate(data)


@pytest.mark.parametrize(
    "location,key",
    [
        ("request", "operator_id"),
        ("payload", "password"),
        ("payload", "token"),
        ("payload", "api_key"),
        ("payload", "credential"),
        ("payload", "secret"),
        ("payload", "account_id"),
    ],
)
def test_operator_and_credential_like_fields_are_rejected(location: str, key: str) -> None:
    data = request_data("note.add")
    if location == "request":
        data[key] = "forbidden"
    else:
        data["payload"] = {**VALID_PAYLOADS["note.add"], key: "forbidden"}
    with pytest.raises(ValidationError):
        CommandRequest.model_validate(data)


def test_payload_over_64_kib_is_rejected_before_model_binding() -> None:
    payload = {**VALID_PAYLOADS["note.add"], "unknown": "x" * 65_536}
    with pytest.raises(ValidationError, match="payload-too-large"):
        CommandRequest.model_validate(request_data("note.add", payload))


@pytest.mark.parametrize(
    "command_type,field,valid,invalid",
    [
        ("note.add", "body", "x" * 8_000, "x" * 8_001),
        ("agent.send-message", "text", "x" * 8_000, "x" * 8_001),
        ("agent.enqueue", "title", "x" * 512, "x" * 513),
        ("agent.enqueue", "objective", "x" * 8_000, "x" * 8_001),
        ("backup.create", "destination", "x" * 32_767, "x" * 32_768),
        ("backup.restore", "archive", "x" * 32_767, "x" * 32_768),
    ],
    ids=["note-body", "agent-message", "agent-title", "agent-objective", "backup", "restore"],
)
def test_text_fields_enforce_exact_maximums(
    command_type: str,
    field: str,
    valid: str,
    invalid: str,
) -> None:
    valid_payload = {**VALID_PAYLOADS[command_type], field: valid}
    assert CommandRequest.model_validate(request_data(command_type, valid_payload))
    invalid_payload = {**VALID_PAYLOADS[command_type], field: invalid}
    with pytest.raises(ValidationError):
        CommandRequest.model_validate(request_data(command_type, invalid_payload))


def test_evidence_ids_are_bounded_to_32() -> None:
    payload = {**VALID_PAYLOADS["approval.rework"], "evidence_ids": [f"e:{i}" for i in range(32)]}
    assert CommandRequest.model_validate(request_data("approval.rework", payload))
    payload["evidence_ids"] = [f"e:{i}" for i in range(33)]
    with pytest.raises(ValidationError):
        CommandRequest.model_validate(request_data("approval.rework", payload))


def test_confirmation_text_is_raw_and_bounded_for_policy() -> None:
    data = request_data("mode.enable-live")
    data["confirmation"] = {
        "first_confirmed": True,
        "second_confirmed": False,
        "typed_text": " ENABLE LIVE ",
        "bound_preview_hash": None,
    }
    request = CommandRequest.model_validate(data)
    assert request.confirmation == ConfirmationProof(
        first_confirmed=True,
        second_confirmed=False,
        typed_text=" ENABLE LIVE ",
        bound_preview_hash=None,
    )
    data["confirmation"] = {"typed_text": "x" * 513}
    with pytest.raises(ValidationError):
        CommandRequest.model_validate(data)


@pytest.mark.parametrize("value", [-1, 2**64])
def test_reviewed_control_version_is_wire_unsigned(value: int) -> None:
    data = request_data("note.add")
    data["reviewed_control_version"] = value
    with pytest.raises(ValidationError):
        CommandRequest.model_validate(data)


def test_receipt_status_and_nullable_terminal_fields_are_strict() -> None:
    receipt = CommandReceipt(
        command_id="client-1:note.add",
        status=ReceiptStatus.COMPLETED,
        code="completed",
        safe_message="Note stored.",
        accepted_at_utc="2026-08-03T00:00:00Z",
        finished_at_utc="2026-08-03T00:00:01Z",
        result=None,
    )
    assert receipt.status is ReceiptStatus.COMPLETED
    with pytest.raises(ValidationError):
        CommandReceipt.model_validate({**receipt.model_dump(), "safe_message": "x" * 513})


@pytest.mark.parametrize("value", [-(2**63) - 1, 2**64])
def test_receipt_json_integers_stay_in_rust_serde_range(value: int) -> None:
    with pytest.raises(ValidationError):
        CommandReceipt(
            command_id="client-1:note.add",
            status=ReceiptStatus.COMPLETED,
            code="completed",
            safe_message="Done.",
            accepted_at_utc=None,
            finished_at_utc=None,
            result={"count": value},
        )


def test_controls_snapshot_fixture_publishes_all_command_specs() -> None:
    path = Path("TUI testing/contracts/v1/controls_snapshot.json")
    snapshot = ConsoleSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
    assert len(snapshot.command_specs) == 31
    assert tuple(row.command_type for row in snapshot.command_specs) == tuple(PAYLOAD_MODELS)


def test_command_request_json_is_stable_and_contains_no_operator_identity() -> None:
    request = CommandRequest.model_validate(request_data("note.add"))
    wire = json.loads(request.model_dump_json())
    assert wire["payload"] == VALID_PAYLOADS["note.add"]
    assert "operator_id" not in wire


def test_wire_catalog_adds_command_request_and_receipt_in_order() -> None:
    assert tuple(message.value for message in MessageType) == (
        "client-hello",
        "server-hello",
        "auth-setup",
        "auth-unlock",
        "auth-result",
        "lease-request",
        "lease-result",
        "lock-request",
        "lock-result",
        "snapshot-request",
        "snapshot",
        "search-request",
        "search-results",
        "command",
        "command-receipt",
        "event",
        "protocol-error",
        "ping",
        "pong",
    )


@pytest.mark.parametrize("message_type", ["command", "command-receipt"])
def test_new_wire_messages_have_canonical_round_trip_fixtures(message_type: str) -> None:
    fixture = next(
        frame
        for frame in CANONICAL_WIRE_FIXTURES
        if json.loads(frame)["message_type"] == message_type
    )
    envelope = WireEnvelope.model_validate_json(fixture)
    payload = decode_payload(envelope)
    assert payload.model_dump_json().encode("utf-8") == json.dumps(
        json.loads(fixture)["payload"], separators=(",", ":")
    ).encode("utf-8")
    assert envelope.model_dump_json().encode("utf-8") == fixture


def test_command_wire_rejects_client_operator_identity() -> None:
    payload = {"request": {**request_data("note.add"), "operator_id": "operator:spoofed"}}
    envelope = WireEnvelope(
        schema_version=1,
        message_id="client:1",
        sequence=1,
        state_version=0,
        timestamp_utc="2026-08-03T00:00:00Z",
        message_type=MessageType.COMMAND,
        payload=payload,
    )
    with pytest.raises(ValidationError):
        decode_payload(envelope)


def test_wire_descriptor_covers_command_nullability_defaults_and_integer() -> None:
    descriptor = json.loads(WIRE_CONTRACT_DESCRIPTOR)
    assert descriptor["messages"]["command"] == ["request"]
    assert descriptor["messages"]["command-receipt"] == ["receipt"]
    assert "governed-command-contracts" in descriptor["field_catalog_scope"]
    assert "command.request.reason" in descriptor["nullable_required"]
    assert "command-receipt.receipt.result" in descriptor["nullable_required"]
    assert "command.request.confirmation" in descriptor["optional_default"]
    assert "command.request.reviewed_control_version" in descriptor["integer_fields"]
