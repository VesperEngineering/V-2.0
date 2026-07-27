---
name: repo-hygiene-scan
description: Use when the user wants to keep a project folder light and flexible — routinely scan the whole repo for dead files, orphaned bytecode, junk artifacts, superseded version chains, and divergent duplicates. Read-only reference-count audit that presents findings with confidence ratings; never deletes without explicit per-item approval.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [cleanup, dead-code, audit, hygiene, repo-maintenance, dead-files]
    related_skills: [remove-dead-code, codebase-architecture-audit]
---

# Repo Hygiene Scan — Routine Dead-File & Junk Audit

Keep a project folder **lite and flexible** by routinely finding files that no longer earn their place: dead modules, orphaned `.pyc` bytecode, junk artifacts (`nul`, `*.bak`), superseded version chains, and divergent duplicate scripts. This is a **read-only** audit — it presents a confidence-rated report. Deletion is a separate, explicitly-approved step (see `remove-dead-code`).

## When to Use

- "Scan the repo for dead files / keep the project light."
- Routine hygiene pass before a release or after a big refactor.
- "What can I remove / archive?"

**Audit the WHOLE repo, not a subfolder.** If you find yourself auditing only `app/` or only `scripts/`, you are under-scoping — the user expects every top-level area covered and will correct a partial scan ("no, not just X, the entire repo, everything"). Enumerate all top-level dirs first (`git ls-files | awk -F/ '{print $1}' | sort | uniq -c`), then audit each — including `deploy/`, `backend/`, `frontend/`, `desktop/`, `config/`, and root-level files, not just the obvious `app/`/`scripts/`.

Don't use for: in-function dead code (use `codebase-architecture-audit`), directed removal of already-identified dead code (use `remove-dead-code`), or reviewing a recent diff (use `simplify-code`).

## Core Rule: Read-Only Until Approved

Never delete, move, or archive anything during the scan. Present findings, let the user decide per item or per family. The scan's job is a trustworthy, false-positive-free list — not action.

## Workflow

1. **Run the scanner** (`scripts/repo_hygiene_scan.py`) against the repo root. It enumerates tracked files via `git ls-files` (bounded — avoids `rglob`/`find` timeouts on large repos), builds a reference corpus, and counts references per module stem using a single-pass alternation regex.

   ```bash
   python <skill_dir>/scripts/repo_hygiene_scan.py --root D:/vesper
   ```

   Optional: `--include-untracked` to also sweep junk in untracked/git-ignored areas (`nul`, `*.bak`, orphaned `__pycache__`), `--json PATH` to write machine-readable results.

2. **Verify EVERY candidate individually** before rating it dead. The scanner emits *candidates*; the traps below turn some into false positives. Re-grep each with the exact import/usage statement. For reusable runbooks — baseline A/B failure classification on an uncommitted tree, the Windows pytest TMPDIR trap, `.lnk` launch verification, and the one-pass reference-count method — see `references/verification-techniques.md`.

3. **Rate confidence** (CONFIRMED-DEAD / LIKELY-DEAD / UNCERTAIN), group by category, and present highest-confidence first with a prominent "NOT dead — do not delete" section.

4. **Report** per file: full path, size, last-modified, referencing evidence (or "no references"), confidence. End with a recommended action per family (delete / archive / keep) and wait for the user's call.

## Reference classes

- **CODE ref** (file is live): imports, `require()`, subprocess/CLI invocation, scheduler/task XML/BAT, CI workflow paths, test `read_text`/assert paths, config/JSON entries.
- **DOC ref** (LIKELY-DEAD unless an active runbook): mentioned only in plans, changelogs, audits, retired specs.

## Confidence ladder

- **CONFIRMED-DEAD** — zero code refs AND zero doc refs AND clearly superseded/junk. Also: orphaned `.pyc` whose `.py` source is gone; Windows `nul` redirect artifact; `*.bak`/`*.old` backups.
- **LIKELY-DEAD** — referenced only by itself or docs (typical one-shot evidence generator).
- **UNCERTAIN** — zero refs BUT a leaf `__main__` entry point or `.ps1/.js/.bat` an operator runs manually; "no references" is expected. Do NOT call these dead.

## False-positive traps (ALWAYS re-grep before rating dead)

These LOOK dead under a naive stem-count but are LIVE. Each was a real miss:

1. **Helper modules imported by siblings in the same dir** (`*_helpers.py`, `*_common.py`). The scanner's same-dir sibling count catches most; verify any survivor.
2. **Retirement / compatibility shims retained by design.** Body says `RETIRED ... use X`, presence asserted by a CI test (`test_*_retirement.py`, `validation.yml`), or a `RETIRED.md` sits in the dir. Deleting breaks the retirement contract. Check for the marker/test FIRST.
3. **Externally-scheduled entry points.** `cron_*.py`, `scheduler/*.py`, bridge scripts may be wired via Windows Task Scheduler / Hermes cron / `.hermes/lanes.json` with zero in-repo refs. Resolve each enabled job's actual script path before rating.
4. **"Duplicate" dirs that are the live core** (e.g. `deploy/src/na/*` vs `app/*`). Trace actual imports (`from src.na import ...`) before assuming duplication.
5. **Bare-stem grep lies about imports.** A module named `exceptions` matches `return_exceptions=True` (asyncio) and `except ... exc` comments. Use the EXACT statement: `grep -rn "from app.<name> import\|import app.<name>\|from app import <name>"`, then confirm none of the module's own class/def names are referenced either.
6. **String/data-key matches are not imports.** A distinctive stem can appear as a JSON/JS data key (e.g. `massive_fund: "MassF"` in a retired dashboard) or a config string — zero imports but a nonzero stem count. The dotted-path import gate is authoritative; a lone stem hit is a *verify* note, not proof of life.
7. **Common-word stems are meaningless.** `exceptions`, `base`, `utils`, `common`, `helpers`, `types`, `config`, `state` match prose and docstrings everywhere. Never use bare-stem counts for these; rely on the import gate + symbol-name check only.
8. **Cron/scheduler registry can point OUTSIDE the repo at a DIFFERENT set.** The live scheduler may resolve to `~/.../scripts/vesper_*.py` while the repo carries a divergent `scripts/cron_*.py` parallel set. Diff content — a divergent unreferenced in-repo duplicate is an ARCHIVE candidate, not a live file.
9. **Dynamic loaders** (`importlib.import_module`, `pkgutil.iter_modules`, string-built imports) can reference a module the static scan misses. Grep for loader calls and check what they actually load.
10. **Explicit registries** (a factor/plugin registry that imports by name). Confirm the module is absent from the registry's import list AND its class isn't string-referenced in configs/JSON/tests before rating dead.

## Worktree sweep (agent-worktree reconciliation)

When a repo accumulates many agent-created git worktrees (Vesper hit 37), sweep them in evidence-ranked tranches — never bulk-delete from a generated list:

1. **Inventory:** parse `git worktree list --porcelain`, then per worktree: `git merge-base --is-ancestor <branch> <main>`, `git rev-list --left-right --count main...branch`, last-commit date, `git status --short`.
2. **Tranche 1 — ancestor-merged:** branch tip is an ancestor of main → `git worktree remove` + `git branch -d` (both refuse unsafe cases by construction; `--force` only after step 4 archival).
3. **Tranche 2 — patch-equivalent:** `git cherry main <branch>` — commits marked `-` exist in main by patch-id; `unique=0` means the branch contributes nothing even though it isn't ancestor-merged. Archive `git diff main...branch` first, then `branch -D` is justified.
4. **Archive before pruning anything dirty or unmerged:** save the `git diff` patch + untracked files (exclude `.venv/`, `.tmp*`) to an untracked audit dir (e.g. `.hermes/audits/worktree-sweep-<date>/`) so every deletion is reproducible. A worktree with 10+ dirty files may be a LIVE session — leave it alone.
5. **Present survivors as a decision table** (unique-commit count + lean keep/prune per worktree) and let the user call each family.

**Windows pitfall:** MSYS bash loops over `git worktree list --porcelain` fail silently — CRLF endings leave `\r` on branch names, so `merge-base --is-ancestor "branch\r"` never matches and every worktree is skipped with no error. Parse porcelain output in Python (`subprocess.run(..., text=True)`, strip lines) instead of shell `while read` loops.

## Common Pitfalls

1. **Deleting during the scan.** The scan is read-only; action is a separate approved step.
2. **Trusting the raw stem-count.** Always run the individual re-grep — the scanner is a candidate generator, not a verdict.
3. **Unbounded `rglob`/`find`** over a repo with generated test trees or `node_modules` — times out. Use `git ls-files` for tracked source; prune generated dirs.
4. **Flagging `__main__` leaf entry points as dead** just because nothing imports them — operators run them manually.
5. **Recommending deletion of historical evidence generators** (`generate_*`, `run_*_dry_run`) — these preserve receipt reproducibility; recommend ARCHIVE, not delete.

## Verification Checklist

- [ ] Scanner run via `git ls-files`-bounded enumeration (not raw `rglob`)
- [ ] Every candidate individually re-grepped with the exact import statement
- [ ] Checked for `RETIRED.md` / retirement tests before flagging any launcher
- [ ] Resolved external scheduler script paths before flagging cron/scheduler files
- [ ] Checked dynamic loaders + explicit registries for survivors
- [ ] Each finding has a confidence rating with grep evidence
- [ ] "NOT dead — do not delete" section present and verified live
- [ ] No file deleted/moved during the scan
- [ ] Report grouped by category, highest-confidence first, with per-family recommended action
