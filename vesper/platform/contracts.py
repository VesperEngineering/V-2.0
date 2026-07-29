"""Versioned, fail-closed contracts for V20's native agent platform."""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

SCHEMA_VERSION = "1.0"
MAX_CORRECTION_ATTEMPTS = 3

NonEmptyStr = Annotated[str, Field(min_length=1, pattern=r".*\S.*")]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
RelativePath = Annotated[str, Field(min_length=1)]


class SpecialistRole(StrEnum):
    PRODUCT = "v20-product"
    DEVELOPMENT = "v20-development"
    RISK_REVIEW = "v20-risk-review"


class SandboxMode(StrEnum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"


class ExecutionStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    USAGE_LIMITED = "usage-limited"
    PERMISSION_DENIED = "permission-denied"


class RunStatus(StrEnum):
    CREATED = "created"
    DATA_RESEARCH = "data-research"
    MODEL_EVALUATION = "model-evaluation"
    PRODUCT = "product"
    DEVELOPMENT = "development"
    VALIDATION = "validation"
    RISK_REVIEW = "risk-review"
    AWAITING_APPROVAL = "awaiting-approval"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    USAGE_LIMITED = "usage-limited"
    OPERATOR_INTERVENTION = "operator-intervention"
    CANCELLED = "cancelled"


class RiskDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    HOLD = "hold"


class ApprovalDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class VerificationState(StrEnum):
    CANDIDATE = "candidate"
    VERIFIED = "verified"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class MemoryType(StrEnum):
    REPOSITORY_FACT = "repository-fact"
    PRODUCT_DECISION = "product-decision"
    DEVELOPMENT_EPISODE = "development-episode"
    RISK_DECISION = "risk-decision"
    PROGRAM_STATE = "program-state"
    VERIFIED_PROCEDURE = "verified-procedure"
    FAILED_ATTEMPT = "failed-attempt"


class KnowledgeKind(StrEnum):
    MEMORY = "memory"
    SKILL = "skill"


class KnowledgeScope(StrEnum):
    SHARED = "shared"
    PRODUCT = "v20-product"
    DEVELOPMENT = "v20-development"
    RISK_REVIEW = "v20-risk-review"


class KnowledgeTier(StrEnum):
    ACTIVE = "active"
    ARCHIVE = "archive"


class KnowledgeRetention(StrEnum):
    PINNED = "pinned"
    ADAPTIVE = "adaptive"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class KnowledgeObservationProposal(ContractModel):
    concept_key: Annotated[
        str,
        Field(min_length=1, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
    ]
    title: Annotated[str, Field(min_length=1, max_length=120)]
    kind: KnowledgeKind
    scope: KnowledgeScope
    summary: Annotated[str, Field(min_length=1, max_length=600)]
    explicit: bool = False


class KnowledgeObservation(KnowledgeObservationProposal):
    source_ref: Annotated[str, Field(min_length=1, max_length=200)]
    observed_at: AwareDatetime

    @field_validator("observed_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
            raise ValueError("observation timestamps must use UTC")
        return value.astimezone(timezone.utc)


class RunContract(ContractModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    run_id: NonEmptyStr
    task_id: NonEmptyStr
    repository_revision: NonEmptyStr
    created_at: AwareDatetime

    @field_validator("created_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
            raise ValueError("timestamps must use UTC")
        return value.astimezone(timezone.utc)


class FinancialEventType(StrEnum):
    DIRECT_REQUEST = "direct-request"
    WEAK_MODEL_RESULT = "weak-model-result"


class FinancialResearchStatus(StrEnum):
    REQUESTED = "requested"
    PLANNED = "planned"
    COMPLETE = "complete"
    COMPLETED = "completed"
    IGNORED = "ignored"
    NEEDS_RESEARCH = "needs-research"
    NEEDS_ANALYSIS = "needs-analysis"
    STOPPED = "stopped"


class FinancialResearchContract(RunContract):
    event_id: NonEmptyStr
    non_authority: NonEmptyStr


class FinancialEventEnvelope(FinancialResearchContract):
    event_type: FinancialEventType
    occurred_at: AwareDatetime
    observed_at: AwareDatetime
    symbols: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    origin: NonEmptyStr
    deduplication_key: NonEmptyStr
    payload_sha256: Sha256
    summary: NonEmptyStr
    observed_metric: float | None = None
    threshold: float | None = None

    @field_validator("occurred_at", "observed_at")
    @classmethod
    def require_event_utc(cls, value: datetime) -> datetime:
        return RunContract.require_utc(value)

    @model_validator(mode="after")
    def validate_event_metrics(self) -> FinancialEventEnvelope:
        has_metrics = self.observed_metric is not None and self.threshold is not None
        if self.event_type is FinancialEventType.WEAK_MODEL_RESULT and not has_metrics:
            raise ValueError("weak model results require metrics")
        if self.event_type is FinancialEventType.DIRECT_REQUEST and (
            self.observed_metric is not None or self.threshold is not None
        ):
            raise ValueError("direct requests forbid metrics")
        return self


class FinancialTriggerDecision(FinancialResearchContract):
    triggered: bool
    status: FinancialResearchStatus
    reason: NonEmptyStr
    workflow: Literal["analysis-only"]
    resource_budget: NonEmptyStr

    @property
    def should_research(self) -> bool:
        return self.triggered


class FinancialResearchRequest(FinancialResearchContract):
    request_id: NonEmptyStr
    status: FinancialResearchStatus
    questions: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    source_classes: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    symbols: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    time_window_start: NonEmptyStr
    time_window_end: NonEmptyStr
    sufficiency_criteria: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    prior_attempt_ids: tuple[NonEmptyStr, ...] = ()


class AnalysisNode(FinancialResearchContract):
    node_id: NonEmptyStr
    kind: NonEmptyStr
    depends_on: tuple[NonEmptyStr, ...] = ()
    output_schema: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    transform_sha256: Sha256


class FinancialAnalysisPlan(FinancialResearchContract):
    plan_id: NonEmptyStr
    status: FinancialResearchStatus
    nodes: Annotated[tuple[AnalysisNode, ...], Field(min_length=1)]
    acceptance_checks: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_nodes(self) -> FinancialAnalysisPlan:
        node_ids = {node.node_id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("analysis plan node IDs must be unique")
        for node in self.nodes:
            if (
                node.run_id != self.run_id
                or node.task_id != self.task_id
                or node.repository_revision != self.repository_revision
                or node.event_id != self.event_id
            ):
                raise ValueError("analysis node authority must match its plan")
            if node.node_id in node.depends_on or not set(node.depends_on).issubset(node_ids):
                raise ValueError("analysis node dependencies must reference other plan nodes")
        return self


class DerivedDatasetReceipt(FinancialResearchContract):
    dataset_id: NonEmptyStr
    schema_fields: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    row_count: Annotated[int, Field(ge=0)]
    ticker_count: Annotated[int, Field(ge=0)]
    null_close_count: Annotated[int, Field(ge=0)]
    source_hashes: Annotated[tuple[Sha256, ...], Field(min_length=1)]
    transform_sha256: Sha256
    cache_key_sha256: Sha256
    coverage_start: NonEmptyStr
    coverage_end: NonEmptyStr
    lineage_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    derived_output_path: RelativePath
    validation_evidence: EvidenceArtifactRef

    @model_validator(mode="after")
    def validation_evidence_matches_authority(self) -> DerivedDatasetReceipt:
        output_path = self.derived_output_path
        posix_path = PurePosixPath(output_path)
        windows_path = PureWindowsPath(output_path)
        if (
            "\\" in output_path
            or posix_path.is_absolute()
            or windows_path.is_absolute()
            or ".." in posix_path.parts
            or len(posix_path.parts) < 2
            or posix_path.parts[0] != self.run_id
        ):
            raise ValueError("derived output path must be relative and scoped to its run")
        _evidence_matches_authority(self, (self.validation_evidence,))
        return self


class FinancialGapAssessment(FinancialResearchContract):
    assessment_id: NonEmptyStr
    status: FinancialResearchStatus
    supported_claims: tuple[NonEmptyStr, ...] = ()
    unresolved_gaps: tuple[NonEmptyStr, ...] = ()
    contradiction_state: NonEmptyStr
    confidence: Annotated[float, Field(ge=0, le=1)]
    next_action: Literal["request-research", "repair-analysis", "stop"]
    loop_budget_used: Annotated[int, Field(ge=0)]
    content_hashes: tuple[Sha256, ...] = ()
    evidence: tuple[EvidenceArtifactRef, ...] = ()

    @model_validator(mode="after")
    def claims_are_evidence_bound(self) -> FinancialGapAssessment:
        if self.supported_claims and (not self.content_hashes or not self.evidence):
            raise ValueError("claims require evidence and content hashes")
        _evidence_matches_authority(self, self.evidence)
        return self


class FinancialRecommendation(FinancialResearchContract):
    recommendation_id: NonEmptyStr
    status: FinancialResearchStatus
    conclusions: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    uncertainty: NonEmptyStr
    evidence: Annotated[tuple[EvidenceArtifactRef, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def evidence_matches_authority(self) -> FinancialRecommendation:
        _evidence_matches_authority(self, self.evidence)
        return self


class PermissionSet(ContractModel):
    sandbox: SandboxMode
    read_paths: tuple[RelativePath, ...] = ()
    write_paths: tuple[RelativePath, ...] = ()
    allowed_tools: tuple[NonEmptyStr, ...] = ()
    network_allowed: Literal[False] = False
    trading_allowed: Literal[False] = False

    @model_validator(mode="after")
    def read_only_cannot_write(self) -> PermissionSet:
        if self.sandbox is SandboxMode.READ_ONLY and self.write_paths:
            raise ValueError("read-only sandbox cannot grant write paths")
        return self


class EvidenceArtifactRef(RunContract):
    artifact_id: NonEmptyStr
    relative_path: RelativePath
    sha256: Sha256
    size_bytes: Annotated[int, Field(ge=0)]
    media_type: NonEmptyStr


def _evidence_matches_authority(
    owner: RunContract,
    evidence: tuple[EvidenceArtifactRef, ...],
) -> None:
    for artifact in evidence:
        if (
            artifact.run_id != owner.run_id
            or artifact.task_id != owner.task_id
            or artifact.repository_revision != owner.repository_revision
        ):
            raise ValueError("evidence authority must match its containing record")


class TaskRequest(RunContract):
    objective: NonEmptyStr
    repository_root: RelativePath
    acceptance_checks: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]


class DataResearchResult(RunContract):
    available: bool
    database_path: RelativePath
    table_name: NonEmptyStr
    row_count: Annotated[int, Field(ge=0)]
    ticker_count: Annotated[int, Field(ge=0)]
    start_date: NonEmptyStr | None = None
    end_date: NonEmptyStr | None = None
    required_columns: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    null_price_rows: Annotated[int, Field(ge=0)]
    invalid_date_rows: Annotated[int, Field(ge=0)]
    split_adjustments_path: RelativePath
    split_adjustments_sha256: Sha256 | None = None
    warnings: tuple[NonEmptyStr, ...] = ()
    evidence: Annotated[tuple[EvidenceArtifactRef, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def result_is_consistent(self) -> DataResearchResult:
        _evidence_matches_authority(self, self.evidence)
        if self.available and (
            self.row_count == 0
            or self.ticker_count == 0
            or self.start_date is None
            or self.end_date is None
            or self.invalid_date_rows != 0
        ):
            raise ValueError("available data research requires nonempty coverage")
        return self


class ModelEvaluationResult(RunContract):
    available: bool
    configured_model_path: RelativePath
    metadata_path: RelativePath
    actual_sha256: Sha256 | None = None
    expected_sha256: Sha256 | None = None
    hash_matches: bool | None = None
    label_horizon: Annotated[int, Field(ge=1)] | None = None
    train_ic: Annotated[float, Field(ge=-1, le=1)] | None = None
    out_of_sample_ic: Annotated[float, Field(ge=-1, le=1)] | None = None
    train_samples: Annotated[int, Field(ge=1)] | None = None
    test_samples: Annotated[int, Field(ge=1)] | None = None
    evaluation_passed: bool
    warnings: tuple[NonEmptyStr, ...] = ()
    evidence: Annotated[tuple[EvidenceArtifactRef, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def result_is_consistent(self) -> ModelEvaluationResult:
        _evidence_matches_authority(self, self.evidence)
        complete = (
            self.available
            and self.actual_sha256 is not None
            and self.expected_sha256 is not None
            and self.hash_matches is True
            and self.label_horizon is not None
            and self.train_ic is not None
            and self.out_of_sample_ic is not None
            and self.train_samples is not None
            and self.test_samples is not None
        )
        if self.evaluation_passed != complete:
            raise ValueError("model evaluation status must match integrity and metadata checks")
        return self


class SpecialistInput(RunContract):
    role: SpecialistRole
    attempt: Annotated[int, Field(ge=1, le=MAX_CORRECTION_ATTEMPTS)]
    instructions: NonEmptyStr
    workspace: RelativePath
    memory_namespace: Annotated[tuple[NonEmptyStr, ...], Field(min_length=2)]
    permissions: PermissionSet
    thread_id: NonEmptyStr | None = None


class MemoryProposal(ContractModel):
    """A non-authoritative claim emitted before controller provenance is attached."""

    memory_type: MemoryType
    content: NonEmptyStr
    confidence: Annotated[float, Field(ge=0, le=1)]
    contradicts: NonEmptyStr | None = None
    expiration_policy: NonEmptyStr = "review-required"


class ProductSpecialistOutput(RunContract):
    role: Literal[SpecialistRole.PRODUCT]
    attempt: Annotated[int, Field(ge=1, le=MAX_CORRECTION_ATTEMPTS)]
    route: Literal[SpecialistRole.DEVELOPMENT]
    summary: NonEmptyStr
    development_instructions: NonEmptyStr
    acceptance_checks: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
    memory: Annotated[tuple[MemoryProposal, ...], Field(max_length=1)] = ()
    knowledge_observations: Annotated[
        tuple[KnowledgeObservationProposal, ...], Field(max_length=1)
    ] = ()


class DevelopmentSpecialistOutput(RunContract):
    role: Literal[SpecialistRole.DEVELOPMENT]
    attempt: Annotated[int, Field(ge=1, le=MAX_CORRECTION_ATTEMPTS)]
    summary: NonEmptyStr
    changed_files: tuple[RelativePath, ...] = ()
    verification_commands: tuple[NonEmptyStr, ...] = ()
    residual_risks: tuple[NonEmptyStr, ...] = ()
    memory: Annotated[tuple[MemoryProposal, ...], Field(max_length=1)] = ()
    knowledge_observations: Annotated[
        tuple[KnowledgeObservationProposal, ...], Field(max_length=1)
    ] = ()


class RiskSpecialistOutput(RunContract):
    role: Literal[SpecialistRole.RISK_REVIEW]
    attempt: Annotated[int, Field(ge=1, le=MAX_CORRECTION_ATTEMPTS)]
    decision: RiskDecision
    rationale: NonEmptyStr
    reviewed_changed_files: tuple[RelativePath, ...] = ()
    scope_compliant: bool
    evidence_owned: bool
    prohibited_actions_compliant: bool
    residual_risks: tuple[NonEmptyStr, ...] = ()
    memory: Annotated[tuple[MemoryProposal, ...], Field(max_length=1)] = ()
    knowledge_observations: Annotated[
        tuple[KnowledgeObservationProposal, ...], Field(max_length=1)
    ] = ()


SpecialistOutput = Annotated[
    ProductSpecialistOutput | DevelopmentSpecialistOutput | RiskSpecialistOutput,
    Field(discriminator="role"),
]


class SpecialistReceipt(RunContract):
    receipt_id: NonEmptyStr
    role: SpecialistRole
    attempt: Annotated[int, Field(ge=1, le=MAX_CORRECTION_ATTEMPTS)]
    status: ExecutionStatus
    thread_id: NonEmptyStr | None = None
    final_response: str | None = None
    output: SpecialistOutput | None = None
    evidence: tuple[EvidenceArtifactRef, ...] = ()
    memory_candidates: tuple[MemoryCandidate, ...] = ()
    error_code: NonEmptyStr | None = None

    @model_validator(mode="after")
    def evidence_is_authoritative(self) -> SpecialistReceipt:
        _evidence_matches_authority(self, self.evidence)
        if self.output is not None and (
            self.output.run_id != self.run_id
            or self.output.task_id != self.task_id
            or self.output.repository_revision != self.repository_revision
            or self.output.role is not self.role
            or self.output.attempt != self.attempt
        ):
            raise ValueError("specialist output authority must match its receipt")
        for candidate in self.memory_candidates:
            if (
                candidate.run_id != self.run_id
                or candidate.task_id != self.task_id
                or candidate.repository_revision != self.repository_revision
            ):
                raise ValueError("memory candidate authority must match its receipt")
        return self


class ValidationCheck(ContractModel):
    name: NonEmptyStr
    passed: bool
    command: NonEmptyStr
    exit_code: int
    evidence: tuple[EvidenceArtifactRef, ...] = ()


class ValidationResult(RunContract):
    attempt: Annotated[int, Field(ge=1, le=MAX_CORRECTION_ATTEMPTS)]
    passed: bool
    checks: Annotated[tuple[ValidationCheck, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def result_matches_checks(self) -> ValidationResult:
        if self.passed != all(check.passed for check in self.checks):
            raise ValueError("validation result must match its deterministic checks")
        _evidence_matches_authority(
            self,
            tuple(artifact for check in self.checks for artifact in check.evidence),
        )
        return self


class RiskReviewDecision(RunContract):
    attempt: Annotated[int, Field(ge=1, le=MAX_CORRECTION_ATTEMPTS)]
    decision: RiskDecision
    rationale: NonEmptyStr
    evidence: tuple[EvidenceArtifactRef, ...] = ()
    reviewed_changed_files: tuple[RelativePath, ...] = ()
    scope_compliant: bool | None = None
    evidence_owned: bool | None = None
    prohibited_actions_compliant: bool | None = None
    residual_risks: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def evidence_is_authoritative(self) -> RiskReviewDecision:
        _evidence_matches_authority(self, self.evidence)
        return self


class RiskReviewExecution(ContractModel):
    receipt: SpecialistReceipt
    decision: RiskReviewDecision | None = None

    @model_validator(mode="after")
    def authorities_match(self) -> RiskReviewExecution:
        receipt = self.receipt
        decision = self.decision
        if receipt.role is not SpecialistRole.RISK_REVIEW:
            raise ValueError("Risk Review execution requires a Risk Review receipt")
        if receipt.status is ExecutionStatus.COMPLETED and decision is None:
            raise ValueError("completed Risk Review execution requires a decision")
        if receipt.status is not ExecutionStatus.COMPLETED and decision is not None:
            raise ValueError("non-completed Risk Review execution cannot carry a decision")
        if decision is None:
            return self
        if (
            receipt.run_id != decision.run_id
            or receipt.task_id != decision.task_id
            or receipt.repository_revision != decision.repository_revision
            or receipt.attempt != decision.attempt
        ):
            raise ValueError("Risk Review receipt and decision authority must match")
        return self


class CorrectionAttempt(RunContract):
    attempt: Annotated[int, Field(ge=1, le=MAX_CORRECTION_ATTEMPTS)]
    source: Literal["validation", "risk-review"]
    reason: NonEmptyStr
    evidence: tuple[EvidenceArtifactRef, ...] = ()


class HumanApprovalRequest(RunContract):
    request_id: NonEmptyStr
    checkpoint_id: NonEmptyStr
    workspace_sha256: Sha256
    summary: NonEmptyStr
    evidence: Annotated[tuple[EvidenceArtifactRef, ...], Field(min_length=1)]


class HumanApprovalDecision(RunContract):
    approval_id: NonEmptyStr
    request_id: NonEmptyStr
    checkpoint_id: NonEmptyStr
    operator_id: NonEmptyStr
    decision: ApprovalDecision
    reason: NonEmptyStr
    decided_at: AwareDatetime

    @field_validator("decided_at")
    @classmethod
    def require_decision_utc(cls, value: datetime) -> datetime:
        return RunContract.require_utc(value)


class CodexExecutionReceipt(RunContract):
    execution_id: NonEmptyStr
    role: SpecialistRole
    attempt: Annotated[int, Field(ge=1, le=MAX_CORRECTION_ATTEMPTS)]
    status: ExecutionStatus
    sandbox: SandboxMode
    model: NonEmptyStr | None = None
    workspace: RelativePath | None = None
    approval_mode: Literal["deny-all"] | None = None
    authentication_type: NonEmptyStr | None = None
    permission_profile: NonEmptyStr | None = None
    started_at: AwareDatetime
    finished_at: AwareDatetime
    thread_id: NonEmptyStr | None = None
    final_response: str | None = None
    streamed_events: tuple[dict[str, object], ...] = ()
    error_code: NonEmptyStr | None = None

    @field_validator("started_at", "finished_at")
    @classmethod
    def require_execution_utc(cls, value: datetime) -> datetime:
        return RunContract.require_utc(value)

    @model_validator(mode="after")
    def end_not_before_start(self) -> CodexExecutionReceipt:
        if self.finished_at < self.started_at:
            raise ValueError("finished_at cannot precede started_at")
        return self


class MemoryCandidate(RunContract):
    candidate_id: NonEmptyStr
    namespace: Annotated[tuple[NonEmptyStr, ...], Field(min_length=2)]
    memory_type: MemoryType
    content: NonEmptyStr
    source_artifact: EvidenceArtifactRef
    confidence: Annotated[float, Field(ge=0, le=1)]
    contradicts: NonEmptyStr | None = None
    expiration_policy: NonEmptyStr = "review-required"

    @model_validator(mode="after")
    def source_matches_authority(self) -> MemoryCandidate:
        _evidence_matches_authority(self, (self.source_artifact,))
        return self


class MemoryRecord(RunContract):
    memory_id: NonEmptyStr
    namespace: Annotated[tuple[NonEmptyStr, ...], Field(min_length=2)]
    memory_type: MemoryType
    content: NonEmptyStr
    source_run: NonEmptyStr
    source_artifact: EvidenceArtifactRef
    confidence: Annotated[float, Field(ge=0, le=1)]
    verification_state: VerificationState
    supersedes: NonEmptyStr | None = None
    superseded_by: NonEmptyStr | None = None
    review_after: AwareDatetime | None = None
    expiration_policy: NonEmptyStr = "review-required"

    @field_validator("review_after")
    @classmethod
    def require_review_utc(cls, value: datetime | None) -> datetime | None:
        return None if value is None else RunContract.require_utc(value)

    @model_validator(mode="after")
    def source_matches_authority(self) -> MemoryRecord:
        _evidence_matches_authority(self, (self.source_artifact,))
        return self


class KnowledgeDocument(ContractModel):
    knowledge_id: NonEmptyStr
    kind: KnowledgeKind
    scope: KnowledgeScope
    approval_status: Literal["approved", "archived"]
    tier: KnowledgeTier
    retention: KnowledgeRetention
    title: NonEmptyStr
    tags: tuple[NonEmptyStr, ...] = ()
    content: NonEmptyStr
    source_path: RelativePath
    source_sha256: Sha256
    source_line_count: Annotated[int, Field(ge=1)]
    supersedes: tuple[NonEmptyStr, ...] = ()
    review_after: date | None = None
    contested: bool = False

    @model_validator(mode="after")
    def tier_matches_status_and_retention(self) -> KnowledgeDocument:
        if self.tier is KnowledgeTier.ACTIVE and self.approval_status != "approved":
            raise ValueError("active knowledge must use approved status")
        if self.tier is KnowledgeTier.ARCHIVE and self.approval_status != "archived":
            raise ValueError("archived knowledge must use archived status")
        if self.tier is KnowledgeTier.ARCHIVE and self.retention is KnowledgeRetention.PINNED:
            raise ValueError("archived knowledge must use adaptive retention")
        return self


class KnowledgeContext(RunContract):
    role: SpecialistRole
    documents: tuple[KnowledgeDocument, ...] = ()


class ResumableRunMetadata(RunContract):
    checkpoint_id: NonEmptyStr
    thread_id: NonEmptyStr
    status: RunStatus
    updated_at: AwareDatetime
    pending_approval_request_id: NonEmptyStr | None = None

    @field_validator("updated_at")
    @classmethod
    def require_updated_utc(cls, value: datetime) -> datetime:
        return RunContract.require_utc(value)


class RunManifest(RunContract):
    status: RunStatus
    artifacts: tuple[EvidenceArtifactRef, ...] = ()
    resume: ResumableRunMetadata | None = None


class GraphState(RunContract):
    task: TaskRequest | None = None
    status: RunStatus
    current_role: SpecialistRole | None = None
    data_research: DataResearchResult | None = None
    model_evaluation: ModelEvaluationResult | None = None
    product_output: ProductSpecialistOutput | None = None
    correction_attempts: tuple[CorrectionAttempt, ...] = ()
    validation: ValidationResult | None = None
    risk_review: RiskReviewDecision | None = None
    approval_request: HumanApprovalRequest | None = None
    approval: HumanApprovalDecision | None = None
    receipts: tuple[SpecialistReceipt, ...] = ()
    terminal_reason: str | None = None

    @property
    def correction_count(self) -> int:
        return len(self.correction_attempts)

    @model_validator(mode="after")
    def enforce_authority_and_budget(self) -> GraphState:
        if len(self.correction_attempts) > MAX_CORRECTION_ATTEMPTS:
            raise ValueError("correction attempts cannot exceed three")
        if self.status in {
            RunStatus.PRODUCT,
            RunStatus.DEVELOPMENT,
            RunStatus.VALIDATION,
            RunStatus.RISK_REVIEW,
            RunStatus.AWAITING_APPROVAL,
            RunStatus.ACCEPTED,
        }:
            if self.data_research is None or not self.data_research.available:
                raise ValueError("post-research execution requires available Data Research")
            if self.model_evaluation is None or not self.model_evaluation.evaluation_passed:
                raise ValueError("post-research execution requires a passing Model Evaluation")
        if self.status is RunStatus.ACCEPTED:
            if self.validation is None or not self.validation.passed:
                raise ValueError("acceptance requires deterministic validation")
            if self.risk_review is None or self.risk_review.decision is not RiskDecision.APPROVE:
                raise ValueError("acceptance requires Risk Review approval")
            if not all(
                item is True
                for item in (
                    self.risk_review.scope_compliant,
                    self.risk_review.evidence_owned,
                    self.risk_review.prohibited_actions_compliant,
                )
            ):
                raise ValueError("acceptance requires all Risk Review compliance gates")
            if self.approval is None or self.approval.decision is not ApprovalDecision.APPROVE:
                raise ValueError("acceptance requires explicit operator approval")
        return self


SpecialistReceipt.model_rebuild()
RiskReviewExecution.model_rebuild()
