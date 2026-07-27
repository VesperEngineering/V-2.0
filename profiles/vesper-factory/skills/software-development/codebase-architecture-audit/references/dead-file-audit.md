# Read-Only Dead-FILE Audit (orphan / superseded / retired files)

Use when the user asks to audit a repo for **dead, unused, or obsolete FILES** — orphaned
scripts, retired launchers, duplicate/superseded modules, stale bulk artifacts, empty files.
This is FILE-LEVEL dead code, not in-function dead code. The deliverable is a per-file
verdict (path / size / mtime / referencing evidence / confidence), grouped by category,
highest-confidence first. It is read-only: do NOT delete anything unless asked.

## Core technique: reference-count scan

A file is dead only if **nothing references it**. Build a reference corpus and count, per
file stem (word-boundary regex), how many OTHER files mention it. Two reference classes:

- **CODE refs** — imports, `require()`, subprocess/CLI invocations, scheduler/task XML/BAT,
  CI workflow paths, test `read_text`/assert paths, config/JSON. A code ref = the file is live.
- **DOC refs** — mentioned only in plans / changelogs / runbooks / audits. A doc-only ref =
  LIKELY-DEAD (one-shot generator) unless it's an active runbook.

### Confidence ladder
- **CONFIRMED-DEAD** — zero code refs AND zero doc refs AND clearly superseded / junk artifact.
- **LIKELY-DEAD** — referenced only by itself or docs (typical one-shot evidence generator).
- **UNCERTAIN** — zero refs BUT it is a leaf `__main__` entry point (or `.ps1/.js/.bat/.cmd/.vbs`)
  that an operator runs manually, so "no references" is expected. Do NOT call these dead.

### Efficient scan (large repos — avoid the O(N²) blowup)
Per-file × per-file regex over hundreds of scripts times out. Instead:

1. Concatenate each surface into ONE big string per class (code_no_scripts, docs).
2. Build ONE alternation regex `\b(stem1|stem2|...)\b` over all stems (longest first) and do a
   SINGLE pass over the scripts corpus to get per-stem counts; subtract the file's own
   self-occurrences to get sibling-script refs.
3. Per file: `code_refs = findall(code_corpus) + sibling_refs`; `doc_refs = findall(doc_corpus)`.
4. Exclude heavy/generated dirs from the corpus: `.worktrees/ node_modules/ .venv/ .git/
   __pycache__/ .pytest_cache/ .ruff_cache/` and large data dirs — or `find` will time out.

## FALSE-POSITIVE pitfalls (verify before flagging dead)

These all LOOK dead under a naive stem-count but are LIVE — always re-grep the specific file:

- **Helper/common modules imported by sibling scripts in the same dir.** `qth_diagnostics_common.py`,
  `validation_receipt_helpers.py`, `stage8_observation_cycle_helpers.py` have zero refs outside
  `scripts/` but are `import`ed by many sibling scripts. **Include the same directory in the corpus
  and subtract only self-occurrences** — otherwise every helper is a false orphan.
- **Retirement / compatibility shims retained by design.** A file whose body says `RETIRED ... use X`
  and that is asserted-present by a CI test (`test_*_retirement.py`, `validation.yml`) is NOT dead —
  it is a supported fail-closed shim. Deleting it breaks the retirement contract. Check for a
  `RETIRED.md` / retirement test before flagging any `start_*/install_*` launcher.
- **Externally-scheduled entry points.** `cron_*.py`, `scheduler/*.py`, and bridge scripts may be wired
  via an EXTERNAL scheduler (Windows Task Scheduler, Hermes cron, `.hermes/lanes.json`, steward) with
  zero in-repo code refs. Grep the agentic/automation dirs (`.hermes/ .agents/ .memory-bank/ lanes.json`)
  before rating. Recent mtime + a matching plan/audit doc = LIVE.
- **"Duplicate" dirs that are the live core.** A path that looks like a legacy copy (e.g. `deploy/src/na/*`
  vs `app/*`) may be THE live implementation imported via a `PYTHONPATH` package name (`from src.na import ...`).
  Trace actual imports before assuming duplication.
- **Version chains (v1/v2/v3).** Only flag the OLDER versions when a NEWER one carries the references.
  If even the newest has zero refs, the whole chain is UNCERTAIN (not confirmed dead).
- **Dead MODULES under `app/`, not just scripts.** Scans usually target `scripts/`, but an `app/<name>.py`
  can be dead too. Verify with the exact import statement, NOT a bare `grep "<name>"`: `return_exceptions=True`,
  `except ... exc`, and comments will match a module named `exceptions` and produce a false "imported" verdict.
  Run `grep -rn "from app.<name> import\|import app\.<name>\|from app import <name>"` and, if zero, also confirm
  none of the module's own class/def names are referenced anywhere before rating it dead.
- **Symbol-name matches can be a DIFFERENT module's symbol.** The reverse of the `exceptions` trap: when you check
  "is any of this module's class/def names used elsewhere?", a hit on a common name (`format_markdown`,
  `write_receipts`, `main`, `green`, `run`) is usually a *different* module's same-named symbol, not a reference
  to your candidate. Verify the match is actually `from <candidate_module> import <name>` (or `<candidate_module>.<name>`),
  not just the bare name. A candidate whose only "users" are same-named functions in unrelated files is still dead.
  Check the module's *distinctive* symbols (its unique class name, e.g. `MassiveFundamentalsFactor`) — those don't collide.
- **Registry / plugin-enumeration check.** A module in a plugin/factor/strategy directory can be live *only* via a
  registry that explicitly imports or enumerates it — OR dead precisely because the registry does NOT list it.
  Open the registry/`__init__.py` and confirm whether the candidate's class is imported/registered. A factor module
  whose class is absent from the explicit registry import list (and has no other importer) is dead even though
  sibling files in the same dir are live. Don't assume "same directory as live files" = live.
- **Cron/scheduler registry can point OUTSIDE the repo — and at a DIFFERENT set.** "Externally-scheduled"
  cuts both ways. The live scheduler (Hermes cron, Task Scheduler) may reference script names that resolve to a
  location outside the repo (e.g. `~/.../hermes/scripts/vesper_*.py`) while the repo carries a *parallel,
  divergent* set (`scripts/cron_*.py`) with zero references. Do NOT auto-mark the in-repo set LIVE just because
  it looks like a scheduler entry point — resolve each enabled job's actual script path and diff its content
  against the in-repo file. A divergent unreferenced in-repo duplicate is a two-sources-of-truth hazard
  (archive candidate), not a live file.
- **A sub-agent's LIVE/DEAD verdict is a claim, not a fact — re-verify against the authoritative registry.**
  In one audit a sub-agent (and its generated orphan TSV) reported in-repo `scripts/cron_*.py` as "LIVE Swing
  system, wired via Hermes cron" — but the actual enabled cron registry (`cronjob action='list'`) pointed at a
  DIFFERENT set of files outside the repo with DIFFERENT content. The sub-agent had matched on filename vibe, not
  resolved the real job→script path. Always pull the authoritative scheduler/CI/registry yourself and confirm the
  sub-agent's "live" entries against it before repeating them to the user. Treat generated orphan lists as
  UNVERIFIED input: re-grep surprising entries (especially recently-added files and anything marked LIVE) across
  the FULL repo before acting.

## Genuinely-dead signals worth flagging

- **Orphaned bytecode**: a `.pyc` under `__pycache__/` whose `.py` source no longer exists (e.g. a
  renamed module). Generated cache — safe to flag.
- **Redirect-artifact junk files**: e.g. a Windows `nul` file created by a `> nul` redirect capturing
  stderr. Usually already in `.gitignore` — confirm, then flag.
- **`*.bak / *.old / *_copy.py / *-old.py`** data/source backups (respect an allowlisted receipts path).
- **Superseded older versions** in a v1/v2/v3 chain (see above).
- **Retired-tool build scripts** referenced only in a retired plan doc (e.g. an Electron launcher build
  script after Electron was retired), with no test/CI reference.

## Scan checklist
1. Enumerate target dirs (`ls -la`), get sizes + mtimes.
2. Locate reference authorities: scheduler XML/BAT/PS1, `.lnk`/shortcut installers, CI workflows,
   tests, `package.json`/entry points, `.hermes`/`.agents` automation, docs/runbooks.
3. Run the reference-count scan (code + docs classes), excluding generated dirs.
4. Re-grep every ambiguous candidate individually before rating (kills false positives).
5. Classify CONFIRMED-DEAD / LIKELY-DEAD / UNCERTAIN; group by category; order highest-confidence first.
6. Verify junk/empty artifacts against `.gitignore` and `git check-ignore` before recommending removal.

## Verifying with tests on Windows — the TMPDIR cross-mount trap

When an audit step runs pytest to confirm a module is unused or a deletion is safe, a wrong `TMPDIR`
produces failures that look real but are pure environment artifacts:

- Redirecting pytest temp onto a **different drive** than the repo (e.g. `TMPDIR=/tmp/...` resolving to `C:`
  while the repo is on `D:`) breaks any test calling `os.path.relpath(path, repo)` — cross-mount `ValueError`.
- Redirecting temp **inside the repo root** (e.g. `D:\repo\.pytest_run`) breaks tests asserting the system
  temp is *outside* the repo (`rel()`-style helpers no longer return absolute external paths).
- The default `C:\Users\<u>\AppData\Local\Temp\pytest-of-<u>` can hold a **stale lock** (`WinError 5 Access denied`)
  from a prior crashed run.

Fix pattern: point `TMPDIR`/`TEMP`/`TMP` at a **fresh dir on the SAME drive as the repo but OUTSIDE the repo
root** (e.g. repo on `D:` → `D:\pytest_tmp`), `mkdir -p` it first, and re-run the suspect test before believing
a failure. If it passes there, the original failure was your harness, not the code — do not report it as a real
finding. Clean up the temp dir afterward.

## Reporting
Per candidate: full path, size, last-modified, why it looks dead (cite grep evidence or "no references"),
confidence rating. Group by category (orphaned scripts / retired launchers / superseded modules /
stale artifacts / empty files). Lead with a "NOT dead — do not delete" section calling out the
false-positive traps you verified live, so the user doesn't act on them.
