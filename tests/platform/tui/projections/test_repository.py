from __future__ import annotations

import importlib
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vesper.platform.tui.views import Freshness


_OBSERVED_AT = datetime(2026, 8, 4, 2, 30, tzinfo=timezone.utc)
_STATUS = (
    "git",
    "--no-optional-locks",
    "-c",
    "core.fsmonitor=false",
    "status",
    "--porcelain=v1",
    "--untracked-files=normal",
    "--ignore-submodules=all",
    "--",
    ".",
    ":(top,exclude)vesper/data/massive",
    ":(top,exclude)vesper/data/massive/**",
    ":(top,exclude)vesper/data/model_research",
    ":(top,exclude)vesper/data/model_research/**",
)
_BRANCH = ("git", "--no-optional-locks", "rev-parse", "--abbrev-ref", "HEAD")
_REVISION = ("git", "--no-optional-locks", "rev-parse", "--verify", "HEAD")
_WORKTREES = ("git", "--no-optional-locks", "worktree", "list", "--porcelain")
_UNPUSHED = (
    "git",
    "--no-optional-locks",
    "rev-list",
    "--count",
    "@{upstream}..HEAD",
)
_EXPECTED_COMMANDS = (_STATUS, _BRANCH, _REVISION, _WORKTREES, _UNPUSHED)


def _completed(argv: tuple[str, ...], stdout: bytes, returncode: int = 0, stderr: bytes = b""):
    return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr=stderr)


def _successful_outputs(repository_root: Path, *, branch: bytes = b"main\n"):
    return {
        _STATUS: _completed(_STATUS, b""),
        _BRANCH: _completed(_BRANCH, branch),
        _REVISION: _completed(
            _REVISION,
            b"91871cfa16a3c2df45e9693a1c4feb164132b46b\n",
        ),
        _WORKTREES: _completed(
            _WORKTREES,
            f"worktree {repository_root.as_posix()}\n".encode(),
        ),
        _UNPUSHED: _completed(_UNPUSHED, b"0\n"),
    }


def test_repository_projection_reads_only_the_exact_git_allowlist(
    tmp_path: Path,
) -> None:
    module = importlib.import_module("vesper.platform.tui.projections.repository")
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    outputs = {
        _STATUS: b" M README.md\n",
        _BRANCH: b"codex/vesper/ratatui-console\n",
        _REVISION: b"20b4a50d3932bb14c2c77208311f14f46232d8f5\n",
        _WORKTREES: (
            f"worktree {repository_root.as_posix()}\n"
            "HEAD 20b4a50d3932bb14c2c77208311f14f46232d8f5\n"
            "branch refs/heads/codex/vesper/ratatui-console\n\n"
            "worktree C:/tmp/second-worktree\n"
            "HEAD 91871cfa16a3c2df45e9693a1c4feb164132b46b\n"
            "branch refs/heads/main\n"
        ).encode(),
        _UNPUSHED: b"3\n",
    }
    calls: list[tuple[str, ...]] = []

    def run(argv, **kwargs):
        command = tuple(argv)
        assert command in _EXPECTED_COMMANDS
        assert kwargs["cwd"] == repository_root.resolve()
        assert kwargs["timeout"] == 5
        assert kwargs["shell"] is False
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["stdout"] is subprocess.PIPE
        assert kwargs["stderr"] is subprocess.PIPE
        assert kwargs["check"] is False
        assert kwargs["env"]["GIT_OPTIONAL_LOCKS"] == "0"
        assert "PATH" not in kwargs["env"]
        assert "ALPACA_API_KEY" not in kwargs["env"]
        assert "ALPACA_API_SECRET" not in kwargs["env"]
        calls.append(command)
        return _completed(command, outputs[command])

    sample = module.RepositoryProjection(
        repository_root,
        clock=lambda: _OBSERVED_AT,
        git_executable="git",
        runner=run,
    ).read()

    assert tuple(calls) == _EXPECTED_COMMANDS
    assert sample.freshness is Freshness.FRESH
    assert sample.observed_at_utc == _OBSERVED_AT
    assert sample.source == "git"
    assert sample.error is None
    assert sample.value is not None
    assert sample.value.services is None
    assert sample.value.services_error == "Repository projection does not provide services."
    assert sample.value.metrics is None
    assert sample.value.metrics_error == "Repository projection does not provide system metrics."
    assert sample.value.repositories_error is None
    assert sample.value.repositories is not None
    assert len(sample.value.repositories) == 1
    row = sample.value.repositories[0]
    assert row.repository_id == "repository:v20"
    assert row.freshness is Freshness.FRESH
    assert row.as_of_utc == _OBSERVED_AT
    assert row.source == "git"
    assert row.error is None
    assert row.branch == "codex/vesper/ratatui-console"
    assert row.revision == "20b4a50d3932bb14c2c77208311f14f46232d8f5"
    assert row.clean is False
    assert row.worktrees == (
        repository_root.as_posix(),
        "C:/tmp/second-worktree",
    )
    assert row.unpushed_commit_count == 3


def test_missing_upstream_is_stale_without_a_fake_zero_count(
    tmp_path: Path,
) -> None:
    module = importlib.import_module("vesper.platform.tui.projections.repository")
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    outputs = {
        _STATUS: _completed(_STATUS, b""),
        _BRANCH: _completed(_BRANCH, b"main\n"),
        _REVISION: _completed(
            _REVISION,
            b"91871cfa16a3c2df45e9693a1c4feb164132b46b\n",
        ),
        _WORKTREES: _completed(
            _WORKTREES,
            f"worktree {repository_root.as_posix()}\n".encode(),
        ),
        _UNPUSHED: _completed(
            _UNPUSHED,
            b"",
            returncode=128,
            stderr=b"fatal: no upstream configured\n",
        ),
    }

    sample = module.RepositoryProjection(
        repository_root,
        clock=lambda: _OBSERVED_AT,
        git_executable="git",
        runner=lambda argv, **_kwargs: outputs[tuple(argv)],
    ).read()

    assert sample.freshness is Freshness.STALE
    assert sample.observed_at_utc == _OBSERVED_AT
    assert sample.error == "Git upstream is not configured; unpushed commit count is unknown."
    assert sample.value is not None
    assert sample.value.repositories_error is None
    assert sample.value.repositories is not None
    assert len(sample.value.repositories) == 1
    row = sample.value.repositories[0]
    assert row.freshness is Freshness.STALE
    assert row.error == sample.error
    assert row.branch == "main"
    assert row.revision == "91871cfa16a3c2df45e9693a1c4feb164132b46b"
    assert row.clean is True
    assert row.worktrees == (repository_root.as_posix(),)
    assert row.unpushed_commit_count is None


def test_unpushed_query_failure_is_not_misreported_as_missing_upstream(
    tmp_path: Path,
) -> None:
    module = importlib.import_module("vesper.platform.tui.projections.repository")
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    outputs = {
        _STATUS: _completed(_STATUS, b""),
        _BRANCH: _completed(_BRANCH, b"main\n"),
        _REVISION: _completed(
            _REVISION,
            b"91871cfa16a3c2df45e9693a1c4feb164132b46b\n",
        ),
        _WORKTREES: _completed(
            _WORKTREES,
            f"worktree {repository_root.as_posix()}\n".encode(),
        ),
        _UNPUSHED: _completed(
            _UNPUSHED,
            b"",
            returncode=128,
            stderr=b"fatal: corrupt revision data\n",
        ),
    }

    sample = module.RepositoryProjection(
        repository_root,
        git_executable="git",
        runner=lambda argv, **_kwargs: outputs[tuple(argv)],
    ).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.value is None
    assert sample.error == "Git repository facts are unavailable."


def test_malformed_branch_output_fails_closed(tmp_path: Path) -> None:
    module = importlib.import_module("vesper.platform.tui.projections.repository")
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    outputs = _successful_outputs(repository_root, branch=b"main\ninjected\n")
    sample = module.RepositoryProjection(
        repository_root,
        git_executable="git",
        runner=lambda argv, **_kwargs: outputs[tuple(argv)],
    ).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.value is None


def test_git_timeout_fails_closed_without_running_more_commands(
    tmp_path: Path,
) -> None:
    module = importlib.import_module("vesper.platform.tui.projections.repository")
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    calls: list[tuple[str, ...]] = []

    def run(argv, **_kwargs):
        calls.append(tuple(argv))
        raise subprocess.TimeoutExpired(argv, 5)

    sample = module.RepositoryProjection(
        repository_root,
        git_executable="git",
        runner=run,
    ).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.value is None
    assert calls == [_STATUS]


def test_git_output_over_one_mibibyte_fails_closed(tmp_path: Path) -> None:
    module = importlib.import_module("vesper.platform.tui.projections.repository")
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    outputs = _successful_outputs(repository_root)
    outputs[_STATUS] = _completed(_STATUS, b"x" * (1024 * 1024 + 1))
    sample = module.RepositoryProjection(
        repository_root,
        git_executable="git",
        runner=lambda argv, **_kwargs: outputs[tuple(argv)],
    ).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.value is None


def test_detached_head_is_not_claimed_as_a_branch(tmp_path: Path) -> None:
    module = importlib.import_module("vesper.platform.tui.projections.repository")
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    outputs = _successful_outputs(repository_root, branch=b"HEAD\n")
    sample = module.RepositoryProjection(
        repository_root,
        git_executable="git",
        runner=lambda argv, **_kwargs: outputs[tuple(argv)],
    ).read()

    assert sample.freshness is Freshness.FRESH
    assert sample.value is not None
    assert sample.value.repositories is not None
    assert sample.value.repositories[0].branch is None


@pytest.mark.parametrize(
    "branch",
    (
        b"bad branch\n",
        b"-unsafe\n",
        b"main..other\n",
        b"main.lock\n",
        b"main/@{upstream}\n",
        b"main\\other\n",
    ),
)
def test_invalid_git_ref_is_not_rendered_as_a_branch(
    tmp_path: Path,
    branch: bytes,
) -> None:
    module = importlib.import_module("vesper.platform.tui.projections.repository")
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    outputs = _successful_outputs(repository_root, branch=branch)
    sample = module.RepositoryProjection(
        repository_root,
        git_executable="git",
        runner=lambda argv, **_kwargs: outputs[tuple(argv)],
    ).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.value is None


def test_detached_head_without_upstream_keeps_known_repository_facts(
    tmp_path: Path,
) -> None:
    module = importlib.import_module("vesper.platform.tui.projections.repository")
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    outputs = _successful_outputs(repository_root, branch=b"HEAD\n")
    outputs[_UNPUSHED] = _completed(
        _UNPUSHED,
        b"",
        returncode=128,
        stderr=b"fatal: HEAD does not point to a branch\n",
    )
    sample = module.RepositoryProjection(
        repository_root,
        git_executable="git",
        runner=lambda argv, **_kwargs: outputs[tuple(argv)],
    ).read()

    assert sample.freshness is Freshness.STALE
    assert sample.value is not None
    assert sample.value.repositories is not None
    row = sample.value.repositories[0]
    assert row.branch is None
    assert row.unpushed_commit_count is None


def test_default_runner_uses_a_trusted_absolute_git_executable(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = importlib.import_module("vesper.platform.tui.projections.repository")
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    trusted_git = Path(r"C:\Program Files\Git\cmd\git.exe")
    calls: list[tuple[str, ...]] = []

    def run(argv, **_kwargs):
        command = tuple(argv)
        calls.append(command)
        fake_command = ("git", *command[1:])
        return _successful_outputs(repository_root)[fake_command]

    monkeypatch.setattr(module, "_trusted_git_executable", lambda: trusted_git)
    monkeypatch.setattr(module, "_bounded_process_run", run)

    sample = module.RepositoryProjection(repository_root).read()

    assert sample.freshness is Freshness.FRESH
    assert calls
    assert all(Path(command[0]).is_absolute() for command in calls)
    assert all(command[0] == str(trusted_git) for command in calls)


def test_trusted_git_resolution_ignores_caller_path(monkeypatch, tmp_path: Path) -> None:
    module = importlib.import_module("vesper.platform.tui.projections.repository")
    trusted_git = tmp_path / "fixed" / "git.exe"
    trusted_git.parent.mkdir()
    trusted_git.touch()
    path_git = tmp_path / "caller-path" / "git.exe"
    path_git.parent.mkdir()
    path_git.touch()
    monkeypatch.setenv("PATH", str(path_git.parent))
    monkeypatch.setattr(module, "_TRUSTED_GIT_CANDIDATES", (trusted_git,))

    assert module._trusted_git_executable() == trusted_git.resolve()


def test_bounded_runner_streams_and_rejects_output_before_buffering_it_all(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = importlib.import_module("vesper.platform.tui.projections.repository")

    class ChunkedStream:
        def __init__(self, remaining: int) -> None:
            self.remaining = remaining
            self.largest_read = 0
            self.closed = False
            self._lock = threading.Lock()

        def read(self, size: int) -> bytes:
            with self._lock:
                self.largest_read = max(self.largest_read, size)
                if self.remaining == 0:
                    return b""
                amount = min(size, self.remaining)
                self.remaining -= amount
                return b"x" * amount

        def close(self) -> None:
            self.closed = True

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = ChunkedStream(module._MAX_OUTPUT_BYTES + 1)
            self.stderr = ChunkedStream(0)
            self.returncode = 0

        def wait(self, timeout=None):
            return self.returncode

        def terminate(self) -> None:
            self.returncode = -1

        def kill(self) -> None:
            self.returncode = -9

        def communicate(self, *_args, **_kwargs):
            raise AssertionError("communicate() would buffer unbounded output")

    process = FakeProcess()
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: process)

    with pytest.raises(module._RepositoryReadError, match="safe size limit"):
        module._bounded_process_run(
            (r"C:\Program Files\Git\cmd\git.exe", "status"),
            cwd=tmp_path,
            timeout=5,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env={},
        )

    assert process.stdout.largest_read <= module._READ_CHUNK_BYTES
    assert process.stderr.largest_read <= module._READ_CHUNK_BYTES


def test_clock_failure_makes_repository_facts_unavailable(tmp_path: Path) -> None:
    module = importlib.import_module("vesper.platform.tui.projections.repository")
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    outputs = _successful_outputs(repository_root)

    def broken_clock() -> datetime:
        raise RuntimeError("clock unavailable")

    sample = module.RepositoryProjection(
        repository_root,
        clock=broken_clock,
        git_executable="git",
        runner=lambda argv, **_kwargs: outputs[tuple(argv)],
    ).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.observed_at_utc is None
    assert sample.value is None
    assert sample.error == "Git repository facts are unavailable."


def test_test_runner_seam_rejects_executable_substitution(tmp_path: Path) -> None:
    module = importlib.import_module("vesper.platform.tui.projections.repository")

    with pytest.raises(ValueError, match="test Git executable"):
        module.RepositoryProjection(
            tmp_path,
            git_executable="cmd.exe",
            runner=lambda *_args, **_kwargs: None,
        )


@pytest.mark.parametrize("runner_name", ("subprocess", "default"))
def test_test_runner_seam_rejects_real_process_runners(
    tmp_path: Path,
    runner_name: str,
) -> None:
    module = importlib.import_module("vesper.platform.tui.projections.repository")
    runner = subprocess.run if runner_name == "subprocess" else module._bounded_process_run

    with pytest.raises(ValueError, match="test runner"):
        module.RepositoryProjection(tmp_path, git_executable="git", runner=runner)


def test_runner_runtime_error_makes_repository_facts_unavailable(tmp_path: Path) -> None:
    module = importlib.import_module("vesper.platform.tui.projections.repository")

    def broken_runner(*_args, **_kwargs):
        raise RuntimeError("runner failed")

    sample = module.RepositoryProjection(
        tmp_path,
        git_executable="git",
        runner=broken_runner,
    ).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.value is None


def test_runner_returncode_must_be_an_integer(tmp_path: Path) -> None:
    module = importlib.import_module("vesper.platform.tui.projections.repository")

    def invalid_runner(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, "0", stdout=b"", stderr=b"")

    with pytest.raises(module._RepositoryReadError, match="return code"):
        module._run_git(
            tmp_path,
            "git",
            module._STATUS_ARGUMENTS,
            invalid_runner,
        )


def test_malformed_runner_result_makes_repository_facts_unavailable(tmp_path: Path) -> None:
    module = importlib.import_module("vesper.platform.tui.projections.repository")

    sample = module.RepositoryProjection(
        tmp_path,
        git_executable="git",
        runner=lambda *_args, **_kwargs: object(),
    ).read()

    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.observed_at_utc is None
    assert sample.value is None
    assert sample.error == "Git repository facts are unavailable."


def test_canonical_protected_repository_root_is_rejected(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = importlib.import_module("vesper.platform.tui.projections.repository")
    protected_root = tmp_path / "vesper" / "data" / "massive"
    repository_root = protected_root / "nested"
    repository_root.mkdir(parents=True)
    monkeypatch.setattr(module, "_PROTECTED_REPOSITORY_ROOTS", (protected_root.resolve(),))

    with pytest.raises(ValueError, match="protected data"):
        module.RepositoryProjection(
            repository_root,
            git_executable="git",
            runner=lambda *_args, **_kwargs: None,
        )
