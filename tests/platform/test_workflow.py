from __future__ import annotations

import json
import socket
import urllib.request
from collections import defaultdict, deque
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from langgraph.types import Command

from vesper.platform.contracts import (
    ApprovalDecision,
    DataResearchResult,
    DevelopmentSpecialistOutput,
    EvidenceArtifactRef,
    ExecutionStatus,
    HumanApprovalDecision,
    ModelEvaluationResult,
    ProductSpecialistOutput,
    RiskDecision,
    RiskReviewExecution,
    RiskReviewDecision,
    RunStatus,
    SpecialistReceipt,
    SpecialistRole,
    TaskRequest,
    ValidationCheck,
    ValidationResult,
)
from vesper.platform.persistence import PlatformPaths, open_persistence
from vesper.platform.workflow import (
    PendingApprovalError,
    WorkflowController,
    _workspace_sha256,
    build_workflow,
)


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


def test_workspace_hash_excludes_git_and_controller_state(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".state").mkdir()
    (tmp_path / ".git" / "control.lock").write_text("locked\n", encoding="utf-8")
    (tmp_path / ".state" / "runtime.json").write_text("state\n", encoding="utf-8")
    source = tmp_path / "source.py"
    source.write_text("before\n", encoding="utf-8")

    initial = _workspace_sha256(tmp_path)
    (tmp_path / ".git" / "control.lock").write_text("changed\n", encoding="utf-8")
    (tmp_path / ".state" / "runtime.json").write_text("changed\n", encoding="utf-8")

    assert _workspace_sha256(tmp_path) == initial
    source.write_text("after\n", encoding="utf-8")
    assert _workspace_sha256(tmp_path) != initial


def test_workspace_hash_excludes_worktree_metadata_files(tmp_path):
    git_file = tmp_path / ".git"
    state_file = tmp_path / ".state"
    source = tmp_path / "source.py"
    git_file.write_text("gitdir: C:/worktrees/v20\n", encoding="utf-8")
    state_file.write_text("controller state\n", encoding="utf-8")
    source.write_text("before\n", encoding="utf-8")

    initial = _workspace_sha256(tmp_path)
    git_file.write_text("gitdir: D:/other-worktree\n", encoding="utf-8")
    state_file.write_text("changed controller state\n", encoding="utf-8")

    assert _workspace_sha256(tmp_path) == initial
    source.write_text("after\n", encoding="utf-8")
    assert _workspace_sha256(tmp_path) != initial


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
    output = None
    if role is SpecialistRole.PRODUCT:
        output = ProductSpecialistOutput(
            **COMMON,
            role=role,
            attempt=attempt,
            route=SpecialistRole.DEVELOPMENT,
            summary="Bounded task.",
            development_instructions="Implement only the bounded task.",
            acceptance_checks=("python -m pytest tests/platform",),
        )
    elif role is SpecialistRole.DEVELOPMENT:
        output = DevelopmentSpecialistOutput(
            **COMMON,
            role=role,
            attempt=attempt,
            summary="Implemented bounded task.",
        )
    return SpecialistReceipt(
        **COMMON,
        receipt_id=f"{role.value}-{attempt}",
        role=role,
        attempt=attempt,
        status=ExecutionStatus.COMPLETED,
        output=output,
        evidence=(artifact(f"{role.value}-{attempt}"),),
    )


class QueuedSpecialists:
    def __init__(self):
        self.calls = []

    def execute(self, request):
        self.calls.append(request)
        return receipt(request.role, request.attempt)


class DataResearcher:
    def __init__(self):
        self.calls = []

    def research(self, request):
        self.calls.append(request)
        return DataResearchResult(
            **COMMON,
            available=True,
            database_path="vesper/data/massive/sp500/sp500_ohlcv.sqlite",
            table_name="sp500_ohlcv",
            row_count=100,
            ticker_count=10,
            start_date="2020-01-02",
            end_date="2026-07-27",
            required_columns=("ticker", "date", "open", "high", "low", "close", "volume"),
            null_price_rows=0,
            invalid_date_rows=0,
            split_adjustments_path="vesper/data/massive/split_adjustments.json",
            split_adjustments_sha256="d" * 64,
            evidence=(artifact("data-research"),),
        )


class ModelEvaluator:
    def __init__(self):
        self.calls = []

    def evaluate(self, request):
        self.calls.append(request)
        return ModelEvaluationResult(
            **COMMON,
            available=True,
            configured_model_path="models/xgb_ranker.json",
            metadata_path="models/xgb_ranker.metadata.json",
            actual_sha256="e" * 64,
            expected_sha256="e" * 64,
            hash_matches=True,
            label_horizon=5,
            train_ic=0.04,
            out_of_sample_ic=0.03,
            train_samples=100,
            test_samples=50,
            evaluation_passed=True,
            evidence=(artifact("model-evaluation"),),
        )


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

    def review(
        self,
        request,
        development_receipt,
        validation,
        *,
        data_research,
        model_evaluation,
    ):
        self.calls.append(
            (request, development_receipt, validation, data_research, model_evaluation)
        )
        decision = self.decisions.popleft()
        return RiskReviewDecision(
            **COMMON,
            attempt=development_receipt.attempt,
            decision=decision,
            rationale=f"Risk decision: {decision.value}.",
            evidence=(artifact(f"risk-{development_receipt.attempt}"),),
            scope_compliant=True,
            evidence_owned=True,
            prohibited_actions_compliant=True,
        )


def controller(
    persistence,
    *,
    validations=(True,),
    risks=(RiskDecision.APPROVE,),
    workspace_hasher=lambda _workspace: "b" * 64,
    evidence_reader=None,
    data_researcher=None,
    model_evaluator=None,
    specialist_executor=None,
):
    specialists = specialist_executor or QueuedSpecialists()
    data_researcher = data_researcher or DataResearcher()
    model_evaluator = model_evaluator or ModelEvaluator()
    validator = QueuedValidator(validations)
    reviewer = QueuedRiskReviewer(risks)
    graph = build_workflow(
        checkpointer=persistence.checkpointer,
        langgraph_store=persistence.langgraph_store,
        approval_store=persistence.store,
        specialists=specialists,
        data_researcher=data_researcher,
        model_evaluator=model_evaluator,
        validator=validator,
        risk_reviewer=reviewer,
        workspace_hasher=workspace_hasher,
        evidence_reader=evidence_reader,
        clock=lambda: NOW,
    )
    return (
        WorkflowController(
            graph=graph,
            store=persistence.store,
            workspace_hasher=workspace_hasher,
            evidence_reader=evidence_reader,
            clock=lambda: NOW,
            id_factory=lambda: "approval-request-001",
        ),
        specialists,
        validator,
        reviewer,
    )


@pytest.mark.parametrize("foreign_stage", ("data", "model"))
def test_research_nodes_fail_closed_on_foreign_authority(tmp_path, foreign_stage):
    class ForeignDataResearcher(DataResearcher):
        def research(self, request):
            return super().research(request).model_copy(update={"run_id": "foreign"})

    class ForeignModelEvaluator(ModelEvaluator):
        def evaluate(self, request):
            return super().evaluate(request).model_copy(update={"run_id": "foreign"})

    options = (
        {"data_researcher": ForeignDataResearcher()}
        if foreign_stage == "data"
        else {"model_evaluator": ForeignModelEvaluator()}
    )
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        workflow, specialists, validator, reviewer = controller(persistence, **options)

        view = workflow.start(task(tmp_path))

    assert view.state.status is RunStatus.FAILED
    assert (
        foreign_stage.replace("data", "Data Research").replace("model", "Model Evaluation")
        in view.state.terminal_reason
    )
    assert specialists.calls == []
    assert validator.calls == []
    assert reviewer.calls == []


@pytest.mark.parametrize("failed_stage", ("data", "model"))
def test_research_readiness_failure_stops_before_product(tmp_path, failed_stage):
    class UnavailableDataResearcher(DataResearcher):
        def research(self, request):
            return (
                super()
                .research(request)
                .model_copy(update={"available": False, "warnings": ("data unavailable",)})
            )

    class FailedModelEvaluator(ModelEvaluator):
        def evaluate(self, request):
            return (
                super()
                .evaluate(request)
                .model_copy(
                    update={
                        "expected_sha256": "f" * 64,
                        "hash_matches": False,
                        "evaluation_passed": False,
                        "warnings": ("model failed",),
                    }
                )
            )

    options = (
        {"data_researcher": UnavailableDataResearcher()}
        if failed_stage == "data"
        else {"model_evaluator": FailedModelEvaluator()}
    )
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        workflow, specialists, validator, reviewer = controller(persistence, **options)

        view = workflow.start(task(tmp_path))

    assert view.state.status is RunStatus.OPERATOR_INTERVENTION
    assert "Research integrity gate failed" in view.state.terminal_reason
    assert specialists.calls == []
    assert validator.calls == []
    assert reviewer.calls == []


def test_resumed_product_rechecks_research_evidence_before_specialist_execution(tmp_path):
    class CrashOnceAtProduct(QueuedSpecialists):
        def __init__(self):
            super().__init__()
            self.crash = True

        def execute(self, request):
            if request.role is SpecialistRole.PRODUCT and self.crash:
                self.crash = False
                raise RuntimeError("simulated controller loss before Product completed")
            return super().execute(request)

    evidence_available = True

    def read_evidence(_artifact):
        if not evidence_available:
            raise OSError("research evidence removed")
        return b"verified"

    specialists = CrashOnceAtProduct()
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        workflow, _, validator, reviewer = controller(
            persistence,
            evidence_reader=read_evidence,
            specialist_executor=specialists,
        )
        with pytest.raises(RuntimeError, match="controller loss"):
            workflow.start(task(tmp_path))

        evidence_available = False
        view = workflow.resume("run-001")

    assert view.state.status is RunStatus.OPERATOR_INTERVENTION
    assert "evidence integrity" in view.state.terminal_reason
    assert specialists.calls == []
    assert validator.calls == []
    assert reviewer.calls == []


def test_pre_research_checkpoint_requires_explicit_new_run(tmp_path):
    legacy = SimpleNamespace(
        values={
            "task": task(tmp_path).model_dump(mode="json"),
            "status": RunStatus.PRODUCT.value,
        },
        config={"configurable": {"checkpoint_id": "legacy-checkpoint"}},
    )
    graph = SimpleNamespace(get_state=lambda _config: legacy)
    store = SimpleNamespace(get=lambda *_args: None)
    workflow = WorkflowController(graph=graph, store=store)

    with pytest.raises(PendingApprovalError, match="predates required"):
        workflow.inspect("run-001")


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
    assert view.state.data_research is not None
    assert view.state.model_evaluation is not None
    assert "Controller-owned read-only research context" in specialists.calls[0].instructions
    assert '"row_count": 100' in specialists.calls[0].instructions
    assert "runs/run-001/data-research.json" not in specialists.calls[0].instructions
    assert reviewer.calls[0][3] == view.state.data_research
    assert reviewer.calls[0][4] == view.state.model_evaluation
    assert view.pending_approval is not None
    assert {item.artifact_id for item in view.pending_approval.evidence} == {
        "data-research",
        "model-evaluation",
        "v20-product-1",
        "v20-development-1",
        "validation-1",
        "risk-1",
    }
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


def test_approval_cannot_accept_workspace_bytes_changed_after_decision(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "RESULT.md").write_text("reviewed\n", encoding="utf-8")
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        workflow, _, _, _ = controller(
            persistence,
            workspace_hasher=_workspace_sha256,
        )
        pending = workflow.start(task(workspace))
        decision = HumanApprovalDecision(
            **COMMON,
            approval_id="approval-001",
            request_id=pending.pending_approval.request_id,
            checkpoint_id=pending.checkpoint_id,
            operator_id="operator",
            decision=ApprovalDecision.APPROVE,
            reason="Reviewed exact workspace bytes.",
            decided_at=NOW,
        )
        workflow.record_decision("run-001", decision)
        (workspace / "RESULT.md").write_text("changed-after-review\n", encoding="utf-8")

        with pytest.raises(PendingApprovalError, match="workspace changed"):
            workflow.resume("run-001")


def test_approval_cannot_accept_corrupt_evidence(tmp_path):
    corrupt = False

    def read_evidence(_artifact):
        if corrupt:
            raise ValueError("corrupt evidence")
        return b"verified"

    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        workflow, _, _, _ = controller(persistence, evidence_reader=read_evidence)
        pending = workflow.start(task(tmp_path))
        decision = HumanApprovalDecision(
            **COMMON,
            approval_id="approval-001",
            request_id=pending.pending_approval.request_id,
            checkpoint_id=pending.checkpoint_id,
            operator_id="operator",
            decision=ApprovalDecision.APPROVE,
            reason="Reviewed evidence.",
            decided_at=NOW,
        )
        workflow.record_decision("run-001", decision)
        corrupt = True

        with pytest.raises(PendingApprovalError, match="evidence"):
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
            langgraph_store=persistence.langgraph_store,
            approval_store=persistence.store,
            specialists=specialists,
            data_researcher=DataResearcher(),
            model_evaluator=ModelEvaluator(),
            validator=QueuedValidator((True,)),
            risk_reviewer=QueuedRiskReviewer((RiskDecision.APPROVE,)),
            clock=lambda: NOW,
        )
        workflow = WorkflowController(graph=graph, store=persistence.store, clock=lambda: NOW)

        view = workflow.start(task(tmp_path))

    assert view.state.status is RunStatus.USAGE_LIMITED
    assert view.state.correction_count == 0
    assert view.pending_approval is None


def test_completed_product_without_typed_output_fails_closed(tmp_path):
    class MissingOutputSpecialists(QueuedSpecialists):
        def execute(self, request):
            self.calls.append(request)
            return receipt(request.role, request.attempt).model_copy(update={"output": None})

    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        graph = build_workflow(
            checkpointer=persistence.checkpointer,
            langgraph_store=persistence.langgraph_store,
            approval_store=persistence.store,
            specialists=MissingOutputSpecialists(),
            data_researcher=DataResearcher(),
            model_evaluator=ModelEvaluator(),
            validator=QueuedValidator((True,)),
            risk_reviewer=QueuedRiskReviewer((RiskDecision.APPROVE,)),
            clock=lambda: NOW,
        )
        view = WorkflowController(
            graph=graph,
            store=persistence.store,
            clock=lambda: NOW,
        ).start(task(tmp_path))

    assert view.state.status is RunStatus.FAILED
    assert "typed output" in view.state.terminal_reason


@pytest.mark.parametrize(
    "execution_status,expected_status,error_code",
    [
        (ExecutionStatus.USAGE_LIMITED, RunStatus.USAGE_LIMITED, "usage_limit"),
        (ExecutionStatus.TIMEOUT, RunStatus.INTERRUPTED, "timeout"),
        (ExecutionStatus.INTERRUPTED, RunStatus.INTERRUPTED, "ambiguous-prior-execution"),
    ],
)
def test_risk_infrastructure_failure_persists_receipt_and_stops(
    tmp_path,
    execution_status,
    expected_status,
    error_code,
):
    class InfrastructureReviewer:
        def review(self, request, development_receipt, validation, **_research):
            return RiskReviewExecution(
                receipt=SpecialistReceipt(
                    **COMMON,
                    receipt_id=f"risk-{error_code}",
                    role=SpecialistRole.RISK_REVIEW,
                    attempt=development_receipt.attempt,
                    status=execution_status,
                    error_code=error_code,
                )
            )

    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        graph = build_workflow(
            checkpointer=persistence.checkpointer,
            langgraph_store=persistence.langgraph_store,
            approval_store=persistence.store,
            specialists=QueuedSpecialists(),
            data_researcher=DataResearcher(),
            model_evaluator=ModelEvaluator(),
            validator=QueuedValidator((True,)),
            risk_reviewer=InfrastructureReviewer(),
            clock=lambda: NOW,
        )
        view = WorkflowController(
            graph=graph,
            store=persistence.store,
            clock=lambda: NOW,
        ).start(task(tmp_path))

    assert view.state.status is expected_status
    assert view.state.receipts[-1].role is SpecialistRole.RISK_REVIEW
    assert view.state.receipts[-1].status is execution_status
    assert view.pending_approval is None


def test_mismatched_risk_authority_fails_closed_without_approval(tmp_path):
    class MismatchedReviewer(QueuedRiskReviewer):
        def review(self, request, development_receipt, validation, **_research):
            valid = super().review(request, development_receipt, validation, **_research)
            return valid.model_copy(update={"task_id": "different-task"})

    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        specialists = QueuedSpecialists()
        graph = build_workflow(
            checkpointer=persistence.checkpointer,
            langgraph_store=persistence.langgraph_store,
            approval_store=persistence.store,
            specialists=specialists,
            data_researcher=DataResearcher(),
            model_evaluator=ModelEvaluator(),
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
            langgraph_store=persistence.langgraph_store,
            approval_store=persistence.store,
            specialists=MismatchedEvidenceSpecialists(),
            data_researcher=DataResearcher(),
            model_evaluator=ModelEvaluator(),
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
            langgraph_store=persistence.langgraph_store,
            approval_store=persistence.store,
            specialists=QueuedSpecialists(),
            data_researcher=DataResearcher(),
            model_evaluator=ModelEvaluator(),
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
        def review(self, request, development_receipt, validation, **_research):
            valid = super().review(request, development_receipt, validation, **_research)
            foreign = artifact("foreign-risk").model_copy(
                update={"repository_revision": "different-revision"}
            )
            return valid.model_copy(update={"evidence": (foreign,)})

    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        graph = build_workflow(
            checkpointer=persistence.checkpointer,
            langgraph_store=persistence.langgraph_store,
            approval_store=persistence.store,
            specialists=QueuedSpecialists(),
            data_researcher=DataResearcher(),
            model_evaluator=ModelEvaluator(),
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


def test_product_typed_brief_is_injected_into_development(tmp_path):
    class BriefingSpecialists(QueuedSpecialists):
        def execute(self, request):
            self.calls.append(request)
            item = receipt(request.role, request.attempt)
            if request.role is SpecialistRole.PRODUCT:
                output = ProductSpecialistOutput(
                    **COMMON,
                    role=SpecialistRole.PRODUCT,
                    attempt=1,
                    route=SpecialistRole.DEVELOPMENT,
                    summary="Bounded documentation change.",
                    development_instructions="Create only M2-CONTROLLED-EXERCISE.md.",
                    acceptance_checks=("python -m pytest tests/platform",),
                )
                return item.model_copy(update={"output": output})
            return item

    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        specialists = BriefingSpecialists()
        graph = build_workflow(
            checkpointer=persistence.checkpointer,
            langgraph_store=persistence.langgraph_store,
            approval_store=persistence.store,
            specialists=specialists,
            data_researcher=DataResearcher(),
            model_evaluator=ModelEvaluator(),
            validator=QueuedValidator((True,)),
            risk_reviewer=QueuedRiskReviewer((RiskDecision.APPROVE,)),
            workspace_hasher=lambda _workspace: "b" * 64,
            clock=lambda: NOW,
        )
        view = WorkflowController(
            graph=graph,
            store=persistence.store,
            workspace_hasher=lambda _workspace: "b" * 64,
            clock=lambda: NOW,
        ).start(task(tmp_path))

    assert view.state.status is RunStatus.AWAITING_APPROVAL
    assert "Create only M2-CONTROLLED-EXERCISE.md." in specialists.calls[1].instructions


def test_product_acceptance_checks_must_match_controller_checks(tmp_path):
    class MismatchedProductChecks(QueuedSpecialists):
        def execute(self, request):
            self.calls.append(request)
            item = receipt(request.role, request.attempt)
            if request.role is SpecialistRole.PRODUCT:
                output = item.output.model_copy(update={"acceptance_checks": ("offline-test",)})
                return item.model_copy(update={"output": output})
            return item

    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        specialists = MismatchedProductChecks()
        workflow, _, _, _ = controller(persistence, specialist_executor=specialists)
        view = workflow.start(task(tmp_path))

    assert view.state.status is RunStatus.FAILED
    assert view.state.terminal_reason == "Product acceptance checks differ from controller checks"
    assert [call.role for call in specialists.calls] == [SpecialistRole.PRODUCT]


def test_product_receives_explicit_artifact_integrity_scope(tmp_path):
    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        specialists = QueuedSpecialists()
        workflow, _, _, _ = controller(persistence, specialist_executor=specialists)
        workflow.start(task(tmp_path))

    product_instructions = specialists.calls[0].instructions
    assert json.dumps(task(tmp_path).acceptance_checks) in product_instructions
    assert '"evaluation_scope": "artifact-integrity-only"' in product_instructions
    assert '"integrity_passed": true' in product_instructions
    assert '"evaluation_passed"' not in product_instructions


def test_risk_execution_receipt_is_persisted_in_graph_state(tmp_path):
    class ReceiptReviewer(QueuedRiskReviewer):
        def review(self, request, development_receipt, validation, **_research):
            decision = super().review(request, development_receipt, validation, **_research)
            return RiskReviewExecution(
                receipt=receipt(SpecialistRole.RISK_REVIEW, development_receipt.attempt),
                decision=decision.model_copy(
                    update={
                        "scope_compliant": True,
                        "evidence_owned": True,
                        "prohibited_actions_compliant": True,
                    }
                ),
            )

    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        graph = build_workflow(
            checkpointer=persistence.checkpointer,
            langgraph_store=persistence.langgraph_store,
            approval_store=persistence.store,
            specialists=QueuedSpecialists(),
            data_researcher=DataResearcher(),
            model_evaluator=ModelEvaluator(),
            validator=QueuedValidator((True,)),
            risk_reviewer=ReceiptReviewer((RiskDecision.APPROVE,)),
            workspace_hasher=lambda _workspace: "b" * 64,
            clock=lambda: NOW,
        )
        view = WorkflowController(
            graph=graph,
            store=persistence.store,
            workspace_hasher=lambda _workspace: "b" * 64,
            clock=lambda: NOW,
        ).start(task(tmp_path))

    assert view.state.status is RunStatus.AWAITING_APPROVAL
    assert [item.role for item in view.state.receipts] == [
        SpecialistRole.PRODUCT,
        SpecialistRole.DEVELOPMENT,
        SpecialistRole.RISK_REVIEW,
    ]


@pytest.mark.parametrize(
    "decision,compliance",
    [
        (RiskDecision.HOLD, True),
        (RiskDecision.APPROVE, False),
    ],
)
def test_risk_hold_or_failed_compliance_requires_operator_intervention(
    tmp_path,
    decision,
    compliance,
):
    class FailClosedReviewer(QueuedRiskReviewer):
        def review(self, request, development_receipt, validation, **_research):
            result = super().review(request, development_receipt, validation, **_research)
            return result.model_copy(
                update={
                    "decision": decision,
                    "scope_compliant": compliance,
                    "evidence_owned": compliance,
                    "prohibited_actions_compliant": compliance,
                }
            )

    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        graph = build_workflow(
            checkpointer=persistence.checkpointer,
            langgraph_store=persistence.langgraph_store,
            approval_store=persistence.store,
            specialists=QueuedSpecialists(),
            data_researcher=DataResearcher(),
            model_evaluator=ModelEvaluator(),
            validator=QueuedValidator((True,)),
            risk_reviewer=FailClosedReviewer((decision,)),
            clock=lambda: NOW,
        )
        view = WorkflowController(
            graph=graph,
            store=persistence.store,
            clock=lambda: NOW,
        ).start(task(tmp_path))

    assert view.state.status is RunStatus.OPERATOR_INTERVENTION
    assert view.pending_approval is None


def test_legacy_risk_approval_without_compliance_gates_cannot_reach_approval(tmp_path):
    class LegacyReviewer(QueuedRiskReviewer):
        def review(self, request, development_receipt, validation, **_research):
            result = super().review(request, development_receipt, validation, **_research)
            return result.model_copy(
                update={
                    "scope_compliant": None,
                    "evidence_owned": None,
                    "prohibited_actions_compliant": None,
                }
            )

    with open_persistence(PlatformPaths.below(tmp_path / "platform")) as persistence:
        graph = build_workflow(
            checkpointer=persistence.checkpointer,
            langgraph_store=persistence.langgraph_store,
            approval_store=persistence.store,
            specialists=QueuedSpecialists(),
            data_researcher=DataResearcher(),
            model_evaluator=ModelEvaluator(),
            validator=QueuedValidator((True,)),
            risk_reviewer=LegacyReviewer((RiskDecision.APPROVE,)),
            clock=lambda: NOW,
        )
        view = WorkflowController(
            graph=graph,
            store=persistence.store,
            clock=lambda: NOW,
        ).start(task(tmp_path))

    assert view.state.status is RunStatus.OPERATOR_INTERVENTION
    assert view.pending_approval is None
