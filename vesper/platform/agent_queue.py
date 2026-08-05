"""Persistent priority queue for event-driven agent work."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .agent_profiles import AUTONOMOUS_AGENT_ROLES
from .contracts import AgentRole, NonEmptyStr
from .persistence import LangGraphStoreAdapter

_NAMESPACE = ("agent-work", "items")


class WorkQueueEmpty(RuntimeError):
    pass


class WorkQueueConflict(RuntimeError):
    pass


class WorkQueueRoleError(RuntimeError):
    pass


class AgentWorkItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    work_id: NonEmptyStr
    role: AgentRole
    session_id: NonEmptyStr
    title: NonEmptyStr
    objective: NonEmptyStr
    priority: int = Field(ge=0, le=100)
    created_at: datetime
    status: Literal["queued", "claimed", "completed", "cancelled", "failed"]
    attempt: int = Field(ge=0)
    claimed_by: str | None = None
    lease_expires_at: datetime | None = None


def _load(raw) -> AgentWorkItem:
    persisted = dict(raw)
    if "title" not in persisted:
        persisted["title"] = persisted.get("objective")
    return AgentWorkItem.model_validate_json(json.dumps(persisted))


class AgentWorkQueue:
    def __init__(self, store: LangGraphStoreAdapter) -> None:
        self.store = store

    def enqueue(
        self,
        work_id: str,
        role: AgentRole,
        session_id: str,
        title: str,
        objective: str,
        priority: int,
        created_at: datetime,
    ) -> AgentWorkItem:
        if role not in AUTONOMOUS_AGENT_ROLES:
            raise WorkQueueRoleError("agent queue requires an approved autonomous quant role")
        existing = self.store.get(_NAMESPACE, work_id)
        if existing is not None:
            item = _load(existing)
            expected = (
                role,
                session_id,
                title,
                objective,
                priority,
                created_at,
            )
            actual = (
                item.role,
                item.session_id,
                item.title,
                item.objective,
                item.priority,
                item.created_at,
            )
            if actual != expected:
                raise WorkQueueConflict(f"conflicting agent work: {work_id}")
            return item
        item = AgentWorkItem(
            work_id=work_id,
            role=role,
            session_id=session_id,
            title=title,
            objective=objective,
            priority=priority,
            created_at=created_at,
            status="queued",
            attempt=0,
        )
        self.store.put(_NAMESPACE, work_id, item.model_dump(mode="json"))
        return item

    def get(self, work_id: str) -> AgentWorkItem | None:
        existing = self.store.get(_NAMESPACE, work_id)
        return None if existing is None else _load(existing)

    def list(self) -> tuple[AgentWorkItem, ...]:
        return tuple(_load(raw) for raw in self.store.search(_NAMESPACE, limit=10_000))

    def claim(self, worker_id: str, now: datetime, *, lease_seconds: int) -> AgentWorkItem:
        def claim_one(records) -> tuple[str, dict[str, object]]:
            items = (_load(raw) for _, raw in records)
            candidates = [
                item
                for item in items
                if item.status == "queued"
                or (
                    item.status == "claimed"
                    and item.lease_expires_at is not None
                    and item.lease_expires_at <= now
                )
            ]
            if not candidates:
                raise WorkQueueEmpty("no agent work is ready")
            item = sorted(
                candidates, key=lambda value: (-value.priority, value.created_at, value.work_id)
            )[0]
            claimed = item.model_copy(
                update={
                    "status": "claimed",
                    "attempt": item.attempt + 1,
                    "claimed_by": worker_id,
                    "lease_expires_at": now + timedelta(seconds=lease_seconds),
                }
            )
            return claimed.work_id, claimed.model_dump(mode="json")

        return _load(self.store.atomic_replace(_NAMESPACE, claim_one))

    def complete(self, work_id: str, worker_id: str, claim_attempt: int) -> AgentWorkItem:
        return self._finish(work_id, worker_id, claim_attempt, status="completed")

    def renew(
        self,
        work_id: str,
        worker_id: str,
        claim_attempt: int,
        now: datetime,
        *,
        lease_seconds: float,
    ) -> AgentWorkItem:
        def renew_one(records) -> tuple[str, dict[str, object]]:
            raw = next((raw for key, raw in records if key == work_id), None)
            if raw is None:
                raise WorkQueueEmpty(f"unknown work item: {work_id}")
            item = _load(raw)
            if (
                item.status != "claimed"
                or item.claimed_by != worker_id
                or item.attempt != claim_attempt
                or item.lease_expires_at is None
                or item.lease_expires_at <= now
            ):
                raise WorkQueueEmpty("work item is not owned by this worker")
            renewed = item.model_copy(
                update={"lease_expires_at": now + timedelta(seconds=lease_seconds)}
            )
            return work_id, renewed.model_dump(mode="json")

        return _load(self.store.atomic_replace(_NAMESPACE, renew_one))

    def fail(self, work_id: str, worker_id: str, claim_attempt: int) -> AgentWorkItem:
        return self._finish(work_id, worker_id, claim_attempt, status="failed")

    def _finish(
        self,
        work_id: str,
        worker_id: str,
        claim_attempt: int,
        *,
        status: Literal["completed", "failed"],
    ) -> AgentWorkItem:
        def finish_one(records) -> tuple[str, dict[str, object]]:
            raw = next((raw for key, raw in records if key == work_id), None)
            if raw is None:
                raise WorkQueueEmpty(f"unknown work item: {work_id}")
            item = _load(raw)
            if (
                item.status != "claimed"
                or item.claimed_by != worker_id
                or item.attempt != claim_attempt
            ):
                raise WorkQueueEmpty("work item is not owned by this worker")
            finished = item.model_copy(
                update={"status": status, "claimed_by": None, "lease_expires_at": None}
            )
            return work_id, finished.model_dump(mode="json")

        return _load(self.store.atomic_replace(_NAMESPACE, finish_one))
