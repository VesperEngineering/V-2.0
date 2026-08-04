from __future__ import annotations

from collections.abc import Mapping

import pytest
from pydantic import ValidationError

from vesper.platform.tui.command_contracts import (
    COMMAND_SPECS,
    CommandRequest,
    ConfirmationProof,
)
from vesper.platform.tui.command_policy import (
    AuthorizationDecision,
    CommandContext,
    CommandPolicy,
    EvaluatedPrerequisites,
    PrerequisiteCheck,
    canonical_request_hash,
)
from vesper.platform.tui.views import CapabilityState, CapabilityView, CommandSpecView


CONTROL_HASH = "7c222fb2927d828af22f592134e8932480637c0d1a3a6c9f5d6f0f975f6e3f43"
OTHER_HASH = "8c222fb2927d828af22f592134e8932480637c0d1a3a6c9f5d6f0f975f6e3f43"
_DEFAULT = object()
VALID_PAYLOADS: Mapping[str, dict[str, object]] = {
    "note.add": {
        "target_type": "stock",
        "target_id": "AAPL",
        "body": "Note",
        "visibility": "private",
    },
    "alert.dismiss": {"alert_id": "alert:1"},
    "layout.reset": {"screen": None},
    "approval.approve": {"run_id": "run:1", "checkpoint_id": "checkpoint:1"},
    "approval.hold": {"run_id": "run:1", "checkpoint_id": "checkpoint:1"},
    "approval.reject": {"run_id": "run:1", "checkpoint_id": "checkpoint:1"},
    "approval.rework": {
        "run_id": "run:1",
        "checkpoint_id": "checkpoint:1",
        "evidence_ids": ["evidence:1"],
    },
    "agent.send-message": {"agent_id": "agent:risk", "text": "Review"},
    "agent.enqueue": {
        "agent_id": "agent:risk",
        "title": "Review",
        "objective": "Check risk",
        "priority": 50,
    },
    "agent.pause": {"work_id": "work:1"},
    "agent.stop": {"work_id": "work:1", "workflow_run_id": None},
    "agent.retry": {"work_id": "work:1"},
    "agent.set-priority": {"work_id": "work:1", "priority": 75},
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
    "model.request-promotion": {"candidate_id": "candidate:1", "evidence_ids": ["evidence:1"]},
    "model.request-rollback": {"candidate_id": "candidate:1", "evidence_ids": ["evidence:1"]},
    "memory.compress-now": {"agent_id": "agent:risk"},
    "backup.create": {"destination": "C:\\backups\\v20.zip"},
    "backup.restore": {
        "archive": "C:\\backups\\v20.zip",
        "preview_hash": CONTROL_HASH,
        "safety_backup_receipt_id": "receipt:backup",
    },
    "source-control.push": {"expected_revision": "a" * 40},
}


def spec_for(command_type: str) -> CommandSpecView:
    return next(spec for spec in COMMAND_SPECS if spec.command_type == command_type)


def confirmation_for(spec: CommandSpecView) -> ConfirmationProof | None:
    if spec.confirmation_level == "none":
        return None
    if spec.confirmation_level == "confirm":
        return ConfirmationProof(first_confirmed=True)
    if spec.confirmation_level == "double-confirm":
        bound = CONTROL_HASH if spec.command_type == "backup.restore" else None
        return ConfirmationProof(
            first_confirmed=True,
            second_confirmed=True,
            bound_preview_hash=bound,
        )
    return ConfirmationProof(first_confirmed=True, typed_text="ENABLE LIVE")


def request_for(
    command_type: str,
    *,
    reason: str | None | object = _DEFAULT,
    confirmation: ConfirmationProof | None | object = _DEFAULT,
) -> CommandRequest:
    spec = spec_for(command_type)
    selected_reason = "Required rationale" if spec.reason_rule == "required" else None
    selected_confirmation = confirmation_for(spec)
    if reason is not _DEFAULT:
        assert reason is None or isinstance(reason, str)
        selected_reason = reason
    if confirmation is not _DEFAULT:
        assert confirmation is None or isinstance(confirmation, ConfirmationProof)
        selected_confirmation = confirmation
    return CommandRequest.model_validate(
        {
            "command_id": f"client-1:{command_type}",
            "command_type": command_type,
            "reviewed_control_version": 19,
            "reviewed_control_hash": CONTROL_HASH,
            "reason": selected_reason,
            "confirmation": (
                selected_confirmation.model_dump(mode="json")
                if isinstance(selected_confirmation, ConfirmationProof)
                else selected_confirmation
            ),
            "payload": VALID_PAYLOADS[command_type],
        }
    )


def context_for(
    request: CommandRequest,
    *,
    authenticated: bool = True,
    owns_control_lease: bool = True,
    capability_state: CapabilityState = CapabilityState.ENABLED,
    control_version: int = 19,
    control_hash: str = CONTROL_HASH,
    prerequisite_hash: str | None = None,
    checks: tuple[PrerequisiteCheck, ...] | None = None,
) -> CommandContext:
    request_hash = prerequisite_hash or canonical_request_hash(request)
    selected_checks = checks
    if selected_checks is None:
        selected_checks = (
            PrerequisiteCheck(
                prerequisite_id="control-state",
                state="satisfied",
                binding_hash=request_hash,
                reason=None,
            ),
        )
    return CommandContext(
        operator_id="operator:windows",
        client_id="client:1",
        authenticated=authenticated,
        owns_control_lease=owns_control_lease,
        control_version=control_version,
        control_hash=control_hash,
        capabilities=(
            CapabilityView(
                capability_id=request.command_type,
                state=capability_state,
                reason=None if capability_state is CapabilityState.ENABLED else "Disabled.",
            ),
        ),
        prerequisites=EvaluatedPrerequisites(
            request_sha256=request_hash,
            complete=True,
            checks=selected_checks,
        ),
    )


@pytest.mark.parametrize("spec", COMMAND_SPECS, ids=lambda spec: spec.command_type)
def test_all_31_canonical_commands_authorize_with_exact_policy(spec: CommandSpecView) -> None:
    request = request_for(spec.command_type)
    decision = CommandPolicy().authorize(context_for(request), request, spec)
    assert decision == AuthorizationDecision(
        allowed=True,
        code="authorized",
        safe_message="Command is authorized.",
    )


def test_rejection_precedence_is_exact() -> None:
    request = request_for("approval.reject", reason=None, confirmation=None)
    canonical = spec_for("approval.reject")
    forged = canonical.model_copy(update={"capability_id": "wrong-capability"})
    policy = CommandPolicy()
    context = context_for(
        request,
        authenticated=False,
        owns_control_lease=False,
        capability_state=CapabilityState.DISABLED,
        control_version=18,
        control_hash=OTHER_HASH,
        prerequisite_hash=OTHER_HASH,
        checks=(
            PrerequisiteCheck(
                prerequisite_id="risk",
                state="failed",
                binding_hash=OTHER_HASH,
                reason="Blocked.",
            ),
        ),
    )
    assert policy.authorize(context, request, forged).code == "locked"
    context = context.model_copy(update={"authenticated": True})
    assert policy.authorize(context, request, forged).code == "viewer"
    context = context.model_copy(update={"owns_control_lease": True})
    assert policy.authorize(context, request, forged).code == "unknown-command"
    assert policy.authorize(context, request, canonical).code == "capability-disabled"
    context = context.model_copy(
        update={
            "capabilities": (
                CapabilityView(
                    capability_id=request.command_type,
                    state=CapabilityState.ENABLED,
                    reason=None,
                ),
            )
        }
    )
    assert policy.authorize(context, request, canonical).code == "stale-state"
    context = context.model_copy(update={"control_version": 19, "control_hash": CONTROL_HASH})
    assert policy.authorize(context, request, canonical).code == "reason-required"
    request = request_for("approval.reject", confirmation=None)
    assert policy.authorize(context, request, canonical).code == "confirmation-missing"
    request = request_for("approval.reject")
    assert policy.authorize(context, request, canonical).code == "prerequisite-failed"
    context = context_for(request)
    assert policy.authorize(context, request, canonical).allowed is True


@pytest.mark.parametrize(
    "command_type,confirmation,code",
    [
        ("note.add", None, "authorized"),
        ("note.add", ConfirmationProof(), "confirmation-missing"),
        ("approval.approve", None, "confirmation-missing"),
        ("approval.approve", ConfirmationProof(first_confirmed=False), "confirmation-missing"),
        ("approval.approve", ConfirmationProof(first_confirmed=True), "authorized"),
        (
            "approval.approve",
            ConfirmationProof(first_confirmed=True, second_confirmed=True),
            "confirmation-missing",
        ),
        (
            "approval.approve",
            ConfirmationProof(first_confirmed=True, typed_text="extra"),
            "confirmation-missing",
        ),
        (
            "approval.approve",
            ConfirmationProof(first_confirmed=True, bound_preview_hash=CONTROL_HASH),
            "confirmation-missing",
        ),
        (
            "trading.emergency-stop",
            ConfirmationProof(first_confirmed=False, second_confirmed=True),
            "confirmation-missing",
        ),
        (
            "trading.emergency-stop",
            ConfirmationProof(first_confirmed=True, second_confirmed=False),
            "confirmation-missing",
        ),
        (
            "trading.emergency-stop",
            ConfirmationProof(first_confirmed=True, second_confirmed=True),
            "authorized",
        ),
        (
            "trading.emergency-stop",
            ConfirmationProof(
                first_confirmed=True,
                second_confirmed=True,
                typed_text="extra",
            ),
            "confirmation-missing",
        ),
        (
            "trading.emergency-stop",
            ConfirmationProof(
                first_confirmed=True,
                second_confirmed=True,
                bound_preview_hash=CONTROL_HASH,
            ),
            "confirmation-missing",
        ),
        ("mode.enable-live", None, "confirmation-missing"),
        (
            "mode.enable-live",
            ConfirmationProof(first_confirmed=True),
            "typed-confirmation-mismatch",
        ),
        (
            "mode.enable-live",
            ConfirmationProof(first_confirmed=True, typed_text="enable live"),
            "typed-confirmation-mismatch",
        ),
        (
            "mode.enable-live",
            ConfirmationProof(first_confirmed=True, typed_text=" ENABLE LIVE "),
            "typed-confirmation-mismatch",
        ),
        (
            "mode.enable-live",
            ConfirmationProof(first_confirmed=False, typed_text="ENABLE LIVE"),
            "confirmation-missing",
        ),
        (
            "mode.enable-live",
            ConfirmationProof(
                first_confirmed=True, second_confirmed=True, typed_text="ENABLE LIVE"
            ),
            "confirmation-missing",
        ),
        (
            "mode.enable-live",
            ConfirmationProof(
                first_confirmed=True,
                typed_text="ENABLE LIVE",
                bound_preview_hash=CONTROL_HASH,
            ),
            "confirmation-missing",
        ),
        (
            "mode.enable-live",
            ConfirmationProof(first_confirmed=True, typed_text="ENABLE LIVE"),
            "authorized",
        ),
    ],
)
def test_confirmation_matrix_is_exact(
    command_type: str,
    confirmation: ConfirmationProof | None,
    code: str,
) -> None:
    request = request_for(command_type, confirmation=confirmation)
    decision = CommandPolicy().authorize(context_for(request), request, spec_for(command_type))
    assert decision.code == code


def test_prerequisites_are_bound_to_canonical_request_hash() -> None:
    original = request_for("approval.approve")
    changed = request_for("approval.approve", reason="A later reason")
    assert canonical_request_hash(original) != canonical_request_hash(changed)
    context = context_for(changed, prerequisite_hash=canonical_request_hash(original))
    decision = CommandPolicy().authorize(context, changed, spec_for("approval.approve"))
    assert decision.code == "prerequisite-failed"
    assert decision.safe_message == "Command prerequisites are missing, stale, or failed."
    failed = PrerequisiteCheck(
        prerequisite_id="risk",
        state="failed",
        binding_hash=canonical_request_hash(changed),
        reason="Risk is blocked.",
    )
    context = context_for(changed, checks=(failed,))
    decision = CommandPolicy().authorize(context, changed, spec_for("approval.approve"))
    assert decision.code == "prerequisite-failed"
    assert decision.safe_message == "Risk is blocked."
    unavailable = failed.model_copy(update={"state": "unavailable", "reason": "Unavailable."})
    context = context_for(changed, checks=(unavailable,))
    decision = CommandPolicy().authorize(context, changed, spec_for("approval.approve"))
    assert decision.code == "prerequisite-failed"
    assert decision.safe_message == "Unavailable."


def test_canonical_request_hash_is_pinned_utf8_compact_json() -> None:
    request = CommandRequest.model_validate(
        {
            "command_id": "client-1:note.add",
            "command_type": "note.add",
            "reviewed_control_version": 19,
            "reviewed_control_hash": CONTROL_HASH,
            "reason": None,
            "confirmation": None,
            "payload": {
                "target_type": "stock",
                "target_id": "AAPL",
                "body": "Café ☕",
                "visibility": "private",
            },
        }
    )
    assert canonical_request_hash(request) == (
        "3bb019d9e8891d0c1ff22d15de756e35163583afa4d61aef63babbd4926b0ead"
    )
    assert canonical_request_hash(request) == canonical_request_hash(request)


def test_canonical_request_hash_changes_with_semantic_fields() -> None:
    request = request_for("approval.approve")
    changed_requests = (
        request.model_copy(update={"reason": "Changed reason"}),
        request.model_copy(update={"confirmation": ConfirmationProof(first_confirmed=False)}),
        request.model_copy(
            update={"payload": request.payload.model_copy(update={"checkpoint_id": "checkpoint:2"})}
        ),
    )
    request_hash = canonical_request_hash(request)
    assert all(canonical_request_hash(changed) != request_hash for changed in changed_requests)


def test_each_prerequisite_fact_can_have_its_own_controller_hash() -> None:
    request = request_for("approval.approve")
    check = PrerequisiteCheck(
        prerequisite_id="risk",
        state="satisfied",
        binding_hash=OTHER_HASH,
        reason=None,
    )
    decision = CommandPolicy().authorize(
        context_for(request, checks=(check,)), request, spec_for("approval.approve")
    )
    assert decision.code == "authorized"


@pytest.mark.parametrize("bound_hash", [None, OTHER_HASH])
def test_restore_confirmation_must_bind_to_preview_hash(bound_hash: str | None) -> None:
    request = request_for(
        "backup.restore",
        confirmation=ConfirmationProof(
            first_confirmed=True,
            second_confirmed=True,
            bound_preview_hash=bound_hash,
        ),
    )
    decision = CommandPolicy().authorize(context_for(request), request, spec_for("backup.restore"))
    assert decision.code == "prerequisite-failed"


def test_canonical_spec_and_enabled_capability_are_controller_owned() -> None:
    request = request_for("note.add")
    canonical = spec_for("note.add")
    forged = canonical.model_copy(update={"confirmation_level": "confirm"})
    decision = CommandPolicy().authorize(context_for(request), request, forged)
    assert decision.code == "unknown-command"
    assert decision.safe_message == "Command is not in the current catalog."
    for state in (CapabilityState.DISABLED, CapabilityState.READ_ONLY):
        decision = CommandPolicy().authorize(
            context_for(request, capability_state=state), request, canonical
        )
        assert decision.code == "capability-disabled"
        assert decision.safe_message == "Disabled."

    missing = context_for(request).model_copy(update={"capabilities": ()})
    decision = CommandPolicy().authorize(missing, request, canonical)
    assert decision.code == "capability-disabled"
    assert decision.safe_message == "Command capability is disabled."


def test_context_and_prerequisites_reject_duplicate_ids_and_are_frozen() -> None:
    request = request_for("note.add")
    capability = CapabilityView(
        capability_id="note.add", state=CapabilityState.ENABLED, reason=None
    )
    with pytest.raises(ValidationError, match="capability IDs must be unique"):
        CommandContext(
            operator_id="operator:windows",
            client_id="client:1",
            authenticated=True,
            owns_control_lease=True,
            control_version=19,
            control_hash=CONTROL_HASH,
            capabilities=(capability, capability),
            prerequisites=EvaluatedPrerequisites(
                request_sha256=canonical_request_hash(request),
                complete=True,
                checks=(),
            ),
        )
    check = PrerequisiteCheck(
        prerequisite_id="risk",
        state="satisfied",
        binding_hash=canonical_request_hash(request),
        reason=None,
    )
    with pytest.raises(ValidationError, match="prerequisite check IDs must be unique"):
        EvaluatedPrerequisites(
            request_sha256=canonical_request_hash(request),
            complete=True,
            checks=(check, check),
        )
    with pytest.raises(ValidationError):
        check.state = "failed"


@pytest.mark.parametrize(
    "state,reason,valid",
    [
        ("satisfied", None, True),
        ("satisfied", "unexpected", False),
        ("failed", "Failed.", True),
        ("failed", None, False),
        ("unavailable", "Unavailable.", True),
        ("unavailable", None, False),
    ],
)
def test_prerequisite_state_requires_exact_reason_shape(
    state: str,
    reason: str | None,
    valid: bool,
) -> None:
    values = {
        "prerequisite_id": "risk",
        "state": state,
        "binding_hash": CONTROL_HASH,
        "reason": reason,
    }
    if valid:
        assert PrerequisiteCheck.model_validate(values).state == state
    else:
        with pytest.raises(ValidationError):
            PrerequisiteCheck.model_validate(values)


def test_evaluated_prerequisites_are_complete_and_bounded_to_64() -> None:
    checks = tuple(
        PrerequisiteCheck(
            prerequisite_id=f"check:{index}",
            state="satisfied",
            binding_hash=CONTROL_HASH,
            reason=None,
        )
        for index in range(64)
    )
    assert EvaluatedPrerequisites(request_sha256=CONTROL_HASH, complete=True, checks=checks)
    with pytest.raises(ValidationError):
        EvaluatedPrerequisites(
            request_sha256=CONTROL_HASH,
            complete=True,
            checks=checks
            + (
                PrerequisiteCheck(
                    prerequisite_id="check:64",
                    state="satisfied",
                    binding_hash=CONTROL_HASH,
                    reason=None,
                ),
            ),
        )
    with pytest.raises(ValidationError):
        EvaluatedPrerequisites.model_validate(
            {"request_sha256": CONTROL_HASH, "complete": False, "checks": []}
        )


def test_first_failed_or_unavailable_prerequisite_reason_is_returned() -> None:
    request = request_for("approval.approve")
    request_hash = canonical_request_hash(request)
    checks = (
        PrerequisiteCheck(
            prerequisite_id="market-data",
            state="satisfied",
            binding_hash=request_hash,
            reason=None,
        ),
        PrerequisiteCheck(
            prerequisite_id="broker-view",
            state="unavailable",
            binding_hash=request_hash,
            reason="Broker view is unavailable.",
        ),
        PrerequisiteCheck(
            prerequisite_id="risk",
            state="failed",
            binding_hash=request_hash,
            reason="Risk check failed.",
        ),
    )
    decision = CommandPolicy().authorize(
        context_for(request, checks=checks), request, spec_for("approval.approve")
    )
    assert decision.code == "prerequisite-failed"
    assert decision.safe_message == "Broker view is unavailable."


def test_fixed_rejection_messages_are_exact() -> None:
    request = request_for("approval.approve")
    spec = spec_for("approval.approve")
    policy = CommandPolicy()

    locked = policy.authorize(context_for(request, authenticated=False), request, spec)
    assert locked.safe_message == "Console session is locked."
    viewer = policy.authorize(context_for(request, owns_control_lease=False), request, spec)
    assert viewer.safe_message == "Take Control before sending commands."

    stale = policy.authorize(context_for(request, control_version=18), request, spec)
    assert stale.code == "stale-state"
    assert stale.safe_message == "The reviewed control state changed. Review and try again."

    missing_confirmation = request_for("approval.approve", confirmation=None)
    decision = policy.authorize(context_for(missing_confirmation), missing_confirmation, spec)
    assert decision.safe_message == "Required confirmation is missing."

    typed = request_for(
        "mode.enable-live",
        confirmation=ConfirmationProof(first_confirmed=True, typed_text="enable live"),
    )
    decision = policy.authorize(context_for(typed), typed, spec_for("mode.enable-live"))
    assert decision.code == "typed-confirmation-mismatch"
    assert decision.safe_message == "Type ENABLE LIVE exactly."


def test_authorization_decision_only_enforces_allowed_code_consistency() -> None:
    decision = AuthorizationDecision(
        allowed=False,
        code="capability-disabled",
        safe_message="Controller-owned disabled reason.",
    )
    assert decision.safe_message == "Controller-owned disabled reason."
    with pytest.raises(ValidationError, match="authorization outcome and code disagree"):
        AuthorizationDecision(
            allowed=True,
            code="capability-disabled",
            safe_message="Controller-owned disabled reason.",
        )
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AuthorizationDecision.model_validate(
            {
                "allowed": False,
                "code": "viewer",
                "safe_message": "Take Control before sending commands.",
                "request_hash": CONTROL_HASH,
            }
        )
