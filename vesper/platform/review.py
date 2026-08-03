"""Daily agent digest, acknowledgement receipts, and hybrid admission gate."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Mapping, Sequence

from .contracts import AgentRole, JournalEvent
from .persistence import LangGraphStoreAdapter

_ACK_NAMESPACE = ("agent-review", "acknowledgements")
_BOOTSTRAP_NAMESPACE = ("agent-review", "bootstrap")


class ReviewIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DailySection:
    role: AgentRole
    event_count: int
    last_event_hash: str | None
    events: tuple[JournalEvent, ...]


@dataclass(frozen=True, slots=True)
class DailyDigest:
    session_date: date
    sections: tuple[DailySection, ...]
    sha256: str
    json_path: Path
    markdown_path: Path


class DailyReviewService:
    def __init__(self, store: LangGraphStoreAdapter, root: Path) -> None:
        self.store = store
        self.root = root.resolve()

    def render(
        self,
        session_date: date,
        events_by_role: Mapping[AgentRole, Sequence[JournalEvent]],
    ) -> DailyDigest:
        sections: list[DailySection] = []
        document_sections: list[dict[str, object]] = []
        for role in AgentRole:
            events = tuple(events_by_role.get(role, ()))
            self._verify_chain(events)
            section = DailySection(
                role,
                len(events),
                events[-1].event_hash if events else None,
                events,
            )
            sections.append(section)
            document_sections.append(
                {
                    "role": role.value,
                    "event_count": len(events),
                    "last_event_hash": section.last_event_hash,
                    "events": [event.model_dump(mode="json") for event in events],
                }
            )
        document = {
            "schema_version": "1.0",
            "session_date": session_date.isoformat(),
            "sections": document_sections,
        }
        body = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest_hash = hashlib.sha256(body).hexdigest()
        directory = self.root / session_date.isoformat()
        directory.mkdir(parents=True, exist_ok=True)
        json_path = directory / "digest.json"
        markdown_path = directory / "digest.md"
        markdown = self._markdown(session_date, sections, digest_hash).encode("utf-8")
        self._write_immutable(json_path, body)
        self._write_immutable(markdown_path, markdown)
        return DailyDigest(session_date, tuple(sections), digest_hash, json_path, markdown_path)

    def acknowledge(self, digest: DailyDigest, operator: str, acknowledged_at: datetime) -> None:
        if not operator.strip():
            raise ReviewIntegrityError("operator identity is required")
        if (
            not digest.json_path.is_file()
            or hashlib.sha256(digest.json_path.read_bytes()).hexdigest() != digest.sha256
        ):
            raise ReviewIntegrityError("daily digest JSON does not match its hash")
        key = digest.session_date.isoformat()
        receipt = {
            "schema_version": "1.0",
            "session_date": key,
            "digest_sha256": digest.sha256,
            "operator": operator,
            "acknowledged_at": acknowledged_at.isoformat(),
        }
        existing = self.store.get(_ACK_NAMESPACE, key)
        if existing is not None and dict(existing) != receipt:
            raise ReviewIntegrityError("daily review already has a different acknowledgement")
        self.store.put(_ACK_NAMESPACE, key, receipt)

    @staticmethod
    def _verify_chain(events: Sequence[JournalEvent]) -> None:
        previous = None
        sequence = 0
        session_id = None
        for event in events:
            if event.session_id != session_id:
                session_id = event.session_id
                sequence = 0
                previous = None
            sequence += 1
            if event.sequence != sequence or event.previous_hash != previous:
                raise ReviewIntegrityError("journal chain is incomplete or out of order")
            material = event.model_dump(mode="json")
            material.pop("event_hash")
            digest = hashlib.sha256(
                json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            if digest != event.event_hash:
                raise ReviewIntegrityError("journal event hash does not match its content")
            previous = event.event_hash

    @staticmethod
    def _markdown(session_date: date, sections: Sequence[DailySection], digest_hash: str) -> str:
        lines = [
            f"# V20 agent review — {session_date.isoformat()}",
            "",
            f"Digest SHA-256: `{digest_hash}`",
            "",
        ]
        for section in sections:
            lines.extend(
                (
                    f"## {section.role.value}",
                    "",
                    f"Events: {section.event_count}",
                    f"Last event hash: `{section.last_event_hash or 'none'}`",
                    "",
                )
            )
            for event in section.events:
                payload = json.dumps(event.payload, sort_keys=True, ensure_ascii=True)
                lines.append(
                    f"- {event.created_at.isoformat()} | {event.event_type.value} | {payload}"
                )
            if section.events:
                lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _write_immutable(path: Path, body: bytes) -> None:
        if path.exists():
            if path.read_bytes() != body:
                raise ReviewIntegrityError(f"daily review artifact changed: {path.name}")
            return
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_bytes(body)
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()


class HybridReviewGate:
    def __init__(self, store: LangGraphStoreAdapter) -> None:
        self.store = store

    def bootstrap(self, session_date: date, operator: str, created_at: datetime) -> None:
        self.store.put(
            _BOOTSTRAP_NAMESPACE,
            "initial-enablement",
            {
                "session_date": session_date.isoformat(),
                "operator": operator,
                "created_at": created_at.isoformat(),
            },
        )

    def can_admit(self, prior_session_date: date, *, digest_sha256: str | None = None) -> bool:
        receipt = self.store.get(_ACK_NAMESPACE, prior_session_date.isoformat())
        if receipt is None:
            return False
        return digest_sha256 is None or receipt.get("digest_sha256") == digest_sha256
