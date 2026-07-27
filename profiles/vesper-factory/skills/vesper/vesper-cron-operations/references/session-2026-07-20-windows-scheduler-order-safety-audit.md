# 2026-07-20 Windows scheduler and order-safety audit

Use this as a concrete evidence pattern for future **read-only** audits. It is a dated snapshot, not current machine truth.

## Scope and posture

- Inspected repository governance and the active recovery roadmap first.
- Made no scheduler, process, source, configuration, broker, account, or order changes.
- Audited both scheduler planes: Windows Task Scheduler and Hermes cron/Kanban.
- Joined installed definitions to action files, transitive scripts, logs, receipts, process trees, and order-capable source gates.

## High-value findings

### A green task can execute the wrong root

`Vesper Factor Scores Backup` returned `0`, but its action ran from the non-Git machine-local root:

`C:\Users\bgonn\AppData\Local\VesperFactorRuntime`

The executable pipeline files matched canonical hashes, yet the governance file differed and the runtime and `D:\vesper` produced different factor-score and sector-basket hashes for the same market session. The baskets differed by one constituent and score values.

**Durable rule:** scheduler success is not canonical-readiness evidence until action root, source identity, configuration/governance hash, output root, and receipt root are all proven to be the intended deployment.

### Missing actions are not a parking mechanism

Five enabled paper-submit tasks targeted the absent file:

`D:\vesper\scheduler\windows_paper_submit.bat`

The wrapper was absent from all local worktrees and Git refs. All tasks failed with result `1`, but restoring that filename would have reopened five mutation windows immediately.

**Durable rule:** order-capable tasks must be explicitly disabled/parked. A missing binary, missing credential, broken path, or failing wrapper is accidental inertness, not a safety control.

### Audit the full action closure

Historical logs showed the missing batch wrapper had invoked another absent/untracked helper, `scripts\submit_factor_candidate_paper_order.py`. Inspecting only the installed first-hop path would have missed the second orphan.

**Durable rule:** trace task → launcher → wrapper → script/module → side-effect endpoint, and verify existence, source control/release manifest, hash, root, and working directory at every hop.

### Recovery freshness must use market sessions

`pipeline_recovery.py` checked wall-clock filenames such as `factor_scores_<today>.json`. On a Monday morning the latest completed XNYS session was Friday, so healthy session-stamped outputs still looked missing and recovery could duplicate the pipeline.

**Durable rule:** recovery readiness must join to the authoritative completed trading session or a run manifest/receipt, never calendar “today” alone.

### Receipt freshness is not scheduler provenance

The natural Hermes EOD job failed at 17:00, but a later execution overwrote the same receipt with `PASS`. The watchdog accepted the fresh receipt as healthy because it did not join to Hermes `last_run_at`/`last_status`, a scheduler run ID, or run origin.

**Durable rule:** every scheduled receipt needs at least `scheduler`, `job_id`, `scheduled_for`, `run_id`, `run_origin`, `started_at`, `finished_at`, `source_commit`, and action/config hashes. Do not overwrite failed natural-run evidence with a manual run. Health must compare scheduler state and receipt identity, not freshness alone.

### One receipt path cannot represent repeated triggers

Five reconciliation tasks overwrote one daily receipt. The final file proved only the last run, not the five-run sequence.

**Durable rule:** name receipts by job ID + scheduled trigger/run ID, then maintain a separate atomic latest pointer if needed.

### Historical side effects require contract reconciliation

Local evidence showed a July 15 paper buy and subsequent fill for one symbol, while the final reconciliation monitor rejected that symbol as outside its approved envelope. No durable same-day intent record existed.

**Durable rule:** if submit and reconciliation contracts disagree around a recorded side effect, keep all mutation paths parked. Resolve local lifecycle evidence first; any broker readback is a separate explicit authority decision.

### High-level gates do not protect direct entry points

The high-level daily loop contained an affirmative candidate-intent gate and tests, but the low-level submitter could still be invoked directly and did not itself require the same operator-decision field before reaching its other gates.

**Durable rule:** enforce affirmative intent, envelope, idempotency, account identity, and fail-closed recovery inside every order-capable entry point. Or make lower-level mutators non-public and capability-gated; never rely only on one orchestrator.

### Process duplication requires topology, not name counts

Hermes uses launcher → venv shim → interpreter chains, so multiple PIDs can represent one logical session. A detached gateway legitimately has a dead launcher parent. Vesper Hermes workers should be joined by PID to read-only Kanban state (`worker_pid`, status, heartbeat, run ID) before calling them orphaned.

**Durable rule:** classify logical roots, descendants, parent liveness, command line, start time, window/process role, and scheduler/Kanban ownership. Do not kill based on repeated executable names.

## Windows audit checklist

For every matching task (match both task name/path and action/arguments):

1. Capture enabled/state, principal/logon type, trigger, next/last run, decimal+hex result, action, arguments, working directory, timeout, battery policy, catch-up policy, and multiple-instance policy.
2. Resolve and hash the complete action closure; verify tracked/release-manifested identity.
3. Check the Task Scheduler Operational log state before expecting event history.
4. Join result to wrapper start/end log and a run-specific receipt.
5. Compare outputs and receipts across every possible runtime root.
6. Inventory all overlapping scheduler planes and recovery/steward paths.
7. Inventory relevant processes by exact command line and map workers to their owning run/card.
8. For order/account/provider-capable paths, classify capability separately from observed behavior.
9. Separate routine engineering repairs from authority-changing or side-effect validation work.

## Safe validation ladder

1. Static action/root/hash closure.
2. Offline tests with broker/network methods replaced by fail-on-call fakes.
3. Install definitions while side-effect-capable tasks remain disabled.
4. Validate no-submit and data jobs on their next **natural** run.
5. Require scheduler event/log/receipt parity for at least two cycles.
6. Validate process singleton/ownership topology.
7. Treat any order canary or broker reconciliation as a separately approved phase, never routine scheduler verification.
