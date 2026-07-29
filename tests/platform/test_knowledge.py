from __future__ import annotations

import hashlib
import importlib
import stat
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from vesper.platform.contracts import KnowledgeRetention, KnowledgeTier, SpecialistRole, TaskRequest
from vesper.platform.persistence import PlatformPaths, open_persistence


def _write_note(
    vault: Path,
    relative_path: str,
    *,
    knowledge_id: str = "split-adjustment-policy",
    kind: str = "memory",
    status: str = "approved",
    scope: str = "shared",
    title: str = "Split adjustment policy",
    tags: tuple[str, ...] = ("prices", "splits"),
    body: str = "Raw prices must be split-adjusted before feature computation.",
) -> Path:
    path = vault / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    tag_lines = "\n".join(f"  - {tag}" for tag in tags)
    path.write_text(
        "\n".join(
            (
                "---",
                f"vesper_id: {knowledge_id}",
                f"vesper_kind: {kind}",
                f"vesper_status: {status}",
                f"vesper_scope: {scope}",
                f"title: {title}",
                "tags:",
                tag_lines,
                "---",
                f"# {title}",
                "",
                body,
                "",
            )
        ),
        encoding="utf-8",
    )
    return path


def _knowledge_module():
    return importlib.import_module("vesper.platform.knowledge")


def test_approved_memory_note_becomes_typed_document_with_source_provenance(tmp_path):
    vault = tmp_path / "knowledge"
    note = _write_note(vault, "memory/split-adjustments.md")

    documents = _knowledge_module().load_approved_documents(vault)

    assert len(documents) == 1
    document = documents[0]
    assert document.knowledge_id == "split-adjustment-policy"
    assert document.kind.value == "memory"
    assert document.scope.value == "shared"
    assert document.approval_status == "approved"
    assert document.tier is KnowledgeTier.ACTIVE
    assert document.retention is KnowledgeRetention.ADAPTIVE
    assert document.title == "Split adjustment policy"
    assert document.tags == ("prices", "splits")
    assert document.source_path == "memory/split-adjustments.md"
    assert document.source_sha256 == hashlib.sha256(note.read_bytes()).hexdigest()
    assert document.source_line_count == len(note.read_text(encoding="utf-8").splitlines())
    assert document.content == (
        "# Split adjustment policy\n\nRaw prices must be split-adjusted before feature computation."
    )


def test_approved_skill_note_is_typed_as_role_scoped_procedure(tmp_path):
    vault = tmp_path / "knowledge"
    _write_note(
        vault,
        "skills/reproduce-failure.md",
        knowledge_id="reproduce-failure-first",
        kind="skill",
        scope="v20-development",
        title="Reproduce failures before repair",
        tags=("testing",),
        body="Write a failing test before changing production code.",
    )

    document = _knowledge_module().load_approved_documents(vault)[0]

    assert document.kind.value == "skill"
    assert document.scope.value == "v20-development"
    assert document.title == "Reproduce failures before repair"


def test_candidate_and_out_of_scope_markdown_never_enter_approved_documents(tmp_path):
    vault = tmp_path / "knowledge"
    _write_note(
        vault,
        "memory/candidate.md",
        knowledge_id="candidate-memory",
        status="candidate",
    )
    _write_note(
        vault,
        "inbox/proposal.md",
        knowledge_id="inbox-proposal",
        status="approved",
    )
    (vault / "README.md").write_text("# V20 Knowledge\n", encoding="utf-8")

    assert _knowledge_module().load_approved_documents(vault) == ()


def test_malformed_approved_note_fails_with_relative_source_path(tmp_path):
    vault = tmp_path / "knowledge"
    note = _write_note(vault, "memory/malformed.md")
    note.write_text(
        note.read_text(encoding="utf-8").replace("vesper_scope: shared\n", ""),
        encoding="utf-8",
    )

    with pytest.raises(
        _knowledge_module().KnowledgeSyncError,
        match=r"memory/malformed\.md.*vesper_scope",
    ):
        _knowledge_module().load_approved_documents(vault)


def test_invalid_approved_scope_fails_with_relative_source_path(tmp_path):
    vault = tmp_path / "knowledge"
    _write_note(vault, "memory/invalid-scope.md", scope="not-a-scope")

    with pytest.raises(
        _knowledge_module().KnowledgeSyncError,
        match=r"memory/invalid-scope\.md.*metadata is invalid",
    ):
        _knowledge_module().load_approved_documents(vault)


def test_duplicate_approved_ids_fail_before_documents_are_returned(tmp_path):
    vault = tmp_path / "knowledge"
    _write_note(vault, "memory/first.md", knowledge_id="duplicate-id")
    _write_note(vault, "skills/second.md", knowledge_id="duplicate-id", kind="skill")

    with pytest.raises(
        _knowledge_module().KnowledgeSyncError,
        match=r"duplicate vesper_id.*duplicate-id",
    ):
        _knowledge_module().load_approved_documents(vault)


def test_invalid_utf8_in_scanned_note_fails_closed(tmp_path):
    vault = tmp_path / "knowledge"
    note = vault / "memory" / "invalid.md"
    note.parent.mkdir(parents=True)
    note.write_bytes(b"---\nvesper_status: approved\n---\n\xff")

    with pytest.raises(
        _knowledge_module().KnowledgeSyncError,
        match=r"memory/invalid\.md.*UTF-8",
    ):
        _knowledge_module().load_approved_documents(vault)


def test_linked_scanned_note_fails_closed(tmp_path, monkeypatch):
    vault = tmp_path / "knowledge"
    note = _write_note(vault, "memory/linked.md")
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: path == note or original_is_symlink(path),
    )

    with pytest.raises(
        _knowledge_module().KnowledgeSyncError,
        match=r"memory/linked\.md.*linked knowledge notes",
    ):
        _knowledge_module().load_approved_documents(vault)


def test_reparse_point_component_fails_closed(tmp_path, monkeypatch):
    vault = tmp_path / "knowledge"
    _write_note(vault, "memory/linked.md")
    memory_directory = vault / "memory"
    original_lstat = Path.lstat

    def lstat_with_reparse_point(path, *args, **kwargs):
        result = original_lstat(path, *args, **kwargs)
        if path == memory_directory:
            return SimpleNamespace(
                st_mode=result.st_mode,
                st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT,
            )
        return result

    monkeypatch.setattr(Path, "lstat", lstat_with_reparse_point)

    with pytest.raises(
        _knowledge_module().KnowledgeSyncError,
        match=r"memory.*linked knowledge paths",
    ):
        _knowledge_module().load_approved_documents(vault)


def test_missing_vault_fails_instead_of_silently_indexing_nothing(tmp_path):
    vault = tmp_path / "missing"

    with pytest.raises(_knowledge_module().KnowledgeSyncError, match="vault does not exist"):
        _knowledge_module().load_approved_documents(vault)


def _service(vault: Path, persistence):
    return _knowledge_module().ObsidianKnowledgeService(
        vault_root=vault,
        store=persistence.store,
        index=persistence.knowledge_index,
    )


def _task(*, objective: str = "Review evidence and split adjustment policy") -> TaskRequest:
    return TaskRequest(
        run_id="run-knowledge",
        task_id="task-knowledge",
        repository_revision="revision-knowledge",
        created_at=datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc),
        objective=objective,
        repository_root="C:/workspace",
        acceptance_checks=("pytest",),
    )


def test_sync_persists_approved_documents_and_search_survives_reopen(tmp_path):
    vault = tmp_path / "knowledge"
    _write_note(vault, "memory/splits.md")
    paths = PlatformPaths.below(tmp_path / "platform")

    with open_persistence(paths) as persistence:
        report = _service(vault, persistence).sync()

        assert report == {"added": 1, "updated": 0, "unchanged": 0, "deleted": 0}

    with open_persistence(paths) as reopened:
        results = _service(vault, reopened).search(
            SpecialistRole.DEVELOPMENT,
            "split adjusted prices",
        )

    assert [item.knowledge_id for item in results] == ["split-adjustment-policy"]


def test_repeated_sync_is_idempotent_and_changed_or_deleted_notes_are_reconciled(tmp_path):
    vault = tmp_path / "knowledge"
    changed = _write_note(vault, "memory/changed.md", knowledge_id="changed")
    removed = _write_note(
        vault,
        "skills/removed.md",
        knowledge_id="removed",
        kind="skill",
        body="Use the obsolete procedure.",
    )
    paths = PlatformPaths.below(tmp_path / "platform")

    with open_persistence(paths) as persistence:
        service = _service(vault, persistence)
        assert service.sync() == {
            "added": 2,
            "updated": 0,
            "unchanged": 0,
            "deleted": 0,
        }
        assert service.sync() == {
            "added": 0,
            "updated": 0,
            "unchanged": 2,
            "deleted": 0,
        }
        changed.write_text(
            changed.read_text(encoding="utf-8").replace(
                "Raw prices must be split-adjusted before feature computation.",
                "New unique correction policy applies to adjusted prices.",
            ),
            encoding="utf-8",
        )
        removed.unlink()

        assert service.sync() == {
            "added": 0,
            "updated": 1,
            "unchanged": 0,
            "deleted": 1,
        }
        assert service.status() == {"documents": 1, "memory": 1, "skill": 0}
        assert service.search(SpecialistRole.PRODUCT, "obsolete procedure") == ()
        assert service.search(SpecialistRole.PRODUCT, "unique correction")[0].content.endswith(
            "adjusted prices."
        )


def test_search_combines_shared_and_role_scope_without_cross_role_leakage(tmp_path):
    vault = tmp_path / "knowledge"
    _write_note(
        vault,
        "skills/shared.md",
        knowledge_id="shared-evidence",
        kind="skill",
        title="Shared evidence procedure",
        body="Inspect evidence provenance.",
    )
    _write_note(
        vault,
        "skills/development.md",
        knowledge_id="development-evidence",
        kind="skill",
        scope="v20-development",
        title="Development evidence procedure",
        body="Reproduce evidence failures.",
    )
    _write_note(
        vault,
        "memory/risk.md",
        knowledge_id="risk-evidence",
        scope="v20-risk-review",
        title="Risk evidence memory",
        body="Independently review evidence ownership.",
    )
    paths = PlatformPaths.below(tmp_path / "platform")

    with open_persistence(paths) as persistence:
        service = _service(vault, persistence)
        service.sync()

        product_ids = {
            item.knowledge_id for item in service.search(SpecialistRole.PRODUCT, "evidence")
        }
        development_ids = {
            item.knowledge_id for item in service.search(SpecialistRole.DEVELOPMENT, "evidence")
        }
        risk_ids = {
            item.knowledge_id for item in service.search(SpecialistRole.RISK_REVIEW, "evidence")
        }

    assert product_ids == {"shared-evidence"}
    assert development_ids == {"shared-evidence", "development-evidence"}
    assert risk_ids == {"shared-evidence", "risk-evidence"}


def test_punctuation_only_search_returns_no_documents(tmp_path):
    vault = tmp_path / "knowledge"
    _write_note(vault, "memory/splits.md")
    paths = PlatformPaths.below(tmp_path / "platform")

    with open_persistence(paths) as persistence:
        service = _service(vault, persistence)
        service.sync()

        assert service.search(SpecialistRole.DEVELOPMENT, "--- ???") == ()


def test_failed_duplicate_sync_leaves_previous_store_and_index_unchanged(tmp_path):
    vault = tmp_path / "knowledge"
    _write_note(vault, "memory/original.md", knowledge_id="stable")
    paths = PlatformPaths.below(tmp_path / "platform")

    with open_persistence(paths) as persistence:
        service = _service(vault, persistence)
        service.sync()
        _write_note(vault, "skills/duplicate.md", knowledge_id="stable", kind="skill")

        with pytest.raises(_knowledge_module().KnowledgeSyncError, match="duplicate vesper_id"):
            service.sync()

        assert service.status() == {"documents": 1, "memory": 1, "skill": 0}
        assert service.search(SpecialistRole.PRODUCT, "split adjustment")[0].knowledge_id == (
            "stable"
        )


def test_snapshot_persists_bounded_role_context_bound_to_the_run(tmp_path):
    vault = tmp_path / "knowledge"
    for index in range(7):
        _write_note(
            vault,
            f"memory/evidence-{index}.md",
            knowledge_id=f"evidence-{index}",
            title=f"Evidence procedure {index}",
            body=f"Evidence {index} " + ("bounded " * 180),
        )
    paths = PlatformPaths.below(tmp_path / "platform")
    task = _task(objective="evidence bounded")

    with open_persistence(paths) as persistence:
        service = _service(vault, persistence)
        service.sync()

        contexts = service.snapshot(task)
        development = service.context(task.run_id, SpecialistRole.DEVELOPMENT)

    assert {context.role for context in contexts} == set(SpecialistRole)
    assert development is not None
    assert development.run_id == task.run_id
    assert development.task_id == task.task_id
    assert development.repository_revision == task.repository_revision
    assert development.created_at == task.created_at
    assert len(development.documents) == 5
    assert sum(len(item.content) for item in development.documents) <= 8_000


def test_snapshot_is_immutable_when_vault_and_search_index_change_later(tmp_path):
    vault = tmp_path / "knowledge"
    note = _write_note(
        vault,
        "memory/original.md",
        knowledge_id="stable-snapshot",
        body="Original evidence guidance.",
    )
    paths = PlatformPaths.below(tmp_path / "platform")
    task = _task(objective="evidence guidance")

    with open_persistence(paths) as persistence:
        service = _service(vault, persistence)
        service.sync()
        service.snapshot(task)
        note.write_text(
            note.read_text(encoding="utf-8").replace("Original", "Replacement"),
            encoding="utf-8",
        )
        service.sync()

        context = service.context(task.run_id, SpecialistRole.PRODUCT)
        current = service.search(SpecialistRole.PRODUCT, "replacement")

    assert context is not None
    assert context.documents[0].content.endswith("Original evidence guidance.")
    assert current[0].content.endswith("Replacement evidence guidance.")


def test_historical_run_without_snapshot_does_not_read_current_vault(tmp_path):
    vault = tmp_path / "knowledge"
    _write_note(vault, "memory/current.md")
    paths = PlatformPaths.below(tmp_path / "platform")

    with open_persistence(paths) as persistence:
        service = _service(vault, persistence)
        service.sync()

        assert service.context("historical-run", SpecialistRole.PRODUCT) is None
