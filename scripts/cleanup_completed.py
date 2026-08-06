"""Preview or remove generated V20 task artifacts without touching source."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


SAFE_DIRECTORY_NAMES = {
    ".codegraph",
    ".pytest_cache",
    ".pytest_tmp",
    ".ruff_cache",
    ".state",
    ".tmp",
    "target",
    "tmp",
}
SAFE_DIRECTORY_PREFIXES = (".pytest-tmp-", ".tmp-", ".uv-cache")
SAFE_DIRECTORY_SUFFIXES = (".egg-info",)
SKIP_DIRECTORY_NAMES = {".git", ".venv", "node_modules"}
PROTECTED_DATA_NAMES = {"massive", "model_research"}


class CleanupError(ValueError):
    """Raised when a requested cleanup path fails a safety check."""


@dataclass(frozen=True)
class Candidate:
    path: Path
    size_bytes: int | None


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _is_protected(path: Path, repo_root: Path) -> bool:
    relative = path.relative_to(repo_root)
    parts = tuple(part.lower() for part in relative.parts)
    return any(
        parts[index : index + 3] == ("vesper", "data", protected)
        for index in range(max(0, len(parts) - 2))
        for protected in PROTECTED_DATA_NAMES
    )


def _is_safe_name(name: str) -> bool:
    return (
        name in SAFE_DIRECTORY_NAMES
        or name.startswith(SAFE_DIRECTORY_PREFIXES)
        or name.endswith(SAFE_DIRECTORY_SUFFIXES)
    )


def _validate_root(repo_root: Path, requested: Path) -> Path:
    resolved = requested.resolve()
    if not _is_within(resolved, repo_root):
        raise CleanupError(f"outside repository: {resolved}")
    if not resolved.exists() or not resolved.is_dir():
        raise CleanupError(f"cleanup path is not a directory: {resolved}")
    if _is_protected(resolved, repo_root):
        raise CleanupError(f"protected data path: {resolved}")
    if resolved.is_symlink():
        raise CleanupError(f"refusing symlink: {resolved}")
    return resolved


def _resolve_requested_path(repo_root: Path, raw_path: str) -> Path:
    requested = Path(raw_path)
    if not requested.is_absolute():
        requested = repo_root / requested
    return _validate_root(repo_root, requested)


def _git_status(path: Path) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "-c",
            "safe.directory=*",
            "-C",
            str(path),
            "status",
            "--porcelain",
            "--untracked-files=normal",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "git status failed"
        raise CleanupError(f"cannot read worktree status for {path}: {detail}")
    return [line for line in result.stdout.splitlines() if line.strip()]


def _directory_size(path: Path) -> int | None:
    total = 0
    unreadable = False

    def onerror(_: OSError) -> None:
        nonlocal unreadable
        unreadable = True

    try:
        for current, _, file_names in os.walk(path, topdown=True, onerror=onerror):
            for file_name in file_names:
                try:
                    total += (Path(current) / file_name).stat().st_size
                except OSError:
                    unreadable = True
    except OSError:
        unreadable = True
    return None if unreadable else total


def _walk_candidates(root: Path, repo_root: Path) -> Iterable[Path]:
    if _is_safe_name(root.name):
        yield root
        return

    if root == repo_root:
        try:
            children = list(root.iterdir())
        except (OSError, PermissionError) as exc:
            raise CleanupError(f"cannot inspect {root}: {exc}") from exc
        for child in children:
            if child.is_dir() and not child.is_symlink() and _is_safe_name(child.name):
                yield child
        return

    def onerror(exc: OSError) -> None:
        raise CleanupError(f"cannot inspect {root}: {exc}") from exc

    for current, directory_names, _ in os.walk(root, topdown=True, onerror=onerror):
        current_path = Path(current)
        for directory_name in list(directory_names):
            child = current_path / directory_name
            if directory_name in SKIP_DIRECTORY_NAMES:
                directory_names.remove(directory_name)
                continue
            if _is_protected(child, repo_root):
                directory_names.remove(directory_name)
                continue
            if _is_safe_name(directory_name):
                directory_names.remove(directory_name)
                if not child.is_symlink():
                    yield child


def find_candidates(repo_root: Path, requested_paths: Sequence[str]) -> list[Candidate]:
    repo_root = repo_root.resolve()
    if not repo_root.is_dir():
        raise CleanupError(f"repository root is not a directory: {repo_root}")

    candidates: dict[Path, Candidate] = {}
    for raw_path in requested_paths:
        root = _resolve_requested_path(repo_root, raw_path)
        for path in _walk_candidates(root, repo_root):
            candidates[path] = Candidate(path=path, size_bytes=_directory_size(path))
    return sorted(candidates.values(), key=lambda candidate: str(candidate.path).lower())


def _size_text(size_bytes: int | None) -> str:
    if size_bytes is None:
        return "unreadable"
    return f"{size_bytes / (1024**3):.3f} GB"


def _remove(candidates: Sequence[Candidate]) -> None:
    for candidate in candidates:
        if candidate.size_bytes is None:
            raise CleanupError(f"refusing unreadable candidate: {candidate.path}")
        if not candidate.path.exists() or not candidate.path.is_dir():
            raise CleanupError(f"candidate changed before removal: {candidate.path}")
        if candidate.path.is_symlink():
            raise CleanupError(f"refusing symlink: {candidate.path}")
        shutil.rmtree(candidate.path)
        print(f"REMOVED {candidate.path} ({_size_text(candidate.size_bytes)})")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preview or remove generated V20 task artifacts. Source is never a candidate."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (default: this checkout)",
    )
    parser.add_argument(
        "--path",
        action="append",
        required=True,
        help="directory to inspect; repeat for multiple worktrees or generated paths",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="remove listed generated directories; default is dry-run",
    )
    parser.add_argument(
        "--done",
        action="store_true",
        help="require a clean Git path, then remove generated cleanup candidates",
    )
    args = parser.parse_args(argv)

    try:
        if args.done and args.apply:
            raise CleanupError("--done and --apply cannot be combined")
        candidates = find_candidates(args.repo_root, args.path)
        if args.done:
            repo_root = args.repo_root.resolve()
            for raw_path in args.path:
                worktree = _resolve_requested_path(repo_root, raw_path)
                status = _git_status(worktree)
                if status:
                    raise CleanupError(
                        f"dirty worktree {worktree} ({len(status)} entries)"
                    )
            if candidates:
                _remove(candidates)
                print("DONE OK: generated cleanup applied; Git worktree is clean.")
                return 0
            print("DONE OK: no Git changes or generated cleanup candidates.")
            return 0
        if not candidates:
            print("No generated cleanup candidates found.")
            return 0
        if args.apply:
            _remove(candidates)
        else:
            for candidate in candidates:
                print(f"DRY-RUN {candidate.path} ({_size_text(candidate.size_bytes)})")
        return 0
    except CleanupError as exc:
        print(f"CLEANUP REFUSED: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
