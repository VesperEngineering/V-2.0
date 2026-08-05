"""Plan-first retention for inactive V20 model candidate binaries."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal, Protocol, Self

from pydantic import ValidationError, field_validator, model_validator

if os.name == "nt":  # pragma: no cover - imported and exercised on Windows
    import ctypes
    import msvcrt
    from ctypes import wintypes

from vesper.platform.ops.activation import (
    ActivationAuthorityError,
    ActivationCapability,
    OperationsActivationStore,
)
from vesper.platform.tui.views import (
    NonEmptyStr,
    SafeId,
    Sha256Hex,
    StrictModel,
    UtcDateTime,
)


CandidateStatus = Literal["failed", "rejected", "passed", "unselected"]
CandidateFileKind = Literal["binary", "metrics", "evidence", "lineage", "history"]
_PERMANENT_KINDS = frozenset({"metrics", "evidence", "lineage", "history"})
_RETENTION_DAYS = {"failed": 30, "rejected": 30, "passed": 90, "unselected": 90}
_MANIFEST_DIRECTORY = ".retention"
_PREPARED_SUFFIX = ".prepared.json"


class CandidateRetentionError(RuntimeError):
    """A candidate manifest or filesystem boundary is unsafe."""


class CandidateRetentionAuthorityError(RuntimeError):
    """Candidate deletion lacks an exact root-and-plan receipt."""


class CandidateRetentionRollbackError(CandidateRetentionError):
    """A pre-commit staging failure could not be fully reversed."""


class AuthorityReceiptStore(Protocol):
    def require_candidate_deletion(
        self,
        receipt_id: str,
        approved_root: Path,
        plan_hash: str,
    ) -> object: ...


class CandidateArtifactFile(StrictModel):
    relative_path: NonEmptyStr
    kind: CandidateFileKind
    sha256: Sha256Hex

    @field_validator("relative_path", mode="before")
    @classmethod
    def require_safe_canonical_relative_path(cls, value: object) -> object:
        if type(value) is not str:
            return value
        windows = PureWindowsPath(value)
        posix = PurePosixPath(value)
        if value != value.strip() or any(part != part.rstrip(" .") for part in windows.parts):
            raise ValueError("candidate file path contains a Windows alias")
        if (
            "\\" in value
            or windows.is_absolute()
            or posix.is_absolute()
            or bool(windows.drive)
            or bool(windows.root)
            or bool(windows.anchor)
            or ".." in windows.parts
            or ".." in posix.parts
            or value != posix.as_posix()
        ):
            raise ValueError("candidate file path must be canonical and relative")
        if any("\x00" in part or ":" in part for part in windows.parts):
            raise ValueError("candidate file path contains an unsafe marker")
        if any(PureWindowsPath(part).is_reserved() for part in windows.parts):
            raise ValueError("candidate file path contains a reserved Windows name")
        if not posix.parts or posix.parts[0].casefold() == _MANIFEST_DIRECTORY:
            raise ValueError("candidate file path uses a controller-reserved location")
        return value


class CandidateArtifact(StrictModel):
    candidate_id: SafeId
    status: CandidateStatus
    created_at_utc: UtcDateTime
    files: tuple[CandidateArtifactFile, ...]

    @model_validator(mode="after")
    def require_unique_files(self) -> Self:
        if not self.files:
            raise ValueError("candidate artifact requires at least one file")
        paths = tuple(item.relative_path for item in self.files)
        if len(paths) != len(set(paths)):
            raise ValueError("candidate artifact file paths must be unique")
        return self


class CandidateRetentionManifest(StrictModel):
    candidates: tuple[CandidateArtifact, ...]
    active_candidate_id: SafeId | None = None
    rollback_candidate_id: SafeId | None = None

    @model_validator(mode="after")
    def bind_candidate_identities_and_files(self) -> Self:
        candidate_ids = tuple(item.candidate_id for item in self.candidates)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate IDs must be unique")
        known = set(candidate_ids)
        if self.active_candidate_id is not None and self.active_candidate_id not in known:
            raise ValueError("active candidate ID must exist in the manifest")
        if self.rollback_candidate_id is not None and self.rollback_candidate_id not in known:
            raise ValueError("rollback candidate ID must exist in the manifest")
        if (
            self.active_candidate_id is not None
            and self.active_candidate_id == self.rollback_candidate_id
        ):
            raise ValueError("active and rollback candidate IDs must be distinct")
        paths = tuple(
            file.relative_path for candidate in self.candidates for file in candidate.files
        )
        windows_keys = tuple(
            tuple(part.casefold() for part in PureWindowsPath(path).parts) for path in paths
        )
        if len(windows_keys) != len(set(windows_keys)):
            raise ValueError("manifest file paths contain Windows path aliases")
        return self


class CandidateDeletion(StrictModel):
    candidate_id: SafeId
    status: CandidateStatus
    relative_path: NonEmptyStr
    sha256: Sha256Hex
    expires_at_utc: UtcDateTime


class CandidateFileBinding(StrictModel):
    candidate_id: SafeId
    relative_path: NonEmptyStr
    kind: CandidateFileKind
    sha256: Sha256Hex
    identity_sha256: Sha256Hex


class CandidateRetentionPlan(StrictModel):
    plan_hash: Sha256Hex
    manifest_hash: Sha256Hex
    approved_root: NonEmptyStr
    planned_at_utc: UtcDateTime
    active_candidate_id: SafeId | None
    rollback_candidate_id: SafeId | None
    candidate_training_paused: bool
    file_bindings: tuple[CandidateFileBinding, ...]
    deletions: tuple[CandidateDeletion, ...]


class CandidateRetentionPreparedJournal(StrictModel):
    state: Literal["PREPARED"] = "PREPARED"
    plan: CandidateRetentionPlan


class CandidateRetentionReceipt(StrictModel):
    accepted: bool
    plan_hash: Sha256Hex
    reason: NonEmptyStr
    deleted_files: tuple[NonEmptyStr, ...] = ()
    quarantined_files: tuple[NonEmptyStr, ...] = ()
    unverified_files: tuple[NonEmptyStr, ...] = ()
    deletion_manifest: NonEmptyStr | None = None

    @classmethod
    def rejected(cls, plan_hash: str, reason: str) -> CandidateRetentionReceipt:
        return cls(accepted=False, plan_hash=plan_hash, reason=reason)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _plan_hash_from_model(plan: CandidateRetentionPlan) -> str:
    payload = plan.model_dump(mode="json")
    payload.pop("plan_hash")
    return _sha256_bytes(_canonical_bytes(payload))


def _is_sha256_hex(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _stat_signature(status: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        int(status.st_dev),
        int(status.st_ino),
        int(status.st_nlink),
        int(status.st_size),
        int(status.st_mtime_ns),
    )


def _is_reparse(status: os.stat_result) -> bool:
    if stat.S_ISLNK(status.st_mode):
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(status, "st_file_attributes", 0) & reparse_flag)


def _identity_sha256(status: os.stat_result) -> str:
    return _sha256_bytes(
        _canonical_bytes(
            {
                "device": int(status.st_dev),
                "inode": int(status.st_ino),
                "links": int(status.st_nlink),
                "size": int(status.st_size),
                "modified_ns": int(status.st_mtime_ns),
            }
        )
    )


def _open_existing_no_follow(path: Path) -> int:
    if os.name != "nt":  # pragma: no cover - production host is Windows
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        return os.open(path, flags)

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        str(path),
        0x80000000,  # GENERIC_READ
        0x00000001 | 0x00000002 | 0x00000004,  # share read, write, and delete
        None,
        3,  # OPEN_EXISTING
        0x00200000 | 0x00000080,  # OPEN_REPARSE_POINT | ATTRIBUTE_NORMAL
        None,
    )
    invalid = ctypes.c_void_p(-1).value
    if handle == invalid:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return msvcrt.open_osfhandle(
            int(handle),
            os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0),
        )
    except BaseException:
        kernel32.CloseHandle(handle)
        raise


def _open_directory_no_delete_share(path: Path) -> int:
    if os.name != "nt":  # pragma: no cover - production host is Windows
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        return os.open(path, flags)

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        str(path),
        0x80000000,  # GENERIC_READ
        0x00000001 | 0x00000002,  # share read and write, but not delete/rename
        None,
        3,  # OPEN_EXISTING
        0x02000000 | 0x00200000,  # BACKUP_SEMANTICS | OPEN_REPARSE_POINT
        None,
    )
    invalid = ctypes.c_void_p(-1).value
    if handle == invalid:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return msvcrt.open_osfhandle(
            int(handle),
            os.O_RDONLY | getattr(os, "O_NOINHERIT", 0),
        )
    except BaseException:
        kernel32.CloseHandle(handle)
        raise


@contextmanager
def _locked_directory(path: Path) -> Iterator[None]:
    try:
        before = path.lstat()
        if _is_reparse(before) or not stat.S_ISDIR(before.st_mode):
            raise CandidateRetentionError("controller directory is unsafe")
        descriptor = _open_directory_no_delete_share(path)
        try:
            opened = os.fstat(descriptor)
            if (
                _is_reparse(opened)
                or not stat.S_ISDIR(opened.st_mode)
                or (int(opened.st_dev), int(opened.st_ino))
                != (int(before.st_dev), int(before.st_ino))
            ):
                raise CandidateRetentionError("controller directory identity changed")
        except BaseException:
            os.close(descriptor)
            raise
    except CandidateRetentionError:
        raise
    except OSError as error:
        raise CandidateRetentionError("controller directory could not be locked") from error
    try:
        yield
    finally:
        os.close(descriptor)


def _read_opened_regular(
    path: Path,
    *,
    expected_hash: str | None = None,
    expected_identity: str | None = None,
    expected_payload: bytes | None = None,
) -> tuple[bytes, os.stat_result]:
    try:
        before = path.lstat()
        if _is_reparse(before) or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise CandidateRetentionError("file is not a regular single-link file")
        if expected_payload is not None and before.st_size != len(expected_payload):
            raise CandidateRetentionError("existing manifest does not match the plan")
        signature = _stat_signature(before)
        descriptor = _open_existing_no_follow(path)
        try:
            opened = os.fstat(descriptor)
            if (
                _is_reparse(opened)
                or not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or _stat_signature(opened) != signature
            ):
                raise CandidateRetentionError("file identity changed before read")
            capture_payload = expected_hash is None or expected_payload is not None
            chunks: list[bytes] = []
            digest = hashlib.sha256() if expected_hash is not None else None
            remaining = opened.st_size
            while remaining:
                chunk = os.read(descriptor, min(1024 * 1024, remaining))
                if not chunk:
                    raise CandidateRetentionError("file changed while it was read")
                if capture_payload:
                    chunks.append(chunk)
                if digest is not None:
                    digest.update(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks) if capture_payload else b""
            final = os.fstat(descriptor)
            if _stat_signature(final) != signature:
                raise CandidateRetentionError("file changed while it was read")
        finally:
            os.close(descriptor)
    except CandidateRetentionError:
        raise
    except OSError as error:
        raise CandidateRetentionError("file could not be opened safely") from error
    identity = _identity_sha256(before)
    if expected_hash is not None and (digest is None or digest.hexdigest() != expected_hash):
        raise CandidateRetentionError("file hash changed")
    if expected_identity is not None and identity != expected_identity:
        raise CandidateRetentionError("file identity changed")
    if expected_payload is not None and payload != expected_payload:
        raise CandidateRetentionError("existing manifest does not match the plan")
    return payload, before


def _verify_created_manifest_path(
    path: Path,
    created_identity: tuple[int, int],
    expected_size: int,
) -> None:
    after = path.lstat()
    if (
        (int(after.st_dev), int(after.st_ino)) != created_identity
        or _is_reparse(after)
        or not stat.S_ISREG(after.st_mode)
        or after.st_nlink != 1
        or after.st_size != expected_size
    ):
        raise CandidateRetentionError("new manifest path changed after write")


def _create_exclusive_manifest(path: Path, payload: bytes) -> bool:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOINHERIT", 0)
    )
    descriptor = os.open(path, flags, 0o600)
    created_identity: tuple[int, int] | None = None
    failure: BaseException | None = None
    durable = False
    try:
        opened = os.fstat(descriptor)
        if _is_reparse(opened) or not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise CandidateRetentionError("new manifest is not a regular single-link file")
        created_identity = (int(opened.st_dev), int(opened.st_ino))
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
        durable = True
        final = os.fstat(descriptor)
        if final.st_size != len(payload) or final.st_nlink != 1 or _is_reparse(final):
            raise CandidateRetentionError("new manifest changed while it was written")
    except BaseException as error:
        failure = error
    try:
        os.close(descriptor)
    except BaseException as error:
        if failure is None:
            failure = error
    if failure is not None:
        if durable:
            return False
        try:
            current = path.lstat()
            if (
                created_identity is None
                or (int(current.st_dev), int(current.st_ino)) != created_identity
                or _is_reparse(current)
                or not stat.S_ISREG(current.st_mode)
                or current.st_nlink != 1
            ):
                raise CandidateRetentionRollbackError("failed manifest path changed before cleanup")
            path.unlink()
        except CandidateRetentionRollbackError:
            raise
        except OSError as cleanup_error:
            raise CandidateRetentionRollbackError(
                "failed manifest could not be removed"
            ) from cleanup_error
        raise failure
    if created_identity is None:  # pragma: no cover - guarded by the open-file checks above
        raise CandidateRetentionError("new manifest identity is unavailable")
    try:
        _verify_created_manifest_path(path, created_identity, len(payload))
    except Exception:
        return False
    return True


def _physical_delete(path: Path) -> None:
    path.unlink()


def _default_disk_free_gb(root: Path) -> int:
    return shutil.disk_usage(root).free // (1024**3)


def _overlaps(first: Path, second: Path) -> bool:
    return first == second or first.is_relative_to(second) or second.is_relative_to(first)


class CandidateRetentionService:
    """Controller-owned retention planner with receipt-bound deletion."""

    def __init__(
        self,
        root: Path,
        manifest: CandidateRetentionManifest,
        *,
        repository_root: Path,
        disk_free_gb: Callable[[Path], int] = _default_disk_free_gb,
        minimum_disk_free_gb: int = 10,
    ) -> None:
        if not isinstance(root, Path) or not isinstance(repository_root, Path):
            raise TypeError("root and repository_root must be Path values")
        if type(manifest) is not CandidateRetentionManifest:
            raise TypeError("manifest must be CandidateRetentionManifest")
        if not callable(disk_free_gb):
            raise TypeError("disk_free_gb must be callable")
        if type(minimum_disk_free_gb) is not int:
            raise TypeError("minimum_disk_free_gb must be an integer")
        if minimum_disk_free_gb < 0:
            raise ValueError("minimum_disk_free_gb cannot be negative")

        try:
            resolved_root = root.resolve(strict=True)
        except OSError as error:
            raise CandidateRetentionError("candidate root is unavailable") from error
        if root.is_symlink() or not resolved_root.is_dir():
            raise CandidateRetentionError("candidate root must be a real directory")
        repository = repository_root.resolve(strict=False)
        protected_roots = (
            repository,
            (repository / "vesper" / "data" / "massive").resolve(strict=False),
            (repository / "vesper" / "data" / "model_research").resolve(strict=False),
        )
        if any(_overlaps(resolved_root, protected) for protected in protected_roots):
            raise CandidateRetentionError("candidate root overlaps a protected root")

        try:
            checked_manifest = CandidateRetentionManifest.model_validate_json(
                manifest.model_dump_json(), strict=True
            )
        except ValidationError as error:  # pragma: no cover - import-free defensive boundary
            raise CandidateRetentionError("candidate manifest is invalid") from error
        self._root = resolved_root
        self._manifest = checked_manifest
        self._manifest_hash = _sha256_bytes(
            _canonical_bytes(checked_manifest.model_dump(mode="json"))
        )
        self._protected_roots = protected_roots
        self._disk_free_gb = disk_free_gb
        self._minimum_disk_free_gb = minimum_disk_free_gb
        self._plans: dict[str, CandidateRetentionPlan] = {}
        self._recover_prepared_transactions()

    @property
    def root(self) -> Path:
        return self._root

    def plan(self, now_utc: datetime) -> CandidateRetentionPlan:
        if not isinstance(now_utc, datetime) or now_utc.utcoffset() != timedelta(0):
            raise CandidateRetentionError("retention time must be timezone-aware UTC")
        self._require_root_identity()
        file_bindings = self._verify_manifest_files()
        try:
            free_gb = self._disk_free_gb(self._root)
        except Exception as error:
            raise CandidateRetentionError("disk free space is unavailable") from error
        if type(free_gb) is not int or free_gb < 0:
            raise CandidateRetentionError("disk free space reading is invalid")

        protected_ids = {
            candidate_id
            for candidate_id in (
                self._manifest.active_candidate_id,
                self._manifest.rollback_candidate_id,
            )
            if candidate_id is not None
        }
        deletions: list[CandidateDeletion] = []
        for candidate in self._manifest.candidates:
            expires_at = candidate.created_at_utc + timedelta(
                days=_RETENTION_DAYS[candidate.status]
            )
            if candidate.candidate_id in protected_ids or now_utc < expires_at:
                continue
            for file in candidate.files:
                if file.kind in _PERMANENT_KINDS:
                    continue
                deletions.append(
                    CandidateDeletion(
                        candidate_id=candidate.candidate_id,
                        status=candidate.status,
                        relative_path=file.relative_path,
                        sha256=file.sha256,
                        expires_at_utc=expires_at,
                    )
                )
        ordered = tuple(sorted(deletions, key=lambda item: (item.candidate_id, item.relative_path)))
        payload = {
            "manifest_hash": self._manifest_hash,
            "approved_root": str(self._root),
            "planned_at_utc": now_utc.isoformat().replace("+00:00", "Z"),
            "active_candidate_id": self._manifest.active_candidate_id,
            "rollback_candidate_id": self._manifest.rollback_candidate_id,
            "candidate_training_paused": free_gb <= self._minimum_disk_free_gb,
            "file_bindings": [item.model_dump(mode="json") for item in file_bindings],
            "deletions": [item.model_dump(mode="json") for item in ordered],
        }
        plan = CandidateRetentionPlan(
            plan_hash=_sha256_bytes(_canonical_bytes(payload)),
            manifest_hash=self._manifest_hash,
            approved_root=str(self._root),
            planned_at_utc=now_utc,
            active_candidate_id=self._manifest.active_candidate_id,
            rollback_candidate_id=self._manifest.rollback_candidate_id,
            candidate_training_paused=free_gb <= self._minimum_disk_free_gb,
            file_bindings=file_bindings,
            deletions=ordered,
        )
        self._plans[plan.plan_hash] = CandidateRetentionPlan.model_validate_json(
            plan.model_dump_json(), strict=True
        )
        return plan

    def apply(
        self,
        plan_hash: str,
        activation_store: OperationsActivationStore,
        authority_receipts: AuthorityReceiptStore,
    ) -> CandidateRetentionReceipt:
        if not isinstance(plan_hash, str) or not _is_sha256_hex(plan_hash):
            raise TypeError("plan_hash must be a SHA-256 hex string")
        if type(activation_store) is not OperationsActivationStore:
            raise TypeError("activation_store must be OperationsActivationStore")
        plan = self._plans.get(plan_hash)
        if plan is None:
            return CandidateRetentionReceipt.rejected(plan_hash, "plan-not-found")

        try:
            grant = activation_store.validated_grant(ActivationCapability.CANDIDATE_DELETION)
        except ActivationAuthorityError:
            return CandidateRetentionReceipt.rejected(plan_hash, "activation-authority-invalid")
        except Exception:
            return CandidateRetentionReceipt.rejected(plan_hash, "activation-authority-invalid")
        if not grant.enabled:
            return CandidateRetentionReceipt.rejected(plan_hash, "activation-disabled")
        if grant.receipt_id is None:
            return CandidateRetentionReceipt.rejected(plan_hash, "activation-authority-invalid")

        try:
            authority_receipts.require_candidate_deletion(
                grant.receipt_id,
                self._root,
                plan_hash,
            )
        except Exception:
            return CandidateRetentionReceipt.rejected(plan_hash, "deletion-authority-invalid")

        manifest_path = self._root / _MANIFEST_DIRECTORY / f"{plan_hash}.json"
        manifest_payload = _canonical_bytes(plan.model_dump(mode="json"))
        try:
            self._require_root_identity()
            if self._existing_manifest_matches(manifest_path, manifest_payload):
                return self._replay_receipt(plan, manifest_path)
        except CandidateRetentionError:
            return CandidateRetentionReceipt.rejected(plan_hash, "deletion-manifest-unsafe")

        try:
            self._verify_plan_bindings(plan)
        except CandidateRetentionError:
            return CandidateRetentionReceipt.rejected(plan_hash, "planned-file-changed")

        try:
            staged, created_directories, prepared_path = self._stage_plan(plan)
        except CandidateRetentionRollbackError:
            raise
        except CandidateRetentionError:
            return CandidateRetentionReceipt.rejected(plan_hash, "candidate-staging-failed")

        try:
            commit_verified = self._commit_manifest(manifest_path, manifest_payload)
        except CandidateRetentionRollbackError:
            self._rollback_staging(staged, created_directories, prepared_path, plan)
            raise
        except (CandidateRetentionError, OSError):
            self._rollback_staging(staged, created_directories, prepared_path, plan)
            return CandidateRetentionReceipt.rejected(plan_hash, "deletion-manifest-unavailable")
        except BaseException:
            self._rollback_staging(staged, created_directories, prepared_path, plan)
            raise

        if not commit_verified:
            quarantined, unverified = self._classify_staged_quarantine(staged)
            return CandidateRetentionReceipt(
                accepted=True,
                plan_hash=plan_hash,
                reason="candidate-retention-commit-indeterminate",
                quarantined_files=quarantined,
                unverified_files=unverified,
            )

        self._remove_prepared_journal(prepared_path, plan, required=False)
        deleted, quarantined, unverified = self._cleanup_committed_quarantine(
            staged, created_directories
        )
        return CandidateRetentionReceipt(
            accepted=True,
            plan_hash=plan_hash,
            reason=(
                "candidate-binaries-unverified"
                if unverified
                else (
                    "candidate-binaries-quarantined"
                    if quarantined
                    else "candidate-binaries-deleted"
                )
            ),
            deleted_files=deleted,
            quarantined_files=quarantined,
            unverified_files=unverified,
            deletion_manifest=str(manifest_path),
        )

    def _verify_plan_bindings(self, plan: CandidateRetentionPlan) -> None:
        identities: set[tuple[int, int]] = set()
        for binding in plan.file_bindings:
            _path, identity, _identity_hash = self._verified_file(
                binding.relative_path,
                binding.sha256,
                binding.identity_sha256,
            )
            if identity in identities:
                raise CandidateRetentionError("manifest file identity is not unique")
            identities.add(identity)

    def _existing_manifest_matches(self, path: Path, payload: bytes) -> bool:
        directory = path.parent
        if not os.path.lexists(directory):
            return False
        with _locked_directory(self._root):
            self._require_safe_directory(directory)
            with _locked_directory(directory):
                if not os.path.lexists(path):
                    return False
                _read_opened_regular(path, expected_payload=payload)
                return True

    def _replay_receipt(
        self, plan: CandidateRetentionPlan, manifest_path: Path
    ) -> CandidateRetentionReceipt:
        deletion_paths = {item.relative_path for item in plan.deletions}
        binding_by_path = {item.relative_path: item for item in plan.file_bindings}
        for binding in plan.file_bindings:
            if binding.relative_path in deletion_paths:
                continue
            self._verified_file(
                binding.relative_path,
                binding.sha256,
                binding.identity_sha256,
            )
        deleted: list[str] = []
        quarantined: list[str] = []
        quarantine_root = self._root / _MANIFEST_DIRECTORY / "quarantine" / plan.plan_hash
        for deletion in plan.deletions:
            source = self._root.joinpath(*PurePosixPath(deletion.relative_path).parts)
            if os.path.lexists(source):
                raise CandidateRetentionError("committed source file reappeared")
            staged = quarantine_root.joinpath(*PurePosixPath(deletion.relative_path).parts)
            if os.path.lexists(staged):
                binding = binding_by_path[deletion.relative_path]
                self._verified_staged_file(staged, binding)
                quarantined.append(deletion.relative_path)
            else:
                deleted.append(deletion.relative_path)
        return CandidateRetentionReceipt(
            accepted=True,
            plan_hash=plan.plan_hash,
            reason="candidate-retention-already-committed",
            deleted_files=tuple(deleted),
            quarantined_files=tuple(quarantined),
            deletion_manifest=str(manifest_path),
        )

    def _prepared_payload(self, plan: CandidateRetentionPlan) -> bytes:
        return _canonical_bytes(
            CandidateRetentionPreparedJournal(plan=plan).model_dump(mode="json")
        )

    def _write_prepared_journal(self, path: Path, plan: CandidateRetentionPlan) -> None:
        if _plan_hash_from_model(plan) != plan.plan_hash:
            raise CandidateRetentionError("prepared plan hash is invalid")
        payload = self._prepared_payload(plan)
        with _locked_directory(self._root):
            self._require_safe_directory(path.parent)
            with _locked_directory(path.parent):
                try:
                    verified = _create_exclusive_manifest(path, payload)
                except FileExistsError as error:
                    raise CandidateRetentionError("prepared journal already exists") from error
                if verified:
                    return
                try:
                    _existing, status = _read_opened_regular(path, expected_payload=payload)
                    self._unlink_same_regular_file(path, status)
                except (CandidateRetentionError, OSError) as error:
                    raise CandidateRetentionRollbackError(
                        "uncertain prepared journal could not be removed"
                    ) from error
                raise CandidateRetentionError("prepared journal durability is uncertain")

    def _remove_prepared_journal(
        self,
        path: Path,
        plan: CandidateRetentionPlan,
        *,
        required: bool,
    ) -> bool:
        payload = self._prepared_payload(plan)
        try:
            if not os.path.lexists(path.parent):
                return True
            with _locked_directory(self._root):
                self._require_safe_directory(path.parent)
                with _locked_directory(path.parent):
                    if not os.path.lexists(path):
                        return True
                    _existing, status = _read_opened_regular(path, expected_payload=payload)
                    self._unlink_same_regular_file(path, status)
            return True
        except (CandidateRetentionError, OSError) as error:
            if required:
                raise CandidateRetentionRollbackError(
                    "prepared journal could not be removed"
                ) from error
            return False

    def _unlink_same_regular_file(self, path: Path, expected: os.stat_result) -> None:
        current = path.lstat()
        if (
            _is_reparse(current)
            or not stat.S_ISREG(current.st_mode)
            or current.st_nlink != 1
            or (int(current.st_dev), int(current.st_ino))
            != (int(expected.st_dev), int(expected.st_ino))
        ):
            raise CandidateRetentionError("controller journal identity changed")
        path.unlink()
        if os.path.lexists(path):
            raise CandidateRetentionError("controller journal removal was not confirmed")

    def _recover_prepared_transactions(self) -> None:
        retention = self._root / _MANIFEST_DIRECTORY
        if not os.path.lexists(retention):
            return
        self._require_root_identity()
        with _locked_directory(self._root):
            self._require_safe_directory(retention)
            with _locked_directory(retention):
                prepared_paths = sorted(
                    (
                        Path(entry.path)
                        for entry in os.scandir(retention)
                        if entry.name.endswith(_PREPARED_SUFFIX)
                    ),
                    key=lambda path: path.name,
                )
                for path in prepared_paths:
                    plan_hash = path.name[: -len(_PREPARED_SUFFIX)]
                    if not _is_sha256_hex(plan_hash):
                        raise CandidateRetentionError("prepared journal name is invalid")
                    self._recover_prepared_transaction(path, plan_hash)

    def _recover_prepared_transaction(self, path: Path, plan_hash: str) -> None:
        committed_path = self._root / _MANIFEST_DIRECTORY / f"{plan_hash}.json"
        if os.path.lexists(committed_path):
            committed_payload, _status = _read_opened_regular(committed_path)
            committed_plan = self._parse_recovery_plan(committed_payload, plan_hash)
            expected_prepared = self._prepared_payload(committed_plan)
            try:
                _payload, prepared_status = _read_opened_regular(
                    path, expected_payload=expected_prepared
                )
                self._unlink_same_regular_file(path, prepared_status)
            except (CandidateRetentionError, OSError):
                pass
            return

        prepared_payload, prepared_status = _read_opened_regular(path)
        try:
            journal = CandidateRetentionPreparedJournal.model_validate_json(
                prepared_payload, strict=True
            )
        except ValidationError as error:
            raise CandidateRetentionError("prepared journal is invalid") from error
        if self._prepared_payload(journal.plan) != prepared_payload:
            raise CandidateRetentionError("prepared journal is not canonical")
        self._validate_recovery_plan(journal.plan, plan_hash)
        self._restore_prepared_plan(journal.plan)
        self._unlink_same_regular_file(path, prepared_status)
        self._remove_empty_recovery_directories(journal.plan)

    def _parse_recovery_plan(self, payload: bytes, plan_hash: str) -> CandidateRetentionPlan:
        try:
            plan = CandidateRetentionPlan.model_validate_json(payload, strict=True)
        except ValidationError as error:
            raise CandidateRetentionError("committed retention manifest is invalid") from error
        if _canonical_bytes(plan.model_dump(mode="json")) != payload:
            raise CandidateRetentionError("committed retention manifest is not canonical")
        self._validate_recovery_plan(plan, plan_hash)
        return plan

    def _validate_recovery_plan(
        self, plan: CandidateRetentionPlan, expected_plan_hash: str
    ) -> None:
        if plan.plan_hash != expected_plan_hash or _plan_hash_from_model(plan) != plan.plan_hash:
            raise CandidateRetentionError("recovery plan hash is invalid")
        if plan.manifest_hash != self._manifest_hash or plan.approved_root != str(self._root):
            raise CandidateRetentionError("recovery plan authority is invalid")
        if (
            plan.active_candidate_id != self._manifest.active_candidate_id
            or plan.rollback_candidate_id != self._manifest.rollback_candidate_id
        ):
            raise CandidateRetentionError("recovery plan candidate protection changed")

        expected_files = {
            file.relative_path: (candidate, file)
            for candidate in self._manifest.candidates
            for file in candidate.files
        }
        bindings = {binding.relative_path: binding for binding in plan.file_bindings}
        if len(bindings) != len(plan.file_bindings) or set(bindings) != set(expected_files):
            raise CandidateRetentionError("recovery plan file bindings are invalid")
        for relative_path, binding in bindings.items():
            candidate, file = expected_files[relative_path]
            if (
                binding.candidate_id != candidate.candidate_id
                or binding.kind != file.kind
                or binding.sha256 != file.sha256
            ):
                raise CandidateRetentionError("recovery plan file binding changed")

        protected_ids = {
            candidate_id
            for candidate_id in (
                self._manifest.active_candidate_id,
                self._manifest.rollback_candidate_id,
            )
            if candidate_id is not None
        }
        deletion_paths: set[str] = set()
        for deletion in plan.deletions:
            if deletion.relative_path in deletion_paths:
                raise CandidateRetentionError("recovery plan deletion is duplicated")
            deletion_paths.add(deletion.relative_path)
            expected = expected_files.get(deletion.relative_path)
            if expected is None:
                raise CandidateRetentionError("recovery plan deletion is unknown")
            candidate, file = expected
            expires_at = candidate.created_at_utc + timedelta(
                days=_RETENTION_DAYS[candidate.status]
            )
            if (
                file.kind != "binary"
                or deletion.candidate_id != candidate.candidate_id
                or deletion.status != candidate.status
                or deletion.sha256 != file.sha256
                or deletion.expires_at_utc != expires_at
                or plan.planned_at_utc < expires_at
                or candidate.candidate_id in protected_ids
            ):
                raise CandidateRetentionError("recovery plan deletion is invalid")

    def _restore_prepared_plan(self, plan: CandidateRetentionPlan) -> None:
        bindings = {binding.relative_path: binding for binding in plan.file_bindings}
        transaction = self._root / _MANIFEST_DIRECTORY / "quarantine" / plan.plan_hash
        for deletion in reversed(plan.deletions):
            binding = bindings[deletion.relative_path]
            source = self._root.joinpath(*PurePosixPath(deletion.relative_path).parts)
            destination = transaction.joinpath(*PurePosixPath(deletion.relative_path).parts)
            source_exists = os.path.lexists(source)
            destination_exists = os.path.lexists(destination)
            if source_exists and destination_exists:
                raise CandidateRetentionError(
                    "prepared recovery found both source and quarantine files"
                )
            if source_exists:
                self._verified_file(
                    binding.relative_path,
                    binding.sha256,
                    binding.identity_sha256,
                )
                continue
            if not destination_exists:
                raise CandidateRetentionError("prepared recovery candidate file is unavailable")
            with (
                self._locked_directory_chain(source.parent),
                self._locked_directory_chain(destination.parent),
            ):
                if os.path.lexists(source) or not os.path.lexists(destination):
                    raise CandidateRetentionError("prepared recovery candidate state changed")
                self._verified_staged_file(destination, binding)
                os.rename(destination, source)
                self._verified_file(
                    binding.relative_path,
                    binding.sha256,
                    binding.identity_sha256,
                )
        self._verify_plan_bindings(plan)

    def _remove_empty_recovery_directories(self, plan: CandidateRetentionPlan) -> None:
        retention = self._root / _MANIFEST_DIRECTORY
        quarantine = retention / "quarantine"
        transaction = quarantine / plan.plan_hash
        directories: set[Path] = {transaction, quarantine, retention}
        for deletion in plan.deletions:
            current = transaction.joinpath(*PurePosixPath(deletion.relative_path).parts).parent
            while current != transaction.parent:
                directories.add(current)
                current = current.parent
        for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass

    def _stage_plan(
        self, plan: CandidateRetentionPlan
    ) -> tuple[
        list[tuple[CandidateDeletion, CandidateFileBinding, Path, Path]],
        list[Path],
        Path,
    ]:
        created: list[Path] = []
        staged: list[tuple[CandidateDeletion, CandidateFileBinding, Path, Path]] = []
        bindings = {item.relative_path: item for item in plan.file_bindings}
        retention = self._root / _MANIFEST_DIRECTORY
        prepared_path = retention / f"{plan.plan_hash}{_PREPARED_SUFFIX}"
        prepared_written = False
        quarantine = retention / "quarantine"
        transaction = quarantine / plan.plan_hash
        try:
            self._create_or_validate_directory(retention, created)
            self._write_prepared_journal(prepared_path, plan)
            prepared_written = True
            self._create_or_validate_directory(quarantine, created)
            if os.path.lexists(transaction):
                raise CandidateRetentionError("candidate staging directory already exists")
            self._create_or_validate_directory(transaction, created)
            for deletion in plan.deletions:
                binding = bindings[deletion.relative_path]
                source = self._root.joinpath(*PurePosixPath(deletion.relative_path).parts)
                destination = transaction.joinpath(*PurePosixPath(deletion.relative_path).parts)
                current = transaction
                for part in PurePosixPath(deletion.relative_path).parts[:-1]:
                    current = current / part
                    self._create_or_validate_directory(current, created)
                with (
                    self._locked_directory_chain(source.parent),
                    self._locked_directory_chain(destination.parent),
                ):
                    source, _identity, _identity_hash = self._verified_file(
                        deletion.relative_path,
                        deletion.sha256,
                        binding.identity_sha256,
                    )
                    if os.path.lexists(destination):
                        raise CandidateRetentionError("candidate staging path already exists")
                    os.rename(source, destination)
                    staged.append((deletion, binding, source, destination))
                    self._verified_staged_file(destination, binding)
            return staged, created, prepared_path
        except BaseException as error:
            try:
                self._rollback_staging(
                    staged,
                    created,
                    prepared_path if prepared_written else None,
                    plan,
                )
            except CandidateRetentionRollbackError:
                raise
            if isinstance(error, CandidateRetentionError):
                raise
            raise CandidateRetentionError("candidate staging failed") from error

    def _rollback_staging(
        self,
        staged: list[tuple[CandidateDeletion, CandidateFileBinding, Path, Path]],
        created_directories: list[Path],
        prepared_path: Path | None,
        plan: CandidateRetentionPlan,
    ) -> None:
        try:
            for _deletion, binding, source, destination in reversed(staged):
                with (
                    self._locked_directory_chain(source.parent),
                    self._locked_directory_chain(destination.parent),
                ):
                    if os.path.lexists(source):
                        raise CandidateRetentionRollbackError(
                            "candidate source path was occupied during rollback"
                        )
                    self._verified_staged_file(destination, binding)
                    os.rename(destination, source)
                    self._verified_file(
                        binding.relative_path,
                        binding.sha256,
                        binding.identity_sha256,
                    )
            if prepared_path is not None:
                self._remove_prepared_journal(prepared_path, plan, required=True)
            for directory in reversed(created_directories):
                directory.rmdir()
        except CandidateRetentionRollbackError:
            raise
        except BaseException as error:
            raise CandidateRetentionRollbackError(
                "candidate staging rollback was incomplete"
            ) from error

    def _cleanup_committed_quarantine(
        self,
        staged: list[tuple[CandidateDeletion, CandidateFileBinding, Path, Path]],
        created_directories: list[Path],
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        deleted: list[str] = []
        quarantined: list[str] = []
        unverified: list[str] = []
        for deletion, binding, _source, destination in staged:
            with self._locked_directory_chain(destination.parent):
                try:
                    self._verified_staged_file(destination, binding)
                except (CandidateRetentionError, OSError):
                    unverified.append(deletion.relative_path)
                    continue
                try:
                    _physical_delete(destination)
                except OSError:
                    pass
                if not os.path.lexists(destination):
                    deleted.append(deletion.relative_path)
                    continue
                try:
                    self._verified_staged_file(destination, binding)
                except (CandidateRetentionError, OSError):
                    unverified.append(deletion.relative_path)
                else:
                    quarantined.append(deletion.relative_path)
        for directory in reversed(created_directories):
            if directory == self._root / _MANIFEST_DIRECTORY:
                continue
            try:
                directory.rmdir()
            except OSError:
                pass
        return tuple(deleted), tuple(quarantined), tuple(unverified)

    def _classify_staged_quarantine(
        self,
        staged: list[tuple[CandidateDeletion, CandidateFileBinding, Path, Path]],
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        quarantined: list[str] = []
        unverified: list[str] = []
        for deletion, binding, source, destination in staged:
            if os.path.lexists(source) or not os.path.lexists(destination):
                unverified.append(deletion.relative_path)
                continue
            with self._locked_directory_chain(destination.parent):
                try:
                    self._verified_staged_file(destination, binding)
                except (CandidateRetentionError, OSError):
                    unverified.append(deletion.relative_path)
                else:
                    quarantined.append(deletion.relative_path)
        return tuple(quarantined), tuple(unverified)

    def _verified_staged_file(self, path: Path, binding: CandidateFileBinding) -> None:
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise CandidateRetentionError("quarantined candidate is unavailable") from error
        if not resolved.is_relative_to(self._root):
            raise CandidateRetentionError("quarantined candidate leaves approved root")
        _read_opened_regular(
            resolved,
            expected_hash=binding.sha256,
            expected_identity=binding.identity_sha256,
        )

    def _create_or_validate_directory(self, path: Path, created: list[Path]) -> None:
        if os.path.lexists(path):
            self._require_safe_directory(path)
            return
        try:
            path.mkdir()
        except FileExistsError:
            self._require_safe_directory(path)
            return
        created.append(path)
        self._require_safe_directory(path)

    def _require_safe_directory(self, path: Path) -> None:
        try:
            status = path.lstat()
            if _is_reparse(status) or not stat.S_ISDIR(status.st_mode):
                raise CandidateRetentionError("controller directory is unsafe")
            resolved = path.resolve(strict=True)
        except CandidateRetentionError:
            raise
        except OSError as error:
            raise CandidateRetentionError("controller directory is unavailable") from error
        if not resolved.is_relative_to(self._root):
            raise CandidateRetentionError("controller directory leaves candidate root")

    @contextmanager
    def _locked_directory_chain(self, directory: Path) -> Iterator[None]:
        try:
            relative = directory.relative_to(self._root)
        except ValueError as error:
            raise CandidateRetentionError("controller directory leaves candidate root") from error
        with ExitStack() as locks:
            current = self._root
            locks.enter_context(_locked_directory(current))
            for part in relative.parts:
                current = current / part
                self._require_safe_directory(current)
                locks.enter_context(_locked_directory(current))
            yield

    def _commit_manifest(self, path: Path, payload: bytes) -> bool:
        commit_result: bool | None = None
        try:
            with _locked_directory(self._root):
                self._require_safe_directory(path.parent)
                with _locked_directory(path.parent):
                    try:
                        commit_result = _create_exclusive_manifest(path, payload)
                    except FileExistsError:
                        _read_opened_regular(path, expected_payload=payload)
                        commit_result = True
        except BaseException:
            if commit_result is not None:
                return False
            raise
        if commit_result is None:  # pragma: no cover - every body path assigns or raises
            raise CandidateRetentionError("manifest commit result is unavailable")
        return commit_result

    def _verify_manifest_files(self) -> tuple[CandidateFileBinding, ...]:
        identities: set[tuple[int, int]] = set()
        bindings: list[CandidateFileBinding] = []
        for candidate in self._manifest.candidates:
            for file in candidate.files:
                _path, identity, identity_hash = self._verified_file(
                    file.relative_path, file.sha256
                )
                if identity in identities:
                    raise CandidateRetentionError("manifest file identity is not unique")
                identities.add(identity)
                bindings.append(
                    CandidateFileBinding(
                        candidate_id=candidate.candidate_id,
                        relative_path=file.relative_path,
                        kind=file.kind,
                        sha256=file.sha256,
                        identity_sha256=identity_hash,
                    )
                )
        return tuple(sorted(bindings, key=lambda item: (item.candidate_id, item.relative_path)))

    def _verified_file(
        self,
        relative_path: str,
        expected_hash: str,
        expected_identity: str | None = None,
    ) -> tuple[Path, tuple[int, int], str]:
        pure = PurePosixPath(relative_path)
        path = self._root.joinpath(*pure.parts)
        current = self._root
        for part in pure.parts:
            current = current / part
            try:
                current_status = current.lstat()
            except OSError as error:
                raise CandidateRetentionError("candidate file is unavailable") from error
            if _is_reparse(current_status):
                raise CandidateRetentionError("candidate file resolves outside candidate root")
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise CandidateRetentionError("candidate file is unavailable") from error
        if not resolved.is_relative_to(self._root):
            raise CandidateRetentionError("candidate file resolves outside candidate root")
        if any(_overlaps(resolved, protected) for protected in self._protected_roots):
            raise CandidateRetentionError("candidate file overlaps a protected root")
        try:
            if resolved.lstat().st_nlink != 1:
                raise CandidateRetentionError("candidate file has hard links")
        except OSError as error:
            raise CandidateRetentionError("candidate file is unavailable") from error
        _payload, status = _read_opened_regular(
            resolved,
            expected_hash=expected_hash,
            expected_identity=expected_identity,
        )
        if status.st_nlink != 1:
            raise CandidateRetentionError("candidate file has hard links")
        return (
            resolved,
            (int(status.st_dev), int(status.st_ino)),
            _identity_sha256(status),
        )

    def _require_root_identity(self) -> None:
        try:
            current = self._root.resolve(strict=True)
        except OSError as error:
            raise CandidateRetentionError("candidate root is unavailable") from error
        if current != self._root or self._root.is_symlink() or not current.is_dir():
            raise CandidateRetentionError("candidate root identity changed")
        if any(_overlaps(current, protected) for protected in self._protected_roots):
            raise CandidateRetentionError("candidate root overlaps a protected root")
