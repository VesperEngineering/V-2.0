"""No-effect default ports and strict work contracts for optional operations."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal, Protocol, Self

from pydantic import field_validator, model_validator

from vesper.platform.contracts import AgentRole
from vesper.platform.tui.views import (
    CapabilityState,
    CapabilityView,
    NonEmptyStr,
    SafeId,
    StrictModel,
)


class AdapterUnavailable(RuntimeError):
    """An optional effect adapter was not reviewed and installed."""


class CandidateApprovalError(RuntimeError):
    """The exact candidate request has no validated approval binding."""


class CandidateTrainingRequest(StrictModel):
    request_id: SafeId
    model_family: NonEmptyStr
    strategy: Literal["ml_model", "momentum"]
    feature_set_id: SafeId
    data_identity: NonEmptyStr
    evaluation_contract: NonEmptyStr
    artifact_root: NonEmptyStr

    @field_validator("artifact_root")
    @classmethod
    def require_safe_relative_artifact_root(cls, value: str) -> str:
        windows = PureWindowsPath(value)
        posix = PurePosixPath(value)
        if (
            windows.is_absolute()
            or posix.is_absolute()
            or bool(windows.drive)
            or bool(windows.root)
            or bool(windows.anchor)
        ):
            raise ValueError("artifact root must be relative")
        if ".." in windows.parts or ".." in posix.parts:
            raise ValueError("artifact root cannot traverse parent directories")
        if any(":" in part for part in windows.parts):
            raise ValueError("artifact root cannot contain Windows drive or stream markers")
        if any(PureWindowsPath(part).is_reserved() for part in windows.parts):
            raise ValueError("artifact root cannot contain a reserved Windows name")
        if len(windows.parts) < 2 or windows.parts[0].casefold() != "candidates":
            raise ValueError("artifact root must stay below the approved candidates root")
        return value

    def resolve_artifact_path(self, approved_root: Path) -> Path:
        if not isinstance(approved_root, Path):
            raise TypeError("approved_root must be Path")
        root = approved_root.resolve(strict=False)
        relative = Path(*PureWindowsPath(self.artifact_root).parts)
        candidate = (root / relative).resolve(strict=False)
        if not candidate.is_relative_to(root):
            raise ValueError("artifact root resolves outside the approved root")
        return candidate


def canonical_training_request_sha256(request: CandidateTrainingRequest) -> str:
    if type(request) is not CandidateTrainingRequest:
        raise TypeError("request must be CandidateTrainingRequest")
    payload = json.dumps(
        request.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class CandidateTrainingReceipt(StrictModel):
    request_id: SafeId
    receipt_id: SafeId
    status: Literal["completed", "failed"]


class WorkItem(StrictModel):
    work_id: SafeId
    kind: Literal[
        "incident",
        "approval",
        "portfolio",
        "operator-command",
        "normal",
        "research",
        "candidate",
    ]
    agent_id: SafeId
    objective: NonEmptyStr
    source_adapter_id: SafeId | None = None
    training_request: CandidateTrainingRequest | None = None

    @field_validator("agent_id")
    @classmethod
    def require_approved_agent_role(cls, value: str) -> str:
        if value not in {role.value for role in AgentRole}:
            raise ValueError("work item agent is not an approved V20 role")
        return value

    @model_validator(mode="after")
    def bind_candidate_request(self) -> Self:
        if (self.kind == "candidate") != (self.training_request is not None):
            raise ValueError("candidate-training-request-invariant")
        if (
            self.training_request is not None
            and self.training_request.request_id != self.work_id
        ):
            raise ValueError("candidate request ID must match work ID")
        return self


def validate_work_item(item: WorkItem) -> WorkItem:
    if type(item) is not WorkItem:
        raise TypeError("item must be WorkItem")
    return WorkItem.model_validate_json(item.model_dump_json(), strict=True)


class WorkReceipt(StrictModel):
    work_id: SafeId
    receipt_id: SafeId
    status: Literal["completed", "failed"]


class QwenWorkPort(Protocol):
    def available(self) -> CapabilityView: ...

    def run_one(self, work_item: WorkItem) -> WorkReceipt: ...


class CandidateTrainingPort(Protocol):
    def available(self) -> CapabilityView: ...

    def train_and_evaluate(
        self,
        request: CandidateTrainingRequest,
    ) -> CandidateTrainingReceipt: ...


class CandidateTrainingApprovalStore(Protocol):
    def require(self, request: CandidateTrainingRequest) -> None: ...


class UnavailableCandidateTrainingApprovalStore:
    def require(self, request: CandidateTrainingRequest) -> None:
        if type(request) is not CandidateTrainingRequest:
            raise TypeError("request must be CandidateTrainingRequest")
        raise CandidateApprovalError("candidate request is not exactly approved")


class UnavailableQwenWorkPort:
    _REASON = "The qwen:64k runtime adapter is not configured."

    def available(self) -> CapabilityView:
        return CapabilityView(
            capability_id="ops.qwen-work",
            state=CapabilityState.DISABLED,
            reason=self._REASON,
        )

    def run_one(self, work_item: WorkItem) -> WorkReceipt:
        if type(work_item) is not WorkItem:
            raise TypeError("work_item must be WorkItem")
        raise AdapterUnavailable(self._REASON)


class UnavailableTrainingPort:
    _REASON = "No approved candidate training adapter is configured."

    def available(self) -> CapabilityView:
        return CapabilityView(
            capability_id="ops.candidate-training",
            state=CapabilityState.DISABLED,
            reason=self._REASON,
        )

    def train_and_evaluate(
        self,
        request: CandidateTrainingRequest,
    ) -> CandidateTrainingReceipt:
        if type(request) is not CandidateTrainingRequest:
            raise TypeError("request must be CandidateTrainingRequest")
        raise AdapterUnavailable(self._REASON)
