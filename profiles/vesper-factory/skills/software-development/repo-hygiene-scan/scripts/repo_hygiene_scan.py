#!/usr/bin/env python3
"""Repo hygiene scanner — read-only dead-file / junk candidate finder.

Enumerates tracked files via ``git ls-files`` (bounded, avoids rglob timeouts),
builds a reference corpus, and counts references per module stem with a
single-pass alternation regex. Emits CANDIDATES, not verdicts — every candidate
must be individually re-grepped per the SKILL.md false-positive traps before
being rated dead.

Read-only: never deletes, moves, or modifies anything.

Usage:
    python repo_hygiene_scan.py --root D:/vesper
    python repo_hygiene_scan.py --root D:/vesper --include-untracked --json out.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Extensions treated as importable/referenceable source or config.
CODE_EXTS = {
    ".py", ".ps1", ".bat", ".cmd", ".vbs", ".js", ".ts", ".tsx", ".sh",
    ".json", ".yaml", ".yml", ".xml", ".toml", ".cfg", ".ini",
}
DOC_EXTS = {".md", ".txt", ".rst"}
# Dirs never scanned for candidates or corpus (generated / heavy / external).
PRUNE_DIRS = {
    ".worktrees", ".git", "node_modules", ".venv", "venv", "__pycache__",
    ".pytest_cache", ".ruff_cache", ".pytest_run", ".pt", "dist", "build",
    "out", "output", "tmp", "logs",
}
# Top-level dirs that hold executable source candidates.
CANDIDATE_TOPS = ("app", "deploy", "backend", "scheduler", "scripts", "desktop")


def git_tracked(root: Path) -> list[str]:
    """Return tracked file paths (POSIX, relative), excluding worktree sandboxes."""
    try:
        out = subprocess.run(
            ["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True
        ).stdout
    except (subprocess.CalledProcessError, OSError) as exc:
        sys.exit(f"error: git ls-files failed in {root}: {exc}")
    return [
        line.strip()
        for line in out.splitlines()
        if line.strip() and not line.startswith(".worktrees/")
    ]


def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def build_corpus(root: Path, tracked: list[str], tops: tuple[str, ...] | None,
                 exts: set[str]) -> dict[str, str]:
    """Concatenate matching tracked files into {relpath: text}."""
    corpus: dict[str, str] = {}
    for t in tracked:
        if "__pycache__" in t:
            continue
        if tops is not None and t.split("/")[0] not in tops:
            continue
        if Path(t).suffix.lower() not in exts:
            continue
        corpus[t] = read_text(root / t)
    return corpus


def count_stems(stems: list[str], corpus: dict[str, str]) -> dict[str, int]:
    """Single-pass alternation count of each stem across the concatenated corpus."""
    if not stems:
        return {}
    blob = "\n".join(corpus.values())
    alt = re.compile(r"\b(" + "|".join(re.escape(s) for s in stems) + r")\b")
    counts: dict[str, int] = {}
    for m in alt.finditer(blob):
        counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    return counts


def find_orphaned_pyc(root: Path) -> list[dict]:
    """A .pyc whose sibling .py source no longer exists.

    Walks the pruned tree but deliberately KEEPS __pycache__ dirs (we must
    descend into them to read the .pyc files); other generated dirs are pruned.
    """
    orphans = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune heavy/generated dirs but KEEP __pycache__ (that's what we scan).
        dirnames[:] = [
            d for d in dirnames
            if d == "__pycache__" or d not in PRUNE_DIRS
        ]
        if "__pycache__" not in dirpath:
            continue
        for fn in filenames:
            if not fn.endswith(".pyc"):
                continue
            # module.cpython-311.pyc -> module.py one level up
            base = fn.split(".cpython-")[0]
            src = Path(dirpath).parent / (base + ".py")
            if not src.exists():
                p = Path(dirpath) / fn
                orphans.append({
                    "path": str(p.relative_to(root)),
                    "size": p.stat().st_size,
                    "reason": "orphaned bytecode (source removed)",
                    "confidence": "CONFIRMED-DEAD",
                })
    return orphans


def find_junk(root: Path, include_untracked: bool) -> list[dict]:
    """Redirect artifacts, backups, swap files. Respects tracked set unless sweeping."""
    junk_names = {"nul"}
    junk_suffix = (".bak", ".old", ".orig", "~", ".tmp")
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS]
        for fn in filenames:
            is_junk = fn in junk_names or fn.endswith(junk_suffix) or \
                fn.endswith(("_old.py", "_copy.py", "-old.py"))
            if not is_junk:
                continue
            p = Path(dirpath) / fn
            out.append({
                "path": str(p.relative_to(root)),
                "size": p.stat().st_size,
                "reason": "junk/backup artifact",
                "confidence": "CONFIRMED-DEAD",
            })
    return out


def version_chains(candidates: list[str], code_counts: dict[str, int],
                   doc_counts: dict[str, int]) -> list[dict]:
    """Flag older _vN / vN versions superseded by a newer referenced version."""
    out = []
    groups: dict[str, list[tuple[int, str]]] = {}
    ver = re.compile(r"^(.*?)[_ ]?v(\d+)$")
    for c in candidates:
        stem = Path(c).stem
        m = ver.match(stem)
        if m:
            groups.setdefault(m.group(1), []).append((int(m.group(2)), c))
    for base, vers in groups.items():
        if len(vers) < 2:
            continue
        vers.sort()
        newest_path = vers[-1][1]
        newest_stem = Path(newest_path).stem
        newest_live = code_counts.get(newest_stem, 0) > 0 or doc_counts.get(newest_stem, 0) > 0
        for _, old_path in vers[:-1]:
            old_stem = Path(old_path).stem
            if code_counts.get(old_stem, 0) == 0:
                out.append({
                    "path": old_path,
                    "reason": f"superseded by {newest_stem} (newest {'referenced' if newest_live else 'UNREFERENCED — whole chain UNCERTAIN'})",
                    "confidence": "LIKELY-DEAD" if newest_live else "UNCERTAIN",
                })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only repo hygiene scanner")
    ap.add_argument("--root", required=True, help="repo root (e.g. D:/vesper)")
    ap.add_argument("--include-untracked", action="store_true",
                    help="also sweep untracked/git-ignored areas for junk + orphaned pyc")
    ap.add_argument("--json", metavar="PATH", help="write machine-readable results to PATH")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not (root / ".git").exists():
        print(f"warning: {root} has no .git; git ls-files may fail", file=sys.stderr)

    tracked = git_tracked(root)

    # Candidate modules: tracked .py under executable-source top dirs.
    candidates = [
        t for t in tracked
        if t.endswith(".py") and t.split("/")[0] in CANDIDATE_TOPS
        and Path(t).stem != "__init__" and "__pycache__" not in t
    ]

    # Reference corpora: all code/config source, and docs.
    code_corpus = build_corpus(root, tracked, None, CODE_EXTS | DOC_EXTS)
    doc_corpus = build_corpus(
        root, tracked,
        ("docs", ".hermes", ".agents", ".memory-bank", "knowledge"),
        DOC_EXTS | CODE_EXTS,
    )
    # Root-level docs also count as doc authority.
    for t in tracked:
        if "/" not in t and Path(t).suffix.lower() in DOC_EXTS | {".toml", ".json"}:
            doc_corpus[t] = read_text(root / t)

    stems = sorted({Path(c).stem for c in candidates}, key=len, reverse=True)
    code_counts = count_stems(stems, code_corpus)
    doc_counts = count_stems(stems, doc_corpus)

    code_blob = "\n".join(code_corpus.values())

    # Build ONE combined alternation over all candidate dotted module paths and
    # count import-style references in a single pass (O(blob), not O(N×blob)).
    # A real import uses the dotted path: ``from app.factors.trends import ...``
    # or ``import app.factors.trends``. Bare stem matches are too noisy (a
    # module named ``exceptions`` would match ``return_exceptions=True``).
    dotted_of = {c: c[:-3].replace("/", ".") for c in candidates}
    dpaths = sorted(set(dotted_of.values()), key=len, reverse=True)
    import_counts: dict[str, int] = {}
    if dpaths:
        alt = re.compile(
            r"(?:from\s+|import\s+)(" + "|".join(re.escape(d) for d in dpaths) + r")(?:\s+import|\b)"
        )
        for m in alt.finditer(code_blob):
            import_counts[m.group(1)] = import_counts.get(m.group(1), 0) + 1

    # Module candidates with zero code refs.
    # Liveness gate = authoritative dotted-path import. The bare-stem count is
    # only a SECONDARY signal and is unreliable for stems that are also common
    # English words (``exceptions``, ``base``, ``utils``) — it matches prose and
    # comments, not imports. So: a module is a dead-file CANDIDATE when its
    # dotted-path import count is zero; we additionally require the stem to not
    # be a known-noisy common word before trusting the stem signal at all.
    NOISY_STEMS = {
        "exceptions", "base", "utils", "common", "helpers", "types", "models",
        "config", "constants", "state", "errors", "main", "cli",
    }
    zero_ref = []
    for c in candidates:
        stem = Path(c).stem
        import_refs = import_counts.get(dotted_of[c], 0)
        if import_refs > 0:
            continue  # definitively live — imported by path
        self_occ = len(re.findall(r"\b" + re.escape(stem) + r"\b", read_text(root / c)))
        stem_refs = code_counts.get(stem, 0) - self_occ
        doc_refs = doc_counts.get(stem, 0)
        # For noisy (common-word) stems, the bare-stem count is meaningless —
        # treat as candidate on the (zero) import count alone. For distinctive
        # stems, allow stem_refs <= 1: a single hit is almost always a string
        # key / prose mention (e.g. a JSON key in a retired dashboard), not an
        # import — flag it for verification. stem_refs > 1 means the name is
        # genuinely referenced by name elsewhere; keep it out of the dead list.
        has_main = "__main__" in read_text(root / c)
        if stem in NOISY_STEMS:
            is_candidate, note = True, "noisy-stem"
        elif stem_refs <= 0:
            is_candidate, note = True, "zero-stem"
        elif stem_refs == 1:
            # Lone hit — likely a string key or doc mention, NOT an import
            # (import gate already passed zero). Surface for manual verify.
            is_candidate, note = True, "stem-match-x1-verify"
        else:
            is_candidate, note = False, ""
        if is_candidate:
            zero_ref.append({
                "path": c,
                "doc_refs": doc_refs,
                "has_main": has_main,
                "note": note,
                "confidence": "UNCERTAIN" if has_main else ("LIKELY-DEAD" if doc_refs else "CANDIDATE-CONFIRMED"),
                "reason": "zero code refs (verify exact import + registry + dynamic load)",
            })

    results = {
        "root": str(root),
        "scanned_tracked_files": len(tracked),
        "candidate_modules": len(candidates),
        "zero_code_ref_candidates": sorted(zero_ref, key=lambda r: (r["doc_refs"] > 0, r["path"])),
        "orphaned_pyc": find_orphaned_pyc(root),
        "junk": find_junk(root, args.include_untracked),
        "version_chains": version_chains(candidates, code_counts, doc_counts),
    }

    # ---- report ----
    print(f"Repo hygiene scan — {root}")
    print(f"  tracked files scanned : {results['scanned_tracked_files']}")
    print(f"  candidate modules     : {results['candidate_modules']}")
    print()
    print(f"== Zero-code-ref module candidates ({len(zero_ref)}) — VERIFY before rating ==")
    for r in results["zero_code_ref_candidates"]:
        note = f", {r['note']}" if r.get("note") else ""
        print(f"  [{r['confidence']:>20}] {r['path']}  (doc_refs={r['doc_refs']}, main={r['has_main']}{note})")
    print()
    print(f"== Orphaned .pyc ({len(results['orphaned_pyc'])}) — source removed ==")
    for r in results["orphaned_pyc"]:
        print(f"  {r['path']}  ({r['size']} B)")
    print()
    print(f"== Junk / backup artifacts ({len(results['junk'])}) ==")
    for r in results["junk"]:
        print(f"  {r['path']}  ({r['size']} B)")
    print()
    print(f"== Superseded version chains ({len(results['version_chains'])}) ==")
    for r in results["version_chains"]:
        print(f"  [{r['confidence']:>10}] {r['path']}  — {r['reason']}")
    print()
    print("REMINDER: these are CANDIDATES. Re-grep each with the exact import")
    print("statement and check RETIRED markers, registries, dynamic loaders, and")
    print("external scheduler paths before rating anything dead. Read-only scan.")

    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
