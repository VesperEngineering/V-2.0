---
name: vesper-engineering
description: Engineering workflow, patterns, and guardrails for VESPER 2.0 development. Covers pre-flight context loading, quant model training conventions, and dashboard integration patterns.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [vesper, engineering, workflow, quant, tkinter, pre-flight]
    related_skills: [surgical-engineering, vesper-tkinter-ui-engineering, vesper-factor-workflow, test-driven-development]
---

# Vesper Engineering

Engineering workflow and reusable patterns for the VESPER 2.0 quantitative trading system.

## When to Use

Before editing any VESPER code, running training, or building dashboard features. This skill is the first stop after `surgical-engineering` whenever the project is `C:\Users\bgonn\Desktop\v20` (or any VESPER codebase).

## 0. Mandatory Pre-Flight Checklist

Before touching any code, you **must** complete these three steps. The user has explicitly demanded this; skipping them produces blind edits and fabricated assumptions.

1. **Load relevant skills** via `skill_view(name)`. The system prompt mandates this; it is not optional.
   - Likely candidates: `surgical-engineering`, `vesper-factor-workflow`, `vesper-tkinter-ui-engineering`, `test-driven-development`.
2. **Query the codegraph** via `codegraph_explore` on the exact symbols/files you plan to change.
   - If the project has no `.codegraph/` index, run `codegraph init` in the project root first.
   - V20 has the active index and is the sole implementation workspace. Do not query or edit the frozen `D:\vesper` codebase for V20 planning or implementation; consult it only for an explicitly permitted canonical-data/artifact check.
   - If an ambiguous query returns unrelated symbols or trims the planned trainer/test source, refine once with the exact filename and symbol. Avoid generic symbols such as `main` in a multi-file query: query the module filename plus distinctive constants/functions (for example `MODEL_PARAMS`, `write_model_metadata`) so the graph result stays on the intended edit surface. Then read the scoped on-disk trainer and every directly related test before editing; an index query is required pre-flight evidence, not a substitute for inspecting the actual edit surface.
3. **Read project instructions**: `AGENTS.md`, `SKILLS/CODE.md`, `SKILLS/EXAMPLES.md` if present.

Do not begin implementation until these three are complete.

### Worktree-local CodeGraph and strict-TDD recovery

A V20 linked worktree can inherit discovery from the canonical repository's `.codegraph` index. After local edits, CodeGraph may explicitly report that its results came from the parent worktree and omit newly added symbols. Treat that warning as stale-index evidence: do not claim post-edit graph coverage from it. If creating a worktree-local index is outside the authorized path allowlist, do not add `.codegraph` files merely for verification; use full on-disk reads of changed logical blocks, the exact diff, focused regressions, and the declared review gates instead. The canonical pre-edit CodeGraph query remains required.

If an implementation branch was added before a test exercised it, recover strict TDD rather than accepting a test that passes immediately: remove only the untested branch, prove the already-supported focused slice is green, add the missing behavior test and observe RED, then restore the smallest implementation and observe GREEN. This commonly matters when a zero-variance/empty special case is tested but the nonconstant/general scoring branch is not. Preserve the RED and GREEN outputs separately in the independent-review handoff.

## 0.1 Active workspace and roadmap authority

For Brennan's VESPER 2.0 work, establish project identity from current sources before answering roadmap questions or editing anything:

- The sole active implementation root is `C:\Users\bgonn\Desktop\v20`.
- `D:\vesper` is frozen legacy material. Do not inspect it to infer current VOT status, propose it as an implementation target, or let its old roadmap govern V20. Consult it only when the user explicitly permits a canonical-data or retained-artifact check.
- Historical sessions are secondary context, not proof of current repository state. Inspect V20 and the current Vesper Factory planning notes before stating what exists or what comes next.
- The Obsidian architecture outline under `Vesper 2.0\Vesper Factory` ties together the current XGBoost baseline, expert forecasts, later master combiner, portfolio targets, deterministic hard risk, execution, and Factory evidence/orchestration. Do not confuse the master-model roadmap with Gate A or a narrow SPY evaluator gate.
- Obsidian is readable across `Vesper 2.0`, but assistant-authored edits stay under `Vesper 2.0\Vesper Factory`; the carry-forward map is the sole running Obsidian journal.

When corrected about workspace identity, stop immediately, acknowledge the mistake plainly, update durable workspace knowledge, and re-ground subsequent recommendations in V20. Do not continue reasoning from the frozen repository.

## 1. Quant Model Training Conventions

### Chronological train/test split (non-negotiable)

Financial time series are **not i.i.d.** Random shuffling leaks future information and produces overfit models with inflated IC.

**Rule:** Always split by calendar date, never by random sample.

```python
# build_training_set() returns dates alongside X, y
cutoff = np.datetime64("2021-01-01")
train_mask = dates < cutoff
test_mask = dates >= cutoff
X_train, y_train = X[train_mask], y[train_mask]
X_test, y_test = X[test_mask], y[test_mask]
```

**Report both:**
- Train IC (expect moderate, e.g. 0.15–0.35)
- **Out-of-sample IC** (the number that matters; > 0.03 is viable, > 0.05 is good)

An in-sample IC > 0.90 without a chronological split is a red flag for overfitting, not a good result.

### Feature/label alignment

- Features from `compute_features(df)`
- Labels: forward N-day return (`df["close"].pct_change(N).shift(-N)`)
- Align and drop NaN before stacking
- Remove infinite values after stacking

See `references/quant-model-training-pattern.md` for the full training script template.  
See `references/xgboost-ic-experiments.md` for empirical IC results and regularization guidance.  
See `references/windows-encoding-pitfall.md` for the Windows `cp1252` vs `utf-8` file open issue.  
See `references/spy-cpu-slice2-admission-cycle.md` for the admission-gated SPY CPU evaluator cycle: acceptance-matrix repair, atomic contract-bound outcome authorization with no reusable context or importable outcome helper, complete source-map validation, TOCTOU post-hash checks, environment-bound review gates, worktree/freeze/ff-only integration, and read-only SQLite admission checks.  
See `references/shadow-forecast-tdd-slice.md` for the minimal inert forecast-contract pattern: immutable provenance-complete records, signal-preserving score extraction, stale/nonfinite rejection, strict RED recovery, and staged review evidence.  
See `references/shadow-portfolio-target-tdd-slice.md` for the minimal inert Step 3 portfolio-target pattern: truthful raw-score thresholding, deterministic top-N/equal weights, cash-aware turnover, closed no-authority schemas, strict TDD, and fresh staged ad-hoc verification.  
See `references/shadow-target-hold-repair.md` for the adversarial Step 3 HOLD-repair pattern: compatibility-rooted universe identity, internally content-bound holdings/cash/cost/constraint identities, explicit liquidation lines and costs, canonical numeric hashing, rank coherence, public-dataclass invariant closure, mutation-bypass checks, and frozen staged-candidate verification.  
See `references/shadow-delta-independent-review.md` for exact staged-candidate review of inert Step 4 proposed deltas: detached public-line invariants, strict Boolean status fields, pending-order completeness, baseline-comparison scope, external adversarial probes, and fail-closed PASS/HOLD reporting.  
See `references/shadow-delta-hold-repair.md` for the corresponding Step 4 HOLD-repair pattern: exact detached arithmetic and state coherence, strict public scalar types, completeness- and provenance-bound pending-order snapshots, documented signal/target divergence, external-temp adversarial verification, and staged tree/diff freezing.  
See `references/step5-direct-final-create-spike.md` for the VALIDATED Step 5 direct-final root-relative `FILE_CREATE` protocol spike: windows-sys 0.61 feature gates, hand-declared NtCreateFile/NtQueryDirectoryFile FFI, the `FileAttributeTagInfo` read-access pitfall, the post-create verification ladder, and the fail-closed crash-residue contract (no atomic visibility, no auto-repair).

## 2. Dashboard Subprocess Log Streaming

When a Tkinter dashboard needs to show live output from a long-running subprocess (e.g., model training):

### Pattern

1. **Launch** with `subprocess.Popen(..., stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)`
2. **Read** stdout in a background `threading.Thread`; push each line into a `queue.Queue`
3. **Drain** the queue from the Tk thread via `root.after(ms, drain_callback)`
4. **Render** into a `tk.Text` widget:
   - Keep widget in `disabled` state between inserts
   - Use `widget.configure(state="normal")`, `insert()`, `see("end")`, then `configure(state="disabled")`
   - Prefix lines with timestamps
5. **Button state:** disable while running, re-enable when a sentinel string (`__DONE__`) appears in the queue

### Why this pattern

- Tk event loop must never block on I/O
- Subprocess stdout is a stream, not a file
- `queue.Queue` is the thread-safe bridge between worker and Tk threads

See `references/tkinter-subprocess-log-streaming.md` for complete code.

## 3. Data Boundaries

- `/data` folder (massive SQLite stores) is **read-only** for code agents unless explicitly authorized.
- Training reads from `vesper/data/massive/sp500/sp500_ohlcv.sqlite`.
- Model artifacts write to `models/`.
- Engine state writes to `data/engine_state.json`.

## 4. Background Execution for Training Jobs

**NEVER** poll a long-running training job with repeated `terminal()` calls. The user explicitly rejects this pattern.

### Correct pattern (one tool call)

```python
terminal(
    command="python scripts/train_model.py",
    background=True,
    notify_on_complete=True,
)
```

This counts as **one** tool call. The process runs to completion; you get one notification with the full output. No polling. No burn-through of the tool-call budget.

### Pitfalls

- **Polling loop** (forbidden): calling `terminal()` every 4–5 seconds to check status.
- **Duplicate launches**: starting the same background job again before the first finishes.
- **Missing notification**: forgetting `notify_on_complete=True` and never learning the result.

If you need mid-run progress, have the script write to a log file (`--log-file`) and read that file separately — do not launch duplicate processes. If asynchronous completion notification is unavailable in a one-shot/cron session, use one blocking `process(action="wait", session_id=...)` after the launch to obtain the exit result; do not substitute a repeated polling loop. A background launch can still return a valid process session while declaring notifications unsupported. When command output is redirected to a run log, treat the process exit code plus a parsed result artifact (for example, model metadata or a ranking JSON receipt) as the verification evidence rather than expecting diagnostic stdout from `wait`.

## 5. Model Evaluation Thresholds & Experiment Reporting

Report every experiment in a **standard table**:

| Experiment | Train IC | Test IC | Delta | Verdict |
|------------|----------|---------|-------|---------|

### IC interpretation (XGBoost on raw price/volume features)

| Test IC | Meaning | Action |
|---------|---------|--------|
| < 0.02 | Noise | Stop tweaking hyperparameters; need better features or architecture |
| 0.02–0.04 | Weak positive | Marginally viable; check backtest for actual trades |
| 0.05–0.10 | Minimum viable | Worth paper trading after cost analysis |
| > 0.10 | Good | Strong candidate for live deployment review |

### Key findings from prior experiments

- **Heavy regularization improves generalization.** Default (200 trees, depth 4, alpha=0.1) gave train IC 0.14, test IC 0.022. Heavy reg (50 trees, depth 2, alpha=5.0, lambda=20.0) gave train IC 0.043, test IC **0.032**.
- **Shorter horizon is not automatically better.** Switching from 5-day to 1-day forward returns reduced test IC from 0.022 to 0.016.
- **Raw price/volume features plateau around 0.03 IC.** To break through, switch to sequence models (transformers) or alternative data.

## 6. Controlled V20 Regularization Experiment Ticks

For a bounded research tick that changes one XGBoost capacity/regularization variant, treat the iteration-state JSON as the sole manifest and the active model path as a mutable candidate slot:

1. Read state plus the baseline directory before editing. Before creating the next record, assert that the proposed run number is absent from both terminal lists (`accepted` and `rejected`) and that no `pending` record exists. Predeclare exactly one candidate, increment the run counter once, and persist a `pending` record before training. This prevents a rerun or overlapping cron tick from silently reusing a receipt number.
2. Hold the protocol fixed unless the manifest explicitly changes it: feature set, label horizon, chronological cutoff, split-adjusted local data, and seed. Change only the declared capacity/regularization parameters.
3. For a trainer-source change, first search the directly related tests for every assertion that encodes the active model parameters. Make one TDD slice: update **all** candidate-parameter expectations, observe a focused metadata assertion fail against the previous parameters, make the smallest parameter-only change, then observe the focused tests pass. Do not stop after the first focused test: run every directly related metadata test before training, because a second assertion can still encode the accepted baseline. On rejection, restore every candidate-specific test expectation as well as the trainer/model/metadata, then rerun the focused tests against the restored baseline; never leave a stale candidate-only assertion behind.
4. Capture candidate evidence before deciding: metadata/hash, train and out-of-sample IC, and a no-submit ranking diagnostic with rank IC and top-minus-bottom spread. Parse the diagnostic according to its nested receipt schema: `receipt["results"]["ml_model"]["mean_rank_ic"]` and `receipt["results"]["ml_model"]["mean_top_bottom_spread"]`; do not assume top-level `rank_ic` or `ranking_spread` keys. Validate the values are finite before applying a gate. If a declared parameter change produces a candidate model hash identical to the accepted baseline, record that fact explicitly; still apply the metric gate mechanically and do not promote merely because the candidate configuration differs. A model at the active path is evidence only, never deployment readiness.
5. Apply the manifest acceptance gate mechanically. On any failed gate or command failure, restore trainer, model, and metadata byte-for-byte from baseline; finalize the state as rejected with logs, diagnostic path, parameters, metrics, and deltas; then remove `pending`.
6. On acceptance only, copy the exact trainer/model/metadata into baseline and update baseline metrics and artifact hash in state. After either disposition, verify active-to-baseline hashes and parse all JSON receipts.

If a one-off verification probe is necessary, create it outside the repository in the approved temporary directory, run it once, and remove it after a passing result. Preserve only its verifiable conclusion in the durable receipt. A probe stored outside the repository must explicitly add the repository root to `sys.path` before importing project modules; its own file location is not an import root.

**Do not compress a multi-step verifier into `python -c`.** Compound statements such as `with`, `try`, and `for` cannot follow a semicolon in a one-liner and can turn a required restoration check into a syntax error. Write a uniquely named temporary `hermes-verify-*.py` probe outside the repository, execute it with `PYTHONDONTWRITEBYTECODE=1`, then delete it and verify deletion. This is especially appropriate when checking disposable metadata serialization, active-to-baseline hashes, manifest terminal state, and diagnostic receipt parsing in one probe.

For cron-managed bounded ticks, honor any explicit intermediate-delivery contract exactly. If the task requires `[SILENT]` until a terminal run, persist evidence in the permitted receipts but return exactly `[SILENT]` for earlier runs—do not append verification narration or a status summary.

### Strict write scopes and Python bytecode

When a bounded V20 tick explicitly permits writes only to selected source, test, model, and report paths, prevent Python from creating `__pycache__/*.pyc` outside that allowlist. Running a script or importing its module can otherwise create bytecode under `scripts/__pycache__/`, which is an unauthorized filesystem write even when source changes are restored.

- Prefix training, diagnostic, and pytest commands with `PYTHONDONTWRITEBYTECODE=1` when imports would write caches outside the approved paths.
- Do **not** use `python -m py_compile` when its bytecode destination is outside the write scope. For a no-write syntax check, compile source in memory: `python -c "from pathlib import Path; compile(Path('scripts/train_model.py').read_text(encoding='utf-8'), 'scripts/train_model.py', 'exec'); print('syntax ok')"`.
- On this Windows/Git-Bash host, run V20 tests from the project root with `PYTHONPATH=.` because the repository is not installed as a package; a bare `pytest -q` can fail collection with `ModuleNotFoundError: vesper` even when code is correct. Supply pytest `--basetemp` in native Windows form such as `D:/tmp/pytest-run-10`, not MSYS `/d/tmp/pytest-run-10`: the default user Temp `pytest-of-<user>` root can be ACL-locked and Windows `pathlib` may interpret the MSYS form as `C:\\d\\tmp\\...`. Create the disposable external directory, run `PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 pytest -q --basetemp=D:/tmp/pytest-run-10`, then remove it from outside the leaf and verify its absence. Treat a temporary-path setup error separately from a test failure.
- Establish this before candidate training; do not rely on deleting an unauthorized cache afterwards, since deletion can itself violate the scope.
- Continue to parse JSON receipts and compare active/baseline hashes after disposition.
- A worktree may not expose usable Git metadata. In that case, retain scope and restoration evidence with byte-level comparisons (`cmp -s` or SHA-256) for active trainer/model/metadata against their baseline copies, plus explicit readback of the terminal state record and candidate receipt. Do not treat an unavailable `git diff` as verification.
- Put each external verifier in a uniquely named temporary leaf directory, execute it only after the candidate process exits, then remove that leaf and verify it is absent. This keeps verifier cleanup independent of shared pytest or system temporary roots.

### Post-restoration verifier for candidate ticks

A rejected candidate can leave the repository *looking* correct while an active file, test expectation, or receipt is stale. After restoring the trainer, model, metadata, and any candidate-specific tests, run one small ad-hoc verifier from an approved external temporary directory, then remove it. The verifier should use the project venv with `PYTHONDONTWRITEBYTECODE=1` and assert all of the following:

1. The active `MODEL_PARAMS` and metadata serialization reflect the accepted baseline, using a disposable model file under an OS-safe temporary directory.
2. Active trainer, model, and metadata SHA-256 values equal their baseline copies byte-for-byte.
3. The iteration state parses, has no `pending` record, and its final accepted/rejected record names the completed run.
4. The candidate ranking receipt parses and has the expected finite/positive spread when that was part of the captured evidence.
5. Any candidate-specific test expectations have been restored to the accepted baseline values, and the active trainer source compiles in memory. This proves that a rejected parameter edit did not leave the trainer/tests asserting the rejected candidate while the model bytes were restored. When the candidate adds a `MODEL_PARAMS` key, explicitly assert that key is absent from both restored trainer source and its exact-metadata test; source/artifact hashes alone cannot prove the test expectation was restored.
6. Parse the just-appended Markdown experiment-log entry as part of finalization, so state, JSON receipt, and human-readable receipt agree on the same run number and verdict.
7. Run the focused metadata/trainer test only after every restoration write has completed. A candidate-era green test does not validate the restored baseline contract; keep the successful post-restoration command/output in the run evidence.

Use a uniquely named external verifier script under an OS-safe temporary directory (rather than a compound `python -c` command), execute it with `PYTHONDONTWRITEBYTECODE=1`, then remove both the script and its temporary directory. This is a verification action only: it does not promote a model or change the deployment gate. It remains required even when a candidate source edit was restored, because restoration itself is a behavior-critical branch.

**Cleanup is a terminal gate.** Do not return an intermediate-delivery token such as `[SILENT]` after a verifier succeeds if removal of its temporary script or leaf directory failed. First confirm the verifier process exited, retry cleanup from outside that leaf (so no shell/process has it as a current directory), and verify the path is absent. If cleanup still cannot be verified, finalize the experiment fail-closed and report the unresolved cleanup rather than implying a fully verified silent tick.

**Windows temporary-directory cleanup recovery.** A successful verifier followed by `rm: ... Device or resource busy` is a failed terminal gate, not a harmless warning. Do not send `[SILENT]`, rerun the experiment, or create another verifier until cleanup is resolved. Run cleanup from a directory outside the temporary leaf; if the first removal fails, wait briefly for the child Python process/file handle to release, then retry and assert the leaf is absent. If a bounded job cannot perform a verified cleanup within its remaining budget, preserve the receipt/state, leave the experiment fail-closed, and deliver a concise explicit blocker instead of a silent-success token.

**Empty-but-busy leaf diagnostic.** A Windows temporary leaf can remain locked even after the verifier exits and its file has disappeared. From a directory outside the leaf, inspect the leaf contents and relevant Python/pytest processes before retrying deletion. If the leaf is empty but both Git Bash removal and `cmd.exe rmdir` still report an in-use handle, do not treat the successful verifier as a fully clean terminal gate. Record that the verifier passed, state that the empty directory could not be removed, and return the explicit cleanup blocker rather than `[SILENT]`. Do not rerun the candidate merely to clear this lock.

**Do not mask cleanup failure in chained shell commands.** Preserve verifier/test status and cleanup status separately. A sequence such as `rm -rf <leaf>; test ! -e <leaf>; exit $code` can incorrectly return the earlier verifier status when `$code` is restored after a failed absence assertion. Make the final status depend on cleanup confirmation (for example, `rm -rf <leaf> && test ! -e <leaf>`), or explicitly combine both statuses. If the leaf remains after Git Bash and `cmd.exe rmdir` retries, final delivery must be an explicit cleanup blocker—not `[SILENT]`.

### Receipt-write safety in Git Bash

When updating a Markdown experiment log from Windows Git Bash, do **not** embed Markdown backticks inside a double-quoted `python -c "..."` shell command: Bash treats backticks as command substitution and can silently strip paths, hashes, and parameter names while leaving a superficially valid log. Prefer `write_file`/`patch` for a targeted Markdown correction, or use a separately written script/file with shell-safe quoting. Immediately read back the newly written receipt and verify its parameter table, artifact paths, and candidate hash before finalizing the manifest.

### Tool-budget reservation for bounded cron ticks

A bounded tick has terminal obligations after model training: candidate diagnostic readback, disposition/restore or promotion, receipt and manifest finalization, and active-to-baseline verification. Reserve enough tool calls for those steps **before** starting the long training command. Do not spend the final available calls on broad discovery or optional checks.

If a turn/tool-call ceiling is reached after training, do not report an unverified candidate as completed. The safe terminal state is the recorded fail-closed disposition (restored baseline when rejected) and the required intermediate-delivery token such as `[SILENT]`; the next tick must begin by verifying the terminal receipt and active/baseline hashes before proposing another candidate.

**Finalization-first reservation:** Once training and the ranking diagnostic have completed, stop optional discovery, duplicate source reads, and secondary CodeGraph queries. Reserve the remaining calls in this order: (1) execute the restore-or-promote transaction, (2) run the required post-disposition verifier, (3) read back state/receipt/hashes, and only then run any additional focused test or review. Do not spend the final call writing a verifier or finalizer without enough budget to execute it; a prepared but unexecuted restoration script is not a fail-closed disposition.

## 7. Research Evidence Visualization

When displaying bounded model-search results, prevent raw candidate scores from being mistaken for selected or deployable improvements.

- Plot **individual candidate outcomes** as dots, with an explicit accepted/rejected status.
- Plot a separate **best-observed-so-far stair-step** line so the research trajectory is legible over time.
- Draw both the active-baseline metric and the predeclared promotion threshold.
- Label the best-observed candidate as a *research leader*, not the active model, unless it passes every gate (for example, OOS IC and ranking-spread requirements).
- Surface the rejection reason in the accompanying table or detail pane. A candidate above the baseline can still fail the material-improvement threshold or another required metric.
- Never manufacture a monotonically improving chart by hiding failed candidates; distinguish noisy raw trials from the running leader honestly.

### Read-only backtest/control evidence in the dashboard

When adding an operator surface for a backtest or control audit, treat the structured audit receipt as its sole summary authority. A companion log may be diagnostic support but must not override the receipt. Use a small pure loader/formatter with RED→GREEN tests before connecting it to Tk; missing, malformed, or incomplete evidence must render `EVIDENCE UNAVAILABLE`.

The view must display the run window, result, relevant control count, source path, and a literal boundary such as `backtest evidence only; not promotion or execution readiness`. Derive status mechanically: any positive stale/unsafe/control-finding count is `CONTROL FINDING OPEN`, never `corrected`, `clear`, or green based on a filename or narrative. The surface stays read-only: do not start a run or mutate audit/model/risk/execution state from the dashboard. Verify by opening the real Tk view and asserting its displayed receipt-backed values, then run the full suite with the repository interpreter/venv that provides the project dependencies.

## 8. Backtest Debugging Checklist

If the backtest shows **0 trades** or **0% return**, check in order:

1. **Lookback ≥ max feature window + 50 days buffer.** `SMA_50` needs 50+ days of history before it produces valid values. If `lookback_days=60` and backtest starts on day 1, all features are NaN. Use `lookback = 120` minimum (or `max_feature_window + 50`).
2. **Entry threshold not blocking.** If the model outputs small predictions (common with heavy regularization), `entry_threshold: 0.001` blocks everything. Try `0.0` first, then tune upward.
3. **Rebalance interval not skipping.** `rebalance_interval: 30` means signals only fire every 30 days. For a 38-day backtest, only day 1 and day 31 generate signals.
4. **Predictions are non-zero.** Add debug logging: `log.info("Model rankings: %s", ranked[:10])` to verify the model is outputting ranked scores.
5. **Risk checks not rejecting.** Verify `RiskLimits.check_signal()` approves the signal (position size, exposure, cash reserve).
6. **File encoding on Windows.** If loading YAML config fails with `UnicodeDecodeError: 'charmap' codec can't decode byte`, the `open()` call is missing `encoding="utf-8"`. Windows defaults to `cp1252`.
7. **Risk-state freshness and daily-loss semantics.** Update broker prices before taking the day snapshot; before each same-day signal, fetch the current account and positions again so prior fills affect the next risk check. Compute `daily_pnl` from prior-session equity, not cumulative backtest P&L. Add a regression test with consecutive same-day buys and verify that configured position and exposure caps cannot be exceeded. If this repair changes results, invalidate and rerun previous economic conclusions.

## Common Pitfalls

1. **Skipping skills/codegraph.** The user will call this out. It is a first-class error.
2. **Random train/test split on financial data.** Produces useless models.
3. **Blocking Tk callbacks with subprocesses.** Freezes the UI.
4. **Mixing POSIX and Windows paths carelessly.** MSYS/bash accepts both, but Python `pathlib` and SQLite connection strings need native Windows paths on Windows.
5. **Hard-coding credentials.** Massive/S3 keys must come from environment variables; never commit them.
6. **Polling training jobs.** Use `background=True, notify_on_complete=True`.
7. **Trusting in-sample IC.** Train IC > 0.90 is a red flag, not a good result.
8. **Assuming shorter horizon = easier target.** 1-day returns can be noisier than 5-day.
9. **Forgetting `encoding="utf-8"` on Windows file opens.** Python defaults to `cp1252` on Windows. YAML, JSON, or text files with Unicode characters (em dashes, arrows) will throw `UnicodeDecodeError: 'charmap' codec can't decode byte`. Always use `open(path, encoding="utf-8")`.
10. **Assuming Signal has `qty` field.** The `Signal` dataclass uses `strength` (a float 0.0–1.0 for position sizing), not `qty`. Accessing `sig.qty` raises `AttributeError`.

## Non-Git V20 review and environment preflight

When Brennan intentionally keeps V20 outside Git, do not make Git initialization a prerequisite and do not claim a Git diff. Use an explicit non-Git evidence contract:

1. Before changing an existing file, record its size/SHA-256 and create a scoped backup; for a new file, record `absent`.
2. Declare the complete path allowlist before editing. Afterward, record size/SHA-256 for every allowed path and compare against the before manifest. If there is no trustworthy before-state for an existing modified file, current correctness may be reviewed but accidental-churn/rollback proof remains `HOLD`.
3. Give an independent reviewer the complete changed files, contract, before/after manifest, and static-scan results. Preserve the reviewer receipt alongside focused tests.
4. Satisfy Python compilation into an external temporary `cfile` when repository bytecode is outside the write scope. Remove the temporary leaf from outside it and verify absence.
5. Do not claim a clean worktree, commit, or atomic rollback. Hash manifests and backups are the temporary control until the user chooses version control.

Before reporting a missing Python dependency or a failed full suite, verify the command used the project environment. On this Windows V20 workspace:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest -q --basetemp="$TMPROOT/pytest"
```

Check `requirements.txt` and import availability inside `.venv` before changing source or installing anything. A system-`python` `ModuleNotFoundError` is not a project dependency defect when the declared package exists in `.venv`. Use a unique native external `TMPROOT`; after the run, wait once if Windows still holds a handle, remove the leaf from outside it, and verify absence.

## Kanban review handoff caution

A V20 task routed to `triage` by the repeated-block loop breaker cannot be closed with ordinary `promote` or `complete`: `promote` accepts only `todo`/`blocked`, and `complete` rejects that triage state. Do not run `specify` or `decompose` merely to force closure because those LLM paths may rewrite or duplicate already-reviewed scope. Record the acceptance receipt, preserve the verified artifacts, and reconcile through an explicitly supported board-state path; never write the Kanban SQLite database directly. Prevent this condition where possible by avoiding repeated same-kind re-blocks for a review that can be represented as one bounded handoff.

## Verification Checklist

- [ ] Pre-flight checklist completed (skills, codegraph, project instructions).
- [ ] Model training uses chronological split and reports out-of-sample IC.
- [ ] Tkinter subprocess integration uses queue + `root.after`, not blocking callbacks.
- [ ] No credentials hard-coded in source.
- [ ] `/data` folder untouched unless explicitly authorized.
- [ ] Training jobs launched with `background=True, notify_on_complete=True`, not polled.
- [ ] Backtest lookback exceeds max feature window + 50-day buffer (e.g., 120 days for SMA_50).
- [ ] Entry threshold set to `0.0` first when debugging zero-trade backtests.
- [ ] Experiment results reported in standard table format (train IC, test IC, delta).
- [ ] All file `open()` calls on Windows specify `encoding="utf-8"`.
- [ ] Signal objects accessed via `strength` field, not `qty`.
