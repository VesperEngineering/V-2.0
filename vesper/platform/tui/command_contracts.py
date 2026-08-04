"""Strict governed-command and durable receipt wire contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Literal, TypeAlias, cast

from pydantic import Field, SerializeAsAny, StringConstraints, field_validator, model_validator
from typing_extensions import TypeAliasType

from .views import (
    CommandSpecView,
    DecimalString,
    FiniteFloat,
    NonEmptyStr,
    SafeId,
    Sha256Hex,
    StrictModel,
    UtcDateTime,
    WireUInt,
)


MAX_COMMAND_PAYLOAD_BYTES = 64 * 1024
MAX_EVIDENCE_IDS = 32

GitRevision = Annotated[
    str,
    StringConstraints(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$"),
]
ScreenName = Literal[
    "impact",
    "portfolio",
    "orders",
    "agents",
    "models-regime",
    "timeline",
    "risk-approvals",
    "data-evidence",
    "memory",
    "system",
]
CommandType = Literal[
    "note.add",
    "alert.dismiss",
    "layout.reset",
    "approval.approve",
    "approval.hold",
    "approval.reject",
    "approval.rework",
    "agent.send-message",
    "agent.enqueue",
    "agent.pause",
    "agent.stop",
    "agent.retry",
    "agent.set-priority",
    "risk.propose-limit",
    "trading.pause",
    "trading.emergency-stop",
    "service.pause",
    "service.restart",
    "runtime.start",
    "runtime.stop-safe",
    "runtime.stop-force",
    "runtime.prepare-shutdown",
    "mode.switch",
    "mode.leave-live",
    "mode.enable-live",
    "model.request-promotion",
    "model.request-rollback",
    "memory.compress-now",
    "backup.create",
    "backup.restore",
    "source-control.push",
]
ReasonRule = Literal["forbidden", "optional", "required"]
ConfirmationLevelValue = Literal["none", "confirm", "double-confirm", "typed-live"]
ReasonText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
]
LongText = Annotated[str, StringConstraints(min_length=1, max_length=8000)]
WindowsPathText = Annotated[str, StringConstraints(min_length=1, max_length=32767)]
RawConfirmationText = Annotated[str, StringConstraints(max_length=512)]
EvidenceIds = Annotated[tuple[SafeId, ...], Field(max_length=MAX_EVIDENCE_IDS)]

CommandJsonInt = Annotated[int, Field(ge=-(2**63), le=2**64 - 1)]
CommandJsonFloat = Annotated[FiniteFloat, Field(strict=True)]
CommandJsonScalar: TypeAlias = None | bool | CommandJsonInt | CommandJsonFloat | str
CommandJsonValue = TypeAliasType(
    "CommandJsonValue",
    CommandJsonScalar | list["CommandJsonValue"] | dict[str, "CommandJsonValue"],
)


class ConfirmationLevel(StrEnum):
    NONE = "none"
    CONFIRM = "confirm"
    DOUBLE_CONFIRM = "double-confirm"
    TYPED_LIVE = "typed-live"


class ReceiptStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EmptyPayload(StrictModel):
    pass


class NoteAddPayload(StrictModel):
    target_type: Literal["stock", "order", "approval", "agent-event"]
    target_id: SafeId
    body: LongText
    visibility: Literal["private", "shared"]


class AlertDismissPayload(StrictModel):
    alert_id: SafeId


class LayoutResetPayload(StrictModel):
    screen: ScreenName | None = None


class ApprovalPayload(StrictModel):
    run_id: SafeId
    checkpoint_id: SafeId


class ApprovalReworkPayload(ApprovalPayload):
    evidence_ids: EvidenceIds


class AgentMessagePayload(StrictModel):
    agent_id: SafeId
    text: LongText
    selected_entity_type: NonEmptyStr | None = None
    selected_entity_id: SafeId | None = None


class AgentEnqueuePayload(StrictModel):
    agent_id: SafeId
    title: NonEmptyStr
    objective: LongText
    priority: Annotated[int, Field(ge=0, le=100)]


class AgentWorkPayload(StrictModel):
    work_id: SafeId


class AgentStopPayload(AgentWorkPayload):
    workflow_run_id: SafeId | None = None


class AgentPriorityPayload(AgentWorkPayload):
    priority: Annotated[int, Field(ge=0, le=100)]


class RiskLimitPayload(StrictModel):
    limit_id: SafeId
    proposed_value: DecimalString
    evidence_ids: EvidenceIds


class ServicePayload(StrictModel):
    service_id: SafeId


class RuntimeStartPayload(StrictModel):
    mode: Literal["shadow", "paper"]
    activation_receipt_id: SafeId


class ModeSwitchPayload(StrictModel):
    target_mode: Literal["shadow", "paper"]


class EnableLivePayload(StrictModel):
    desired_portfolio_id: SafeId


class ModelDecisionPayload(StrictModel):
    candidate_id: SafeId
    evidence_ids: EvidenceIds


class CompressMemoryPayload(StrictModel):
    agent_id: SafeId


class BackupCreatePayload(StrictModel):
    destination: WindowsPathText


class BackupRestorePayload(StrictModel):
    archive: WindowsPathText
    preview_hash: Sha256Hex
    safety_backup_receipt_id: SafeId


class SourceControlPushPayload(StrictModel):
    expected_revision: GitRevision


class ConfirmationProof(StrictModel):
    first_confirmed: bool = False
    second_confirmed: bool = False
    typed_text: RawConfirmationText | None = None
    bound_preview_hash: Sha256Hex | None = None


PAYLOAD_MODELS: Mapping[CommandType, type[StrictModel]] = MappingProxyType(
    {
        "note.add": NoteAddPayload,
        "alert.dismiss": AlertDismissPayload,
        "layout.reset": LayoutResetPayload,
        "approval.approve": ApprovalPayload,
        "approval.hold": ApprovalPayload,
        "approval.reject": ApprovalPayload,
        "approval.rework": ApprovalReworkPayload,
        "agent.send-message": AgentMessagePayload,
        "agent.enqueue": AgentEnqueuePayload,
        "agent.pause": AgentWorkPayload,
        "agent.stop": AgentStopPayload,
        "agent.retry": AgentWorkPayload,
        "agent.set-priority": AgentPriorityPayload,
        "risk.propose-limit": RiskLimitPayload,
        "trading.pause": EmptyPayload,
        "trading.emergency-stop": EmptyPayload,
        "service.pause": ServicePayload,
        "service.restart": ServicePayload,
        "runtime.start": RuntimeStartPayload,
        "runtime.stop-safe": EmptyPayload,
        "runtime.stop-force": EmptyPayload,
        "runtime.prepare-shutdown": EmptyPayload,
        "mode.switch": ModeSwitchPayload,
        "mode.leave-live": ModeSwitchPayload,
        "mode.enable-live": EnableLivePayload,
        "model.request-promotion": ModelDecisionPayload,
        "model.request-rollback": ModelDecisionPayload,
        "memory.compress-now": CompressMemoryPayload,
        "backup.create": BackupCreatePayload,
        "backup.restore": BackupRestorePayload,
        "source-control.push": SourceControlPushPayload,
    }
)

COMMAND_DECISIONS: Mapping[CommandType, tuple[ReasonRule, ConfirmationLevelValue]] = (
    MappingProxyType(
        {
            "note.add": ("forbidden", "none"),
            "alert.dismiss": ("forbidden", "none"),
            "layout.reset": ("forbidden", "none"),
            "approval.approve": ("optional", "confirm"),
            "approval.hold": ("required", "confirm"),
            "approval.reject": ("required", "confirm"),
            "approval.rework": ("required", "confirm"),
            "agent.send-message": ("forbidden", "none"),
            "agent.enqueue": ("required", "confirm"),
            "agent.pause": ("required", "confirm"),
            "agent.stop": ("required", "confirm"),
            "agent.retry": ("required", "confirm"),
            "agent.set-priority": ("required", "confirm"),
            "risk.propose-limit": ("required", "confirm"),
            "trading.pause": ("required", "confirm"),
            "trading.emergency-stop": ("required", "double-confirm"),
            "service.pause": ("required", "confirm"),
            "service.restart": ("required", "confirm"),
            "runtime.start": ("required", "confirm"),
            "runtime.stop-safe": ("required", "confirm"),
            "runtime.stop-force": ("required", "double-confirm"),
            "runtime.prepare-shutdown": ("required", "confirm"),
            "mode.switch": ("required", "confirm"),
            "mode.leave-live": ("required", "confirm"),
            "mode.enable-live": ("required", "typed-live"),
            "model.request-promotion": ("required", "confirm"),
            "model.request-rollback": ("required", "confirm"),
            "memory.compress-now": ("forbidden", "none"),
            "backup.create": ("optional", "confirm"),
            "backup.restore": ("required", "double-confirm"),
            "source-control.push": ("required", "confirm"),
        }
    )
)


class CommandRequest(StrictModel):
    command_id: SafeId
    command_type: CommandType
    reviewed_control_version: WireUInt
    reviewed_control_hash: Sha256Hex
    reason: ReasonText | None
    confirmation: ConfirmationProof | None = None
    payload: SerializeAsAny[StrictModel]

    @model_validator(mode="before")
    @classmethod
    def bind_payload_model(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        command_type = value.get("command_type")
        if not isinstance(command_type, str) or command_type not in PAYLOAD_MODELS:
            raise ValueError("unknown-command")
        payload_type = PAYLOAD_MODELS[cast(CommandType, command_type)]
        raw_payload = value.get("payload")
        if isinstance(raw_payload, StrictModel):
            if type(raw_payload) is not payload_type:
                raise ValueError("payload-model-mismatch")
            payload_json = raw_payload.model_dump(mode="json")
        else:
            if not isinstance(raw_payload, dict):
                raise ValueError("payload-object-required")
            payload_json = raw_payload
        encoded = json.dumps(payload_json, ensure_ascii=False, separators=(",", ":")).encode()
        if len(encoded) > MAX_COMMAND_PAYLOAD_BYTES:
            raise ValueError("payload-too-large")
        if isinstance(raw_payload, StrictModel):
            return value
        return {
            **value,
            "payload": payload_type.model_validate_json(
                json.dumps(raw_payload, ensure_ascii=False, separators=(",", ":"))
            ),
        }

    @model_validator(mode="after")
    def require_exact_payload_model_and_reason_shape(self) -> CommandRequest:
        if type(self.payload) is not PAYLOAD_MODELS[self.command_type]:
            raise ValueError("payload-model-mismatch")
        if COMMAND_DECISIONS[self.command_type][0] == "forbidden" and self.reason is not None:
            raise ValueError("reason-forbidden")
        return self


COMMAND_SPECS: tuple[CommandSpecView, ...] = tuple(
    CommandSpecView(
        command_type=command_type,
        payload_model=PAYLOAD_MODELS[command_type].__name__,
        capability_id=command_type,
        reason_rule=COMMAND_DECISIONS[command_type][0],
        confirmation_level=COMMAND_DECISIONS[command_type][1],
    )
    for command_type in PAYLOAD_MODELS
)


class CommandReceipt(StrictModel):
    command_id: SafeId
    status: ReceiptStatus
    code: SafeId
    safe_message: NonEmptyStr
    accepted_at_utc: UtcDateTime | None
    finished_at_utc: UtcDateTime | None
    result: dict[str, CommandJsonValue] | None

    @field_validator("result", mode="before")
    @classmethod
    def require_rust_serde_integer_range(cls, value: object) -> object:
        _require_command_json_integer_range(value)
        return value


class CommandMessagePayload(StrictModel):
    request: CommandRequest


class CommandReceiptPayload(StrictModel):
    receipt: CommandReceipt


def _require_command_json_integer_range(value: object) -> None:
    if type(value) is int and not -(2**63) <= value <= 2**64 - 1:
        raise ValueError("JSON integer is outside the shared Rust serde range")
    if isinstance(value, dict):
        for child in value.values():
            _require_command_json_integer_range(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _require_command_json_integer_range(child)
