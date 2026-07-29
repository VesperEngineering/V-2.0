from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import stat
import threading
from types import SimpleNamespace

import pytest
import yaml

from vesper.platform.contracts import (
    DevelopmentSpecialistOutput,
    ExecutionStatus,
    KnowledgeKind,
    KnowledgeObservation,
    KnowledgeObservationProposal,
    KnowledgeRetention,
    KnowledgeScope,
    KnowledgeTier,
    KnowledgeContext,
    KnowledgeDocument,
    SpecialistReceipt,
    SpecialistRole,
    TaskRequest,
)


NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)


class DictStore:
    def __init__(self) -> None:
        self.values: dict[tuple[tuple[str, ...], str], dict[str, object]] = {}

    def put(self, namespace, key, value) -> None:
        self.values[(namespace, key)] = dict(value)

    def get(self, namespace, key):
        value = self.values.get((namespace, key))
        return None if value is None else dict(value)

    def search(self, namespace, *, limit=10):
        return tuple(
            dict(value)
            for (stored_namespace, _), value in self.values.items()
            if stored_namespace == namespace
        )[:limit]

    def delete(self, namespace, key) -> None:
        self.values.pop((namespace, key), None)


def _lifecycle_module():
    from vesper.platform import knowledge_lifecycle

    return knowledge_lifecycle


def lifecycle_service(tmp_path: Path):
    vault = tmp_path / "knowledge"
    return (
        _lifecycle_module().KnowledgeLifecycleService(
            vault_root=vault,
            store=DictStore(),
            clock=lambda: NOW,
        ),
        vault,
    )


def task(*, run_id: str = "run-001") -> TaskRequest:
    return TaskRequest(
        run_id=run_id,
        task_id="task-001",
        repository_revision="abc1234",
        created_at=NOW,
        objective="Record adaptive knowledge usage.",
        repository_root=".",
        acceptance_checks=("python -m pytest tests/platform",),
    )


def knowledge_document(
    knowledge_id: str,
    tier: KnowledgeTier,
    *,
    retention: KnowledgeRetention = KnowledgeRetention.ADAPTIVE,
    lines: int = 10,
    supersedes: tuple[str, ...] = (),
    review_after: date | None = None,
    contested: bool = False,
) -> KnowledgeDocument:
    return KnowledgeDocument(
        knowledge_id=knowledge_id,
        kind=KnowledgeKind.MEMORY,
        scope=KnowledgeScope.DEVELOPMENT,
        approval_status="approved" if tier is KnowledgeTier.ACTIVE else "archived",
        tier=tier,
        retention=retention,
        title=f"{knowledge_id} note",
        content="Knowledge body.",
        source_path=("memory" if tier is KnowledgeTier.ACTIVE else "archive/memory")
        + f"/{knowledge_id}.md",
        source_sha256=(knowledge_id[0] * 64) if knowledge_id[0] in "abcdef" else "a" * 64,
        source_line_count=lines,
        supersedes=supersedes,
        review_after=review_after,
        contested=contested,
    )


def knowledge_context(
    knowledge_id: str,
    tier: KnowledgeTier,
    *,
    run_id: str = "run-001",
    task_id: str = "task-001",
    role: SpecialistRole = SpecialistRole.DEVELOPMENT,
) -> KnowledgeContext:
    return KnowledgeContext(
        run_id=run_id,
        task_id=task_id,
        repository_revision="abc1234",
        created_at=NOW,
        role=role,
        documents=(knowledge_document(knowledge_id, tier),),
    )


def receipt_with_observation(*, run_id: str = "run-001") -> SpecialistReceipt:
    output = DevelopmentSpecialistOutput(
        run_id=run_id,
        task_id="task-001",
        repository_revision="abc1234",
        created_at=NOW,
        role=SpecialistRole.DEVELOPMENT,
        attempt=1,
        summary="Implemented the bounded change.",
        knowledge_observations=(
            KnowledgeObservationProposal(
                concept_key="accepted-observation",
                title="Accepted observation",
                kind=KnowledgeKind.MEMORY,
                scope=KnowledgeScope.DEVELOPMENT,
                summary="Only accepted runs materialize this observation.",
                explicit=True,
            ),
        ),
    )
    return SpecialistReceipt(
        run_id=run_id,
        task_id="task-001",
        repository_revision="abc1234",
        created_at=NOW,
        receipt_id="receipt-001",
        role=SpecialistRole.DEVELOPMENT,
        attempt=1,
        status=ExecutionStatus.COMPLETED,
        output=output,
    )


def observation(
    *,
    source_ref: str = "task-0",
    observed_at: datetime = NOW,
    title: str = "Brief writing guidance",
    kind: KnowledgeKind = KnowledgeKind.MEMORY,
    scope: KnowledgeScope = KnowledgeScope.DEVELOPMENT,
    summary: str = "Write the task brief before changing implementation code.",
    explicit: bool = False,
) -> KnowledgeObservation:
    return KnowledgeObservation(
        concept_key="brief-writing",
        source_ref=source_ref,
        observed_at=observed_at,
        title=title,
        kind=kind,
        scope=scope,
        summary=summary,
        explicit=explicit,
    )


def _write_note(
    vault: Path,
    relative_path: str,
    *,
    knowledge_id: str,
    kind: str = "memory",
    status: str = "approved",
    retention: str = "adaptive",
    supersedes: tuple[str, ...] = (),
    review_after: date | None = None,
    contested: bool = False,
    body: str = "Existing body.",
) -> Path:
    path = vault / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = [
        "---",
        f"vesper_id: {knowledge_id}",
        f"vesper_kind: {kind}",
        f"vesper_status: {status}",
        f"vesper_retention: {retention}",
        "vesper_scope: v20-development",
        "title: Existing note",
    ]
    if supersedes:
        metadata.append(f"vesper_supersedes: {list(supersedes)}")
    if review_after is not None:
        metadata.append(f"vesper_review_after: {review_after.isoformat()}")
    if contested:
        metadata.append("vesper_contested: true")
    path.write_text("\n".join((*metadata, "---", body, "")), encoding="utf-8")
    return path


def _metadata(path: Path) -> dict[str, object]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return yaml.safe_load("\n".join(lines[1 : lines.index("---", 1)]))


def test_three_distinct_observations_create_one_candidate_and_replay_is_idempotent(tmp_path):
    service, vault = lifecycle_service(tmp_path)

    for index in range(3):
        result = service.observe(observation(source_ref=f"task-{index}"))

    candidate = vault / "inbox" / "brief-writing.md"
    assert result == {
        "status": "candidate-created",
        "concept_key": "brief-writing",
        "observation_count": 3,
    }
    assert candidate.is_file()
    assert "vesper_status: candidate" in candidate.read_text(encoding="utf-8")

    replay = service.observe(
        observation(source_ref="task-2", observed_at=NOW + timedelta(minutes=30))
    )

    assert replay["status"] == "candidate-unchanged"
    assert _metadata(candidate)["vesper_observation_count"] == 3
    assert _metadata(candidate)["vesper_confidence"] == "medium"
    assert _metadata(candidate)["vesper_source_refs"] == ["task-0", "task-1", "task-2"]


def test_replaying_an_unchanged_candidate_does_not_replace_its_file(tmp_path, monkeypatch):
    service, _ = lifecycle_service(tmp_path)
    for index in range(3):
        service.observe(observation(source_ref=f"task-{index}"))

    def unexpected_replace(_path: Path, _target: Path):
        raise AssertionError("unchanged candidate was replaced")

    monkeypatch.setattr(Path, "replace", unexpected_replace)

    result = service.observe(observation(source_ref="task-2"))

    assert result["status"] == "candidate-unchanged"


def test_model_copied_concept_key_cannot_escape_vault_or_reach_store(tmp_path):
    vault = tmp_path / "knowledge"
    store = DictStore()
    service = _lifecycle_module().KnowledgeLifecycleService(vault_root=vault, store=store)
    unsafe = observation(explicit=True).model_copy(update={"concept_key": "../../escaped"})

    with pytest.raises(_lifecycle_module().KnowledgeLifecycleError, match="concept key"):
        service.observe(unsafe)

    assert store.values == {}
    assert not (tmp_path / "escaped.md").exists()


@pytest.mark.parametrize("linked_path", ("knowledge", "knowledge/inbox"))
def test_linked_or_reparse_vault_components_fail_before_store_access(
    tmp_path, monkeypatch, linked_path
):
    vault = tmp_path / "knowledge"
    target = tmp_path / linked_path
    target.mkdir(parents=True)
    store = DictStore()
    service = _lifecycle_module().KnowledgeLifecycleService(vault_root=vault, store=store)
    original_lstat = Path.lstat

    def lstat_with_reparse_point(path: Path, *args, **kwargs):
        if path == target:
            return SimpleNamespace(
                st_mode=0,
                st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
            )
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", lstat_with_reparse_point)

    with pytest.raises(_lifecycle_module().KnowledgeLifecycleError, match="linked knowledge path"):
        service.observe(observation(explicit=True))

    assert store.values == {}


def test_fractional_timestamps_are_compared_as_utc_datetimes(tmp_path):
    vault = tmp_path / "knowledge"
    store = DictStore()
    store.put(
        ("knowledge", "adaptive", "observations"),
        "brief-writing",
        {
            "source_refs": ["task-0"],
            "first_observed_at": "2026-07-28T12:00:00Z",
            "last_observed_at": "2026-07-28T12:00:00Z",
            "title": "Brief writing guidance",
            "kind": "memory",
            "scope": "v20-development",
            "summary": "Write the task brief before changing implementation code.",
            "explicit": False,
        },
    )
    service = _lifecycle_module().KnowledgeLifecycleService(vault_root=vault, store=store)

    result = service.observe(
        observation(
            source_ref="task-1",
            observed_at=datetime(2026, 7, 28, 12, 0, 0, 100000, tzinfo=timezone.utc),
            explicit=True,
        )
    )

    metadata = _metadata(vault / "inbox" / "brief-writing.md")
    assert result["status"] == "candidate-created"
    assert metadata["vesper_first_observed_at"] == "2026-07-28T12:00:00Z"
    assert metadata["vesper_last_observed_at"] == "2026-07-28T12:00:00.100000Z"


def test_fewer_than_three_distinct_nonexplicit_observations_are_recorded_only(tmp_path):
    service, vault = lifecycle_service(tmp_path)

    result = service.observe(observation(source_ref="task-0"))

    assert result == {
        "status": "recorded",
        "concept_key": "brief-writing",
        "observation_count": 1,
    }
    assert not (vault / "inbox").exists()


def test_explicit_observation_creates_high_confidence_candidate_immediately(tmp_path):
    service, vault = lifecycle_service(tmp_path)

    result = service.observe(observation(explicit=True))

    metadata = _metadata(vault / "inbox" / "brief-writing.md")
    assert result["status"] == "candidate-created"
    assert metadata["vesper_confidence"] == "high"
    assert metadata["vesper_observation_count"] == 1


def test_changed_proposal_updates_existing_candidate_without_losing_provenance(tmp_path):
    service, vault = lifecycle_service(tmp_path)
    for index in range(3):
        service.observe(observation(source_ref=f"task-{index}"))

    result = service.observe(
        observation(
            source_ref="task-2",
            title="Test-first brief writing",
            summary="Write and run a failing test before implementation changes.",
        )
    )

    metadata = _metadata(vault / "inbox" / "brief-writing.md")
    assert result["status"] == "candidate-updated"
    assert metadata["title"] == "Test-first brief writing"
    assert metadata["vesper_observation_count"] == 3
    assert metadata["vesper_source_refs"] == ["task-0", "task-1", "task-2"]


@pytest.mark.parametrize(
    ("relative_path", "status", "expected_status"),
    (
        ("memory/brief-writing.md", "approved", "already-active"),
        ("archive/memory/brief-writing.md", "archived", "archived-observed"),
    ),
)
def test_active_and_archived_ids_keep_stable_identity(
    tmp_path, relative_path, status, expected_status
):
    service, vault = lifecycle_service(tmp_path)
    _write_note(
        vault,
        relative_path,
        knowledge_id="brief-writing",
        status=status,
    )

    result = service.observe(observation(explicit=True))

    assert result["status"] == expected_status
    assert not (vault / "inbox" / "brief-writing.md").exists()


def test_existing_candidate_is_updated_in_place(tmp_path):
    service, vault = lifecycle_service(tmp_path)
    candidate = _write_note(
        vault,
        "inbox/brief-writing.md",
        knowledge_id="brief-writing",
        status="candidate",
    )
    original_path = candidate

    result = service.observe(observation(explicit=True))

    assert result["status"] == "candidate-updated"
    assert candidate == original_path
    assert _metadata(candidate)["vesper_observation_count"] == 1


def test_preexisting_inbox_id_at_another_path_fails_closed(tmp_path):
    service, vault = lifecycle_service(tmp_path)
    _write_note(vault, "inbox/other.md", knowledge_id="brief-writing", status="candidate")

    with pytest.raises(
        _lifecycle_module().KnowledgeLifecycleError, match="candidate path collision"
    ):
        service.observe(observation(explicit=True))

    assert not (vault / "inbox" / "brief-writing.md").exists()


def test_candidate_path_with_a_different_id_fails_closed(tmp_path):
    service, vault = lifecycle_service(tmp_path)
    candidate = _write_note(
        vault, "inbox/brief-writing.md", knowledge_id="other-id", status="candidate"
    )
    original = candidate.read_bytes()

    with pytest.raises(
        _lifecycle_module().KnowledgeLifecycleError, match="candidate path collision"
    ):
        service.observe(observation(explicit=True))

    assert candidate.read_bytes() == original


@pytest.mark.parametrize("field", ("concept_key", "title", "summary", "source_ref"))
def test_prohibited_content_in_any_writable_observation_field_never_writes_candidate(
    tmp_path, field
):
    service, vault = lifecycle_service(tmp_path)
    unsafe = observation(explicit=True).model_copy(update={field: "password = hunter2"})

    with pytest.raises(_lifecycle_module().KnowledgeLifecycleError, match="prohibited content"):
        service.observe(unsafe)

    assert not (vault / "inbox").exists()


@pytest.mark.parametrize("field", ("concept_key", "title", "summary", "source_ref"))
def test_control_characters_in_any_writable_observation_field_never_write_candidate(
    tmp_path, field
):
    service, vault = lifecycle_service(tmp_path)
    unsafe = observation(explicit=True).model_copy(update={field: "unsafe\x00value"})

    with pytest.raises(_lifecycle_module().KnowledgeLifecycleError, match="prohibited content"):
        service.observe(unsafe)

    assert not (vault / "inbox").exists()


@pytest.mark.parametrize(
    "summary",
    (
        "api_key: sk-abcdefghijklmnopqrstuvwxyz123456",
        "-----BEGIN PRIVATE KEY-----",
    ),
)
def test_secret_like_observation_never_writes_candidate(tmp_path, summary):
    service, vault = lifecycle_service(tmp_path)

    with pytest.raises(_lifecycle_module().KnowledgeLifecycleError, match="prohibited content"):
        service.observe(observation(summary=summary, explicit=True))

    assert not (vault / "inbox").exists()


def test_atomic_replacement_failure_preserves_existing_candidate(tmp_path, monkeypatch):
    service, vault = lifecycle_service(tmp_path)
    for index in range(3):
        service.observe(observation(source_ref=f"task-{index}"))
    candidate = vault / "inbox" / "brief-writing.md"
    original = candidate.read_bytes()
    original_replace = Path.replace

    def fail_replace(path: Path, target: Path):
        if target == candidate:
            raise OSError("replace failed")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        service.observe(observation(title="Updated title", source_ref="task-2"))

    assert candidate.read_bytes() == original
    assert not list(candidate.parent.glob("*.tmp"))


def test_identical_retry_repairs_candidate_after_failed_replacement(tmp_path, monkeypatch):
    service, vault = lifecycle_service(tmp_path)
    for index in range(3):
        service.observe(observation(source_ref=f"task-{index}"))
    candidate = vault / "inbox" / "brief-writing.md"
    original_replace = Path.replace
    replacement_attempts = 0

    def fail_first_replace(path: Path, target: Path):
        nonlocal replacement_attempts
        if target == candidate:
            replacement_attempts += 1
            if replacement_attempts == 1:
                raise OSError("replace failed")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_first_replace)
    updated = observation(title="Updated title", source_ref="task-2")

    with pytest.raises(OSError, match="replace failed"):
        service.observe(updated)

    repaired = service.observe(updated)

    assert repaired["status"] == "candidate-updated"
    assert _metadata(candidate)["title"] == "Updated title"

    def unexpected_replace(_path: Path, _target: Path):
        raise AssertionError("byte-identical candidate was replaced")

    monkeypatch.setattr(Path, "replace", unexpected_replace)

    replay = service.observe(updated)

    assert replay["status"] == "candidate-unchanged"


def test_candidate_yaml_is_stably_ordered_and_five_sources_are_high_confidence(tmp_path):
    service, vault = lifecycle_service(tmp_path)
    for index in range(5):
        service.observe(
            observation(
                source_ref=f"task-{index}",
                observed_at=NOW + timedelta(minutes=index),
            )
        )

    candidate = vault / "inbox" / "brief-writing.md"
    content = candidate.read_text(encoding="utf-8")
    metadata = _metadata(candidate)
    ordered_keys = [
        "vesper_id:",
        "vesper_kind:",
        "vesper_status:",
        "vesper_retention:",
        "vesper_scope:",
        "title:",
        "tags:",
        "vesper_observation_count:",
        "vesper_first_observed_at:",
        "vesper_last_observed_at:",
        "vesper_confidence:",
        "vesper_source_refs:",
    ]

    assert [content.index(key) for key in ordered_keys] == sorted(
        content.index(key) for key in ordered_keys
    )
    assert metadata["vesper_confidence"] == "high"
    assert metadata["vesper_first_observed_at"] == "2026-07-28T12:00:00Z"
    assert metadata["vesper_last_observed_at"] == "2026-07-28T12:04:00Z"
    assert metadata["tags"] == ["agent-observed"]


def test_recording_selections_does_not_credit_success_or_mutate_notes(tmp_path):
    service, vault = lifecycle_service(tmp_path)
    _write_note(vault, "memory/active-id.md", knowledge_id="active-id")
    context = knowledge_context("active-id", KnowledgeTier.ACTIVE)
    before = (vault / "memory" / "active-id.md").read_bytes()

    service.record_selections((context, context))

    usage = service.usage("active-id")
    assert usage["selection_count"] == 1
    assert usage["successful_run_count"] == 0
    assert (vault / "memory" / "active-id.md").read_bytes() == before


def test_accepted_run_credits_selected_documents_once_and_records_observations(tmp_path):
    service, vault = lifecycle_service(tmp_path)
    context = knowledge_context("active-id", KnowledgeTier.ACTIVE)
    service.record_selections((context,))

    first = service.accept_run(task(), receipts=(receipt_with_observation(),))
    replay = service.accept_run(task(), receipts=(receipt_with_observation(),))

    usage = service.usage("active-id")
    assert usage["selection_count"] == 1
    assert usage["successful_run_count"] == 1
    assert first == replay
    assert first["knowledge_ids"] == ["active-id"]
    assert first["observations"][0]["concept_key"] == "accepted-observation"
    assert (vault / "inbox" / "accepted-observation.md").is_file()


def test_one_accepted_run_selected_by_three_roles_counts_as_one_success(tmp_path):
    service, vault = lifecycle_service(tmp_path)
    _write_note(
        vault, "archive/memory/archived-id.md", knowledge_id="archived-id", status="archived"
    )
    contexts = tuple(
        knowledge_context("archived-id", KnowledgeTier.ARCHIVE, role=role)
        for role in SpecialistRole
    )
    service.record_selections(contexts)

    service.accept_run(task(), receipts=())

    usage = service.usage("archived-id")
    assert usage["selection_count"] == 3
    assert usage["successful_run_count"] == 1
    assert service.reactivation_plan()["entries"] == []


def test_selection_usage_persists_task_role_and_tier_provenance(tmp_path):
    store = DictStore()
    service = _lifecycle_module().KnowledgeLifecycleService(
        vault_root=tmp_path / "knowledge",
        store=store,
        clock=lambda: NOW,
    )
    context = knowledge_context(
        "archived-id",
        KnowledgeTier.ARCHIVE,
        run_id="run-archive",
        task_id="task-archive",
        role=SpecialistRole.RISK_REVIEW,
    )

    service.record_selections((context,))

    usage = store.get(_lifecycle_module().USAGE_NAMESPACE, "archived-id")
    assert usage is not None
    assert usage["selections"] == [
        {
            "run_id": "run-archive",
            "task_id": "task-archive",
            "role": "v20-risk-review",
            "tier": "archive",
        }
    ]


def test_legacy_role_refs_count_distinct_runs_without_archive_evidence(tmp_path):
    store = DictStore()
    vault = tmp_path / "knowledge"
    service = _lifecycle_module().KnowledgeLifecycleService(
        vault_root=vault,
        store=store,
        clock=lambda: NOW,
    )
    refs = [f"run-legacy:{role.value}" for role in SpecialistRole]
    store.put(
        _lifecycle_module().USAGE_NAMESPACE,
        "archived-id",
        {
            "knowledge_id": "archived-id",
            "selection_refs": refs,
            "successful_refs": refs,
            "last_successful_use": "2026-07-28T12:00:00Z",
        },
    )
    _write_note(
        vault, "archive/memory/archived-id.md", knowledge_id="archived-id", status="archived"
    )

    assert service.usage("archived-id")["successful_run_count"] == 1
    assert service.reactivation_plan()["entries"] == []


def test_unaccepted_work_never_creates_success_credit_or_observations(tmp_path):
    service, vault = lifecycle_service(tmp_path)
    service.record_selections((knowledge_context("active-id", KnowledgeTier.ACTIVE),))

    usage = service.usage("active-id")

    assert usage["successful_run_count"] == 0
    assert not (vault / "inbox").exists()


def test_compaction_excludes_pinned_notes_and_never_moves_files(tmp_path):
    service, vault = lifecycle_service(tmp_path)
    _write_note(vault, "memory/pinned-policy.md", knowledge_id="pinned-policy", retention="pinned")
    _write_note(vault, "memory/review-note.md", knowledge_id="review-note")
    before = sorted(path.relative_to(vault) for path in vault.rglob("*.md"))

    proposal = service.compaction_plan(target_lines=0)

    assert "pinned-policy" not in {item["knowledge_id"] for item in proposal["entries"]}
    assert proposal["projected_active_lines"] == 9
    assert sorted(path.relative_to(vault) for path in vault.rglob("*.md")) == before


def test_compaction_rejects_invalid_targets_without_mutation(tmp_path):
    service, vault = lifecycle_service(tmp_path)
    note = _write_note(vault, "memory/active-id.md", knowledge_id="active-id")
    before = note.read_bytes()

    for target in (-1, 3001):
        with pytest.raises(_lifecycle_module().KnowledgeLifecycleError, match="target lines"):
            service.compaction_plan(target_lines=target)

    assert note.read_bytes() == before


def test_compaction_plans_a_valid_active_corpus_over_the_hard_admission_limit(tmp_path):
    service, vault = lifecycle_service(tmp_path)
    _write_note(
        vault,
        "memory/over-budget.md",
        knowledge_id="over-budget",
        body="\n".join("line" for _ in range(3_000)),
    )

    proposal = service.compaction_plan()

    assert proposal["active_lines"] > 3_000
    assert proposal["projected_active_lines"] == 0
    assert [item["knowledge_id"] for item in proposal["entries"]] == ["over-budget"]


def test_compaction_ranks_superseded_over_overdue_contested_and_low_use(tmp_path):
    service, vault = lifecycle_service(tmp_path)
    _write_note(vault, "memory/legacy-policy.md", knowledge_id="legacy-policy")
    _write_note(
        vault,
        "memory/current-policy.md",
        knowledge_id="current-policy",
        supersedes=("legacy-policy",),
    )
    _write_note(
        vault,
        "memory/overdue.md",
        knowledge_id="overdue",
        review_after=NOW.date() - timedelta(days=1),
    )
    _write_note(vault, "memory/contested.md", knowledge_id="contested", contested=True)

    proposal = service.compaction_plan(target_lines=0)

    assert [item["knowledge_id"] for item in proposal["entries"]] == [
        "legacy-policy",
        "overdue",
        "contested",
        "current-policy",
    ]
    assert proposal["entries"][0]["reasons"] == ["superseded"]
    assert proposal["entries"][1]["reasons"] == ["review-overdue"]
    assert proposal["entries"][2]["reasons"] == ["contested"]
    assert proposal["entries"][3]["reasons"] == ["low-success-use"]


def test_compaction_proposal_hashes_and_line_impacts_are_deterministic(tmp_path):
    service, vault = lifecycle_service(tmp_path)
    _write_note(vault, "memory/active-id.md", knowledge_id="active-id")

    first = service.compaction_plan(target_lines=0)
    second = service.compaction_plan(target_lines=0)

    assert first["proposal_id"] == second["proposal_id"]
    assert first["entries"] == second["entries"]
    assert first["entries"][0]["source_path"] == "memory/active-id.md"
    assert first["entries"][0]["source_sha256"]
    assert first["entries"][0]["lines_released"] == 9


def test_reactivation_proposal_credits_repeated_archived_use_without_file_moves(tmp_path):
    service, vault = lifecycle_service(tmp_path)
    archived = knowledge_document("archived-id", KnowledgeTier.ARCHIVE, lines=12)
    _write_note(
        vault, "archive/memory/archived-id.md", knowledge_id="archived-id", status="archived"
    )
    before = sorted(path.relative_to(vault) for path in vault.rglob("*.md"))

    for index in range(3):
        run_id = f"run-{index}"
        context = KnowledgeContext(
            run_id=run_id,
            task_id="task-001",
            repository_revision="abc1234",
            created_at=NOW + timedelta(minutes=index),
            role=SpecialistRole.DEVELOPMENT,
            documents=(archived,),
        )
        service.record_selections((context,))
        service.accept_run(task(run_id=run_id), receipts=())

    proposal = service.reactivation_plan()

    assert proposal["entries"][0]["knowledge_id"] == "archived-id"
    assert proposal["entries"][0]["successful_run_count"] == 3
    assert proposal["entries"][0]["fits_without_displacement"] is True
    assert sorted(path.relative_to(vault) for path in vault.rglob("*.md")) == before


def test_reactivation_ignores_successes_selected_while_note_was_active(tmp_path):
    service, vault = lifecycle_service(tmp_path)
    _write_note(
        vault, "archive/memory/archived-id.md", knowledge_id="archived-id", status="archived"
    )
    for index, tier in enumerate(
        (KnowledgeTier.ACTIVE, KnowledgeTier.ACTIVE, KnowledgeTier.ARCHIVE)
    ):
        run_id = f"run-{index}"
        service.record_selections((knowledge_context("archived-id", tier, run_id=run_id),))
        service.accept_run(task(run_id=run_id), receipts=())

    assert service.usage("archived-id")["successful_run_count"] == 3
    assert service.reactivation_plan()["entries"] == []


def test_post_acceptance_archive_selections_cannot_reclassify_success(tmp_path):
    store = DictStore()
    vault = tmp_path / "knowledge"
    service = _lifecycle_module().KnowledgeLifecycleService(
        vault_root=vault,
        store=store,
        clock=lambda: NOW,
    )
    _write_note(
        vault, "archive/memory/archived-id.md", knowledge_id="archived-id", status="archived"
    )
    for index in range(3):
        run_id = f"run-{index}"
        service.record_selections(
            (knowledge_context("archived-id", KnowledgeTier.ACTIVE, run_id=run_id),)
        )
        service.accept_run(task(run_id=run_id), receipts=())

    for index in range(3):
        run_id = f"run-{index}"
        service.record_selections(
            (knowledge_context("archived-id", KnowledgeTier.ARCHIVE, run_id=run_id),)
        )
        service.accept_run(task(run_id=run_id), receipts=())

    assert service.usage("archived-id")["successful_run_count"] == 3
    usage = store.get(_lifecycle_module().USAGE_NAMESPACE, "archived-id")
    assert usage is not None
    assert [item["tiers"] for item in usage["successful_runs"]] == [
        ["active"],
        ["active"],
        ["active"],
    ]
    assert service.reactivation_plan()["entries"] == []


def test_concurrent_observations_preserve_every_distinct_source(tmp_path):
    class CoordinatedStore(DictStore):
        def __init__(self) -> None:
            super().__init__()
            self._coordination_lock = threading.Lock()
            self._armed = False
            self._reads = 0
            self.first_read = threading.Event()
            self.second_read = threading.Event()
            self.release_first = threading.Event()

        def arm(self) -> None:
            self._armed = True

        def get(self, namespace, key):
            value = super().get(namespace, key)
            if not self._armed or namespace != _lifecycle_module().OBSERVATION_NAMESPACE:
                return value
            with self._coordination_lock:
                self._reads += 1
                read_number = self._reads
            if read_number == 1:
                self.first_read.set()
                assert self.release_first.wait(timeout=5)
            elif read_number == 2:
                self.second_read.set()
            return value

    vault = tmp_path / "knowledge"
    store = CoordinatedStore()
    first_service = _lifecycle_module().KnowledgeLifecycleService(
        vault_root=vault,
        store=store,
        clock=lambda: NOW,
    )
    second_service = _lifecycle_module().KnowledgeLifecycleService(
        vault_root=vault,
        store=store,
        clock=lambda: NOW,
    )
    first_service.observe(observation(source_ref="task-0"))
    store.arm()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(first_service.observe, observation(source_ref="task-1"))
        assert store.first_read.wait(timeout=5)
        second = executor.submit(second_service.observe, observation(source_ref="task-2"))
        store.second_read.wait(timeout=1)
        store.release_first.set()
        first.result(timeout=5)
        second.result(timeout=5)

    candidate = vault / "inbox" / "brief-writing.md"
    assert _metadata(candidate)["vesper_source_refs"] == ["task-0", "task-1", "task-2"]
