#!/usr/bin/env python
"""Create deterministic read-only manifests for a source bundle.

The script never imports target code and never writes inside the target.
Run it before and after a strict no-modification audit and compare JSON output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable

DEFAULT_DEPENDENCY_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "vendor",
    "third_party",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".cache",
}
VOLATILE_DIRS = {"__pycache__", "data", "logs", "coverage", "artifacts", "receipts"}
VOLATILE_SUFFIXES = {".pyc", ".pyo", ".coverage"}


def iter_entries(root: Path, excluded_dirs: set[str]) -> Iterable[Path]:
    for base, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        base_path = Path(base)
        kept_dirs = []
        for name in sorted(dirnames):
            path = base_path / name
            if name in excluded_dirs:
                continue
            if path.is_symlink():
                yield path
            else:
                kept_dirs.append(name)
        dirnames[:] = kept_dirs
        for name in sorted(filenames):
            yield base_path / name


def is_source_scope(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if any(part in VOLATILE_DIRS for part in rel.parts[:-1]):
        return False
    return path.suffix.lower() not in VOLATILE_SUFFIXES


def build_manifest(root: Path, entries: list[Path]) -> dict:
    content = hashlib.sha256()
    metadata = hashlib.sha256()
    total_bytes = 0
    symlinks = []

    for path in sorted(entries, key=lambda p: p.relative_to(root).as_posix().casefold()):
        rel = path.relative_to(root).as_posix()
        st = path.lstat()
        metadata.update(f"{rel}\0{st.st_size}\0{st.st_mtime_ns}\0{st.st_mode}\0".encode())
        content.update(rel.encode() + b"\0")

        if path.is_symlink():
            target = os.readlink(path)
            symlinks.append({"path": rel, "target": target})
            content.update(b"SYMLINK\0" + target.encode(errors="surrogateescape") + b"\0")
            continue

        total_bytes += st.st_size
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                content.update(block)
        content.update(b"\0")

    return {
        "file_or_symlink_count": len(entries),
        "total_regular_file_bytes": total_bytes,
        "content_sha256": content.hexdigest(),
        "metadata_sha256": metadata.hexdigest(),
        "symlinks": symlinks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", help="Source-bundle directory to inspect")
    parser.add_argument(
        "--exclude-dir",
        action="append",
        default=[],
        help="Additional directory basename to prune; may be repeated",
    )
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        parser.error(f"not a directory: {root}")

    excluded = DEFAULT_DEPENDENCY_DIRS | set(args.exclude_dir)
    entries = list(iter_entries(root, excluded))
    source_entries = [p for p in entries if is_source_scope(p, root)]
    volatile = sorted(
        p.relative_to(root).as_posix()
        for p in entries
        if (
            any(part in VOLATILE_DIRS for part in p.relative_to(root).parts)
            or p.suffix.lower() in VOLATILE_SUFFIXES
        )
    )

    result = {
        "schema_version": 1,
        "root": str(root),
        "git_directory_present": (root / ".git").exists(),
        "top_level": sorted(p.name for p in root.iterdir()),
        "excluded_dependency_dir_basenames": sorted(excluded),
        "all_non_dependency_scope": build_manifest(root, entries),
        "source_scope": build_manifest(root, source_entries),
        "volatile_artifact_count": len(volatile),
        "volatile_artifacts_first_200": volatile[:200],
        "volatile_artifacts_truncated": len(volatile) > 200,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
