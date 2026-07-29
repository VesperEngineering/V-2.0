"""Read-only Obsidian Markdown ingestion for controller-owned knowledge."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import stat
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

import yaml
from pydantic import ValidationError

from .contracts import (
    KnowledgeContext,
    KnowledgeDocument,
    KnowledgeKind,
    KnowledgeRetention,
    KnowledgeScope,
    KnowledgeTier,
    SpecialistRole,
    TaskRequest,
)


class KnowledgeSyncError(RuntimeError):
    """The dedicated V20 knowledge vault failed deterministic validation."""


_MAX_ACTIVE_LINES = 3_000
_KNOWLEDGE_ROOTS = (
    ("memory", KnowledgeKind.MEMORY, KnowledgeTier.ACTIVE, "approved"),
    ("skills", KnowledgeKind.SKILL, KnowledgeTier.ACTIVE, "approved"),
    ("archive/memory", KnowledgeKind.MEMORY, KnowledgeTier.ARCHIVE, "archived"),
    ("archive/skills", KnowledgeKind.SKILL, KnowledgeTier.ARCHIVE, "archived"),
)
_REQUIRED_FIELDS = (
    "vesper_id",
    "vesper_kind",
    "vesper_retention",
    "vesper_scope",
    "title",
)
_DOCUMENT_NAMESPACE = ("knowledge", "obsidian", "documents")
_SEARCH_CANDIDATE_LIMIT = 25
_MAX_ARCHIVE_RESULTS = 2
_MAX_CONTEXT_DOCUMENTS = 5
_MAX_CONTEXT_CHARACTERS = 8_000
_KnowledgeIndexRow = tuple[object, object, object, object, object, object, object]


@dataclass(frozen=True, slots=True)
class KnowledgeCorpus:
    active: tuple[KnowledgeDocument, ...]
    archived: tuple[KnowledgeDocument, ...]
    active_lines: int

    @property
    def documents(self) -> tuple[KnowledgeDocument, ...]:
        return self.active + self.archived


@dataclass(frozen=True, slots=True)
class KnowledgeSearchHit:
    knowledge_id: str
    tier: KnowledgeTier
    score: float


class KnowledgeStorePort(Protocol):
    def put(self, namespace: tuple[str, ...], key: str, value: Mapping[str, object]) -> None: ...

    def get(self, namespace: tuple[str, ...], key: str) -> Mapping[str, object] | None: ...

    def search(
        self,
        namespace: tuple[str, ...],
        *,
        limit: int = 10,
    ) -> tuple[Mapping[str, object], ...]: ...

    def delete(self, namespace: tuple[str, ...], key: str) -> None: ...

    def replace(
        self,
        namespace: tuple[str, ...],
        values: Mapping[str, Mapping[str, object]],
    ) -> None: ...


class SqliteKnowledgeIndex:
    """Disposable local FTS5 index over Store-backed knowledge documents."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._lock = threading.RLock()

    def setup(self) -> None:
        with self._lock:
            columns = self._connection.execute("PRAGMA table_info(v20_knowledge_fts)").fetchall()
            if columns and "tier" not in {str(column[1]) for column in columns}:
                self._connection.execute("DROP TABLE v20_knowledge_fts")
            self._connection.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS v20_knowledge_fts USING fts5("
                "knowledge_id UNINDEXED, kind UNINDEXED, scope UNINDEXED, tier UNINDEXED, "
                "title, tags, content, tokenize='porter unicode61')"
            )

    def rebuild(self, documents: tuple[KnowledgeDocument, ...]) -> None:
        rows = tuple(
            (
                item.knowledge_id,
                item.kind.value,
                item.scope.value,
                item.tier.value,
                item.title,
                " ".join(item.tags),
                item.content,
            )
            for item in documents
        )
        self.restore(rows)

    def snapshot(self) -> tuple[_KnowledgeIndexRow, ...]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT knowledge_id, kind, scope, tier, title, tags, content "
                "FROM v20_knowledge_fts ORDER BY rowid"
            ).fetchall()
        return tuple(tuple(row) for row in rows)

    def restore(self, rows: tuple[_KnowledgeIndexRow, ...]) -> None:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute("DELETE FROM v20_knowledge_fts")
                self._connection.executemany(
                    "INSERT INTO v20_knowledge_fts "
                    "(knowledge_id, kind, scope, tier, title, tags, content) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    rows,
                )
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
            self._connection.execute("COMMIT")

    def search(
        self,
        query: str,
        *,
        scopes: tuple[str, ...],
        limit: int = 5,
    ) -> tuple[KnowledgeSearchHit, ...]:
        tokens = tuple(re.findall(r"[A-Za-z0-9_]+", query.casefold()))
        if not tokens:
            return ()
        expression = " OR ".join(f'"{token}"' for token in tokens)
        scope_parameters = ", ".join("?" for _ in scopes)
        statement = (
            "SELECT knowledge_id, tier, "
            "bm25(v20_knowledge_fts, 0.0, 0.0, 0.0, 0.0, 5.0, 2.0, 1.0) "
            "FROM v20_knowledge_fts "
            f"WHERE v20_knowledge_fts MATCH ? AND scope IN ({scope_parameters}) "
            "ORDER BY bm25(v20_knowledge_fts, 0.0, 0.0, 0.0, 0.0, 5.0, 2.0, 1.0), "
            "CASE tier WHEN 'active' THEN 0 ELSE 1 END, knowledge_id LIMIT ?"
        )
        with self._lock:
            rows = self._connection.execute(
                statement,
                (expression, *scopes, limit),
            ).fetchall()
        return tuple(
            KnowledgeSearchHit(
                knowledge_id=str(row[0]),
                tier=KnowledgeTier(row[1]),
                score=float(row[2]),
            )
            for row in rows
        )

    def close(self) -> None:
        self._connection.close()


class ObsidianKnowledgeService:
    """Synchronize canonical Markdown and retrieve approved scoped knowledge."""

    def __init__(
        self,
        *,
        vault_root: Path,
        store: KnowledgeStorePort,
        index: SqliteKnowledgeIndex,
    ) -> None:
        self._vault_root = vault_root
        self._store = store
        self._index = index

    def sync(self) -> dict[str, int]:
        corpus = load_knowledge_corpus(self._vault_root)
        documents = corpus.documents
        current = {item.knowledge_id: item for item in documents}
        existing_values = {}
        existing = {}
        for raw in self._store.search(_DOCUMENT_NAMESPACE, limit=100_000):
            item = _parse_document(raw)
            existing_values[item.knowledge_id] = dict(raw)
            existing[item.knowledge_id] = item
        existing_index_rows = self._index.snapshot()
        added = current.keys() - existing.keys()
        deleted = existing.keys() - current.keys()
        updated = {key for key in current.keys() & existing.keys() if current[key] != existing[key]}
        unchanged = current.keys() & existing.keys() - updated
        current_values = {key: item.model_dump(mode="json") for key, item in current.items()}
        try:
            self._store.replace(_DOCUMENT_NAMESPACE, current_values)
            self._index.rebuild(documents)
        except Exception as sync_error:
            rollback_errors = []
            try:
                self._store.replace(_DOCUMENT_NAMESPACE, existing_values)
            except Exception as exc:
                rollback_errors.append(f"Store rollback failed: {exc}")
            try:
                self._index.restore(existing_index_rows)
            except Exception as exc:
                rollback_errors.append(f"FTS rollback failed: {exc}")
            if rollback_errors:
                detail = "; ".join(rollback_errors)
                raise KnowledgeSyncError(
                    f"knowledge sync failed and could not restore the previous corpus: {detail}"
                ) from sync_error
            raise
        return {
            "added": len(added),
            "updated": len(updated),
            "unchanged": len(unchanged),
            "deleted": len(deleted),
        }

    def search(
        self,
        role: SpecialistRole,
        query: str,
        *,
        limit: int = 5,
    ) -> tuple[KnowledgeDocument, ...]:
        hits = self._index.search(
            query,
            scopes=(KnowledgeScope.SHARED.value, role.value),
            limit=_SEARCH_CANDIDATE_LIMIT,
        )
        documents = []
        archive_count = 0
        for hit in hits:
            if len(documents) >= limit:
                break
            raw = self._store.get(_DOCUMENT_NAMESPACE, hit.knowledge_id)
            if raw is not None:
                document = _parse_document(raw)
                if document.tier is KnowledgeTier.ARCHIVE:
                    if archive_count >= _MAX_ARCHIVE_RESULTS:
                        continue
                    archive_count += 1
                documents.append(document)
        return tuple(documents)

    def status(self) -> dict[str, int]:
        documents = tuple(
            _parse_document(raw) for raw in self._store.search(_DOCUMENT_NAMESPACE, limit=100_000)
        )
        return {
            "documents": len(documents),
            "active": sum(item.tier is KnowledgeTier.ACTIVE for item in documents),
            "archived": sum(item.tier is KnowledgeTier.ARCHIVE for item in documents),
            "memory": sum(item.kind is KnowledgeKind.MEMORY for item in documents),
            "skill": sum(item.kind is KnowledgeKind.SKILL for item in documents),
            "active_lines": sum(
                item.source_line_count for item in documents if item.tier is KnowledgeTier.ACTIVE
            ),
            "active_line_limit": _MAX_ACTIVE_LINES,
        }

    def snapshot(self, task: TaskRequest) -> tuple[KnowledgeContext, ...]:
        contexts = []
        namespace = ("runs", task.run_id, "knowledge")
        for role in SpecialistRole:
            selected = []
            character_count = 0
            for document in self.search(
                role,
                task.objective,
                limit=_MAX_CONTEXT_DOCUMENTS,
            ):
                next_count = character_count + len(document.content)
                if next_count > _MAX_CONTEXT_CHARACTERS:
                    continue
                selected.append(document)
                character_count = next_count
            context = KnowledgeContext(
                run_id=task.run_id,
                task_id=task.task_id,
                repository_revision=task.repository_revision,
                created_at=task.created_at,
                role=role,
                documents=tuple(selected),
            )
            self._store.put(namespace, role.value, context.model_dump(mode="json"))
            contexts.append(context)
        return tuple(contexts)

    def context(self, run_id: str, role: SpecialistRole) -> KnowledgeContext | None:
        raw = self._store.get(("runs", run_id, "knowledge"), role.value)
        if raw is None:
            return None
        return KnowledgeContext.model_validate_json(json.dumps(raw))


def _parse_document(raw: Mapping[str, object]) -> KnowledgeDocument:
    return KnowledgeDocument.model_validate_json(json.dumps(raw))


def _is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(metadata, "st_file_attributes", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)


def _first_link_component(root: Path, path: Path) -> Path | None:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return None
    current = root
    if _is_link_like(current):
        return current
    for part in relative.parts:
        current = current / part
        if _is_link_like(current):
            return current
    return None


def load_approved_documents(vault_root: Path) -> tuple[KnowledgeDocument, ...]:
    """Load only active approved notes for existing retrieval callers."""
    return load_knowledge_corpus(vault_root).active


def load_knowledge_corpus(vault_root: Path) -> KnowledgeCorpus:
    """Validate the complete canonical corpus before exposing active notes."""
    corpus = load_knowledge_inventory(vault_root)
    if corpus.active_lines > _MAX_ACTIVE_LINES:
        per_note_counts = ", ".join(
            f"{item.source_path}={item.source_line_count}" for item in corpus.active
        )
        raise KnowledgeSyncError(
            f"active corpus exceeds {_MAX_ACTIVE_LINES:,} active lines: total={corpus.active_lines}, "
            f"overage={corpus.active_lines - _MAX_ACTIVE_LINES}, notes={per_note_counts}"
        )
    return corpus


def load_knowledge_inventory(vault_root: Path) -> KnowledgeCorpus:
    """Validate and inventory the complete corpus without applying the active admission limit."""
    vault = vault_root.resolve()
    if not vault_root.exists() or not vault_root.is_dir():
        raise KnowledgeSyncError(f"knowledge vault does not exist: {vault_root}")
    if _is_link_like(vault_root):
        raise KnowledgeSyncError("knowledge vault cannot be a linked knowledge path")

    documents: dict[str, KnowledgeDocument] = {}
    active = []
    archived = []
    for directory_name, expected_kind, tier, status in _KNOWLEDGE_ROOTS:
        directory = vault / directory_name
        if not directory.exists():
            continue
        if not directory.is_dir() or _first_link_component(vault, directory) is not None:
            raise KnowledgeSyncError(f"{directory_name}: linked knowledge paths are not allowed")
        for path in sorted(directory.rglob("*.md")):
            if path.name.casefold() == "readme.md":
                continue
            relative = path.relative_to(vault).as_posix()
            document = _load_note(vault, path, relative, expected_kind, tier, status)
            if document is None:
                continue
            if document.knowledge_id in documents:
                raise KnowledgeSyncError(
                    f"duplicate vesper_id {document.knowledge_id!r}: {relative}"
                )
            documents[document.knowledge_id] = document
            (active if tier is KnowledgeTier.ACTIVE else archived).append(document)

    _inventory_inbox_ids(vault, documents)
    active = tuple(sorted(active, key=lambda item: item.knowledge_id))
    archived = tuple(sorted(archived, key=lambda item: item.knowledge_id))
    active_lines = sum(item.source_line_count for item in active)
    return KnowledgeCorpus(active=active, archived=archived, active_lines=active_lines)


def _inventory_inbox_ids(vault: Path, documents: Mapping[str, KnowledgeDocument]) -> None:
    inbox = vault / "inbox"
    if not inbox.exists():
        return
    if not inbox.is_dir() or _first_link_component(vault, inbox) is not None:
        raise KnowledgeSyncError("inbox: linked knowledge paths are not allowed")
    known_ids = set(documents)
    for path in sorted(inbox.rglob("*.md")):
        if path.name.casefold() == "readme.md":
            continue
        relative = path.relative_to(vault).as_posix()
        parsed = _read_note_metadata(vault, path, relative)
        if parsed is None:
            continue
        _, _, metadata = parsed
        knowledge_id = metadata.get("vesper_id")
        if not isinstance(knowledge_id, str) or not knowledge_id.strip():
            continue
        if knowledge_id in known_ids:
            raise KnowledgeSyncError(f"duplicate vesper_id {knowledge_id!r}: {relative}")
        known_ids.add(knowledge_id)


def _load_note(
    vault: Path,
    path: Path,
    relative: str,
    expected_kind: KnowledgeKind,
    expected_tier: KnowledgeTier,
    expected_status: str,
) -> KnowledgeDocument | None:
    parsed = _read_note_metadata(vault, path, relative)
    if parsed is None:
        return None
    source, lines, metadata = parsed
    if metadata.get("vesper_status") != expected_status:
        return None
    for field in _REQUIRED_FIELDS:
        if field not in metadata:
            raise KnowledgeSyncError(f"{relative}: admitted note requires {field}")
    if metadata["vesper_kind"] != expected_kind.value:
        raise KnowledgeSyncError(
            f"{relative}: vesper_kind must be {expected_kind.value!r} in this directory"
        )
    body = "\n".join(lines[_frontmatter_boundary(lines) + 1 :]).strip()
    tags = metadata.get("tags", ())
    if tags is None:
        tags = ()
    if not isinstance(tags, (list, tuple)):
        raise KnowledgeSyncError(f"{relative}: tags must be a list")
    supersedes = metadata.get("vesper_supersedes", ())
    if supersedes is None:
        supersedes = ()
    if not isinstance(supersedes, (list, tuple)):
        raise KnowledgeSyncError(f"{relative}: vesper_supersedes must be a list")
    try:
        return KnowledgeDocument(
            knowledge_id=metadata["vesper_id"],
            kind=KnowledgeKind(metadata["vesper_kind"]),
            scope=KnowledgeScope(metadata["vesper_scope"]),
            approval_status=expected_status,
            tier=expected_tier,
            retention=KnowledgeRetention(metadata["vesper_retention"]),
            title=metadata["title"],
            tags=tuple(tags),
            content=body,
            source_path=relative,
            source_sha256=hashlib.sha256(source).hexdigest(),
            source_line_count=len(lines),
            supersedes=tuple(supersedes),
            review_after=metadata.get("vesper_review_after"),
            contested=metadata.get("vesper_contested", False),
        )
    except (ValidationError, TypeError, ValueError) as exc:
        raise KnowledgeSyncError(f"{relative}: admitted note metadata is invalid: {exc}") from exc


def _read_note_metadata(
    vault: Path,
    path: Path,
    relative: str,
) -> tuple[bytes, list[str], dict[str, object]] | None:
    if _first_link_component(vault, path) is not None or not path.resolve().is_relative_to(vault):
        raise KnowledgeSyncError(f"{relative}: linked knowledge notes are not allowed")
    source = path.read_bytes()
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise KnowledgeSyncError(f"{relative}: note must be valid UTF-8") from exc
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    boundary = _frontmatter_boundary(lines, relative)
    try:
        raw_metadata = yaml.safe_load("\n".join(lines[1:boundary]))
    except yaml.YAMLError as exc:
        raise KnowledgeSyncError(f"{relative}: frontmatter is invalid YAML") from exc
    if not isinstance(raw_metadata, Mapping):
        raise KnowledgeSyncError(f"{relative}: frontmatter must be a mapping")
    return source, lines, dict(raw_metadata)


def _frontmatter_boundary(lines: list[str], relative: str = "note") -> int:
    try:
        return next(index for index, line in enumerate(lines[1:], start=1) if line == "---")
    except StopIteration as exc:
        raise KnowledgeSyncError(f"{relative}: frontmatter is not terminated") from exc
