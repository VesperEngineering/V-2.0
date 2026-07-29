from __future__ import annotations

import hashlib
import importlib
import stat
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from vesper.platform.contracts import (
    KnowledgeRetention,
    KnowledgeScope,
    KnowledgeTier,
    SpecialistRole,
    TaskRequest,
)
from vesper.platform.persistence import PlatformPaths, open_persistence


def _write_note(
    vault: Path,
    relative_path: str,
    *,
    knowledge_id: str = "split-adjustment-policy",
    kind: str = "memory",
    status: str = "approved",
    retention: str | None = "adaptive",
    scope: str = "shared",
    title: str = "Split adjustment policy",
    tags: tuple[str, ...] = ("prices", "splits"),
    body: str = "Raw prices must be split-adjusted before feature computation.",
    supersedes: tuple[str, ...] = (),
    review_after: str | None = None,
    contested: bool | None = None,
) -> Path:
    path = vault / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    tag_lines = "\n".join(f"  - {tag}" for tag in tags)
    metadata = (
        f"vesper_id: {knowledge_id}",
        f"vesper_kind: {kind}",
        f"vesper_status: {status}",
        *((f"vesper_retention: {retention}",) if retention is not None else ()),
        f"vesper_scope: {scope}",
        *(("vesper_supersedes:", *(f"  - {item}" for item in supersedes)) if supersedes else ()),
        *((f"vesper_review_after: {review_after}",) if review_after is not None else ()),
        *((f"vesper_contested: {str(contested).lower()}",) if contested is not None else ()),
    )
    path.write_text(
        "\n".join(
            (
                "---",
                *metadata,
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


def test_corpus_separates_active_and_archived_and_counts_complete_active_lines(tmp_path):
    vault = tmp_path / "knowledge"
    active = _write_note(
        vault,
        "memory/active.md",
        retention="pinned",
        supersedes=("prior-split-policy",),
        review_after="2026-08-01",
        contested=True,
    )
    _write_note(
        vault,
        "archive/skills/archived.md",
        knowledge_id="archived-procedure",
        kind="skill",
        status="archived",
        retention="adaptive",
    )

    corpus = _knowledge_module().load_knowledge_corpus(vault)

    assert [item.knowledge_id for item in corpus.active] == ["split-adjustment-policy"]
    assert [item.knowledge_id for item in corpus.archived] == ["archived-procedure"]
    assert corpus.active_lines == len(active.read_text(encoding="utf-8").splitlines())
    assert corpus.active[0].supersedes == ("prior-split-policy",)
    assert str(corpus.active[0].review_after) == "2026-08-01"
    assert corpus.active[0].contested is True
    assert _knowledge_module().load_approved_documents(vault) == corpus.active


def test_active_corpus_over_3000_lines_fails_before_sync_mutates_store(tmp_path):
    vault = tmp_path / "knowledge"
    _write_note(vault, "memory/too-large.md", body="\n".join("line" for _ in range(3000)))
    paths = PlatformPaths.below(tmp_path / "platform")

    with open_persistence(paths) as persistence:
        service = _service(vault, persistence)
        with pytest.raises(_knowledge_module().KnowledgeSyncError, match=r"3,000.*active lines"):
            service.sync()
        assert service.status()["documents"] == 0


def test_planning_inventory_validates_over_budget_corpus_without_relaxing_admission(tmp_path):
    vault = tmp_path / "knowledge"
    _write_note(vault, "memory/too-large.md", body="\n".join("line" for _ in range(3_000)))

    inventory = _knowledge_module().load_knowledge_inventory(vault)

    assert inventory.active_lines > 3_000
    with pytest.raises(_knowledge_module().KnowledgeSyncError, match=r"3,000.*active lines"):
        _knowledge_module().load_approved_documents(vault)


def test_active_corpus_at_3000_lines_is_admitted(tmp_path):
    vault = tmp_path / "knowledge"
    note = _write_note(
        vault,
        "memory/exact-budget.md",
        body="\n".join("line" for _ in range(2987)),
    )

    assert len(note.read_text(encoding="utf-8").splitlines()) == 3_000

    corpus = _knowledge_module().load_knowledge_corpus(vault)

    assert corpus.active_lines == 3_000


def test_duplicate_ids_across_active_archive_and_inbox_fail_before_admission(tmp_path):
    vault = tmp_path / "knowledge"
    _write_note(vault, "memory/active.md", knowledge_id="active-id")
    _write_note(
        vault,
        "archive/skills/archived.md",
        knowledge_id="shared-id",
        kind="skill",
        status="archived",
    )
    _write_note(vault, "inbox/candidate.md", knowledge_id="shared-id", status="candidate")

    with pytest.raises(
        _knowledge_module().KnowledgeSyncError, match=r"duplicate vesper_id.*shared-id"
    ):
        _knowledge_module().load_knowledge_corpus(vault)


def test_admitted_note_requires_retention(tmp_path):
    vault = tmp_path / "knowledge"
    _write_note(vault, "memory/missing-retention.md", retention=None)

    with pytest.raises(
        _knowledge_module().KnowledgeSyncError,
        match=r"memory/missing-retention\.md.*vesper_retention",
    ):
        _knowledge_module().load_knowledge_corpus(vault)


def test_archived_note_cannot_use_pinned_retention(tmp_path):
    vault = tmp_path / "knowledge"
    _write_note(
        vault,
        "archive/memory/pinned.md",
        status="archived",
        retention="pinned",
    )

    with pytest.raises(_knowledge_module().KnowledgeSyncError, match=r"archive/memory/pinned\.md"):
        _knowledge_module().load_knowledge_corpus(vault)


def test_archived_note_must_match_its_kind_directory(tmp_path):
    vault = tmp_path / "knowledge"
    _write_note(
        vault,
        "archive/memory/wrong-kind.md",
        kind="skill",
        status="archived",
    )

    with pytest.raises(
        _knowledge_module().KnowledgeSyncError,
        match=r"archive/memory/wrong-kind\.md.*vesper_kind must be 'memory'",
    ):
        _knowledge_module().load_knowledge_corpus(vault)


def test_linked_archived_note_fails_closed(tmp_path, monkeypatch):
    vault = tmp_path / "knowledge"
    note = _write_note(vault, "archive/memory/linked.md", status="archived")
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: path == note or original_is_symlink(path),
    )

    with pytest.raises(
        _knowledge_module().KnowledgeSyncError,
        match=r"archive/memory/linked\.md.*linked knowledge notes",
    ):
        _knowledge_module().load_knowledge_corpus(vault)


def test_readme_is_excluded_from_corpus_roots(tmp_path):
    vault = tmp_path / "knowledge"
    _write_note(vault, "memory/README.md")

    corpus = _knowledge_module().load_knowledge_corpus(vault)

    assert corpus.documents == ()


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


class _FailOnceAfterStoreMutation:
    def __init__(self, store) -> None:
        self._store = store
        self._failed = False

    def __getattr__(self, name):
        return getattr(self._store, name)

    def put(self, namespace, key, value) -> None:
        self._store.put(namespace, key, value)
        if not self._failed:
            self._failed = True
            raise RuntimeError("injected Store mutation failure")

    def replace(self, namespace, values) -> None:
        self._store.replace(namespace, values)
        if not self._failed:
            self._failed = True
            raise RuntimeError("injected Store mutation failure")


class _FailOnceAfterIndexRebuild:
    def __init__(self, index) -> None:
        self._index = index
        self._failed = False

    def __getattr__(self, name):
        return getattr(self._index, name)

    def rebuild(self, documents) -> None:
        self._index.rebuild(documents)
        if not self._failed:
            self._failed = True
            raise RuntimeError("injected FTS rebuild failure")


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
        assert service.status() == {
            "documents": 1,
            "active": 1,
            "archived": 0,
            "memory": 1,
            "skill": 0,
            "active_lines": len(changed.read_text(encoding="utf-8").splitlines()),
            "active_line_limit": 3_000,
        }
        assert service.search(SpecialistRole.PRODUCT, "obsolete procedure") == ()
        assert service.search(SpecialistRole.PRODUCT, "unique correction")[0].content.endswith(
            "adjusted prices."
        )


def test_store_mutation_failure_restores_previous_store_and_fts_corpora(tmp_path):
    vault = tmp_path / "knowledge"
    original = _write_note(
        vault,
        "memory/original.md",
        knowledge_id="stable",
        body="Original stable policy token.",
    )

    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        service = _service(vault, persistence)
        service.sync()
        previous_store = persistence.store.search(
            ("knowledge", "obsidian", "documents"), limit=100_000
        )
        original.write_text(
            original.read_text(encoding="utf-8").replace("Original", "Replacement"),
            encoding="utf-8",
        )
        _write_note(
            vault,
            "memory/added.md",
            knowledge_id="added",
            body="Newly added policy token.",
        )
        service._store = _FailOnceAfterStoreMutation(persistence.store)

        with pytest.raises(RuntimeError, match="injected Store mutation failure"):
            service.sync()

        assert (
            persistence.store.search(("knowledge", "obsidian", "documents"), limit=100_000)
            == previous_store
        )
        assert [
            item.knowledge_id for item in service.search(SpecialistRole.PRODUCT, "original stable")
        ] == ["stable"]
        assert service.search(SpecialistRole.PRODUCT, "replacement newly") == ()


def test_fts_rebuild_failure_restores_previous_store_and_fts_corpora(tmp_path):
    vault = tmp_path / "knowledge"
    original = _write_note(
        vault,
        "memory/original.md",
        knowledge_id="stable",
        body="Original stable policy token.",
    )

    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        service = _service(vault, persistence)
        service.sync()
        previous_store = persistence.store.search(
            ("knowledge", "obsidian", "documents"), limit=100_000
        )
        original.write_text(
            original.read_text(encoding="utf-8").replace("Original", "Replacement"),
            encoding="utf-8",
        )
        service._index = _FailOnceAfterIndexRebuild(persistence.knowledge_index)

        with pytest.raises(RuntimeError, match="injected FTS rebuild failure"):
            service.sync()

        assert (
            persistence.store.search(("knowledge", "obsidian", "documents"), limit=100_000)
            == previous_store
        )
        assert [
            item.knowledge_id for item in service.search(SpecialistRole.PRODUCT, "original stable")
        ] == ["stable"]
        assert service.search(SpecialistRole.PRODUCT, "replacement") == ()


def test_fts_failure_restores_divergent_prior_fts_corpus_exactly(tmp_path):
    vault = tmp_path / "knowledge"
    original = _write_note(
        vault,
        "memory/original.md",
        knowledge_id="stable",
        body="Original stable policy token.",
    )
    divergent_vault = tmp_path / "divergent-knowledge"
    _write_note(
        divergent_vault,
        "archive/memory/fts-only.md",
        knowledge_id="fts-only",
        status="archived",
        title="Independent FTS sentinel",
        tags=("fts-marker",),
        body="Divergent searchable corpus token.",
    )

    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        service = _service(vault, persistence)
        service.sync()
        persistence.knowledge_index.rebuild(
            _knowledge_module().load_knowledge_corpus(divergent_vault).documents
        )
        previous_store = persistence.store.search(
            ("knowledge", "obsidian", "documents"), limit=100_000
        )
        previous_fts_rows = persistence.knowledge_index.snapshot()
        scopes = (KnowledgeScope.SHARED.value,)
        queries = ("independent sentinel", "fts marker", "divergent corpus", "original stable")
        previous_fts = {
            query: persistence.knowledge_index.search(query, scopes=scopes, limit=25)
            for query in queries
        }
        original.write_text(
            original.read_text(encoding="utf-8").replace("Original", "Replacement"),
            encoding="utf-8",
        )
        service._index = _FailOnceAfterIndexRebuild(persistence.knowledge_index)

        with pytest.raises(RuntimeError, match="injected FTS rebuild failure"):
            service.sync()

        assert (
            persistence.store.search(("knowledge", "obsidian", "documents"), limit=100_000)
            == previous_store
        )
        assert persistence.knowledge_index.snapshot() == previous_fts_rows
        assert {
            query: persistence.knowledge_index.search(query, scopes=scopes, limit=25)
            for query in queries
        } == previous_fts


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


def test_search_returns_active_and_archive_hits_in_deterministic_tier_order(tmp_path):
    vault = tmp_path / "knowledge"
    for knowledge_id in ("active-b", "active-a"):
        _write_note(
            vault,
            f"memory/{knowledge_id}.md",
            knowledge_id=knowledge_id,
            title="Recovery evidence",
            body="Rare recovery evidence.",
        )
    for knowledge_id in ("archive-b", "archive-a"):
        _write_note(
            vault,
            f"archive/memory/{knowledge_id}.md",
            knowledge_id=knowledge_id,
            status="archived",
            title="Recovery evidence",
            body="Rare recovery evidence.",
        )
    paths = PlatformPaths.below(tmp_path / "platform")

    with open_persistence(paths) as persistence:
        service = _service(vault, persistence)
        service.sync()
        hits = persistence.knowledge_index.search(
            "rare recovery evidence",
            scopes=(KnowledgeScope.SHARED.value,),
            limit=25,
        )
        documents = service.search(
            SpecialistRole.DEVELOPMENT,
            "rare recovery evidence",
        )
        status = service.status()

    assert [(hit.knowledge_id, hit.tier) for hit in hits] == [
        ("active-a", KnowledgeTier.ACTIVE),
        ("active-b", KnowledgeTier.ACTIVE),
        ("archive-a", KnowledgeTier.ARCHIVE),
        ("archive-b", KnowledgeTier.ARCHIVE),
    ]
    assert all(isinstance(hit.score, float) for hit in hits)
    assert [item.knowledge_id for item in documents] == [
        "active-a",
        "active-b",
        "archive-a",
        "archive-b",
    ]
    assert status == {
        "documents": 4,
        "active": 2,
        "archived": 2,
        "memory": 4,
        "skill": 0,
        "active_lines": sum(
            len((vault / "memory" / f"{knowledge_id}.md").read_text(encoding="utf-8").splitlines())
            for knowledge_id in ("active-a", "active-b")
        ),
        "active_line_limit": 3_000,
    }


def test_archive_search_never_crosses_role_scope(tmp_path):
    vault = tmp_path / "knowledge"
    _write_note(
        vault,
        "archive/memory/shared.md",
        knowledge_id="archive-shared",
        status="archived",
        body="Archived recovery evidence.",
    )
    _write_note(
        vault,
        "archive/memory/development.md",
        knowledge_id="archive-development",
        status="archived",
        scope="v20-development",
        body="Archived recovery evidence.",
    )
    _write_note(
        vault,
        "archive/memory/risk.md",
        knowledge_id="archive-risk",
        status="archived",
        scope="v20-risk-review",
        body="Archived recovery evidence.",
    )

    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        service = _service(vault, persistence)
        service.sync()
        development = service.search(SpecialistRole.DEVELOPMENT, "archived recovery evidence")
        product = service.search(SpecialistRole.PRODUCT, "archived recovery evidence")

    assert {item.knowledge_id for item in development} == {
        "archive-development",
        "archive-shared",
    }
    assert [item.knowledge_id for item in product] == ["archive-shared"]


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
    original = _write_note(vault, "memory/original.md", knowledge_id="stable")
    paths = PlatformPaths.below(tmp_path / "platform")

    with open_persistence(paths) as persistence:
        service = _service(vault, persistence)
        service.sync()
        _write_note(vault, "skills/duplicate.md", knowledge_id="stable", kind="skill")

        with pytest.raises(_knowledge_module().KnowledgeSyncError, match="duplicate vesper_id"):
            service.sync()

        assert service.status() == {
            "documents": 1,
            "active": 1,
            "archived": 0,
            "memory": 1,
            "skill": 0,
            "active_lines": len(original.read_text(encoding="utf-8").splitlines()),
            "active_line_limit": 3_000,
        }
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


def test_snapshot_allows_at_most_two_archived_documents_inside_existing_bounds(tmp_path):
    vault = tmp_path / "knowledge"
    for index in range(4):
        _write_note(
            vault,
            f"archive/memory/archive-{index}.md",
            knowledge_id=f"archive-{index}",
            status="archived",
            retention="adaptive",
            body=f"rare recovery evidence {index} " + ("archive " * 100),
        )
    _write_note(
        vault,
        "memory/active.md",
        knowledge_id="active",
        body="recovery evidence",
    )

    with open_persistence(PlatformPaths.below(tmp_path / "state")) as persistence:
        service = _service(vault, persistence)
        service.sync()
        service.snapshot(_task(objective="rare recovery evidence"))
        context = service.context("run-knowledge", SpecialistRole.DEVELOPMENT)

    assert context is not None
    assert "active" in {item.knowledge_id for item in context.documents}
    assert sum(item.tier is KnowledgeTier.ARCHIVE for item in context.documents) == 2
    assert len(context.documents) <= 5
    assert sum(len(item.content) for item in context.documents) <= 8_000


def test_archived_snapshot_is_immutable_when_archive_changes_later(tmp_path):
    vault = tmp_path / "knowledge"
    note = _write_note(
        vault,
        "archive/memory/original.md",
        knowledge_id="stable-archive-snapshot",
        status="archived",
        body="Original archived recovery guidance.",
    )
    paths = PlatformPaths.below(tmp_path / "platform")
    task = _task(objective="archived recovery guidance")

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
        current = service.search(SpecialistRole.PRODUCT, "replacement recovery")

    assert context is not None
    assert context.documents[0].tier is KnowledgeTier.ARCHIVE
    assert context.documents[0].content.endswith("Original archived recovery guidance.")
    assert current[0].content.endswith("Replacement archived recovery guidance.")


def test_historical_run_without_snapshot_does_not_read_current_vault(tmp_path):
    vault = tmp_path / "knowledge"
    _write_note(vault, "memory/current.md")
    paths = PlatformPaths.below(tmp_path / "platform")

    with open_persistence(paths) as persistence:
        service = _service(vault, persistence)
        service.sync()

        assert service.context("historical-run", SpecialistRole.PRODUCT) is None
