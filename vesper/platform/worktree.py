"""Read-only verification of the disposable standalone clone boundary."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class WorktreeBoundaryError(RuntimeError):
    """The requested execution root is not an approved disposable clone."""


@dataclass(frozen=True, slots=True)
class WorktreeContext:
    path: Path
    branch: str
    commit: str
    starting_status: tuple[str, ...]
    standalone_clone: bool


def inspect_worktree(
    path: Path,
    *,
    require_standalone: bool = True,
    require_clean: bool = True,
    required_branch_prefix: str | None = None,
) -> WorktreeContext:
    root = path.resolve()
    if not root.is_dir():
        raise WorktreeBoundaryError("clone path does not exist")
    standalone = (root / ".git").is_dir()
    if require_standalone and not standalone:
        raise WorktreeBoundaryError("execution requires a standalone disposable Git clone")
    if require_standalone:
        common_directory = Path(_git(root, "rev-parse", "--git-common-dir"))
        if not common_directory.is_absolute():
            common_directory = root / common_directory
        if common_directory.resolve() != (root / ".git").resolve():
            raise WorktreeBoundaryError("execution requires a standalone disposable Git clone")
        if not _git_optional(root, "config", "--get", "remote.origin.url"):
            raise WorktreeBoundaryError("disposable clone must retain its origin provenance")
        if any(
            line.startswith("160000 ") for line in _git(root, "ls-files", "--stage").splitlines()
        ):
            raise WorktreeBoundaryError("disposable clone must not contain submodules")
    branch = _git(root, "branch", "--show-current")
    commit = _git(root, "rev-parse", "HEAD")
    status_text = _git(
        root,
        "status",
        "--short",
        "--untracked-files=all",
        "--ignored=matching",
    )
    status = tuple(line for line in status_text.splitlines() if line)
    if not branch:
        raise WorktreeBoundaryError("detached HEAD is not approved for the exercise")
    if required_branch_prefix is not None and not branch.startswith(required_branch_prefix):
        raise WorktreeBoundaryError(f"disposable branch must start with {required_branch_prefix!r}")
    if require_clean and status:
        raise WorktreeBoundaryError("disposable clone must be clean before execution")
    return WorktreeContext(
        path=root,
        branch=branch,
        commit=commit,
        starting_status=status,
        standalone_clone=standalone,
    )


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )
    if completed.returncode != 0:
        raise WorktreeBoundaryError(
            f"Git clone inspection failed: {(completed.stderr or completed.stdout).strip()}"
        )
    return completed.stdout.strip()


def _git_optional(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else ""
