from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from vesper.platform.contracts import (
    ApprovalDecision,
    CodexExecutionReceipt,
    CorrectionAttempt,
    DataResearchResult,
    DevelopmentSpecialistOutput,
    EvidenceArtifactRef,
    ExecutionStatus,
    GraphState,
    HumanApprovalDecision,
    HumanApprovalRequest,
    KnowledgeDocument,
    KnowledgeKind,
    KnowledgeObservation,
    KnowledgeObservationProposal,
    KnowledgeRetention,
    KnowledgeScope,
    KnowledgeTier,
    MemoryCandidate,
    MemoryRecord,
    MemoryType,
    ModelEvaluationResult,
    PermissionSet,
    ProductSpecialistOutput,
    RiskDecision,
    RiskReviewDecision,
    RiskSpecialistOutput,
    RunStatus,
    SandboxMode,
    SpecialistInput,
    SpecialistReceipt,
    SpecialistRole,
    TaskRequest,
    ValidationCheck,
    ValidationResult,
    VerificationState,
)


NOW = datetime(2026, 7, 27, 16, 0, tzinfo=timezone.utc)
COMMON = {
    "run_id": "run-001",
    "task_id": "task-001",
    "repository_revision": "9f9df7f",
    "created_at": NOW,
}


def artifact() -> EvidenceArtifactRef:
    return EvidenceArtifactRef(
        **COMMON,
        artifact_id="artifact-001",
        relative_path="runs/run-001/result.json",
        sha256="a" * 64,
        size_bytes=12,
        media_type="application/json",
    )


def available_data_research() -> DataResearchResult:
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
        split_adjustments_sha256="b" * 64,
        evidence=(artifact(),),
    )


def available_model_evaluation() -> ModelEvaluationResult:
    return ModelEvaluationResult(
        **COMMON,
        available=True,
        configured_model_path="models/xgb_ranker.json",
        metadata_path="models/xgb_ranker.metadata.json",
        actual_sha256="c" * 64,
        expected_sha256="c" * 64,
        hash_matches=True,
        label_horizon=5,
        train_ic=0.04,
        out_of_sample_ic=0.03,
        train_samples=100,
        test_samples=50,
        evaluation_passed=True,
        evidence=(artifact(),),
    )


def validation(*, passed: bool = True) -> ValidationResult:
    return ValidationResult(
        **COMMON,
        attempt=1,
        passed=passed,
        checks=(
            ValidationCheck(
                name="pytest",
                passed=passed,
                command="python -m pytest tests/platform",
                exit_code=0 if passed else 1,
                evidence=(artifact(),),
            ),
        ),
    )


def risk(*, decision: RiskDecision = RiskDecision.APPROVE) -> RiskReviewDecision:
    return RiskReviewDecision(
        **COMMON,
        attempt=1,
        decision=decision,
        rationale="Deterministic evidence reviewed.",
        evidence=(artifact(),),
        scope_compliant=True,
        evidence_owned=True,
        prohibited_actions_compliant=True,
    )


def approval(*, decision: ApprovalDecision = ApprovalDecision.APPROVE):
    return HumanApprovalDecision(
        **COMMON,
        approval_id="approval-001",
        request_id="request-001",
        checkpoint_id="checkpoint-001",
        operator_id="operator",
        decision=decision,
        reason="Reviewed the evidence.",
        decided_at=NOW,
    )


def test_contracts_serialize_to_stable_json_and_round_trip():
    task = TaskRequest(
        **COMMON,
        objective="Implement the offline platform boundary.",
        repository_root=".",
        acceptance_checks=("python -m pytest tests/platform",),
    )

    payload = json.loads(task.model_dump_json())

    assert payload["schema_version"] == "1.0"
    assert payload["created_at"] == "2026-07-27T16:00:00Z"
    assert TaskRequest.model_validate_json(json.dumps(payload)) == task


def test_research_and_model_evaluation_contracts_bind_evidence_authority():
    data = DataResearchResult(
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
        split_adjustments_sha256="b" * 64,
        evidence=(artifact(),),
    )
    evaluation = ModelEvaluationResult(
        **COMMON,
        available=True,
        configured_model_path="models/xgb_ranker.json",
        metadata_path="models/xgb_ranker.metadata.json",
        actual_sha256="c" * 64,
        expected_sha256="c" * 64,
        hash_matches=True,
        label_horizon=5,
        train_ic=0.04,
        out_of_sample_ic=0.03,
        train_samples=100,
        test_samples=50,
        evaluation_passed=True,
        evidence=(artifact(),),
    )

    assert DataResearchResult.model_validate_json(data.model_dump_json()) == data
    assert ModelEvaluationResult.model_validate_json(evaluation.model_dump_json()) == evaluation

    foreign = artifact().model_copy(update={"run_id": "foreign"})
    payload = data.model_dump()
    payload["evidence"] = (foreign,)
    with pytest.raises(ValidationError, match="evidence authority"):
        DataResearchResult.model_validate(payload)


def test_available_data_research_rejects_invalid_source_dates():
    payload = available_data_research().model_dump()
    payload["invalid_date_rows"] = 1

    with pytest.raises(ValidationError, match="nonempty coverage"):
        DataResearchResult.model_validate(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", ""),
        ("task_id", "  "),
        ("repository_revision", ""),
        ("objective", ""),
    ],
)
def test_task_request_rejects_blank_authority_fields(field, value):
    data = {
        **COMMON,
        "objective": "Build contracts.",
        "repository_root": ".",
        "acceptance_checks": ("pytest",),
    }
    data[field] = value

    with pytest.raises(ValidationError):
        TaskRequest.model_validate(data)


def test_contracts_reject_non_utc_and_naive_timestamps():
    for bad_timestamp in (
        datetime(2026, 7, 27, 16, 0),
        datetime.fromisoformat("2026-07-27T16:00:00+01:00"),
    ):
        with pytest.raises(ValidationError):
            TaskRequest(
                **{**COMMON, "created_at": bad_timestamp},
                objective="Build contracts.",
                repository_root=".",
                acceptance_checks=("pytest",),
            )


def _knowledge_document_payload(**overrides):
    return {
        "knowledge_id": "brief-writing",
        "kind": KnowledgeKind.MEMORY,
        "scope": KnowledgeScope.SHARED,
        "approval_status": "approved",
        "tier": KnowledgeTier.ACTIVE,
        "retention": KnowledgeRetention.ADAPTIVE,
        "title": "Brief writing",
        "content": "Prefer brief wording.",
        "source_path": "memory/brief-writing.md",
        "source_sha256": "a" * 64,
        "source_line_count": 10,
        **overrides,
    }


def test_knowledge_document_requires_consistent_tier_status_and_retention():
    with pytest.raises(ValidationError, match="archived knowledge must use archived status"):
        KnowledgeDocument(**_knowledge_document_payload(tier=KnowledgeTier.ARCHIVE))

    with pytest.raises(ValidationError, match="archived knowledge must use adaptive retention"):
        KnowledgeDocument(
            **_knowledge_document_payload(
                approval_status="archived",
                tier=KnowledgeTier.ARCHIVE,
                retention=KnowledgeRetention.PINNED,
            )
        )


def test_observation_proposal_rejects_non_slug_key_and_long_summary():
    with pytest.raises(ValidationError):
        KnowledgeObservationProposal(
            concept_key="Not A Stable Key",
            title="Brief writing",
            kind=KnowledgeKind.MEMORY,
            scope=KnowledgeScope.SHARED,
            summary="x" * 601,
        )


def test_observation_requires_utc_timestamp_and_rejects_unknown_fields():
    with pytest.raises(ValidationError, match="observation timestamps must use UTC"):
        KnowledgeObservation(
            concept_key="brief-writing",
            title="Brief writing",
            kind=KnowledgeKind.MEMORY,
            scope=KnowledgeScope.SHARED,
            summary="Prefer brief wording.",
            source_ref="task-001",
            observed_at=datetime.fromisoformat("2026-07-27T16:00:00+01:00"),
        )

    with pytest.raises(ValidationError):
        KnowledgeObservationProposal(
            concept_key="brief-writing",
            title="Brief writing",
            kind=KnowledgeKind.MEMORY,
            scope=KnowledgeScope.SHARED,
            summary="Prefer brief wording.",
            unknown=True,
        )


@pytest.mark.parametrize(
    "model,payload",
    [
        (
            ProductSpecialistOutput,
            {
                **COMMON,
                "role": SpecialistRole.PRODUCT,
                "attempt": 1,
                "route": SpecialistRole.DEVELOPMENT,
                "summary": "A bounded contract task.",
                "development_instructions": "Implement only the requested contracts.",
                "acceptance_checks": ("pytest",),
            },
        ),
        (
            DevelopmentSpecialistOutput,
            {
                **COMMON,
                "role": SpecialistRole.DEVELOPMENT,
                "attempt": 1,
                "summary": "Implemented the bounded contract task.",
            },
        ),
        (
            RiskSpecialistOutput,
            {
                **COMMON,
                "role": SpecialistRole.RISK_REVIEW,
                "attempt": 1,
                "decision": RiskDecision.APPROVE,
                "rationale": "The bounded contract change is in scope.",
                "scope_compliant": True,
                "evidence_owned": True,
                "prohibited_actions_compliant": True,
            },
        ),
    ],
)
def test_specialist_outputs_allow_at_most_one_knowledge_observation(model, payload):
    observation = KnowledgeObservationProposal(
        concept_key="brief-writing",
        title="Brief writing",
        kind=KnowledgeKind.MEMORY,
        scope=KnowledgeScope.SHARED,
        summary="Prefer brief wording.",
    )

    assert model(**payload).knowledge_observations == ()
    assert model(**payload, knowledge_observations=(observation,)).knowledge_observations == (
        observation,
    )
    with pytest.raises(ValidationError):
        model(**payload, knowledge_observations=(observation, observation))


def test_contracts_reject_unknown_and_secret_like_fields():
    with pytest.raises(ValidationError):
        TaskRequest.model_validate(
            {
                **COMMON,
                "objective": "Build contracts.",
                "repository_root": ".",
                "acceptance_checks": ["pytest"],
                "api_key": "must-not-be-accepted",
            }
        )


def test_specialist_input_has_explicit_permissions_and_namespace():
    request = SpecialistInput(
        **COMMON,
        role=SpecialistRole.DEVELOPMENT,
        attempt=1,
        instructions="Implement only the requested files.",
        workspace=".",
        memory_namespace=("profiles", "v20-development", "development-episodes"),
        permissions=PermissionSet(
            sandbox=SandboxMode.WORKSPACE_WRITE,
            read_paths=(".",),
            write_paths=("vesper/platform", "tests/platform"),
            allowed_tools=("read", "write", "test"),
        ),
    )

    assert request.permissions.network_allowed is False
    assert request.permissions.trading_allowed is False


def test_specialist_receipt_cannot_claim_acceptance():
    with pytest.raises(ValidationError):
        SpecialistReceipt.model_validate(
            {
                **COMMON,
                "receipt_id": "receipt-001",
                "role": "v20-development",
                "attempt": 1,
                "status": "completed",
                "accepted": True,
            }
        )


def test_malformed_risk_and_approval_decisions_fail_closed():
    risk_payload = {
        **COMMON,
        "attempt": 1,
        "decision": "looks-good",
        "rationale": "not a defined decision",
    }
    approval_payload = {
        **COMMON,
        "approval_id": "approval-001",
        "request_id": "request-001",
        "checkpoint_id": "checkpoint-001",
        "operator_id": "operator",
        "decision": True,
        "reason": "invalid boolean decision",
        "decided_at": NOW,
    }

    with pytest.raises(ValidationError):
        RiskReviewDecision.model_validate(risk_payload)
    with pytest.raises(ValidationError):
        HumanApprovalDecision.model_validate(approval_payload)


def test_graph_acceptance_requires_all_authoritative_gates():
    base = {
        **COMMON,
        "status": RunStatus.ACCEPTED,
        "current_role": None,
        "data_research": available_data_research(),
        "model_evaluation": available_model_evaluation(),
        "correction_attempts": (),
        "validation": validation(),
        "risk_review": risk(),
        "approval": approval(),
    }
    accepted = GraphState.model_validate(base)
    assert accepted.status is RunStatus.ACCEPTED

    for missing in (
        "data_research",
        "model_evaluation",
        "validation",
        "risk_review",
        "approval",
    ):
        invalid = {**base, missing: None}
        with pytest.raises(ValidationError):
            GraphState.model_validate(invalid)

    with pytest.raises(ValidationError, match="available Data Research"):
        GraphState.model_validate(
            {
                **base,
                "data_research": available_data_research().model_copy(update={"available": False}),
            }
        )
    with pytest.raises(ValidationError, match="passing Model Evaluation"):
        GraphState.model_validate(
            {
                **base,
                "model_evaluation": available_model_evaluation().model_copy(
                    update={
                        "expected_sha256": "f" * 64,
                        "hash_matches": False,
                        "evaluation_passed": False,
                    }
                ),
            }
        )

    with pytest.raises(ValidationError):
        GraphState.model_validate({**base, "approval": approval(decision=ApprovalDecision.REJECT)})


@pytest.mark.parametrize(
    "status",
    (
        RunStatus.PRODUCT,
        RunStatus.DEVELOPMENT,
        RunStatus.VALIDATION,
        RunStatus.RISK_REVIEW,
        RunStatus.AWAITING_APPROVAL,
    ),
)
def test_post_research_graph_states_require_passing_research(status):
    base = {
        **COMMON,
        "status": status,
        "data_research": available_data_research(),
        "model_evaluation": available_model_evaluation(),
    }

    with pytest.raises(ValidationError, match="available Data Research"):
        GraphState.model_validate(
            {
                **base,
                "data_research": available_data_research().model_copy(update={"available": False}),
            }
        )
    with pytest.raises(ValidationError, match="passing Model Evaluation"):
        GraphState.model_validate(
            {
                **base,
                "model_evaluation": available_model_evaluation().model_copy(
                    update={
                        "expected_sha256": "f" * 64,
                        "hash_matches": False,
                        "evaluation_passed": False,
                    }
                ),
            }
        )


def test_correction_attempts_are_bounded_to_three():
    attempts = tuple(
        CorrectionAttempt(
            **COMMON,
            attempt=index,
            source="validation",
            reason=f"failure {index}",
        )
        for index in range(1, 4)
    )
    state = GraphState(
        **COMMON,
        status=RunStatus.OPERATOR_INTERVENTION,
        correction_attempts=attempts,
    )
    assert state.correction_count == 3

    with pytest.raises(ValidationError):
        GraphState(
            **COMMON,
            status=RunStatus.DEVELOPMENT,
            correction_attempts=attempts
            + (
                CorrectionAttempt(
                    **COMMON,
                    attempt=4,
                    source="risk-review",
                    reason="fourth failure",
                ),
            ),
        )


def test_memory_contracts_retain_verification_and_supersession_lineage():
    candidate = MemoryCandidate(
        **COMMON,
        candidate_id="candidate-001",
        namespace=("shared", "repository-facts"),
        memory_type=MemoryType.REPOSITORY_FACT,
        content="The platform package has no trading imports.",
        source_artifact=artifact(),
        confidence=0.95,
    )
    record = MemoryRecord(
        **COMMON,
        memory_id="memory-002",
        namespace=candidate.namespace,
        memory_type=candidate.memory_type,
        content=candidate.content,
        source_run=candidate.run_id,
        source_artifact=candidate.source_artifact,
        confidence=candidate.confidence,
        verification_state=VerificationState.VERIFIED,
        supersedes="memory-001",
        review_after=NOW,
    )

    assert record.supersedes == "memory-001"
    assert record.verification_state is VerificationState.VERIFIED


def test_codex_receipt_classifies_usage_limit_without_acceptance():
    receipt = CodexExecutionReceipt(
        **COMMON,
        execution_id="execution-001",
        role=SpecialistRole.DEVELOPMENT,
        attempt=1,
        status=ExecutionStatus.USAGE_LIMITED,
        sandbox=SandboxMode.WORKSPACE_WRITE,
        started_at=NOW,
        finished_at=NOW,
        error_code="usage_limit",
    )
    assert receipt.status is ExecutionStatus.USAGE_LIMITED
    assert "accepted" not in CodexExecutionReceipt.model_fields


def test_approval_request_is_bound_to_checkpoint_and_evidence():
    request = HumanApprovalRequest(
        **COMMON,
        request_id="request-001",
        checkpoint_id="checkpoint-001",
        workspace_sha256="b" * 64,
        summary="Risk review approved; operator decision required.",
        evidence=(artifact(),),
    )
    assert request.checkpoint_id == "checkpoint-001"


def test_generated_records_reject_evidence_from_other_authority_domains():
    foreign = artifact().model_copy(update={"run_id": "other-run"})

    with pytest.raises(ValidationError, match="evidence authority"):
        SpecialistReceipt(
            **COMMON,
            receipt_id="receipt-001",
            role=SpecialistRole.DEVELOPMENT,
            attempt=1,
            status=ExecutionStatus.COMPLETED,
            evidence=(foreign,),
        )

    with pytest.raises(ValidationError, match="evidence authority"):
        ValidationResult(
            **COMMON,
            attempt=1,
            passed=True,
            checks=(
                ValidationCheck(
                    name="pytest",
                    passed=True,
                    command="pytest",
                    exit_code=0,
                    evidence=(foreign,),
                ),
            ),
        )

    with pytest.raises(ValidationError, match="evidence authority"):
        RiskReviewDecision(
            **COMMON,
            attempt=1,
            decision=RiskDecision.APPROVE,
            rationale="Foreign evidence cannot support approval.",
            evidence=(foreign,),
        )


def test_v1_fixture_remains_backward_compatible():
    fixture = {
        "schema_version": "1.0",
        "run_id": "run-old",
        "task_id": "task-old",
        "repository_revision": "abc123",
        "created_at": "2026-01-01T00:00:00Z",
        "objective": "Load a stable v1 task.",
        "repository_root": ".",
        "acceptance_checks": ["pytest"],
    }
    loaded = TaskRequest.model_validate_json(json.dumps(fixture))
    assert json.loads(loaded.model_dump_json()) == fixture


def test_unknown_schema_version_is_rejected():
    with pytest.raises(ValidationError):
        TaskRequest.model_validate(
            {
                **COMMON,
                "schema_version": "2.0",
                "objective": "Reject unsupported schema.",
                "repository_root": ".",
                "acceptance_checks": ["pytest"],
            }
        )
