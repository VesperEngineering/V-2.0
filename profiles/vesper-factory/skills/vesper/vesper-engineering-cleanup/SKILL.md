---
name: vesper-engineering-cleanup
description: Systematic audit and cleanup of Vesper engineering debt — dead code, hardcoded paths, SQL patterns, factor bloat, redundant cron, and post-rename Nova references.
---

# Vesper Engineering Cleanup

Ruthless, targeted cleanup of the Vesper quant codebase. Applies the same FM-style rigor ("kill what doesn't work") to engineering artifacts.

## Trigger Conditions

- User says "inspect engineering", "clean up code", "anything to improve"
- After a factor purge or refactor — verify nothing rotted
- After renames (Nova→Vesper) — sweep for stale references
- Cron/scheduler redundancy check
- Any time the repo feels bloated
- A large deletion set, sharply reduced test count, or suspiciously green surviving suite appears

## Recovery Gate Before Cleanup

When repository integrity is uncertain, recover the baseline before deleting or refactoring anything. Preserve staged and unstaged binary patches separately, restore only unexplained tracked deletions, verify workflow-required paths, and run layered validation. See `references/repository-recovery-and-baseline-restoration.md`.

## Audit Checklist (Run in Order)

### 1. Orphan Factor Files
```bash
# Factors on disk but NOT in registry.py
for f in app/factors/*.py; do
  name=$(basename $f .py)
  [ "$name" = "__init__" -o "$name" = "base" ] && continue
  grep -q "$name" app/factors/registry.py || echo "ORPHAN: $name"
done
```
Investigate every orphan. Delete only after confirming ownership, absence from registry/import/docs/runtime paths, and relevant passing tests. In a dirty or recovery-state worktree, preserve it until provenance is clear.

### 2. Zero-Weight Factors
Check `scripts/run_all_factors.py` — any factor with weight 0.0 is dead weight. Remove from registry AND delete the source file. The STATUS.md rule is "kill dilutive factors." Weight 0.0 = killed.

### 3. Dead Scripts (Evolutionary Artifacts)
Look for:
- `*_v2.py`, `*_v3.py`, `*_v4.py` — only v4 (or latest) is current
- `no_order_checkpoint*`, `post_rebuild*` — one-time rebuild artifacts
- `generate_*` scripts with no matching `run_*` or scheduler reference

**Retirement procedure (prove → quarantine → keep importable → track):**

1. Verify the script is not imported by any active code path:
   ```bash
   grep -rl "script_name" app/ scripts/ tests/ --include="*.py" | grep -v ".worktrees" | grep -v "__pycache__"
   ```
2. If it has a `run()` or `main()` that another module references, create a **compatibility shim** at the original path: `from scripts.archived.research import script_v1 as _legacy`
3. Copy the file to `scripts/archived/research/<name>_v<N>.py`
4. Replace the root file with the compatibility shim
5. Update cosmetic cross-references (print statements, docstrings that mention the old path)
6. Add the archived path to `ARCHIVED_RESEARCH` in `tests/test_repository_retirement_contract.py`
7. Verify the shim: `python -c "from scripts.script_name import run; print('OK')"`
8. Run retirement contract tests: `python -m pytest tests/test_repository_retirement_contract.py -q`

Only delete without a shim when the script has zero import references and zero documented callers.

### 4. Unreferenced Files
```bash
# Find scripts never called from scheduler or cron
for f in scripts/*.py; do
  name=$(basename $f)
  grep -rq "$name" scheduler/ --include="*.json" || echo "UNREF: $name"
done
```
Also check root-level `.py` files. `mine_signals.py` at root was 341 lines of unreferenced code.

### 5. Hardcoded Paths
Search for literal paths that break on other machines:
```bash
grep -rn "D:/vesper" app/ scheduler/ vesper-dashboard/ --include="*.py"
grep -rn "C:\\\\Users\\\\bgonn\\\\AppData\\\\Local\\\\hermes" app/ --include="*.py"
```
Replace with env-var-based resolution:
- Vesper repo paths: `Path(os.environ.get("VESPER_ROOT", "D:/vesper"))`
- Hermes home paths: `Path(os.environ.get("HERMES_HOME", str(Path.home() / "AppData" / "Local" / "hermes")))`
- Icon assets: `HERMES_HOME.parent.parent / "vesper" / "assets" / ...`
- Kanban DB: `HERMES_HOME / "kanban" / "boards" / "vesper" / "kanban.db"`
- Hermes CLI: `str(HERMES_HOME / "hermes-agent" / "venv" / "Scripts" / "hermes.exe")`

This pattern lets the same code work across machines, profiles, and portable
installations without code changes. The `HERMES_HOME` env var is the canonical
root for all Hermes Agent state.

### 6. SQL Injection Patterns
```bash
grep -rn "\.format.*SELECT\|f\".*SELECT\|%s.*SELECT" app/factors/ --include="*.py"
```
Replace with parameterized queries using `?` placeholders. Extract shared helpers to `app/factors/db.py`.

### 7. Shared Code Extraction
Duplicated SQLite connection/open/fetch patterns across factors? Extract to `app/factors/db.py`. Same for rank z-score, winsorization, panel building — factor code should be signal logic only, not plumbing.

### 8. Cron Redundancy
Run `cronjob action=list` and compare against `scheduler/jobs.json`. Any job in both = duplicate execution. The Vesper Scheduler is primary — pause redundant Hermes jobs. Only keep Hermes jobs the scheduler can't do (LLM-driven research, one-shot reminders).

### 9. Nova/Vesper CLI Migration Audit
```bash
grep -rn "deploy/nova\.py\|deploy/vesper\.py\|Nova\b" app/ scripts/ scheduler/ deploy/ tests/ --include="*.py"
```
Treat the rename as an atomic compatibility migration, not a blind replacement. Inventory launchers, production command constructors, tests, fixtures, workflow commands, safety markers, docs, and historical evidence contracts. Keep the canonical compatibility entry point until the whole slice passes; otherwise defer the rename. Also check `.cmd`/`.ps1` launchers.

### 10. Scheduler Hygiene
- Add `RotatingFileHandler` for `scheduler.log` (5MB, 3 backups)
- Add per-job log retention (100 max per job) via `_cleanup_job_logs()`
- Verify `jobs.json` scripts all exist and reference correct paths
- Check the live scheduler process list; configured jobs are not evidence that the daemon is running

### 11. Windows Scheduled-Pipeline Verification

For critical unattended workflows, use one tested Python orchestrator and keep the
`.bat` file as a thin wrapper. The orchestrator must run dependency order
sequentially and stop on the first nonzero child exit.

1. Add targeted RED tests for ordering, downstream suppression, required artifact/data admission, and CLI dry-run behavior.
2. Make every script entry point return a meaningful status through `raise SystemExit(main())`; logging an error while returning 0 is a failed guard.
3. In the wrapper set `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8`, quote the exact interpreter, redirect logs, capture `%ERRORLEVEL%`, and `exit /b` with it. Windows Task Scheduler redirection may otherwise use CP1252 and crash on Unicode status text.
4. Query the task's exact action, trigger, user/logon mode, last result, and next run. `Ready` proves only configuration, not successful execution.
5. Run the real artifact-only task once and verify its Last Result, logs, and output artifacts. Do not manually invoke a broker/rebalance task merely to test scheduling.
6. Verify the fix file is tracked in git (`git status --short` on the wrapper), not just present on disk. Untracked fix files are lost on fresh clone and must be committed before the audit is complete.
7. Cross-reference documented state against real data sources: check VESPER_FACT_BASE.json's `local_ohlcv_date` matches actual DB max. A false-green fact base — claiming a newer date than reality — silently invalidates all downstream status claims.
8. Record whether the task is `Interactive only`; such a fallback does not survive logout and is not equivalent to a persistent daemon.
9. Broker-facing scheduled scripts need independent guards: paper endpoint, weekday, broker market-open clock, date/freshness, exact target shape, and exception propagation.
10. Update `docs/STATUS.md`, `README.md`, `CHANGELOG.md`, and `docs/VESPER_FACT_BASE.json` with verified behavior, unverified surfaces, safety boundaries, and next actions.

See `references/windows-scheduled-pipeline.md` for templates and the verification checklist.

For lane schedulers that inflate heartbeat cycles, repeatedly select completed work, or need exactly-once worker dispatch plus a logout-safe Windows backup, follow `references/steward-state-machine-and-windows-task-recovery.md`.

### 11A. Dashboard / Operator-Console Plumbing Before Layout

When the user asks whether the GUI can be trusted, **do not redesign it first**. Preserve the current visual layout and audit the truth path underneath it:

1. Identify the exact process, command line, cwd, static root, startup launcher, refresh wrapper, and scheduled-task wrappers serving the GUI. Hash served assets against the intended repository copy; eliminate shadow runtime copies only after verified cutover.
2. Replace literal or unconditional `HEALTHY`, `Connected`, and `live` claims with fail-closed derived state and explicit reasons. HTTP reachability is not system health.
3. Keep browser-fetch age, payload age, score age, basket age, portfolio snapshot age, and broker-live age separate. Format offset-aware ISO timestamps once in `America/New_York`; never reinterpret already-local display strings.
4. Read the exact canonical basket consumed by rebalance. Keep raw score leaders, approved target, last executed target, snapshot holdings, and live holdings distinct.
5. Preserve raw factor values separately from governance-weighted deployed contributions. Zero-weight diagnostics cannot be labeled as active drivers.
6. Discover scheduler authority per job instead of assuming Hermes, Windows Task Scheduler, and an internal daemon are interchangeable. Exclude paused jobs from active state and verify Windows `Last Result`, not just `Ready`.
7. Use one refresh controller that owns and clears every timer, reevaluates market phase/visibility, and prevents overlapping requests.
8. Add RED tests for each misleading claim before backend or binding changes. After repair, verify focused tests, full pytest, API output, browser DOM/console, served hashes, live process command line, task results, and source artifacts.

See `references/dashboard-operator-plumbing.md` for the complete audit sequence, common failure patterns, and completion bar.

### 11B. Broker / Local-State Atomicity and Worker Supervision

For any Alpaca mutation or execution-worker change, audit the broker boundary as a distributed transaction—not a normal database write:

1. Guard **every** broker-mutating path (submission, EOD, cancellation, liquidation, retry, shutdown, and compensation) with the same enabled-paper/endpoint/account authority check.
2. Commit a unique deterministic intent before POST; retries must get-or-create and reconcile by client ID rather than POST again.
3. Represent timeout and malformed responses as unresolved uncertainty, because Alpaca may have accepted the request.
4. Require exact database row counts, non-masking cleanup, and authoritative post-state verification after compensating DELETE.
5. Supervise stream, risk, persistence, and queue workers together; any critical worker exit must stop ingress and broker mutation immediately.
6. Run adversarial probes for DB open/insert/commit/update/close failures, duplicate/concurrent retries, malformed broker responses, disabled/live mutation attempts, and each worker’s independent failure.
7. Keep execution disabled and continue independent review until a fail-closed verdict passes; a fixed review-cycle count is not deployment authority.

See `references/broker-local-state-safety.md` for the full failure matrix and stopping rule.

### 12. Holistic Quant-Firm Audit

When the user asks for a broad or co-founder-level review, do not reduce the task to a narrow bug hunt. Audit five connected systems:

1. **Research validity** — point-in-time data, survivorship, labels/cutoffs, leakage, costs/slippage, walk-forward/out-of-sample evidence, performance metrics, and whether receipts prove economics or only mechanics.
2. **Portfolio/risk** — sizing, concentration, sector/beta exposure, drawdown, turnover, correlation, stops, and whether controls are actually applied at the execution boundary.
3. **Execution** — every broker mutation path, paper/live endpoint, idempotency, ambiguous network outcomes, reconciliation, fills/positions/P&L, retries, and worker failure behavior.
4. **Model governance** — champion/challenger admission, path/hash provenance, promotion/rollback, drift, registry truth, stale aliases, and false-green evidence.
5. **Firm operations** — scheduler authority, Windows task outcomes, receipts, operator controls, status/board synchronization, secrets, recovery, and documentation.

Start with a read-only baseline: current worktree/status, governance files, test collection, active process state, and canonical-vs-historical path boundaries. Exclude `.venv`, `.worktrees`, generated artifacts, caches, and browser scratch from production scans unless auditing those boundaries specifically. Treat plan/diagnostic/review modules as non-economic evidence until an executable producer and validator are identified.

Dispatch bounded independent audits by domain, then consolidate findings into a priority order. Prefer fixes that establish truth or fail-closed behavior over adding signals. Record every finding in the repository issue ledger with severity, evidence, remediation, exact verification, and execution impact. Preserve unrelated dirty worktree state.

See `references/quant-research-path-active-inventory-20260714.md` for the current active pipeline map, stale-path inventory, and three highest-value validity risks (PIT universe, label timing, cost model disconnect) with exact path/line evidence.

See `references/score-artifact-universe-gate-audit.md` for the version-gap diagnostic pattern: verifying whether a universe gate or governance field addition was actually exercised by comparing artifact timestamps against commit history, parsing the SP500 tickers file, and checking all 502 members against scored output.

### 12A. Receipt Freshness / Telemetry False-Green Audit

Telemetry and status receipts that only check *existence* of artifacts (not *freshness*) produce false-green output — a report reading `Blockers: None` when scores are 4 days stale is structurally misleading.

**Pattern to audit:**

1. For every telemetry/status receipt, distinguish between:
   - **Existence check**: "artifact X exists" → true even when stale
   - **Freshness check**: "artifact X is recent enough for its purpose" → requires a configurable SLA (e.g. scores must be within 3 calendar days)
   - **Semantic check**: "artifact X contains valid/meaningful data" → e.g. scores are not all-zero, not all-NaN, universe-filtered

2. **Probe every "Blockers: None" or "PASS" claim** — verify it wouldn't also fire for a 4-day-old artifact.

3. **Check recency with a calendar-day gap** (not business days, to keep it simple and fail-closed):
   ```python
   from datetime import date, timedelta
   latest_score = max(receipt_dates["factor_scores"])
   score_date = date(int(s[:4]), int(s[4:6]), int(s[6:8]))
   if date.today() - score_date > timedelta(days=3):
       blockers.append(f"Factor scores are stale — latest is {s} ({(date.today() - score_date).days} days ago)")
   ```

4. **Verification**: run the telemetry after the fix — it should flag the stale gap, then regenerate the receipt to confirm false-green is resolved.

**Common findings:**
| Report says | Reality | Fix |
|---|---|---|
| `Blockers: None` | Latest score is 4 days old | Add recency check with >3-day gap |
| `Status: READY` | Score artifact predates universe gate (no universe filtering) | Add field presence check + recency check |
| `factor_scores: 9 found` | All 9 are from before the gate was added | Gate wasn't exercised — no existing artifact passes it |

See also `references/score-artifact-universe-gate-audit.md` for the version-gap diagnostic.

**Immediate stop rule:** if the user says `/stop`, “stop,” or equivalent, cancel the remaining todo state and do not start or continue tools, tests, edits, commits, pushes, or background delegations. Late asynchronous results may arrive; acknowledge them without resuming work.

### 12B. Artifact Commit-Policy Registry

When CI shows `BLOCKED_UNKNOWN_ARTIFACT_FAMILY` for files in a new commit, the artifact path pattern isn't registered in `app/services/artifact_schema_registry.py`. Register the family so the CI gate passes — see `references/artifact-commit-policy-registry.md`.

### 13. Concurrent Agent / Scan Handoff
When another Hermes or Codex session is already modifying `D:\vesper`, observe before acting:

1. Treat its session ID as an observability handle, not a process ID.
2. Inspect matching Hermes agent/error logs to determine model, current tool activity, termination reason, and whether delegated results arrived.
3. Do **not** edit the repository or run broad mutating commands while that session is active.
4. After it stops, inspect only the files it created or touched and run the narrowest relevant verification first.
5. Never equate `max_iterations_reached`, a final prose response, or a written test with completion. Confirm every imported module exists and execute the tests fresh.
6. If the working tree was already dirty, do not attribute the entire diff to the latest agent. Separate new files by timestamps and task scope.
7. Open-ended scans can consume dozens of subscription-backed model calls. Prefer bounded briefs with explicit deliverables, verification commands, and a call/iteration ceiling.

See `references/concurrent-agent-scan-verification.md` for the reusable monitoring and handoff checklist.

When the task is to *verify* the finished session's slice (not just observe it), follow `references/concurrent-session-verification.md`: run an independent read-only battery (compile/import/lint/focused tests/live-data smoke), classify every red test as introduced-vs-pre-existing via a baseline stash (`git stash push -u`, test at HEAD, `git stash pop`, confirm clean restore), split "pre-existing" into strict-string drift / retired-path / replaced-literal / structural-fail-closed, and scope the verdict to exactly what the checks proved.

### 14. Governed Vesper Quant Worker Team

For a broad cleanup that spans research, data, portfolio/risk, execution, governance, or operations, use a small managed team rather than one overloaded agent or an uncontrolled swarm. Keep every persona under the identity **Vesper Quant** and make the managing agent responsible for integration and authority decisions.

Use the reusable roster and work-packet contract in `references/governed-worker-team.md`. For the first real model-backed worker, follow `references/worker-runtime-proof-slice.md`: prove one report-only worker through task claim, provider lifecycle receipt, bounded input context, artifact/receipt validation, and independent review before expanding the roster. Start with only the needed roles: Research & Evidence, Data Steward, Portfolio & Risk Architect, and Skeptical Red-Team Reviewer. Add Execution/Operations or Model Governance when the work reaches those boundaries; activate specialized low-latency, FPGA, derivatives, fund-operations, ML, or product roles only when the repository has a justified need.

Every worker assignment must specify scope, allowed paths, safety boundary, evidence required, tests, deliverable, and stop conditions. First passes should be read-only. Workers may research and propose bounded repairs but may not independently promote models, change risk, enable live execution, mutate scheduler authority, submit broker orders, switch providers, or delete ambiguous code.

Use independent domain audits followed by adversarial review. Consolidate only after verifying active callers and current authority. Apply **prove -> quarantine -> delete**: map the active chain, fail-closed dangerous or ambiguous paths, add regression coverage and issue-ledger entries, then remove only code proven dead and outside historical provenance.

See `references/governed-worker-team.md` for the role charter and lean-pipeline target.

### 15. Git Worktree Reconciliation Sweep

Worktree sprawl is reconciliation debt against AGENTS.md ("completed work must be reconciled back into this root"). Sweep with evidence tranches — never bulk-prune from a generated list.

1. **Inventory in Python, not bash.** `git worktree list --porcelain` lines carry `\r` on Windows/MSYS; bash loops over it silently break exact branch-name matching (`merge-base` checks fail, nothing prunes, loop looks successful). Parse porcelain blocks in Python (or `tr -d '\r'`).
2. **Tranche A — ancestor-merged:** `git merge-base --is-ancestor <branch> vesper` → every commit is in main; safe to `git worktree remove` + `git branch -d`.
3. **Tranche B — patch-equivalent:** `git cherry vesper <branch>` → lines starting `+` are unique commits, `-` are equivalents already in main. `unique=0` justifies `git branch -D` (the branch isn't an ancestor, but its patches are).
4. **Archive before any `--force`:** for dirty worktrees, save `git -C <wt> diff > <name>.patch` plus untracked files (skip `.venv/`, `.tmp*`) into `.hermes/audits/worktree-sweep-<date>/` BEFORE removal. Working-tree residue is uncommitted — merged branch tips say nothing about it. Check whether untracked files exist in main (`git cat-file -e vesper:<path>`); archive the ones that don't.
5. **`git worktree remove` refuses dirty trees by default** — the clean tranche is safe by construction; only the archived tranche needs `--force`.
6. **Unique-commit worktrees are owner decisions, not sweep targets.** Present each with unique-commit count, last-commit date/subject, and dirty-file count. Many dirty files can mean a live concurrent session is working in it — leave those alone.

See `references/worktree-reconciliation-sweep.md` for the 2026-07-19 sweep (37 → 13 worktrees), the tranche evidence pattern, and the remaining-triage table shape.

### 15A. Read-Only Git Reconciliation Before Integration

When canonical is dirty, local/default history diverges from the remote, and several branches or worktrees may contain retries, first perform a read-only reconciliation audit rather than a prune or merge. Prove the live remote tip with `ls-remote` instead of fetching; classify branch tips separately from worktree residue; map patch-equivalent commits; bind every unfrozen candidate by worktree/HEAD/allowlist/diff digest; predict committed conflicts with `merge-tree` and uncommitted applicability with `git apply --check`; then re-snapshot because concurrent agents may advance refs during the audit. Prefer a linear candidate based on the live remote tip over a merge that retains duplicate patch-equivalent history. Never invent a cherry-pick SHA for uncommitted work, and never treat a clean candidate as proof that every roadmap exit gate is complete.

See `references/read-only-git-reconciliation-audit.md` for the full command matrix, classifications, conflict probes, concurrent-writer handling, integration-sequence rules, and report template.

## Governed Worker Runtime Vertical Slices

When turning the documented Vesper workforce into real model-backed workers, begin with one bounded vertical slice rather than adding more personas or broad autonomy. The worker hierarchy and lane metadata are not runtime evidence.

1. Preserve unrelated dirty worktree state. Isolate the slice to new worker-runtime code and focused tests where possible.
2. Define a durable task lifecycle: `queued -> claimed -> needs_review -> completed`.
3. Make claims exactly once; a delegation or claim event is not worker execution or completion.
4. Require the declared artifact path, a physical completion receipt, explicit `PASS` verification, and an independent reviewer before completion.
5. Store task lifecycle events in a tamper-evident append-only ledger and fail closed on malformed or hash-mismatched history.
6. Only after the local lifecycle contract is green, attach a real model/provider adapter. Provider lifecycle receipts (`started`, terminal state, model, worker, lane, request ID, usage) must remain separate from local coordination/activity events.
7. Never infer model activity, worker completion, capability growth, or strategic authority from a Steward heartbeat, lane cycle count, delegation event, or worker persona file.
8. Keep the first worker report-only and bounded. No broker/order, model promotion, scheduler mutation, target/risk mutation, provider switch, secret exposure, or destructive cleanup authority.
9. Verify the slice with RED -> GREEN focused tests, adjacent Steward/provider-ledger tests, Python compilation, and `git diff --check`. Do not claim a real workforce until a real provider request, artifact, receipt, and independent review are all observed.

The reusable lifecycle contract is intentionally provider-agnostic so the safety and evidence boundary can be tested without credentials or model spend. Attach the provider only as the next separately verified slice. For the provider slice, use an explicit model adapter with injectable fake transport first; emit separate `started`/`completed`/`failed` provider receipts with request ID and usage; bind the generated artifact and receipt to the task's declared path; and fail closed on missing credentials, malformed responses, empty content, inconsistent usage, or path escape. Do not silently fall back to another provider, treat a model heartbeat as proof of execution, or claim live completion when the credentialed path was not exercised. Steward integration must be opt-in per packet; legacy signal-only packets should remain unchanged until they declare the full runtime contract.

## Post-Cleanup Verification

```bash
# Always run full suite
python -m pytest tests/ -q --tb=short

# Verify factor imports
python -c "from app.factors.registry import get_registry; print(len(get_registry().names))"

# Verify scheduler compiles
python -c "import py_compile; py_compile.compile('scheduler/__init__.py', doraise=True)"

# Update STATUS.md date and summary
```

### Pytest on Windows — point the temp dir at an external path on the repo's own drive

Pytest's tmp handling breaks three ways on this Windows/D-drive setup, and all
three produce FALSE failures that look like real regressions:

1. **Default temp is permission-locked.** `C:\Users\bgonn\AppData\Local\Temp\pytest-of-bgonn`
   intermittently raises `WinError 5 Access is denied` (stale lock). Tests
   ERROR before running.
2. **MSYS `/tmp` resolves to the wrong drive.** `TMPDIR=/tmp/...` lands pytest
   tmp on `C:` while the repo is on `D:`. Any test that calls
   `os.path.relpath(tmp_path, repo)` raises `ValueError: path is on mount
   'C:', start on mount 'D:'` — reads as a code failure, is pure environment.
3. **A temp dir INSIDE the repo breaks external-path tests.** Setting
   `TMPDIR` to somewhere under `D:\vesper` makes tests that assert "system
   temp is outside the repo root" fail (their `rel()` now returns a
   repo-relative path instead of the absolute external path).

Fix — use an external directory on the SAME drive as the repo, every run:

```bash
mkdir -p /d/pytest_tmp
TMPDIR="D:\\pytest_tmp" TEMP="D:\\pytest_tmp" TMP="D:\\pytest_tmp" \
  python -m pytest tests/ -q --no-header -p no:cacheprovider
rm -rf /d/pytest_tmp   # clean up after
```

When a full-suite run surfaces a failure you didn't expect, re-run that single
test with this temp config before classifying it — a cross-mount or in-repo
temp artifact is not a code bug.

## Pitfalls

- **Broad-suite evidence must reflect the restored surface**: a green run after hundreds of test deletions is not a baseline. Preserve the dirty state, restore unexplained tracked deletions, run workflow-required tests, then run the broad suite and report exact pass/skip/fail counts. Separate deterministic repository failures from optional-runtime process corruption.
- **Dirty worktrees are user state**: never `git stash`, `git reset`, `git add -A`, broad-format, or revert unrelated paths to manufacture a baseline. Capture `git status --short`, define an allowlist, include untracked files explicitly (they do not appear in `git diff`), and compare against a previously recorded baseline or file-scoped `HEAD` evidence where valid.
- **Large legacy text can contain control characters**: after any documentation patch, inspect diff stats and hunk headers. If a tiny top-of-file edit changes hundreds of distant lines, restore the untouched bytes and reapply the intended insertion with a byte-preserving method.
- **Use targeted file tools for edits/searches**: prefer `patch`, `write_file`, `search_files`, and `read_file` over shell-wide `sed`, `grep`, or destructive batch replacements. Re-read the exact region after fuzzy edits; if adjacent lines are absorbed, stop incremental patching and rewrite the small file once from a complete read.
- **GUI retirement shims are retained by design, NOT dead**: `scripts/start_operator_gui*.vbs/.ps1/.cmd`, `create_operator_gui_shortcut.ps1`, `install_operator_gui_shortcut.ps1`, `operator_gui_desktop_launcher.py`, `sync_operator_gui_desktop.ps1`, `retire_operator_gui.ps1`, `app/operator_tui.py`, `app/main.py`, `app/pages/*` are fail-closed "RETIRED" shims forwarding to `app.operator_terminal`. They are gated by `tests/test_operator_gui_retirement.py`, `test_operator_launcher.py`, `test_operator_terminal_shortcut.py` and `.github/workflows/validation.yml`. Do NOT delete them in a dead-code sweep — deletion breaks the retirement contract tests.
- **Sibling-imported helpers in `scripts/` are live, not orphans**: `qth_diagnostics_common.py`, `validation_receipt_helpers.py`, `stage8_observation_cycle_helpers.py` have no refs outside `scripts/` but are `import`ed by many sibling scripts/tests. A naive stem-count against only `app/ tests/ scheduler/` flags them falsely. Include `scripts/` in the reference corpus (subtract self-occurrences) before calling any `scripts/` helper dead.
- **`deploy/src/na/` is the live quant core, not a legacy duplicate**: imported as `from src.na.*` by `app/services/*` and `deploy/cli/*` via PYTHONPATH. Do not treat it as a superseded copy of `app/`.
- **Externally-scheduled scripts are live despite zero in-repo refs**: `scripts/cron_*.py`, `cron_dry_run.py`, `research_to_kanban_bridge.py`, `telemetry_baseline.py` are wired via Hermes cron / `.hermes/lanes.json` (Vesper Swing agentic system), not Windows Task Scheduler. Grep `.hermes/` before rating cron/bridge scripts dead. For file-level dead audits (orphan/superseded/retired FILES with a confidence ladder), see the `codebase-architecture-audit` skill's `references/dead-file-audit.md`.
- **Deletion requires scope ownership**: use `git rm` only for tracked files explicitly owned by the cleanup and only after verifying imports, registry references, docs, and tests. Never infer that existing deleted tests belong to the current session.
- **Nova rename hits tests and command construction**: search both production and test paths, including `deploy/cli/data.py`; update only confirmed stale references.
- **Scheduled success must be end-to-end**: direct Python success, dry-run success, task status `Ready`, and a rewritten wrapper are each insufficient alone. Verify the real task action and Last Result through Task Scheduler.
- **A new wrapper file on disk is not committed**: a `.bat` or `.ps1` fix that exists only as an untracked file (`??` in `git status`) is lost on fresh clone. Always verify the fix is tracked in git before marking the audit complete.
- **Log file name drift between old and new wrappers**: replacing a wrapper that wrote to `windows_factor_pipeline.log` with one that writes to `windows_pipeline.log` creates two log files, confounding troubleshooting. Keep the log file name consistent across wrapper versions, or document the rename explicitly.
- **Artifact success is not economic validity**: a score/basket pipeline result of 0 proves mechanics only. Keep symbol anomalies, stale-source risk, and point-in-time data defects explicit.
- **Receipt-factory anti-pattern**: a system can produce hundreds of PASS receipts while making zero substantive decisions (model admission, source switch, promotion, risk change). Each receipt confirms the system is waiting, but the waiting state is self-reinforcing. When receipt count is high and decision count is zero, the governance layer is generating false-green evidence. The fix is not more receipts — it's explicit decision gates with deadlines. See `references/red-team-methodology.md` for detection patterns.
- **Contradictory status fields**: when a boolean gate (e.g. `Execution allowed: true`) is immediately qualified by prose (e.g. "bounded paper only"), the boolean is structurally misleading. Any downstream parser, automation, or future contributor that reads only the boolean will misinterpret authority. Replace qualified booleans with explicit enumerated states (`execution_mode: paper_only`).
- **Deadlocked receipt chains**: when multiple sequential receipts all produce the same conclusion (`proven: false`, `admission allowed: false`) with no change in approach, the chain is a self-referential receipt mill — not forward progress. Require root-cause diagnostics and falsifiable hypotheses before issuing new approvals in the same chain.
- **Graduated autonomy over big-bang automation**: never jump from manual operation to autonomous execution. Use a level-ladder approach (0: manual → 1: scheduled data → 2: scheduled basket → 3: auto-paper with health gates → 4: live shadow → 5: minimal live) where every promotion requires a corresponding fail-closed health check. Each level's gate defaults to STOP. See `references/graduated-autonomy-ladder.md`.

## Key User Preferences

- Aggressive culling: "kill dilutive factors" means DELETE them, not move to 0.0 weight
- FM is gold standard — engineering follows the same philosophy (if it doesn't carry weight, remove it)
- Honest reporting: pre-existing failures are pre-existing, say so
- Set-and-forget: once cleaned, it should stay clean
- Direct, concise: no fluff, just results
- GUI work order: prove and repair plumbing, provenance, freshness, scheduler authority, and deployment source before changing the layout; preserve the current dark visual design during trust-layer repairs
- Verdict scope: report exactly what the checks proved — a green build/smoke run is not "release-verified". Enumerate the release-gate items not run, and read any concurrent session's own repair/findings report before issuing a verdict on the same artifact.
