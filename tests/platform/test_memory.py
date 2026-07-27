from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from vesper.platform.contracts import (
    DevelopmentSpecialistOutput,
    EvidenceArtifactRef,
    ExecutionStatus,
    MemoryCandidate,
    MemoryType,
    ProductSpecialistOutput,
    RiskDecision,
    RiskReviewDecision,
    RiskSpecialistOutput,
    SpecialistReceipt,
    SpecialistRole,
    ValidationCheck,
    ValidationResult,
)
from vesper.platform.memory import (
    DeterministicMemoryCandidateValidator,
    ControllerActor,
    MemoryAccessDenied,
    MemoryConsolidationNode,
    MemoryService,
    UnvalidatedMemoryError,
)
from vesper.platform.persistence import PlatformPaths, open_persistence


NOW = datetime(2026, 7, 27, 16, 0, tzinfo=timezone.utc)
COMMON = {
    "run_id": "run-001",
    "task_id": "task-001",
    "repository_revision": "9f9df7f",
    "created_at": NOW,
}


class DictStore:
    def __init__(self):
        self.values: dict[tuple[tuple[str, ...], str], dict] = {}

    def put(self, namespace, key, value):
        self.values[(tuple(namespace), key)] = dict(value)

    def get(self, namespace, key):
        return self.values.get((tuple(namespace), key))

    def search(self, namespace):
        prefix = tuple(namespace)
        return tuple(
            value
            for (stored_namespace, _), value in self.values.items()
            if stored_namespace == prefix
        )


def artifact() -> EvidenceArtifactRef:
    return EvidenceArtifactRef(
        **COMMON,
        artifact_id="source",
        relative_path="runs/run-001/source.json",
        sha256="a" * 64,
        size_bytes=10,
        media_type="application/json",
    )


def candidate(
    memory_type: MemoryType,
    namespace: tuple[str, ...],
    *,
    candidate_id: str = "candidate-001",
    content: str = "Validated fact.",
    contradicts: str | None = None,
) -> MemoryCandidate:
    return MemoryCandidate(
        **COMMON,
        candidate_id=candidate_id,
        namespace=namespace,
        memory_type=memory_type,
        content=content,
        source_artifact=artifact(),
        confidence=0.9,
        contradicts=contradicts,
    )


def service(store=None):
    identifiers = iter(("memory-001", "memory-002", "memory-003"))
    return MemoryService(
        store or DictStore(),
        id_factory=lambda: next(identifiers),
        clock=lambda: NOW,
    )


def test_only_validated_candidates_can_be_committed():
    memory = service()
    item = candidate(
        MemoryType.DEVELOPMENT_EPISODE,
        ("profiles", "v20-development", "development-episodes"),
    )

    with pytest.raises(UnvalidatedMemoryError):
        memory.commit(SpecialistRole.DEVELOPMENT, item, validated=False)

    record = memory.commit(SpecialistRole.DEVELOPMENT, item, validated=True)
    assert record.memory_id == "memory-001"
    assert record.source_artifact == artifact()


def test_profile_namespaces_are_isolated():
    memory = service()
    product = candidate(
        MemoryType.PRODUCT_DECISION,
        ("profiles", "v20-product", "product-decisions"),
    )
    memory.commit(SpecialistRole.PRODUCT, product, validated=True)

    assert len(memory.search(SpecialistRole.PRODUCT, MemoryType.PRODUCT_DECISION)) == 1
    with pytest.raises(MemoryAccessDenied):
        memory.search(SpecialistRole.DEVELOPMENT, MemoryType.PRODUCT_DECISION)


def test_development_cannot_modify_or_read_risk_decision_memory():
    memory = service()
    risk_item = candidate(
        MemoryType.RISK_DECISION,
        ("profiles", "v20-risk-review", "risk-decisions"),
    )

    with pytest.raises(MemoryAccessDenied):
        memory.commit(SpecialistRole.DEVELOPMENT, risk_item, validated=True)
    with pytest.raises(MemoryAccessDenied):
        memory.search(SpecialistRole.DEVELOPMENT, MemoryType.RISK_DECISION)

    record = memory.commit(SpecialistRole.RISK_REVIEW, risk_item, validated=True)
    assert record.namespace[1] == "v20-risk-review"


def test_shared_repository_facts_are_controller_written_and_profile_readable():
    memory = service()
    shared = candidate(
        MemoryType.REPOSITORY_FACT,
        ("shared", "repository-facts"),
    )

    with pytest.raises(MemoryAccessDenied):
        memory.commit(SpecialistRole.PRODUCT, shared, validated=True)
    memory.commit(ControllerActor.CONTROLLER, shared, validated=True)

    assert memory.search(SpecialistRole.DEVELOPMENT, MemoryType.REPOSITORY_FACT)
    assert memory.search(SpecialistRole.RISK_REVIEW, MemoryType.REPOSITORY_FACT)


def test_program_state_is_controller_owned_and_task_scoped():
    memory = service()
    program_state = candidate(
        MemoryType.PROGRAM_STATE,
        ("programs", "task-001", "state"),
    )

    with pytest.raises(MemoryAccessDenied):
        memory.commit(SpecialistRole.PRODUCT, program_state, validated=True)
    memory.commit(ControllerActor.CONTROLLER, program_state, validated=True)

    assert memory.search(
        ControllerActor.CONTROLLER,
        MemoryType.PROGRAM_STATE,
        task_id="task-001",
    )
    assert not memory.search(
        ControllerActor.CONTROLLER,
        MemoryType.PROGRAM_STATE,
        task_id="different-task",
    )


def test_contradictory_memories_are_append_only_with_explicit_lineage():
    store = DictStore()
    memory = service(store)
    first = candidate(
        MemoryType.PRODUCT_DECISION,
        ("profiles", "v20-product", "product-decisions"),
        content="Use option A.",
    )
    old_record = memory.commit(SpecialistRole.PRODUCT, first, validated=True)
    replacement = candidate(
        MemoryType.PRODUCT_DECISION,
        ("profiles", "v20-product", "product-decisions"),
        candidate_id="candidate-002",
        content="Use option B.",
        contradicts=old_record.memory_id,
    )

    new_record = memory.commit(SpecialistRole.PRODUCT, replacement, validated=True)

    all_records = memory.history(SpecialistRole.PRODUCT, MemoryType.PRODUCT_DECISION)
    assert {item.memory_id for item in all_records} == {"memory-001", "memory-002"}
    assert new_record.supersedes == old_record.memory_id
    assert memory.search(SpecialistRole.PRODUCT, MemoryType.PRODUCT_DECISION) == (new_record,)


def test_candidate_namespace_is_derived_and_cannot_be_spoofed():
    memory = service()
    spoofed = candidate(
        MemoryType.DEVELOPMENT_EPISODE,
        ("profiles", "v20-risk-review", "risk-decisions"),
    )
    with pytest.raises(MemoryAccessDenied):
        memory.commit(SpecialistRole.DEVELOPMENT, spoofed, validated=True)


class FakeEmitter:
    def emit_candidates(self, source_text, context):
        assert source_text == "validated receipts"
        return [
            {
                **COMMON,
                "candidate_id": "candidate-001",
                "namespace": ["profiles", "v20-development", "development-episodes"],
                "memory_type": "development-episode",
                "content": "The deterministic test passed.",
                "source_artifact": artifact().model_dump(mode="json"),
                "confidence": 0.9,
            }
        ]


def test_memory_consolidation_node_emits_typed_candidates_from_fake_codex_boundary():
    node = MemoryConsolidationNode(FakeEmitter())
    emitted = node.consolidate(source_text="validated receipts", context={"validated": True})
    assert len(emitted) == 1
    assert isinstance(emitted[0], MemoryCandidate)


def test_memory_consolidation_fails_closed_on_malformed_output():
    class MalformedEmitter:
        def emit_candidates(self, source_text, context):
            return [{"content": "missing authority and provenance"}]

    with pytest.raises(ValidationError):
        MemoryConsolidationNode(MalformedEmitter()).consolidate(
            source_text="validated receipts",
            context={"validated": True},
        )


def test_memory_service_persists_through_local_langgraph_store(tmp_path):
    paths = PlatformPaths.below(tmp_path / "platform")
    item = candidate(
        MemoryType.DEVELOPMENT_EPISODE,
        ("profiles", "v20-development", "development-episodes"),
    )
    with open_persistence(paths) as persistence:
        memory = MemoryService(
            persistence.store,
            id_factory=lambda: "memory-local",
            clock=lambda: NOW,
        )
        memory.commit(SpecialistRole.DEVELOPMENT, item, validated=True)

    with open_persistence(paths) as reopened:
        recovered = MemoryService(reopened.store).search(
            SpecialistRole.DEVELOPMENT,
            MemoryType.DEVELOPMENT_EPISODE,
        )

    assert recovered[0].memory_id == "memory-local"
    assert recovered[0].content == "Validated fact."


def test_corrupted_local_store_memory_record_is_rejected(tmp_path):
    paths = PlatformPaths.below(tmp_path / "platform")
    namespace = ("profiles", "v20-development", "development-episodes")
    with open_persistence(paths) as persistence:
        persistence.store.put(namespace, "corrupt", {"content": "missing provenance"})
        memory = MemoryService(persistence.store)

        with pytest.raises(ValidationError):
            memory.history(SpecialistRole.DEVELOPMENT, MemoryType.DEVELOPMENT_EPISODE)


def test_memory_candidate_rejects_foreign_source_artifact():
    foreign = artifact().model_copy(update={"run_id": "foreign-run"})

    with pytest.raises(ValidationError):
        MemoryCandidate(
            **COMMON,
            candidate_id="candidate-foreign",
            namespace=("profiles", "v20-development", "development-episodes"),
            memory_type=MemoryType.DEVELOPMENT_EPISODE,
            content="Foreign evidence must not become memory.",
            source_artifact=foreign,
            confidence=0.9,
        )


def test_generated_memory_requires_exact_authoritative_claim_and_validation():
    validator = DeterministicMemoryCandidateValidator()
    output = DevelopmentSpecialistOutput(
        **COMMON,
        role=SpecialistRole.DEVELOPMENT,
        attempt=1,
        summary="Created the controlled marker.",
        changed_files=("RESULT.md",),
    )
    exact = candidate(
        MemoryType.DEVELOPMENT_EPISODE,
        ("profiles", "v20-development", "development-episodes"),
        content="Validated Development attempt 1; changed_files=RESULT.md",
    )
    unverified = exact.model_copy(
        update={"candidate_id": "candidate-unverified", "content": "Everything is safe."}
    )
    receipt = SpecialistReceipt(
        **COMMON,
        receipt_id="development-001",
        role=SpecialistRole.DEVELOPMENT,
        attempt=1,
        status=ExecutionStatus.COMPLETED,
        output=output,
        evidence=(artifact(),),
        memory_candidates=(exact, unverified),
    )
    passed = ValidationResult(
        **COMMON,
        attempt=1,
        passed=True,
        checks=(
            ValidationCheck(
                name="git-diff-check",
                passed=True,
                command="git diff --check",
                exit_code=0,
            ),
        ),
    )

    assert validator.accepts(receipt, exact, validation=passed) is True
    assert validator.accepts(receipt, unverified, validation=passed) is False
    assert (
        validator.accepts(
            receipt,
            exact,
            validation=passed.model_copy(update={"passed": False}),
        )
        is False
    )


def test_product_and_risk_memory_claims_are_bound_to_typed_outputs():
    validator = DeterministicMemoryCandidateValidator()
    product_output = ProductSpecialistOutput(
        **COMMON,
        role=SpecialistRole.PRODUCT,
        attempt=1,
        route=SpecialistRole.DEVELOPMENT,
        summary="Route task.",
        development_instructions="Create RESULT.md.",
        acceptance_checks=("git-diff-check",),
    )
    product_candidate = candidate(
        MemoryType.PRODUCT_DECISION,
        ("profiles", "v20-product", "product-decisions"),
        content="Product routed task to v20-development.",
    )
    product_receipt = SpecialistReceipt(
        **COMMON,
        receipt_id="product-001",
        role=SpecialistRole.PRODUCT,
        attempt=1,
        status=ExecutionStatus.COMPLETED,
        output=product_output,
        evidence=(artifact(),),
        memory_candidates=(product_candidate,),
    )
    assert validator.accepts(product_receipt, product_candidate) is True

    risk_output = RiskSpecialistOutput(
        **COMMON,
        role=SpecialistRole.RISK_REVIEW,
        attempt=1,
        decision=RiskDecision.APPROVE,
        rationale="Evidence passed.",
        reviewed_changed_files=("RESULT.md",),
        scope_compliant=True,
        evidence_owned=True,
        prohibited_actions_compliant=True,
    )
    risk_candidate = candidate(
        MemoryType.RISK_DECISION,
        ("profiles", "v20-risk-review", "risk-decisions"),
        content="Risk Review decision=approve; attempt=1",
    )
    risk_receipt = SpecialistReceipt(
        **COMMON,
        receipt_id="risk-001",
        role=SpecialistRole.RISK_REVIEW,
        attempt=1,
        status=ExecutionStatus.COMPLETED,
        output=risk_output,
        evidence=(artifact(),),
        memory_candidates=(risk_candidate,),
    )
    decision = RiskReviewDecision(
        **COMMON,
        attempt=1,
        decision=RiskDecision.APPROVE,
        rationale="Evidence passed.",
        reviewed_changed_files=("RESULT.md",),
        scope_compliant=True,
        evidence_owned=True,
        prohibited_actions_compliant=True,
    )
    assert validator.accepts(risk_receipt, risk_candidate, risk_decision=decision) is True
    assert validator.accepts(risk_receipt, risk_candidate) is False
