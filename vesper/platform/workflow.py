"""Native research, model, Product, Development, Validation, and Risk workflow."""

from __future__ import annotations

import json
import hashlib
import os
import stat
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Protocol, TypedDict

from .contracts import (
    ApprovalDecision,
    CorrectionAttempt,
    DataResearchResult,
    DevelopmentSpecialistOutput,
    EvidenceArtifactRef,
    ExecutionStatus,
    GraphState,
    HumanApprovalDecision,
    HumanApprovalRequest,
    ModelEvaluationResult,
    PermissionSet,
    ProductSpecialistOutput,
    RiskDecision,
    RiskReviewDecision,
    RiskReviewExecution,
    RunStatus,
    SandboxMode,
    SpecialistInput,
    SpecialistReceipt,
    SpecialistRole,
    TaskRequest,
    ValidationResult,
)
from .memory import DeterministicMemoryCandidateValidator, MemoryService
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
        *,
        data_research: DataResearchResult,
        model_evaluation: ModelEvaluationResult,
    ) -> RiskReviewDecision | RiskReviewExecution: ...


class DataResearcher(Protocol):
    def research(self, request: TaskRequest) -> DataResearchResult: ...


class ModelEvaluator(Protocol):
    def evaluate(self, request: TaskRequest) -> ModelEvaluationResult: ...


class StorePort(Protocol):
    def put(self, namespace: tuple[str, ...], key: str, value: Mapping[str, object]) -> None: ...

    def get(self, namespace: tuple[str, ...], key: str) -> Mapping[str, object] | None: ...


class WorkflowRuntimeState(TypedDict, total=False):
    task: dict[str, object]
    status: str
    current_role: str | None
    data_research: dict[str, object] | None
    model_evaluation: dict[str, object] | None
    product_output: dict[str, object] | None
    correction_attempts: list[dict[str, object]]
    validation: dict[str, object] | None
    risk_review: dict[str, object] | None
    reviewed_workspace_sha256: str | None
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
    if receipt.status is ExecutionStatus.INTERRUPTED:
        return RunStatus.INTERRUPTED, "specialist execution outcome is ambiguous after interruption"
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


def _workspace_sha256(workspace: Path) -> str:
    root = workspace.resolve()
    if not root.is_dir():
        raise PendingApprovalError("approval workspace is unavailable")
    digest = hashlib.sha256()
    for current, directories, files in os.walk(root, followlinks=False):
        directory = Path(current)
        if directory == root:
            directories[:] = [name for name in directories if name not in {".git", ".state"}]
        directories.sort()
        files.sort()
        for name in (*directories, *files):
            path = directory / name
            metadata = path.lstat()
            reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
            if stat.S_ISLNK(metadata.st_mode) or bool(
                getattr(metadata, "st_file_attributes", 0) & reparse
            ):
                raise PendingApprovalError("approval workspace contains a link or junction")
            relative = path.relative_to(root).as_posix().encode("utf-8")
            digest.update(len(relative).to_bytes(8, "big"))
            digest.update(relative)
            if path.is_dir():
                digest.update(b"directory\0")
            elif path.is_file():
                body = path.read_bytes()
                digest.update(b"file\0")
                digest.update(len(body).to_bytes(8, "big"))
                digest.update(body)
            else:
                raise PendingApprovalError("approval workspace contains an unsupported path")
    return digest.hexdigest()


def _approval_evidence(state: Mapping[str, object]) -> tuple[EvidenceArtifactRef, ...]:
    artifacts = []
    raw_data_research = state.get("data_research")
    if raw_data_research is not None:
        artifacts.extend(_parse(DataResearchResult, raw_data_research).evidence)
    raw_model_evaluation = state.get("model_evaluation")
    if raw_model_evaluation is not None:
        artifacts.extend(_parse(ModelEvaluationResult, raw_model_evaluation).evidence)
    for raw in state.get("receipts", []):
        artifacts.extend(_parse(SpecialistReceipt, raw).evidence)
    raw_validation = state.get("validation")
    if raw_validation is not None:
        validation = _parse(ValidationResult, raw_validation)
        artifacts.extend(item for check in validation.checks for item in check.evidence)
    raw_risk = state.get("risk_review")
    if raw_risk is not None:
        artifacts.extend(_parse(RiskReviewDecision, raw_risk).evidence)
    return tuple(
        {(artifact.relative_path, artifact.sha256): artifact for artifact in artifacts}.values()
    )


def _research_summary(
    data_research: DataResearchResult,
    model_evaluation: ModelEvaluationResult,
) -> dict[str, object]:
    return {
        "data": {
            "available": data_research.available,
            "row_count": data_research.row_count,
            "ticker_count": data_research.ticker_count,
            "start_date": data_research.start_date,
            "end_date": data_research.end_date,
            "null_price_rows": data_research.null_price_rows,
            "invalid_date_rows": data_research.invalid_date_rows,
            "split_adjustments_verified": data_research.split_adjustments_sha256 is not None,
            "warnings": data_research.warnings,
        },
        "model": {
            "available": model_evaluation.available,
            "hash_matches": model_evaluation.hash_matches,
            "label_horizon": model_evaluation.label_horizon,
            "train_ic": model_evaluation.train_ic,
            "out_of_sample_ic": model_evaluation.out_of_sample_ic,
            "train_samples": model_evaluation.train_samples,
            "test_samples": model_evaluation.test_samples,
            "evaluation_passed": model_evaluation.evaluation_passed,
            "warnings": model_evaluation.warnings,
        },
    }


def build_workflow(
    *,
    checkpointer,
    store,
    specialists: SpecialistExecutor,
    data_researcher: DataResearcher,
    model_evaluator: ModelEvaluator,
    validator: DeterministicValidator,
    risk_reviewer: RiskReviewer,
    memory_service: MemoryService | None = None,
    memory_validator: DeterministicMemoryCandidateValidator | None = None,
    workspace_hasher: Callable[[Path], str] = _workspace_sha256,
    evidence_reader: Callable[[EvidenceArtifactRef], bytes] | None = None,
    clock: Callable[[], datetime] = _utc_now,
):
    """Compile the first bounded native workflow against local persistence."""

    def data_research_node(state: WorkflowRuntimeState) -> dict[str, object]:
        request = _parse(TaskRequest, state["task"])
        result = data_researcher.research(request)
        if not _authority_matches(request, result):
            return {
                "status": RunStatus.FAILED.value,
                "current_role": None,
                "terminal_reason": "Data Research authority mismatch",
            }
        return {
            "status": RunStatus.MODEL_EVALUATION.value,
            "current_role": None,
            "data_research": _dump(result),
        }

    def model_evaluation_node(state: WorkflowRuntimeState) -> dict[str, object]:
        request = _parse(TaskRequest, state["task"])
        data_research = _parse(DataResearchResult, state["data_research"])
        result = model_evaluator.evaluate(request)
        if not _authority_matches(request, result):
            return {
                "status": RunStatus.FAILED.value,
                "current_role": None,
                "terminal_reason": "Model Evaluation authority mismatch",
            }
        if not data_research.available or not result.evaluation_passed:
            reasons = [
                *data_research.warnings,
                *result.warnings,
            ]
            return {
                "status": RunStatus.OPERATOR_INTERVENTION.value,
                "current_role": None,
                "model_evaluation": _dump(result),
                "terminal_reason": ("Research readiness gate failed: " + "; ".join(reasons)),
            }
        return {
            "status": RunStatus.PRODUCT.value,
            "current_role": SpecialistRole.PRODUCT.value,
            "model_evaluation": _dump(result),
        }

    def product_node(state: WorkflowRuntimeState) -> dict[str, object]:
        request = _parse(TaskRequest, state["task"])
        data_research = _parse(DataResearchResult, state["data_research"])
        model_evaluation = _parse(ModelEvaluationResult, state["model_evaluation"])
        if (
            not _authority_matches(request, data_research)
            or not _authority_matches(request, model_evaluation)
            or not data_research.available
            or not model_evaluation.evaluation_passed
        ):
            return {
                "status": RunStatus.OPERATOR_INTERVENTION.value,
                "current_role": None,
                "terminal_reason": "Research readiness gate failed before Product.",
            }
        if evidence_reader is not None:
            try:
                for artifact in (*data_research.evidence, *model_evaluation.evidence):
                    evidence_reader(artifact)
            except Exception:
                return {
                    "status": RunStatus.OPERATOR_INTERVENTION.value,
                    "current_role": None,
                    "terminal_reason": "Research evidence integrity gate failed before Product.",
                }
        research_context = _research_summary(data_research, model_evaluation)
        specialist_input = SpecialistInput(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=request.created_at,
            role=SpecialistRole.PRODUCT,
            attempt=1,
            instructions=(
                f"Produce a bounded development brief for: {request.objective}\n"
                "Controller-owned read-only research context:\n"
                + json.dumps(research_context, sort_keys=True)
            ),
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
        if not isinstance(receipt.output, ProductSpecialistOutput):
            return {
                "status": RunStatus.FAILED.value,
                "current_role": None,
                "receipts": receipts,
                "terminal_reason": "completed Product execution omitted typed output",
            }
        _commit_receipt_memories(memory_service, memory_validator, receipt)
        product_output = receipt.output
        return {
            "status": RunStatus.DEVELOPMENT.value,
            "current_role": SpecialistRole.DEVELOPMENT.value,
            "receipts": receipts,
            "product_output": None if product_output is None else _dump(product_output),
        }

    def development_node(state: WorkflowRuntimeState) -> dict[str, object]:
        request = _parse(TaskRequest, state["task"])
        attempt = len(state.get("correction_attempts", [])) + 1
        feedback = state.get("feedback")
        raw_product_output = state.get("product_output")
        product_output = (
            None
            if raw_product_output is None
            else _parse(ProductSpecialistOutput, raw_product_output)
        )
        instructions = (
            f"Implement the bounded objective: {request.objective}"
            if product_output is None
            else product_output.development_instructions
        )
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
        if not isinstance(receipt.output, DevelopmentSpecialistOutput):
            return {
                "status": RunStatus.FAILED.value,
                "current_role": None,
                "receipts": receipts,
                "terminal_reason": "completed Development execution omitted typed output",
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
            _commit_receipt_memories(
                memory_service,
                memory_validator,
                development_receipt,
                validation=result,
            )
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
        data_research = _parse(DataResearchResult, state["data_research"])
        model_evaluation = _parse(ModelEvaluationResult, state["model_evaluation"])
        review = risk_reviewer.review(
            request,
            development_receipt,
            validation,
            data_research=data_research,
            model_evaluation=model_evaluation,
        )
        if isinstance(review, RiskReviewExecution):
            risk_receipt = review.receipt
            if (
                not _authority_matches(
                    request,
                    risk_receipt,
                    attempt=development_receipt.attempt,
                )
                or risk_receipt.role is not SpecialistRole.RISK_REVIEW
            ):
                return {
                    "status": RunStatus.FAILED.value,
                    "current_role": None,
                    "terminal_reason": "Risk Review receipt authority mismatch",
                }
            receipts = [*state.get("receipts", []), _dump(risk_receipt)]
            if risk_receipt.status is not ExecutionStatus.COMPLETED:
                status, reason = _infrastructure_status(risk_receipt)
                return {
                    "status": status.value,
                    "current_role": None,
                    "receipts": receipts,
                    "terminal_reason": reason,
                }
            decision = review.decision
            if decision is None:
                return {
                    "status": RunStatus.FAILED.value,
                    "current_role": None,
                    "receipts": receipts,
                    "terminal_reason": "completed Risk Review execution omitted its decision",
                }
        else:
            receipts = state.get("receipts", [])
            decision = review
        if not _authority_matches(request, decision, attempt=development_receipt.attempt):
            return {
                "status": RunStatus.FAILED.value,
                "current_role": None,
                "receipts": receipts,
                "terminal_reason": "Risk Review authority mismatch",
            }
        if isinstance(review, RiskReviewExecution):
            _commit_receipt_memories(
                memory_service,
                memory_validator,
                review.receipt,
                risk_decision=decision,
            )
        if decision.decision is RiskDecision.HOLD:
            return {
                "status": RunStatus.OPERATOR_INTERVENTION.value,
                "current_role": None,
                "receipts": receipts,
                "risk_review": _dump(decision),
                "terminal_reason": f"Risk Review hold: {decision.rationale}",
            }
        if decision.decision is RiskDecision.APPROVE:
            compliance = (
                decision.scope_compliant,
                decision.evidence_owned,
                decision.prohibited_actions_compliant,
            )
            if not all(item is True for item in compliance):
                return {
                    "status": RunStatus.OPERATOR_INTERVENTION.value,
                    "current_role": None,
                    "receipts": receipts,
                    "risk_review": _dump(decision),
                    "terminal_reason": "Risk Review approval failed mandatory compliance checks",
                }
            return {
                "status": RunStatus.AWAITING_APPROVAL.value,
                "current_role": None,
                "receipts": receipts,
                "risk_review": _dump(decision),
                "reviewed_workspace_sha256": workspace_hasher(Path(request.repository_root)),
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
            "receipts": receipts,
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
        persisted_request_item = store.get(APPROVAL_REQUEST_NAMESPACE, request.run_id)
        if persisted_request_item is None:
            raise PendingApprovalError("no persisted approval request exists")
        approval_request = _parse(HumanApprovalRequest, persisted_request_item.value)
        if decision.decision is ApprovalDecision.APPROVE:
            if workspace_hasher(Path(request.repository_root)) != approval_request.workspace_sha256:
                raise PendingApprovalError("approval workspace changed after Risk Review")
            if evidence_reader is not None:
                for artifact in approval_request.evidence:
                    evidence_reader(artifact)
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
    builder.add_node("data_research", data_research_node)
    builder.add_node("model_evaluation", model_evaluation_node)
    builder.add_node("product", product_node)
    builder.add_node("development", development_node)
    builder.add_node("validation", validation_node)
    builder.add_node("risk_review", risk_review_node)
    builder.add_node("human_approval", human_approval_node)
    builder.add_edge(START, "data_research")
    builder.add_conditional_edges(
        "data_research",
        lambda state: (
            "model_evaluation" if state["status"] == RunStatus.MODEL_EVALUATION.value else "end"
        ),
        {"model_evaluation": "model_evaluation", "end": END},
    )
    builder.add_conditional_edges(
        "model_evaluation",
        lambda state: "product" if state["status"] == RunStatus.PRODUCT.value else "end",
        {"product": "product", "end": END},
    )
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


def _commit_receipt_memories(
    memory_service: MemoryService | None,
    memory_validator: DeterministicMemoryCandidateValidator | None,
    receipt: SpecialistReceipt,
    *,
    validation: ValidationResult | None = None,
    risk_decision: RiskReviewDecision | None = None,
) -> None:
    if memory_service is None or memory_validator is None:
        return
    for candidate in receipt.memory_candidates:
        if memory_validator.accepts(
            receipt,
            candidate,
            validation=validation,
            risk_decision=risk_decision,
        ):
            memory_service.commit(receipt.role, candidate, validated=True)


class WorkflowController:
    def __init__(
        self,
        *,
        graph,
        store: StorePort,
        workspace_hasher: Callable[[Path], str] = _workspace_sha256,
        evidence_reader: Callable[[EvidenceArtifactRef], bytes] | None = None,
        clock: Callable[[], datetime] = _utc_now,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self.graph = graph
        self.store = store
        self.workspace_hasher = workspace_hasher
        self.evidence_reader = evidence_reader
        self.clock = clock
        self.id_factory = id_factory

    def start(self, task: TaskRequest) -> WorkflowView:
        initial: WorkflowRuntimeState = {
            "task": _dump(task),
            "status": RunStatus.DATA_RESEARCH.value,
            "current_role": None,
            "data_research": None,
            "model_evaluation": None,
            "product_output": None,
            "correction_attempts": [],
            "validation": None,
            "risk_review": None,
            "reviewed_workspace_sha256": None,
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
        if "data_research" not in snapshot.values or "model_evaluation" not in snapshot.values:
            raise PendingApprovalError(
                "run predates required Data Research and Model Evaluation; create a new run"
            )
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
        if decision.decision is ApprovalDecision.APPROVE:
            self._verify_approval_integrity(view.state.task, request)
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
        if view.state.status is not RunStatus.AWAITING_APPROVAL:
            if (
                view.state.status
                not in {
                    RunStatus.PRODUCT,
                    RunStatus.DATA_RESEARCH,
                    RunStatus.MODEL_EVALUATION,
                    RunStatus.DEVELOPMENT,
                    RunStatus.VALIDATION,
                    RunStatus.RISK_REVIEW,
                }
                or not view.next_nodes
            ):
                raise PendingApprovalError("run has no resumable checkpoint")
            self.graph.invoke(None, self._config(run_id))
            return self.inspect(run_id)
        if view.pending_approval is None:
            raise PendingApprovalError("run is missing its approval checkpoint")
        raw = self.store.get(APPROVAL_DECISION_NAMESPACE, run_id)
        if raw is None:
            raise PendingApprovalError("no persisted operator decision exists")
        decision = _parse(HumanApprovalDecision, raw)
        if decision.decision is ApprovalDecision.APPROVE:
            self._verify_approval_integrity(view.state.task, view.pending_approval)
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
            RunStatus.FAILED,
            RunStatus.INTERRUPTED,
            RunStatus.USAGE_LIMITED,
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
        request = _parse(TaskRequest, snapshot.values["task"])
        evidence = _approval_evidence(snapshot.values)
        reviewed_workspace_sha256 = snapshot.values.get("reviewed_workspace_sha256")
        if not isinstance(reviewed_workspace_sha256, str):
            raise PendingApprovalError("Risk Review omitted the reviewed workspace hash")
        if raw is not None:
            persisted = _parse(HumanApprovalRequest, raw)
            if persisted.checkpoint_id != checkpoint_id:
                raise PendingApprovalError("persisted approval request is stale")
            if persisted.evidence != evidence:
                raise PendingApprovalError("persisted approval evidence differs from graph state")
            return persisted
        interrupts = snapshot.tasks[0].interrupts
        payload = interrupts[0].value
        if not evidence:
            raise PendingApprovalError("approval requires controller-owned evidence")
        approval_request = HumanApprovalRequest(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=self.clock(),
            request_id=str(payload["request_id"]),
            checkpoint_id=checkpoint_id,
            workspace_sha256=reviewed_workspace_sha256,
            summary=str(payload["summary"]),
            evidence=evidence,
        )
        self._verify_approval_integrity(request, approval_request)
        self.store.put(APPROVAL_REQUEST_NAMESPACE, request.run_id, _dump(approval_request))
        return approval_request

    def _verify_approval_integrity(
        self,
        task: TaskRequest | None,
        request: HumanApprovalRequest,
    ) -> None:
        if task is None:
            raise PendingApprovalError("approval task is unavailable")
        try:
            workspace_sha256 = self.workspace_hasher(Path(task.repository_root))
        except PendingApprovalError:
            raise
        except Exception as exc:
            raise PendingApprovalError("approval workspace could not be verified") from exc
        if workspace_sha256 != request.workspace_sha256:
            raise PendingApprovalError("approval workspace changed after Risk Review")
        if self.evidence_reader is None:
            return
        try:
            for artifact in request.evidence:
                self.evidence_reader(artifact)
        except Exception as exc:
            raise PendingApprovalError("approval evidence failed integrity verification") from exc

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
            "data_research": values.get("data_research"),
            "model_evaluation": values.get("model_evaluation"),
            "product_output": values.get("product_output"),
            "correction_attempts": values.get("correction_attempts", []),
            "validation": values.get("validation"),
            "risk_review": values.get("risk_review"),
            "approval_request": None if pending is None else _dump(pending),
            "approval": values.get("approval"),
            "receipts": values.get("receipts", []),
            "terminal_reason": values.get("terminal_reason"),
        }
        return GraphState.model_validate_json(json.dumps(payload))
