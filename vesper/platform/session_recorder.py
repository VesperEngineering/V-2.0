"""Controller-owned redacted conversation capture for Dream Gate inputs."""

from __future__ import annotations

import hashlib
import json
import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import yaml


MAX_CAPTURE_CHARS = 50_000
MAX_SESSION_CHARS = 500_000
MAX_SESSION_EVENTS = 512
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]+$")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|secret|password|credential)\s*[:=]\s*[^\s,;]+"
)
_BEARER = re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]+")
_PRIVATE_KEY = re.compile(
    r"-----BEGIN [^-]+-----.*?-----END [^-]+-----", re.DOTALL
)
_THINK_BLOCK = re.compile(r"(?is)<think>.*?</think>")
_REASONING_ASSIGNMENT = re.compile(
    r"(?is)(?:hidden|producer)[_-]?reasoning\s*[:=]\s*[^,\n}\]]+"
)
_EVENT_SPEAKERS = frozenset({"user", "assistant", "tool", "runtime"})
_EVENT_TYPES = frozenset({"message", "tool_call", "tool_result", "runtime"})
_SENSITIVE_FIELD = re.compile(
    r"(?i)^(?:api[_-]?key|access[_-]?token|token|secret|password|credential|authorization)$"
)
_OMITTED_FIELD = re.compile(
    r"(?i)^(?:hidden[_-]?reasoning|producer[_-]?reasoning|reasoning|thinking|analysis|"
    r"raw[_-]?prompt|system[_-]?prompt)$"
)


def is_cold_transcript(content: str) -> bool:
    """Return whether Markdown has a recorder-compatible conversation event."""
    return any(
        line.startswith(("## Event ", "## Turn ")) for line in content.splitlines()
    )


class SessionRecorderError(RuntimeError):
    """A conversation could not be safely appended to its session record."""


@dataclass(frozen=True, slots=True)
class SessionTurnReceipt:
    path: Path
    role: str
    session_id: str
    turn_count: int
    turn_sha256: str


@dataclass(frozen=True, slots=True)
class SessionEventReceipt:
    path: Path
    role: str
    session_id: str
    event_count: int
    turn_count: int
    event_sha256: str


class SessionRecorder:
    """Append bounded redacted V20 events to cold session Markdown."""

    def __init__(
        self,
        knowledge_root: Path,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.knowledge_root = knowledge_root.resolve()
        self._clock = clock
        self._lock = threading.RLock()

    def record_turn(
        self,
        *,
        role: str,
        session_id: str,
        run_id: str,
        task_id: str,
        repository_revision: str,
        speaker: str,
        content: str,
        created_at: datetime | None = None,
    ) -> SessionTurnReceipt:
        if not isinstance(content, str) or not content.strip():
            raise SessionRecorderError("conversation content must be non-empty text")
        if speaker not in {"user", "assistant"}:
            raise SessionRecorderError("speaker must be user or assistant")
        receipt = self.record_event(
            role=role,
            session_id=session_id,
            run_id=run_id,
            task_id=task_id,
            repository_revision=repository_revision,
            speaker=speaker,
            event_type="message",
            content=content,
            created_at=created_at,
        )
        return SessionTurnReceipt(
            receipt.path,
            receipt.role,
            receipt.session_id,
            receipt.turn_count,
            receipt.event_sha256,
        )

    def record_event(
        self,
        *,
        role: str,
        session_id: str,
        run_id: str,
        task_id: str,
        repository_revision: str,
        speaker: str,
        event_type: str,
        content: object,
        metadata: Mapping[str, object] | None = None,
        created_at: datetime | None = None,
    ) -> SessionEventReceipt:
        if speaker not in _EVENT_SPEAKERS:
            raise SessionRecorderError(f"speaker must be one of: {', '.join(sorted(_EVENT_SPEAKERS))}")
        if event_type not in _EVENT_TYPES:
            raise SessionRecorderError(
                f"event type must be one of: {', '.join(sorted(_EVENT_TYPES))}"
            )
        for value, label in (
            (role, "role"),
            (session_id, "session ID"),
            (run_id, "run ID"),
            (task_id, "task ID"),
            (repository_revision, "repository revision"),
        ):
            self._validate_component(value, label)
        timestamp = (created_at or self._clock()).astimezone(timezone.utc)
        redacted_content = self._serialize_payload(content)
        redacted_metadata = (
            None if metadata is None else self._serialize_payload(metadata)
        )
        if not redacted_content.strip() and redacted_metadata is None:
            raise SessionRecorderError("session event content must be non-empty")
        path = (
            self.knowledge_root
            / "sessions"
            / timestamp.date().isoformat()
            / f"{role}--{session_id}.md"
        )
        with self._lock:
            metadata, body = self._load_existing(path)
            if metadata:
                expected = {
                    "role": role,
                    "session_id": session_id,
                    "run_id": run_id,
                    "task_id": task_id,
                    "repository_revision": repository_revision,
                }
                if any(str(metadata.get(key)) != value for key, value in expected.items()):
                    raise SessionRecorderError("session identity conflicts with existing record")
                event_count = int(metadata.get("event_count", metadata.get("turn_count", 0))) + 1
                turn_count = int(metadata.get("turn_count", 0)) + (
                    1 if event_type == "message" else 0
                )
                created_value = str(metadata.get("created_at"))
            else:
                event_count = 1
                turn_count = 1 if event_type == "message" else 0
                created_value = timestamp.isoformat().replace("+00:00", "Z")
            if event_count > MAX_SESSION_EVENTS:
                raise SessionRecorderError("session event limit reached")
            updated_value = timestamp.isoformat().replace("+00:00", "Z")
            event_material = {
                "event_count": event_count,
                "event_type": event_type,
                "speaker": speaker,
                "content": redacted_content,
                "metadata": redacted_metadata,
            }
            event_hash = hashlib.sha256(
                json.dumps(event_material, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            frontmatter = self._frontmatter(
                kind="session-transcript",
                status="redacted",
                role=role,
                session_id=session_id,
                run_id=run_id,
                task_id=task_id,
                repository_revision=repository_revision,
                created_at=created_value,
                updated_at=updated_value,
                event_count=event_count,
                turn_count=turn_count,
            )
            heading = f"## Event {event_count} — {speaker} / {event_type}\n\n"
            if redacted_metadata is not None:
                heading += f"metadata: {redacted_metadata}\n\n"
            event_body = (
                heading
                + redacted_content
                + f"\n\n<!-- event_sha256: {event_hash} -->\n\n"
            )
            if len(body) + len(event_body) > MAX_SESSION_CHARS:
                event_body = (
                    heading
                    + "[EVENT CONTENT OMITTED: SESSION CAP REACHED]"
                    + f"\n\n<!-- event_sha256: {event_hash} -->\n\n"
                )
                if len(body) + len(event_body) > MAX_SESSION_CHARS:
                    raise SessionRecorderError("session event cannot fit within session limit")
            new_body = body + event_body
            self._atomic_write(path, frontmatter + new_body)
        return SessionEventReceipt(path, role, session_id, event_count, turn_count, event_hash)

    @staticmethod
    def redact(content: str) -> str:
        if "\x00" in content:
            raise SessionRecorderError("conversation content contains a NUL byte")
        cleaned = _THINK_BLOCK.sub("[REASONING OMITTED]", content)
        cleaned = _REASONING_ASSIGNMENT.sub("[REASONING OMITTED]", cleaned)
        cleaned = _PRIVATE_KEY.sub("[PRIVATE KEY REDACTED]", cleaned)
        cleaned = _SECRET_ASSIGNMENT.sub(
            lambda match: f"{match.group(1)}=[REDACTED]", cleaned
        )
        cleaned = _BEARER.sub(r"\1 [REDACTED]", cleaned)
        cleaned = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "[TOKEN REDACTED]", cleaned)
        if len(cleaned) > MAX_CAPTURE_CHARS:
            cleaned = cleaned[:MAX_CAPTURE_CHARS] + "\n[TURN TRUNCATED]\n"
        return cleaned.strip()

    @classmethod
    def redact_payload(cls, value: object) -> object:
        if isinstance(value, str):
            return cls.redact(value)
        if isinstance(value, Mapping):
            redacted = {}
            for key, item in value.items():
                field = str(key)
                redacted[field] = (
                    "[REDACTED]"
                    if _SENSITIVE_FIELD.fullmatch(field)
                    else "[REASONING OMITTED]"
                    if _OMITTED_FIELD.fullmatch(field)
                    else cls.redact_payload(item)
                )
            return redacted
        if isinstance(value, (list, tuple)):
            return [cls.redact_payload(item) for item in value]
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return cls.redact(str(value))

    @classmethod
    def _serialize_payload(cls, value: object) -> str:
        redacted = cls.redact_payload(value)
        if isinstance(redacted, str):
            serialized = redacted
        else:
            serialized = json.dumps(redacted, ensure_ascii=False, sort_keys=True)
        if len(serialized) > MAX_CAPTURE_CHARS:
            serialized = serialized[:MAX_CAPTURE_CHARS] + "\n[EVENT TRUNCATED]\n"
        return serialized

    @staticmethod
    def _validate_component(value: str, label: str) -> None:
        if not isinstance(value, str) or not value or not _SAFE_COMPONENT.fullmatch(value):
            raise SessionRecorderError(f"{label} contains unsafe path characters")

    @staticmethod
    def _frontmatter(**values: object) -> str:
        lines = []
        for key, value in values.items():
            serialized = json.dumps(value, ensure_ascii=False) if isinstance(value, str) else value
            lines.append(f"{key}: {serialized}")
        return "---\n" + "\n".join(lines) + "\n---\n\n"

    @staticmethod
    def _load_existing(path: Path) -> tuple[dict[str, object], str]:
        if not path.exists():
            return {}, ""
        try:
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        except UnicodeDecodeError as exc:
            raise SessionRecorderError("existing session record is not valid UTF-8") from exc
        if not lines or lines[0].strip() != "---":
            raise SessionRecorderError("existing session record has invalid frontmatter")
        try:
            boundary = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
        except StopIteration as exc:
            raise SessionRecorderError("existing session frontmatter is unterminated") from exc
        raw = yaml.safe_load("".join(lines[1:boundary]))
        if not isinstance(raw, dict):
            raise SessionRecorderError("existing session frontmatter must be a mapping")
        return dict(raw), "".join(lines[boundary + 1 :])

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
