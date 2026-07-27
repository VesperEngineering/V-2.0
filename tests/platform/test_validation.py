from __future__ import annotations

import subprocess
from datetime import datetime, timezone

import pytest

from vesper.platform.contracts import (
    DevelopmentSpecialistOutput,
    ExecutionStatus,
    SpecialistReceipt,
    SpecialistRole,
    TaskRequest,
)
from vesper.platform.evidence import FilesystemEvidenceStore
from vesper.platform.validation import LocalDeterministicValidator, validate_acceptance_checks


NOW = datetime(2026, 7, 27, 16, 0, tzinfo=timezone.utc)


def initialize_repository(path):
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    (path / "README.md").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=V20 Test",
            "-c",
            "user.email=v20-test@example.invalid",
            "commit",
            "-q",
            "-m",
            "baseline",
        ],
        cwd=path,
        check=True,
    )


def request(workspace, checks):
    return TaskRequest(
        run_id="run-001",
        task_id="task-001",
        repository_revision="abc123",
        created_at=NOW,
        objective="Create a harmless documentation marker.",
        repository_root=str(workspace),
        acceptance_checks=checks,
    )


def receipt(changed_files=("M2-CONTROLLED-EXERCISE.md",), *, attempt=1):
    return SpecialistReceipt(
        run_id="run-001",
        task_id="task-001",
        repository_revision="abc123",
        created_at=NOW,
        receipt_id="development-001",
        role=SpecialistRole.DEVELOPMENT,
        attempt=attempt,
        status=ExecutionStatus.COMPLETED,
        output=DevelopmentSpecialistOutput(
            run_id="run-001",
            task_id="task-001",
            repository_revision="abc123",
            created_at=NOW,
            role=SpecialistRole.DEVELOPMENT,
            attempt=attempt,
            summary="Created bounded marker.",
            changed_files=changed_files,
        ),
    )


def test_validator_runs_only_typed_local_checks_and_hashes_evidence(tmp_path):
    initialize_repository(tmp_path)
    workspace = tmp_path / "exercise"
    workspace.mkdir()
    target = workspace / "M2-CONTROLLED-EXERCISE.md"
    target.write_text("# V20 M2 controlled exercise\n", encoding="utf-8")
    validator = LocalDeterministicValidator(
        repository_root=tmp_path,
        evidence=FilesystemEvidenceStore(tmp_path / ".state" / "evidence"),
        clock=lambda: NOW,
    )

    result = validator.validate(
        request(
            workspace,
            (
                "git-diff-check",
                "path-exists::M2-CONTROLLED-EXERCISE.md",
                "file-contains::M2-CONTROLLED-EXERCISE.md::V20 M2 controlled exercise",
            ),
        ),
        receipt(),
    )

    assert result.passed is True
    assert [check.name for check in result.checks] == [
        "git-diff-check",
        "path-exists",
        "file-contains",
    ]
    assert all(check.evidence for check in result.checks)


def test_validator_fails_closed_on_unknown_or_escaping_check(tmp_path):
    initialize_repository(tmp_path)
    workspace = tmp_path / "exercise"
    workspace.mkdir()
    validator = LocalDeterministicValidator(
        repository_root=tmp_path,
        evidence=FilesystemEvidenceStore(tmp_path / ".state" / "evidence"),
        clock=lambda: NOW,
    )

    unknown = validator.validate(request(workspace, ("shell::whoami",)), receipt())
    escaping = validator.validate(request(workspace, ("path-exists::../outside.txt",)), receipt())

    assert unknown.passed is False
    assert unknown.checks[0].exit_code == 2
    assert escaping.passed is False
    assert escaping.checks[0].exit_code == 2


@pytest.mark.parametrize(
    "checks",
    [
        (),
        ("shell::whoami",),
        ("path-exists::../outside.txt",),
        ("path-exists::C:/outside.txt",),
        ("file-contains::RESULT.md::",),
        ("file-contains::../RESULT.md::marker",),
    ],
)
def test_acceptance_check_preflight_rejects_unknown_or_unsafe_syntax(checks):
    with pytest.raises(ValueError):
        validate_acceptance_checks(checks)


def test_acceptance_check_preflight_accepts_only_the_controller_grammar():
    checks = (
        "git-diff-check",
        "path-exists::RESULT.md",
        "file-contains::RESULT.md::controlled-write",
    )

    assert validate_acceptance_checks(checks) == checks


def test_git_diff_check_rejects_noop_and_untracked_trailing_whitespace(tmp_path):
    initialize_repository(tmp_path)
    workspace = tmp_path / "exercise"
    workspace.mkdir()
    validator = LocalDeterministicValidator(
        repository_root=tmp_path,
        evidence=FilesystemEvidenceStore(tmp_path / ".state" / "evidence"),
        clock=lambda: NOW,
    )

    noop = validator.validate(request(workspace, ("git-diff-check",)), receipt(()))
    (workspace / "M2-CONTROLLED-EXERCISE.md").write_text(
        "trailing whitespace   \n",
        encoding="utf-8",
    )
    whitespace = validator.validate(
        request(workspace, ("git-diff-check",)),
        receipt(attempt=2),
    )

    assert noop.passed is False
    assert whitespace.passed is False
