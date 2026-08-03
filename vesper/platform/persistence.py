"""Local SQLite checkpointer, LangGraph Store, and evidence lifecycle."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Mapping, Sequence

from .evidence import FilesystemEvidenceStore
from .knowledge import SqliteKnowledgeIndex
from .runtime_env import enforce_offline_runtime_environment

enforce_offline_runtime_environment()

from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: E402
from langgraph.store.base import _validate_namespace  # noqa: E402
from langgraph.store.sqlite import SqliteStore  # noqa: E402


@dataclass(frozen=True, slots=True)
class PlatformPaths:
    root: Path
    checkpoint_db: Path
    store_db: Path
    knowledge_index_db: Path
    evidence_root: Path

    @classmethod
    def below(cls, root: Path) -> PlatformPaths:
        resolved = root.resolve()
        return cls(
            root=resolved,
            checkpoint_db=resolved / "checkpoints.sqlite3",
            store_db=resolved / "store.sqlite3",
            knowledge_index_db=resolved / "knowledge-index.sqlite3",
            evidence_root=resolved / "evidence",
        )


@dataclass(frozen=True, slots=True)
class AtomicCreatePlan:
    value: Mapping[str, object]
    linked_items: Sequence[tuple[tuple[str, ...], str, Mapping[str, object]]] = ()


class LangGraphStoreAdapter:
    """Thread-safe JSON mapping facade over the local LangGraph Store."""

    def __init__(self, store: SqliteStore) -> None:
        self._store = store
        self._lock = threading.RLock()

    @staticmethod
    def _prefix(namespace: tuple[str, ...]) -> str:
        _validate_namespace(namespace)
        return ".".join(namespace)

    def put(self, namespace: tuple[str, ...], key: str, value: Mapping[str, object]) -> None:
        with self._lock:
            self._store.put(namespace, key, dict(value))

    def get(self, namespace: tuple[str, ...], key: str) -> Mapping[str, object] | None:
        with self._lock:
            item = self._store.get(namespace, key)
        return None if item is None else item.value

    def delete(self, namespace: tuple[str, ...], key: str) -> None:
        with self._lock:
            self._store.delete(namespace, key)

    def search(
        self,
        namespace: tuple[str, ...],
        *,
        filter: Mapping[str, object] | None = None,
        limit: int = 10,
    ) -> tuple[Mapping[str, object], ...]:
        with self._lock:
            items = self._store.search(
                namespace,
                filter=None if filter is None else dict(filter),
                limit=limit,
            )
        return tuple(item.value for item in items)

    def search_exact_records(
        self,
        namespace: tuple[str, ...],
    ) -> tuple[tuple[str, Mapping[str, object]], ...]:
        """Return keyed items from exactly one namespace, excluding prefix matches."""

        prefix = self._prefix(namespace)
        with self._lock, self._store.lock:
            rows = self._store.conn.execute(
                "SELECT key, value FROM store WHERE prefix = ? ORDER BY key",
                (prefix,),
            ).fetchall()
        return tuple((str(key), json.loads(value)) for key, value in rows)

    def scan_subtree_records(
        self,
        namespace: tuple[str, ...],
    ) -> tuple[tuple[str, str, Mapping[str, object]], ...]:
        """Return prefix, key, and value for one namespace subtree."""

        prefix = self._prefix(namespace)
        with self._lock, self._store.lock:
            rows = self._store.conn.execute(
                "SELECT prefix, key, value FROM store "
                "WHERE prefix = ? OR substr(prefix, 1, length(?) + 1) = ? || '.' "
                "ORDER BY prefix, key",
                (prefix, prefix, prefix),
            ).fetchall()
        return tuple(
            (str(item_prefix), str(key), json.loads(value)) for item_prefix, key, value in rows
        )

    def atomic_replace(
        self,
        namespace: tuple[str, ...],
        mutation: Callable[
            [tuple[tuple[str, Mapping[str, object]], ...]],
            tuple[str, Mapping[str, object]],
        ],
    ) -> Mapping[str, object]:
        """Select and replace one existing namespace item in one SQLite transaction."""

        prefix = self._prefix(namespace)
        connection = self._store.conn
        with self._lock, self._store.lock:
            try:
                connection.execute("BEGIN IMMEDIATE")
                rows = connection.execute(
                    "SELECT key, value FROM store WHERE prefix = ?", (prefix,)
                ).fetchall()
                records = tuple((str(key), json.loads(value)) for key, value in rows)
                key, value = mutation(records)
                updated = connection.execute(
                    "UPDATE store SET value = ?, updated_at = CURRENT_TIMESTAMP "
                    "WHERE prefix = ? AND key = ?",
                    (
                        json.dumps(dict(value), sort_keys=True, separators=(",", ":")),
                        prefix,
                        key,
                    ),
                )
                if updated.rowcount != 1:
                    raise RuntimeError("atomic store replacement target is missing")
                connection.commit()
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
        return dict(value)

    def atomic_create(
        self,
        namespace: tuple[str, ...],
        key: str,
        factory: Callable[
            [
                tuple[tuple[str, Mapping[str, object]], ...],
                Mapping[str, object] | None,
            ],
            AtomicCreatePlan,
        ],
    ) -> tuple[Mapping[str, object], bool]:
        """Create one item and upsert linked items in one locked transaction."""

        prefix = self._prefix(namespace)
        connection = self._store.conn
        with self._lock, self._store.lock:
            try:
                connection.execute("BEGIN IMMEDIATE")
                rows = connection.execute(
                    "SELECT key, value FROM store WHERE prefix = ?", (prefix,)
                ).fetchall()
                records = tuple((str(item_key), json.loads(value)) for item_key, value in rows)
                existing = next((value for item_key, value in records if item_key == key), None)
                created = existing is None
                plan = factory(records, existing)
                value = dict(plan.value)
                if created:
                    connection.execute(
                        "INSERT INTO store (prefix, key, value) VALUES (?, ?, ?)",
                        (
                            prefix,
                            key,
                            json.dumps(value, sort_keys=True, separators=(",", ":")),
                        ),
                    )
                for linked_namespace, linked_key, linked_value in plan.linked_items:
                    connection.execute(
                        "INSERT INTO store (prefix, key, value) VALUES (?, ?, ?) "
                        "ON CONFLICT(prefix, key) DO UPDATE SET "
                        "value = excluded.value, updated_at = CURRENT_TIMESTAMP",
                        (
                            self._prefix(linked_namespace),
                            linked_key,
                            json.dumps(dict(linked_value), sort_keys=True, separators=(",", ":")),
                        ),
                    )
                connection.commit()
            except Exception:
                if connection.in_transaction:
                    connection.rollback()
                raise
        return value, created


@dataclass(slots=True)
class PlatformPersistence:
    paths: PlatformPaths
    checkpointer: SqliteSaver
    langgraph_store: SqliteStore
    store: LangGraphStoreAdapter
    knowledge_index: SqliteKnowledgeIndex
    evidence: FilesystemEvidenceStore
    _checkpoint_connection: sqlite3.Connection
    _store_connection: sqlite3.Connection

    def close(self) -> None:
        self.knowledge_index.close()
        self._store_connection.close()
        self._checkpoint_connection.close()


@contextmanager
def open_persistence(paths: PlatformPaths) -> Iterator[PlatformPersistence]:
    paths.root.mkdir(parents=True, exist_ok=True)
    checkpoint_connection = sqlite3.connect(
        paths.checkpoint_db,
        check_same_thread=False,
        timeout=30,
    )
    store_connection = sqlite3.connect(
        paths.store_db,
        check_same_thread=False,
        isolation_level=None,
        timeout=30,
    )
    knowledge_index_connection = sqlite3.connect(
        paths.knowledge_index_db,
        check_same_thread=False,
        isolation_level=None,
        timeout=30,
    )
    checkpointer = SqliteSaver(checkpoint_connection)
    langgraph_store = SqliteStore(store_connection)
    checkpointer.setup()
    langgraph_store.setup()
    knowledge_index = SqliteKnowledgeIndex(knowledge_index_connection)
    knowledge_index.setup()
    persistence = PlatformPersistence(
        paths=paths,
        checkpointer=checkpointer,
        langgraph_store=langgraph_store,
        store=LangGraphStoreAdapter(langgraph_store),
        knowledge_index=knowledge_index,
        evidence=FilesystemEvidenceStore(paths.evidence_root),
        _checkpoint_connection=checkpoint_connection,
        _store_connection=store_connection,
    )
    try:
        yield persistence
    finally:
        persistence.close()
