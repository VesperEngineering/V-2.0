"""Verified compression of closed raw logs without deleting durable history."""

from __future__ import annotations

import gzip
import hashlib
import io
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath

from pydantic import TypeAdapter, field_validator

from .views import NonEmptyStr, SafeId, StrictModel, UtcDateTime


_RETENTION_AGE = timedelta(days=30)
_UTC = TypeAdapter(UtcDateTime)


class RetentionError(RuntimeError):
    """A raw log could not be compressed without risking data loss."""


class RawLogRecord(StrictModel):
    """Controller-owned identity and closure time for one raw log."""

    log_id: SafeId
    relative_path: NonEmptyStr
    closed_at_utc: UtcDateTime

    @field_validator("relative_path")
    @classmethod
    def require_safe_log_path(cls, value: str) -> str:
        _validate_relative_log_path(value)
        return value


@dataclass(frozen=True)
class CompressedLogReceipt:
    log_id: str
    original_path: Path
    compressed_path: Path
    original_sha256: str
    compressed_sha256: str


@dataclass(frozen=True)
class HistoryRetentionReceipt:
    entries: tuple[CompressedLogReceipt, ...]
    skipped_count: int

    @property
    def compressed_path(self) -> Path:
        if len(self.entries) != 1:
            raise RetentionError("receipt-does-not-contain-one-compressed-log")
        return self.entries[0].compressed_path

    @property
    def compressed_sha256(self) -> str:
        if len(self.entries) != 1:
            return ""
        return self.entries[0].compressed_sha256


def deterministic_gzip(raw_bytes: bytes) -> bytes:
    """Return gzip bytes with no filename or wall-clock metadata."""

    if type(raw_bytes) is not bytes:
        raise TypeError("raw log content must be bytes")
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as stream:
        stream.write(raw_bytes)
    return output.getvalue()


class HistoryRetentionService:
    """Compress only manifest-listed logs at the approved 30-day boundary."""

    def __init__(
        self,
        raw_root: Path,
        compressed_root: Path,
        records: tuple[RawLogRecord, ...],
        *,
        history_reader: Callable[[], tuple[object, ...]] | None = None,
    ) -> None:
        if not isinstance(raw_root, Path) or not isinstance(compressed_root, Path):
            raise TypeError("retention roots must be Path values")
        if not raw_root.is_absolute() or not compressed_root.is_absolute():
            raise ValueError("retention roots must be absolute")
        if type(records) is not tuple or any(type(item) is not RawLogRecord for item in records):
            raise TypeError("records must be a tuple of RawLogRecord values")
        if history_reader is not None and not callable(history_reader):
            raise TypeError("history_reader must be callable")
        self._raw_root = raw_root
        self._compressed_root = compressed_root
        self._records = tuple(
            RawLogRecord.model_validate(record.model_dump(), strict=True) for record in records
        )
        paths = [record.relative_path for record in self._records]
        ids = [record.log_id for record in self._records]
        if len(set(paths)) != len(paths):
            raise ValueError("duplicate raw log path")
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate raw log ID")
        raw_resolved = raw_root.resolve(strict=False)
        compressed_resolved = compressed_root.resolve(strict=False)
        if _contains(raw_resolved, compressed_resolved) or _contains(
            compressed_resolved, raw_resolved
        ):
            raise ValueError("raw and compressed roots must not overlap")
        if raw_root.is_symlink() or compressed_root.is_symlink():
            raise ValueError("retention roots must not be symlinks")
        self._history_reader = history_reader or (lambda: ())

    def apply(self, now_utc: datetime) -> HistoryRetentionReceipt:
        now = _UTC.validate_python(now_utc, strict=True)
        eligible = tuple(
            sorted(
                (
                    record
                    for record in self._records
                    if now - record.closed_at_utc >= _RETENTION_AGE
                ),
                key=lambda record: record.relative_path,
            )
        )
        entries = tuple(self._compress_one(record) for record in eligible)
        return HistoryRetentionReceipt(
            entries=entries,
            skipped_count=len(self._records) - len(eligible),
        )

    def permanent_history_rows(self) -> tuple[object, ...]:
        rows = self._history_reader()
        if type(rows) is not tuple:
            raise TypeError("permanent history reader must return a tuple")
        return rows

    def _compress_one(self, record: RawLogRecord) -> CompressedLogReceipt:
        raw_root = self._raw_root.resolve(strict=True)
        source = self._safe_source(raw_root, record.relative_path)
        try:
            first_stat = source.stat()
            raw_bytes = source.read_bytes()
        except OSError as error:
            raise RetentionError("raw-log-read-failed") from error
        original_sha256 = _sha256(raw_bytes)
        compressed_bytes = deterministic_gzip(raw_bytes)
        destination = self._safe_destination(record.relative_path)
        self._prepare_safe_destination_parent(destination)
        if destination.exists() or destination.is_symlink():
            try:
                existing = destination.read_bytes()
            except OSError as error:
                raise RetentionError("compressed-copy-conflict") from error
            if destination.is_symlink() or existing != compressed_bytes:
                raise RetentionError("compressed-copy-conflict")
        else:
            self._atomic_write(destination, compressed_bytes)
        try:
            verified_compressed = destination.read_bytes()
            if gzip.decompress(verified_compressed) != raw_bytes:
                raise RetentionError("decompression-mismatch")
            second_stat = source.stat()
            if (
                first_stat.st_dev != second_stat.st_dev
                or first_stat.st_ino != second_stat.st_ino
                or first_stat.st_size != second_stat.st_size
                or first_stat.st_mtime_ns != second_stat.st_mtime_ns
                or _sha256(source.read_bytes()) != original_sha256
            ):
                raise RetentionError("raw-log-changed")
            source.unlink()
        except RetentionError:
            raise
        except (OSError, EOFError, gzip.BadGzipFile) as error:
            raise RetentionError("compression-verification-failed") from error
        return CompressedLogReceipt(
            log_id=record.log_id,
            original_path=source,
            compressed_path=destination,
            original_sha256=original_sha256,
            compressed_sha256=_sha256(verified_compressed),
        )

    def _safe_source(self, raw_root: Path, relative_path: str) -> Path:
        candidate = self._raw_root.joinpath(*PurePosixPath(relative_path).parts)
        if not os.path.lexists(candidate):
            raise RetentionError("raw-log-missing")
        if candidate.is_symlink() or not candidate.is_file():
            raise RetentionError("unsafe-raw-log")
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(raw_root)
        except (OSError, ValueError) as error:
            raise RetentionError("unsafe-raw-log") from error
        current = candidate.parent
        while current != self._raw_root:
            if current.is_symlink():
                raise RetentionError("unsafe-raw-log")
            current = current.parent
        return resolved

    def _safe_destination(self, relative_path: str) -> Path:
        relative = PurePosixPath(f"{relative_path}.gz")
        return self._compressed_root.joinpath(*relative.parts)

    def _prepare_safe_destination_parent(self, destination: Path) -> None:
        self._create_directory_chain(self._compressed_root)
        relative_parent = destination.parent.relative_to(self._compressed_root)
        current = self._compressed_root
        for part in relative_parent.parts:
            current = current / part
            if os.path.lexists(current):
                if current.is_symlink() or not current.is_dir():
                    raise RetentionError("unsafe-compressed-path")
            else:
                current.mkdir()
        root = self._compressed_root.resolve(strict=True)
        try:
            destination.parent.resolve(strict=True).relative_to(root)
        except (OSError, ValueError) as error:
            raise RetentionError("unsafe-compressed-path") from error
        current = destination.parent
        while current != self._compressed_root:
            if current.is_symlink():
                raise RetentionError("unsafe-compressed-path")
            current = current.parent

    @staticmethod
    def _create_directory_chain(path: Path) -> None:
        current = Path(path.anchor)
        for part in path.parts[1:]:
            current = current / part
            if os.path.lexists(current):
                if current.is_symlink() or not current.is_dir():
                    raise RetentionError("unsafe-compressed-path")
            else:
                current.mkdir()

    @staticmethod
    def _atomic_write(destination: Path, payload: bytes) -> None:
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{destination.name}.",
                suffix=".tmp",
                dir=destination.parent,
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, destination)
            temp_path = None
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass


def _validate_relative_log_path(value: str) -> None:
    if type(value) is not str or not value or "\\" in value or ":" in value:
        raise ValueError("raw log path is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("raw log path is invalid")
    if path.suffix != ".log":
        raise ValueError("raw log path must end in .log")


def _contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
