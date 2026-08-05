"""Pure controller-owned authorization policy for governed TUI commands."""

from __future__ import annotations

import hashlib
import hmac
import json
from types import MappingProxyType
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .command_contracts import (
    COMMAND_SPECS,
    BackupRestorePayload,
    CommandRequest,
)
from .views import (
    CapabilityState,
    CapabilityView,
    CommandSpecView,
    NonEmptyStr,
    SafeId,
    Sha256Hex,
    StrictModel,
    WireUInt,
)


AuthorizationCode = Literal[
    "authorized",
    "locked",
    "viewer",
    "unknown-command",
    "capability-disabled",
    "stale-state",
    "reason-required",
    "confirmation-missing",
    "typed-confirmation-mismatch",
    "prerequisite-failed",
]
PrerequisiteState = Literal["satisfied", "failed", "unavailable"]

_SAFE_MESSAGES: MappingProxyType[str, str] = MappingProxyType(
    {
        "authorized": "Command is authorized.",
        "locked": "Console session is locked.",
        "viewer": "Take Control before sending commands.",
        "unknown-command": "Command is not in the current catalog.",
        "capability-disabled": "Command capability is disabled.",
        "stale-state": "The reviewed control state changed. Review and try again.",
        "reason-required": "A reason is required for this command.",
        "confirmation-missing": "Required confirmation is missing.",
        "typed-confirmation-mismatch": "Type ENABLE LIVE exactly.",
        "prerequisite-failed": "Command prerequisites are missing, stale, or failed.",
    }
)
_CANONICAL_SPECS: MappingProxyType[str, CommandSpecView] = MappingProxyType(
    {spec.command_type: spec for spec in COMMAND_SPECS}
)


class PrerequisiteCheck(StrictModel):
    prerequisite_id: SafeId
    state: PrerequisiteState
    binding_hash: Sha256Hex
    reason: NonEmptyStr | None

    @model_validator(mode="after")
    def require_reason_for_non_satisfied_state(self) -> Self:
        if self.state == "satisfied" and self.reason is not None:
            raise ValueError("satisfied prerequisite checks cannot include a reason")
        if self.state != "satisfied" and self.reason is None:
            raise ValueError("failed and unavailable prerequisite checks require a reason")
        return self


class EvaluatedPrerequisites(StrictModel):
    request_sha256: Sha256Hex
    complete: Literal[True]
    checks: Annotated[tuple[PrerequisiteCheck, ...], Field(max_length=64)]

    @model_validator(mode="after")
    def require_unique_check_ids(self) -> Self:
        check_ids = tuple(check.prerequisite_id for check in self.checks)
        if len(check_ids) != len(set(check_ids)):
            raise ValueError("prerequisite check IDs must be unique")
        return self


class CommandContext(StrictModel):
    operator_id: SafeId
    client_id: SafeId
    authenticated: bool
    owns_control_lease: bool
    control_version: WireUInt
    control_hash: Sha256Hex
    capabilities: tuple[CapabilityView, ...]
    prerequisites: EvaluatedPrerequisites

    @model_validator(mode="after")
    def require_unique_capability_ids(self) -> Self:
        capability_ids = tuple(capability.capability_id for capability in self.capabilities)
        if len(capability_ids) != len(set(capability_ids)):
            raise ValueError("capability IDs must be unique")
        return self


class AuthorizationDecision(StrictModel):
    allowed: bool
    code: AuthorizationCode
    safe_message: NonEmptyStr

    @model_validator(mode="after")
    def require_consistent_outcome(self) -> Self:
        if self.allowed != (self.code == "authorized"):
            raise ValueError("authorization outcome and code disagree")
        return self


def canonical_request_hash(request: CommandRequest) -> str:
    """Hash the complete typed request using canonical UTF-8 JSON."""

    canonical = json.dumps(
        request.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class CommandPolicy:
    """Authorize without performing I/O, logging payloads, or calling handlers."""

    def authorize(
        self,
        context: CommandContext,
        request: CommandRequest,
        spec: CommandSpecView,
    ) -> AuthorizationDecision:
        if not context.authenticated:
            return self._decision(False, "locked")
        if not context.owns_control_lease:
            return self._decision(False, "viewer")

        canonical_spec = _CANONICAL_SPECS.get(request.command_type)
        if canonical_spec is None or spec != canonical_spec:
            return self._decision(False, "unknown-command")

        capability = next(
            (
                row
                for row in context.capabilities
                if row.capability_id == canonical_spec.capability_id
            ),
            None,
        )
        if capability is None or capability.state is not CapabilityState.ENABLED:
            safe_message = capability.reason if capability is not None else None
            return self._decision(False, "capability-disabled", safe_message)

        if request.reviewed_control_version != context.control_version or not hmac.compare_digest(
            request.reviewed_control_hash,
            context.control_hash,
        ):
            return self._decision(False, "stale-state")

        if canonical_spec.reason_rule == "required" and request.reason is None:
            return self._decision(False, "reason-required")

        confirmation_rejection = self._confirmation_rejection(request, canonical_spec)
        if confirmation_rejection is not None:
            return self._decision(False, confirmation_rejection)

        request_hash = canonical_request_hash(request)
        prerequisites = context.prerequisites
        if not hmac.compare_digest(prerequisites.request_sha256, request_hash):
            return self._decision(False, "prerequisite-failed")
        failed_check = next(
            (check for check in prerequisites.checks if check.state != "satisfied"),
            None,
        )
        if failed_check is not None:
            return self._decision(False, "prerequisite-failed", failed_check.reason)
        if isinstance(request.payload, BackupRestorePayload):
            bound_hash = (
                request.confirmation.bound_preview_hash
                if request.confirmation is not None
                else None
            )
            if bound_hash is None or not hmac.compare_digest(
                bound_hash,
                request.payload.preview_hash,
            ):
                return self._decision(False, "prerequisite-failed")

        return self._decision(True, "authorized")

    @staticmethod
    def _confirmation_rejection(
        request: CommandRequest,
        spec: CommandSpecView,
    ) -> Literal["confirmation-missing", "typed-confirmation-mismatch"] | None:
        confirmation = request.confirmation
        if spec.confirmation_level == "none":
            return None if confirmation is None else "confirmation-missing"
        if confirmation is None:
            return "confirmation-missing"
        if spec.confirmation_level == "confirm":
            valid = (
                confirmation.first_confirmed
                and not confirmation.second_confirmed
                and confirmation.typed_text is None
                and confirmation.bound_preview_hash is None
            )
            return None if valid else "confirmation-missing"
        if spec.confirmation_level == "double-confirm":
            valid = (
                confirmation.first_confirmed
                and confirmation.second_confirmed
                and confirmation.typed_text is None
                and (
                    spec.command_type == "backup.restore" or confirmation.bound_preview_hash is None
                )
            )
            return None if valid else "confirmation-missing"
        valid_shape = (
            confirmation.first_confirmed
            and not confirmation.second_confirmed
            and confirmation.bound_preview_hash is None
        )
        if not valid_shape:
            return "confirmation-missing"
        if confirmation.typed_text != "ENABLE LIVE":
            return "typed-confirmation-mismatch"
        return None

    @staticmethod
    def _decision(
        allowed: bool,
        code: AuthorizationCode,
        safe_message: str | None = None,
    ) -> AuthorizationDecision:
        return AuthorizationDecision(
            allowed=allowed,
            code=code,
            safe_message=safe_message or _SAFE_MESSAGES[code],
        )
