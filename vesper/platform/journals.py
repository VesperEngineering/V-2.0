"""Append-only, hash-chained journals for bounded agents."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime
from typing import Mapping

from .contracts import AgentRole, JournalEvent, JournalEventType
from .persistence import LangGraphStoreAdapter


class JournalConflictError(RuntimeError):
    """An event ID was replayed with different content."""


class AgentJournal:
    def __init__(self, store: LangGraphStoreAdapter) -> None:
        self._store = store
        self._lock = threading.RLock()

    @staticmethod
    def _namespace(role: AgentRole, session_id: str) -> tuple[str, ...]:
        return ("agent-journals", role.value, session_id)

    def append(
        self,
        *,
        event_id: str,
        role: AgentRole,
        session_id: str,
        run_id: str,
        task_id: str,
        repository_revision: str,
        created_at: datetime,
        event_type: JournalEventType,
        payload: Mapping[str, str | int | float | bool | None],
        correction_of: str | None = None,
    ) -> JournalEvent:
        namespace = self._namespace(role, session_id)
        with self._lock:
            current = self._store.get(namespace, event_id)
            events = self.list(role, session_id)
            if event_type is JournalEventType.CORRECTION:
                if correction_of is None or all(
                    event.event_id != correction_of for event in events
                ):
                    raise JournalConflictError("correction must link to an existing event")
            previous_hash = events[-1].event_hash if events else None
            sequence = events[-1].sequence + 1 if events else 1
            candidate = JournalEvent(
                run_id=run_id,
                task_id=task_id,
                repository_revision=repository_revision,
                created_at=created_at,
                event_id=event_id,
                role=role,
                session_id=session_id,
                sequence=sequence,
                event_type=event_type,
                payload=dict(payload),
                previous_hash=previous_hash,
                event_hash="0" * 64,
                correction_of=correction_of,
            )
            material = candidate.model_dump(mode="json")
            material.pop("event_hash")
            event_hash = hashlib.sha256(
                json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            candidate = candidate.model_copy(update={"event_hash": event_hash})
            if current is not None:
                existing = JournalEvent.model_validate_json(json.dumps(current))
                replay_material = candidate.model_dump(mode="json")
                replay_material["sequence"] = existing.sequence
                replay_material["previous_hash"] = existing.previous_hash
                replay_material.pop("event_hash")
                replay_hash = hashlib.sha256(
                    json.dumps(replay_material, sort_keys=True, separators=(",", ":")).encode(
                        "utf-8"
                    )
                ).hexdigest()
                if replay_hash != existing.event_hash:
                    raise JournalConflictError(f"conflicting journal event: {event_id}")
                return existing
            self._store.put(namespace, event_id, candidate.model_dump(mode="json"))
            self._store.put(
                ("agent-journals", "sessions"),
                f"{role.value}:{session_id}",
                {"role": role.value, "session_id": session_id},
            )
            return candidate

    def list(self, role: AgentRole, session_id: str) -> tuple[JournalEvent, ...]:
        raw = self._store.search(
            self._namespace(role, session_id),
            filter={"role": role.value, "session_id": session_id},
            limit=10_000,
        )
        events = (JournalEvent.model_validate_json(json.dumps(item)) for item in raw)
        return tuple(
            sorted(
                (
                    event
                    for event in events
                    if event.role is role and event.session_id == session_id
                ),
                key=lambda event: event.sequence,
            )
        )

    def verify(self, role: AgentRole, session_id: str) -> bool:
        previous: str | None = None
        for expected_sequence, event in enumerate(self.list(role, session_id), start=1):
            if event.sequence != expected_sequence or event.previous_hash != previous:
                return False
            material = event.model_dump(mode="json")
            material.pop("event_hash")
            digest = hashlib.sha256(
                json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            if digest != event.event_hash:
                return False
            previous = event.event_hash
        return True

    def sessions(self) -> tuple[tuple[AgentRole, str], ...]:
        records = self._store.search(("agent-journals", "sessions"), limit=10_000)
        return tuple(
            sorted(
                (AgentRole(str(record["role"])), str(record["session_id"])) for record in records
            )
        )
