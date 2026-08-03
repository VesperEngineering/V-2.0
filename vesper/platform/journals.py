"""Append-only, hash-chained journals for bounded agents."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .contracts import AgentRole, JournalEvent, JournalEventType, NonEmptyStr, Sha256
from .persistence import AtomicCreatePlan, LangGraphStoreAdapter


_JOURNAL_ROOT = ("agent-journals",)
_REGISTRY_NAMESPACE = (*_JOURNAL_ROOT, "sessions")
_MANIFEST_KEY = "__journal_manifest__"


class _JournalManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    role: AgentRole
    session_id: NonEmptyStr
    event_count: Annotated[int, Field(ge=1)]
    head_event_id: NonEmptyStr
    head_hash: Sha256


class _JournalRegistryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    role: AgentRole
    session_id: NonEmptyStr


class JournalConflictError(RuntimeError):
    """Journal storage or replay violates an integrity constraint."""


class AgentJournal:
    def __init__(self, store: LangGraphStoreAdapter) -> None:
        self._store = store

    @staticmethod
    def _namespace(role: AgentRole, session_id: str) -> tuple[str, ...]:
        return (*_JOURNAL_ROOT, role.value, session_id)

    @staticmethod
    def _registry_key(role: AgentRole, session_id: str) -> str:
        return f"{role.value}:{session_id}"

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
        if event_id == _MANIFEST_KEY:
            raise JournalConflictError("journal event ID is reserved")
        namespace = self._namespace(role, session_id)

        def build_candidate(sequence: int, previous_hash: str | None) -> JournalEvent:
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
            return candidate.model_copy(update={"event_hash": event_hash})

        def create(
            records,
            existing: Mapping[str, object] | None,
        ) -> AtomicCreatePlan:
            events, manifest = self._validated_session_records(
                records,
                role=role,
                session_id=session_id,
            )
            if not self._chain_is_valid(events):
                raise JournalConflictError("journal chain is invalid")
            if manifest is None:
                if events:
                    raise JournalConflictError("journal manifest is missing")
            elif not self._manifest_matches(events, manifest):
                raise JournalConflictError("journal manifest does not match its events")
            if existing is not None:
                existing_event = JournalEvent.model_validate_json(json.dumps(existing))
                replay = build_candidate(existing_event.sequence, existing_event.previous_hash)
                if replay.event_hash != existing_event.event_hash:
                    raise JournalConflictError(f"conflicting journal event: {event_id}")
                stored = dict(existing)
                linked_items = (
                    (
                        _REGISTRY_NAMESPACE,
                        self._registry_key(role, session_id),
                        {"role": role.value, "session_id": session_id},
                    ),
                )
            else:
                if event_type is JournalEventType.CORRECTION:
                    if correction_of is None or all(
                        event.event_id != correction_of for event in events
                    ):
                        raise JournalConflictError("correction must link to an existing event")
                previous_hash = events[-1].event_hash if events else None
                sequence = events[-1].sequence + 1 if events else 1
                candidate = build_candidate(sequence, previous_hash)
                stored = candidate.model_dump(mode="json")
                updated_events = (*events, candidate)
                linked_items = (
                    (
                        namespace,
                        _MANIFEST_KEY,
                        self._manifest_for(updated_events).model_dump(mode="json"),
                    ),
                    (
                        _REGISTRY_NAMESPACE,
                        self._registry_key(role, session_id),
                        {"role": role.value, "session_id": session_id},
                    ),
                )
            return AtomicCreatePlan(value=stored, linked_items=linked_items)

        stored, _ = self._store.atomic_create(
            namespace,
            event_id,
            create,
        )
        event = JournalEvent.model_validate_json(json.dumps(stored))
        return event

    def list(self, role: AgentRole, session_id: str) -> tuple[JournalEvent, ...]:
        records = self._store.search_exact_records(self._namespace(role, session_id))
        events, _ = self._validated_session_records(
            records,
            role=role,
            session_id=session_id,
        )
        return events

    def verify(self, role: AgentRole, session_id: str) -> bool:
        try:
            records = self._store.search_exact_records(self._namespace(role, session_id))
            events, manifest = self._validated_session_records(
                records,
                role=role,
                session_id=session_id,
            )
            registry_raw = self._store.get(
                _REGISTRY_NAMESPACE,
                self._registry_key(role, session_id),
            )
            if registry_raw is None:
                return False
            self._validated_registry_entry(
                self._registry_key(role, session_id),
                registry_raw,
            )
        except JournalConflictError:
            return False
        return (
            manifest is not None
            and self._chain_is_valid(events)
            and self._manifest_matches(events, manifest)
        )

    @classmethod
    def _validated_session_records(
        cls,
        records: tuple[tuple[str, Mapping[str, object]], ...],
        *,
        role: AgentRole,
        session_id: str,
    ) -> tuple[tuple[JournalEvent, ...], _JournalManifest | None]:
        events: list[JournalEvent] = []
        manifest = None
        for key, raw in records:
            if key == _MANIFEST_KEY:
                manifest = cls._validated_manifest(raw)
                if manifest.role != role or manifest.session_id != session_id:
                    raise JournalConflictError("journal manifest identity does not match namespace")
                continue
            event = cls._validated_event(raw)
            if key != event.event_id:
                raise JournalConflictError("journal event storage key does not match event ID")
            if event.role != role or event.session_id != session_id:
                raise JournalConflictError("journal event identity does not match namespace")
            events.append(event)
        return tuple(sorted(events, key=lambda event: event.sequence)), manifest

    @staticmethod
    def _validated_event(raw: Mapping[str, object]) -> JournalEvent:
        try:
            return JournalEvent.model_validate_json(json.dumps(raw))
        except (TypeError, ValueError, ValidationError) as exc:
            raise JournalConflictError("journal event is invalid") from exc

    @staticmethod
    def _validated_manifest(raw: Mapping[str, object]) -> _JournalManifest:
        try:
            return _JournalManifest.model_validate_json(json.dumps(raw))
        except (TypeError, ValueError, ValidationError) as exc:
            raise JournalConflictError("journal manifest is invalid") from exc

    @classmethod
    def _validated_registry_entry(
        cls,
        key: str,
        raw: Mapping[str, object],
    ) -> _JournalRegistryEntry:
        try:
            entry = _JournalRegistryEntry.model_validate_json(json.dumps(raw))
        except (TypeError, ValueError, ValidationError) as exc:
            raise JournalConflictError("journal session registry entry is invalid") from exc
        if key != cls._registry_key(entry.role, entry.session_id):
            raise JournalConflictError("journal session registry key does not match its identity")
        return entry

    @staticmethod
    def _manifest_for(events: tuple[JournalEvent, ...]) -> _JournalManifest:
        if not events:
            raise JournalConflictError("journal manifest requires at least one event")
        head = events[-1]
        return _JournalManifest(
            role=head.role,
            session_id=head.session_id,
            event_count=len(events),
            head_event_id=head.event_id,
            head_hash=head.event_hash,
        )

    @staticmethod
    def _manifest_matches(
        events: tuple[JournalEvent, ...],
        manifest: _JournalManifest,
    ) -> bool:
        if not events:
            return False
        head = events[-1]
        return (
            manifest.role == head.role
            and manifest.session_id == head.session_id
            and manifest.event_count == len(events)
            and manifest.head_event_id == head.event_id
            and manifest.head_hash == head.event_hash
        )

    @staticmethod
    def _chain_is_valid(events: tuple[JournalEvent, ...]) -> bool:
        previous: str | None = None
        for expected_sequence, event in enumerate(events, start=1):
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
        records = self._store.scan_subtree_records(_JOURNAL_ROOT)
        registry_prefix = ".".join(_REGISTRY_NAMESPACE)
        sessions: set[tuple[AgentRole, str]] = set()
        for prefix, key, raw in records:
            if prefix == registry_prefix:
                entry = self._validated_registry_entry(key, raw)
                sessions.add((entry.role, entry.session_id))
                continue
            if prefix.startswith(f"{registry_prefix}."):
                raise JournalConflictError("journal session registry namespace is invalid")
            if key == _MANIFEST_KEY:
                record = self._validated_manifest(raw)
                record_role = record.role
                record_session_id = record.session_id
            else:
                event = self._validated_event(raw)
                if key != event.event_id:
                    raise JournalConflictError("journal event storage key does not match event ID")
                record_role = event.role
                record_session_id = event.session_id
            if prefix != ".".join(self._namespace(record_role, record_session_id)):
                raise JournalConflictError("journal record namespace does not match its identity")
            sessions.add((record_role, record_session_id))
        return tuple(sorted(sessions, key=lambda item: (item[0].value, item[1])))
