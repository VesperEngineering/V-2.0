"""Bounded read-only projection of controller-managed V20 working memory."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError

from vesper.platform.tui.ports import (
    MEMORY_AGENT_USAGE_UNAVAILABLE,
    MemoryFacts,
    SourceSample,
)
from vesper.platform.tui.views import (
    Freshness,
    MemoryRow,
    SafeId,
    StrictModel,
    TimelineRow,
    UtcDateTime,
)
from vesper.platform.tui.working_memory import CORE_WORD_LIMIT, word_count


_SOURCE = "managed V20 working memory"
_NOT_INITIALIZED = "Managed V20 working-memory ledger is not initialized."
_INVALID = "Managed V20 working-memory ledger is invalid or unsafe."
_PREPARED = "Managed V20 working memory has an unrecovered change."
_BOUNDS = "Managed V20 working memory exceeds bounded read limits."
_CLOCK = "Managed V20 working-memory projection clock is unavailable."
_CORE_LIMIT = "Managed V20 Core Memory exceeds the 2,000-word limit."
_DATABASE_NAME = ".working-memory.sqlite3"
_APPLICATION_ID = 0x5632304D
_SCHEMA_VERSION = 1
_MAX_ROWS = 10_000
_MAX_HISTORY_ROWS = 10_000
_MAX_DATABASE_BYTES = 64 * 1024 * 1024
_MAX_WAL_BYTES = 64 * 1024 * 1024
_MAX_SHM_BYTES = 8 * 1024 * 1024
_MAX_VALUE_BYTES = 512 * 1024
_MAX_TOTAL_BYTES = 4 * 1024 * 1024
_MAX_CONTENT_CHARS = 100_000
_BUSY_TIMEOUT_MS = 250
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
_CANDIDATE_FIELDS = {
    "memory_id",
    "content",
    "scope",
    "category",
    "supported",
    "evidence_ids",
    "reason",
    "score",
    "supersedes",
}
_RECEIPT_FIELDS = {
    "change_id",
    "trigger",
    "status",
    "reason",
    "evidence_ids",
    "before_hash",
    "after_hash",
    "restored_hash",
    "added_ids",
    "removed_ids",
    "created_at_utc",
}
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class _UnsafeMemoryState(RuntimeError):
    pass


class _MissingMemoryState(_UnsafeMemoryState):
    pass


class _PreparedMemoryChange(_UnsafeMemoryState):
    pass


class _BoundedMemoryRead(_UnsafeMemoryState):
    pass


class _CoreMemoryLimit(_UnsafeMemoryState):
    pass


class MemoryContentUnavailable(RuntimeError):
    """The exact managed-memory document cannot be read safely."""


class MemoryContentStale(MemoryContentUnavailable):
    """The reviewed memory timestamp no longer matches controller truth."""


@dataclass(slots=True)
class _ReadBudget:
    total: int = 0

    def add(self, *values: object) -> None:
        for value in values:
            if not isinstance(value, (str, bytes)):
                raise _UnsafeMemoryState
            body = value.encode("utf-8") if isinstance(value, str) else value
            if len(body) > _MAX_VALUE_BYTES:
                raise _BoundedMemoryRead
            self.total += len(body)
            if self.total > _MAX_TOTAL_BYTES:
                raise _BoundedMemoryRead


@dataclass(frozen=True, slots=True)
class _MemoryDocument:
    row: MemoryRow
    content: str
    searchable: str


class MemoryContentDocument(StrictModel):
    memory_id: SafeId
    updated_at_utc: UtcDateTime
    content: str

    @classmethod
    def from_document(cls, document: _MemoryDocument) -> MemoryContentDocument:
        if not 1 <= len(document.content) <= _MAX_CONTENT_CHARS:
            raise MemoryContentUnavailable("Managed memory content is unavailable.")
        return cls(
            memory_id=document.row.memory_id,
            updated_at_utc=document.row.updated_at_utc,
            content=document.content,
        )


class ManagedMemoryProjection:
    """Read the existing managed-memory ledger without setup, repair, or writes."""

    def __init__(
        self,
        vault: Path,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(vault, Path):
            raise TypeError("vault must be a Path")
        self._vault = Path(os.path.abspath(vault))
        self._database = self._vault / _DATABASE_NAME
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def source(self) -> str:
        return _SOURCE

    def read(self) -> SourceSample[MemoryFacts]:
        try:
            observed_at = self._utc_now()
        except Exception:
            return _unavailable(_CLOCK)
        try:
            database = self._validated_database()
            with _readonly_database(database) as connection:
                _require_schema(connection)
                if (
                    connection.execute(
                        "SELECT 1 FROM memory_changes WHERE status = 'prepared' LIMIT 1"
                    ).fetchone()
                    is not None
                ):
                    raise _PreparedMemoryChange
                budget = _ReadBudget()
                rows = tuple(document.row for document in _memory_documents(connection, budget))
                history = _memory_history(connection, budget)
            return SourceSample[MemoryFacts](
                value=MemoryFacts(
                    rows=rows,
                    history=history,
                    agent_usage_error=MEMORY_AGENT_USAGE_UNAVAILABLE,
                ),
                freshness=Freshness.FRESH,
                observed_at_utc=observed_at,
                source=_SOURCE,
                error=None,
            )
        except _MissingMemoryState:
            return _unavailable(_NOT_INITIALIZED)
        except _PreparedMemoryChange:
            return _unavailable(_PREPARED)
        except _BoundedMemoryRead:
            return _unavailable(_BOUNDS)
        except _CoreMemoryLimit:
            return _unavailable(_CORE_LIMIT)
        except Exception:
            return _unavailable(_INVALID)

    def search_archive(self, query: str, limit: int = 100) -> tuple[MemoryRow, ...]:
        """Search complete archived content through the same bounded read-only path."""

        if type(query) is not str:
            raise TypeError("query must be a string")
        if not query.strip():
            raise ValueError("query cannot be empty")
        if len(query) > 256:
            raise ValueError("query cannot exceed 256 characters")
        if type(limit) is not int:
            raise TypeError("limit must be an integer")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        tokens = _search_tokens(query)
        if not tokens:
            return ()
        try:
            database = self._validated_database()
            with _readonly_database(database) as connection:
                _require_schema(connection)
                if (
                    connection.execute(
                        "SELECT 1 FROM memory_changes WHERE status = 'prepared' LIMIT 1"
                    ).fetchone()
                    is not None
                ):
                    raise _PreparedMemoryChange
                documents = _memory_documents(connection, _ReadBudget())
            return tuple(
                document.row
                for document in documents
                if document.row.status == "archived"
                and _matches_tokens(document.searchable, tokens)
            )[:limit]
        except _MissingMemoryState:
            return ()
        except Exception as exc:
            raise RuntimeError("Managed memory archive search is unavailable.") from exc

    def read_content(
        self,
        memory_id: SafeId,
        reviewed_updated_at_utc: UtcDateTime,
    ) -> MemoryContentDocument:
        """Read one exact current document through the validated read-only path."""

        try:
            if type(memory_id) is not str or _SAFE_ID.fullmatch(memory_id) is None:
                raise MemoryContentUnavailable("Managed memory content is unavailable.")
            if (
                not isinstance(reviewed_updated_at_utc, datetime)
                or reviewed_updated_at_utc.tzinfo is None
                or reviewed_updated_at_utc.utcoffset() != timedelta(0)
            ):
                raise MemoryContentUnavailable("Managed memory content is unavailable.")
            reviewed = reviewed_updated_at_utc.astimezone(timezone.utc)
            database = self._validated_database()
            with _readonly_database(database) as connection:
                _require_schema(connection)
                if (
                    connection.execute(
                        "SELECT 1 FROM memory_changes WHERE status = 'prepared' LIMIT 1"
                    ).fetchone()
                    is not None
                ):
                    raise _PreparedMemoryChange
                documents = _memory_documents(connection, _ReadBudget())
            document = next(
                (item for item in documents if item.row.memory_id == memory_id),
                None,
            )
            if document is None:
                raise MemoryContentUnavailable("Memory content is unavailable.")
            if document.row.updated_at_utc != reviewed:
                raise MemoryContentStale("Memory changed. Search again.")
            return MemoryContentDocument.from_document(document)
        except MemoryContentUnavailable:
            raise
        except Exception as exc:
            raise MemoryContentUnavailable("Managed memory content is unavailable.") from exc

    def _utc_now(self) -> datetime:
        value = self._clock()
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() != timedelta(0)
        ):
            raise _UnsafeMemoryState
        return value.astimezone(timezone.utc)

    def _validated_database(self) -> Path:
        try:
            vault_status = self._vault.lstat()
            database_status = self._database.lstat()
        except FileNotFoundError as exc:
            raise _MissingMemoryState from exc
        if _is_reparse(vault_status) or not stat.S_ISDIR(vault_status.st_mode):
            raise _UnsafeMemoryState
        if (
            _is_reparse(database_status)
            or not stat.S_ISREG(database_status.st_mode)
            or database_status.st_nlink != 1
        ):
            raise _UnsafeMemoryState
        if database_status.st_size > _MAX_DATABASE_BYTES:
            raise _BoundedMemoryRead
        try:
            vault = self._vault.resolve(strict=True)
            database = self._database.resolve(strict=True)
            if database.parent != vault or database.name != _DATABASE_NAME:
                raise _UnsafeMemoryState
        except _UnsafeMemoryState:
            raise
        except (OSError, RuntimeError, ValueError) as exc:
            raise _UnsafeMemoryState from exc
        return database


def _unavailable(reason: str) -> SourceSample[MemoryFacts]:
    return SourceSample[MemoryFacts](
        value=None,
        freshness=Freshness.UNAVAILABLE,
        observed_at_utc=None,
        source=_SOURCE,
        error=reason,
    )


def _is_reparse(metadata: os.stat_result) -> bool:
    marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & marker
    )


@contextmanager
def _readonly_database(path: Path) -> Iterator[sqlite3.Connection]:
    handle = None
    connection = None
    auxiliary_presence: dict[Path, bool] = {}
    try:
        before = path.stat()
        handle = path.open("rb")
        opened = os.fstat(handle.fileno())
        if _identity(opened) != _identity(before):
            raise _UnsafeMemoryState
        header = handle.read(20)
        if _identity(os.fstat(handle.fileno())) != _identity(before):
            raise _UnsafeMemoryState
        if len(header) != 20 or header[:16] != b"SQLite format 3\x00":
            raise _UnsafeMemoryState
        if header[18:20] not in {b"\x01\x01", b"\x02\x02"}:
            raise _UnsafeMemoryState
        wal = Path(f"{path}-wal")
        shared_memory = Path(f"{path}-shm")
        rollback_journal = Path(f"{path}-journal")
        wal_metadata = _validated_auxiliary_file(wal)
        shared_memory_metadata = _validated_auxiliary_file(shared_memory)
        journal_metadata = _validated_auxiliary_file(rollback_journal)
        if journal_metadata is not None or (wal_metadata is None) != (
            shared_memory_metadata is None
        ):
            raise _UnsafeMemoryState
        if wal_metadata is not None and wal_metadata.st_size > _MAX_WAL_BYTES:
            raise _BoundedMemoryRead
        if shared_memory_metadata is not None and shared_memory_metadata.st_size > _MAX_SHM_BYTES:
            raise _BoundedMemoryRead
        auxiliary_presence = {
            wal: wal_metadata is not None,
            shared_memory: shared_memory_metadata is not None,
            rollback_journal: journal_metadata is not None,
        }
        uri = (
            f"{path.as_uri()}?mode=ro"
            if wal_metadata is not None
            else f"{path.as_uri()}?mode=ro&immutable=1"
        )
        connection = sqlite3.connect(
            uri,
            uri=True,
            check_same_thread=False,
            isolation_level=None,
            timeout=_BUSY_TIMEOUT_MS / 1000,
        )
        connection.execute("PRAGMA query_only = ON")
        connection.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.execute("PRAGMA temp_store = MEMORY")
        if connection.execute("PRAGMA query_only").fetchone() != (1,):
            raise _UnsafeMemoryState
        connection.execute("BEGIN")
        yield connection
    except (_UnsafeMemoryState, _BoundedMemoryRead):
        raise
    except (OSError, sqlite3.Error) as exc:
        raise _UnsafeMemoryState from exc
    finally:
        if connection is not None:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            connection.close()
        if handle is not None:
            handle.close()
        try:
            if handle is not None and _identity(path.stat()) != _identity(before):
                raise _UnsafeMemoryState
            if any(
                not existed and auxiliary.exists()
                for auxiliary, existed in auxiliary_presence.items()
            ):
                raise _UnsafeMemoryState
        except OSError as exc:
            raise _UnsafeMemoryState from exc


def _validated_auxiliary_file(path: Path) -> os.stat_result | None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    if _is_reparse(metadata) or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise _UnsafeMemoryState
    return metadata


def _identity(metadata: os.stat_result) -> tuple[int, int, int]:
    return (
        int(metadata.st_dev),
        int(metadata.st_ino),
        int(metadata.st_nlink),
    )


def _require_schema(connection: sqlite3.Connection) -> None:
    if connection.execute("PRAGMA application_id").fetchone() != (_APPLICATION_ID,):
        raise _UnsafeMemoryState
    if connection.execute("PRAGMA user_version").fetchone() != (_SCHEMA_VERSION,):
        raise _UnsafeMemoryState
    objects = {
        str(row[0]): str(row[1])
        for row in connection.execute(
            "SELECT name, type FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'"
        )
    }
    if objects != {name: "table" for name in _EXPECTED_COLUMNS}:
        raise _UnsafeMemoryState
    for table, expected in _EXPECTED_COLUMNS.items():
        actual = tuple(str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})"))
        if actual != expected:
            raise _UnsafeMemoryState


def _memory_documents(
    connection: sqlite3.Connection,
    budget: _ReadBudget,
) -> tuple[_MemoryDocument, ...]:
    item_count = connection.execute("SELECT COUNT(*) FROM memory_items").fetchone()
    if (
        item_count is None
        or type(item_count[0]) is not int
        or item_count[0] < 0
        or item_count[0] > _MAX_ROWS
    ):
        raise _BoundedMemoryRead
    cursor = connection.execute(
        """
        SELECT i.memory_id, i.status, i.updated_at_utc,
               p.candidate_json, p.candidate_sha256
        FROM memory_items AS i
        JOIN memory_proposals AS p USING(memory_id)
        ORDER BY CASE i.status WHEN 'core' THEN 0 ELSE 1 END, i.memory_id
        LIMIT ?
        """,
        (_MAX_ROWS + 1,),
    )
    documents: list[_MemoryDocument] = []
    core_words = 0
    for raw in cursor:
        if len(documents) == _MAX_ROWS or len(raw) != 5:
            raise _BoundedMemoryRead
        memory_id, status, updated_at, candidate_json, candidate_sha256 = raw
        budget.add(memory_id, status, updated_at, candidate_json, candidate_sha256)
        if not all(isinstance(value, str) for value in raw):
            raise _UnsafeMemoryState
        if hashlib.sha256(candidate_json.encode("utf-8")).hexdigest() != candidate_sha256:
            raise _UnsafeMemoryState
        try:
            candidate = json.loads(candidate_json)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise _UnsafeMemoryState from exc
        if not isinstance(candidate, dict) or set(candidate) != _CANDIDATE_FIELDS:
            raise _UnsafeMemoryState
        content = candidate.get("content")
        category = candidate.get("category")
        reason = candidate.get("reason")
        evidence_ids = candidate.get("evidence_ids")
        if (
            candidate.get("memory_id") != memory_id
            or candidate.get("scope") != "v20"
            or candidate.get("supported") is not True
            or not isinstance(content, str)
            or not content.strip()
            or len(content) > _MAX_CONTENT_CHARS
            or not isinstance(category, str)
            or not category.strip()
            or not isinstance(reason, str)
            or not reason.strip()
            or not isinstance(evidence_ids, list)
        ):
            raise _UnsafeMemoryState
        if status == "core":
            core_words += word_count(content)
            if core_words > CORE_WORD_LIMIT:
                raise _CoreMemoryLimit
        try:
            row = MemoryRow(
                memory_id=memory_id,
                status=status,
                summary=_summary(content),
                evidence_ids=tuple(evidence_ids),
                updated_at_utc=updated_at,
                used_by_agents=(),
                change_reason=reason,
            )
            documents.append(
                _MemoryDocument(
                    row=row,
                    content=content,
                    searchable=" ".join(
                        (
                            memory_id,
                            status,
                            content,
                            category,
                            reason,
                            *row.evidence_ids,
                        )
                    ),
                )
            )
        except (TypeError, ValidationError, ValueError) as exc:
            raise _UnsafeMemoryState from exc
    if len(documents) != item_count[0]:
        raise _UnsafeMemoryState
    return tuple(documents)


def _search_tokens(value: str) -> tuple[str, ...]:
    tokens: list[str] = []
    current: list[str] = []
    for character in value.casefold():
        if character.isalnum() or character == "_":
            current.append(character)
        elif current:
            tokens.append("".join(current))
            current.clear()
    if current:
        tokens.append("".join(current))
    return tuple(tokens)


def _matches_tokens(value: str, query_tokens: tuple[str, ...]) -> bool:
    document_tokens = _search_tokens(value)
    return all(
        any(document_token.startswith(query_token) for document_token in document_tokens)
        for query_token in query_tokens
    )


def _memory_history(
    connection: sqlite3.Connection,
    budget: _ReadBudget,
) -> tuple[TimelineRow, ...]:
    count = connection.execute(
        "SELECT COUNT(*) FROM memory_changes WHERE status = 'committed'"
    ).fetchone()
    if count is None or type(count[0]) is not int or count[0] < 0 or count[0] > _MAX_HISTORY_ROWS:
        raise _BoundedMemoryRead
    cursor = connection.execute(
        """
        SELECT change_id, trigger, receipt_json, created_at_utc
        FROM memory_changes
        WHERE status = 'committed'
        ORDER BY rowid DESC
        LIMIT ?
        """,
        (_MAX_HISTORY_ROWS + 1,),
    )
    rows: list[TimelineRow] = []
    for raw in cursor:
        if len(rows) == _MAX_HISTORY_ROWS or len(raw) != 4:
            raise _BoundedMemoryRead
        change_id, trigger, receipt_json, created_at = raw
        budget.add(change_id, trigger, receipt_json, created_at)
        if not all(isinstance(value, str) for value in raw):
            raise _UnsafeMemoryState
        receipt = _change_receipt(
            change_id=change_id,
            trigger=trigger,
            created_at=created_at,
            receipt_json=receipt_json,
        )
        added_ids = receipt["added_ids"]
        removed_ids = receipt["removed_ids"]
        evidence_ids = receipt["evidence_ids"]
        try:
            rows.append(
                TimelineRow(
                    event_id=change_id,
                    occurred_at_utc=created_at,
                    impact=bool(added_ids or removed_ids),
                    severity="resolved",
                    summary=_change_summary(
                        trigger,
                        len(added_ids),
                        len(removed_ids),
                        str(receipt["reason"]),
                    ),
                    agent_id=None,
                    symbol=None,
                    model_id=None,
                    approval_id=None,
                    order_id=None,
                    evidence_ids=tuple(evidence_ids),
                    work_id=None,
                )
            )
        except (TypeError, ValidationError, ValueError) as exc:
            raise _UnsafeMemoryState from exc
    if len(rows) != count[0]:
        raise _UnsafeMemoryState
    return tuple(rows)


def _change_receipt(
    *,
    change_id: str,
    trigger: str,
    created_at: str,
    receipt_json: str,
) -> dict[str, object]:
    try:
        receipt = json.loads(receipt_json)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise _UnsafeMemoryState from exc
    if not isinstance(receipt, dict) or set(receipt) != _RECEIPT_FIELDS:
        raise _UnsafeMemoryState
    if (
        receipt.get("change_id") != change_id
        or receipt.get("trigger") != trigger
        or receipt.get("status") != "committed"
        or receipt.get("created_at_utc") != created_at
        or trigger not in {"validated-work", "daily", "rollback"}
    ):
        raise _UnsafeMemoryState
    reason = receipt.get("reason")
    before_hash = receipt.get("before_hash")
    after_hash = receipt.get("after_hash")
    restored_hash = receipt.get("restored_hash")
    if (
        not isinstance(reason, str)
        or not reason.strip()
        or len(reason) > 512
        or not isinstance(before_hash, str)
        or _SHA256.fullmatch(before_hash) is None
        or not isinstance(after_hash, str)
        or _SHA256.fullmatch(after_hash) is None
        or (
            restored_hash is not None
            and (not isinstance(restored_hash, str) or _SHA256.fullmatch(restored_hash) is None)
        )
    ):
        raise _UnsafeMemoryState
    evidence_ids = _safe_id_list(receipt.get("evidence_ids"))
    added_ids = _safe_id_list(receipt.get("added_ids"))
    removed_ids = _safe_id_list(receipt.get("removed_ids"))
    if set(added_ids) & set(removed_ids):
        raise _UnsafeMemoryState
    receipt["evidence_ids"] = evidence_ids
    receipt["added_ids"] = added_ids
    receipt["removed_ids"] = removed_ids
    return receipt


def _safe_id_list(value: object) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or _SAFE_ID.fullmatch(item) is None for item in value)
        or value != sorted(set(value))
    ):
        raise _UnsafeMemoryState
    return tuple(value)


def _change_summary(trigger: str, added: int, removed: int, reason: str) -> str:
    label = {
        "validated-work": "Validated-work memory curation",
        "daily": "Daily memory curation",
        "rollback": "Memory rollback",
    }[trigger]
    prefix = f"{label} committed: {added} added to Core; {removed} moved to archive. Reason: "
    normalized_reason = " ".join(reason.split())
    available = 512 - len(prefix)
    if len(normalized_reason) > available:
        normalized_reason = f"{normalized_reason[: available - 3]}..."
    return f"{prefix}{normalized_reason}"


def _summary(content: str) -> str:
    value = " ".join(content.split())
    if not value:
        raise _UnsafeMemoryState
    return value if len(value) <= 512 else f"{value[:509]}..."
