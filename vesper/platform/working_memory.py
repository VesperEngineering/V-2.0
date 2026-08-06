"""Bounded, per-agent working memory with reversible file receipts."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .contracts import WorkingMemoryCandidate


MAX_WORKING_MEMORY_WORDS = 2_000


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class WorkingMemoryChange:
    change_id: str
    agent_id: str
    word_count: int
    active_ids: tuple[str, ...]
    archived_ids: tuple[str, ...]


class WorkingMemoryStore:
    """Controller-owned working memory; agents only submit candidates."""

    def __init__(
        self,
        root: Path,
        *,
        max_words: int = MAX_WORKING_MEMORY_WORDS,
        clock: Callable[[], datetime] = _utc_now,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        if max_words < 1:
            raise ValueError("working-memory word cap must be positive")
        self.root = root.resolve()
        self.max_words = max_words
        self._clock = clock
        self._id_factory = id_factory
        self.root.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.root / "working-memory.sqlite3")
        self._connection.row_factory = sqlite3.Row
        self._setup()

    def close(self) -> None:
        self._connection.close()

    def propose(self, candidate: WorkingMemoryCandidate) -> None:
        """Persist a candidate outside the active core."""
        payload = candidate.model_dump(mode="json")
        self._connection.execute(
            "INSERT INTO proposals (agent_id, memory_id, payload) VALUES (?, ?, ?) "
            "ON CONFLICT(agent_id, memory_id) DO UPDATE SET payload=excluded.payload",
            (candidate.agent_id, candidate.memory_id, json.dumps(payload, sort_keys=True)),
        )
        self._connection.commit()

    def curate(self, agent_id: str) -> WorkingMemoryChange:
        self._validate_agent_id(agent_id)
        current = self._load_items("active", agent_id)
        proposals = self._load_items("proposals", agent_id)
        candidates = {item.memory_id: item for item in (*current, *proposals)}
        if not candidates:
            raise ValueError(f"no working-memory candidates for {agent_id}")

        selected: list[WorkingMemoryCandidate] = []
        word_count = 0
        for item in sorted(candidates.values(), key=lambda value: (-value.score, value.memory_id)):
            if item.word_count > self.max_words:
                continue
            if word_count + item.word_count > self.max_words:
                continue
            selected.append(item)
            word_count += item.word_count
        if not selected:
            raise ValueError("working-memory candidates exceed the word cap")

        selected_ids = {item.memory_id for item in selected}
        previous_payload = [item.model_dump(mode="json") for item in current]
        archived_ids = tuple(
            item.memory_id for item in candidates.values() if item.memory_id not in selected_ids
        )
        self._connection.execute("DELETE FROM active WHERE agent_id = ?", (agent_id,))
        self._connection.execute("DELETE FROM proposals WHERE agent_id = ?", (agent_id,))
        for item in selected:
            self._put("active", item)
        for item in candidates.values():
            if item.memory_id not in selected_ids and item.word_count <= self.max_words:
                self._put("archive", item)

        change_id = self._id_factory()
        after_payload = [item.model_dump(mode="json") for item in selected]
        self._connection.execute(
            "INSERT INTO history (change_id, agent_id, before_payload, after_payload, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                change_id,
                agent_id,
                json.dumps(previous_payload, sort_keys=True),
                json.dumps(after_payload, sort_keys=True),
                self._clock().isoformat(),
            ),
        )
        self._connection.commit()
        self._write_core(agent_id, tuple(selected))
        for item in candidates.values():
            if item.memory_id not in selected_ids and item.word_count <= self.max_words:
                self._write_archive(agent_id, item)
        self._write_history(agent_id, change_id, previous_payload, after_payload)
        return WorkingMemoryChange(
            change_id=change_id,
            agent_id=agent_id,
            word_count=word_count,
            active_ids=tuple(item.memory_id for item in selected),
            archived_ids=archived_ids,
        )

    def core(self, agent_id: str) -> tuple[WorkingMemoryCandidate, ...]:
        return self._load_items("active", agent_id)

    def archive(self, agent_id: str) -> tuple[WorkingMemoryCandidate, ...]:
        return self._load_items("archive", agent_id)

    def rollback(self, change_id: str) -> None:
        row = self._connection.execute(
            "SELECT agent_id, before_payload FROM history WHERE change_id = ?",
            (change_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown working-memory change: {change_id}")
        agent_id = str(row["agent_id"])
        before = tuple(
            WorkingMemoryCandidate.model_validate_json(json.dumps(item))
            for item in json.loads(str(row["before_payload"]))
        )
        if sum(item.word_count for item in before) > self.max_words:
            raise ValueError("rollback would exceed the working-memory word cap")
        self._connection.execute("DELETE FROM active WHERE agent_id = ?", (agent_id,))
        for item in before:
            self._put("active", item)
        self._connection.commit()
        self._write_core(agent_id, before)

    def status(self, agent_id: str) -> dict[str, object]:
        active = self.core(agent_id)
        return {
            "agent_id": agent_id,
            "active_items": len(active),
            "active_words": sum(item.word_count for item in active),
            "word_limit": self.max_words,
            "archive_items": len(self.archive(agent_id)),
        }

    def _setup(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS proposals (
                agent_id TEXT NOT NULL,
                memory_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (agent_id, memory_id)
            );
            CREATE TABLE IF NOT EXISTS active (
                agent_id TEXT NOT NULL,
                memory_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (agent_id, memory_id)
            );
            CREATE TABLE IF NOT EXISTS archive (
                agent_id TEXT NOT NULL,
                memory_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (agent_id, memory_id)
            );
            CREATE TABLE IF NOT EXISTS history (
                change_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                before_payload TEXT NOT NULL,
                after_payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self._connection.commit()

    def _put(self, tier: str, item: WorkingMemoryCandidate) -> None:
        self._connection.execute(
            f"INSERT INTO {tier} (agent_id, memory_id, payload) VALUES (?, ?, ?) "
            "ON CONFLICT(agent_id, memory_id) DO UPDATE SET payload=excluded.payload",
            (
                item.agent_id,
                item.memory_id,
                json.dumps(item.model_dump(mode="json"), sort_keys=True),
            ),
        )

    def _load_items(self, tier: str, agent_id: str) -> tuple[WorkingMemoryCandidate, ...]:
        self._validate_agent_id(agent_id)
        rows = self._connection.execute(
            f"SELECT payload FROM {tier} WHERE agent_id = ? ORDER BY memory_id", (agent_id,)
        ).fetchall()
        return tuple(
            WorkingMemoryCandidate.model_validate_json(str(row[0])) for row in rows
        )

    def _write_core(self, agent_id: str, items: tuple[WorkingMemoryCandidate, ...]) -> None:
        directory = self.root / agent_id
        directory.mkdir(parents=True, exist_ok=True)
        body = [
            "---",
            "vesper_kind: working-memory",
            f"agent_id: {agent_id}",
            f"word_count: {sum(item.word_count for item in items)}",
            f"word_limit: {self.max_words}",
            "status: active",
            "---",
            "# Core Memory",
            "",
        ]
        for item in items:
            body.extend((f"## {item.memory_id}", "", item.content, ""))
        self._atomic_write(directory / "Core Memory.md", "\n".join(body))

    def _write_archive(self, agent_id: str, item: WorkingMemoryCandidate) -> None:
        directory = self.root / agent_id / "Archive"
        directory.mkdir(parents=True, exist_ok=True)
        content = (
            "---\nvesper_kind: working-memory\n"
            f"agent_id: {agent_id}\nmemory_id: {item.memory_id}\nstatus: archived\n---\n\n"
            f"# {item.memory_id}\n\n{item.content}\n"
        )
        self._atomic_write(directory / f"{item.memory_id}.md", content)

    def _write_history(
        self,
        agent_id: str,
        change_id: str,
        before: list[dict[str, object]],
        after: list[dict[str, object]],
    ) -> None:
        directory = self.root / agent_id / "History"
        directory.mkdir(parents=True, exist_ok=True)
        payload = {"change_id": change_id, "before": before, "after": after}
        self._atomic_write(
            directory / f"{change_id}.md",
            f"# Working-memory change {change_id}\n\n```json\n"
            f"{json.dumps(payload, indent=2, sort_keys=True)}\n```\n",
        )

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _validate_agent_id(agent_id: str) -> None:
        if not agent_id or agent_id in {".", ".."} or Path(agent_id).name != agent_id:
            raise ValueError("agent ID must be a single safe path component")
