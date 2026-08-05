"""Controller-owned, bounded V20 working memory."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Callable, Iterator, Literal, TypeAlias
from urllib.parse import quote

import yaml


CORE_WORD_LIMIT = 2_000
SAFETY_RARITY_THRESHOLD = 80
SAFETY_SCORE_FLOOR = 400
_APPLICATION_ID = 0x5632304D
_SCHEMA_VERSION = 1
_EXPECTED_COLUMNS = {
    "memory_proposals": (
        "memory_id",
        "candidate_json",
        "candidate_sha256",
        "proposal_json",
        "proposed_at_utc",
    ),
    "memory_items": ("memory_id", "status", "created_at_utc", "updated_at_utc"),
    "memory_changes": (
        "change_id",
        "status",
        "trigger",
        "receipt_json",
        "before_state_json",
        "after_state_json",
        "created_at_utc",
    ),
    "memory_change_files": (
        "change_id",
        "relative_path",
        "before_exists",
        "before_payload",
        "after_exists",
        "after_payload",
    ),
}
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_WORD_RE = re.compile(r"\b\w+(?:['’]\w+)*\b", re.UNICODE)
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:api[ _-]?key|secret|password|access[ _-]?token|bearer)\b\s*[:=]\s*\S+"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
)
_TASK_PROGRESS_RE = re.compile(
    r"(?i)^\s*(?:#+\s*)?(?:(?:task progress|progress update|session outcome|run status)"
    r"\s*[:=-]|(?:task|work)\s+is\s+(?:currently\s+)?in progress\b)"
)
_TEMPORARY_BLOCKER_RE = re.compile(
    r"(?i)^\s*(?:#+\s*)?(?:(?:temporary|current) blocker\s*[:=-]|"
    r"waiting for (?:this|the) (?:run|task|session)\b)"
)
_UNSUPPORTED_CLAIM_RE = re.compile(
    r"(?i)^\s*(?:#+\s*)?(?:unverified|unsupported claim|speculation)\s*[:=-]"
)
_DIRECT_SECRET_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{16,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
)
_COMPOUND_SECRET_RE = re.compile(
    r"(?i)\b[A-Za-z][A-Za-z0-9_-]{0,40}"
    r"(?:secret|password|token|api[_-]?key|private[_-]?key)"
    r"[A-Za-z0-9_-]{0,20}\s*[:=]\s*\S+"
)
_LOCK_TIMEOUT_SECONDS = 5.0
_LOCK_POLL_SECONDS = 0.05
_DURABLE_CATEGORIES = {
    "stable-preference",
    "project-invariant",
    "verified-procedure",
    "durable-lesson",
    "safety-fact",
}


MemoryCategory: TypeAlias = Literal[
    "stable-preference",
    "project-invariant",
    "verified-procedure",
    "durable-lesson",
    "safety-fact",
]
MemoryStatus: TypeAlias = Literal["core", "archived"]
CurationTrigger: TypeAlias = Literal["validated-work", "daily"]
ChangeTrigger: TypeAlias = Literal["validated-work", "daily", "rollback"]


class WorkingMemoryError(RuntimeError):
    """Base error for managed working memory."""


class WorkingMemoryRejected(WorkingMemoryError):
    """A candidate or destination crossed the memory policy."""


class WorkingMemoryConflict(WorkingMemoryError):
    """An immutable ID was reused with different content."""


@dataclass(frozen=True, slots=True)
class MemoryValueScore:
    evidence: int
    usefulness: int
    reuse: int
    relevance: int
    age: int
    safety_rarity: int

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if type(value) is not int or not 0 <= value <= 100:
                raise ValueError(f"{name} must be an integer from 0 through 100")

    @property
    def total(self) -> int:
        raw = (
            self.evidence
            + self.usefulness
            + self.reuse
            + self.relevance
            + self.age
            + self.safety_rarity
        )
        if self.safety_rarity >= SAFETY_RARITY_THRESHOLD:
            return max(raw, SAFETY_SCORE_FLOOR)
        return raw


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    memory_id: str
    content: str
    scope: str
    category: MemoryCategory
    supported: bool
    evidence_ids: tuple[str, ...]
    reason: str
    score: MemoryValueScore
    supersedes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MemoryProposal:
    memory_id: str
    accepted_at_utc: datetime
    evidence_ids: tuple[str, ...]
    reason: str
    score: MemoryValueScore
    content_hash: str


@dataclass(frozen=True, slots=True)
class MemoryItem:
    memory_id: str
    content: str
    scope: Literal["v20"]
    category: MemoryCategory
    status: MemoryStatus
    evidence_ids: tuple[str, ...]
    reason: str
    score: MemoryValueScore
    supersedes: tuple[str, ...]
    created_at_utc: datetime
    updated_at_utc: datetime
    content_hash: str


@dataclass(frozen=True, slots=True)
class MemoryChangeReceipt:
    change_id: str
    trigger: ChangeTrigger
    status: Literal["committed"]
    reason: str
    evidence_ids: tuple[str, ...]
    before_hash: str
    after_hash: str
    restored_hash: str | None
    added_ids: tuple[str, ...]
    removed_ids: tuple[str, ...]
    created_at_utc: datetime


def default_vault_path() -> Path:
    """Return the approved default without creating or opening it."""
    profile = os.environ.get("USERPROFILE")
    home = Path(profile) if profile else Path.home()
    return home / "Documents" / "V20 Qwen Vault"


def word_count(value: str | tuple[MemoryItem, ...] | list[MemoryItem]) -> int:
    """Count Unicode words in text or managed memory items."""
    if isinstance(value, str):
        return len(_WORD_RE.findall(value))
    if not isinstance(value, (tuple, list)):
        raise TypeError("word_count requires text or a sequence of MemoryItem values")
    if any(type(item) is not MemoryItem for item in value):
        raise TypeError("word_count item sequences must contain MemoryItem values")
    return sum(word_count(item.content) for item in value)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() != timedelta(0):
        raise WorkingMemoryError("ledger timestamp is not UTC")
    return parsed.astimezone(timezone.utc)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )


def _score_json(score: MemoryValueScore) -> dict[str, int]:
    return asdict(score)


def _score_from_json(value: object) -> MemoryValueScore:
    if not isinstance(value, dict):
        raise WorkingMemoryError("stored score is invalid")
    try:
        return MemoryValueScore(**value)
    except (TypeError, ValueError) as exc:
        raise WorkingMemoryError("stored score is invalid") from exc


def _candidate_json(candidate: MemoryCandidate) -> dict[str, object]:
    return {
        "memory_id": candidate.memory_id,
        "content": candidate.content,
        "scope": candidate.scope,
        "category": candidate.category,
        "supported": candidate.supported,
        "evidence_ids": list(candidate.evidence_ids),
        "reason": candidate.reason,
        "score": _score_json(candidate.score),
        "supersedes": list(candidate.supersedes),
    }


def _proposal_json(proposal: MemoryProposal) -> dict[str, object]:
    return {
        "memory_id": proposal.memory_id,
        "accepted_at_utc": _utc_text(proposal.accepted_at_utc),
        "evidence_ids": list(proposal.evidence_ids),
        "reason": proposal.reason,
        "score": _score_json(proposal.score),
        "content_hash": proposal.content_hash,
    }


def _receipt_json(receipt: MemoryChangeReceipt) -> dict[str, object]:
    return {
        "change_id": receipt.change_id,
        "trigger": receipt.trigger,
        "status": receipt.status,
        "reason": receipt.reason,
        "evidence_ids": list(receipt.evidence_ids),
        "before_hash": receipt.before_hash,
        "after_hash": receipt.after_hash,
        "restored_hash": receipt.restored_hash,
        "added_ids": list(receipt.added_ids),
        "removed_ids": list(receipt.removed_ids),
        "created_at_utc": _utc_text(receipt.created_at_utc),
    }


def _receipt_from_json(value: str) -> MemoryChangeReceipt:
    try:
        raw = json.loads(value)
        return MemoryChangeReceipt(
            change_id=str(raw["change_id"]),
            trigger=raw["trigger"],
            status=raw["status"],
            reason=str(raw["reason"]),
            evidence_ids=tuple(str(item) for item in raw["evidence_ids"]),
            before_hash=str(raw["before_hash"]),
            after_hash=str(raw["after_hash"]),
            restored_hash=(None if raw["restored_hash"] is None else str(raw["restored_hash"])),
            added_ids=tuple(str(item) for item in raw["added_ids"]),
            removed_ids=tuple(str(item) for item in raw["removed_ids"]),
            created_at_utc=_parse_utc(str(raw["created_at_utc"])),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise WorkingMemoryError("stored memory receipt is invalid") from exc


def _atomic_replace(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


@contextmanager
def _exclusive_writer_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
            os.fsync(handle.fileno())
        deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
        acquired = False
        while not acquired:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise WorkingMemoryError("working memory writer lock is already held") from exc
                time.sleep(_LOCK_POLL_SECONDS)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _safe_file_stem(identifier: str) -> str:
    encoded = quote(identifier, safe="-_.")
    if len(encoded) <= 180:
        return encoded
    return f"{encoded[:140]}-{_sha256(identifier.encode('utf-8'))[:32]}"


class WorkingMemoryStore:
    """Persist validated V20 candidates and curate a reversible 2,000-word core."""

    def __init__(
        self,
        vault: Path | None = None,
        *,
        repository_root: Path | None = None,
        clock: Callable[[], datetime] = _utc_now,
        id_factory: Callable[[], str] = lambda: f"change:{uuid.uuid4()}",
        candidate_validator: Callable[[MemoryCandidate], bool] | None = None,
        after_files_written: Callable[[str], None] | None = None,
    ) -> None:
        if vault is not None and not isinstance(vault, Path):
            raise TypeError("vault must be a Path")
        root = Path(__file__).resolve().parents[3] if repository_root is None else repository_root
        if not isinstance(root, Path):
            raise TypeError("repository_root must be a Path")
        resolved_vault = (default_vault_path() if vault is None else vault).resolve(strict=False)
        knowledge_root = (root / "knowledge").resolve(strict=False)
        if resolved_vault == knowledge_root or resolved_vault.is_relative_to(knowledge_root):
            raise WorkingMemoryRejected("working memory cannot write to repository knowledge")
        self._vault = resolved_vault
        self._clock = clock
        self._id_factory = id_factory
        self._candidate_validator = candidate_validator
        self._after_files_written = after_files_written
        self._thread_lock = threading.RLock()
        self._closed = False
        self._vault.mkdir(parents=True, exist_ok=True)
        database = self._vault / ".working-memory.sqlite3"
        if not database.resolve(strict=False).is_relative_to(self._vault):
            raise WorkingMemoryRejected("working memory ledger must stay inside the vault")
        self._lock_path = self._vault / ".working-memory.lock"
        if not self._lock_path.resolve(strict=False).is_relative_to(self._vault):
            raise WorkingMemoryRejected("working memory writer lock must stay inside the vault")
        try:
            self._connection = sqlite3.connect(database, isolation_level=None, timeout=5)
            self._connection.execute("PRAGMA busy_timeout = 5000")
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.execute("PRAGMA synchronous = FULL")
            self._initialize_schema()
            self.repair_prepared_changes()
        except WorkingMemoryError:
            if hasattr(self, "_connection"):
                self._connection.close()
            raise
        except (sqlite3.Error, OSError) as exc:
            if hasattr(self, "_connection"):
                self._connection.close()
            raise WorkingMemoryError("working memory ledger is unavailable") from exc

    def __enter__(self) -> WorkingMemoryStore:
        self._require_open()
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._connection.close()
        self._closed = True

    def propose(self, candidate: MemoryCandidate) -> MemoryProposal:
        self._require_open()
        self._validate_candidate(candidate)
        self._require_controller_validation(candidate)
        with self._writer_lock():
            return self._propose_locked(candidate)

    def _propose_locked(self, candidate: MemoryCandidate) -> MemoryProposal:
        now = self._now()
        candidate_payload = _candidate_json(candidate)
        candidate_text = _json(candidate_payload)
        payload_hash = _sha256(candidate_text.encode("utf-8"))
        proposal = MemoryProposal(
            memory_id=candidate.memory_id,
            accepted_at_utc=now,
            evidence_ids=candidate.evidence_ids,
            reason=candidate.reason,
            score=candidate.score,
            content_hash=_sha256(candidate.content.encode("utf-8")),
        )
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT candidate_json, proposal_json FROM memory_proposals WHERE memory_id = ?",
                (candidate.memory_id,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != candidate_text:
                    raise WorkingMemoryConflict(
                        "memory ID is already proposed with different content"
                    )
                return self._proposal_from_json(str(existing[1]))
            connection.execute(
                """
                INSERT INTO memory_proposals (
                    memory_id, candidate_json, candidate_sha256, proposal_json, proposed_at_utc
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    candidate.memory_id,
                    candidate_text,
                    payload_hash,
                    _json(_proposal_json(proposal)),
                    _utc_text(now),
                ),
            )
        return proposal

    def curate(self, trigger: CurationTrigger) -> MemoryChangeReceipt:
        self._require_open()
        if trigger not in {"validated-work", "daily"}:
            raise ValueError("curation trigger must be validated-work or daily")
        with self._writer_lock():
            return self._curate_locked(trigger)

    def _curate_locked(self, trigger: CurationTrigger) -> MemoryChangeReceipt:
        candidates = self._all_candidates()
        selected = self._deterministic_selection(candidates)
        before_state = self._current_state()
        after_state = {
            candidate.memory_id: ("core" if candidate.memory_id in selected else "archived")
            for candidate, _accepted_at in candidates
        }
        evidence_ids = tuple(
            sorted(
                {
                    evidence_id
                    for candidate, _accepted_at in candidates
                    for evidence_id in candidate.evidence_ids
                }
            )
        )
        return self._apply_state_change(
            trigger=trigger,
            reason=f"Controller curation after {trigger}.",
            evidence_ids=evidence_ids,
            before_state=before_state,
            after_state=after_state,
        )

    def core(self) -> tuple[MemoryItem, ...]:
        self._require_open()
        return self._items("core")

    def archive(self, query: str, limit: int = 100) -> tuple[MemoryItem, ...]:
        self._require_open()
        if not isinstance(query, str) or not query.strip() or len(query) > 256:
            raise ValueError("archive query must contain 1 through 256 characters")
        self._validate_limit(limit)
        needle = query.casefold()
        matches = (
            item
            for item in self._items("archived")
            if needle in item.memory_id.casefold()
            or needle in item.content.casefold()
            or needle in item.reason.casefold()
        )
        return tuple(list(matches)[:limit])

    def history(self, limit: int = 100) -> tuple[MemoryChangeReceipt, ...]:
        self._require_open()
        self._validate_limit(limit)
        rows = self._connection.execute(
            """
            SELECT receipt_json FROM memory_changes
            WHERE status = 'committed'
            ORDER BY rowid DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return tuple(_receipt_from_json(str(row[0])) for row in rows)

    def rollback(self, change_id: str) -> MemoryChangeReceipt:
        self._require_open()
        self._validate_id(change_id, "change ID")
        with self._writer_lock():
            return self._rollback_locked(change_id)

    def _rollback_locked(self, change_id: str) -> MemoryChangeReceipt:
        row = self._connection.execute(
            """
            SELECT before_state_json, receipt_json FROM memory_changes
            WHERE change_id = ? AND status = 'committed'
            """,
            (change_id,),
        ).fetchone()
        if row is None:
            raise WorkingMemoryRejected("rollback target is not a committed memory change")
        target_state = self._decode_state(str(row[0]))
        target_receipt = _receipt_from_json(str(row[1]))
        all_ids = {candidate.memory_id for candidate, _accepted_at in self._all_candidates()}
        after_state: dict[str, MemoryStatus] = {memory_id: "archived" for memory_id in all_ids}
        after_state.update(target_state)
        core_image = self._connection.execute(
            """
            SELECT before_exists, before_payload FROM memory_change_files
            WHERE change_id = ? AND relative_path = 'Core Memory.md'
            """,
            (change_id,),
        ).fetchone()
        override = None
        if core_image is not None:
            override = (bool(core_image[0]), core_image[1])
        return self._apply_state_change(
            trigger="rollback",
            reason=f"Controller rollback of {change_id}.",
            evidence_ids=target_receipt.evidence_ids,
            before_state=self._current_state(),
            after_state=after_state,
            restored_hash=target_receipt.before_hash,
            core_override=override,
        )

    def repair_prepared_changes(self) -> None:
        self._require_open()
        with self._writer_lock():
            self._repair_prepared_changes_locked()

    def _repair_prepared_changes_locked(self) -> None:
        rows = self._connection.execute(
            """
            SELECT change_id FROM memory_changes
            WHERE status = 'prepared' ORDER BY rowid DESC
            """
        ).fetchall()
        for row in rows:
            change_id = str(row[0])
            before = self._prepared_before_images(change_id)
            self._restore_before_images(before)
            with self._transaction() as connection:
                connection.execute(
                    "UPDATE memory_changes SET status = 'rolled_back' WHERE change_id = ?",
                    (change_id,),
                )

    def _initialize_schema(self) -> None:
        application_id = int(self._connection.execute("PRAGMA application_id").fetchone()[0])
        version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
        object_count = int(
            self._connection.execute(
                "SELECT COUNT(*) FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'"
            ).fetchone()[0]
        )
        if application_id not in {0, _APPLICATION_ID}:
            raise WorkingMemoryError("working memory ledger has an unexpected owner")
        if version not in {0, _SCHEMA_VERSION}:
            raise WorkingMemoryError("working memory ledger has an unsupported schema")
        if (application_id == 0 or version == 0) and object_count:
            raise WorkingMemoryError("working memory ledger schema is unrecognized")
        if application_id == 0 and version == 0 and object_count == 0:
            try:
                self._connection.executescript(
                    f"""
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS memory_proposals (
                    memory_id TEXT PRIMARY KEY,
                    candidate_json TEXT NOT NULL CHECK(json_valid(candidate_json)),
                    candidate_sha256 TEXT NOT NULL CHECK(length(candidate_sha256) = 64),
                    proposal_json TEXT NOT NULL CHECK(json_valid(proposal_json)),
                    proposed_at_utc TEXT NOT NULL
                ) STRICT;
                CREATE TABLE IF NOT EXISTS memory_items (
                    memory_id TEXT PRIMARY KEY REFERENCES memory_proposals(memory_id),
                    status TEXT NOT NULL CHECK(status IN ('core', 'archived')),
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                ) STRICT;
                CREATE TABLE IF NOT EXISTS memory_changes (
                    change_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK(status IN ('prepared', 'committed', 'rolled_back')),
                    trigger TEXT NOT NULL CHECK(trigger IN ('validated-work', 'daily', 'rollback')),
                    receipt_json TEXT NOT NULL CHECK(json_valid(receipt_json)),
                    before_state_json TEXT NOT NULL CHECK(json_valid(before_state_json)),
                    after_state_json TEXT NOT NULL CHECK(json_valid(after_state_json)),
                    created_at_utc TEXT NOT NULL
                ) STRICT;
                CREATE TABLE IF NOT EXISTS memory_change_files (
                    change_id TEXT NOT NULL REFERENCES memory_changes(change_id),
                    relative_path TEXT NOT NULL,
                    before_exists INTEGER NOT NULL CHECK(before_exists IN (0, 1)),
                    before_payload BLOB,
                    after_exists INTEGER NOT NULL CHECK(after_exists IN (0, 1)),
                    after_payload BLOB,
                    PRIMARY KEY(change_id, relative_path),
                    CHECK((before_exists = 1) = (before_payload IS NOT NULL)),
                    CHECK((after_exists = 1) = (after_payload IS NOT NULL))
                ) STRICT;
                PRAGMA application_id = {_APPLICATION_ID};
                PRAGMA user_version = {_SCHEMA_VERSION};
                COMMIT;
                """
                )
            except BaseException:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise
        self._validate_schema()
        if tuple(str(row[0]) for row in self._connection.execute("PRAGMA quick_check")) != ("ok",):
            raise WorkingMemoryError("working memory ledger failed integrity checking")

    def _validate_schema(self) -> None:
        objects = {
            str(row[0]): str(row[1])
            for row in self._connection.execute(
                "SELECT name, type FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'"
            )
        }
        if objects != {name: "table" for name in _EXPECTED_COLUMNS}:
            raise WorkingMemoryError("working memory ledger schema is incomplete or changed")
        for table, expected in _EXPECTED_COLUMNS.items():
            actual = tuple(
                str(row[1]) for row in self._connection.execute(f"PRAGMA table_info({table})")
            )
            if actual != expected:
                raise WorkingMemoryError("working memory ledger schema columns are invalid")

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        self._require_open()
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            yield self._connection
            self._connection.execute("COMMIT")
        except BaseException:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise

    def _apply_state_change(
        self,
        *,
        trigger: ChangeTrigger,
        reason: str,
        evidence_ids: tuple[str, ...],
        before_state: dict[str, MemoryStatus],
        after_state: dict[str, MemoryStatus],
        restored_hash: str | None = None,
        core_override: tuple[bool, bytes | None] | None = None,
    ) -> MemoryChangeReceipt:
        change_id = self._id_factory()
        self._validate_id(change_id, "change ID")
        now = self._now()
        before_core = {key for key, status in before_state.items() if status == "core"}
        after_core = {key for key, status in after_state.items() if status == "core"}
        receipt = MemoryChangeReceipt(
            change_id=change_id,
            trigger=trigger,
            status="committed",
            reason=reason,
            evidence_ids=tuple(sorted(set(evidence_ids))),
            before_hash=self._core_hash(before_state),
            after_hash=self._core_hash(after_state),
            restored_hash=restored_hash,
            added_ids=tuple(sorted(after_core - before_core)),
            removed_ids=tuple(sorted(before_core - after_core)),
            created_at_utc=now,
        )
        writes = self._state_writes(after_state, receipt, core_override)
        before_images = {path: path.read_bytes() if path.is_file() else None for path in writes}
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO memory_changes (
                    change_id, status, trigger, receipt_json,
                    before_state_json, after_state_json, created_at_utc
                ) VALUES (?, 'prepared', ?, ?, ?, ?, ?)
                """,
                (
                    change_id,
                    trigger,
                    _json(_receipt_json(receipt)),
                    _json(before_state),
                    _json(after_state),
                    _utc_text(now),
                ),
            )
            for path, payload in writes.items():
                relative = path.relative_to(self._vault).as_posix()
                before = before_images[path]
                connection.execute(
                    """
                    INSERT INTO memory_change_files (
                        change_id, relative_path, before_exists, before_payload,
                        after_exists, after_payload
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        change_id,
                        relative,
                        int(before is not None),
                        before,
                        int(payload is not None),
                        payload,
                    ),
                )
        try:
            for path, payload in writes.items():
                if payload is None:
                    path.unlink(missing_ok=True)
                else:
                    _atomic_replace(path, payload)
            if self._after_files_written is not None:
                self._after_files_written(change_id)
            proposed_at = {
                candidate.memory_id: accepted_at
                for candidate, accepted_at in self._all_candidates()
            }
            with self._transaction() as connection:
                for memory_id, status in after_state.items():
                    accepted_at = proposed_at[memory_id]
                    updated_at = max(now, accepted_at)
                    connection.execute(
                        """
                        INSERT INTO memory_items (
                            memory_id, status, created_at_utc, updated_at_utc
                        ) VALUES (?, ?, ?, ?)
                        ON CONFLICT(memory_id) DO UPDATE SET
                            status = excluded.status,
                            updated_at_utc = CASE
                                WHEN memory_items.status != excluded.status
                                THEN max(memory_items.updated_at_utc, excluded.updated_at_utc)
                                ELSE memory_items.updated_at_utc
                            END
                        """,
                        (
                            memory_id,
                            status,
                            _utc_text(accepted_at),
                            _utc_text(updated_at),
                        ),
                    )
                connection.execute(
                    "UPDATE memory_changes SET status = 'committed' WHERE change_id = ?",
                    (change_id,),
                )
            return receipt
        except BaseException:
            self._restore_before_images(before_images)
            with self._transaction() as connection:
                connection.execute(
                    "UPDATE memory_changes SET status = 'rolled_back' WHERE change_id = ?",
                    (change_id,),
                )
            raise

    def _state_writes(
        self,
        state: dict[str, MemoryStatus],
        receipt: MemoryChangeReceipt,
        core_override: tuple[bool, bytes | None] | None,
    ) -> dict[Path, bytes | None]:
        items = self._items_for_state(state, receipt.created_at_utc)
        core_items = tuple(item for item in items if item.status == "core")
        writes: dict[Path, bytes | None] = {}
        core_path = self._ledger_path("Core Memory.md")
        if core_override is None:
            writes[core_path] = self._render_core(core_items)
        else:
            exists, payload = core_override
            writes[core_path] = payload if exists else None
        for item in items:
            archive_path = self._ledger_path(f"Archive/{_safe_file_stem(item.memory_id)}.md")
            writes[archive_path] = self._render_archive(item) if item.status == "archived" else None
        history_path = self._ledger_path(f"History/{_safe_file_stem(receipt.change_id)}.md")
        writes[history_path] = self._render_history(receipt)
        return writes

    def _render_core(self, items: tuple[MemoryItem, ...]) -> bytes:
        body = "# V20 Core Memory\n"
        if items:
            body += "\n" + "\n\n".join(
                f"## {item.memory_id}\n\n{item.content.strip()}" for item in items
            )
            body += "\n"
        score_components = {
            name: sum(getattr(item.score, name) for item in items)
            for name in asdict(MemoryValueScore(0, 0, 0, 0, 0, 0))
        }
        metadata = {
            "id": "core-memory",
            "status": "core",
            "scope": "v20",
            "created_utc": (
                _utc_text(min(item.created_at_utc for item in items)) if items else None
            ),
            "updated_utc": (
                _utc_text(max(item.updated_at_utc for item in items)) if items else None
            ),
            "memory_ids": [item.memory_id for item in items],
            "evidence_ids": sorted(
                {evidence_id for item in items for evidence_id in item.evidence_ids}
            ),
            "score_components": score_components,
            "supersedes": sorted({memory_id for item in items for memory_id in item.supersedes}),
            "word_count": word_count(list(items)),
            "word_limit": CORE_WORD_LIMIT,
            "content_sha256": _sha256(body.encode("utf-8")),
        }
        return self._markdown(metadata, body)

    def _render_archive(self, item: MemoryItem) -> bytes:
        body = f"# {item.memory_id}\n\n{item.content.strip()}\n"
        metadata = {
            "id": item.memory_id,
            "status": "archived",
            "scope": item.scope,
            "category": item.category,
            "created_utc": _utc_text(item.created_at_utc),
            "updated_utc": _utc_text(item.updated_at_utc),
            "evidence_ids": list(item.evidence_ids),
            "reason": item.reason,
            "score_components": _score_json(item.score),
            "score_total": item.score.total,
            "supersedes": list(item.supersedes),
            "content_sha256": item.content_hash,
        }
        return self._markdown(metadata, body)

    def _render_history(self, receipt: MemoryChangeReceipt) -> bytes:
        body = f"# Memory change {receipt.change_id}\n\n{receipt.reason}\n"
        metadata = {
            "id": receipt.change_id,
            "status": receipt.status,
            "trigger": receipt.trigger,
            "created_utc": _utc_text(receipt.created_at_utc),
            "updated_utc": _utc_text(receipt.created_at_utc),
            "evidence_ids": list(receipt.evidence_ids),
            "reason": receipt.reason,
            "before_sha256": receipt.before_hash,
            "after_sha256": receipt.after_hash,
            "restored_sha256": receipt.restored_hash,
            "added_ids": list(receipt.added_ids),
            "removed_ids": list(receipt.removed_ids),
            "content_sha256": _sha256(body.encode("utf-8")),
        }
        return self._markdown(metadata, body)

    @staticmethod
    def _markdown(metadata: dict[str, object], body: str) -> bytes:
        front = yaml.safe_dump(
            metadata,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
        return f"---\n{front}---\n{body}".encode("utf-8")

    def _items(self, status: MemoryStatus) -> tuple[MemoryItem, ...]:
        rows = self._connection.execute(
            """
            SELECT p.candidate_json, i.status, i.created_at_utc, i.updated_at_utc
            FROM memory_items AS i
            JOIN memory_proposals AS p USING(memory_id)
            WHERE i.status = ?
            """,
            (status,),
        ).fetchall()
        items = tuple(
            self._item_from_row(
                str(row[0]),
                row[1],
                str(row[2]),
                str(row[3]),
            )
            for row in rows
        )
        return tuple(sorted(items, key=lambda item: (-item.score.total, item.memory_id)))

    def _items_for_state(
        self,
        state: dict[str, MemoryStatus],
        changed_at: datetime,
    ) -> tuple[MemoryItem, ...]:
        candidates = {
            candidate.memory_id: (candidate, accepted_at)
            for candidate, accepted_at in self._all_candidates()
        }
        current = {
            str(row[0]): (
                row[1],
                _parse_utc(str(row[2])),
                _parse_utc(str(row[3])),
            )
            for row in self._connection.execute(
                """
                SELECT memory_id, status, created_at_utc, updated_at_utc
                FROM memory_items
                """
            )
        }
        items: list[MemoryItem] = []
        for memory_id, status in state.items():
            candidate, accepted_at = candidates[memory_id]
            existing = current.get(memory_id)
            if existing is None:
                created_at = accepted_at
                updated_at = max(changed_at, accepted_at)
            else:
                old_status, created_at, prior_updated_at = existing
                updated_at = (
                    max(prior_updated_at, changed_at) if old_status != status else prior_updated_at
                )
            items.append(
                self._item_from_candidate(
                    (candidate, accepted_at),
                    status,
                    created_at=created_at,
                    updated_at=updated_at,
                )
            )
        return tuple(sorted(items, key=lambda item: (-item.score.total, item.memory_id)))

    @staticmethod
    def _item_from_candidate(
        value: tuple[MemoryCandidate, datetime],
        status: MemoryStatus,
        *,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> MemoryItem:
        candidate, accepted_at = value
        return MemoryItem(
            memory_id=candidate.memory_id,
            content=candidate.content,
            scope="v20",
            category=candidate.category,
            status=status,
            evidence_ids=candidate.evidence_ids,
            reason=candidate.reason,
            score=candidate.score,
            supersedes=candidate.supersedes,
            created_at_utc=created_at or accepted_at,
            updated_at_utc=updated_at or accepted_at,
            content_hash=_sha256(candidate.content.encode("utf-8")),
        )

    def _item_from_row(
        self,
        candidate_json: str,
        status: object,
        created_at_utc: str,
        updated_at_utc: str,
    ) -> MemoryItem:
        if status not in {"core", "archived"}:
            raise WorkingMemoryError("stored memory status is invalid")
        return self._item_from_candidate(
            (self._candidate_from_json(candidate_json), _parse_utc(created_at_utc)),
            status,
            created_at=_parse_utc(created_at_utc),
            updated_at=_parse_utc(updated_at_utc),
        )

    def _all_candidates(self) -> tuple[tuple[MemoryCandidate, datetime], ...]:
        rows = self._connection.execute(
            "SELECT candidate_json, proposed_at_utc FROM memory_proposals ORDER BY memory_id"
        ).fetchall()
        return tuple(
            (self._candidate_from_json(str(row[0])), _parse_utc(str(row[1]))) for row in rows
        )

    def _candidate_from_json(self, value: str) -> MemoryCandidate:
        try:
            raw = json.loads(value)
            candidate = MemoryCandidate(
                memory_id=str(raw["memory_id"]),
                content=str(raw["content"]),
                scope=str(raw["scope"]),
                category=raw["category"],
                supported=raw["supported"],
                evidence_ids=tuple(str(item) for item in raw["evidence_ids"]),
                reason=str(raw["reason"]),
                score=_score_from_json(raw["score"]),
                supersedes=tuple(str(item) for item in raw["supersedes"]),
            )
            self._validate_candidate(candidate)
            return candidate
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise WorkingMemoryError("stored memory candidate is invalid") from exc

    @staticmethod
    def _proposal_from_json(value: str) -> MemoryProposal:
        try:
            raw = json.loads(value)
            return MemoryProposal(
                memory_id=str(raw["memory_id"]),
                accepted_at_utc=_parse_utc(str(raw["accepted_at_utc"])),
                evidence_ids=tuple(str(item) for item in raw["evidence_ids"]),
                reason=str(raw["reason"]),
                score=_score_from_json(raw["score"]),
                content_hash=str(raw["content_hash"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise WorkingMemoryError("stored memory proposal is invalid") from exc

    def _current_state(self) -> dict[str, MemoryStatus]:
        return {
            str(row[0]): row[1]
            for row in self._connection.execute(
                "SELECT memory_id, status FROM memory_items ORDER BY memory_id"
            )
        }

    def _core_hash(self, state: dict[str, MemoryStatus]) -> str:
        candidates = {
            candidate.memory_id: _sha256(_json(_candidate_json(candidate)).encode("utf-8"))
            for candidate, _accepted_at in self._all_candidates()
        }
        core = [
            {"memory_id": memory_id, "candidate_sha256": candidates[memory_id]}
            for memory_id, status in sorted(state.items())
            if status == "core"
        ]
        return _sha256(_json(core).encode("utf-8"))

    @staticmethod
    def _deterministic_selection(
        candidates: tuple[tuple[MemoryCandidate, datetime], ...],
    ) -> frozenset[str]:
        ordered = sorted(
            (candidate for candidate, _at in candidates), key=lambda item: item.memory_id
        )
        states: list[tuple[int, tuple[str, ...]] | None] = [None] * (CORE_WORD_LIMIT + 1)
        states[0] = (0, ())
        for candidate in ordered:
            words = word_count(candidate.content)
            if words > CORE_WORD_LIMIT:
                continue
            for capacity in range(CORE_WORD_LIMIT, words - 1, -1):
                previous = states[capacity - words]
                if previous is None:
                    continue
                proposed = (
                    previous[0] + candidate.score.total,
                    (*previous[1], candidate.memory_id),
                )
                current = states[capacity]
                if (
                    current is None
                    or proposed[0] > current[0]
                    or (proposed[0] == current[0] and proposed[1] < current[1])
                ):
                    states[capacity] = proposed
        valid = (state for state in states if state is not None)
        best = next(valid, (0, ()))
        for state in valid:
            if state[0] > best[0] or (state[0] == best[0] and state[1] < best[1]):
                best = state
        return frozenset(best[1])

    def _prepared_before_images(self, change_id: str) -> dict[Path, bytes | None]:
        rows = self._connection.execute(
            """
            SELECT relative_path, before_exists, before_payload
            FROM memory_change_files WHERE change_id = ? ORDER BY relative_path
            """,
            (change_id,),
        ).fetchall()
        return {self._ledger_path(str(row[0])): row[2] if bool(row[1]) else None for row in rows}

    def _ledger_path(self, relative_path: str) -> Path:
        pure = PurePosixPath(relative_path)
        if pure.is_absolute() or not pure.parts or ".." in pure.parts:
            raise WorkingMemoryError("ledger contains an unsafe memory file path")
        path = self._vault.joinpath(*pure.parts)
        if not path.resolve(strict=False).is_relative_to(self._vault):
            raise WorkingMemoryError("ledger memory file leaves the vault")
        return path

    @staticmethod
    def _restore_before_images(before: dict[Path, bytes | None]) -> None:
        for path, payload in reversed(tuple(before.items())):
            if payload is None:
                path.unlink(missing_ok=True)
            else:
                _atomic_replace(path, payload)

    @staticmethod
    def _decode_state(value: str) -> dict[str, MemoryStatus]:
        try:
            raw = json.loads(value)
        except json.JSONDecodeError as exc:
            raise WorkingMemoryError("stored memory state is invalid") from exc
        if not isinstance(raw, dict) or any(
            not isinstance(key, str) or status not in {"core", "archived"}
            for key, status in raw.items()
        ):
            raise WorkingMemoryError("stored memory state is invalid")
        return raw

    @contextmanager
    def _writer_lock(self) -> Iterator[None]:
        self._require_open()
        with self._thread_lock, _exclusive_writer_lock(self._lock_path):
            yield

    def _require_controller_validation(self, candidate: MemoryCandidate) -> None:
        if self._candidate_validator is None:
            raise WorkingMemoryRejected("candidate requires controller validation")
        try:
            accepted = self._candidate_validator(candidate)
        except Exception as exc:
            raise WorkingMemoryRejected("candidate controller validation failed") from exc
        if accepted is not True:
            raise WorkingMemoryRejected("candidate failed controller validation")

    def _validate_candidate(self, candidate: MemoryCandidate) -> None:
        if type(candidate) is not MemoryCandidate:
            raise TypeError("candidate must be MemoryCandidate")
        self._validate_id(candidate.memory_id, "memory ID")
        if candidate.scope != "v20":
            raise WorkingMemoryRejected("candidate must use V20 scope")
        if type(candidate.supported) is not bool or not candidate.supported:
            raise WorkingMemoryRejected("candidate must be supported by current evidence")
        if not isinstance(candidate.category, str) or candidate.category not in _DURABLE_CATEGORIES:
            raise WorkingMemoryRejected("candidate must use a durable category")
        if not isinstance(candidate.content, str) or not candidate.content.strip():
            raise WorkingMemoryRejected("candidate content is required")
        if len(candidate.content) > 100_000 or word_count(candidate.content) == 0:
            raise WorkingMemoryRejected("candidate content must contain bounded Unicode words")
        if not isinstance(candidate.reason, str) or not 1 <= len(candidate.reason.strip()) <= 512:
            raise WorkingMemoryRejected("candidate requires a bounded reason")
        free_text = (candidate.content, candidate.reason)
        if any(
            pattern.search(text)
            for pattern in (*_SECRET_PATTERNS, *_DIRECT_SECRET_PATTERNS, _COMPOUND_SECRET_RE)
            for text in free_text
        ):
            raise WorkingMemoryRejected("candidate contains a possible secret")
        if _TASK_PROGRESS_RE.search(candidate.content):
            raise WorkingMemoryRejected("candidate is task progress, not durable memory")
        if _TEMPORARY_BLOCKER_RE.search(candidate.content):
            raise WorkingMemoryRejected("candidate is a temporary blocker")
        if _UNSUPPORTED_CLAIM_RE.search(candidate.content):
            raise WorkingMemoryRejected("candidate is an unsupported claim")
        if (
            not isinstance(candidate.evidence_ids, tuple)
            or not 1 <= len(candidate.evidence_ids) <= 32
        ):
            raise WorkingMemoryRejected("candidate requires evidence IDs")
        if len(set(candidate.evidence_ids)) != len(candidate.evidence_ids):
            raise WorkingMemoryRejected("candidate evidence IDs must be unique")
        for evidence_id in candidate.evidence_ids:
            self._validate_id(evidence_id, "evidence ID")
        if type(candidate.score) is not MemoryValueScore:
            raise WorkingMemoryRejected("candidate requires a MemoryValueScore")
        if not isinstance(candidate.supersedes, tuple) or len(candidate.supersedes) > 32:
            raise WorkingMemoryRejected("candidate supersedes must be a bounded tuple")
        for memory_id in candidate.supersedes:
            self._validate_id(memory_id, "superseded memory ID")

    @staticmethod
    def _validate_id(value: object, label: str) -> None:
        if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
            raise WorkingMemoryRejected(f"{label} must be a safe ID")

    @staticmethod
    def _validate_limit(limit: int) -> None:
        if type(limit) is not int:
            raise TypeError("limit must be an integer")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be from 1 through 100")

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.utcoffset() != timedelta(0):
            raise WorkingMemoryRejected("working memory clock must return UTC")
        return value.astimezone(timezone.utc)

    def _require_open(self) -> None:
        if self._closed:
            raise WorkingMemoryError("working memory store is closed")
