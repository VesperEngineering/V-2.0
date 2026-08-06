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
    KnowledgeScope,
    SpecialistRole,
    TaskRequest,
)


class KnowledgeSyncError(RuntimeError):
    """The dedicated V20 knowledge vault failed deterministic validation."""


_APPROVED_STATUS = "approved"
_SCANNED_ROOTS = {
    "memory": KnowledgeKind.MEMORY,
    "skills": KnowledgeKind.SKILL,
}
_REQUIRED_FIELDS = (
    "vesper_id",
    "vesper_kind",
    "vesper_scope",
    "title",
)
_DOCUMENT_NAMESPACE = ("knowledge", "obsidian", "documents")
_MAX_CONTEXT_DOCUMENTS = 5
_MAX_CONTEXT_CHARACTERS = 8_000
ACTIVE_KNOWLEDGE_LINE_LIMIT = 3_000


@dataclass(frozen=True, slots=True)
class ActiveKnowledgeBudget:
    line_limit: int
    total_lines: int
    per_note: tuple[tuple[str, int], ...]
    compaction_candidates: tuple[str, ...]

    @property
    def over_by(self) -> int:
        return max(0, self.total_lines - self.line_limit)


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


class SqliteKnowledgeIndex:
    """Disposable local FTS5 index over Store-backed knowledge documents."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._lock = threading.RLock()

    def setup(self) -> None:
        with self._lock:
            self._connection.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS v20_knowledge_fts USING fts5("
                "knowledge_id UNINDEXED, kind UNINDEXED, scope UNINDEXED, "
                "title, tags, content, tokenize='porter unicode61')"
            )

    def rebuild(self, documents: tuple[KnowledgeDocument, ...]) -> None:
        rows = (
            (
                item.knowledge_id,
                item.kind.value,
                item.scope.value,
                item.title,
                " ".join(item.tags),
                item.content,
            )
            for item in documents
        )
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute("DELETE FROM v20_knowledge_fts")
                self._connection.executemany(
                    "INSERT INTO v20_knowledge_fts "
                    "(knowledge_id, kind, scope, title, tags, content) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
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
    ) -> tuple[str, ...]:
        tokens = tuple(re.findall(r"[A-Za-z0-9_]+", query.casefold()))
        if not tokens:
            return ()
        expression = " OR ".join(f'"{token}"' for token in tokens)
        scope_parameters = ", ".join("?" for _ in scopes)
        statement = (
            "SELECT knowledge_id FROM v20_knowledge_fts "
            f"WHERE v20_knowledge_fts MATCH ? AND scope IN ({scope_parameters}) "
            "ORDER BY bm25(v20_knowledge_fts, 0.0, 0.0, 0.0, 5.0, 2.0, 1.0), "
            "knowledge_id LIMIT ?"
        )
        with self._lock:
            rows = self._connection.execute(
                statement,
                (expression, *scopes, limit),
            ).fetchall()
        return tuple(str(row[0]) for row in rows)

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
        active_line_limit: int = ACTIVE_KNOWLEDGE_LINE_LIMIT,
    ) -> None:
        if active_line_limit < 1:
            raise ValueError("active knowledge line limit must be positive")
        self._vault_root = vault_root
        self._store = store
        self._index = index
        self._active_line_limit = active_line_limit

    def sync(self) -> dict[str, int]:
        documents = load_approved_documents(self._vault_root)
        budget = assess_active_budget(
            self._vault_root,
            line_limit=self._active_line_limit,
            documents=documents,
        )
        if budget.over_by:
            candidates = ", ".join(budget.compaction_candidates) or "none"
            raise KnowledgeSyncError(
                "active knowledge line budget exceeded: "
                f"{budget.total_lines}/{budget.line_limit} lines, "
                f"over by {budget.over_by}; compaction candidates: {candidates}"
            )
        current = {item.knowledge_id: item for item in documents}
        existing = {
            item.knowledge_id: item
            for item in (
                _parse_document(raw)
                for raw in self._store.search(_DOCUMENT_NAMESPACE, limit=100_000)
            )
        }
        added = current.keys() - existing.keys()
        deleted = existing.keys() - current.keys()
        updated = {key for key in current.keys() & existing.keys() if current[key] != existing[key]}
        unchanged = current.keys() & existing.keys() - updated
        for key in sorted(added | updated):
            self._store.put(
                _DOCUMENT_NAMESPACE,
                key,
                current[key].model_dump(mode="json"),
            )
        for key in sorted(deleted):
            self._store.delete(_DOCUMENT_NAMESPACE, key)
        self._index.rebuild(documents)
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
        identifiers = self._index.search(
            query,
            scopes=(KnowledgeScope.SHARED.value, role.value),
            limit=limit,
        )
        documents = []
        for identifier in identifiers:
            raw = self._store.get(_DOCUMENT_NAMESPACE, identifier)
            if raw is not None:
                documents.append(_parse_document(raw))
        return tuple(documents)

    def status(self) -> dict[str, int]:
        documents = tuple(
            _parse_document(raw) for raw in self._store.search(_DOCUMENT_NAMESPACE, limit=100_000)
        )
        return {
            "documents": len(documents),
            "memory": sum(item.kind is KnowledgeKind.MEMORY for item in documents),
            "skill": sum(item.kind is KnowledgeKind.SKILL for item in documents),
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
    """Load approved notes from the dedicated memory and skills directories."""
    vault = vault_root.resolve()
    if not vault_root.exists() or not vault_root.is_dir():
        raise KnowledgeSyncError(f"knowledge vault does not exist: {vault_root}")
    if _is_link_like(vault_root):
        raise KnowledgeSyncError("knowledge vault cannot be a linked knowledge path")

    documents: dict[str, KnowledgeDocument] = {}
    for directory_name, expected_kind in _SCANNED_ROOTS.items():
        directory = vault / directory_name
        if not directory.exists():
            continue
        if not directory.is_dir() or _first_link_component(vault, directory) is not None:
            raise KnowledgeSyncError(f"{directory_name}: linked knowledge paths are not allowed")
        for path in sorted(directory.rglob("*.md")):
            relative = path.relative_to(vault).as_posix()
            document = _load_note(vault, path, relative, expected_kind)
            if document is None:
                continue
            if document.knowledge_id in documents:
                raise KnowledgeSyncError(
                    f"duplicate vesper_id {document.knowledge_id!r}: {relative}"
                )
            documents[document.knowledge_id] = document
    return tuple(documents[key] for key in sorted(documents))


def assess_active_budget(
    vault_root: Path,
    *,
    line_limit: int = ACTIVE_KNOWLEDGE_LINE_LIMIT,
    documents: tuple[KnowledgeDocument, ...] | None = None,
) -> ActiveKnowledgeBudget:
    """Count approved source lines and return non-binding compaction candidates."""
    if line_limit < 1:
        raise ValueError("active knowledge line limit must be positive")
    loaded = load_approved_documents(vault_root) if documents is None else documents
    per_note: list[tuple[str, int]] = []
    adaptive: list[tuple[str, int]] = []
    for document in loaded:
        path = vault_root.resolve() / document.source_path
        source = path.read_text(encoding="utf-8")
        line_count = len(source.splitlines())
        per_note.append((document.source_path, line_count))
        metadata = _read_frontmatter(path, document.source_path)
        if metadata.get("vesper_retention", "adaptive") != "pinned":
            adaptive.append((document.source_path, line_count))
    total_lines = sum(lines for _, lines in per_note)
    candidates = ()
    if total_lines > line_limit:
        candidates = tuple(
            path for path, _ in sorted(adaptive, key=lambda item: (-item[1], item[0]))
        )
    return ActiveKnowledgeBudget(
        line_limit=line_limit,
        total_lines=total_lines,
        per_note=tuple(sorted(per_note)),
        compaction_candidates=candidates,
    )


def _read_frontmatter(path: Path, relative: str) -> Mapping[str, object]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise KnowledgeSyncError(f"{relative}: approved note has no frontmatter")
    try:
        boundary = next(index for index, line in enumerate(lines[1:], start=1) if line == "---")
    except StopIteration as exc:
        raise KnowledgeSyncError(f"{relative}: frontmatter is not terminated") from exc
    raw = yaml.safe_load("\n".join(lines[1:boundary]))
    if not isinstance(raw, Mapping):
        raise KnowledgeSyncError(f"{relative}: frontmatter must be a mapping")
    return raw


def _load_note(
    vault: Path,
    path: Path,
    relative: str,
    expected_kind: KnowledgeKind,
) -> KnowledgeDocument | None:
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
    try:
        boundary = next(index for index, line in enumerate(lines[1:], start=1) if line == "---")
    except StopIteration as exc:
        raise KnowledgeSyncError(f"{relative}: frontmatter is not terminated") from exc
    try:
        raw_metadata = yaml.safe_load("\n".join(lines[1:boundary]))
    except yaml.YAMLError as exc:
        raise KnowledgeSyncError(f"{relative}: frontmatter is invalid YAML") from exc
    if not isinstance(raw_metadata, Mapping):
        raise KnowledgeSyncError(f"{relative}: frontmatter must be a mapping")
    metadata = dict(raw_metadata)
    if metadata.get("vesper_status") != _APPROVED_STATUS:
        return None
    for field in _REQUIRED_FIELDS:
        if field not in metadata:
            raise KnowledgeSyncError(f"{relative}: approved note requires {field}")
    if metadata["vesper_kind"] != expected_kind.value:
        raise KnowledgeSyncError(
            f"{relative}: vesper_kind must be {expected_kind.value!r} in this directory"
        )
    body = "\n".join(lines[boundary + 1 :]).strip()
    tags = metadata.get("tags", ())
    if tags is None:
        tags = ()
    if not isinstance(tags, (list, tuple)):
        raise KnowledgeSyncError(f"{relative}: tags must be a list")
    try:
        return KnowledgeDocument(
            knowledge_id=metadata["vesper_id"],
            kind=KnowledgeKind(metadata["vesper_kind"]),
            scope=KnowledgeScope(metadata["vesper_scope"]),
            title=metadata["title"],
            tags=tuple(tags),
            content=body,
            source_path=relative,
            source_sha256=hashlib.sha256(source).hexdigest(),
        )
    except (ValidationError, TypeError, ValueError) as exc:
        raise KnowledgeSyncError(f"{relative}: approved note metadata is invalid: {exc}") from exc
