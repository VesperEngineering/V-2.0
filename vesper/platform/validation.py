"""Allowlisted deterministic validation for local specialist workspaces."""

from __future__ import annotations

import json
import os
import subprocess
import hashlib
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from .contracts import (
    DevelopmentSpecialistOutput,
    SpecialistReceipt,
    TaskRequest,
    ValidationCheck,
    ValidationResult,
)
from .evidence import FilesystemEvidenceStore


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_subprocess_environment() -> dict[str, str]:
    allowed = (
        "SYSTEMROOT",
        "WINDIR",
        "PATH",
        "PATHEXT",
        "COMSPEC",
        "TEMP",
        "TMP",
    )
    return {name: os.environ[name] for name in allowed if name in os.environ}


def validate_acceptance_checks(checks: tuple[str, ...]) -> tuple[str, ...]:
    """Reject unknown or unsafe check specifications before any specialist runs."""
    if not checks:
        raise ValueError("at least one deterministic acceptance check is required")
    for specification in checks:
        if specification == "git-diff-check":
            continue
        if specification.startswith("path-exists::"):
            parts = specification.split("::", 1)
            if len(parts) == 2 and _is_safe_relative(parts[1]):
                continue
        if specification.startswith("file-contains::"):
            parts = specification.split("::", 2)
            if len(parts) == 3 and _is_safe_relative(parts[1]) and parts[2].strip():
                continue
        raise ValueError(f"unknown or unsafe deterministic validation check: {specification}")
    return checks


def _is_safe_relative(value: str) -> bool:
    candidate = Path(value)
    return bool(candidate.parts) and not candidate.is_absolute() and ".." not in candidate.parts


class LocalDeterministicValidator:
    """Evaluate only controller-approved, non-shell validation predicates."""

    def __init__(
        self,
        *,
        repository_root: Path,
        evidence: FilesystemEvidenceStore,
        clock: Callable[[], datetime] = _utc_now,
        command_timeout_seconds: float = 60,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.evidence = evidence
        self.clock = clock
        self.command_timeout_seconds = command_timeout_seconds

    def validate(
        self,
        request: TaskRequest,
        development_receipt: SpecialistReceipt,
    ) -> ValidationResult:
        if (
            request.run_id != development_receipt.run_id
            or request.task_id != development_receipt.task_id
            or request.repository_revision != development_receipt.repository_revision
        ):
            raise ValueError("Development receipt authority does not match validation task")
        workspace = Path(request.repository_root).resolve()
        if not workspace.is_dir() or not workspace.is_relative_to(self.repository_root):
            raise ValueError("validation workspace is outside the approved repository")
        checks = tuple(
            self._evaluate(request, development_receipt, workspace, index, specification)
            for index, specification in enumerate(request.acceptance_checks, start=1)
        )
        return ValidationResult(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=self.clock(),
            attempt=development_receipt.attempt,
            passed=all(check.passed for check in checks),
            checks=checks,
        )

    def _evaluate(
        self,
        request: TaskRequest,
        receipt: SpecialistReceipt,
        workspace: Path,
        index: int,
        specification: str,
    ) -> ValidationCheck:
        if specification == "git-diff-check":
            return self._git_diff_check(request, receipt, workspace, index)
        if specification.startswith("path-exists::"):
            relative = specification.removeprefix("path-exists::")
            return self._path_exists(request, receipt, workspace, index, relative)
        if specification.startswith("file-contains::"):
            parts = specification.split("::", 2)
            if len(parts) == 3:
                return self._file_contains(
                    request,
                    receipt,
                    workspace,
                    index,
                    parts[1],
                    parts[2],
                )
        return self._result(
            request,
            receipt,
            index=index,
            name="invalid-check",
            command=specification,
            passed=False,
            exit_code=2,
            detail="unknown or malformed deterministic validation check",
        )

    def _git_diff_check(
        self,
        request: TaskRequest,
        receipt: SpecialistReceipt,
        workspace: Path,
        index: int,
    ) -> ValidationCheck:
        output = receipt.output
        if not isinstance(output, DevelopmentSpecialistOutput) or not output.changed_files:
            return self._result(
                request,
                receipt,
                index=index,
                name="git-diff-check",
                command="git diff HEAD --check -- .",
                passed=False,
                exit_code=1,
                detail="Development produced no controller-observed file changes",
            )
        try:
            completed = subprocess.run(
                ["git", "diff", "HEAD", "--check", "--", "."],
                cwd=workspace,
                env=_safe_subprocess_environment(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.command_timeout_seconds,
                check=False,
            )
            details = [(completed.stdout + completed.stderr).strip()]
            for relative in output.changed_files:
                path = self._safe_path(workspace, relative)
                if path is None:
                    details.append(f"unsafe changed path: {relative}")
                    continue
                if not path.is_file() or path.is_symlink():
                    continue
                body = path.read_bytes()
                if b"\0" in body:
                    continue
                for line_number, line in enumerate(body.splitlines(), start=1):
                    if line.endswith((b" ", b"\t")):
                        details.append(f"{relative}:{line_number}: trailing whitespace")
                    indentation = line[: len(line) - len(line.lstrip(b" \t"))]
                    if b" \t" in indentation:
                        details.append(f"{relative}:{line_number}: space before tab in indent")
            detail = "\n".join(item for item in details if item)
            return self._result(
                request,
                receipt,
                index=index,
                name="git-diff-check",
                command="git diff HEAD --check -- .",
                passed=completed.returncode == 0 and not detail,
                exit_code=completed.returncode
                if completed.returncode != 0
                else (1 if detail else 0),
                detail=detail,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return self._result(
                request,
                receipt,
                index=index,
                name="git-diff-check",
                command="git diff HEAD --check -- .",
                passed=False,
                exit_code=124,
                detail=type(exc).__name__,
            )

    def _path_exists(
        self,
        request: TaskRequest,
        receipt: SpecialistReceipt,
        workspace: Path,
        index: int,
        relative: str,
    ) -> ValidationCheck:
        path = self._safe_path(workspace, relative)
        valid = path is not None and path.is_file() and not path.is_symlink()
        return self._result(
            request,
            receipt,
            index=index,
            name="path-exists" if path is not None else "invalid-check",
            command=f"path-exists::{relative}",
            passed=valid,
            exit_code=0 if valid else (1 if path is not None else 2),
            detail="regular file exists" if valid else "path is missing, unsafe, or not a file",
        )

    def _file_contains(
        self,
        request: TaskRequest,
        receipt: SpecialistReceipt,
        workspace: Path,
        index: int,
        relative: str,
        marker: str,
    ) -> ValidationCheck:
        path = self._safe_path(workspace, relative)
        valid = False
        if path is not None and marker and path.is_file() and not path.is_symlink():
            try:
                valid = marker in path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                valid = False
        return self._result(
            request,
            receipt,
            index=index,
            name="file-contains" if path is not None and marker else "invalid-check",
            command=f"file-contains::{relative}::<redacted-marker>",
            passed=valid,
            exit_code=0 if valid else (1 if path is not None and marker else 2),
            detail="required marker found" if valid else "marker absent or path unsafe",
        )

    @staticmethod
    def _safe_path(workspace: Path, relative: str) -> Path | None:
        candidate = Path(relative)
        if not relative or candidate.is_absolute() or ".." in candidate.parts:
            return None
        resolved = (workspace / candidate).resolve()
        return resolved if resolved.is_relative_to(workspace) else None

    def _result(
        self,
        request: TaskRequest,
        receipt: SpecialistReceipt,
        *,
        index: int,
        name: str,
        command: str,
        passed: bool,
        exit_code: int,
        detail: str,
    ) -> ValidationCheck:
        body = (
            json.dumps(
                {
                    "schema_version": "1.0",
                    "name": name,
                    "command": command,
                    "passed": passed,
                    "exit_code": exit_code,
                    "detail": detail,
                },
                indent=2,
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
        evidence = self.evidence.put_bytes(
            run_id=request.run_id,
            task_id=request.task_id,
            repository_revision=request.repository_revision,
            created_at=self.clock(),
            artifact_id=(
                f"validation-{receipt.attempt}-{index}-"
                f"{hashlib.sha256(command.encode('utf-8')).hexdigest()[:12]}"
            ),
            body=body,
            media_type="application/json",
            suffix=".json",
        )
        return ValidationCheck(
            name=name,
            passed=passed,
            command=command,
            exit_code=exit_code,
            evidence=(evidence,),
        )
