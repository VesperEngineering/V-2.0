"""Local SQLite checkpointer, LangGraph Store, and evidence lifecycle."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Mapping

from .evidence import FilesystemEvidenceStore
from .knowledge import SqliteKnowledgeIndex
from .paths import default_platform_root
from .runtime_env import enforce_offline_runtime_environment

enforce_offline_runtime_environment()

from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: E402
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


def default_platform_paths() -> PlatformPaths:
    """Return canonical local platform paths without creating them."""

    return PlatformPaths.below(default_platform_root())


class LangGraphStoreAdapter:
    """Thread-safe JSON mapping facade over the local LangGraph Store."""

    def __init__(self, store: SqliteStore) -> None:
        self._store = store
        self._lock = threading.RLock()

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
        limit: int = 10,
    ) -> tuple[Mapping[str, object], ...]:
        with self._lock:
            items = self._store.search(namespace, limit=limit)
        return tuple(item.value for item in items)


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
