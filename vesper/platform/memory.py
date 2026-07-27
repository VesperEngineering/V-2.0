"""Controller-owned memory authorization and typed consolidation boundary."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Callable, Mapping, Protocol

from .contracts import (
    MemoryCandidate,
    MemoryRecord,
    MemoryType,
    SpecialistRole,
    VerificationState,
)


class ControllerActor(StrEnum):
    CONTROLLER = "controller"


MemoryActor = SpecialistRole | ControllerActor


class MemoryAccessDenied(RuntimeError):
    """An actor attempted to cross an authoritative memory boundary."""


class UnvalidatedMemoryError(RuntimeError):
    """A generated candidate was presented without deterministic validation."""


class MemoryStorePort(Protocol):
    def put(self, namespace: tuple[str, ...], key: str, value: Mapping[str, object]) -> None: ...

    def get(self, namespace: tuple[str, ...], key: str) -> Mapping[str, object] | None: ...

    def search(self, namespace: tuple[str, ...]) -> tuple[Mapping[str, object], ...]: ...


class MemoryCandidateEmitter(Protocol):
    def emit_candidates(
        self, source_text: str, context: Mapping[str, object]
    ) -> list[Mapping[str, object]]: ...


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_default(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    raise TypeError(f"unsupported generated value: {type(value).__name__}")


class MemoryService:
    """Authorize controller-mediated memory reads and append-only writes."""

    def __init__(
        self,
        store: MemoryStorePort,
        *,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._store = store
        self._id_factory = id_factory
        self._clock = clock

    def commit(
        self,
        actor: MemoryActor,
        candidate: MemoryCandidate,
        *,
        validated: bool,
    ) -> MemoryRecord:
        if not validated:
            raise UnvalidatedMemoryError("memory candidates require deterministic validation")
        expected = self._authorized_namespace(
            actor, candidate.memory_type, candidate.task_id, write=True
        )
        if candidate.namespace != expected:
            raise MemoryAccessDenied(
                "candidate namespace does not match controller-derived namespace"
            )

        supersedes = candidate.contradicts
        if supersedes is not None:
            previous = self._load_record(expected, supersedes)
            if previous is None:
                raise MemoryAccessDenied(
                    "contradicted memory does not exist in the authorized namespace"
                )

        record = MemoryRecord(
            run_id=candidate.run_id,
            task_id=candidate.task_id,
            repository_revision=candidate.repository_revision,
            created_at=self._clock(),
            memory_id=self._id_factory(),
            namespace=expected,
            memory_type=candidate.memory_type,
            content=candidate.content,
            source_run=candidate.run_id,
            source_artifact=candidate.source_artifact,
            confidence=candidate.confidence,
            verification_state=VerificationState.VERIFIED,
            supersedes=supersedes,
            expiration_policy=candidate.expiration_policy,
        )
        self._store.put(expected, record.memory_id, record.model_dump(mode="json"))
        self._store.put(
            ("_index", *expected),
            f"active:{candidate.memory_type.value}",
            {"memory_id": record.memory_id},
        )
        return record

    def search(
        self,
        actor: MemoryActor,
        memory_type: MemoryType,
        *,
        task_id: str = "shared",
    ) -> tuple[MemoryRecord, ...]:
        namespace = self._authorized_namespace(actor, memory_type, task_id, write=False)
        pointer = self._store.get(("_index", *namespace), f"active:{memory_type.value}")
        if pointer is None:
            return ()
        record = self._load_record(namespace, str(pointer["memory_id"]))
        return () if record is None else (record,)

    def history(
        self,
        actor: MemoryActor,
        memory_type: MemoryType,
        *,
        task_id: str = "shared",
    ) -> tuple[MemoryRecord, ...]:
        namespace = self._authorized_namespace(actor, memory_type, task_id, write=False)
        records = tuple(self._parse_record(value) for value in self._store.search(namespace))
        return tuple(record for record in records if record.memory_type is memory_type)

    def _load_record(self, namespace: tuple[str, ...], memory_id: str) -> MemoryRecord | None:
        raw = self._store.get(namespace, memory_id)
        return None if raw is None else self._parse_record(raw)

    @staticmethod
    def _parse_record(raw: Mapping[str, object]) -> MemoryRecord:
        return MemoryRecord.model_validate_json(json.dumps(raw))

    @staticmethod
    def _authorized_namespace(
        actor: MemoryActor,
        memory_type: MemoryType,
        task_id: str,
        *,
        write: bool,
    ) -> tuple[str, ...]:
        if memory_type is MemoryType.REPOSITORY_FACT:
            if write and actor is not ControllerActor.CONTROLLER:
                raise MemoryAccessDenied("shared repository facts are controller-written")
            return ("shared", "repository-facts")
        if memory_type is MemoryType.VERIFIED_PROCEDURE:
            if write and actor is not ControllerActor.CONTROLLER:
                raise MemoryAccessDenied("verified procedures are controller-written")
            return ("shared", "verified-procedures")
        if memory_type is MemoryType.PROGRAM_STATE:
            if actor is not ControllerActor.CONTROLLER:
                raise MemoryAccessDenied("program state is controller-owned")
            return ("programs", task_id, "state")

        owner_by_type = {
            MemoryType.PRODUCT_DECISION: SpecialistRole.PRODUCT,
            MemoryType.DEVELOPMENT_EPISODE: SpecialistRole.DEVELOPMENT,
            MemoryType.RISK_DECISION: SpecialistRole.RISK_REVIEW,
        }
        if memory_type is MemoryType.FAILED_ATTEMPT:
            if actor is ControllerActor.CONTROLLER:
                return ("system", "failed-attempts")
            return ("profiles", actor.value, "failed-attempts")
        owner = owner_by_type.get(memory_type)
        if actor is not ControllerActor.CONTROLLER and actor is not owner:
            raise MemoryAccessDenied(f"{actor.value} cannot access {memory_type.value}")
        if owner is None:
            raise MemoryAccessDenied(
                f"memory type has no authorized namespace: {memory_type.value}"
            )
        return ("profiles", owner.value, f"{memory_type.value}s")


class MemoryConsolidationNode:
    """Validate structured candidates emitted through a Codex-compatible port."""

    def __init__(self, emitter: MemoryCandidateEmitter) -> None:
        self._emitter = emitter

    def consolidate(
        self,
        *,
        source_text: str,
        context: Mapping[str, object],
    ) -> tuple[MemoryCandidate, ...]:
        if context.get("validated") is not True:
            raise UnvalidatedMemoryError("consolidation requires validated source evidence")
        raw_candidates = self._emitter.emit_candidates(source_text, context)
        return tuple(
            MemoryCandidate.model_validate_json(json.dumps(raw, default=_json_default))
            for raw in raw_candidates
        )
