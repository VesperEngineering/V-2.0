from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from vesper.platform.tui.command_contracts import CommandRequest, ConfirmationProof
from vesper.platform.tui.command_registry import CommandRegistry
from vesper.platform.tui.git_port import (
    LocalGitPort,
    MergeRequest,
    VerificationCommand,
    VerificationRequest,
    WorktreeRequest,
)
from vesper.platform.tui.process_capture import BoundedProcessError, run_bounded_process
from vesper.platform.tui.views import CapabilityState


def _pytest_gate(
    name: str = "focused-tests",
    target: str = "tests/platform/tui/test_git_port.py",
) -> VerificationCommand:
    return VerificationCommand(
        name=name,
        argv=("uv", "run", "--locked", "python", "-m", "pytest", target, "-q"),
    )


def _push_request(command_id: str, revision: str) -> CommandRequest:
    return CommandRequest.model_validate(
        {
            "command_id": command_id,
            "command_type": "source-control.push",
            "reviewed_control_version": 1,
            "reviewed_control_hash": "d" * 64,
            "reason": "Push the reviewed revision.",
            "confirmation": {"first_confirmed": True},
            "payload": {"expected_revision": revision},
        }
    )


def _git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", str(repository), *arguments),
        check=True,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"},
    )


def _repository(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(
        ("git", "init", "--initial-branch=main", str(repository)),
        check=True,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    _git(repository, "config", "user.name", "V20 Test")
    _git(repository, "config", "user.email", "v20-test@example.invalid")
    source = repository / "vesper" / "platform" / "tui" / "safe.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")
    _git(repository, "add", "--", "vesper/platform/tui/safe.py")
    _git(repository, "commit", "-m", "initial")
    return repository, _git(repository, "rev-parse", "HEAD").stdout.strip()


def _candidate_worktree(
    tmp_path: Path,
) -> tuple[LocalGitPort, Path, Path, str, str, str]:
    repository, base_revision = _repository(tmp_path)
    worktree_parent = tmp_path / "worktrees"
    worktree_parent.mkdir()
    worktree = worktree_parent / "candidate"
    port = LocalGitPort(repository, worktree_root=worktree_parent)
    created = port.create_worktree(
        WorktreeRequest(
            path=worktree,
            branch="candidate-safe-fix",
            start_revision=base_revision,
        )
    )
    assert created.accepted is True
    source = worktree / "vesper" / "platform" / "tui" / "safe.py"
    source.write_text("VALUE = 2\n", encoding="utf-8")
    _git(worktree, "add", "--", "vesper/platform/tui/safe.py")
    _git(worktree, "commit", "-m", "safe fix")
    candidate_revision = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    diff_hash = port.diff_hash(base_revision, candidate_revision)
    return port, repository, worktree, base_revision, candidate_revision, diff_hash


def _clean_external_worktree(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    repository, revision = _repository(tmp_path)
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree = worktree_root / "verification"
    port = LocalGitPort(repository, worktree_root=worktree_root)
    receipt = port.create_worktree(
        WorktreeRequest(
            path=worktree,
            branch="verification-only",
            start_revision=revision,
        )
    )
    assert receipt.accepted is True
    return repository, worktree_root, worktree, revision


def test_status_reports_exact_revision_and_clean_state(tmp_path: Path) -> None:
    repository, revision = _repository(tmp_path)
    port = LocalGitPort(repository, worktree_root=tmp_path / "worktrees")

    status = port.status()

    assert status.revision == revision
    assert status.clean is True
    (repository / "vesper" / "platform" / "tui" / "safe.py").write_text("dirty\n", encoding="utf-8")
    assert port.status().clean is False


def test_git_runner_receives_direct_argv_bounded_output_and_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    monkeypatch.setenv("PYTEST_ADDOPTS", "-p unsafe_plugin")
    monkeypatch.setenv("RUSTC_WRAPPER", "unsafe-wrapper")
    monkeypatch.setenv("GIT_SSH_COMMAND", "unsafe-ssh-wrapper")
    monkeypatch.setenv("CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_RUNNER", "unsafe-runner")
    monkeypatch.setenv("V20_FAKE_API_KEY", "do-not-pass")
    revision = "a" * 40
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def runner(command: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        calls.append((command, options))
        stdout = f"{revision}\n".encode() if "rev-parse" in command else b""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr=b"")

    port = LocalGitPort(
        repository,
        worktree_root=tmp_path / "worktrees",
        runner=runner,
    )

    assert port.status().revision == revision
    assert len(calls) == 2
    for command, options in calls:
        assert type(command) is tuple
        assert command[:3] == ("git", "-C", str(repository))
        assert options["shell"] is False
        assert options["check"] is False
        assert options["stdin"] == subprocess.DEVNULL
        assert options["stdout"] == subprocess.PIPE
        assert options["stderr"] == subprocess.PIPE
        assert options["timeout"] <= 300
        assert options["max_output_bytes"] <= 16 * 1024 * 1024
        environment = options["env"]
        assert isinstance(environment, dict)
        assert environment["UV_OFFLINE"] == "1"
        assert environment["CARGO_NET_OFFLINE"] == "true"
        assert environment["PIP_NO_INDEX"] == "1"
        assert environment.get("PYTEST_ADDOPTS") is None
        assert environment.get("RUSTC_WRAPPER") is None
        assert environment.get("GIT_SSH_COMMAND") is None
        assert environment.get("CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_RUNNER") is None
        assert environment.get("V20_FAKE_API_KEY") is None


@pytest.mark.parametrize(
    ("name", "argv"),
    (
        (
            "focused-tests",
            ("uv", "run", "--locked", "python", "-m", "pytest", "tests/platform/tui", "-q"),
        ),
        (
            "static-analysis",
            ("uv", "run", "--locked", "ruff", "check", "vesper/platform/tui"),
        ),
        (
            "formatting",
            (
                "uv",
                "run",
                "--locked",
                "ruff",
                "format",
                "--check",
                "vesper/platform/tui",
            ),
        ),
        ("formatting", ("cargo", "fmt", "--all", "--", "--check")),
        (
            "static-analysis",
            ("cargo", "check", "--locked", "--offline", "--all-targets"),
        ),
        (
            "static-analysis",
            (
                "cargo",
                "clippy",
                "--locked",
                "--offline",
                "--all-targets",
                "--",
                "-D",
                "warnings",
            ),
        ),
        (
            "broad-tests",
            ("cargo", "test", "--locked", "--offline", "--all-targets"),
        ),
    ),
)
def test_verification_command_accepts_only_structured_v20_gates(
    name: str,
    argv: tuple[str, ...],
) -> None:
    assert VerificationCommand(name=name, argv=argv).argv == argv


def test_verification_gate_name_must_match_command_kind() -> None:
    with pytest.raises(ValidationError, match="does not match"):
        VerificationCommand(
            name="formatting",
            argv=(
                "uv",
                "run",
                "--locked",
                "python",
                "-m",
                "pytest",
                "tests/platform/tui",
            ),
        )


@pytest.mark.parametrize(
    "argv",
    (
        ("cmd", "/c", "pytest"),
        ("powershell", "-Command", "pytest"),
        ("pwsh", "-Command", "pytest"),
        ("git", "push", "origin", "main"),
        ("curl", "https://example.invalid"),
        ("ssh", "host"),
        ("gh", "pr", "create"),
        ("uv", "run", "--locked", "python", "-c", "print('unsafe')"),
        ("uv", "run", "--locked", "python", "script.py"),
        (
            "uv",
            "run",
            "--locked",
            "python",
            "-m",
            "pytest",
            "tests/platform/tui",
            "powershell",
        ),
        ("uv", "run", "python", "-m", "pytest", "tests/platform/tui"),
        ("uv", "run", "--locked", "ruff", "check", "https://example.invalid"),
        ("uv", "run", "--locked", "ruff", "format", "vesper/platform/tui"),
        ("cargo", "run", "--locked", "--offline"),
        ("cargo", "install", "tool"),
        ("cargo", "test", "--offline"),
        ("cargo", "test", "--locked"),
        ("cargo", "test", "--locked", "--offline", "--manifest-path", "../Cargo.toml"),
    ),
)
def test_verification_command_rejects_shell_network_and_mutation_shapes(
    argv: tuple[str, ...],
) -> None:
    with pytest.raises(ValidationError, match="approved V20 verification gate"):
        VerificationCommand(name="focused-tests", argv=argv)


def test_create_worktree_rejects_target_outside_injected_root(tmp_path: Path) -> None:
    repository, revision = _repository(tmp_path)
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    port = LocalGitPort(repository, worktree_root=worktree_root)

    receipt = port.create_worktree(
        WorktreeRequest(
            path=tmp_path / "outside",
            branch="candidate-outside",
            start_revision=revision,
        )
    )

    assert receipt.accepted is False
    assert receipt.code == "unsafe-worktree-path"
    assert not (tmp_path / "outside").exists()


@pytest.mark.parametrize("failure_mode", ("nonzero", "exception"))
def test_create_worktree_cleans_partial_target_branch_and_metadata(
    tmp_path: Path,
    failure_mode: str,
) -> None:
    repository, revision = _repository(tmp_path)
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    target = worktree_root / "partial"

    def runner(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        if len(argv) > 4 and argv[3:5] == ("worktree", "add"):
            created = run_bounded_process(argv, **options)  # type: ignore[arg-type]
            assert created.returncode == 0
            if failure_mode == "exception":
                raise BoundedProcessError("injected after worktree mutation")
            return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"")
        return run_bounded_process(argv, **options)  # type: ignore[arg-type]

    port = LocalGitPort(repository, worktree_root=worktree_root, runner=runner)

    receipt = port.create_worktree(
        WorktreeRequest(
            path=target,
            branch="partial-candidate",
            start_revision=revision,
        )
    )

    assert receipt.accepted is False
    assert receipt.code == "worktree-create-failed"
    assert not target.exists()
    assert (
        subprocess.run(
            (
                "git",
                "-C",
                str(repository),
                "show-ref",
                "--verify",
                "--quiet",
                "refs/heads/partial-candidate",
            ),
            check=False,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        ).returncode
        != 0
    )
    assert str(target) not in _git(repository, "worktree", "list", "--porcelain").stdout


def test_create_worktree_verification_failure_cleans_target_branch_and_metadata(
    tmp_path: Path,
) -> None:
    repository, revision = _repository(tmp_path)
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    target = worktree_root / "verification-fails"
    created = False
    failed_readback = False

    def runner(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        nonlocal created, failed_readback
        result = run_bounded_process(argv, **options)  # type: ignore[arg-type]
        if len(argv) > 4 and argv[3:5] == ("worktree", "add"):
            assert result.returncode == 0
            created = True
        elif (
            created
            and not failed_readback
            and len(argv) > 3
            and argv[3] == "rev-parse"
            and Path(options["cwd"]) == target  # type: ignore[arg-type]
        ):
            failed_readback = True
            raise BoundedProcessError("injected worktree verification failure")
        return result

    port = LocalGitPort(repository, worktree_root=worktree_root, runner=runner)

    receipt = port.create_worktree(
        WorktreeRequest(
            path=target,
            branch="verification-fails",
            start_revision=revision,
        )
    )

    assert receipt.accepted is False
    assert receipt.code == "worktree-verification-failed"
    assert not target.exists()
    assert (
        subprocess.run(
            (
                "git",
                "-C",
                str(repository),
                "rev-parse",
                "--verify",
                "--quiet",
                "refs/heads/verification-fails^{commit}",
            ),
            check=False,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        ).returncode
        == 1
    )
    assert str(target) not in _git(repository, "worktree", "list", "--porcelain").stdout


def test_create_worktree_reports_metadata_cleanup_failure_without_raising(
    tmp_path: Path,
) -> None:
    repository, revision = _repository(tmp_path)
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    target = worktree_root / "metadata-unavailable"

    def runner(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        if len(argv) > 4 and argv[3:5] == ("worktree", "add"):
            created = run_bounded_process(argv, **options)  # type: ignore[arg-type]
            assert created.returncode == 0
            return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"")
        if len(argv) > 4 and argv[3:5] == ("worktree", "list"):
            return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"")
        return run_bounded_process(argv, **options)  # type: ignore[arg-type]

    port = LocalGitPort(repository, worktree_root=worktree_root, runner=runner)

    try:
        receipt = port.create_worktree(
            WorktreeRequest(
                path=target,
                branch="metadata-unavailable",
                start_revision=revision,
            )
        )

        assert receipt.accepted is False
        assert receipt.code == "worktree-create-failed-cleanup-failed"
    finally:
        if target.exists():
            _git(repository, "worktree", "remove", "--force", "--", str(target))
        branch = subprocess.run(
            (
                "git",
                "-C",
                str(repository),
                "rev-parse",
                "--verify",
                "--quiet",
                "refs/heads/metadata-unavailable^{commit}",
            ),
            check=False,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
        if branch.returncode == 0:
            _git(repository, "branch", "-D", "--", "metadata-unavailable")


def test_worktree_root_must_be_outside_main_repository(tmp_path: Path) -> None:
    repository, _revision = _repository(tmp_path)

    for unsafe_root in (repository / ".worktrees", tmp_path):
        with pytest.raises(ValueError, match="repository"):
            LocalGitPort(
                repository,
                worktree_root=unsafe_root,
            )


def test_verification_uses_only_exact_allowlisted_direct_argv(tmp_path: Path) -> None:
    repository, worktree_root, worktree, _ = _clean_external_worktree(tmp_path)
    command = _pytest_gate()

    def runner(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        if argv[0] == "uv":
            return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")
        return run_bounded_process(argv, **options)  # type: ignore[arg-type]

    port = LocalGitPort(
        repository,
        worktree_root=worktree_root,
        allowed_verification_commands=(command,),
        runner=runner,
    )

    passed = port.verify(VerificationRequest(worktree=worktree, commands=(command,)))
    unconfigured = _pytest_gate(
        name="broad-tests",
        target="tests/platform/tui/test_command_contracts.py",
    )
    rejected = port.verify(VerificationRequest(worktree=worktree, commands=(unconfigured,)))

    assert passed.accepted is True
    assert passed.code == "verification-passed"
    assert rejected.accepted is False
    assert rejected.code == "verification-command-not-allowed"


def test_public_verification_rejects_main_before_any_runner_call(tmp_path: Path) -> None:
    repository, _revision = _repository(tmp_path)
    command = _pytest_gate()
    runner_calls = 0

    def runner(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        nonlocal runner_calls
        runner_calls += 1
        if argv[0] == "uv":
            return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")
        return run_bounded_process(argv, **options)  # type: ignore[arg-type]

    port = LocalGitPort(
        repository,
        worktree_root=tmp_path / "worktrees",
        allowed_verification_commands=(command,),
        runner=runner,
    )

    receipt = port.verify(VerificationRequest(worktree=repository, commands=(command,)))

    assert receipt.accepted is False
    assert receipt.code == "unsafe-verification-worktree"
    assert runner_calls == 0


def test_failed_verification_is_bounded_failure_receipt(tmp_path: Path) -> None:
    repository, worktree_root, worktree, _ = _clean_external_worktree(tmp_path)
    command = _pytest_gate()

    def runner(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        if argv[0] == "uv":
            return subprocess.CompletedProcess(argv, 7, stdout=b"", stderr=b"")
        return run_bounded_process(argv, **options)  # type: ignore[arg-type]

    port = LocalGitPort(
        repository,
        worktree_root=worktree_root,
        allowed_verification_commands=(command,),
        runner=runner,
    )

    receipt = port.verify(VerificationRequest(worktree=worktree, commands=(command,)))

    assert receipt.accepted is False
    assert receipt.code == "verification-failed"
    assert receipt.failed_check == "focused-tests"


def test_verification_rejects_dirty_worktree_before_running_checks(tmp_path: Path) -> None:
    repository, worktree_root, worktree, _ = _clean_external_worktree(tmp_path)
    command = _pytest_gate()
    gate_calls = 0

    def runner(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        nonlocal gate_calls
        if argv[0] == "uv":
            gate_calls += 1
            return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")
        return run_bounded_process(argv, **options)  # type: ignore[arg-type]

    port = LocalGitPort(
        repository,
        worktree_root=worktree_root,
        allowed_verification_commands=(command,),
        runner=runner,
    )
    (worktree / "dirty-user-work.txt").write_text("preserve\n", encoding="utf-8")

    receipt = port.verify(VerificationRequest(worktree=worktree, commands=(command,)))

    assert receipt.accepted is False
    assert receipt.code == "verification-worktree-not-clean"
    assert gate_calls == 0
    assert (worktree / "dirty-user-work.txt").read_text(encoding="utf-8") == "preserve\n"


def test_verification_fails_if_check_changes_worktree_and_never_cleans_it(
    tmp_path: Path,
) -> None:
    repository, worktree_root, worktree, _ = _clean_external_worktree(tmp_path)
    command = VerificationCommand(
        name="static-analysis",
        argv=("uv", "run", "--locked", "ruff", "check", "vesper/platform/tui"),
    )

    def runner(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        if argv[0] == "uv":
            (worktree / "generated.txt").write_text("keep", encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")
        return run_bounded_process(argv, **options)  # type: ignore[arg-type]

    port = LocalGitPort(
        repository,
        worktree_root=worktree_root,
        allowed_verification_commands=(command,),
        runner=runner,
    )

    receipt = port.verify(VerificationRequest(worktree=worktree, commands=(command,)))

    assert receipt.accepted is False
    assert receipt.code == "verification-worktree-changed"
    assert (worktree / "generated.txt").read_text(encoding="utf-8") == "keep"


def test_merge_no_ff_requires_clean_exact_base_and_reviewed_diff(tmp_path: Path) -> None:
    port, repository, _worktree, base, candidate, diff_hash = _candidate_worktree(tmp_path)

    receipt = port.merge_no_ff(
        MergeRequest(
            repository_root=repository,
            expected_base_revision=base,
            candidate_revision=candidate,
            reviewed_diff_hash=diff_hash,
            rollback_revision=base,
            changed_paths=("vesper/platform/tui/safe.py",),
        )
    )

    assert receipt.accepted is True
    assert receipt.code == "merge-completed"
    assert receipt.revision is not None
    parents = _git(repository, "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()
    assert len(parents) == 3
    assert parents[1] == base
    assert parents[2] == candidate
    assert _git(repository, "status", "--porcelain").stdout == ""


@pytest.mark.parametrize(
    ("request_change", "expected_code"),
    (
        ({"expected_base_revision": "e" * 40}, "base-revision-mismatch"),
        ({"reviewed_diff_hash": "f" * 64}, "reviewed-diff-mismatch"),
        ({"rollback_revision": "e" * 40}, "rollback-revision-mismatch"),
    ),
)
def test_merge_gate_failure_makes_no_commit(
    tmp_path: Path,
    request_change: dict[str, str],
    expected_code: str,
) -> None:
    port, repository, _worktree, base, candidate, diff_hash = _candidate_worktree(tmp_path)
    request = MergeRequest(
        repository_root=repository,
        expected_base_revision=base,
        candidate_revision=candidate,
        reviewed_diff_hash=diff_hash,
        rollback_revision=base,
        changed_paths=("vesper/platform/tui/safe.py",),
    ).model_copy(update=request_change)

    receipt = port.merge_no_ff(request)

    assert receipt.accepted is False
    assert receipt.code == expected_code
    assert _git(repository, "rev-parse", "HEAD").stdout.strip() == base


def test_dirty_main_is_never_reset_or_cleaned_for_merge(tmp_path: Path) -> None:
    port, repository, _worktree, base, candidate, diff_hash = _candidate_worktree(tmp_path)
    dirty = repository / "local-user-work.txt"
    dirty.write_text("preserve me\n", encoding="utf-8")

    receipt = port.merge_no_ff(
        MergeRequest(
            repository_root=repository,
            expected_base_revision=base,
            candidate_revision=candidate,
            reviewed_diff_hash=diff_hash,
            rollback_revision=base,
            changed_paths=("vesper/platform/tui/safe.py",),
        )
    )

    assert receipt.accepted is False
    assert receipt.code == "main-not-clean"
    assert dirty.read_text(encoding="utf-8") == "preserve me\n"
    assert _git(repository, "rev-parse", "HEAD").stdout.strip() == base


def test_merge_receipt_repository_must_match_port_repository(tmp_path: Path) -> None:
    port, repository, _worktree, base, candidate, diff_hash = _candidate_worktree(tmp_path)
    different_repository = tmp_path / "different-repository"
    different_repository.mkdir()

    receipt = port.merge_no_ff(
        MergeRequest(
            repository_root=different_repository,
            expected_base_revision=base,
            candidate_revision=candidate,
            reviewed_diff_hash=diff_hash,
            rollback_revision=base,
            changed_paths=("vesper/platform/tui/safe.py",),
        )
    )

    assert receipt.accepted is False
    assert receipt.code == "repository-root-mismatch"
    assert _git(repository, "rev-parse", "HEAD").stdout.strip() == base


class HeldMergeLock:
    def __enter__(self) -> None:
        raise BlockingIOError("held")

    def __exit__(self, *_args: object) -> None:
        return None


def test_held_injected_merge_lock_blocks_merge_without_mutation(tmp_path: Path) -> None:
    _port, repository, _worktree, base, candidate, _diff_hash = _candidate_worktree(tmp_path)
    port = LocalGitPort(
        repository,
        worktree_root=tmp_path / "worktrees",
        merge_lock_factory=lambda: HeldMergeLock(),
    )
    diff_hash = port.diff_hash(base, candidate)

    receipt = port.merge_no_ff(
        MergeRequest(
            repository_root=repository,
            expected_base_revision=base,
            candidate_revision=candidate,
            reviewed_diff_hash=diff_hash,
            rollback_revision=base,
            changed_paths=("vesper/platform/tui/safe.py",),
        )
    )

    assert receipt.accepted is False
    assert receipt.code == "merge-lock-held"
    assert _git(repository, "rev-parse", "HEAD").stdout.strip() == base


def test_revert_targets_merge_commit_once_and_preserves_clean_worktree(tmp_path: Path) -> None:
    port, repository, _worktree, base, candidate, diff_hash = _candidate_worktree(tmp_path)
    merged = port.merge_no_ff(
        MergeRequest(
            repository_root=repository,
            expected_base_revision=base,
            candidate_revision=candidate,
            reviewed_diff_hash=diff_hash,
            rollback_revision=base,
            changed_paths=("vesper/platform/tui/safe.py",),
        )
    )
    assert merged.revision is not None

    reverted = port.revert(merged.revision)

    assert reverted.accepted is True
    assert reverted.code == "revert-completed"
    assert (repository / "vesper" / "platform" / "tui" / "safe.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"
    assert _git(repository, "status", "--porcelain").stdout == ""
    subjects = _git(repository, "log", "-2", "--format=%s").stdout.splitlines()
    assert subjects[0].startswith("Revert ")
    assert len(subjects) == 2


def test_revert_rejects_clean_but_wrong_tree_commit(tmp_path: Path) -> None:
    original, repository, worktree, base, candidate, diff_hash = _candidate_worktree(tmp_path)
    merged = original.merge_no_ff(
        MergeRequest(
            repository_root=repository,
            expected_base_revision=base,
            candidate_revision=candidate,
            reviewed_diff_hash=diff_hash,
            rollback_revision=base,
            changed_paths=("vesper/platform/tui/safe.py",),
        )
    )
    assert merged.accepted and merged.revision is not None

    def runner(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        if len(argv) > 3 and argv[3] == "revert":
            _git(repository, "commit", "--allow-empty", "-m", "wrong rollback")
            return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")
        return run_bounded_process(argv, **options)  # type: ignore[arg-type]

    port = LocalGitPort(repository, worktree_root=worktree.parent, runner=runner)

    receipt = port.revert(merged.revision)

    assert receipt.accepted is False
    assert receipt.code == "revert-verification-failed-manual-recovery-required"
    assert (repository / "vesper" / "platform" / "tui" / "safe.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"


def test_revert_exception_after_exact_effect_is_recovered_as_completed(tmp_path: Path) -> None:
    original, repository, worktree, base, candidate, diff_hash = _candidate_worktree(tmp_path)
    merged = original.merge_no_ff(
        MergeRequest(
            repository_root=repository,
            expected_base_revision=base,
            candidate_revision=candidate,
            reviewed_diff_hash=diff_hash,
            rollback_revision=base,
            changed_paths=("vesper/platform/tui/safe.py",),
        )
    )
    assert merged.accepted and merged.revision is not None

    def runner(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        if len(argv) > 3 and argv[3] == "revert":
            reverted = run_bounded_process(argv, **options)  # type: ignore[arg-type]
            assert reverted.returncode == 0
            raise BoundedProcessError("injected after revert mutation")
        return run_bounded_process(argv, **options)  # type: ignore[arg-type]

    port = LocalGitPort(repository, worktree_root=worktree.parent, runner=runner)

    receipt = port.revert(merged.revision)

    assert receipt.accepted is True
    assert receipt.code == "revert-completed"
    assert (
        _git(repository, "rev-parse", "HEAD^{tree}").stdout.strip()
        == _git(repository, "rev-parse", f"{base}^{{tree}}").stdout.strip()
    )


def test_merge_exception_after_exact_effect_is_recovered_as_completed(tmp_path: Path) -> None:
    original, repository, worktree, base, candidate, diff_hash = _candidate_worktree(tmp_path)

    def runner(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        if len(argv) > 3 and argv[3] == "merge":
            merged = run_bounded_process(argv, **options)  # type: ignore[arg-type]
            assert merged.returncode == 0
            raise BoundedProcessError("injected after merge mutation")
        return run_bounded_process(argv, **options)  # type: ignore[arg-type]

    port = LocalGitPort(repository, worktree_root=worktree.parent, runner=runner)

    receipt = port.merge_no_ff(
        MergeRequest(
            repository_root=repository,
            expected_base_revision=base,
            candidate_revision=candidate,
            reviewed_diff_hash=diff_hash,
            rollback_revision=base,
            changed_paths=("vesper/platform/tui/safe.py",),
        )
    )

    assert receipt.accepted is True
    assert receipt.code == "merge-completed"


def test_merge_rejects_changed_path_list_that_does_not_match_exact_diff(
    tmp_path: Path,
) -> None:
    port, repository, _worktree, base, candidate, diff_hash = _candidate_worktree(tmp_path)

    receipt = port.merge_no_ff(
        MergeRequest(
            repository_root=repository,
            expected_base_revision=base,
            candidate_revision=candidate,
            reviewed_diff_hash=diff_hash,
            rollback_revision=base,
            changed_paths=("vesper/platform/tui/different.py",),
        )
    )

    assert receipt.accepted is False
    assert receipt.code == "changed-paths-mismatch"
    assert _git(repository, "rev-parse", "HEAD").stdout.strip() == base


def test_protected_broker_source_renamed_to_allowed_path_is_reported_and_rejected(
    tmp_path: Path,
) -> None:
    repository, _ = _repository(tmp_path)
    broker_source = repository / "vesper" / "execution" / "broker.py"
    broker_source.parent.mkdir(parents=True)
    broker_source.write_text("BROKER = True\n", encoding="utf-8")
    _git(repository, "add", "--", "vesper/execution/broker.py")
    _git(repository, "commit", "-m", "add protected broker source")
    base = _git(repository, "rev-parse", "HEAD").stdout.strip()
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree = worktree_root / "candidate"
    port = LocalGitPort(repository, worktree_root=worktree_root)
    assert port.create_worktree(
        WorktreeRequest(
            path=worktree,
            branch="candidate-rename-bypass",
            start_revision=base,
        )
    ).accepted
    destination = "vesper/platform/tui/safe_fix.py"
    _git(worktree, "mv", "vesper/execution/broker.py", destination)
    _git(worktree, "commit", "-m", "attempt protected rename")
    candidate = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    diff_hash = port.diff_hash(base, candidate)

    assert port.changed_paths(base, candidate) == (
        "vesper/execution/broker.py",
        destination,
    )
    receipt = port.merge_no_ff(
        MergeRequest(
            repository_root=repository,
            expected_base_revision=base,
            candidate_revision=candidate,
            reviewed_diff_hash=diff_hash,
            rollback_revision=base,
            changed_paths=(destination,),
        )
    )

    assert receipt.accepted is False
    assert receipt.code == "changed-paths-mismatch"
    assert _git(repository, "rev-parse", "HEAD").stdout.strip() == base


def test_merge_rejects_symlink_entry_in_candidate_commit(tmp_path: Path) -> None:
    repository, base = _repository(tmp_path)
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    worktree = worktree_root / "candidate"
    port = LocalGitPort(repository, worktree_root=worktree_root)
    created = port.create_worktree(
        WorktreeRequest(
            path=worktree,
            branch="candidate-symlink",
            start_revision=base,
        )
    )
    assert created.accepted is True
    payload = tmp_path / "symlink-payload.txt"
    payload.write_text("../../outside.py", encoding="utf-8")
    blob = _git(worktree, "hash-object", "-w", str(payload)).stdout.strip()
    relative = "vesper/platform/tui/link.py"
    _git(worktree, "update-index", "--add", "--cacheinfo", f"120000,{blob},{relative}")
    _git(worktree, "commit", "-m", "unsafe symlink")
    candidate = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    diff_hash = port.diff_hash(base, candidate)

    receipt = port.merge_no_ff(
        MergeRequest(
            repository_root=repository,
            expected_base_revision=base,
            candidate_revision=candidate,
            reviewed_diff_hash=diff_hash,
            rollback_revision=base,
            changed_paths=(relative,),
        )
    )

    assert receipt.accepted is False
    assert receipt.code == "unsafe-candidate-tree-entry"
    assert _git(repository, "rev-parse", "HEAD").stdout.strip() == base


def test_merge_detached_verification_and_failed_check_revert_share_one_lock(
    tmp_path: Path,
) -> None:
    repository, base = _repository(tmp_path)
    worktree_root = tmp_path / "worktrees"
    worktree_root.mkdir()
    verification_worktree = worktree_root / "post-merge-verification"
    lock_state = {"held": False, "entries": 0, "exits": 0}

    class TrackingLock:
        def __enter__(self) -> None:
            assert lock_state["held"] is False
            lock_state["held"] = True
            lock_state["entries"] += 1

        def __exit__(self, *_args: object) -> None:
            assert lock_state["held"] is True
            lock_state["held"] = False
            lock_state["exits"] += 1

    def runner(command: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        is_transaction_mutation = (
            len(command) > 3
            and command[0] == "git"
            and command[3]
            in {
                "merge",
                "revert",
            }
        )
        is_verification = command[0] == "uv"
        is_verification_worktree_lifecycle = (
            len(command) > 4
            and command[0] == "git"
            and command[3] == "worktree"
            and command[4] in {"add", "remove"}
            and str(verification_worktree) in command
        )
        if is_transaction_mutation or is_verification or is_verification_worktree_lifecycle:
            assert lock_state["held"] is True
        if is_verification:
            return subprocess.CompletedProcess(command, 7, stdout=b"", stderr=b"")
        return run_bounded_process(command, **options)  # type: ignore[arg-type]

    failed_check = _pytest_gate(name="post-merge-tests")
    port = LocalGitPort(
        repository,
        worktree_root=worktree_root,
        allowed_verification_commands=(failed_check,),
        runner=runner,
        merge_lock_factory=TrackingLock,
    )
    worktree = worktree_root / "candidate"
    assert port.create_worktree(
        WorktreeRequest(
            path=worktree,
            branch="candidate-transaction",
            start_revision=base,
        )
    ).accepted
    assert lock_state == {"held": False, "entries": 1, "exits": 1}
    source = worktree / "vesper" / "platform" / "tui" / "safe.py"
    source.write_text("VALUE = 2\n", encoding="utf-8")
    _git(worktree, "add", "--", "vesper/platform/tui/safe.py")
    _git(worktree, "commit", "-m", "safe fix")
    candidate = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    diff_hash = port.diff_hash(base, candidate)

    transaction = port.merge_verify_revert(
        MergeRequest(
            repository_root=repository,
            expected_base_revision=base,
            candidate_revision=candidate,
            reviewed_diff_hash=diff_hash,
            rollback_revision=base,
            changed_paths=("vesper/platform/tui/safe.py",),
        ),
        VerificationRequest(worktree=verification_worktree, commands=(failed_check,)),
    )

    assert transaction.accepted is False
    assert transaction.code == "post-merge-verification-failed-reverted"
    assert transaction.merge is not None and transaction.merge.accepted
    assert transaction.verification is not None
    assert transaction.verification.code == "verification-failed"
    assert transaction.revert is not None and transaction.revert.accepted
    assert lock_state == {"held": False, "entries": 2, "exits": 2}
    assert not verification_worktree.exists()
    assert _git(repository, "status", "--porcelain").stdout == ""


def test_successful_post_merge_check_uses_and_removes_detached_worktree(
    tmp_path: Path,
) -> None:
    _, repository, candidate_worktree, base, candidate, diff_hash = _candidate_worktree(tmp_path)
    worktree_root = candidate_worktree.parent
    verification_worktree = worktree_root / "post-merge-verification"
    command = _pytest_gate(name="post-merge-tests")
    check_roots: list[Path] = []

    def runner(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        if argv[0] == "uv":
            check_roots.append(Path(options["cwd"]))  # type: ignore[arg-type]
            return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")
        return run_bounded_process(argv, **options)  # type: ignore[arg-type]

    port = LocalGitPort(
        repository,
        worktree_root=worktree_root,
        allowed_verification_commands=(command,),
        runner=runner,
    )

    transaction = port.merge_verify_revert(
        MergeRequest(
            repository_root=repository,
            expected_base_revision=base,
            candidate_revision=candidate,
            reviewed_diff_hash=diff_hash,
            rollback_revision=base,
            changed_paths=("vesper/platform/tui/safe.py",),
        ),
        VerificationRequest(worktree=verification_worktree, commands=(command,)),
    )

    assert transaction.accepted is True
    assert transaction.code == "maintenance-merged"
    assert transaction.merge is not None and transaction.merge.accepted
    assert transaction.verification is not None and transaction.verification.accepted
    assert transaction.verification.revision == transaction.merge.revision
    assert transaction.revert is None
    assert check_roots == [verification_worktree]
    assert not verification_worktree.exists()
    assert _git(repository, "status", "--porcelain").stdout == ""
    assert (repository / "vesper" / "platform" / "tui" / "safe.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"


def test_transaction_rejects_verification_outside_configured_root_before_merge(
    tmp_path: Path,
) -> None:
    port, repository, _worktree, base, candidate, diff_hash = _candidate_worktree(tmp_path)
    command = _pytest_gate(name="post-merge-tests")
    outside = tmp_path / "outside-verification"

    transaction = port.merge_verify_revert(
        MergeRequest(
            repository_root=repository,
            expected_base_revision=base,
            candidate_revision=candidate,
            reviewed_diff_hash=diff_hash,
            rollback_revision=base,
            changed_paths=("vesper/platform/tui/safe.py",),
        ),
        VerificationRequest(worktree=outside, commands=(command,)),
    )

    assert transaction.accepted is False
    assert transaction.code == "unsafe-post-merge-verification-worktree"
    assert transaction.merge is None
    assert _git(repository, "rev-parse", "HEAD").stdout.strip() == base


def test_transaction_rejects_verification_worktree_collision_before_merge(
    tmp_path: Path,
) -> None:
    port, repository, candidate_worktree, base, candidate, diff_hash = _candidate_worktree(tmp_path)
    command = _pytest_gate(name="post-merge-tests")

    transaction = port.merge_verify_revert(
        MergeRequest(
            repository_root=repository,
            expected_base_revision=base,
            candidate_revision=candidate,
            reviewed_diff_hash=diff_hash,
            rollback_revision=base,
            changed_paths=("vesper/platform/tui/safe.py",),
        ),
        VerificationRequest(worktree=candidate_worktree, commands=(command,)),
    )

    assert transaction.accepted is False
    assert transaction.code == "unsafe-post-merge-verification-worktree"
    assert transaction.merge is None
    assert _git(repository, "rev-parse", "HEAD").stdout.strip() == base


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
def test_transaction_rejects_reparse_parent_before_merge(tmp_path: Path) -> None:
    port, repository, candidate_worktree, base, candidate, diff_hash = _candidate_worktree(tmp_path)
    worktree_root = candidate_worktree.parent
    inside_target = worktree_root / "junction-target"
    inside_target.mkdir()
    junction = worktree_root / "junction"
    subprocess.run(
        ("cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(inside_target)),
        check=True,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    verification_worktree = junction / "post-merge-verification"
    command = _pytest_gate(name="post-merge-tests")

    try:
        transaction = port.merge_verify_revert(
            MergeRequest(
                repository_root=repository,
                expected_base_revision=base,
                candidate_revision=candidate,
                reviewed_diff_hash=diff_hash,
                rollback_revision=base,
                changed_paths=("vesper/platform/tui/safe.py",),
            ),
            VerificationRequest(worktree=verification_worktree, commands=(command,)),
        )

        assert transaction.accepted is False
        assert transaction.code == "unsafe-post-merge-verification-worktree"
        assert transaction.merge is None
        assert _git(repository, "rev-parse", "HEAD").stdout.strip() == base
    finally:
        if junction.exists():
            os.rmdir(junction)


@pytest.mark.parametrize("mutation", ("tracked-file", "head"))
def test_post_merge_check_mutation_is_confined_to_disposable_worktree_and_reverts(
    tmp_path: Path,
    mutation: str,
) -> None:
    _, repository, candidate_worktree, base, candidate, diff_hash = _candidate_worktree(tmp_path)
    worktree_root = candidate_worktree.parent
    verification_worktree = worktree_root / "post-merge-verification"
    command = _pytest_gate(name="post-merge-tests")
    observed_check_roots: list[Path] = []

    def runner(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        if argv[0] == "uv":
            check_root = Path(options["cwd"])  # type: ignore[arg-type]
            observed_check_roots.append(check_root)
            if mutation == "tracked-file":
                (check_root / "vesper" / "platform" / "tui" / "safe.py").write_text(
                    "DIRTY = True\n",
                    encoding="utf-8",
                )
            else:
                _git(check_root, "checkout", "--detach", base)
            return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")
        return run_bounded_process(argv, **options)  # type: ignore[arg-type]

    port = LocalGitPort(
        repository,
        worktree_root=worktree_root,
        allowed_verification_commands=(command,),
        runner=runner,
    )

    transaction = port.merge_verify_revert(
        MergeRequest(
            repository_root=repository,
            expected_base_revision=base,
            candidate_revision=candidate,
            reviewed_diff_hash=diff_hash,
            rollback_revision=base,
            changed_paths=("vesper/platform/tui/safe.py",),
        ),
        VerificationRequest(worktree=verification_worktree, commands=(command,)),
    )

    assert transaction.accepted is False
    assert transaction.code == "post-merge-verification-failed-reverted"
    assert transaction.verification is not None and not transaction.verification.accepted
    assert transaction.revert is not None and transaction.revert.accepted
    assert observed_check_roots == [verification_worktree]
    assert not verification_worktree.exists()
    assert _git(repository, "status", "--porcelain").stdout == ""
    assert (repository / "vesper" / "platform" / "tui" / "safe.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"


def test_verification_worktree_setup_failure_reverts_clean_main(tmp_path: Path) -> None:
    _, repository, candidate_worktree, base, candidate, diff_hash = _candidate_worktree(tmp_path)
    worktree_root = candidate_worktree.parent
    verification_worktree = worktree_root / "post-merge-verification"
    command = _pytest_gate(name="post-merge-tests")

    def runner(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        if len(argv) > 4 and argv[3:5] == ("worktree", "add"):
            return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"")
        return run_bounded_process(argv, **options)  # type: ignore[arg-type]

    port = LocalGitPort(
        repository,
        worktree_root=worktree_root,
        allowed_verification_commands=(command,),
        runner=runner,
    )

    transaction = port.merge_verify_revert(
        MergeRequest(
            repository_root=repository,
            expected_base_revision=base,
            candidate_revision=candidate,
            reviewed_diff_hash=diff_hash,
            rollback_revision=base,
            changed_paths=("vesper/platform/tui/safe.py",),
        ),
        VerificationRequest(worktree=verification_worktree, commands=(command,)),
    )

    assert transaction.accepted is False
    assert transaction.code == "post-merge-verification-setup-failed-reverted"
    assert transaction.verification is not None
    assert transaction.verification.code == "verification-worktree-create-failed"
    assert transaction.revert is not None and transaction.revert.accepted
    assert _git(repository, "status", "--porcelain").stdout == ""
    assert not verification_worktree.exists()


def test_partial_verification_worktree_setup_is_cleaned_before_revert(tmp_path: Path) -> None:
    _, repository, candidate_worktree, base, candidate, diff_hash = _candidate_worktree(tmp_path)
    worktree_root = candidate_worktree.parent
    verification_worktree = worktree_root / "post-merge-verification"
    command = _pytest_gate(name="post-merge-tests")

    def runner(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        if len(argv) > 4 and argv[3:5] == ("worktree", "add"):
            created = run_bounded_process(argv, **options)  # type: ignore[arg-type]
            assert created.returncode == 0
            return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"")
        return run_bounded_process(argv, **options)  # type: ignore[arg-type]

    port = LocalGitPort(
        repository,
        worktree_root=worktree_root,
        allowed_verification_commands=(command,),
        runner=runner,
    )

    try:
        transaction = port.merge_verify_revert(
            MergeRequest(
                repository_root=repository,
                expected_base_revision=base,
                candidate_revision=candidate,
                reviewed_diff_hash=diff_hash,
                rollback_revision=base,
                changed_paths=("vesper/platform/tui/safe.py",),
            ),
            VerificationRequest(worktree=verification_worktree, commands=(command,)),
        )

        assert transaction.accepted is False
        assert transaction.code == "post-merge-verification-setup-failed-reverted"
        assert transaction.revert is not None and transaction.revert.accepted
        assert not verification_worktree.exists()
        assert _git(repository, "status", "--porcelain").stdout == ""
    finally:
        if verification_worktree.exists():
            _git(
                repository,
                "worktree",
                "remove",
                "--force",
                "--",
                str(verification_worktree),
            )
        if _git(repository, "rev-parse", "HEAD").stdout.strip() != base:
            parents = _git(repository, "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()
            if len(parents) == 3:
                _git(repository, "revert", "--no-edit", "-m", "1", "HEAD")


def test_verification_status_exception_still_cleans_worktree_and_reverts(
    tmp_path: Path,
) -> None:
    _, repository, candidate_worktree, base, candidate, diff_hash = _candidate_worktree(tmp_path)
    worktree_root = candidate_worktree.parent
    verification_worktree = worktree_root / "post-merge-verification"
    command = _pytest_gate(name="post-merge-tests")
    verification_status_calls = 0

    def runner(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        nonlocal verification_status_calls
        if argv[0] == "uv":
            return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")
        if (
            len(argv) > 3 and argv[3] == "status" and Path(options["cwd"]) == verification_worktree  # type: ignore[arg-type]
        ):
            verification_status_calls += 1
            if verification_status_calls == 2:
                raise BoundedProcessError("injected final verification status failure")
        return run_bounded_process(argv, **options)  # type: ignore[arg-type]

    port = LocalGitPort(
        repository,
        worktree_root=worktree_root,
        allowed_verification_commands=(command,),
        runner=runner,
    )

    try:
        transaction = port.merge_verify_revert(
            MergeRequest(
                repository_root=repository,
                expected_base_revision=base,
                candidate_revision=candidate,
                reviewed_diff_hash=diff_hash,
                rollback_revision=base,
                changed_paths=("vesper/platform/tui/safe.py",),
            ),
            VerificationRequest(worktree=verification_worktree, commands=(command,)),
        )

        assert transaction.accepted is False
        assert transaction.code == "post-merge-verification-failed-reverted"
        assert transaction.revert is not None and transaction.revert.accepted
        assert not verification_worktree.exists()
        assert _git(repository, "status", "--porcelain").stdout == ""
    finally:
        if verification_worktree.exists():
            _git(
                repository,
                "worktree",
                "remove",
                "--force",
                "--",
                str(verification_worktree),
            )
        if _git(repository, "rev-parse", "HEAD").stdout.strip() != base:
            parents = _git(repository, "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()
            if len(parents) == 3:
                _git(repository, "revert", "--no-edit", "-m", "1", "HEAD")


def test_merge_verification_exception_after_mutation_is_reverted(tmp_path: Path) -> None:
    _, repository, candidate_worktree, base, candidate, diff_hash = _candidate_worktree(tmp_path)
    worktree_root = candidate_worktree.parent
    verification_worktree = worktree_root / "post-merge-verification"
    command = _pytest_gate(name="post-merge-tests")
    merge_mutated = False
    failed_status = False

    def runner(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        nonlocal merge_mutated, failed_status
        if len(argv) > 3 and argv[3] == "merge":
            merged = run_bounded_process(argv, **options)  # type: ignore[arg-type]
            assert merged.returncode == 0
            merge_mutated = True
            return merged
        if len(argv) > 3 and argv[3] == "status" and merge_mutated and not failed_status:
            failed_status = True
            raise BoundedProcessError("injected merge verification failure")
        if argv[0] == "uv":
            return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")
        return run_bounded_process(argv, **options)  # type: ignore[arg-type]

    port = LocalGitPort(
        repository,
        worktree_root=worktree_root,
        allowed_verification_commands=(command,),
        runner=runner,
    )

    try:
        transaction = port.merge_verify_revert(
            MergeRequest(
                repository_root=repository,
                expected_base_revision=base,
                candidate_revision=candidate,
                reviewed_diff_hash=diff_hash,
                rollback_revision=base,
                changed_paths=("vesper/platform/tui/safe.py",),
            ),
            VerificationRequest(worktree=verification_worktree, commands=(command,)),
        )

        assert transaction.accepted is False
        assert transaction.code == "merge-verification-failed-manual-recovery-required-reverted"
        assert transaction.merge is not None and transaction.merge.revision is not None
        assert transaction.revert is not None and transaction.revert.accepted
        assert not verification_worktree.exists()
        assert _git(repository, "status", "--porcelain").stdout == ""
    finally:
        if verification_worktree.exists():
            _git(
                repository,
                "worktree",
                "remove",
                "--force",
                "--",
                str(verification_worktree),
            )
        if _git(repository, "rev-parse", "HEAD").stdout.strip() != base:
            parents = _git(repository, "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()
            if len(parents) == 3:
                _git(repository, "revert", "--no-edit", "-m", "1", "HEAD")


def test_verification_worktree_cleanup_failure_is_reported_and_reverts_clean_main(
    tmp_path: Path,
) -> None:
    _, repository, candidate_worktree, base, candidate, diff_hash = _candidate_worktree(tmp_path)
    worktree_root = candidate_worktree.parent
    verification_worktree = worktree_root / "post-merge-verification"
    command = _pytest_gate(name="post-merge-tests")
    removal_calls: list[tuple[str, ...]] = []

    def runner(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        if argv[0] == "uv":
            return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")
        if len(argv) > 4 and argv[3:5] == ("worktree", "remove"):
            removal_calls.append(argv)
            return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"")
        return run_bounded_process(argv, **options)  # type: ignore[arg-type]

    port = LocalGitPort(
        repository,
        worktree_root=worktree_root,
        allowed_verification_commands=(command,),
        runner=runner,
    )

    try:
        transaction = port.merge_verify_revert(
            MergeRequest(
                repository_root=repository,
                expected_base_revision=base,
                candidate_revision=candidate,
                reviewed_diff_hash=diff_hash,
                rollback_revision=base,
                changed_paths=("vesper/platform/tui/safe.py",),
            ),
            VerificationRequest(worktree=verification_worktree, commands=(command,)),
        )

        assert transaction.accepted is False
        assert transaction.code == "post-merge-verification-cleanup-failed-reverted"
        assert transaction.verification is not None and transaction.verification.accepted
        assert transaction.revert is not None and transaction.revert.accepted
        assert removal_calls == [
            (
                "git",
                "-C",
                str(repository),
                "worktree",
                "remove",
                "--force",
                "--",
                str(verification_worktree),
            )
        ]
        assert verification_worktree.exists()
        assert _git(repository, "status", "--porcelain").stdout == ""
    finally:
        if verification_worktree.exists():
            _git(
                repository,
                "worktree",
                "remove",
                "--force",
                "--",
                str(verification_worktree),
            )


def test_push_defaults_disabled_and_requires_exact_confirmation_and_revision(
    tmp_path: Path,
) -> None:
    repository, revision = _repository(tmp_path)
    port = LocalGitPort(repository, worktree_root=tmp_path / "worktrees")

    disabled = port.push(
        "client:push:disabled",
        revision,
        ConfirmationProof(first_confirmed=True),
    )

    assert disabled.accepted is False
    assert disabled.code == "push-disabled"

    enabled = LocalGitPort(
        repository,
        worktree_root=tmp_path / "worktrees",
        push_enabled=True,
        push_remote=str(tmp_path / "unused-bare.git"),
        push_destination="refs/heads/main",
        push_receipt_database=tmp_path / "receipts.sqlite3",
    )
    unconfirmed = enabled.push("client:push:unconfirmed", revision, ConfirmationProof())
    stale = enabled.push(
        "client:push:stale",
        "f" * 40,
        ConfirmationProof(first_confirmed=True),
    )

    assert unconfirmed.accepted is False
    assert unconfirmed.code == "push-confirmation-missing"
    assert stale.accepted is False
    assert stale.code == "push-revision-mismatch"
    assert not (tmp_path / "unused-bare.git").exists()


def test_real_local_git_port_enables_registry_source_control_capability(tmp_path: Path) -> None:
    repository, _revision = _repository(tmp_path)
    bare = tmp_path / "bare.git"
    subprocess.run(
        ("git", "init", "--bare", str(bare)),
        check=True,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    port = LocalGitPort(
        repository,
        worktree_root=tmp_path / "worktrees",
        push_enabled=True,
        push_remote=str(bare),
        push_destination="refs/heads/main",
        push_receipt_database=tmp_path / "bound-receipts.sqlite3",
    )
    registry = CommandRegistry(
        tmp_path / "commands.sqlite3",
        object(),  # type: ignore[arg-type]
        source_control_port=port,
    )

    try:
        capability = next(
            row
            for row in registry.command_capabilities
            if row.capability_id == "source-control.push"
        )
        assert capability.state is CapabilityState.ENABLED
        assert "source-control.push" in registry.enabled_command_types
    finally:
        registry.close()


def test_push_receipt_is_bound_to_registry_command_id(tmp_path: Path) -> None:
    repository, revision = _repository(tmp_path)
    bare = tmp_path / "bare.git"
    subprocess.run(
        ("git", "init", "--bare", str(bare)),
        check=True,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    port = LocalGitPort(
        repository,
        worktree_root=tmp_path / "worktrees",
        push_enabled=True,
        push_remote=str(bare),
        push_destination="refs/heads/main",
        push_receipt_database=tmp_path / "command-bound-receipts.sqlite3",
    )
    receipt = None

    try:
        receipt = port.push(
            "client:push:bound",
            revision,
            ConfirmationProof(first_confirmed=True),
        )
    except TypeError:
        pass

    assert receipt is not None
    assert receipt.accepted is True
    assert receipt.command_id == "client:push:bound"


def test_push_receipt_is_durable_idempotent_and_recoverable(tmp_path: Path) -> None:
    repository, revision = _repository(tmp_path)
    bare = tmp_path / "bare.git"
    subprocess.run(
        ("git", "init", "--bare", str(bare)),
        check=True,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    receipt_database = tmp_path / "receipts" / "source-control.sqlite3"
    push_calls = 0

    def runner(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        nonlocal push_calls
        if len(argv) > 3 and argv[3] == "push":
            push_calls += 1
        return run_bounded_process(argv, **options)  # type: ignore[arg-type]

    port = None
    try:
        port = LocalGitPort(
            repository,
            worktree_root=tmp_path / "worktrees",
            runner=runner,
            push_enabled=True,
            push_remote=str(bare),
            push_destination="refs/heads/main",
            push_receipt_database=receipt_database,
        )
    except TypeError:
        pass
    assert port is not None

    first = port.push(
        "client:push:durable",
        revision,
        ConfirmationProof(first_confirmed=True),
    )
    restarted = LocalGitPort(
        repository,
        worktree_root=tmp_path / "worktrees",
        runner=runner,
        push_enabled=True,
        push_remote=str(bare),
        push_destination="refs/heads/main",
        push_receipt_database=receipt_database,
    )
    second = restarted.push(
        "client:push:durable",
        revision,
        ConfirmationProof(first_confirmed=True),
    )
    recovered = restarted.recover(
        "client:push:durable",
        _push_request("client:push:durable", revision),
    )

    assert first.accepted is True
    assert second == first
    assert recovered == "completed"
    assert push_calls == 1


def test_push_requires_exact_remote_destination_readback(tmp_path: Path) -> None:
    repository, revision = _repository(tmp_path)
    bare = tmp_path / "bare.git"
    subprocess.run(
        ("git", "init", "--bare", str(bare)),
        check=True,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )

    def runner(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        if len(argv) > 3 and argv[3] == "push":
            return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")
        return run_bounded_process(argv, **options)  # type: ignore[arg-type]

    port = LocalGitPort(
        repository,
        worktree_root=tmp_path / "worktrees",
        runner=runner,
        push_enabled=True,
        push_remote=str(bare),
        push_destination="refs/heads/main",
        push_receipt_database=tmp_path / "receipts.sqlite3",
    )

    receipt = port.push(
        "client:push:no-remote-effect",
        revision,
        ConfirmationProof(first_confirmed=True),
    )

    assert receipt.accepted is False
    assert receipt.code == "push-remote-verification-failed"
    remote_ref = subprocess.run(
        ("git", "-C", str(bare), "show-ref", "--verify", "refs/heads/main"),
        check=False,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    assert remote_ref.returncode != 0


@pytest.mark.parametrize("persistence_error", (OSError, sqlite3.OperationalError))
def test_push_reports_completed_when_remote_is_exact_but_receipt_save_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    persistence_error: type[Exception],
) -> None:
    repository, revision = _repository(tmp_path)
    bare = tmp_path / "bare.git"
    subprocess.run(
        ("git", "init", "--bare", str(bare)),
        check=True,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    port = LocalGitPort(
        repository,
        worktree_root=tmp_path / "worktrees",
        push_enabled=True,
        push_remote=str(bare),
        push_destination="refs/heads/main",
        push_receipt_database=tmp_path / "receipts.sqlite3",
    )
    assert port._push_receipts is not None

    def fail_save(_record: object) -> None:
        raise persistence_error("injected persistence failure")

    monkeypatch.setattr(port._push_receipts, "save", fail_save)

    receipt = port.push(
        "client:push:degraded-receipt",
        revision,
        ConfirmationProof(first_confirmed=True),
    )

    assert receipt.accepted is True
    assert receipt.code == "push-completed-receipt-persistence-degraded"
    assert receipt.revision == revision
    assert _git(bare, "rev-parse", "refs/heads/main").stdout.strip() == revision


def test_push_reports_completed_when_local_status_readback_raises(tmp_path: Path) -> None:
    repository, revision = _repository(tmp_path)
    bare = tmp_path / "bare.git"
    subprocess.run(
        ("git", "init", "--bare", str(bare)),
        check=True,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    push_completed = False

    def runner(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        nonlocal push_completed
        if len(argv) > 3 and argv[3] == "push":
            result = run_bounded_process(argv, **options)  # type: ignore[arg-type]
            assert result.returncode == 0
            push_completed = True
            return result
        if push_completed and len(argv) > 3 and argv[3] == "status":
            raise BoundedProcessError("injected local readback failure")
        return run_bounded_process(argv, **options)  # type: ignore[arg-type]

    port = LocalGitPort(
        repository,
        worktree_root=tmp_path / "worktrees",
        runner=runner,
        push_enabled=True,
        push_remote=str(bare),
        push_destination="refs/heads/main",
        push_receipt_database=tmp_path / "receipts.sqlite3",
    )

    receipt = port.push(
        "client:push:local-readback-error",
        revision,
        ConfirmationProof(first_confirmed=True),
    )

    assert receipt.accepted is True
    assert receipt.code == "push-completed-local-verification-degraded"
    assert _git(bare, "rev-parse", "refs/heads/main").stdout.strip() == revision


def test_push_configuration_rejects_direct_remote_helper_syntax(tmp_path: Path) -> None:
    repository, _revision = _repository(tmp_path)

    with pytest.raises(ValueError, match="push remote"):
        LocalGitPort(
            repository,
            worktree_root=tmp_path / "worktrees",
            push_enabled=True,
            push_remote="ext::unsafe-helper",
            push_destination="refs/heads/main",
        )


def test_direct_push_target_rejects_git_url_rewrite_without_redirecting(
    tmp_path: Path,
) -> None:
    repository, revision = _repository(tmp_path)
    approved = tmp_path / "approved.git"
    alternate = tmp_path / "alternate.git"
    for bare in (approved, alternate):
        subprocess.run(
            ("git", "init", "--bare", str(bare)),
            check=True,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    _git(
        repository,
        "config",
        f"url.{alternate}.insteadOf",
        str(approved),
    )
    port = LocalGitPort(
        repository,
        worktree_root=tmp_path / "worktrees",
        push_enabled=True,
        push_remote=str(approved),
        push_destination="refs/heads/main",
        push_receipt_database=tmp_path / "receipts.sqlite3",
    )

    capability = port.available("source-control.push")
    receipt = port.push(
        "client:push:rewrite-rejected",
        revision,
        ConfirmationProof(first_confirmed=True),
    )

    assert capability.state is CapabilityState.DISABLED
    assert capability.reason == "Source-control remote configuration is unsafe."
    assert receipt.accepted is False
    assert receipt.code == "push-remote-unsafe"
    assert (
        subprocess.run(
            ("git", "-C", str(alternate), "show-ref", "--verify", "refs/heads/main"),
            check=False,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        ).returncode
        != 0
    )


def test_named_remote_with_helper_url_disables_capability_without_executing_it(
    tmp_path: Path,
) -> None:
    repository, _revision = _repository(tmp_path)
    _git(repository, "remote", "add", "origin", "ext::unsafe-helper")
    port = LocalGitPort(
        repository,
        worktree_root=tmp_path / "worktrees",
        push_enabled=True,
        push_remote="origin",
        push_destination="refs/heads/main",
        push_receipt_database=tmp_path / "receipts.sqlite3",
    )

    capability = port.available("source-control.push")

    assert capability.state is CapabilityState.DISABLED
    assert capability.reason == "Source-control remote configuration is unsafe."


@pytest.mark.parametrize("unsafe_shape", ("helper", "multiple"))
def test_named_remote_rejects_unsafe_or_multiple_pushurls(
    tmp_path: Path,
    unsafe_shape: str,
) -> None:
    repository, _revision = _repository(tmp_path)
    first = tmp_path / "first.git"
    second = tmp_path / "second.git"
    for bare in (first, second):
        subprocess.run(
            ("git", "init", "--bare", str(bare)),
            check=True,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    _git(repository, "remote", "add", "origin", str(first))
    if unsafe_shape == "helper":
        _git(repository, "config", "--add", "remote.origin.pushurl", "ext::unsafe-helper")
    else:
        _git(repository, "config", "--add", "remote.origin.pushurl", str(first))
        _git(repository, "config", "--add", "remote.origin.pushurl", str(second))
    port = LocalGitPort(
        repository,
        worktree_root=tmp_path / "worktrees",
        push_enabled=True,
        push_remote="origin",
        push_destination="refs/heads/main",
        push_receipt_database=tmp_path / "receipts.sqlite3",
    )

    capability = port.available("source-control.push")

    assert capability.state is CapabilityState.DISABLED
    assert capability.reason == "Source-control remote configuration is unsafe."


def test_named_remote_push_uses_one_exact_validated_pushurl_for_push_and_readback(
    tmp_path: Path,
) -> None:
    repository, revision = _repository(tmp_path)
    bare = tmp_path / "bare.git"
    subprocess.run(
        ("git", "init", "--bare", str(bare)),
        check=True,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    _git(repository, "remote", "add", "origin", str(bare))
    remote_commands: list[tuple[str, ...]] = []

    def runner(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        if len(argv) > 3 and argv[3] in {"push", "ls-remote"}:
            remote_commands.append(argv)
        return run_bounded_process(argv, **options)  # type: ignore[arg-type]

    port = LocalGitPort(
        repository,
        worktree_root=tmp_path / "worktrees",
        runner=runner,
        push_enabled=True,
        push_remote="origin",
        push_destination="refs/heads/main",
        push_receipt_database=tmp_path / "receipts.sqlite3",
    )

    receipt = port.push(
        "client:push:named",
        revision,
        ConfirmationProof(first_confirmed=True),
    )

    assert receipt.accepted is True
    assert remote_commands
    assert all("origin" not in command for command in remote_commands)
    assert all(str(bare) in command for command in remote_commands)


def test_recover_records_completed_push_after_remote_effect_before_local_receipt(
    tmp_path: Path,
) -> None:
    repository, revision = _repository(tmp_path)
    bare = tmp_path / "bare.git"
    subprocess.run(
        ("git", "init", "--bare", str(bare)),
        check=True,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    _git(repository, "push", str(bare), f"{revision}:refs/heads/main")
    push_calls = 0

    def runner(argv: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        nonlocal push_calls
        if len(argv) > 3 and argv[3] == "push":
            push_calls += 1
        return run_bounded_process(argv, **options)  # type: ignore[arg-type]

    port = LocalGitPort(
        repository,
        worktree_root=tmp_path / "worktrees",
        runner=runner,
        push_enabled=True,
        push_remote=str(bare),
        push_destination="refs/heads/main",
        push_receipt_database=tmp_path / "receipts.sqlite3",
    )

    recovered = port.recover(
        "client:push:recovered",
        _push_request("client:push:recovered", revision),
    )
    receipt = port.push(
        "client:push:recovered",
        revision,
        ConfirmationProof(first_confirmed=True),
    )

    assert recovered == "completed"
    assert receipt.accepted is True
    assert receipt.command_id == "client:push:recovered"
    assert push_calls == 0


def test_explicit_confirmed_push_can_target_local_bare_repository(tmp_path: Path) -> None:
    repository, revision = _repository(tmp_path)
    bare = tmp_path / "bare.git"
    subprocess.run(
        ("git", "init", "--bare", str(bare)),
        check=True,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    port = LocalGitPort(
        repository,
        worktree_root=tmp_path / "worktrees",
        push_enabled=True,
        push_remote=str(bare),
        push_destination="refs/heads/main",
        push_receipt_database=tmp_path / "local-bare-receipts.sqlite3",
    )

    receipt = port.push(
        "client:push:local-bare",
        revision,
        ConfirmationProof(first_confirmed=True),
    )

    assert receipt.accepted is True
    assert receipt.code == "push-completed"
    assert _git(bare, "rev-parse", "refs/heads/main").stdout.strip() == revision


def test_exact_push_does_not_follow_tags_even_when_repository_config_enables_it(
    tmp_path: Path,
) -> None:
    repository, revision = _repository(tmp_path)
    bare = tmp_path / "bare.git"
    subprocess.run(
        ("git", "init", "--bare", str(bare)),
        check=True,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    _git(repository, "tag", "-a", "v-unsafe-extra", "-m", "must not follow")
    _git(repository, "config", "push.followTags", "true")
    port = LocalGitPort(
        repository,
        worktree_root=tmp_path / "worktrees",
        push_enabled=True,
        push_remote=str(bare),
        push_destination="refs/heads/main",
        push_receipt_database=tmp_path / "receipts.sqlite3",
    )

    receipt = port.push(
        "client:push:no-follow-tags",
        revision,
        ConfirmationProof(first_confirmed=True),
    )

    assert receipt.accepted is True
    assert _git(bare, "rev-parse", "refs/heads/main").stdout.strip() == revision
    extra_tag = subprocess.run(
        ("git", "-C", str(bare), "show-ref", "--verify", "refs/tags/v-unsafe-extra"),
        check=False,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    assert extra_tag.returncode != 0


@pytest.mark.parametrize(
    "destination",
    (
        "refs/tags/v1",
        "refs/heads/*",
        "refs/heads/main..other",
        "refs/heads/main.lock",
        "refs/heads/-danger",
        "+refs/heads/main",
        ":refs/heads/main",
        "HEAD:refs/heads/main",
        "refs/heads/main:other",
    ),
)
def test_push_configuration_rejects_non_branch_force_and_refspec_shapes(
    tmp_path: Path,
    destination: str,
) -> None:
    repository, _ = _repository(tmp_path)

    with pytest.raises(ValueError, match="push destination"):
        LocalGitPort(
            repository,
            worktree_root=tmp_path / "worktrees",
            push_enabled=True,
            push_remote="origin",
            push_destination=destination,
        )


def test_push_holds_one_transaction_lock_and_pushes_exact_expected_object(
    tmp_path: Path,
) -> None:
    repository, revision = _repository(tmp_path)
    bare = tmp_path / "bare.git"
    subprocess.run(
        ("git", "init", "--bare", str(bare)),
        check=True,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    lock_state = {"held": False, "entries": 0, "exits": 0}
    push_commands: list[tuple[str, ...]] = []

    class TrackingLock:
        def __enter__(self) -> None:
            assert lock_state["held"] is False
            lock_state["held"] = True
            lock_state["entries"] += 1

        def __exit__(self, *_args: object) -> None:
            assert lock_state["held"] is True
            lock_state["held"] = False
            lock_state["exits"] += 1

    def runner(command: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        assert lock_state["held"] is True
        if len(command) > 3 and command[3] == "push":
            push_commands.append(command)
        return run_bounded_process(command, **options)  # type: ignore[arg-type]

    port = LocalGitPort(
        repository,
        worktree_root=tmp_path / "worktrees",
        runner=runner,
        merge_lock_factory=TrackingLock,
        push_enabled=True,
        push_remote=str(bare),
        push_destination="refs/heads/main",
        push_receipt_database=tmp_path / "locked-receipts.sqlite3",
    )

    receipt = port.push(
        "client:push:locked",
        revision,
        ConfirmationProof(first_confirmed=True),
    )

    assert receipt.accepted is True
    assert push_commands == [
        (
            "git",
            "-C",
            str(repository),
            "push",
            "--porcelain",
            "--no-verify",
            "--no-follow-tags",
            "--no-recurse-submodules",
            "--no-push-option",
            "--",
            str(bare),
            f"{revision}:refs/heads/main",
        )
    ]
    assert lock_state == {"held": False, "entries": 1, "exits": 1}


def test_held_transaction_lock_blocks_push_before_git_precheck(tmp_path: Path) -> None:
    repository, revision = _repository(tmp_path)
    runner_calls = 0

    class HeldLock:
        def __enter__(self) -> None:
            raise BlockingIOError("held")

        def __exit__(self, *_args: object) -> None:
            return None

    def runner(command: tuple[str, ...], **options: object) -> subprocess.CompletedProcess[bytes]:
        del command, options
        nonlocal runner_calls
        runner_calls += 1
        raise AssertionError("Git must not run while the transaction lock is held")

    port = LocalGitPort(
        repository,
        worktree_root=tmp_path / "worktrees",
        runner=runner,
        merge_lock_factory=HeldLock,
        push_enabled=True,
        push_remote="origin",
        push_destination="refs/heads/main",
    )

    receipt = port.push(
        "client:push:held-lock",
        revision,
        ConfirmationProof(first_confirmed=True),
    )

    assert receipt.accepted is False
    assert receipt.code == "merge-lock-held"
    assert runner_calls == 0
