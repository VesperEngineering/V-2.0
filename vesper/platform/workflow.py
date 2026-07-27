"""First native Product/Development/Validation/Risk LangGraph workflow."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping, Protocol, TypedDict

from .contracts import (
    ApprovalDecision,
    CorrectionAttempt,
    EvidenceArtifactRef,
    ExecutionStatus,
    GraphState,
    HumanApprovalDecision,
    HumanApprovalRequest,
    PermissionSet,
    RiskDecision,
    RiskReviewDecision,
    RunStatus,
    SandboxMode,
    SpecialistInput,
    SpecialistReceipt,
    SpecialistRole,
    TaskRequest,
    ValidationResult,
)
from .runtime_env import enforce_offline_runtime_environment

enforce_offline_runtime_environment()

from langgraph.graph import END, START, StateGraph  # noqa: E402
from langgraph.types import Command, interrupt  # noqa: E402

APPROVAL_REQUEST_NAMESPACE = ("system", "approval-requests")
APPROVAL_DECISION_NAMESPACE = ("system", "approval-decisions")


class WorkflowError(RuntimeError):
    """Base error for local workflow lifecycle failures."""


class RunNotFoundError(WorkflowError):
    """No checkpoint exists for the requested run."""


class PendingApprovalError(WorkflowError):
    """A run is not ready to resume with a valid persisted decision."""


class SpecialistExecutor(Protocol):
    def execute(self, request: SpecialistInput) -> SpecialistReceipt: ...


class DeterministicValidator(Protocol):
    def validate(
        self,
        request: TaskRequest,
        development_receipt: SpecialistReceipt,
    ) -> ValidationResult: ...


class RiskReviewer(Protocol):
    def review(
        self,
        request: TaskRequest,
        development_receipt: SpecialistReceipt,
        validation: ValidationResult,
    ) -> RiskReviewDecision: ...


class StorePort(Protocol):
    def put(self, namespace: tuple[str, ...], key: str, value: Mapping[str, object]) -> None: ...

    def get(self, namespace: tuple[str, ...], key: str) -> Mapping[str, object] | None: ...


class WorkflowRuntimeState(TypedDict, total=False):
    task: dict[str, object]
    status: str
    current_role: str | None
    correction_attempts: list[dict[str, object]]
    validation: dict[str, object] | None
    risk_review: dict[str, object] | None
    approval: dict[str, object] | None
    receipts: list[dict[str, object]]
    feedback: str | None
    terminal_reason: str | None


@dataclass(frozen=True, slots=True)
class WorkflowView:
    state: GraphState
    checkpoint_id: str
    next_nodes: tuple[str, ...]
    pending_approval: HumanApprovalRequest | None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(model_type, value):
    return model_type.model_validate_json(json.dumps(value))


def _dump(model) -> dict[str, object]:
    return model.model_dump(mode="json")


def _infrastructure_status(receipt: SpecialistReceipt) -> tuple[RunStatus, str]:
    if receipt.status is ExecutionStatus.USAGE_LIMITED:
        return RunStatus.USAGE_LIMITED, "specialist usage limit"
    if receipt.status is ExecutionStatus.CANCELLED:
        return RunStatus.CANCELLED, "specialist execution cancelled"
    if receipt.status is ExecutionStatus.TIMEOUT:
        return RunStatus.INTERRUPTED, "specialist execution timed out"
    return RunStatus.FAILED, f"specialist execution ended with {receipt.status.value}"


def _authority_matches(request: TaskRequest, record, *, attempt: int | None = None) -> bool:
    if (
        record.run_id != request.run_id
        or record.task_id != request.task_id
        or record.repository_revision != request.repository_revision
    ):
        return False
    if attempt is not None and record.attempt != attempt:
        return False
    return all(_evidence_authority_matches(request, item) for item in _record_evidence(record))


def _record_evidence(record) -> tuple[EvidenceArtifactRef, ...]:
    if isinstance(record, ValidationResult):
        return tuple(item for check in record.checks for item in check.evidence)
    evidence = getattr(record, "evidence", ())
    return tuple(evidence)


def _evidence_authority_matches(
    request: TaskRequest,
    evidence: EvidenceArtifactRef,
) -> bool:
    return (
        evidence.run_id == request.run_id
        and evidence.task_id == request.task_id
        and evidence.repository_revision == request.repository_revision
    )


def build_workflow(
    *,
    checkpointer,
    store,
    specialists: SpecialistExecutor,
    validator: DeterministicValidator,
    risk_reviewer: RiskReviewer,
    clock: Callable[[], datetime] = _utc_now,
):
    """Compile the first bounded native workflow against local persistence."""

    def product_node(state: WorkflowRuntimeState) -> dict[str, object]:
        request = _parse(TaskRequest, state["task"])
        specialist_input = SpecialistInput(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=request.created_at,
            role=SpecialistRole.PRODUCT,
            attempt=1,
            instructions=f"Produce a bounded development brief for: {request.objective}",
            workspace=request.repository_root,
            memory_namespace=("profiles", "v20-product", "product-decisions"),
            permissions=PermissionSet(
                sandbox=SandboxMode.READ_ONLY,
                read_paths=(request.repository_root,),
                allowed_tools=("read", "search"),
            ),
        )
        receipt = specialists.execute(specialist_input)
        if (
            not _authority_matches(request, receipt, attempt=1)
            or receipt.role is not SpecialistRole.PRODUCT
        ):
            return {
                "status": RunStatus.FAILED.value,
                "current_role": None,
                "receipts": state.get("receipts", []),
                "terminal_reason": "Product receipt authority mismatch",
            }
        receipts = [*state.get("receipts", []), _dump(receipt)]
        if receipt.status is not ExecutionStatus.COMPLETED:
            status, reason = _infrastructure_status(receipt)
            return {
                "status": status.value,
                "current_role": None,
                "receipts": receipts,
                "terminal_reason": reason,
            }
        return {
            "status": RunStatus.DEVELOPMENT.value,
            "current_role": SpecialistRole.DEVELOPMENT.value,
            "receipts": receipts,
        }

    def development_node(state: WorkflowRuntimeState) -> dict[str, object]:
        request = _parse(TaskRequest, state["task"])
        attempt = len(state.get("correction_attempts", [])) + 1
        feedback = state.get("feedback")
        instructions = f"Implement the bounded objective: {request.objective}"
        if feedback:
            instructions += f"\nCorrect this authoritative feedback: {feedback}"
        specialist_input = SpecialistInput(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=request.created_at,
            role=SpecialistRole.DEVELOPMENT,
            attempt=attempt,
            instructions=instructions,
            workspace=request.repository_root,
            memory_namespace=("profiles", "v20-development", "development-episodes"),
            permissions=PermissionSet(
                sandbox=SandboxMode.WORKSPACE_WRITE,
                read_paths=(request.repository_root,),
                write_paths=(request.repository_root,),
                allowed_tools=("read", "search", "write", "test"),
            ),
        )
        receipt = specialists.execute(specialist_input)
        if (
            not _authority_matches(request, receipt, attempt=attempt)
            or receipt.role is not SpecialistRole.DEVELOPMENT
        ):
            return {
                "status": RunStatus.FAILED.value,
                "current_role": None,
                "receipts": state.get("receipts", []),
                "terminal_reason": "Development receipt authority mismatch",
            }
        receipts = [*state.get("receipts", []), _dump(receipt)]
        if receipt.status is not ExecutionStatus.COMPLETED:
            status, reason = _infrastructure_status(receipt)
            return {
                "status": status.value,
                "current_role": None,
                "receipts": receipts,
                "terminal_reason": reason,
            }
        return {
            "status": RunStatus.VALIDATION.value,
            "current_role": None,
            "receipts": receipts,
            "feedback": None,
        }

    def validation_node(state: WorkflowRuntimeState) -> dict[str, object]:
        request = _parse(TaskRequest, state["task"])
        development_receipt = _latest_development_receipt(state)
        result = validator.validate(request, development_receipt)
        if not _authority_matches(request, result, attempt=development_receipt.attempt):
            return {
                "status": RunStatus.FAILED.value,
                "current_role": None,
                "terminal_reason": "validation authority mismatch",
            }
        if result.passed:
            return {
                "status": RunStatus.RISK_REVIEW.value,
                "current_role": SpecialistRole.RISK_REVIEW.value,
                "validation": _dump(result),
            }
        failed_checks = ", ".join(check.name for check in result.checks if not check.passed)
        correction = CorrectionAttempt(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=clock(),
            attempt=development_receipt.attempt,
            source="validation",
            reason=f"Deterministic validation failed: {failed_checks}",
            evidence=tuple(item for check in result.checks for item in check.evidence),
        )
        corrections = [*state.get("correction_attempts", []), _dump(correction)]
        if len(corrections) >= 3:
            return {
                "status": RunStatus.OPERATOR_INTERVENTION.value,
                "current_role": None,
                "validation": _dump(result),
                "correction_attempts": corrections,
                "terminal_reason": "three correction attempts failed",
            }
        return {
            "status": RunStatus.DEVELOPMENT.value,
            "current_role": SpecialistRole.DEVELOPMENT.value,
            "validation": _dump(result),
            "correction_attempts": corrections,
            "feedback": correction.reason,
        }

    def risk_review_node(state: WorkflowRuntimeState) -> dict[str, object]:
        request = _parse(TaskRequest, state["task"])
        development_receipt = _latest_development_receipt(state)
        validation = _parse(ValidationResult, state["validation"])
        decision = risk_reviewer.review(request, development_receipt, validation)
        if not _authority_matches(request, decision, attempt=development_receipt.attempt):
            return {
                "status": RunStatus.FAILED.value,
                "current_role": None,
                "terminal_reason": "Risk Review authority mismatch",
            }
        if decision.decision is RiskDecision.APPROVE:
            return {
                "status": RunStatus.AWAITING_APPROVAL.value,
                "current_role": None,
                "risk_review": _dump(decision),
                "feedback": None,
            }
        correction = CorrectionAttempt(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=clock(),
            attempt=development_receipt.attempt,
            source="risk-review",
            reason=f"Risk Review rejected the attempt: {decision.rationale}",
            evidence=decision.evidence,
        )
        corrections = [*state.get("correction_attempts", []), _dump(correction)]
        if len(corrections) >= 3:
            return {
                "status": RunStatus.OPERATOR_INTERVENTION.value,
                "current_role": None,
                "risk_review": _dump(decision),
                "correction_attempts": corrections,
                "terminal_reason": "three correction attempts failed",
            }
        return {
            "status": RunStatus.DEVELOPMENT.value,
            "current_role": SpecialistRole.DEVELOPMENT.value,
            "risk_review": _dump(decision),
            "correction_attempts": corrections,
            "feedback": correction.reason,
        }

    def human_approval_node(state: WorkflowRuntimeState) -> dict[str, object]:
        request = _parse(TaskRequest, state["task"])
        risk_review = _parse(RiskReviewDecision, state["risk_review"])
        request_id = f"approval:{request.run_id}:{risk_review.attempt}"
        response = interrupt(
            {
                "request_id": request_id,
                "run_id": request.run_id,
                "task_id": request.task_id,
                "summary": "Risk Review approved; explicit operator decision required.",
            }
        )
        decision = _parse(HumanApprovalDecision, response)
        persisted_item = store.get(APPROVAL_DECISION_NAMESPACE, request.run_id)
        if persisted_item is None:
            raise PendingApprovalError("no persisted operator decision exists")
        persisted_decision = _parse(HumanApprovalDecision, persisted_item.value)
        if decision != persisted_decision or decision.request_id != request_id:
            raise PendingApprovalError(
                "resume payload does not match the persisted operator decision"
            )
        if (
            decision.run_id != request.run_id
            or decision.task_id != request.task_id
            or decision.repository_revision != request.repository_revision
        ):
            raise PendingApprovalError("operator decision authority fields do not match the run")
        status = (
            RunStatus.ACCEPTED
            if decision.decision is ApprovalDecision.APPROVE
            else RunStatus.REJECTED
        )
        return {
            "status": status.value,
            "approval": _dump(decision),
            "terminal_reason": None if status is RunStatus.ACCEPTED else decision.reason,
        }

    builder = StateGraph(WorkflowRuntimeState)
    builder.add_node("product", product_node)
    builder.add_node("development", development_node)
    builder.add_node("validation", validation_node)
    builder.add_node("risk_review", risk_review_node)
    builder.add_node("human_approval", human_approval_node)
    builder.add_edge(START, "product")
    builder.add_conditional_edges(
        "product",
        lambda state: "development" if state["status"] == RunStatus.DEVELOPMENT.value else "end",
        {"development": "development", "end": END},
    )
    builder.add_conditional_edges(
        "development",
        lambda state: "validation" if state["status"] == RunStatus.VALIDATION.value else "end",
        {"validation": "validation", "end": END},
    )
    builder.add_conditional_edges(
        "validation",
        lambda state: {
            RunStatus.DEVELOPMENT.value: "development",
            RunStatus.RISK_REVIEW.value: "risk_review",
        }.get(state["status"], "end"),
        {"development": "development", "risk_review": "risk_review", "end": END},
    )
    builder.add_conditional_edges(
        "risk_review",
        lambda state: {
            RunStatus.DEVELOPMENT.value: "development",
            RunStatus.AWAITING_APPROVAL.value: "human_approval",
        }.get(state["status"], "end"),
        {"development": "development", "human_approval": "human_approval", "end": END},
    )
    builder.add_edge("human_approval", END)
    return builder.compile(checkpointer=checkpointer, store=store)


def _latest_development_receipt(state: WorkflowRuntimeState) -> SpecialistReceipt:
    for raw in reversed(state.get("receipts", [])):
        receipt = _parse(SpecialistReceipt, raw)
        if receipt.role is SpecialistRole.DEVELOPMENT:
            return receipt
    raise WorkflowError("workflow has no Development receipt")


class WorkflowController:
    def __init__(
        self,
        *,
        graph,
        store: StorePort,
        clock: Callable[[], datetime] = _utc_now,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self.graph = graph
        self.store = store
        self.clock = clock
        self.id_factory = id_factory

    def start(self, task: TaskRequest) -> WorkflowView:
        initial: WorkflowRuntimeState = {
            "task": _dump(task),
            "status": RunStatus.PRODUCT.value,
            "current_role": SpecialistRole.PRODUCT.value,
            "correction_attempts": [],
            "validation": None,
            "risk_review": None,
            "approval": None,
            "receipts": [],
            "feedback": None,
            "terminal_reason": None,
        }
        self.graph.invoke(initial, self._config(task.run_id))
        return self.inspect(task.run_id)

    def snapshot(self, run_id: str):
        snapshot = self.graph.get_state(self._config(run_id))
        if not snapshot.values:
            raise RunNotFoundError(f"run not found: {run_id}")
        return snapshot

    def inspect(self, run_id: str) -> WorkflowView:
        snapshot = self.snapshot(run_id)
        checkpoint_id = str(snapshot.config["configurable"]["checkpoint_id"])
        pending = self._ensure_approval_request(snapshot, checkpoint_id)
        state = self._state_contract(snapshot.values, pending)
        return WorkflowView(
            state=state,
            checkpoint_id=checkpoint_id,
            next_nodes=tuple(snapshot.next),
            pending_approval=pending,
        )

    def record_decision(
        self,
        run_id: str,
        decision: HumanApprovalDecision,
    ) -> HumanApprovalDecision:
        view = self.inspect(run_id)
        request = view.pending_approval
        if request is None or view.state.status is not RunStatus.AWAITING_APPROVAL:
            raise PendingApprovalError("run is not awaiting operator approval")
        if (
            decision.run_id != run_id
            or decision.task_id != request.task_id
            or decision.repository_revision != request.repository_revision
            or decision.request_id != request.request_id
            or decision.checkpoint_id != view.checkpoint_id
        ):
            raise PendingApprovalError("decision is stale or does not match the approval request")
        self.store.put(APPROVAL_DECISION_NAMESPACE, run_id, _dump(decision))
        return decision

    def resume(self, run_id: str) -> WorkflowView:
        view = self.inspect(run_id)
        if view.state.status is not RunStatus.AWAITING_APPROVAL or view.pending_approval is None:
            raise PendingApprovalError("run is not awaiting operator approval")
        raw = self.store.get(APPROVAL_DECISION_NAMESPACE, run_id)
        if raw is None:
            raise PendingApprovalError("no persisted operator decision exists")
        decision = _parse(HumanApprovalDecision, raw)
        if (
            decision.request_id != view.pending_approval.request_id
            or decision.checkpoint_id != view.checkpoint_id
        ):
            raise PendingApprovalError("persisted operator decision is stale")
        self.graph.invoke(Command(resume=_dump(decision)), self._config(run_id))
        return self.inspect(run_id)

    def cancel(self, run_id: str, reason: str) -> WorkflowView:
        view = self.inspect(run_id)
        if view.state.status in {
            RunStatus.ACCEPTED,
            RunStatus.REJECTED,
            RunStatus.CANCELLED,
            RunStatus.OPERATOR_INTERVENTION,
        }:
            return view
        self.graph.update_state(
            self._config(run_id),
            {"status": RunStatus.CANCELLED.value, "terminal_reason": reason},
        )
        return self.inspect(run_id)

    def _ensure_approval_request(self, snapshot, checkpoint_id: str):
        if (
            snapshot.values.get("status") != RunStatus.AWAITING_APPROVAL.value
            or tuple(snapshot.next) != ("human_approval",)
            or not snapshot.tasks
            or not snapshot.tasks[0].interrupts
        ):
            return None
        raw = self.store.get(APPROVAL_REQUEST_NAMESPACE, snapshot.values["task"]["run_id"])
        if raw is not None:
            persisted = _parse(HumanApprovalRequest, raw)
            if persisted.checkpoint_id != checkpoint_id:
                raise PendingApprovalError("persisted approval request is stale")
            return persisted
        interrupts = snapshot.tasks[0].interrupts
        payload = interrupts[0].value
        request = _parse(TaskRequest, snapshot.values["task"])
        risk_review = _parse(RiskReviewDecision, snapshot.values["risk_review"])
        approval_request = HumanApprovalRequest(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=self.clock(),
            request_id=str(payload["request_id"]),
            checkpoint_id=checkpoint_id,
            summary=str(payload["summary"]),
            evidence=risk_review.evidence,
        )
        self.store.put(APPROVAL_REQUEST_NAMESPACE, request.run_id, _dump(approval_request))
        return approval_request

    @staticmethod
    def _config(run_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": run_id}}

    @staticmethod
    def _state_contract(
        values: Mapping[str, object],
        pending: HumanApprovalRequest | None,
    ) -> GraphState:
        task = _parse(TaskRequest, values["task"])
        payload = {
            "schema_version": "1.0",
            "run_id": task.run_id,
            "task_id": task.task_id,
            "repository_revision": task.repository_revision,
            "created_at": task.created_at.isoformat().replace("+00:00", "Z"),
            "task": values["task"],
            "status": values["status"],
            "current_role": values.get("current_role"),
            "correction_attempts": values.get("correction_attempts", []),
            "validation": values.get("validation"),
            "risk_review": values.get("risk_review"),
            "approval_request": None if pending is None else _dump(pending),
            "approval": values.get("approval"),
            "receipts": values.get("receipts", []),
            "terminal_reason": values.get("terminal_reason"),
        }
        return GraphState.model_validate_json(json.dumps(payload))
