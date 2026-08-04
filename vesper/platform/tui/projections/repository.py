"""Read-only repository facts for the operations console."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path

from vesper.platform.tui.ports import SourceSample, SystemFacts
from vesper.platform.tui.process_capture import (
    READ_CHUNK_BYTES as _READ_CHUNK_BYTES,
    BoundedProcessConfigurationError,
    BoundedProcessOutputLimitError,
    BoundedProcessPipesUnavailableError,
    BoundedProcessReadError,
    BoundedProcessStreamCloseError,
    run_bounded_process,
)
from vesper.platform.tui.views import Freshness, RepositoryRow


_MAX_OUTPUT_BYTES = 1024 * 1024
_STATUS_ARGUMENTS = (
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
_BRANCH_ARGUMENTS = ("--no-optional-locks", "rev-parse", "--abbrev-ref", "HEAD")
_REVISION_ARGUMENTS = ("--no-optional-locks", "rev-parse", "--verify", "HEAD")
_WORKTREES_ARGUMENTS = ("--no-optional-locks", "worktree", "list", "--porcelain")
_UNPUSHED_ARGUMENTS = (
    "--no-optional-locks",
    "rev-list",
    "--count",
    "@{upstream}..HEAD",
)
_ALLOWED_ARGUMENTS = frozenset(
    {
        _STATUS_ARGUMENTS,
        _BRANCH_ARGUMENTS,
        _REVISION_ARGUMENTS,
        _WORKTREES_ARGUMENTS,
        _UNPUSHED_ARGUMENTS,
    }
)
_TRUSTED_GIT_CANDIDATES = (
    (
        Path(r"C:\Program Files\Git\cmd\git.exe"),
        Path(r"C:\Program Files\Git\bin\git.exe"),
        Path(r"C:\Program Files (x86)\Git\cmd\git.exe"),
    )
    if os.name == "nt"
    else (Path("/usr/bin/git"), Path("/usr/local/bin/git"))
)
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_PROTECTED_REPOSITORY_ROOTS = (
    (_PROJECT_ROOT / "vesper" / "data" / "massive").resolve(),
    (_PROJECT_ROOT / "vesper" / "data" / "model_research").resolve(),
)
_REVISION_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_FORBIDDEN_BRANCH_CHARACTERS = frozenset(" ~^:?*[\\")
_SERVICES_REASON = "Repository projection does not provide services."
_METRICS_REASON = "Repository projection does not provide system metrics."
_UPSTREAM_REASON = "Git upstream is not configured; unpushed commit count is unknown."


class _RepositoryReadError(RuntimeError):
    pass


_Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _git_environment(source: Mapping[str, str] = os.environ) -> dict[str, str]:
    environment = {
        name: value
        for name in (
            "APPDATA",
            "HOME",
            "LOCALAPPDATA",
            "SYSTEMROOT",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "WINDIR",
        )
        if (value := source.get(name)) is not None
    }
    environment.update(
        {
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "Never",
            "GIT_PAGER": "",
            "LC_ALL": "C",
            "LANG": "C",
        }
    )
    return environment


def _trusted_git_executable() -> Path:
    """Return Git only from fixed operating-system installation paths."""
    for candidate in _TRUSTED_GIT_CANDIDATES:
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved.is_absolute() and resolved.is_file():
            return resolved
    raise _RepositoryReadError("A trusted Git executable is unavailable.")


def _bounded_process_run(
    command: tuple[str, ...],
    *,
    cwd: Path,
    timeout: float,
    shell: bool,
    stdin: int,
    stdout: int,
    stderr: int,
    check: bool,
    env: Mapping[str, str],
) -> subprocess.CompletedProcess[bytes]:
    """Run one process while retaining at most one MiB per output stream."""
    try:
        return run_bounded_process(
            command,
            max_output_bytes=_MAX_OUTPUT_BYTES,
            cwd=cwd,
            timeout=timeout,
            shell=shell,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            check=check,
            env=env,
        )
    except BoundedProcessConfigurationError as exc:
        raise _RepositoryReadError("Unsafe process runner configuration.") from exc
    except BoundedProcessPipesUnavailableError as exc:
        raise _RepositoryReadError("Git output pipes were unavailable.") from exc
    except BoundedProcessStreamCloseError as exc:
        raise _RepositoryReadError("Git output stream did not close.") from exc
    except BoundedProcessOutputLimitError as exc:
        raise _RepositoryReadError("Git output exceeded the safe size limit.") from exc
    except BoundedProcessReadError as exc:
        raise _RepositoryReadError("Git output could not be read.") from exc


def _decode_output(value: bytes) -> str:
    if not isinstance(value, bytes):
        raise _RepositoryReadError("Git output was not bytes.")
    if len(value) > _MAX_OUTPUT_BYTES:
        raise _RepositoryReadError("Git output exceeded the safe size limit.")
    try:
        return value.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise _RepositoryReadError("Git output was not valid UTF-8.") from exc


def _run_git(
    repository_root: Path,
    git_executable: str,
    arguments: tuple[str, ...],
    runner: _Runner,
) -> tuple[int, str, str]:
    if arguments not in _ALLOWED_ARGUMENTS:
        raise _RepositoryReadError("Git command is not allowlisted.")
    command = (git_executable, *arguments)
    try:
        result = runner(
            command,
            cwd=repository_root,
            timeout=5,
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=_git_environment(),
        )
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        raise _RepositoryReadError("Git read command failed.") from exc
    if not isinstance(result, subprocess.CompletedProcess):
        raise _RepositoryReadError("Git runner result was malformed.")
    if type(result.returncode) is not int:
        raise _RepositoryReadError("Git return code was malformed.")
    stdout = _decode_output(result.stdout)
    stderr = _decode_output(result.stderr)
    return result.returncode, stdout, stderr


def _required_output(
    repository_root: Path,
    git_executable: str,
    arguments: tuple[str, ...],
    runner: _Runner,
) -> str:
    returncode, output, _stderr = _run_git(repository_root, git_executable, arguments, runner)
    if returncode != 0:
        raise _RepositoryReadError("Git read command failed.")
    return output


def _valid_branch(value: str) -> bool:
    if value == "HEAD":
        return True
    if (
        not value
        or len(value) > 255
        or value == "@"
        or value.startswith(("-", "/"))
        or value.endswith(("/", "."))
        or ".." in value
        or "@{" in value
        or "//" in value
        or any(
            ord(character) < 32
            or ord(character) == 127
            or character in _FORBIDDEN_BRANCH_CHARACTERS
            for character in value
        )
    ):
        return False
    return all(
        component and not component.startswith(".") and not component.endswith(".lock")
        for component in value.split("/")
    )


def _missing_upstream(error: str) -> bool:
    normalized = error.casefold()
    return "no upstream configured" in normalized or "does not point to a branch" in normalized


class RepositoryProjection:
    """Project one local Git repository without changing it."""

    def __init__(
        self,
        repository_root: Path,
        *,
        clock: Callable[[], datetime] = _utc_now,
        git_executable: str | None = None,
        runner: _Runner | None = None,
    ) -> None:
        if (git_executable is None) != (runner is None):
            raise ValueError("A test Git executable and runner must be injected together.")
        if runner is not None:
            if git_executable != "git":
                raise ValueError("The injected test Git executable must be exactly 'git'.")
            if runner is subprocess.run or runner is _bounded_process_run:
                raise ValueError("The injected test runner must not execute real processes.")
        resolved_root = repository_root.resolve()
        if any(
            resolved_root == protected_root or protected_root in resolved_root.parents
            for protected_root in _PROTECTED_REPOSITORY_ROOTS
        ):
            raise ValueError("A repository projection cannot target protected data.")
        self._repository_root = resolved_root
        self._clock = clock
        self._git_executable = git_executable
        self._runner = runner

    def read(self) -> SourceSample[SystemFacts]:
        try:
            git_executable = self._git_executable or str(_trusted_git_executable())
            runner = self._runner or _bounded_process_run
            status = _required_output(
                self._repository_root, git_executable, _STATUS_ARGUMENTS, runner
            )
            branch_output = _required_output(
                self._repository_root, git_executable, _BRANCH_ARGUMENTS, runner
            ).strip()
            if not _valid_branch(branch_output):
                raise _RepositoryReadError("Git branch output was malformed.")
            revision = _required_output(
                self._repository_root, git_executable, _REVISION_ARGUMENTS, runner
            ).strip()
            if _REVISION_PATTERN.fullmatch(revision) is None:
                raise _RepositoryReadError("Git revision output was malformed.")
            worktree_output = _required_output(
                self._repository_root, git_executable, _WORKTREES_ARGUMENTS, runner
            )
            worktrees = tuple(
                line.removeprefix("worktree ")
                for line in worktree_output.splitlines()
                if line.startswith("worktree ") and line != "worktree "
            )
            if not worktrees:
                raise _RepositoryReadError("Git worktree output was empty.")
            upstream_returncode, upstream_output, upstream_error = _run_git(
                self._repository_root, git_executable, _UNPUSHED_ARGUMENTS, runner
            )
            try:
                observed_at = self._clock()
            except Exception as exc:
                raise _RepositoryReadError("Repository clock failed.") from exc
            row_values = {
                "repository_id": "repository:v20",
                "as_of_utc": observed_at,
                "source": "git",
                "branch": None if branch_output == "HEAD" else branch_output,
                "revision": revision,
                "clean": not bool(status),
                "worktrees": worktrees,
            }
            if upstream_returncode != 0:
                if not _missing_upstream(upstream_error):
                    raise _RepositoryReadError("Git unpushed query failed.")
                row = RepositoryRow(
                    **row_values,
                    freshness=Freshness.STALE,
                    error=_UPSTREAM_REASON,
                    unpushed_commit_count=None,
                )
                facts = SystemFacts(
                    services=None,
                    services_error=_SERVICES_REASON,
                    metrics=None,
                    metrics_error=_METRICS_REASON,
                    repositories=(row,),
                    repositories_error=None,
                )
                return SourceSample(
                    value=facts,
                    freshness=Freshness.STALE,
                    observed_at_utc=observed_at,
                    source="git",
                    error=_UPSTREAM_REASON,
                )
            unpushed_text = upstream_output.strip()
            if not unpushed_text.isascii() or not unpushed_text.isdecimal():
                raise _RepositoryReadError("Git unpushed count was malformed.")
            row = RepositoryRow(
                **row_values,
                freshness=Freshness.FRESH,
                error=None,
                unpushed_commit_count=int(unpushed_text),
            )
            facts = SystemFacts(
                services=None,
                services_error=_SERVICES_REASON,
                metrics=None,
                metrics_error=_METRICS_REASON,
                repositories=(row,),
                repositories_error=None,
            )
            return SourceSample(
                value=facts,
                freshness=Freshness.FRESH,
                observed_at_utc=observed_at,
                source="git",
                error=None,
            )
        except (ValueError, _RepositoryReadError):
            return SourceSample(
                value=None,
                freshness=Freshness.UNAVAILABLE,
                observed_at_utc=None,
                source="git",
                error="Git repository facts are unavailable.",
            )
