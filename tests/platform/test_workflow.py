from __future__ import annotations

import socket
import urllib.request
from collections import defaultdict, deque
from datetime import datetime, timezone

import pytest
from langgraph.types import Command

from vesper.platform.contracts import (
    ApprovalDecision,
    EvidenceArtifactRef,
    ExecutionStatus,
    HumanApprovalDecision,
    RiskDecision,
    RiskReviewDecision,
    RunStatus,
    SpecialistReceipt,
    SpecialistRole,
    TaskRequest,
    ValidationCheck,
    ValidationResult,
)
from vesper.platform.persistence import PlatformPaths, open_persistence
from vesper.platform.workflow import PendingApprovalError, WorkflowController, build_workflow


NOW = datetime(2026, 7, 27, 16, 0, tzinfo=timezone.utc)
COMMON = {
    "run_id": "run-001",
    "task_id": "task-001",
    "repository_revision": "9f9df7f",
    "created_at": NOW,
}


def task(tmp_path) -> TaskRequest:
    return TaskRequest(
        **COMMON,
        objective="Implement the bounded offline slice.",
        repository_root=str(tmp_path),
        acceptance_checks=("python -m pytest tests/platform",),
    )


def artifact(name: str = "result") -> EvidenceArtifactRef:
    return EvidenceArtifactRef(
        **COMMON,
        artifact_id=name,
        relative_path=f"runs/run-001/{name}.json",
        sha256="a" * 64,
        size_bytes=10,
        media_type="application/json",
    )


def receipt(role: SpecialistRole, attempt: int = 1) -> SpecialistReceipt:
    return SpecialistReceipt(
        **COMMON,
        receipt_id=f"{role.value}-{attempt}",
        role=role,
        attempt=attempt,
        status=ExecutionStatus.COMPLETED,
        evidence=(artifact(f"{role.value}-{attempt}"),),
    )


class QueuedSpecialists:
    def __init__(self):
        self.calls = []

    def execute(self, request):
        self.calls.append(request)
        return receipt(request.role, request.attempt)


class QueuedValidator:
    def __init__(self, results):
        self.results = deque(results)
        self.calls = []

    def validate(self, request, development_receipt):
        self.calls.append((request, development_receipt))
        passed = self.results.popleft()
        return ValidationResult(
            **COMMON,
            attempt=development_receipt.attempt,
            passed=passed,
            checks=(
                ValidationCheck(
                    name="offline-test",
                    passed=passed,
                    command="python -m pytest tests/platform",
                    exit_code=0 if passed else 1,
                    evidence=(artifact(f"validation-{development_receipt.attempt}"),),
                ),
            ),
        )


class QueuedRiskReviewer:
    def __init__(self, decisions):
        self.decisions = deque(decisions)
        self.calls = []

    def review(self, request, development_receipt, validation):
        self.calls.append((request, development_receipt, validation))
        decision = self.decisions.popleft()
        return RiskReviewDecision(
            **COMMON,
            attempt=development_receipt.attempt,
            decision=decision,
            rationale=f"Risk decision: {decision.value}.",
            evidence=(artifact(f"risk-{development_receipt.attempt}"),),
        )


def controller(persistence, *, validations=(True,), risks=(RiskDecision.APPROVE,)):
    specialists = QueuedSpecialists()
    validator = QueuedValidator(validations)
    reviewer = QueuedRiskReviewer(risks)
    graph = build_workflow(
        checkpointer=persistence.checkpointer,
        store=persistence.langgraph_store,
        specialists=specialists,
        validator=validator,
        risk_reviewer=reviewer,
        clock=lambda: NOW,
    )
    return (
        WorkflowController(
            graph=graph,
            store=persistence.store,
            clock=lambda: NOW,
            id_factory=lambda: "approval-request-001",
        ),
        specialists,
        validator,
        reviewer,
    )


def test_product_routes_to_development_then_validation_and_risk(tmp_path):
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        workflow, specialists, validator, reviewer = controller(persistence)

        view = workflow.start(task(tmp_path))

    assert view.state.status is RunStatus.AWAITING_APPROVAL
    assert [call.role for call in specialists.calls] == [
        SpecialistRole.PRODUCT,
        SpecialistRole.DEVELOPMENT,
    ]
    assert len(validator.calls) == 1
    assert len(reviewer.calls) == 1
    assert view.pending_approval is not None
    assert view.state.approval is None


def test_validation_failure_returns_to_development(tmp_path):
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        workflow, specialists, _, _ = controller(persistence, validations=(False, True))

        view = workflow.start(task(tmp_path))

    assert view.state.status is RunStatus.AWAITING_APPROVAL
    assert [call.role for call in specialists.calls].count(SpecialistRole.DEVELOPMENT) == 2
    assert view.state.correction_count == 1
    assert view.state.correction_attempts[0].source == "validation"
    assert "offline-test" in specialists.calls[-1].instructions


def test_risk_rejection_returns_to_development(tmp_path):
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        workflow, specialists, _, reviewer = controller(
            persistence,
            validations=(True, True),
            risks=(RiskDecision.REJECT, RiskDecision.APPROVE),
        )

        view = workflow.start(task(tmp_path))

    assert view.state.status is RunStatus.AWAITING_APPROVAL
    assert [call.role for call in specialists.calls].count(SpecialistRole.DEVELOPMENT) == 2
    assert len(reviewer.calls) == 2
    assert view.state.correction_attempts[0].source == "risk-review"


def test_three_combined_failures_require_operator_intervention(tmp_path):
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        workflow, specialists, _, _ = controller(
            persistence,
            validations=(False, True, False),
            risks=(RiskDecision.REJECT,),
        )

        view = workflow.start(task(tmp_path))

    assert view.state.status is RunStatus.OPERATOR_INTERVENTION
    assert view.state.correction_count == 3
    assert [call.role for call in specialists.calls].count(SpecialistRole.DEVELOPMENT) == 3
    assert view.pending_approval is None


def test_risk_approval_is_a_real_persisted_langgraph_interrupt(tmp_path):
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        workflow, _, _, _ = controller(persistence)
        view = workflow.start(task(tmp_path))
        snapshot = workflow.snapshot("run-001")

    assert view.state.status is RunStatus.AWAITING_APPROVAL
    assert snapshot.next == ("human_approval",)
    assert snapshot.tasks[0].interrupts
    assert view.checkpoint_id
    assert view.pending_approval.checkpoint_id == view.checkpoint_id


def test_explicit_approval_then_resume_is_required_for_acceptance(tmp_path):
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        workflow, _, _, _ = controller(persistence)
        pending = workflow.start(task(tmp_path))
        decision = HumanApprovalDecision(
            **COMMON,
            approval_id="approval-001",
            request_id=pending.pending_approval.request_id,
            checkpoint_id=pending.checkpoint_id,
            operator_id="operator",
            decision=ApprovalDecision.APPROVE,
            reason="Reviewed deterministic and risk evidence.",
            decided_at=NOW,
        )

        stored = workflow.record_decision("run-001", decision)
        still_pending = workflow.inspect("run-001")
        accepted = workflow.resume("run-001")

    assert stored == decision
    assert still_pending.state.status is RunStatus.AWAITING_APPROVAL
    assert accepted.state.status is RunStatus.ACCEPTED
    assert accepted.state.approval == decision
    assert accepted.pending_approval is None


def test_rejection_at_approval_boundary_cannot_accept(tmp_path):
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        workflow, _, _, _ = controller(persistence)
        pending = workflow.start(task(tmp_path))
        decision = HumanApprovalDecision(
            **COMMON,
            approval_id="approval-001",
            request_id=pending.pending_approval.request_id,
            checkpoint_id=pending.checkpoint_id,
            operator_id="operator",
            decision=ApprovalDecision.REJECT,
            reason="Operator rejected the run.",
            decided_at=NOW,
        )
        workflow.record_decision("run-001", decision)

        rejected = workflow.resume("run-001")

    assert rejected.state.status is RunStatus.REJECTED
    assert rejected.state.approval.decision is ApprovalDecision.REJECT
    assert rejected.pending_approval is None


def test_resume_without_persisted_approval_fails_closed(tmp_path):
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        workflow, _, _, _ = controller(persistence)
        workflow.start(task(tmp_path))

        with pytest.raises(PendingApprovalError):
            workflow.resume("run-001")


def test_direct_graph_resume_without_persisted_approval_fails_closed(tmp_path):
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        workflow, _, _, _ = controller(persistence)
        pending = workflow.start(task(tmp_path))
        fabricated = HumanApprovalDecision(
            **COMMON,
            approval_id="fabricated-approval",
            request_id=pending.pending_approval.request_id,
            checkpoint_id=pending.checkpoint_id,
            operator_id="unverified-operator",
            decision=ApprovalDecision.APPROVE,
            reason="This was never persisted through the approval boundary.",
            decided_at=NOW,
        )

        with pytest.raises(PendingApprovalError, match="persisted operator decision"):
            workflow.graph.invoke(
                Command(resume=fabricated.model_dump(mode="json")),
                {"configurable": {"thread_id": "run-001"}},
            )

        assert persistence.store.get(("system", "approval-decisions"), "run-001") is None
        assert workflow.inspect("run-001").state.status is RunStatus.AWAITING_APPROVAL


def test_stale_checkpoint_approval_is_rejected(tmp_path):
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        workflow, _, _, _ = controller(persistence)
        pending = workflow.start(task(tmp_path))
        stale = HumanApprovalDecision(
            **COMMON,
            approval_id="approval-001",
            request_id=pending.pending_approval.request_id,
            checkpoint_id="stale-checkpoint",
            operator_id="operator",
            decision=ApprovalDecision.APPROVE,
            reason="This decision is stale.",
            decided_at=NOW,
        )

        with pytest.raises(PendingApprovalError):
            workflow.record_decision("run-001", stale)


def test_usage_limit_stops_without_consuming_correction_budget(tmp_path):
    class UsageLimitedSpecialists(QueuedSpecialists):
        def execute(self, request):
            self.calls.append(request)
            if request.role is SpecialistRole.DEVELOPMENT:
                return SpecialistReceipt(
                    **COMMON,
                    receipt_id="usage-limited",
                    role=request.role,
                    attempt=request.attempt,
                    status=ExecutionStatus.USAGE_LIMITED,
                    error_code="usage_limit",
                )
            return receipt(request.role, request.attempt)

    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        specialists = UsageLimitedSpecialists()
        graph = build_workflow(
            checkpointer=persistence.checkpointer,
            store=persistence.langgraph_store,
            specialists=specialists,
            validator=QueuedValidator((True,)),
            risk_reviewer=QueuedRiskReviewer((RiskDecision.APPROVE,)),
            clock=lambda: NOW,
        )
        workflow = WorkflowController(graph=graph, store=persistence.store, clock=lambda: NOW)

        view = workflow.start(task(tmp_path))

    assert view.state.status is RunStatus.USAGE_LIMITED
    assert view.state.correction_count == 0
    assert view.pending_approval is None


def test_mismatched_risk_authority_fails_closed_without_approval(tmp_path):
    class MismatchedReviewer(QueuedRiskReviewer):
        def review(self, request, development_receipt, validation):
            valid = super().review(request, development_receipt, validation)
            return valid.model_copy(update={"task_id": "different-task"})

    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        specialists = QueuedSpecialists()
        graph = build_workflow(
            checkpointer=persistence.checkpointer,
            store=persistence.langgraph_store,
            specialists=specialists,
            validator=QueuedValidator((True,)),
            risk_reviewer=MismatchedReviewer((RiskDecision.APPROVE,)),
            clock=lambda: NOW,
        )
        workflow = WorkflowController(graph=graph, store=persistence.store, clock=lambda: NOW)

        view = workflow.start(task(tmp_path))

    assert view.state.status is RunStatus.FAILED
    assert view.pending_approval is None
    assert "authority" in view.state.terminal_reason.lower()


def test_mismatched_specialist_evidence_authority_fails_closed(tmp_path):
    class MismatchedEvidenceSpecialists(QueuedSpecialists):
        def execute(self, request):
            valid = super().execute(request)
            foreign = artifact("foreign-specialist").model_copy(update={"run_id": "other-run"})
            return valid.model_copy(update={"evidence": (foreign,)})

    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        graph = build_workflow(
            checkpointer=persistence.checkpointer,
            store=persistence.langgraph_store,
            specialists=MismatchedEvidenceSpecialists(),
            validator=QueuedValidator((True,)),
            risk_reviewer=QueuedRiskReviewer((RiskDecision.APPROVE,)),
            clock=lambda: NOW,
        )
        workflow = WorkflowController(graph=graph, store=persistence.store, clock=lambda: NOW)

        view = workflow.start(task(tmp_path))

    assert view.state.status is RunStatus.FAILED
    assert "authority" in view.state.terminal_reason.lower()


def test_mismatched_validation_evidence_authority_fails_closed(tmp_path):
    class MismatchedEvidenceValidator(QueuedValidator):
        def validate(self, request, development_receipt):
            valid = super().validate(request, development_receipt)
            foreign = artifact("foreign-validation").model_copy(update={"task_id": "other-task"})
            check = valid.checks[0].model_copy(update={"evidence": (foreign,)})
            return valid.model_copy(update={"checks": (check,)})

    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        graph = build_workflow(
            checkpointer=persistence.checkpointer,
            store=persistence.langgraph_store,
            specialists=QueuedSpecialists(),
            validator=MismatchedEvidenceValidator((True,)),
            risk_reviewer=QueuedRiskReviewer((RiskDecision.APPROVE,)),
            clock=lambda: NOW,
        )
        workflow = WorkflowController(graph=graph, store=persistence.store, clock=lambda: NOW)

        view = workflow.start(task(tmp_path))

    assert view.state.status is RunStatus.FAILED
    assert "authority" in view.state.terminal_reason.lower()


def test_mismatched_risk_evidence_authority_fails_closed(tmp_path):
    class MismatchedEvidenceReviewer(QueuedRiskReviewer):
        def review(self, request, development_receipt, validation):
            valid = super().review(request, development_receipt, validation)
            foreign = artifact("foreign-risk").model_copy(
                update={"repository_revision": "different-revision"}
            )
            return valid.model_copy(update={"evidence": (foreign,)})

    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        graph = build_workflow(
            checkpointer=persistence.checkpointer,
            store=persistence.langgraph_store,
            specialists=QueuedSpecialists(),
            validator=QueuedValidator((True,)),
            risk_reviewer=MismatchedEvidenceReviewer((RiskDecision.APPROVE,)),
            clock=lambda: NOW,
        )
        workflow = WorkflowController(graph=graph, store=persistence.store, clock=lambda: NOW)

        view = workflow.start(task(tmp_path))

    assert view.state.status is RunStatus.FAILED
    assert view.pending_approval is None
    assert "authority" in view.state.terminal_reason.lower()


def test_checkpoint_recovery_after_controller_process_reopen(tmp_path):
    paths = PlatformPaths.below(tmp_path / "platform")
    with open_persistence(paths) as persistence:
        workflow, _, _, _ = controller(persistence)
        pending = workflow.start(task(tmp_path))
        decision = HumanApprovalDecision(
            **COMMON,
            approval_id="approval-001",
            request_id=pending.pending_approval.request_id,
            checkpoint_id=pending.checkpoint_id,
            operator_id="operator",
            decision=ApprovalDecision.APPROVE,
            reason="Resume after process recreation.",
            decided_at=NOW,
        )
        workflow.record_decision("run-001", decision)

    with open_persistence(paths) as reopened:
        recovered_workflow, specialists, _, _ = controller(reopened)
        before_resume = recovered_workflow.inspect("run-001")
        after_resume = recovered_workflow.resume("run-001")

    assert before_resume.state.status is RunStatus.AWAITING_APPROVAL
    assert after_resume.state.status is RunStatus.ACCEPTED
    assert specialists.calls == []


def test_langgraph_execution_makes_no_langsmith_network_calls(tmp_path, monkeypatch):
    attempted = defaultdict(int)

    def forbidden_socket(*args, **kwargs):
        attempted["socket"] += 1
        raise AssertionError("LangSmith network activity is forbidden")

    def forbidden_urlopen(*args, **kwargs):
        attempted["urlopen"] += 1
        raise AssertionError("LangSmith network activity is forbidden")

    monkeypatch.setattr(socket, "create_connection", forbidden_socket)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden_urlopen)

    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        workflow, _, _, _ = controller(persistence)
        view = workflow.start(task(tmp_path))

    assert view.state.status is RunStatus.AWAITING_APPROVAL
    assert dict(attempted) == {}
