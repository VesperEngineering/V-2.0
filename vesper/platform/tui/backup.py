"""Current-user encrypted V20 state backups with staged, reversible restore."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import stat
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from .views import NonEmptyStr, SafeId, Sha256Hex, StrictModel


_MAGIC = b"V20BK1\0"
_DESCRIPTION = "Vesper V20 encrypted backup"
_ENTROPY = b"Vesper.V20.TUI.backup.v1"
_MAX_ENTRIES = 10_000
_MAX_FILE_BYTES = 16 * 1024 * 1024
_MAX_TOTAL_BYTES = 128 * 1024 * 1024
_MAX_ARCHIVE_BYTES = 192 * 1024 * 1024
_ArchivePath = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32_767)
]
_ArchivePaths = Annotated[tuple[_ArchivePath, ...], Field(max_length=_MAX_ENTRIES)]
_Content = Annotated[str, StringConstraints(max_length=24 * 1024 * 1024)]
_FORBIDDEN_PARTS = frozenset(
    {
        ".git",
        ".pytest_cache",
        ".venv",
        "__pycache__",
        "cache",
        "caches",
        "credentials",
        "node_modules",
        "secrets",
        "target",
    }
)
_PROTECTED_PREFIXES = (
    ("vesper", "data", "massive"),
    ("vesper", "data", "model_research"),
)


class BackupError(RuntimeError):
    """Backup input, storage, or archive validation failed closed."""


class BackupRestoreError(BackupError):
    """Restore mutated state, then rolled it back or could not prove rollback."""


class BackupProtectionPort(Protocol):
    def protect(self, plaintext: bytes) -> bytes: ...

    def unprotect(self, ciphertext: bytes) -> bytes: ...


class RuntimeStopProbe(Protocol):
    def exactly_stopped(self) -> bool: ...


class CurrentUserBackupProtection:
    """Encrypt backup bytes for only the current Windows account."""

    def protect(self, plaintext: bytes) -> bytes:
        import win32crypt

        return bytes(
            win32crypt.CryptProtectData(
                plaintext,
                _DESCRIPTION,
                _ENTROPY,
                None,
                None,
                0,
            )
        )

    def unprotect(self, ciphertext: bytes) -> bytes:
        import win32crypt

        description, plaintext = win32crypt.CryptUnprotectData(
            ciphertext,
            _ENTROPY,
            None,
            None,
            0,
        )
        if description != _DESCRIPTION:
            raise ValueError("backup description is invalid")
        return bytes(plaintext)


class _ArchiveEntry(StrictModel):
    path: _ArchivePath
    size: Annotated[int, Field(ge=0, le=_MAX_FILE_BYTES)]
    sha256: Sha256Hex
    content_base64: _Content

    @field_validator("path", mode="before")
    @classmethod
    def validate_path(cls, value: object) -> object:
        if type(value) is str:
            _safe_relative_parts(value)
        return value


class _ArchivePayload(StrictModel):
    version: Literal[1]
    allowlist: _ArchivePaths
    entries: Annotated[tuple[_ArchiveEntry, ...], Field(max_length=_MAX_ENTRIES)]

    @model_validator(mode="after")
    def require_unique_sorted_paths(self) -> Self:
        paths = tuple(entry.path for entry in self.entries)
        if paths != tuple(sorted(paths, key=str.casefold)):
            raise ValueError("archive paths must be sorted")
        aliases = tuple(_windows_key(path) for path in paths)
        if len(aliases) != len(set(aliases)):
            raise ValueError("archive paths contain Windows aliases")
        if tuple(self.allowlist) != tuple(sorted(self.allowlist, key=str.casefold)):
            raise ValueError("archive allowlist must be sorted")
        return self


class BackupManifest(StrictModel):
    receipt_id: SafeId
    destination: _ArchivePath
    paths: _ArchivePaths
    plaintext_sha256: Sha256Hex
    ciphertext_sha256: Sha256Hex


class RestoreChange(StrictModel):
    path: _ArchivePath
    action: Literal["create", "replace", "delete", "unchanged"]
    before_sha256: Sha256Hex | None
    after_sha256: Sha256Hex | None


class RestorePreview(StrictModel):
    archive_sha256: Sha256Hex
    preview_hash: Sha256Hex
    changes: Annotated[tuple[RestoreChange, ...], Field(max_length=_MAX_ENTRIES * 2)]


class RestoreConfirmation(StrictModel):
    preview_hash: Sha256Hex
    safety_backup_receipt_id: SafeId
    first_confirmed: bool = False
    second_confirmed: bool = False


class RestoreReceipt(StrictModel):
    accepted: bool
    reason: NonEmptyStr
    preview_hash: Sha256Hex
    safety_backup_receipt_id: SafeId | None = None
    restored_paths: _ArchivePaths = ()
    deleted_paths: _ArchivePaths = ()

    @classmethod
    def rejected(cls, preview_hash: str, reason: str) -> RestoreReceipt:
        return cls(accepted=False, reason=reason, preview_hash=preview_hash)


@dataclass(frozen=True, slots=True)
class _ArchiveBundle:
    payload: _ArchivePayload
    plaintext: bytes
    plaintext_sha256: str
    receipt_id: str
    files: dict[str, bytes]


@dataclass(frozen=True, slots=True)
class _LoadedArchive:
    bundle: _ArchiveBundle
    ciphertext_sha256: str


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _path_redirects(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(callable(is_junction) and is_junction())


def _windows_key(path: str) -> tuple[str, ...]:
    return tuple(part.casefold() for part in PureWindowsPath(path).parts)


def _safe_relative_parts(value: str) -> tuple[str, ...]:
    if value != value.strip() or "\\" in value:
        raise ValueError("path is not canonical")
    windows = PureWindowsPath(value)
    posix = PurePosixPath(value)
    if (
        posix.is_absolute()
        or windows.is_absolute()
        or windows.drive
        or windows.root
        or windows.anchor
        or ".." in posix.parts
        or "." in posix.parts
        or value != posix.as_posix()
        or not posix.parts
    ):
        raise ValueError("path must be canonical and relative")
    for part in windows.parts:
        if (
            part != part.rstrip(" .")
            or "\x00" in part
            or ":" in part
            or PureWindowsPath(part).is_reserved()
        ):
            raise ValueError("path contains a Windows alias")
    return posix.parts


def _is_forbidden(parts: tuple[str, ...]) -> bool:
    folded = tuple(part.casefold() for part in parts)
    if any(
        part in _FORBIDDEN_PARTS
        or part.startswith(".env")
        or part.endswith((".key", ".pem", ".pfx", ".p12"))
        for part in folded
    ):
        return True
    return any(folded[: len(prefix)] == prefix for prefix in _PROTECTED_PREFIXES)


def _file_signature(status: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        int(status.st_dev),
        int(status.st_ino),
        int(status.st_nlink),
        int(status.st_size),
        int(status.st_mtime_ns),
    )


def _read_regular_file(path: Path) -> bytes:
    try:
        before = path.lstat()
        if (
            _path_redirects(path)
            or not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > _MAX_FILE_BYTES
        ):
            raise BackupError("unsafe-source-path")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if _file_signature(opened) != _file_signature(before):
                raise BackupError("unsafe-source-path")
            chunks: list[bytes] = []
            remaining = int(opened.st_size)
            while remaining:
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    raise BackupError("unsafe-source-path")
                chunks.append(chunk)
                remaining -= len(chunk)
            if _file_signature(os.fstat(descriptor)) != _file_signature(before):
                raise BackupError("unsafe-source-path")
            return b"".join(chunks)
        finally:
            os.close(descriptor)
    except BackupError:
        raise
    except OSError as error:
        raise BackupError("unsafe-source-path") from error


class BackupService:
    """Back up one exact allowlist and restore it only after safe prerequisites."""

    def __init__(
        self,
        root: Path,
        allowlist: tuple[str, ...],
        *,
        runtime: RuntimeStopProbe,
        safety_destination: Callable[[], Path],
        protection: BackupProtectionPort | None = None,
        atomic_replace: Callable[[Path, Path], None] = os.replace,
    ) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise TypeError("root must be an absolute Path")
        if type(allowlist) is not tuple or not allowlist:
            raise TypeError("allowlist must be a non-empty tuple")
        if not callable(getattr(runtime, "exactly_stopped", None)):
            raise TypeError("runtime must provide exactly_stopped")
        if not callable(safety_destination) or not callable(atomic_replace):
            raise TypeError("safety_destination and atomic_replace must be callable")
        selected = CurrentUserBackupProtection() if protection is None else protection
        if not callable(getattr(selected, "protect", None)) or not callable(
            getattr(selected, "unprotect", None)
        ):
            raise TypeError("protection must provide protect and unprotect")
        try:
            resolved = root.resolve(strict=True)
        except OSError as error:
            raise BackupError("unsafe-source-root") from error
        if resolved != root or _path_redirects(root) or not root.is_dir():
            raise BackupError("unsafe-source-root")
        checked_allowlist: list[str] = []
        aliases: set[tuple[str, ...]] = set()
        for value in allowlist:
            if type(value) is not str:
                raise TypeError("allowlist values must be strings")
            parts = _safe_relative_parts(value)
            key = tuple(part.casefold() for part in parts)
            if key in aliases:
                raise ValueError("allowlist contains Windows aliases")
            aliases.add(key)
            checked_allowlist.append(PurePosixPath(*parts).as_posix())
        self._root = root
        self._allowlist = tuple(sorted(checked_allowlist, key=str.casefold))
        self._runtime = runtime
        self._safety_destination = safety_destination
        self._protection = selected
        self._atomic_replace = atomic_replace

    def create(self, destination: Path) -> BackupManifest:
        bundle = self._build_current_bundle()
        ciphertext_hash = self._write_bundle(destination, bundle)
        return BackupManifest(
            receipt_id=bundle.receipt_id,
            destination=str(destination),
            paths=tuple(bundle.files),
            plaintext_sha256=bundle.plaintext_sha256,
            ciphertext_sha256=ciphertext_hash,
        )

    def preview_restore(self, archive: Path) -> RestorePreview:
        loaded = self._load_archive(archive)
        current = self._read_current_files()
        return self._preview(loaded, current)

    def restore(
        self,
        archive: Path,
        confirmation: RestoreConfirmation,
    ) -> RestoreReceipt:
        if type(confirmation) is not RestoreConfirmation:
            raise TypeError("confirmation must be RestoreConfirmation")
        confirmation = RestoreConfirmation.model_validate_json(
            confirmation.model_dump_json(), strict=True
        )
        try:
            stopped = self._runtime.exactly_stopped()
        except Exception:
            stopped = False
        if type(stopped) is not bool or not stopped:
            return RestoreReceipt.rejected(confirmation.preview_hash, "runtime-not-stopped")
        if not confirmation.first_confirmed or not confirmation.second_confirmed:
            return RestoreReceipt.rejected(
                confirmation.preview_hash,
                "double-confirmation-required",
            )

        loaded = self._load_archive(archive)
        before = self._read_current_files()
        preview = self._preview(loaded, before)
        if preview.preview_hash != confirmation.preview_hash:
            return RestoreReceipt.rejected(confirmation.preview_hash, "preview-mismatch")

        safety_bundle = self._bundle_from_files(before)
        if safety_bundle.receipt_id != confirmation.safety_backup_receipt_id:
            return RestoreReceipt.rejected(
                confirmation.preview_hash,
                "safety-backup-mismatch",
            )
        safety_path = self._safety_destination()
        if not isinstance(safety_path, Path) or not safety_path.is_absolute():
            raise BackupError("unsafe-backup-destination")
        self._write_bundle(safety_path, safety_bundle)
        verified_safety = self._load_archive(safety_path)
        if (
            verified_safety.bundle.receipt_id != safety_bundle.receipt_id
            or verified_safety.bundle.files != before
        ):
            raise BackupError("safety-backup-verification-failed")
        if self._read_current_files() != before:
            return RestoreReceipt.rejected(confirmation.preview_hash, "preview-mismatch")
        staging_parent = self._safe_staging_parent(safety_path)

        after = loaded.bundle.files
        try:
            restored, deleted = self._replace_exact_state(after, before, staging_parent)
        except Exception as error:
            try:
                self._replace_exact_state(
                    verified_safety.bundle.files,
                    self._read_current_files(),
                    staging_parent,
                )
            except Exception as rollback_error:
                raise BackupRestoreError("restore-failed-rollback-unverified") from rollback_error
            if self._read_current_files() != before:
                raise BackupRestoreError("restore-failed-rollback-unverified") from error
            raise BackupRestoreError("restore-failed-rolled-back") from error
        return RestoreReceipt(
            accepted=True,
            reason="restore-completed",
            preview_hash=preview.preview_hash,
            safety_backup_receipt_id=safety_bundle.receipt_id,
            restored_paths=restored,
            deleted_paths=deleted,
        )

    def _build_current_bundle(self) -> _ArchiveBundle:
        return self._bundle_from_files(self._read_current_files())

    def _bundle_from_files(self, files: dict[str, bytes]) -> _ArchiveBundle:
        entries = tuple(
            _ArchiveEntry(
                path=path,
                size=len(payload),
                sha256=_sha256(payload),
                content_base64=base64.b64encode(payload).decode("ascii"),
            )
            for path, payload in sorted(files.items(), key=lambda item: item[0].casefold())
        )
        payload = _ArchivePayload(version=1, allowlist=self._allowlist, entries=entries)
        plaintext = _canonical_bytes(payload.model_dump(mode="json"))
        if len(plaintext) > _MAX_ARCHIVE_BYTES:
            raise BackupError("archive-too-large")
        digest = _sha256(plaintext)
        return _ArchiveBundle(
            payload=payload,
            plaintext=plaintext,
            plaintext_sha256=digest,
            receipt_id=f"backup:{digest}",
            files=dict(files),
        )

    def _write_bundle(self, destination: Path, bundle: _ArchiveBundle) -> str:
        self._validate_destination(destination)
        try:
            protected = self._protection.protect(bundle.plaintext)
            if type(protected) is not bytes or not protected:
                raise TypeError("protection returned invalid bytes")
            framed = _MAGIC + protected
            if len(framed) > _MAX_ARCHIVE_BYTES:
                raise ValueError("encrypted archive exceeds limit")
            self._atomic_write(destination, framed)
            if destination.read_bytes() != framed:
                raise OSError("archive verification failed")
            return _sha256(framed)
        except BackupError:
            raise
        except Exception as error:
            raise BackupError("backup-write-failed") from error

    def _load_archive(self, archive: Path) -> _LoadedArchive:
        try:
            if not isinstance(archive, Path) or not archive.is_absolute():
                raise TypeError("archive must be an absolute Path")
            if _path_redirects(archive) or not archive.is_file():
                raise ValueError("archive is not a regular file")
            framed = archive.read_bytes()
            if len(framed) > _MAX_ARCHIVE_BYTES or not framed.startswith(_MAGIC):
                raise ValueError("archive framing is invalid")
            plaintext = self._protection.unprotect(framed[len(_MAGIC) :])
            if type(plaintext) is not bytes or len(plaintext) > _MAX_ARCHIVE_BYTES:
                raise ValueError("archive plaintext is invalid")
            payload = _ArchivePayload.model_validate_json(plaintext, strict=True)
            if tuple(payload.allowlist) != self._allowlist:
                raise ValueError("archive allowlist does not match")
            files: dict[str, bytes] = {}
            total = 0
            for entry in payload.entries:
                parts = _safe_relative_parts(entry.path)
                if _is_forbidden(parts) or not self._is_allowlisted(parts):
                    raise ValueError("archive contains forbidden path")
                content = base64.b64decode(entry.content_base64, validate=True)
                if len(content) != entry.size or _sha256(content) != entry.sha256:
                    raise ValueError("archive entry digest does not match")
                total += len(content)
                if total > _MAX_TOTAL_BYTES:
                    raise ValueError("archive expands past limit")
                files[entry.path] = content
            digest = _sha256(plaintext)
            bundle = _ArchiveBundle(
                payload=payload,
                plaintext=plaintext,
                plaintext_sha256=digest,
                receipt_id=f"backup:{digest}",
                files=files,
            )
            return _LoadedArchive(bundle=bundle, ciphertext_sha256=_sha256(framed))
        except Exception as error:
            raise BackupError("archive-unavailable") from error

    def _preview(
        self,
        loaded: _LoadedArchive,
        current: dict[str, bytes],
    ) -> RestorePreview:
        changes: list[RestoreChange] = []
        for path in sorted(set(current) | set(loaded.bundle.files), key=str.casefold):
            before = current.get(path)
            after = loaded.bundle.files.get(path)
            if before is None:
                action = "create"
            elif after is None:
                action = "delete"
            elif before == after:
                action = "unchanged"
            else:
                action = "replace"
            changes.append(
                RestoreChange(
                    path=path,
                    action=action,
                    before_sha256=None if before is None else _sha256(before),
                    after_sha256=None if after is None else _sha256(after),
                )
            )
        body = {
            "archive_plaintext_sha256": loaded.bundle.plaintext_sha256,
            "allowlist": self._allowlist,
            "changes": [change.model_dump(mode="json") for change in changes],
        }
        return RestorePreview(
            archive_sha256=loaded.ciphertext_sha256,
            preview_hash=_sha256(_canonical_bytes(body)),
            changes=tuple(changes),
        )

    def _read_current_files(self) -> dict[str, bytes]:
        self._require_root()
        files: dict[str, bytes] = {}
        total = 0
        for allowed in self._allowlist:
            parts = _safe_relative_parts(allowed)
            path = self._root.joinpath(*parts)
            if not os.path.lexists(path):
                continue
            for relative, payload in self._visit(path, parts):
                if relative in files:
                    raise BackupError("allowlist-overlap")
                files[relative] = payload
                total += len(payload)
                if len(files) > _MAX_ENTRIES or total > _MAX_TOTAL_BYTES:
                    raise BackupError("backup-source-too-large")
        return dict(sorted(files.items(), key=lambda item: item[0].casefold()))

    def _visit(self, path: Path, parts: tuple[str, ...]):
        if _is_forbidden(parts):
            return
        try:
            status = path.lstat()
        except OSError as error:
            raise BackupError("unsafe-source-path") from error
        if _path_redirects(path):
            raise BackupError("unsafe-source-path")
        if stat.S_ISREG(status.st_mode):
            yield PurePosixPath(*parts).as_posix(), _read_regular_file(path)
            return
        if not stat.S_ISDIR(status.st_mode):
            raise BackupError("unsafe-source-path")
        try:
            children = sorted(path.iterdir(), key=lambda item: item.name.casefold())
        except OSError as error:
            raise BackupError("unsafe-source-path") from error
        for child in children:
            yield from self._visit(child, (*parts, child.name))

    def _replace_exact_state(
        self,
        desired: dict[str, bytes],
        current: dict[str, bytes],
        staging_parent: Path,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        staging = Path(tempfile.mkdtemp(prefix=".v20-restore-", dir=staging_parent))
        staged: dict[str, Path] = {}
        created_directories: list[Path] = []
        try:
            for index, (relative, payload) in enumerate(
                sorted(
                    (
                        (relative, payload)
                        for relative, payload in desired.items()
                        if current.get(relative) != payload
                    ),
                    key=lambda item: item[0].casefold(),
                )
            ):
                staged_path = staging / f"{index:05}.stage"
                with staged_path.open("wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                if staged_path.read_bytes() != payload:
                    raise BackupError("restore-staging-failed")
                staged[relative] = staged_path

            if self._read_current_files() != current:
                raise BackupError("restore-source-changed")
            restored: list[str] = []
            for relative, staged_path in staged.items():
                target = self._target_path(relative)
                self._ensure_target_parent(target.parent, created_directories)
                self._atomic_replace(staged_path, target)
                restored.append(relative)
            deleted: list[str] = []
            for relative in sorted(set(current) - set(desired), key=str.casefold):
                target = self._target_path(relative)
                target.unlink()
                deleted.append(relative)
            if self._read_current_files() != desired:
                raise BackupError("restore-verification-failed")
            return tuple(restored), tuple(deleted)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            for directory in reversed(created_directories):
                try:
                    directory.rmdir()
                except OSError:
                    pass

    def _target_path(self, relative: str) -> Path:
        parts = _safe_relative_parts(relative)
        if _is_forbidden(parts):
            raise BackupError("unsafe-restore-path")
        target = self._root.joinpath(*parts)
        if not target.resolve(strict=False).is_relative_to(self._root):
            raise BackupError("unsafe-restore-path")
        return target

    def _ensure_target_parent(self, parent: Path, created: list[Path]) -> None:
        relative = parent.relative_to(self._root)
        current = self._root
        for part in relative.parts:
            current = current / part
            if os.path.lexists(current):
                if _path_redirects(current) or not current.is_dir():
                    raise BackupError("unsafe-restore-path")
            else:
                current.mkdir()
                created.append(current)

    def _is_allowlisted(self, parts: tuple[str, ...]) -> bool:
        folded = tuple(part.casefold() for part in parts)
        return any(
            folded[: len(allowed)] == allowed
            for allowed in (tuple(_windows_key(path)) for path in self._allowlist)
        )

    def _safe_staging_parent(self, destination: Path) -> Path:
        if not isinstance(destination, Path) or not destination.is_absolute():
            raise BackupError("unsafe-backup-destination")
        self._prepare_parent(destination.parent)
        if destination.parent.stat().st_dev != self._root.stat().st_dev:
            raise BackupError("restore-staging-volume-mismatch")
        return destination.parent

    def _validate_destination(self, destination: Path) -> None:
        if not isinstance(destination, Path) or not destination.is_absolute():
            raise TypeError("destination must be an absolute Path")
        if destination.resolve(strict=False).is_relative_to(self._root):
            raise BackupError("unsafe-backup-destination")
        self._prepare_parent(destination.parent)
        if os.path.lexists(destination) and (
            _path_redirects(destination) or not destination.is_file()
        ):
            raise BackupError("unsafe-backup-destination")

    @staticmethod
    def _prepare_parent(parent: Path) -> None:
        current = Path(parent.anchor)
        for part in parent.parts[1:]:
            current = current / part
            if os.path.lexists(current):
                if _path_redirects(current) or not current.is_dir():
                    raise BackupError("unsafe-backup-destination")
            else:
                current.mkdir()

    def _atomic_write(self, destination: Path, payload: bytes) -> None:
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{destination.name}.",
                suffix=".tmp",
                dir=destination.parent,
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            self._atomic_replace(temporary, destination)
            temporary = None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass

    def _require_root(self) -> None:
        try:
            current = self._root.resolve(strict=True)
        except OSError as error:
            raise BackupError("unsafe-source-root") from error
        if current != self._root or _path_redirects(self._root) or not current.is_dir():
            raise BackupError("unsafe-source-root")
