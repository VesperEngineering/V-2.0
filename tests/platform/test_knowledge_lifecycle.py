from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest
import yaml

from vesper.platform.contracts import (
    KnowledgeKind,
    KnowledgeObservation,
    KnowledgeScope,
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
        return ()

    def delete(self, namespace, key) -> None:
        self.values.pop((namespace, key), None)


def _lifecycle_module():
    from vesper.platform import knowledge_lifecycle

    return knowledge_lifecycle


def lifecycle_service(tmp_path: Path):
    vault = tmp_path / "knowledge"
    return _lifecycle_module().KnowledgeLifecycleService(vault_root=vault, store=DictStore()), vault


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
) -> Path:
    path = vault / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            (
                "---",
                f"vesper_id: {knowledge_id}",
                f"vesper_kind: {kind}",
                f"vesper_status: {status}",
                f"vesper_retention: {retention}",
                "vesper_scope: v20-development",
                "title: Existing note",
                "---",
                "Existing body.",
                "",
            )
        ),
        encoding="utf-8",
    )
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
