"""Bounded local Git operations for reviewed V20 maintenance worktrees."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Annotated, Literal, Protocol

from pydantic import Field, StringConstraints, field_validator, model_validator

from vesper.platform.tui.command_contracts import (
    CommandRequest,
    CommandType,
    ConfirmationProof,
    GitRevision,
    SourceControlPushPayload,
)
from vesper.platform.tui.process_capture import BoundedProcessError, run_bounded_process
from vesper.platform.tui.views import (
    CapabilityState,
    CapabilityView,
    NonEmptyStr,
    SafeId,
    Sha256Hex,
    StrictModel,
)


_METADATA_OUTPUT_LIMIT = 1024 * 1024
_DIFF_OUTPUT_LIMIT = 16 * 1024 * 1024
_COMMAND_TIMEOUT_SECONDS = 300.0
_METADATA_TIMEOUT_SECONDS = 30.0
_PUSH_DESTINATION_PATTERN = re.compile(
    r"^refs/heads/[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*$"
)
_PUSH_REMOTE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PROCESS_ENV_ALLOWLIST = frozenset(
    {
        "APPDATA",
        "CARGO_HOME",
        "COMSPEC",
        "HOMEDRIVE",
        "HOMEPATH",
        "LANG",
        "LC_ALL",
        "LOCALAPPDATA",
        "NO_COLOR",
        "NUMBER_OF_PROCESSORS",
        "PATH",
        "PATHEXT",
        "PROCESSOR_ARCHITECTURE",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "PROGRAMW6432",
        "RUSTUP_HOME",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TERM",
        "TMP",
        "USERPROFILE",
        "UV_CACHE_DIR",
        "VIRTUAL_ENV",
        "WINDIR",
    }
)
_BRANCH = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$",
    ),
]


class GitPortError(RuntimeError):
    """Local Git state could not be read within the safety bounds."""


class ProcessRunner(Protocol):
    def __call__(
        self,
        command: tuple[str, ...],
        *,
        max_output_bytes: int,
        cwd: Path,
        timeout: float,
        shell: bool,
        stdin: int,
        stdout: int,
        stderr: int,
        check: bool,
        env: dict[str, str],
    ) -> subprocess.CompletedProcess[bytes]: ...


class MergeLock(Protocol):
    def __enter__(self) -> object: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: object | None,
    ) -> bool | None: ...


VerificationGateName = Literal[
    "focused-tests",
    "broad-tests",
    "formatting",
    "static-analysis",
    "post-merge-tests",
]


class VerificationCommand(StrictModel):
    name: VerificationGateName
    argv: tuple[NonEmptyStr, ...]

    @field_validator("argv")
    @classmethod
    def require_bounded_direct_argv(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) > 128:
            raise ValueError("verification argv must contain 1 to 128 arguments")
        if any("\x00" in argument or "\r" in argument or "\n" in argument for argument in value):
            raise ValueError("verification argv contains a control character")
        if not _is_approved_verification_argv(value):
            raise ValueError("command is not an approved V20 verification gate")
        return value

    @model_validator(mode="after")
    def bind_gate_name_to_command_kind(self) -> VerificationCommand:
        kind = _verification_command_kind(self.argv)
        allowed_names = {
            "tests": {"focused-tests", "broad-tests", "post-merge-tests"},
            "formatting": {"formatting"},
            "static-analysis": {"static-analysis"},
        }
        if kind is None or self.name not in allowed_names[kind]:
            raise ValueError("verification gate name does not match command kind")
        return self


class VerificationRequest(StrictModel):
    worktree: Path
    commands: tuple[VerificationCommand, ...]


class WorktreeRequest(StrictModel):
    path: Path
    branch: _BRANCH
    start_revision: GitRevision

    @field_validator("branch")
    @classmethod
    def require_safe_branch(cls, value: str) -> str:
        if (
            ".." in value
            or "//" in value
            or value.endswith(("/", "."))
            or "/." in value
            or value.lower().endswith(".lock")
        ):
            raise ValueError("branch name is unsafe")
        return value


class MergeRequest(StrictModel):
    repository_root: Path
    expected_base_revision: GitRevision
    candidate_revision: GitRevision
    reviewed_diff_hash: Sha256Hex
    rollback_revision: GitRevision
    changed_paths: tuple[NonEmptyStr, ...]

    @field_validator("changed_paths")
    @classmethod
    def require_canonical_changed_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(value) > 256:
            raise ValueError("changed paths must contain 1 to 256 entries")
        if tuple(sorted(set(value))) != value or len({path.casefold() for path in value}) != len(
            value
        ):
            raise ValueError("changed paths must be unique and sorted")
        return value


class RepositoryStatus(StrictModel):
    revision: GitRevision
    clean: bool


GitOperation = Literal[
    "create-worktree",
    "verify",
    "merge-no-ff",
    "revert",
    "push",
]


class GitReceipt(StrictModel):
    operation: GitOperation
    accepted: bool
    code: NonEmptyStr
    revision: GitRevision | None
    diff_hash: Sha256Hex | None
    failed_check: NonEmptyStr | None = None
    command_id: SafeId | None = None


class _PushReceiptRecord(StrictModel):
    command_id: SafeId
    expected_revision: GitRevision
    push_remote: NonEmptyStr
    push_target: NonEmptyStr
    push_destination: NonEmptyStr
    receipt: GitReceipt

    @model_validator(mode="after")
    def bind_receipt(self) -> _PushReceiptRecord:
        if (
            not self.receipt.accepted
            or self.receipt.operation != "push"
            or self.receipt.command_id != self.command_id
            or self.receipt.revision != self.expected_revision
        ):
            raise ValueError("push receipt record is not exactly bound")
        return self


class _PushReceiptStore:
    def __init__(self, database: Path) -> None:
        self._database = database

    def load(self, command_id: str) -> _PushReceiptRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT receipt_json FROM source_control_push_receipts WHERE command_id = ?",
                (command_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row[0])
            return _PushReceiptRecord.model_validate(payload, strict=True)
        except Exception as error:
            raise GitPortError("push receipt store is corrupt") from error

    def save(self, record: _PushReceiptRecord) -> None:
        encoded = record.model_dump_json()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT receipt_json FROM source_control_push_receipts WHERE command_id = ?",
                (record.command_id,),
            ).fetchone()
            if row is not None:
                try:
                    existing = _PushReceiptRecord.model_validate_json(row[0], strict=True)
                except Exception as error:
                    raise GitPortError("push receipt store is corrupt") from error
                if existing != record:
                    raise GitPortError("push command receipt conflicts with existing binding")
                return
            connection.execute(
                "INSERT INTO source_control_push_receipts(command_id, receipt_json) VALUES (?, ?)",
                (record.command_id, encoded),
            )

    def _connect(self) -> sqlite3.Connection:
        try:
            self._database.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self._database, timeout=5.0)
            connection.execute(
                "CREATE TABLE IF NOT EXISTS source_control_push_receipts("
                "command_id TEXT PRIMARY KEY NOT NULL, "
                "receipt_json TEXT NOT NULL)"
            )
            return connection
        except sqlite3.Error as error:
            raise GitPortError("push receipt store is unavailable") from error


class MaintenanceTransactionReceipt(StrictModel):
    accepted: bool
    code: NonEmptyStr
    merge: GitReceipt | None
    verification: GitReceipt | None
    revert: GitReceipt | None


class _FileMergeLock(AbstractContextManager["_FileMergeLock"]):
    """One non-blocking cross-process lock stored below LocalAppData."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._stream: object | None = None

    def __enter__(self) -> _FileMergeLock:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        stream = self._path.open("a+b")
        try:
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:  # pragma: no cover - Windows is the supported operator host
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            stream.close()
            raise BlockingIOError("maintenance merge lock is held") from None
        self._stream = stream
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: object | None,
    ) -> None:
        del exception_type, exception, traceback
        stream = self._stream
        self._stream = None
        if stream is None:
            return
        try:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover - Windows is the supported operator host
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()


class LocalGitPort:
    """Execute only fixed local Git operations with bounded direct arguments."""

    def __init__(
        self,
        repository_root: Path,
        *,
        worktree_root: Path,
        allowed_verification_commands: Sequence[VerificationCommand] = (),
        runner: ProcessRunner = run_bounded_process,
        merge_lock_factory: Callable[[], MergeLock] | None = None,
        push_enabled: bool = False,
        push_remote: str | None = None,
        push_destination: str | None = None,
        push_receipt_database: Path | None = None,
    ) -> None:
        self._repository_root = repository_root.resolve(strict=True)
        if not self._repository_root.is_dir():
            raise ValueError("repository root must be a directory")
        self._worktree_root = worktree_root.resolve(strict=False)
        if (
            self._worktree_root == self._repository_root
            or self._worktree_root.is_relative_to(self._repository_root)
            or self._repository_root.is_relative_to(self._worktree_root)
        ):
            raise ValueError("worktree root must be disjoint from repository")
        self._runner = runner
        self._allowed_verification_commands = frozenset(
            (command.name, command.argv) for command in allowed_verification_commands
        )
        self._push_enabled = push_enabled
        self._push_remote = self._safe_push_argument(push_remote, "push remote")
        self._push_destination = self._safe_push_destination(push_destination)
        if push_enabled != (self._push_remote is not None and self._push_destination is not None):
            raise ValueError("push configuration must be complete exactly when enabled")
        if not push_enabled and push_receipt_database is not None:
            raise ValueError("push receipt database requires enabled push")
        if push_enabled:
            receipt_database = (
                _default_push_receipt_database()
                if push_receipt_database is None
                else push_receipt_database.resolve(strict=False)
            )
            if receipt_database.is_relative_to(self._repository_root):
                raise ValueError("push receipt database must be outside repository")
            self._push_receipts: _PushReceiptStore | None = _PushReceiptStore(receipt_database)
        else:
            self._push_receipts = None
        if merge_lock_factory is None:
            lock_path = _default_merge_lock_path()
            self._merge_lock_factory = lambda: _FileMergeLock(lock_path)
        else:
            self._merge_lock_factory = merge_lock_factory

    def available(self, command_type: CommandType) -> CapabilityView:
        if command_type != "source-control.push":
            return CapabilityView(
                capability_id=command_type,
                state=CapabilityState.DISABLED,
                reason="Unsupported source-control command.",
            )
        try:
            self.status()
        except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
            return CapabilityView(
                capability_id="source-control.push",
                state=CapabilityState.DISABLED,
                reason="The local Git repository health check failed.",
            )
        if not self._push_enabled:
            return CapabilityView(
                capability_id="source-control.push",
                state=CapabilityState.DISABLED,
                reason="Source-control push is not configured.",
            )
        if self._validated_push_target() is None:
            return CapabilityView(
                capability_id="source-control.push",
                state=CapabilityState.DISABLED,
                reason="Source-control remote configuration is unsafe.",
            )
        return CapabilityView(
            capability_id="source-control.push",
            state=CapabilityState.ENABLED,
        )

    def status(self) -> RepositoryStatus:
        return self._status_at(self._repository_root)

    def _status_at(self, worktree: Path) -> RepositoryStatus:
        revision = self._resolve_commit("HEAD", worktree)
        result = self._git(
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            cwd=worktree,
        )
        if result.returncode != 0:
            raise GitPortError("repository status failed")
        return RepositoryStatus(revision=revision, clean=not result.stdout)

    def create_worktree(self, request: WorktreeRequest) -> GitReceipt:
        if not self._safe_worktree_target(request.path):
            return self._reject("create-worktree", "unsafe-worktree-path")
        try:
            with self._merge_lock_factory():
                return self._create_worktree_locked(request)
        except (BlockingIOError, OSError):
            return self._reject("create-worktree", "worktree-lock-held")

    def _create_worktree_locked(self, request: WorktreeRequest) -> GitReceipt:
        if not self._safe_worktree_target(request.path):
            return self._reject("create-worktree", "unsafe-worktree-path")
        try:
            status = self.status()
            start_revision = self._resolve_commit(request.start_revision, self._repository_root)
            branch_revision = self._branch_revision(request.branch)
        except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
            return self._reject("create-worktree", "repository-state-unavailable")
        if not status.clean:
            return self._reject("create-worktree", "main-not-clean")
        if status.revision != start_revision:
            return self._reject("create-worktree", "base-revision-mismatch")
        if branch_revision is not None:
            return self._reject("create-worktree", "worktree-branch-exists")
        try:
            result = self._git(
                "worktree",
                "add",
                "-b",
                request.branch,
                "--",
                str(request.path),
                start_revision,
                cwd=self._repository_root,
                timeout=_COMMAND_TIMEOUT_SECONDS,
            )
        except (BoundedProcessError, OSError, subprocess.TimeoutExpired):
            result = None
        if result is None or result.returncode != 0:
            cleanup_succeeded = self._cleanup_created_worktree(
                request.path,
                request.branch,
                start_revision,
            )
            return self._reject(
                "create-worktree",
                (
                    "worktree-create-failed"
                    if cleanup_succeeded
                    else "worktree-create-failed-cleanup-failed"
                ),
            )
        try:
            created_revision = self._resolve_commit("HEAD", request.path)
            created_status = self._status_at(request.path)
            created_branch = self._branch_revision(request.branch)
            verified = (
                self._safe_existing_worktree(request.path)
                and created_revision == start_revision
                and created_status.clean
                and created_status.revision == start_revision
                and created_branch == start_revision
            )
        except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
            created_revision = None
            verified = False
        if not verified:
            cleanup_succeeded = self._cleanup_created_worktree(
                request.path,
                request.branch,
                start_revision,
            )
            return self._reject(
                "create-worktree",
                (
                    "worktree-verification-failed"
                    if cleanup_succeeded
                    else "worktree-verification-failed-cleanup-failed"
                ),
                revision=created_revision,
            )
        assert created_revision is not None
        return GitReceipt(
            operation="create-worktree",
            accepted=True,
            code="worktree-created",
            revision=created_revision,
            diff_hash=None,
        )

    def _cleanup_created_worktree(
        self,
        target: Path,
        branch: str,
        start_revision: str,
    ) -> bool:
        if not self._worktree_path_is_contained(target):
            return False
        target_clean = self._remove_worktree_target(target)
        try:
            branch_revision = self._branch_revision(branch)
        except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
            return False
        if branch_revision is None:
            return target_clean
        if not target_clean or branch_revision != start_revision:
            return False
        try:
            deleted = self._git(
                "branch",
                "-D",
                "--",
                branch,
                cwd=self._repository_root,
                timeout=_COMMAND_TIMEOUT_SECONDS,
            )
            return deleted.returncode == 0 and self._branch_revision(branch) is None
        except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
            return False

    def verify(self, request: VerificationRequest) -> GitReceipt:
        return self._verify_unlocked(request, expected_revision=None)

    def _verify_unlocked(
        self,
        request: VerificationRequest,
        *,
        expected_revision: str | None,
    ) -> GitReceipt:
        if not self._safe_existing_worktree(request.worktree):
            return self._reject("verify", "unsafe-verification-worktree")
        if not request.commands:
            return self._reject("verify", "verification-empty")
        try:
            initial_status = self._status_at(request.worktree)
        except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
            return self._reject("verify", "verification-state-unavailable")
        revision = initial_status.revision
        if expected_revision is not None and revision != expected_revision:
            return self._reject(
                "verify",
                "verification-revision-mismatch",
                revision=revision,
            )
        if not initial_status.clean:
            return self._reject(
                "verify",
                "verification-worktree-not-clean",
                revision=revision,
            )
        for command in request.commands:
            if (command.name, command.argv) not in self._allowed_verification_commands:
                return self._reject(
                    "verify",
                    "verification-command-not-allowed",
                    revision=revision,
                    failed_check=command.name,
                )
            try:
                result = self._run(
                    command.argv,
                    cwd=request.worktree,
                    timeout=_COMMAND_TIMEOUT_SECONDS,
                    max_output_bytes=_METADATA_OUTPUT_LIMIT,
                )
            except (BoundedProcessError, OSError, subprocess.TimeoutExpired):
                return self._reject(
                    "verify",
                    "verification-failed",
                    revision=revision,
                    failed_check=command.name,
                )
            if result.returncode != 0:
                return self._reject(
                    "verify",
                    "verification-failed",
                    revision=revision,
                    failed_check=command.name,
                )
        try:
            final_status = self._status_at(request.worktree)
            if final_status.revision != revision or (
                expected_revision is not None and final_status.revision != expected_revision
            ):
                return self._reject(
                    "verify",
                    "verification-revision-changed",
                    revision=final_status.revision,
                )
        except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
            return self._reject("verify", "verification-state-unavailable")
        if not final_status.clean:
            return self._reject(
                "verify",
                "verification-worktree-changed",
                revision=revision,
            )
        return GitReceipt(
            operation="verify",
            accepted=True,
            code="verification-passed",
            revision=revision,
            diff_hash=None,
        )

    def diff_hash(self, base_revision: str, candidate_revision: str) -> str:
        base = self._resolve_commit(base_revision, self._repository_root)
        candidate = self._resolve_commit(candidate_revision, self._repository_root)
        result = self._git(
            "diff",
            "--binary",
            "--full-index",
            "--no-ext-diff",
            f"{base}..{candidate}",
            "--",
            cwd=self._repository_root,
            max_output_bytes=_DIFF_OUTPUT_LIMIT,
        )
        if result.returncode != 0:
            raise GitPortError("review diff could not be read")
        return hashlib.sha256(result.stdout).hexdigest()

    def changed_paths(self, base_revision: str, candidate_revision: str) -> tuple[str, ...]:
        base = self._resolve_commit(base_revision, self._repository_root)
        candidate = self._resolve_commit(candidate_revision, self._repository_root)
        return self._changed_paths(base, candidate)

    def merge_no_ff(self, request: MergeRequest) -> GitReceipt:
        if not self._request_repository_matches(request):
            return self._reject("merge-no-ff", "repository-root-mismatch")
        try:
            with self._merge_lock_factory():
                return self._merge_locked(request)
        except (BlockingIOError, OSError):
            return self._reject("merge-no-ff", "merge-lock-held")

    def merge_verify_revert(
        self,
        request: MergeRequest,
        post_merge_verification: VerificationRequest,
    ) -> MaintenanceTransactionReceipt:
        if not self._request_repository_matches(request):
            return self._transaction_reject("repository-root-mismatch")
        if not self._safe_worktree_target(post_merge_verification.worktree):
            return self._transaction_reject("unsafe-post-merge-verification-worktree")
        try:
            with self._merge_lock_factory():
                if not self._safe_worktree_target(post_merge_verification.worktree):
                    return self._transaction_reject("unsafe-post-merge-verification-worktree")
                merged = self._merge_locked(request)
                if not merged.accepted or merged.revision is None:
                    if (
                        merged.revision is not None
                        and merged.revision != request.expected_base_revision
                    ):
                        reverted = self._revert_locked(merged.revision)
                        return MaintenanceTransactionReceipt(
                            accepted=False,
                            code=(
                                f"{merged.code}-"
                                f"{'reverted' if reverted.accepted else 'revert-failed'}"
                            ),
                            merge=merged,
                            verification=None,
                            revert=reverted,
                        )
                    return MaintenanceTransactionReceipt(
                        accepted=False,
                        code=merged.code,
                        merge=merged,
                        verification=None,
                        revert=None,
                    )
                verified, setup_succeeded, cleanup_succeeded = self._verify_in_detached_worktree(
                    post_merge_verification,
                    expected_revision=merged.revision,
                )
                try:
                    main_status = self.status()
                    main_matches_merge = (
                        main_status.clean and main_status.revision == merged.revision
                    )
                except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
                    main_matches_merge = False
                if (
                    verified.accepted
                    and verified.revision == merged.revision
                    and setup_succeeded
                    and cleanup_succeeded
                    and main_matches_merge
                ):
                    return MaintenanceTransactionReceipt(
                        accepted=True,
                        code="maintenance-merged",
                        merge=merged,
                        verification=verified,
                        revert=None,
                    )
                failure = self._post_merge_failure_code(
                    verified,
                    expected_revision=merged.revision,
                    setup_succeeded=setup_succeeded,
                    cleanup_succeeded=cleanup_succeeded,
                    main_matches_merge=main_matches_merge,
                )
                reverted = self._revert_locked(merged.revision)
                code = f"{failure}-{'reverted' if reverted.accepted else 'revert-failed'}"
                return MaintenanceTransactionReceipt(
                    accepted=False,
                    code=code,
                    merge=merged,
                    verification=verified,
                    revert=reverted,
                )
        except (BlockingIOError, OSError):
            return self._transaction_reject("merge-lock-held")

    def _verify_in_detached_worktree(
        self,
        request: VerificationRequest,
        *,
        expected_revision: str,
    ) -> tuple[GitReceipt, bool, bool]:
        target = request.worktree
        try:
            created = self._git(
                "worktree",
                "add",
                "--detach",
                "--",
                str(target),
                expected_revision,
                cwd=self._repository_root,
                timeout=_COMMAND_TIMEOUT_SECONDS,
            )
        except (BoundedProcessError, OSError, subprocess.TimeoutExpired):
            created = None
        if created is None or created.returncode != 0:
            cleanup_succeeded = self._remove_verification_worktree(target)
            return (
                self._reject(
                    "verify",
                    "verification-worktree-create-failed",
                    revision=expected_revision,
                ),
                False,
                cleanup_succeeded,
            )
        try:
            verified = self._verify_unlocked(request, expected_revision=expected_revision)
        except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
            verified = self._reject(
                "verify",
                "verification-state-unavailable",
                revision=expected_revision,
            )
        finally:
            cleanup_succeeded = self._remove_verification_worktree(target)
        return verified, True, cleanup_succeeded

    def _remove_verification_worktree(self, target: Path) -> bool:
        return self._remove_worktree_target(target)

    def _remove_worktree_target(self, target: Path) -> bool:
        if not self._worktree_path_is_contained(target):
            return False
        try:
            registered = self._worktree_target_registered(target)
            if not _path_exists_or_reparse(target) and not registered:
                return True
            removed = self._git(
                "worktree",
                "remove",
                "--force",
                "--",
                str(target),
                cwd=self._repository_root,
                timeout=_COMMAND_TIMEOUT_SECONDS,
            )
        except (
            BoundedProcessError,
            GitPortError,
            OSError,
            subprocess.TimeoutExpired,
        ):
            return False
        try:
            still_registered = self._worktree_target_registered(target)
        except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
            return False
        return (
            removed.returncode == 0 and not _path_exists_or_reparse(target) and not still_registered
        )

    def _worktree_target_registered(self, target: Path) -> bool:
        result = self._git(
            "worktree",
            "list",
            "--porcelain",
            "-z",
            cwd=self._repository_root,
        )
        if result.returncode != 0:
            raise GitPortError("worktree metadata is unavailable")
        target_resolved = target.resolve(strict=False)
        for field in result.stdout.split(b"\x00"):
            if not field.startswith(b"worktree "):
                continue
            try:
                listed = Path(field.removeprefix(b"worktree ").decode("utf-8", errors="strict"))
                if listed.resolve(strict=False) == target_resolved:
                    return True
            except (OSError, UnicodeDecodeError) as error:
                raise GitPortError("worktree metadata is malformed") from error
        return False

    @staticmethod
    def _post_merge_failure_code(
        verified: GitReceipt,
        *,
        expected_revision: str,
        setup_succeeded: bool,
        cleanup_succeeded: bool,
        main_matches_merge: bool,
    ) -> str:
        if not setup_succeeded:
            return (
                "post-merge-verification-setup-failed"
                if cleanup_succeeded
                else "post-merge-verification-setup-and-cleanup-failed"
            )
        if not cleanup_succeeded:
            return (
                "post-merge-verification-cleanup-failed"
                if verified.accepted
                else "post-merge-verification-and-cleanup-failed"
            )
        if not main_matches_merge:
            return "post-merge-main-state-invalid"
        if verified.accepted and verified.revision != expected_revision:
            return "post-merge-verification-revision-mismatch"
        return "post-merge-verification-failed"

    def _merge_locked(self, request: MergeRequest) -> GitReceipt:
        try:
            status = self.status()
        except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
            return self._reject("merge-no-ff", "repository-state-unavailable")
        if not status.clean:
            return self._reject("merge-no-ff", "main-not-clean", revision=status.revision)
        if status.revision != request.expected_base_revision:
            return self._reject("merge-no-ff", "base-revision-mismatch", revision=status.revision)
        if request.rollback_revision != status.revision:
            return self._reject(
                "merge-no-ff", "rollback-revision-mismatch", revision=status.revision
            )
        try:
            candidate = self._resolve_commit(request.candidate_revision, self._repository_root)
            ancestry = self._git(
                "merge-base",
                "--is-ancestor",
                status.revision,
                candidate,
                cwd=self._repository_root,
            )
            if ancestry.returncode != 0 or candidate == status.revision:
                return self._reject("merge-no-ff", "candidate-not-based-on-current-main")
            changed_paths = self._changed_paths(status.revision, candidate)
            current_diff_hash = self.diff_hash(status.revision, candidate)
        except (GitPortError, OSError, BoundedProcessError, subprocess.TimeoutExpired):
            return self._reject("merge-no-ff", "candidate-state-unavailable")
        if changed_paths != request.changed_paths:
            return self._reject(
                "merge-no-ff",
                "changed-paths-mismatch",
                revision=status.revision,
                diff_hash=current_diff_hash,
            )
        try:
            if not self._candidate_tree_is_safe(candidate, changed_paths):
                return self._reject(
                    "merge-no-ff",
                    "unsafe-candidate-tree-entry",
                    revision=status.revision,
                    diff_hash=current_diff_hash,
                )
        except (GitPortError, OSError, BoundedProcessError, subprocess.TimeoutExpired):
            return self._reject("merge-no-ff", "candidate-state-unavailable")
        if current_diff_hash != request.reviewed_diff_hash:
            return self._reject(
                "merge-no-ff",
                "reviewed-diff-mismatch",
                revision=status.revision,
                diff_hash=current_diff_hash,
            )
        try:
            self._git(
                "merge",
                "--no-ff",
                "--no-edit",
                candidate,
                cwd=self._repository_root,
                timeout=_COMMAND_TIMEOUT_SECONDS,
            )
        except (BoundedProcessError, OSError, subprocess.TimeoutExpired):
            pass
        try:
            merge_revision = self._resolve_commit("HEAD", self._repository_root)
        except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
            return self._reject("merge-no-ff", "merge-failed-manual-recovery-required")
        try:
            parents = self._commit_parents(merge_revision)
        except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
            return self._reject(
                "merge-no-ff",
                "merge-failed-manual-recovery-required",
                revision=(merge_revision if merge_revision != status.revision else None),
                diff_hash=current_diff_hash,
            )
        if merge_revision == status.revision:
            try:
                unchanged = self.status()
            except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
                return self._reject(
                    "merge-no-ff",
                    "merge-failed-manual-recovery-required",
                )
            return self._reject(
                "merge-no-ff",
                (
                    "merge-failed"
                    if unchanged.clean and unchanged.revision == status.revision
                    else "merge-failed-manual-recovery-required"
                ),
            )
        if parents != (status.revision, candidate):
            return self._reject(
                "merge-no-ff",
                "merge-failed-manual-recovery-required",
                revision=merge_revision,
                diff_hash=current_diff_hash,
            )
        try:
            final_status = self.status()
        except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
            return self._reject(
                "merge-no-ff",
                "merge-verification-failed-manual-recovery-required",
                revision=merge_revision,
                diff_hash=current_diff_hash,
            )
        if final_status.revision != merge_revision or not final_status.clean:
            return self._reject(
                "merge-no-ff",
                "merge-verification-failed-manual-recovery-required",
                revision=merge_revision,
                diff_hash=current_diff_hash,
            )
        return GitReceipt(
            operation="merge-no-ff",
            accepted=True,
            code="merge-completed",
            revision=merge_revision,
            diff_hash=current_diff_hash,
        )

    def revert(self, commit: str) -> GitReceipt:
        try:
            with self._merge_lock_factory():
                return self._revert_locked(commit)
        except (BlockingIOError, OSError):
            return self._reject("revert", "merge-lock-held")

    def _revert_locked(self, commit: str) -> GitReceipt:
        try:
            status = self.status()
            target = self._resolve_commit(commit, self._repository_root)
        except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
            return self._reject("revert", "repository-state-unavailable")
        if not status.clean:
            return self._reject("revert", "main-not-clean", revision=status.revision)
        if target != status.revision:
            return self._reject("revert", "revert-target-not-head", revision=status.revision)
        try:
            parents = self._commit_parents(target)
            if len(parents) != 2:
                return self._reject("revert", "revert-target-not-merge")
            first_parent_tree = self._resolve_tree(parents[0])
        except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
            return self._reject("revert", "revert-target-not-merge")
        try:
            self._git(
                "revert",
                "--no-edit",
                "-m",
                "1",
                target,
                cwd=self._repository_root,
                timeout=_COMMAND_TIMEOUT_SECONDS,
            )
        except (BoundedProcessError, OSError, subprocess.TimeoutExpired):
            pass
        try:
            final = self.status()
            final_parents = self._commit_parents(final.revision)
            final_tree = self._resolve_tree(final.revision)
        except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
            return self._reject(
                "revert",
                "revert-failed-manual-recovery-required",
            )
        if (
            final.clean
            and final.revision != target
            and final_parents == (target,)
            and final_tree == first_parent_tree
        ):
            return GitReceipt(
                operation="revert",
                accepted=True,
                code="revert-completed",
                revision=final.revision,
                diff_hash=None,
            )
        if final.clean and final.revision == target:
            return self._reject(
                "revert",
                "revert-failed",
                revision=target,
            )
        return self._reject(
            "revert",
            "revert-verification-failed-manual-recovery-required",
            revision=final.revision,
        )

    def _changed_paths(self, base_revision: str, candidate_revision: str) -> tuple[str, ...]:
        result = self._git(
            "diff",
            "--name-only",
            "--no-renames",
            "-z",
            "--diff-filter=ACDMRTUXB",
            f"{base_revision}..{candidate_revision}",
            "--",
            cwd=self._repository_root,
            max_output_bytes=_METADATA_OUTPUT_LIMIT,
        )
        if result.returncode != 0 or (result.stdout and not result.stdout.endswith(b"\x00")):
            raise GitPortError("changed paths could not be read")
        raw_paths = result.stdout.split(b"\x00")
        if raw_paths and raw_paths[-1] == b"":
            raw_paths.pop()
        try:
            paths = tuple(path.decode("utf-8", errors="strict") for path in raw_paths)
        except UnicodeDecodeError as error:
            raise GitPortError("changed paths were not UTF-8") from error
        if not paths or len(paths) > 256 or tuple(sorted(set(paths))) != paths:
            raise GitPortError("changed paths were empty, duplicate, unsorted, or excessive")
        return paths

    def _candidate_tree_is_safe(
        self, candidate_revision: str, changed_paths: tuple[str, ...]
    ) -> bool:
        result = self._git(
            "ls-tree",
            "-z",
            candidate_revision,
            "--",
            *changed_paths,
            cwd=self._repository_root,
            max_output_bytes=_METADATA_OUTPUT_LIMIT,
        )
        if result.returncode != 0 or (result.stdout and not result.stdout.endswith(b"\x00")):
            raise GitPortError("candidate tree entries could not be read")
        requested = set(changed_paths)
        seen: set[str] = set()
        for record in result.stdout.split(b"\x00"):
            if not record:
                continue
            try:
                metadata, raw_path = record.split(b"\t", 1)
                mode, object_type, _object_id = metadata.split(b" ", 2)
                path = raw_path.decode("utf-8", errors="strict")
            except (UnicodeDecodeError, ValueError) as error:
                raise GitPortError("candidate tree entry was malformed") from error
            if path not in requested or path in seen:
                raise GitPortError("candidate tree entry did not match the changed paths")
            seen.add(path)
            if mode not in {b"100644", b"100755"} or object_type != b"blob":
                return False
        return True

    def push(
        self,
        command_id: str,
        expected_revision: str,
        confirmation: ConfirmationProof,
    ) -> GitReceipt:
        if type(command_id) is not str or _SAFE_ID_PATTERN.fullmatch(command_id) is None:
            return self._reject("push", "push-command-invalid")
        if not self._push_enabled:
            return self._reject("push", "push-disabled", command_id=command_id)
        if type(confirmation) is not ConfirmationProof or not confirmation.first_confirmed:
            return self._reject("push", "push-confirmation-missing", command_id=command_id)
        if not _is_full_git_revision(expected_revision):
            return self._reject("push", "push-revision-mismatch", command_id=command_id)
        try:
            with self._merge_lock_factory():
                return self._push_locked(command_id, expected_revision)
        except (BlockingIOError, OSError):
            return self._reject("push", "merge-lock-held", command_id=command_id)

    def _push_locked(self, command_id: str, expected_revision: str) -> GitReceipt:
        if (
            self._push_remote is None
            or self._push_destination is None
            or self._push_receipts is None
        ):
            return self._reject("push", "push-disabled", command_id=command_id)
        try:
            existing = self._push_receipts.load(command_id)
        except (GitPortError, OSError, sqlite3.Error):
            return self._reject("push", "push-receipt-unavailable", command_id=command_id)
        if existing is not None:
            push_target = self._validated_push_target()
            if push_target is None:
                return self._reject("push", "push-remote-unsafe", command_id=command_id)
            if self._push_record_matches(
                existing,
                command_id,
                expected_revision,
                push_target,
            ):
                return existing.receipt
            return self._reject("push", "push-command-conflict", command_id=command_id)
        try:
            status = self.status()
        except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
            return self._reject("push", "repository-state-unavailable", command_id=command_id)
        if not status.clean:
            return self._reject(
                "push",
                "main-not-clean",
                revision=status.revision,
                command_id=command_id,
            )
        if status.revision != expected_revision:
            return self._reject(
                "push",
                "push-revision-mismatch",
                revision=status.revision,
                command_id=command_id,
            )
        push_target = self._validated_push_target()
        if push_target is None:
            return self._reject("push", "push-remote-unsafe", command_id=command_id)
        remote_state = self._remote_destination_state(push_target, expected_revision)
        if remote_state == "unavailable":
            return self._reject(
                "push",
                "push-remote-state-unavailable",
                revision=status.revision,
                command_id=command_id,
            )
        if remote_state != "exact":
            if not self._url_rewrites_absent():
                return self._reject(
                    "push",
                    "push-remote-unsafe",
                    revision=status.revision,
                    command_id=command_id,
                )
            try:
                result = self._git(
                    "push",
                    "--porcelain",
                    "--no-verify",
                    "--no-follow-tags",
                    "--no-recurse-submodules",
                    "--no-push-option",
                    "--",
                    push_target,
                    f"{expected_revision}:{self._push_destination}",
                    cwd=self._repository_root,
                    timeout=_COMMAND_TIMEOUT_SECONDS,
                )
            except (BoundedProcessError, OSError, subprocess.TimeoutExpired):
                result = None
            remote_state = self._remote_destination_state(push_target, expected_revision)
            if remote_state != "exact":
                return self._reject(
                    "push",
                    (
                        "push-remote-verification-failed"
                        if result is not None and result.returncode == 0
                        else "push-failed"
                    ),
                    revision=status.revision,
                    command_id=command_id,
                )
        try:
            final = self.status()
            local_state_verified = final.clean and final.revision == status.revision
        except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
            local_state_verified = False
        receipt = GitReceipt(
            operation="push",
            accepted=True,
            code=(
                "push-completed"
                if local_state_verified
                else "push-completed-local-verification-degraded"
            ),
            revision=status.revision,
            diff_hash=None,
            command_id=command_id,
        )
        try:
            self._push_receipts.save(
                _PushReceiptRecord(
                    command_id=command_id,
                    expected_revision=expected_revision,
                    push_remote=self._push_remote,
                    push_target=push_target,
                    push_destination=self._push_destination,
                    receipt=receipt,
                )
            )
        except (GitPortError, OSError, sqlite3.Error):
            return GitReceipt(
                operation="push",
                accepted=True,
                code="push-completed-receipt-persistence-degraded",
                revision=status.revision,
                diff_hash=None,
                command_id=command_id,
            )
        return receipt

    def recover(self, command_id: str, request: CommandRequest) -> str:
        if (
            type(command_id) is not str
            or _SAFE_ID_PATTERN.fullmatch(command_id) is None
            or type(request) is not CommandRequest
            or request.command_id != command_id
            or request.command_type != "source-control.push"
            or type(request.payload) is not SourceControlPushPayload
            or request.confirmation is None
            or not request.confirmation.first_confirmed
            or self._push_receipts is None
        ):
            return "unknown"
        try:
            with self._merge_lock_factory():
                record = self._push_receipts.load(command_id)
                push_target = self._validated_push_target()
                if push_target is None:
                    return "unknown"
                if record is None:
                    state = self._remote_destination_state(
                        push_target,
                        request.payload.expected_revision,
                    )
                    if state == "missing":
                        return "not-started"
                    if state == "different":
                        return "failed"
                    if (
                        state != "exact"
                        or self._push_remote is None
                        or self._push_destination is None
                    ):
                        return "unknown"
                    receipt = GitReceipt(
                        operation="push",
                        accepted=True,
                        code="push-completed",
                        revision=request.payload.expected_revision,
                        diff_hash=None,
                        command_id=command_id,
                    )
                    self._push_receipts.save(
                        _PushReceiptRecord(
                            command_id=command_id,
                            expected_revision=request.payload.expected_revision,
                            push_remote=self._push_remote,
                            push_target=push_target,
                            push_destination=self._push_destination,
                            receipt=receipt,
                        )
                    )
                    return "completed"
        except (BlockingIOError, GitPortError, OSError, sqlite3.Error):
            return "unknown"
        return (
            "completed"
            if self._push_record_matches(
                record,
                command_id,
                request.payload.expected_revision,
                push_target,
            )
            else "unknown"
        )

    def _push_record_matches(
        self,
        record: _PushReceiptRecord,
        command_id: str,
        expected_revision: str,
        push_target: str,
    ) -> bool:
        return (
            self._push_remote is not None
            and self._push_destination is not None
            and record.command_id == command_id
            and record.expected_revision == expected_revision
            and record.push_remote == self._push_remote
            and record.push_target == push_target
            and record.push_destination == self._push_destination
        )

    def _resolve_commit(self, revision: str, cwd: Path) -> str:
        result = self._git(
            "rev-parse",
            "--verify",
            f"{revision}^{{commit}}",
            cwd=cwd,
        )
        if result.returncode != 0:
            raise GitPortError("Git revision is unavailable")
        resolved = self._decode(result.stdout).strip()
        if len(resolved) not in (40, 64) or any(
            character not in "0123456789abcdef" for character in resolved
        ):
            raise GitPortError("Git returned an invalid revision")
        if revision != "HEAD" and resolved != revision:
            raise GitPortError("Git revision does not resolve exactly")
        return resolved

    def _branch_revision(self, branch: str) -> str | None:
        result = self._git(
            "rev-parse",
            "--verify",
            "--quiet",
            f"refs/heads/{branch}^{{commit}}",
            cwd=self._repository_root,
        )
        if result.returncode == 1 and not result.stdout:
            return None
        if result.returncode != 0:
            raise GitPortError("branch state is unavailable")
        revision = self._decode(result.stdout).strip()
        if not _is_full_git_revision(revision):
            raise GitPortError("branch revision is invalid")
        return revision

    def _commit_parents(self, revision: str) -> tuple[str, ...]:
        result = self._git(
            "rev-list",
            "--parents",
            "-n",
            "1",
            revision,
            cwd=self._repository_root,
        )
        fields = self._decode(result.stdout).strip().split()
        if (
            result.returncode != 0
            or not fields
            or fields[0] != revision
            or any(not _is_full_git_revision(field) for field in fields)
        ):
            raise GitPortError("commit parents are unavailable")
        return tuple(fields[1:])

    def _resolve_tree(self, revision: str) -> str:
        result = self._git(
            "rev-parse",
            "--verify",
            f"{revision}^{{tree}}",
            cwd=self._repository_root,
        )
        tree = self._decode(result.stdout).strip()
        if result.returncode != 0 or not _is_full_git_revision(tree):
            raise GitPortError("commit tree is unavailable")
        return tree

    def _git(
        self,
        *arguments: str,
        cwd: Path,
        timeout: float = _METADATA_TIMEOUT_SECONDS,
        max_output_bytes: int = _METADATA_OUTPUT_LIMIT,
    ) -> subprocess.CompletedProcess[bytes]:
        return self._run(
            ("git", "-C", str(cwd), *arguments),
            cwd=cwd,
            timeout=timeout,
            max_output_bytes=max_output_bytes,
        )

    def _run(
        self,
        command: tuple[str, ...],
        *,
        cwd: Path,
        timeout: float,
        max_output_bytes: int,
    ) -> subprocess.CompletedProcess[bytes]:
        return self._runner(
            command,
            max_output_bytes=max_output_bytes,
            cwd=cwd,
            timeout=timeout,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=_safe_process_environment(),
        )

    def _safe_worktree_target(self, path: Path) -> bool:
        return not _path_exists_or_reparse(path) and self._worktree_path_is_contained(path)

    def _worktree_path_is_contained(self, path: Path) -> bool:
        if ".." in path.parts or _is_link_or_reparse(path):
            return False
        try:
            resolved = path.resolve(strict=False)
            resolved.relative_to(self._worktree_root)
        except (OSError, ValueError):
            return False
        return resolved != self._worktree_root and not _has_reparse_component(
            path.parent, self._worktree_root
        )

    def _request_repository_matches(self, request: MergeRequest) -> bool:
        return self._is_exact_repository_path(request.repository_root)

    def _is_exact_repository_path(self, path: Path) -> bool:
        try:
            return not path.is_symlink() and path.resolve(strict=True) == self._repository_root
        except OSError:
            return False

    def _safe_existing_worktree(self, path: Path) -> bool:
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            return False
        allowed = resolved.is_relative_to(self._worktree_root)
        if not allowed or not resolved.is_dir() or _is_link_or_reparse(path):
            return False
        if _has_reparse_component(path, self._worktree_root):
            return False
        try:
            result = self._git("rev-parse", "--show-toplevel", cwd=resolved)
            top_level = Path(self._decode(result.stdout).strip()).resolve(strict=True)
        except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0 and top_level == resolved

    @staticmethod
    def _safe_push_argument(value: str | None, label: str) -> str | None:
        if value is None:
            return None
        if not value or any(character in value for character in ("\x00", "\r", "\n")):
            raise ValueError(f"{label} is unsafe")
        path = Path(value)
        if path.is_absolute():
            return str(path.resolve(strict=False))
        if "::" in value or _PUSH_REMOTE_NAME_PATTERN.fullmatch(value) is None:
            raise ValueError(f"{label} is unsafe")
        return value

    def _validated_push_target(self) -> str | None:
        remote = self._push_remote
        if remote is None or not self._url_rewrites_absent():
            return None
        remote_path = Path(remote)
        if remote_path.is_absolute():
            return self._validated_remote_url(remote)
        try:
            result = self._git(
                "remote",
                "get-url",
                "--push",
                "--all",
                remote,
                cwd=self._repository_root,
            )
            urls = self._decode(result.stdout).splitlines()
        except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0 or len(urls) != 1:
            return None
        return self._validated_remote_url(urls[0])

    def _validated_remote_url(self, value: str) -> str | None:
        if (
            not value
            or len(value) > 4096
            or any(character in value for character in ("\x00", "\r", "\n"))
            or "::" in value
            or value.startswith("-")
        ):
            return None
        path = Path(value)
        is_network_url = (
            "://" in value
            or re.fullmatch(
                r"(?:[^/@:\s]+@)?[^/:\s]+:[^\\\s].+",
                value,
            )
            is not None
        )
        if is_network_url:
            return value
        resolved = (
            path.resolve(strict=False)
            if path.is_absolute()
            else (self._repository_root / path).resolve(strict=False)
        )
        if not resolved.exists() or not resolved.is_dir() or _is_link_or_reparse(resolved):
            return None
        return str(resolved)

    def _remote_destination_state(self, push_target: str, expected_revision: str) -> str:
        if self._push_destination is None or not self._url_rewrites_absent():
            return "unavailable"
        try:
            result = self._git(
                "ls-remote",
                "--exit-code",
                "--refs",
                push_target,
                self._push_destination,
                cwd=self._repository_root,
                timeout=_COMMAND_TIMEOUT_SECONDS,
            )
            output = self._decode(result.stdout)
        except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
            return "unavailable"
        if result.returncode == 2 and not output:
            return "missing"
        lines = output.splitlines()
        if result.returncode != 0 or len(lines) != 1:
            return "unavailable"
        fields = lines[0].split("\t")
        if (
            len(fields) != 2
            or not _is_full_git_revision(fields[0])
            or fields[1] != self._push_destination
        ):
            return "unavailable"
        return "exact" if fields[0] == expected_revision else "different"

    def _url_rewrites_absent(self) -> bool:
        try:
            result = self._git(
                "config",
                "--get-regexp",
                r"^url\..*\.(insteadof|pushinsteadof)$",
                cwd=self._repository_root,
            )
        except (BoundedProcessError, GitPortError, OSError, subprocess.TimeoutExpired):
            return False
        if result.returncode == 1 and not result.stdout:
            return True
        return False

    @staticmethod
    def _safe_push_destination(value: str | None) -> str | None:
        if value is None:
            return None
        branch_parts = value.removeprefix("refs/heads/").split("/")
        if (
            _PUSH_DESTINATION_PATTERN.fullmatch(value) is None
            or ".." in value
            or any(part.endswith((".", ".lock")) for part in branch_parts)
        ):
            raise ValueError("push destination must be one non-force branch ref")
        return value

    @staticmethod
    def _decode(value: bytes) -> str:
        try:
            return value.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise GitPortError("Git output was not UTF-8") from error

    @staticmethod
    def _reject(
        operation: GitOperation,
        code: str,
        *,
        revision: str | None = None,
        diff_hash: str | None = None,
        failed_check: str | None = None,
        command_id: str | None = None,
    ) -> GitReceipt:
        return GitReceipt(
            operation=operation,
            accepted=False,
            code=code,
            revision=revision,
            diff_hash=diff_hash,
            failed_check=failed_check,
            command_id=command_id,
        )

    @staticmethod
    def _transaction_reject(code: str) -> MaintenanceTransactionReceipt:
        return MaintenanceTransactionReceipt(
            accepted=False,
            code=code,
            merge=None,
            verification=None,
            revert=None,
        )


def _default_merge_lock_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        root = Path(local_app_data)
    else:  # pragma: no cover - Windows normally always defines LOCALAPPDATA
        root = Path.home() / "AppData" / "Local"
    return root / "V20" / "locks" / "maintenance-merge.lock"


def _default_push_receipt_database() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        root = Path(local_app_data)
    else:  # pragma: no cover - Windows normally always defines LOCALAPPDATA
        root = Path.home() / "AppData" / "Local"
    return root / "V20" / "receipts" / "source-control-push.sqlite3"


def _safe_process_environment() -> dict[str, str]:
    environment = {
        key: value for key, value in os.environ.items() if key.upper() in _PROCESS_ENV_ALLOWLIST
    }
    environment.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "Never",
            "UV_OFFLINE": "1",
            "UV_NO_PROGRESS": "1",
            "CARGO_NET_OFFLINE": "true",
            "CARGO_TERM_PROGRESS_WHEN": "never",
            "PIP_NO_INDEX": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PYTHONUTF8": "1",
        }
    )
    return environment


def _is_full_git_revision(value: str) -> bool:
    return len(value) in (40, 64) and all(character in "0123456789abcdef" for character in value)


def _path_exists_or_reparse(path: Path) -> bool:
    return path.exists() or _is_link_or_reparse(path)


def _is_link_or_reparse(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
        return bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
    except OSError:
        return False


def _has_reparse_component(path: Path, boundary: Path) -> bool:
    try:
        boundary_resolved = boundary.resolve(strict=False)
        current = path
        chain: list[Path] = []
        while True:
            chain.append(current)
            if current == boundary or current.parent == current:
                break
            current = current.parent
        if chain[-1] != boundary:
            return True
        for component in reversed(chain):
            if _is_link_or_reparse(component):
                return True
        return not path.resolve(strict=False).is_relative_to(boundary_resolved)
    except OSError:
        return True


def _is_approved_verification_argv(argv: tuple[str, ...]) -> bool:
    if argv[:6] == ("uv", "run", "--locked", "python", "-m", "pytest"):
        return _valid_pytest_arguments(argv[6:])
    if argv[:5] == ("uv", "run", "--locked", "ruff", "check"):
        return _valid_ruff_arguments(argv[5:], allowed_flags={"--no-fix"})
    if argv[:6] == ("uv", "run", "--locked", "ruff", "format", "--check"):
        return _valid_ruff_arguments(argv[6:], allowed_flags=set())
    if argv == ("cargo", "fmt", "--all", "--", "--check"):
        return True
    if (
        len(argv) < 4
        or argv[0] != "cargo"
        or argv[1]
        not in {
            "check",
            "clippy",
            "test",
        }
    ):
        return False
    before_separator, separator, after_separator = _split_cargo_separator(argv[2:])
    if "--locked" not in before_separator or "--offline" not in before_separator:
        return False
    common_flags = {
        "--locked",
        "--offline",
        "--all-targets",
        "--all-features",
        "--workspace",
    }
    if argv[1] == "test":
        allowed_flags = common_flags | {"--lib", "--bins", "--tests", "--quiet"}
    else:
        allowed_flags = common_flags
    if len(set(before_separator)) != len(before_separator) or any(
        token not in allowed_flags for token in before_separator
    ):
        return False
    if argv[1] == "clippy":
        return (not separator and not after_separator) or (
            separator and after_separator == ("-D", "warnings")
        )
    return not separator and not after_separator


def _verification_command_kind(argv: tuple[str, ...]) -> str | None:
    if argv[:6] == ("uv", "run", "--locked", "python", "-m", "pytest"):
        return "tests"
    if argv[:5] == ("uv", "run", "--locked", "ruff", "check"):
        return "static-analysis"
    if argv[:6] == ("uv", "run", "--locked", "ruff", "format", "--check"):
        return "formatting"
    if len(argv) >= 2 and argv[0] == "cargo":
        return {
            "fmt": "formatting",
            "check": "static-analysis",
            "clippy": "static-analysis",
            "test": "tests",
        }.get(argv[1])
    return None


def _valid_pytest_arguments(arguments: tuple[str, ...]) -> bool:
    if not arguments:
        return False
    allowed_flags = {"-q", "-x", "--disable-warnings", "--tb=short", "--maxfail=1"}
    targets = tuple(argument for argument in arguments if argument not in allowed_flags)
    return bool(targets) and all(
        _is_safe_gate_target(target, prefixes=("tests/",)) for target in targets
    )


def _valid_ruff_arguments(
    arguments: tuple[str, ...],
    *,
    allowed_flags: set[str],
) -> bool:
    if not arguments:
        return False
    targets = tuple(argument for argument in arguments if argument not in allowed_flags)
    if any(argument.startswith("-") and argument not in allowed_flags for argument in arguments):
        return False
    return bool(targets) and all(
        _is_safe_gate_target(target, prefixes=("tests/", "vesper/")) for target in targets
    )


def _is_safe_gate_target(value: str, *, prefixes: tuple[str, ...]) -> bool:
    lowered = value.casefold()
    posix = Path(value)
    return (
        value == value.strip()
        and value.startswith(prefixes)
        and "\\" not in value
        and ":" not in value
        and not value.startswith(("/", "-"))
        and ".." not in posix.parts
        and not any(
            token in lowered
            for token in (
                "http://",
                "https://",
                "powershell",
                "pwsh",
                "cmd.exe",
                "curl",
                "ssh",
                "git push",
                "gh ",
            )
        )
    )


def _split_cargo_separator(
    arguments: tuple[str, ...],
) -> tuple[tuple[str, ...], bool, tuple[str, ...]]:
    if "--" not in arguments:
        return arguments, False, ()
    index = arguments.index("--")
    if "--" in arguments[index + 1 :]:
        return (), True, ("invalid",)
    return arguments[:index], True, arguments[index + 1 :]
