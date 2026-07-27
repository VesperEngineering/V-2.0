---
name: vesper-cron-operations
description: Schedule and audit Vesper unattended jobs with bounded activation, exactly-one ownership, authority closure, truthful receipts, rollback, and cross-scheduler evidence.
version: 1.4.1
---

# Vesper Cron Operations

Use when wiring Vesper Evidence Operations jobs to run on a schedule (cron), or when adding new scheduled jobs to the Vesper automation stack.

## Core principle

Cron creates governed work, not unchecked authority. Every scheduled job must pass through the safety harness before doing any real work. No job runs without an envelope, a lock, a safety assertion (where applicable), and a receipt.

## The safety harness (Layer 0)

Every governed job follows this sequence, with the strength of each control matched to the authority and exact-once claim:

```
1. Build CronTaskEnvelope  →  bind job/contract/source identity
2. Acquire owned singleton →  kernel lock or transactional owner generation
3. Assert capability deny  →  explicit credential/import/tool/network closure
4. Run bounded work        →  fixed argv, hard deadline, finite retry policy
5. Publish bound receipt   →  atomic per-run artifact + scheduler provenance
6. Release exact ownership →  compare-and-delete / kernel-handle close
```

The legacy Layer-0 classes are useful conventions, not automatic proof of these properties. If any step fails, write a truthful HELD/BLOCKED/FAIL/UNKNOWN terminal posture and exit non-zero. No step may be skipped, and a manual rerun must never overwrite natural scheduler evidence.

### CronTaskEnvelope

Frozen dataclass at `app/services/cron_task_envelope.py`. Must be constructed before any work. Validates:
- `authority_class` must be one of: `no_submit_evidence`, `research_batch`, `watchdog`, `alert_dispatcher`
- All fields non-empty, `allowed_tools` non-empty tuple
- Written to `artifacts/cron/envelopes/<job_id>.json`

### Singleton guard

`app/services/run_lock.py` uses `os.O_EXCL` for initial creation, but its timestamp-only stale reclaim and unconditional pathname unlink are **not safe for exact-once, long-running, or restart-sensitive work**. A live owner can be aged out, a successor can acquire, and the old owner can then delete the successor's lock (an ABA race).

For new authority-sensitive jobs:
- prefer a process-lifetime Windows named mutex/kernel file lock, or a transactional lease;
- bind ownership to a random nonce plus PID and process-creation identity;
- reclaim only after proving owner death, never from elapsed wall-clock time alone;
- release with compare-and-delete semantics for the same owner generation;
- pair process exclusion with a database uniqueness/idempotency constraint.

The legacy `RunLock` may remain a best-effort overlap guard for short, non-authority jobs only after its limitations are explicit. Do not cite it as singleton or restart proof.

### NoSubmitGuard

At `app/services/no_submit_guard.py`. Reads board state from two sources:
1. `PROJECT_ADVANCEMENT.md` — regex extraction of execution flags
2. `docs/VESPER_FACT_BASE.json` — JSON board section (overrides markdown)

Asserts:
- `execution_interpretation` is `bounded_paper_order_evidence_only`
- `paper_execution_scope` is `paper_only`
- Missing interpretation → fail-closed (SafetyViolation)

Only run for `no_submit_evidence` authority jobs. `watchdog` and `research_batch` jobs skip this step.

**Do not treat this guard as no-order capability closure.** It intentionally accepts `execution_allowed=true` when the interpretation is bounded paper evidence, and the guarded daily program still contains an order-submit branch when `--no-submit` is absent. For an unattended report-only proof, also prove that broker/order modules, credentials, endpoints, dynamic imports, shell/tool surfaces, and order-capable argv are unreachable. Hardcode `--no-submit` only as defense in depth.

### CronReceipt

At `app/services/cron_receipt.py`. Written at the end of every job. Validates:
- `PASS` requires `evidence_path`, must not have `error`
- `FAIL` requires `error` message
- `HELD` and `BLOCKED` are valid without evidence/error
- `started_at` must be before `finished_at`

## Cron wrapper scripts (outside repo)

Cron jobs are wired via the Hermes `cronjob` tool with `no_agent=True` and `script=<name>.py`. Wrapper scripts live in `~/.hermes/scripts/` (`C:\Users\<user>\AppData\Local\hermes\scripts\`). They are thin Python scripts that `os.chdir("D:/vesper")` then `subprocess.run` the real script at `D:/vesper/scripts/`.

For credential-closed Windows research wrappers that still use audited shared Kanban—including complete runtime/release identity (not launcher hashes alone), Hermes pre-bootstrap secret-source closure, sanitized `HERMES_HOME` with explicit `HERMES_KANBAN_DB`, hard pre-allocation output caps, Job-Object/process-tree cleanup, whole-tick kernel locking, crash-cutpoint reconciliation, and mandatory rollback-bound schedule evidence—read `references/credential-closed-windows-no-agent-wrapper.md`.

**Critical: do NOT use `.sh` shell wrappers.** See the pitfall below about MSYS bash consuming backslashes. Python wrappers avoid the problem entirely.

### Wrapper pattern

```python
"""Cron wrapper for cron_vesper_eod.py."""
import os, subprocess, sys

VESPER_ROOT = "D:/vesper"
VESPER_PYTHON = "D:/vesper/.venv/Scripts/python.exe"
safe_env = {
    key: value
    for key, value in os.environ.items()
    if not key.upper().startswith("ALPACA_")
}
result = subprocess.run(
    [VESPER_PYTHON, "D:/vesper/scripts/cron_vesper_eod.py"],
    cwd=VESPER_ROOT,
    env=safe_env,
    capture_output=True,
    text=True,
    timeout=600,
)
sys.stdout.write(result.stdout)
sys.stderr.write(result.stderr)
sys.exit(result.returncode)
```

This pattern works because:
1. `cwd=VESPER_ROOT` makes repository imports resolve without mutating the scheduler process's global cwd.
2. The wrapper names the project interpreter explicitly; `sys.executable` is the Hermes venv and does **not** become the Vesper venv merely because `subprocess.run` is used.
3. Forward-slash Windows paths avoid MSYS backslash-eating.
4. The child environment is explicit. For authority-sensitive jobs, replace the illustrative filter above with a minimal allowlist and forbid `.env` reload; Hermes sanitization does not necessarily remove broker credentials.
5. `capture_output=True` is illustrative relay code only; it is **not** a hard bound because the child can fill memory before the length is checked. Authority-sensitive wrappers must use concurrent streaming into fixed-size buffers and terminate the complete Windows process tree on overflow or timeout, as specified in `references/credential-closed-windows-no-agent-wrapper.md`.

## Finite exactly-one unattended proofs

For a bounded one-loop proof, prefer one future ISO-8601 Hermes `once` job with `--no-agent --repeat 1 --deliver local`, no prompt, no skills, and no agent supervisor. Create it only after the supervised canary and release receipt pass.

Define “exactly one” by a canonical activation fingerprint over contract hash, source/release hash, launcher hash, authority class, state root, and schedule. Inventory every Hermes profile, Windows Task Scheduler by name **and action**, services, startup entries, wrappers, and live owner/lease state. Other legitimate report-only jobs may coexist; the claim is exactly one enabled launcher for the approved fingerprint.

Read back and preserve the complete persisted job definition before it can fire. Verify the Hermes scheduler/gateway service is actually running before the scheduled instant—arming a one-shot while the scheduler is quiesced can leave it past due with `last_run_at=null`. If an approved one-shot is already overdue for that reason, restart the scheduler and allow normal overdue-job handling; do not recreate it or use a manual `run`, because either action destroys the natural-trigger claim. Poll while the exact job ID remains visible and join any terminal scheduler metadata to the bound controller receipt. After natural execution, some scheduler surfaces remove the finite job from the active list instead of retaining a terminal row; absence alone is not success evidence. Prove closure from the preserved pre-fire definition, wrapper/source hashes, scheduler-owned run identity/time, exactly one validated controller receipt/ledger activation, and absence of any remaining enabled fingerprint. A manual trigger, `last_status=ok`, elapsed wall-clock time, job disappearance, or an agent supervisor is not equivalent evidence.

Rollback is scoped: pause/read back the exact ID, preserve execution history and receipts, stop only its owned child, remove only that ID after terminal reconciliation, and verify the fingerprint is absent across every scheduler plane. Never restore a whole old `jobs.json` over concurrent jobs.

## Artifact layout

```
artifacts/cron/
  envelopes/     — task envelope JSON per job
  locks/         — run lock files (transient, released after job)
  receipts/      — final receipt JSON per job
  assertions/    — no-submit assertion JSON (no_submit_evidence jobs)
  status/        — heartbeat/status JSON (watchdog jobs)
  alerts/        — alert JSON files (written by watchdogs)
```

## Daily EOD loop wrapper

`scripts/cron_vesper_eod.py` wraps the existing `scripts/run_daily_paper_evidence_loop.py` with:
- `--no-submit` flag hardcoded
- Default symbol=XLK, side=buy, notional=5.00 (basket first symbol)
- 600s timeout
- Captures stdout/stderr tails in receipt metrics
- **Evidence session date:** at the scheduled 17:00 ET run, select the prior completed XNYS session with `previous_xnys_session(xnys_today(now))`, not UTC/local calendar “today.” The just-closed session may still be inside provider/EOD grace, while accepted data and candidate receipts are stamped with the prior completed session. Inject `now` into the resolver and test Monday-after-weekend plus exchange-holiday cases.
- **Natural-run evidence:** do not manually rerun the cron wrapper merely to replace a failed natural receipt; that can make a manual execution look like scheduler proof. Verify the inner no-submit loop separately, retain the failed receipt, and require the next natural scheduled receipt for scheduler closure.
- **Freshness receipt comparison:** daily OHLCV must match the expected completed XNYS session exactly. Macro-cache evidence may be newer, but its local and board dates must agree and must not predate that OHLCV session. Do not use a generic legacy no-order report or its validation sidecar to synthesize a current factor/basket candidate; preserve the explicit factor/basket authority gate.

## Research batch wrapper

`scripts/cron_research_batch.py` runs against the Windows-native island `D:/vesper-research` (own git; replaced WSL2 `~/vesper-ranker` 2026-07-19):
- Window gate first (`island/window.py`): weeknights 18:00–07:00 ET, weekends continuous. Outside window → PASS receipt `action: outside_window`, exit 0.
- Inside window: refresh manifest from `research_directions.json` (idempotent), `lease_next()` one dependency-ready PENDING item, run it via `island/runner.py` under `D:/vesper/.venv-gpu` with hard wall-clock `budget_seconds`, validate artifact against the 13-field schema, mark COMPLETE/FAILED, write receipt.
- No pending items → PASS receipt `action: no_pending` (honest idle, not green noise).

### Replacing or adding a recurring research supervisor

A new recurring experiment executor must be duplicate-safe across both the cron registry and the experiment lifecycle:

1. **Inventory first.** Read all enabled and paused Hermes jobs, Windows tasks, wrappers, and current locks. Classify exact executors separately from adjacent producers/bridges/watchdogs. Never enable a second executor merely because the existing one is presently no-op.
2. **Do not assume cron create is idempotent.** Hermes cron creation has no idempotency key. Under an installer lock, match exact name + script + cadence + workdir + source/definition fingerprint across active and paused jobs. Reuse one exact match, create only when count is zero, and HOLD on multiple or mismatched definitions. Persist the returned job ID and definition hash in the activation receipt/Kanban handoff.
3. **Use one deterministic no-agent tick.** The wrapper may advance at most one dependency-ready experiment and must impose its own timeout, exact source hash, minimal environment, fixed argv, CPU/GPU authority boundary, and singleton owner. A standing `/goal` or Kanban goal-mode worker is not a recurring scheduler primitive.
4. **Define idle narrowly.** Scope the query to the canonical program/root IDs, experiment key prefix, lifecycle states, task runs, queue, and owned locks. A board-wide “no nonterminal cards” check is wrong because historical blocked cards can remain indefinitely. Treat outside-window/no-work as explicit `IDLE`/no-op evidence.
5. **Recovery reconciles; it does not rerun ambiguity.** Derive the experiment key from immutable objective, data manifest, evaluator and candidate-spec hashes. A validated terminal receipt may be replayed/reconciled without executing work. A stale lease, partial artifact, missing terminal receipt, conflicting owner, or changed hash becomes `HELD`; never reset it to PENDING or blindly rerun it. Use monotonic transactional lifecycle state in addition to process exclusion.
6. **Replace an exact conflict before enabling.** Pause and read back the old executor, then create/probe the replacement. Keep the old ID for rollback; do not remove history or restore a whole `jobs.json`. Rollback starts with `hermes cron pause <new-id>` and exact read-back.
7. **Isolate artifact/card namespaces.** Adjacent direction-sync and candidate-bridge jobs may remain only when they cannot consume the new supervisor's artifacts or create duplicate reviews. A review-card idempotency key must bind the experiment/receipt hash, not optional display fields.

**Legacy bridge warning:** `research_to_kanban_bridge.py` historically keyed cards as `research-bridge-{source_commit}-{name}` and defaulted missing `name` to `unnamed`. Multiple unnamed artifacts from one source commit can collapse onto one card. It also marked paths processed after card-creation failure, which can lose delivery rather than retry safely. Do not feed a new recurring supervisor into the legacy `candidate_factor_*.json` namespace until the bridge has an immutable experiment identity and success-only processed marker.

See `references/session-2026-07-21-milestone-c-research-schedule-preflight.md` for the Milestone B proof chain, current conflicting job inventory, and a concrete bounded tick contract.

## Watchdog jobs

Health watchdog checks: EOD receipt age, research receipt status, data freshness (from fact base), kanban blocked-card age.
Disk/VRAM watchdog checks: `shutil.disk_usage` for disk, `nvidia-smi` for GPU (Windows first, WSL2 fallback).
Both write status to `artifacts/cron/status/` and alerts to `artifacts/cron/alerts/` when degraded.

## Gateway-owned configuration changes on Windows

A terminal command launched from a live gateway session is a gateway child. `hermes gateway restart` correctly refuses there because terminating the parent can kill the command before it completes. Do not retry that action from the same gateway-owned shell or claim the changed setting is live merely because it was written to `config.yaml`.

For a configuration change that requires restart:
1. write and read back the configuration;
2. restart from an **independent host context** (an operator terminal or an independently-owned Windows Task Scheduler action), never a gateway child;
3. verify a healthy gateway process and current cron heartbeat; and
4. confirm runtime behavior from logs or a bounded dry-run.

If the independent restart needs an OS approval and it is not granted, stop at the configured-but-not-active state and report that exact remaining action.

## Windows Task Scheduler audit protocol

Treat Windows Task Scheduler, Hermes cron, steward/recovery automation, and process-owned workers as one authority graph. A read-only audit must join installed scheduler state to the complete action closure and its evidence; no single source is sufficient.

1. **Enumerate by both name and action.** Find Vesper-named tasks and any task whose executable, arguments, or working directory references Vesper/Hermes/runtime roots. Capture enabled/state, trigger, principal/logon type, last/next run, decimal+hex result, action/arguments/cwd, timeout, battery/catch-up policy, and multiple-instance policy.
2. **Trace the full closure.** Follow task → launcher → wrapper → script/module → endpoint. Verify every hop exists and is Git-tracked or release-manifested, and record hashes plus the effective root. A tracked first-hop wrapper can still call an untracked or missing helper.
3. **Prove deployment identity.** A `0` result is not canonical readiness if the task ran a shadow copy. Compare governance/config hashes, source identity, output/receipt roots, and representative artifact hashes across every runtime root.
4. **Join result, log, and receipt.** Check whether the Task Scheduler Operational log is enabled before expecting event history. Require wrapper start/end evidence and a receipt unique to job + scheduled trigger/run ID. Repeated triggers must not overwrite one daily receipt.
5. **Require scheduler provenance.** Receipt freshness alone is insufficient. Include and verify scheduler, job ID, scheduled-for time, run ID, run origin, source commit, action/config hash, start, and finish. Never overwrite a failed natural-run receipt with a manual rerun and then call the scheduler healthy.
6. **Use market-session readiness.** Recovery checks for market pipelines must join to the authoritative completed exchange session or a run manifest, not wall-clock `today` filenames.
7. **Audit all scheduler planes for duplication.** Windows primary/backup/recovery tasks, Hermes agent jobs, and steward recovery can all produce the same artifacts. Select one canonical owner before repairing schedules; otherwise a green backup can coexist with conflicting outputs.
8. **Classify capability separately from observed effects.** Provider-read, account-read, order-read, order-submit, cancel, and broad rebalance are distinct authority classes. Missing files/credentials or repeated failures are accidental inertness, not parking. Order-capable tasks are parked only when explicitly disabled or capability-denied.
9. **Map process topology before calling duplicates/orphans.** Group launcher/shim/interpreter descendants into logical roots. For Hermes Vesper workers, join PID to read-only Kanban status, heartbeat, and run ID. A detached gateway can legitimately have an exited launcher parent.
10. **Separate repair classes.** Routine engineering fixes (date quoting, stale one-shot removal, logging/provenance, session-aware freshness) still need approval before changing scheduled behavior. Root ownership, broker reconciliation, order-envelope changes, and canaries remain parked pending explicit authority.

### Windows batch date/session resolvers

Do not embed Python `-c` expressions inside a batch `for /f` command when the expression contains nested quotes, parentheses, and percent-format tokens. `cmd.exe` has multiple parsing layers; a syntactically plausible line can leave the captured variable unset before the guarded runner starts.

Use this class-level pattern instead:

1. Put exchange-session resolution in a tracked Python script whose stdout is exactly one `YYYYMMDD` token.
2. Reuse the canonical market-calendar helpers and select the prior completed XNYS session, not wall-clock calendar `today`.
3. Capture it with `for /f "usebackq delims=" %%D in (`"%PYTHON%" scripts/resolver.py`) do ...`.
4. Fail closed if the variable is undefined, and keep `--no-submit` hardcoded in preview wrappers.
5. Test in two layers: fixed-time Python regressions (Monday/weekend and exchange holiday) plus an exact resolver-only `.bat` canary. The resolver-only canary must not invoke the evidence loop, broker/account/order code, or the installed task.
6. After reviewed source reaches the canonical deployment, run one installed preview-only canary and join scheduler result, wrapper log, and receipt. Do not use a preview repair as authority to trigger an order-capable task.

For the concrete 2026-07-20 audit evidence, action-map categories, and validation ladder, read `references/session-2026-07-20-windows-scheduler-order-safety-audit.md`.
For the RED-to-GREEN batch resolver repair, exact canary pattern, and preconditioned disabling of missing-action order tasks, read `references/session-2026-07-20-windows-preview-repair-and-task-parking.md`.

### Truth-layer rules (learned 2026-07-19, VQ-20260719-001/005)

Every health check MUST be capable of failing. The 2026-07-19 audit found the watchdog was false-green for days because every check had a structural "can't-fail" defect. When writing or auditing checks, enforce:

1. **No unconditional `healthy`.** `_check_data_freshness` returned healthy forever with the date as a cosmetic string. A freshness check must parse the date and COMPARE it to now (`MAX_OHLCV_AGE_DAYS = 4` covers weekends).
2. **Calendar-aware staleness.** A fixed `STALE_RECEIPT_HOURS = 48` against a Mon–Fri 17:00 ET schedule false-alerts every weekend (Fri→Mon = 72h). Compute the last *scheduled* run (`_last_scheduled_eod_run`, America/New_York + grace) and compare the receipt to it.
3. **Dry-run/manual receipts are not scheduled evidence.** Check `metrics.dry_run` and downgrade to `unknown`; monthly reviews must not count them either (P1 #7 below).
4. **PASS must mean productive.** Research batch emitted `PASS {action: no_queue}` ~144×/day against a WSL repo with no queue and no research code. Surface idle actions explicitly in the detail (`last status=PASS (idle: no_queue)`), and treat "no work existed" as a lane-level finding, not health.
5. **Any receipt status ≠ healthy.** `_check_research_receipt` reported healthy even for FAIL. Map status: PASS→healthy, FAIL→unhealthy, missing→missing.
6. **Exercise the alert path end-to-end once.** The first truthful watchdog run was also the first real alert the dispatcher ever attempted — it immediately exposed unconfigured Telegram AND the move-on-fail bug. Fixing a false-green check doubles as the alert-chain integration test; watch the next dispatcher receipt.
7. **Watch the watched entities' ages, not just receipts.** Blocked kanban cards sat 51h with no escalation while the agent layer was paused. `_check_kanban_blocked` (48h, read-only SQLite) surfaces them deterministically.
8. **Cap repeat alerts for persistent conditions.** Without a cooldown, a stale-data condition writes a new alert every 30-min tick (~48 msgs/day). `_alert_recently_raised()` suppresses same-name alerts within `ALERT_REPEAT_COOLDOWN_HOURS = 6`, scanning pending AND dispatched filenames. One notification per condition per window; resolution is proven by the check going green, not by alert silence.

**Testability pattern:** write check functions as `_check_x(path=None, now=None)` defaulting to live paths/now. Tests inject tmp paths and fixed datetimes — no monkeypatching, no clock freezing. RED-first: write the failing-truth tests before repairing the check.

## Pitfalls

- **pytest tmp_path permission error**: Windows `C:\Users\...\AppData\Local\Temp\pytest-of-bgonn` can get ACL-locked. Use `--basetemp=/d/vesper/.pytest_tmp` to redirect.
- **WSL2 path access from Windows**: Use `wsl bash -lc 'command'` — not direct path translation. `~/vesper-ranker` in WSL2 is not accessible as a Windows path.
- **Pre-commit ruff scope**: The repo's `.pre-commit-config.yaml` only enforces `F,E9` (pyflakes + syntax). Full ruff lint (`D`, `UP`, `I`, `N`) produces many style warnings but they are not blocking. Run `ruff check --select F,E9` for the enforced baseline.
- **Cron delivery in TUI**: Cron jobs with `deliver=local` save output but do not deliver live into the TUI session. Alerts are written to files for the operator surface (Layer 2) to pick up.
- **Existing daily loop requires parameters**: `run_daily_paper_evidence_loop.py` needs `--date`, `--symbol`, `--side`, `--notional`, `--no-submit`. The cron wrapper supplies these.
- **Status prefix matching vs substring**: Vesper receipt statuses like `PASS_NO_ORDER_FAIL_CLOSED_RECORDED` contain both "PASS" and "FAIL". Use `status.startswith("PASS")` not `"PASS" in status` when counting pass/fail in monthly reviews. Substring matching double-counts.
- **Hermes cron script path constraint**: The `cronjob` tool requires the `script` parameter to be a bare filename (e.g. `vesper_daily_eod.py`), not an absolute path. The script must live in `~/.hermes/scripts/` (i.e. `C:\Users\<user>\AppData\Local\hermes\scripts\`). Passing an absolute path produces: `Script path must be relative to ~/.hermes/scripts/`.
- **MSYS bash eats backslashes in `.sh` wrappers (CRITICAL)**: Shell scripts launched by Hermes cron run through bash (git-bash/MSYS). MSYS bash interprets Windows backslash paths like `C:\Users\...` as escape sequences, producing garbled paths like `C:UsersbgonnAppDataLocalhermesscripts...`. This caused all 7 cron jobs to fail with `exit code 127` (file not found) on their first scheduled runs. **Three attempts to fix this:**
  1. `.sh` wrappers with `/d/vesper` MSYS paths → Python interpreted as `D:\d\vesper` (wrong)
  2. `.sh` wrappers with `D:/vesper` Windows paths → MSYS bash still mangled the wrapper path itself
  3. **Working fix:** thin Python wrapper scripts in `~/.hermes/scripts/` that use forward-slash native paths, an explicit project interpreter, and `subprocess.run(..., cwd="D:/vesper", shell=False)`. No shell and no Windows backslashes. Do not use `sys.executable` unless the target is intentionally compatible with the Hermes venv.
- **Python wrapper needs an explicit child cwd and interpreter**: Copying the real script directly to `~/.hermes/scripts/` can fail with `ModuleNotFoundError: No module named 'app'`, and `sys.executable` remains the Hermes interpreter. Invoke `D:/vesper/.venv/Scripts/python.exe` explicitly and pass `cwd="D:/vesper"` to the child. Avoid process-global `os.chdir` in scheduler code.
- **Cron job IDs change on recreate**: When you delete and recreate a cron job (e.g. to fix a script path), the `job_id` changes. Any references to specific job IDs in docs or scripts must be updated. Use `cronjob action=list` to get current IDs.
- **Manual triggers prove only the application path.** After wiring a routine cron job, a manual trigger can verify launcher/application behavior, but it does not prove natural scheduler timing, wake/catch-up behavior, scheduler provenance, or exactly-once firing. Keep manual and natural receipts distinct. For a one-shot proof, read back the armed definition before fire and require the subsequent natural execution record plus bound terminal receipt.
- **Live wrappers must name the actual interpreter and canonical target.** Inspect each `~/AppData/Local/hermes/scripts/vesper_*.py` wrapper to prove its explicit child interpreter, `cwd`, target script, environment filter, and timeout. Never infer wiring from naming. The in-repo script is canonical only when the wrapper and release manifest bind its exact bytes/source identity.
- **Blanket "resume them" is not blanket authority.** Before resuming paused cron jobs en masse, group by `paused_at` cohort — distinct pause dates are distinct decisions (2026-07-19: a Jul-15 agent-layer lockdown cohort vs an older Jul-9 retired-Swing-era script cohort). Resume only the cohort the operator means. Broker/order-class jobs (e.g. Alpaca Rebalance) require explicit individual approval every time — never resume them on a blanket instruction; name the held exception in your reply so the hold is visible.
- **“Continue autonomous delivery” after a pause is a scoped continuity instruction, not a global resume.** Resume only the current project’s coordination/research cohort that was paused together, then read back every resumed job’s `enabled`, `state`, schedule, and `next_run_at`. Keep broker/order jobs paused, do not revive expired finite supervisors or obsolete experiment ticks, and leave unrelated project cohorts untouched unless the operator names them. Report the resumed cohort and the explicitly held capability boundary succinctly.
- **Audit dependent-job gaps against observed durations, not intentions.** A downstream review job 5 min after its upstream (Thomas 13:05 vs pipeline 13:00) races when the upstream's observed duration is 5m20s — and worse as the universe widens (502 symbols). Set gaps to ~3× observed upstream duration. Also: Hermes fires missed jobs on wake, so a machine asleep through 19:00/20:00 collapses a 1h gap into minutes — the downstream may read an upstream that finished seconds earlier. Widen evening gaps (audit 19:00 → repair 21:00) to survive wake-bursts.
- **Read the actual job prompt before debating a schedule.** The steward's own prompt ("weekday post-pipeline recovery/dispatch check", silent on `WAITING_FOR_NEW_OHLCV`) declared semantics its 08:30-only schedule contradicted — dispatches unlocked by the 13:00 pipeline waited ~19h. Fix the schedule to match the prompt (`30 8,13 * * 1-5`: morning recovery + true post-pipeline dispatch), not the prompt to match the schedule. Prompts live in `~/AppData/Local/hermes/cron/jobs.json`; `hermes cron list` does not show them.
- **24/7 means asymmetric, not "everything runs always."** Market-facing jobs (pipeline, briefings on pipeline output, EOD) stay on market hours — running them at 3am Saturday recomputes Friday's close at token cost (false-green culture). The jobs that genuinely earn 24/7: GPU research batches, news collection, steward dispatch cadence, and the watchdog/dispatcher skeleton. When the operator asks for a "24/7 agentic workflow," propose this split, not blanket schedule widening.
- **`hermes kanban show` crashes on malformed timestamps.** A card whose `created_at` was written as a literal string (e.g. `'%s'` from a writer formatting bug) makes `_fmt_ts` raise `TypeError: 'str' object cannot be interpreted as an integer`. Fallback: read the card via read-only SQLite (`sqlite3.connect(f"file:{db}?mode=ro", uri=True)` on `~/AppData/Local/hermes/kanban/boards/vesper/kanban.db`; tables `tasks` / `task_comments` / `task_events`). There is no `kanban delete` verb — removal is `hermes kanban archive <id>`.
- **Forensically read a blocked card's comment history before acting on it.** A blocked card that looks like "needs your answers" may be a junk card (title `good`) an auto-decomposer rewrote into a plausible spec-elicitation body — and the operator may have already ordered it removed in comments. Acting on the surface title/body re-animates killed work. Check `task_comments` for prior operator instructions before asking the operator to re-decide.

## User preference: autonomous execution

The user expects you to work through implementation without asking clarification questions. When a plan exists and the user says "go," execute all steps sequentially, make reasonable default choices, and report results. Stop only for genuine blockers (safety violations, missing credentials, ambiguous authority).

This was strongly reinforced during the 4-layer cron build: the user said "Are you able to work through this without asking me anything and just get it done?" and then said "go" for each layer. The expected behavior is: build it, test it, verify it, report what passed — without pausing to ask about naming, parameters, or approach choices that are covered by the plan.

### Layered sequential execution pattern

When implementing a multi-layer plan (like the 4-layer cron build), execute each layer fully before stopping:

1. Implement all tasks in the layer
2. Run verification (pytest, ruff F+E9, py_compile)
3. Wire any cron jobs or integrations
4. Report what passed with test counts
5. Wait for "go" before the next layer

This works because:
- Layers have clear exit conditions (defined in the plan)
- Each layer builds on the previous one
- The user wants to review between layers but not between individual tasks
- The user will say "go" to proceed — don't ask "should I continue?"

## Implementation plan

See `D:\vesper\.hermes\plans\2026-07-17-agentic-workflow-implementation.md` for the full 4-layer plan. All four layers are complete (95 tests, 7 cron jobs).

## Layer 2: Operator surface (cross-system status)

Unified read-only status panel that shows Pipeline + Research health at a glance.

### CrossSystemStatus service

`app/services/cross_system_status.py` — aggregates Layer 1 cron artifacts into a single status object:

- `pipeline_health`: healthy / stale / held / blocked / down / unknown (from EOD receipt + health watchdog)
- `research_health`: healthy / idle / degraded / down / unknown (from research batch receipt)
- `alerts_count`: number of alert files in `artifacts/cron/alerts/`
- `needs_brennan`: list of items requiring operator attention (blocked pipeline, failed research, alerts)
- `overall`: healthy / attention / degraded / unknown

Reads from:
- `artifacts/cron/receipts/vesper-daily-eod.json`
- `artifacts/cron/receipts/research-batch.json`
- `artifacts/cron/status/health.json`
- `artifacts/cron/alerts/` (file count)

Stale receipt threshold: 48 hours.

### Operator terminal: two surfaces

The Vesper Operator Terminal (`app.operator_terminal.py`) has TWO interfaces:

1. **Line-oriented command mode** (batch `--command`): Rich console renderers in `app/operator_terminal_render.py`. Commands: `status`, `pipeline`, `receipts`, `cross-system`, `refresh`, `issues`, `approvals`, `help`. The `cross-system` command was added in Layer 2 and renders a Rich table with color-coded health states.

2. **Full-screen dashboard mode** (the VOT shortcut): A Prompt Toolkit `Application` in `app/operator_terminal_layout.py` (1475 lines). This is the **primary operator surface** — a mission-control layout at 2500×1015 px with:
   - PRIMARY BLOCKER card
   - EVIDENCE SPINE (pipeline chain)
   - PORTFOLIO/ACCOUNT + MARKET/DATA cards
   - STATUS/AUTHORITY + PROVIDER ACCOUNTING cards
   - WORKFORCE rail (worker phases)
   - KANBAN/WORKFLOW card (READY/RUNNING/BLOCKED/PENDING/REVIEW columns)
   - NEXT SAFE + RECENT ACTIVITY cards
   - ISSUES + APPROVALS governed panels
   - Overlay system for detail views
   - Zoom levels (0=focused, 1=balanced, 2=detailed)

   Launched via `scripts/launch_operator_terminal.py` which uses `wt.exe` to create a Windows Terminal tab at 312×63 cells, then resizes the native HWND to 2500×1015 px.

### Next step: wire cron data into the dashboard

The `cross-system` command currently lives only in the line-oriented mode. The full-screen dashboard already has panels for Kanban, workforce, provider accounting, and evidence spine — but it does NOT yet show:
- Cron job status (7 active jobs and their last_status)
- Cross-system health (Pipeline + Research aggregated status from `artifacts/cron/status/`)
- Alert count from `artifacts/cron/alerts/`

The dashboard's `_mission_control_body()` in `app/operator_terminal_layout.py` is the target for wiring. The existing `_kanban_card()`, `_provider_accounting_rows()`, and `_portfolio_rows()` functions show the pattern: data comes from `TerminalSnapshot`, which is loaded by `load_terminal_snapshot()` in `app/services/operator_terminal_status.py`. To add cron data to the dashboard, extend `TerminalSnapshot` with cron status fields and load them in `load_terminal_snapshot()`.

### Tests

`tests/test_cross_system_status.py` — 13 tests covering:
- Defaults (unknown state)
- Healthy pipeline + research
- Stale EOD receipt (>48h)
- Blocked EOD → needs_brennan
- Failed research → needs_brennan
- Alert counting
- Health watchdog override
- Active research batch
- HELD state
- Evidence links populated

## Layer 3: Triggers and alerts

### Research→Kanban bridge

`scripts/research_to_kanban_bridge.py` — watches the island artifacts dir `D:/vesper-research/artifacts/evals/candidate_factor_*.json` (moved off WSL2 watch 2026-07-19):
- Lists candidate artifacts by local glob (same filesystem — no `wsl bash -lc`)
- Validates each against required schema (13 fields: hypothesis, economic_rationale, source_commit, dataset_version, backtest_results, walk_forward_results, transaction_cost_assumptions, stability_analysis, drawdown_analysis, correlation_analysis, known_failure_modes, compute_cost, reproducibility_instructions)
- Creates Hermes Kanban card assigned to `vesper-thomas` with `--idempotency-key`
- Tracks processed artifacts in `artifacts/cron/processed/research_artifacts.txt` (dedup)
- Invalid artifacts are marked processed and skipped (not retried)

Cron: `*/15 * * * *` (every 15 min), `no_agent=True`, `deliver=local`

### Alert dispatcher

`scripts/cron_alert_dispatcher.py` — reads alert files from `artifacts/cron/alerts/`:
- Only dispatches `immediate` severity (suppresses routine success chatter)
- Dispatches via `hermes send <message> -t telegram` (gateway home channel)
- Success → alert archived to `artifacts/cron/alerts/dispatched/`
- Failure → alert STAYS PENDING with an attempts counter (`alerts/attempts/<name>.attempts`); after `MAX_DISPATCH_ATTEMPTS = 24` (~2h at 5-min cadence) it parks in `artifacts/cron/alerts/failed/` — never archived as delivered
- Core policy lives in testable `process_alert_file(alert_file, dispatch_fn, dispatched_dir, failed_dir, attempts_dir)`; tests inject a fake `dispatch_fn`

**Delivery platform config (verified 2026-07-19):** `hermes send` needs NO running gateway for bot-token platforms (Telegram/Discord/Slack/Signal) — credentials in `~/AppData/Local/hermes/.env` suffice. Telegram needs `TELEGRAM_BOT_TOKEN` + `TELEGRAM_HOME_CHANNEL` (+ optional `TELEGRAM_ALLOWED_USERS`), set via `hermes gateway setup` → Telegram (managed-bot flow via @HermesSetupBot avoids BotFather copy-paste); then send the bot any message once to register the home channel. Gotcha: `hermes send --list telegram` can show an empty directory even when delivery works — that list is channel *discovery* (populated by a gateway run), not the credential check. Verify with an actual `hermes send "test" -t telegram`, not the list.

**Telegram agent "capped on tool iterations" diagnosis:** if the gateway agent replies that it cannot investigate (zero tool calls, `api_calls=0` in `logs/gateway.log`), check `agent.max_turns` in `config.yaml` — it was found set to `0` (lockdown residue), making the bot chat-only. The gateway log prints `Agent budget: max_iterations=N` per session start; N=0 confirms. Restore with `hermes config set agent.max_turns 60` then `hermes gateway restart`. Delivery (`hermes send`) is unaffected by this — it is an agent-iteration cap, not a platform fault.

Cron: `*/5 * * * *` (every 5 min), `no_agent=True`, `deliver=local`

**Never reintroduce move-on-fail.** The original "Move to dispatched regardless (prevent infinite retry)" design silently lost every alert raised while the gateway was down — proven live on 2026-07-19 when the first real alerts failed on unconfigured Telegram and were archived as if delivered. Retry-safety comes from the attempts cap, not from dropping alerts.

### Layer 3 cron jobs

| Job | Schedule | Script |
|-----|----------|--------|
| Research→Kanban Bridge | `*/15 * * * *` | `scripts/research_to_kanban_bridge.py` |
| Alert Dispatcher | `*/5 * * * *` | `scripts/cron_alert_dispatcher.py` |

## Full cron job inventory (deterministic set, all verified `ok`)

| # | Job | Schedule | Script | Layer |
|---|-----|----------|--------|-------|
| 1 | Vesper Daily EOD Loop | `0 17 * * 1-5` | `vesper_daily_eod.py` | 1 |
| 2 | Research Batch Advance | `*/30 * * * *` | `vesper_research_batch.py` | 1 |
| 3 | Pipeline Health Watchdog | `*/30 * * * *` | `vesper_health_watchdog.py` | 1 |
| 4 | Disk/VRAM Watchdog | `0 * * * *` | `vesper_disk_vram_watchdog.py` | 1 |
| 5 | Research→Kanban Bridge | `*/15 * * * *` | `vesper_research_bridge.py` | 3 |
| 6 | Alert Dispatcher | `*/5 * * * *` | `vesper_alert_dispatcher.py` | 3 |
| 7 | Monthly Promotion Review | `0 9 1 * *` | `vesper_monthly_review.py` | 4 |
| 8 | Research Directions Sync | `*/30 * * * *` | `vesper_directions_sync.py` | closeout |
| 9 | News Attention Collector | `0 */2 * * *` | `vesper_news_collector.py` | closeout |
| 10 | Weekly Bounded Tuning | `0 10 * * 6` | `vesper_weekly_tuning.py` | closeout |
| 11 | Approval Ledger Sync | `15 * * * *` | `vesper_approval_ledger_sync.py` | closeout |

Agent-layer jobs (LLM, prompts in `~/AppData/Local/hermes/cron/jobs.json`): Research
Engineer Mon 07:00, Steward `30 8,13 * * 1-5`, Factor Pipeline 13:00 weekdays, Thomas
13:20 weekdays, nightly audit 19:00, overnight repair 21:00, weekly hygiene Sat 09:30.
Removed 2026-07-19: Daily Factor Basket, jepa-isolated-research-hour (legacy/superseded).
Alpaca Rebalance remains paused (broker-class, individual approval required).

Job IDs rotate on recreate — use `cronjob action=list` for current IDs. The closeout-wave
jobs (8-11) and their card/spec/ledger conventions are documented in
`references/session-2026-07-19-closeout-batch.md`.

## Layer 4: Guarded continuity

Implemented. Adds safe retry logic, longitudinal monthly review, and an explicit promotion gate.

### Retry policy

`app/services/retry_policy.py` — `evaluate_retry(error, attempt, max_retries=2)` returns a frozen `RetryDecision`:

- **Never retry** (goes straight to HOLD + alert): safety violations, GPU OOM, run-lock conflicts, data-freshness breaches, stale data
- **Retryable** (up to max_retries): timeouts, network errors, transient file locks
- **Unknown errors**: HOLD for operator (no retry)
- Max 2 retries, then HOLD

Tests: `tests/test_retry_policy.py` — 15 tests covering all patterns.

### Monthly promotion review

`scripts/cron_monthly_review.py` — collects daily EOD receipts from the past 30 days and produces an APPROVE / HOLD / REJECT recommendation:

- Collects `artifacts/evals/daily_paper_evidence_loop_*.json` from last 30 days
- Counts PASS/FAIL/HELD using `startswith()` matching (not `in` — avoids double-counting `PASS_NO_ORDER_FAIL_CLOSED_RECORDED`)
- Writes evidence packet to `artifacts/cron/evidence/monthly_review_<YYYYMM>.json`
- Recommendation rules:
  - No receipts → HOLD
  - >30% failures → REJECT
  - <50% pass → HOLD
  - Otherwise → APPROVE
- **Advisory only** — live capital promotion remains Brennan's explicit decision

Cron: `0 9 1 * *` (9 AM on 1st of month), `no_agent=True`, `deliver=local`

### Promotion gate (unchanged)

- Live capital remains Brennan's explicit decision
- No cron job, agent, or pipeline step can promote to live
- The monthly review produces a recommendation; Brennan approves

## Audit findings (2026-07-18 independent verification)

An adversarial READ-ONLY audit was run against the implementation report. These findings must be addressed before calling the system operational:

### P0 — Critical gaps

1. **`retry_policy.py` is dead code.** It has 15 tests but zero imports from any cron script. No job actually retries. The report claims "retry logic" as a feature but it is NOT wired. Fix: import `evaluate_retry` in each cron script's failure path, or remove the claim.

2. **EOD loop has never run on schedule.** The receipt at `artifacts/cron/receipts/vesper-daily-eod.json` has `dry_run=True` — it was written by `cron_dry_run.py` (Layer 0), NOT by `cron_vesper_eod.py`. The real EOD cron has `last_status: null`. It has never executed `run_daily_paper_evidence_loop.py` on schedule. Status: NOT YET PROVEN.

3. **No scheduler health check.** The health watchdog checks receipts and data freshness, but NOTHING checks if the Hermes cron scheduler itself is alive. If the scheduler crashes, all 7 jobs silently stop. No alert is sent because the alert dispatcher is also a cron job that won't run. What watches the watchmen? Fix: add a non-cron heartbeat (e.g., Windows Task Scheduler checks for cron receipt freshness).

4. **No alert dispatcher failure detection.** If the alert dispatcher crashes, alerts accumulate in `artifacts/cron/alerts/` but are never sent. Nobody is notified. The notification path has no fallback.

### P1 — Important gaps

5. **Receipts are conventional JSON, not technically immutable.** Plain `Path.write_text()` — no atomic writes, no hash chain, no cryptographic signing. Anyone with filesystem access can modify them. The report calls them "immutable" but they are only conventionally immutable (frozen dataclass in memory, plain file on disk).

6. **No git commit provenance in receipts.** No receipt references the source commit it ran from. A future factor/research result cannot be traced back to the exact code version that produced it. Fix: add `git rev-parse HEAD` to each receipt's metrics.

7. **Monthly review cannot distinguish dry-run from real receipts.** `cron_monthly_review.py` reads from `artifacts/evals/daily_paper_evidence_loop_*.json` — these are the existing daily loop receipts, not cron receipts. It does NOT filter out dry-run or manual test runs. A dry-run receipt with `dry_run=True` in metrics would count as a PASS, potentially inflating the APPROVE recommendation.

8. **Wrapper scripts can drift from repo.** The 7 Python wrappers in `~/.hermes/scripts/` are copies, not symlinks. If `D:/vesper/scripts/cron_vesper_eod.py` is updated in the repo, the wrapper continues calling the updated file via `subprocess.run` (this is correct), but the wrapper ITSELF is not version-controlled. If the wrapper needs changes, there's no tracking. Fix: commit the wrappers as a `scripts/hermes_cron_wrappers/` directory in the repo and symlink or copy on deploy.

### P2 — Known limitations

9. **No retention policy.** `artifacts/cron/receipts/`, `alerts/dispatched/`, and `envelopes/` accumulate without cleanup. Not gitignored-critical but will grow over time.

10. **No dependency manifest.** The system depends on: Hermes v0.18.2, Python 3.11.15, WSL2 Ubuntu 24.04, nvidia-smi 610.52, Telegram gateway config, `D:/vesper/.venv`. None of these are documented in a machine-readable manifest.

11. **Timezone sensitivity.** `0 17 * * 1-5` means 17:00 local system time. During DST (summer) that's 21:00 UTC; during standard time (winter) it's 22:00 UTC. If the system timezone changes, the EOD schedule shifts silently.

### Revised definition of done

A feature is NOT "live" until:
1. It has completed a naturally scheduled successful run (not manual trigger)
2. The receipt from that run exists and parses with correct status
3. The receipt includes provenance (git commit, config version)
4. An end-to-end acceptance test has passed (not just unit tests)
5. The scheduler health check confirms the scheduler was alive for that run

## Reference

- `references/layer0-layer1-implementation.md` — session-specific implementation detail, test results, and live verification evidence from the July 17 2026 build.
- `references/layer2-layer3-implementation.md` — Layer 2 (operator surface) and Layer 3 (triggers/alerts) implementation detail from the July 17 2026 build.
- `references/layer4-implementation.md` — Layer 4 (retry policy, monthly review) implementation detail from the July 17-18 2026 build.
- `references/session-2026-07-18-cron-wiring-fix-and-report.md` — cron wrapper path bug (three attempts), job recreation, commit/push evidence, cleanup, pre-existing dirty files, VOT dashboard discovery, and the implementation report pointer.
- `references/session-2026-07-19-truth-layer-repair.md` — false-green watchdog repair (checks that couldn't fail), dispatcher move-on-fail bug, research-island audit findings, durable retry design, VQ-20260719-001…005.
- `references/session-2026-07-19-closeout-batch.md` — directions pipeline (kanban card → spec → island queue), news attention collector, approval-ledger parity mirroring, weekly bounded tuning, worktree sweep 6→2, four new cron jobs.
- `references/session-2026-07-20-windows-scheduler-order-safety-audit.md` — read-only Windows/Hermes scheduler audit protocol, action-closure tracing, split-root evidence, natural-run receipt provenance, process topology, order-capability parking, and post-repair validation ladder.
- `references/session-2026-07-20-milestone-b-unattended-proof-audit.md` — exactly-one activation fingerprints, finite no-agent proof scheduling, broker-credential sanitization gaps, singleton ABA failure, scoped rollback, and VOT lifecycle/single-instance requirements.