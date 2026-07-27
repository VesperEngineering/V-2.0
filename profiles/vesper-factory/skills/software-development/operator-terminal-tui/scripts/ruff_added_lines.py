#!/usr/bin/env python
"""Report Ruff diagnostics that land on lines added by the current Git diff."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cached",
        action="store_true",
        help="inspect the staged diff instead of the unstaged diff",
    )
    parser.add_argument("--ruff", default="ruff", help="Ruff executable path")
    args = parser.parse_args()

    diff_prefix = ["git", "diff"] + (["--cached"] if args.cached else [])
    names = _run([*diff_prefix, "--name-only", "--", "*.py"])
    if names.returncode != 0:
        print(names.stderr.strip() or "git diff --name-only failed", file=sys.stderr)
        return 2
    files = [line.strip() for line in names.stdout.splitlines() if line.strip()]
    if not files:
        print("PASS: no changed Python files")
        return 0

    patch = _run([*diff_prefix, "--unified=0", "--", *files])
    if patch.returncode != 0:
        print(patch.stderr.strip() or "git diff failed", file=sys.stderr)
        return 2

    added_ranges: dict[str, list[range]] = {}
    current: str | None = None
    for line in patch.stdout.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            continue
        if current is None or not line.startswith("@@"):
            continue
        match = re.search(r"\+(\d+)(?:,(\d+))?", line)
        if not match:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or 1)
        if count:
            added_ranges.setdefault(current, []).append(range(start, start + count))

    try:
        lint = _run([args.ruff, "check", "--output-format=json", *files])
    except FileNotFoundError:
        print(f"Ruff executable not found: {args.ruff}", file=sys.stderr)
        return 2
    try:
        diagnostics = json.loads(lint.stdout or "[]")
    except json.JSONDecodeError:
        print(lint.stderr.strip() or "Ruff did not return JSON", file=sys.stderr)
        return 2

    resolved = {str(Path(path).resolve()).casefold(): path for path in files}
    added: list[tuple[str, int, str, str]] = []
    for row in diagnostics:
        filename = str(Path(row["filename"]).resolve()).casefold()
        relative = resolved.get(filename)
        line = int(row["location"]["row"])
        if relative and any(line in span for span in added_ranges.get(relative, ())):
            added.append((relative, line, row["code"], row["message"]))

    for relative, line, code, message in added:
        print(f"{relative}:{line} {code} {message}")
    if added:
        print(f"FAIL: {len(added)} Ruff diagnostic(s) on added lines")
        return 1
    print(f"PASS: no Ruff diagnostics on added lines across {len(files)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
