# Milestone B unattended-proof assurance audit — 2026-07-20

## Bound state

- Vesper canonical commit: `a18a967a95c7744345381d14d95cce92aeb9daf6`.
- Hermes source inspected: `a41d280f95c69f67380358b305b62345934ecaf3`, Hermes Agent v0.19.0.
- Audit was read-only. Focused tests ran from a `git archive` of the exact Vesper SHA with temp/cache paths outside the repository: `169 passed`.

## Durable findings

### Exactly-one is a fingerprinted authority claim

Do not count jobs only by display name, scheduler, or “report-only” wording. Define a canonical activation fingerprint over at least:

- contract hash and source/release hash;
- launcher/script hash;
- authority class;
- output/state root;
- schedule kind and finite repeat count.

Inventory Hermes cron in every profile, Windows Task Scheduler by both name and action, services, startup entries, wrappers, and live process/lease ownership. Distinguish configured, enabled, due, running, terminal, and successfully evidenced. Other legitimate report-only schedules may coexist, so “exactly one” must mean exactly one enabled launcher for the approved contract fingerprint—not one report-only job globally.

For a one-loop proof, prefer one future ISO-8601 Hermes `once` job with `--no-agent --repeat 1 --deliver local`, no prompt, no skills, and no agent supervisor. Read back the persisted definition before it can fire. The finite job should retire after one execution; after fire, require one durable execution record plus one validated controller receipt, not an enabled recurring job.

### Natural-trigger runbook after dispatcher quiescence

A review workflow may intentionally stop the Hermes gateway/automatic dispatcher to prevent a pending reviewer card from launching before its receipt hash is bound. Do not leave the scheduler quiesced when arming the later unattended proof.

1. Finish and validate the supervised release gate.
2. Restore the gateway/scheduler and verify it is active.
3. Create the one-shot with the bare script filename under `~/.hermes/scripts/`; record job ID, next-run time, source hash, wrapper hash, fingerprint, rollback command, and a complete pre-fire snapshot of the persisted definition.
4. Read back the job while it is still future-due and preserve that readback outside the mutable active-job list.
5. Let it fire naturally. Do not call the scheduler's manual `run` action.
6. Poll the exact job ID while the scheduler exposes it; join any terminal execution metadata with the immutable per-run controller receipt.
7. Confirm only one receipt/ledger event exists for the activation and that the finite job retired. Some scheduler surfaces remove a completed one-shot from the active list entirely, so disappearance alone proves neither success nor failure. When no terminal job row remains visible, use the preserved pre-fire definition plus source-bound receipt, scheduler-owned run identity/time, wrapper hash, and singleton ledger as the proof chain; never infer success merely from absence.

### Evidence packet for an auto-retiring one-shot

The controller artifact directory alone is insufficient scheduler evidence. Before fire, copy the exact persisted job row/definition into the approved external evidence packet and hash the active job store. After fire, preserve the matching scheduler execution row from the scheduler's durable execution store, bounded stdout/stderr or output record, scheduled-for/start/finish timestamps, exit/outcome, job ID, execution ID, wrapper hash, and the controller receipt/ledger identities. Also capture scheduler heartbeat/status before the due time and inventory every scheduler plane after retirement for the activation fingerprint. When using an active SQLite execution store, obtain an approved consistent snapshot rather than copying only the main database while unapplied WAL may exist. A packet containing only `candidate.json`, `evaluation.json`, `receipt.json`, and `loop.sqlite3` proves the application path, not natural scheduler provenance.

If the scheduler auto-removes the job before the auditor arrives and no preserved pre-fire definition or durable execution row exists, classify the natural-trigger claim `UNKNOWN`/`HOLD`; do not reconstruct the missing record from receipt timestamps or current job absence.

If the job becomes overdue with `last_run_at=null` because the scheduler was stopped, restart the scheduler and allow its ordinary overdue-job path to process the existing job. Do not recreate it, shift its schedule, or manually trigger it. Elapsed wall-clock time alone is not execution evidence.

### A no-agent scheduler is not automatically credential- or order-closed

A dummy-value probe of Hermes subprocess sanitization showed that `ALPACA_API_KEY`, `ALPACA_KEY_ID`, `ALPACA_SECRET_KEY`, and `ALPACA_BASE_URL` survived, while `OPENAI_API_KEY` was stripped. Never print or inspect real values; test name membership and dummy dictionaries only.

The scheduled launcher must build an explicit environment allowlist and remove all broker/account/order credentials and endpoints. It must also prevent `.env` reloading and avoid importing broker/order-capable modules. If a real report-only worker requires model inference, keep provider transport in the existing Hermes gateway while denying the worker terminal/browser/network/order tool surfaces. Permit only fixed `shell=False` CLI argument arrays needed for the governed Kanban bridge.

A `--no-submit` flag and the legacy `NoSubmitGuard` are not capability denial. The guard intentionally accepts `execution_allowed=true` under bounded-paper interpretation, and the daily loop contains an order-submit branch when the flag is absent. Prove no-order closure through import/argv/tool/network/credential boundaries and adversarial tests.

### Timestamp stale-breaking plus unconditional unlink is ABA-unsafe

The legacy `app/services/run_lock.py` atomically creates a file, but stale reclaim ignores live PID/process identity and release unconditionally unlinks the pathname. The audit reproduced this sequence in an external temp directory:

1. owner A acquired;
2. its timestamp was aged while A remained live;
3. owner B broke the file and acquired;
4. A released and deleted B’s lock;
5. owner C acquired while B still believed it held the lock.

For exact-once or long-running jobs, use a process-lifetime Windows named mutex/kernel file lock, or a transactional lease with owner nonce, PID plus process-creation identity, heartbeat, and compare-and-delete release. Never reclaim solely by wall-clock age; prove owner death first. Pair process exclusion with a database uniqueness/idempotency constraint because scheduler duplication and application duplication are separate failure planes.

### Receipt and rollback posture

A mutable “latest receipt” is not proof. Publish immutable per-run receipts atomically and bind schedule job/execution IDs, activation ID, contract/source/release hashes, candidate/evaluator bytes and identities, limits, lifecycle event chain, denied authority, and terminal/recovery state. A local hash chain detects accidental edits and partial writes but not coherent rollback by an actor who can replace every local file; state that boundary honestly.

Rollback must be scoped:

1. pause the exact job ID and read back disabled state;
2. do not kill the shared Hermes gateway;
3. request bounded controller stop or let the owned Job Object deadline terminate its child;
4. classify interrupted work `HELD`, `FAILED`, or `UNKNOWN`, never success;
5. remove only the exact job ID after terminal reconciliation;
6. verify absence of the activation fingerprint across every scheduler plane while preserving receipts and execution history;
7. never restore an old whole `jobs.json`, which can clobber concurrent jobs.

### VOT lifecycle and singleton visibility

Read-only VOT should consume a bounded atomic projection/receipt, not mutate controller state or infer health from a missing job. Keep schedule state, run state, evidence freshness, and evaluator decision separate. Render malformed, missing, stale, future, contradictory, or hash-mismatched evidence as `UNKNOWN`/`UNAVAILABLE`/`STALE`/`BLOCKED`; never as idle or complete. Display literal `execution_authority=false`, `order_authority=false`, and `safe_for_planning=false`.

Acquire a Windows named mutex before `tk.Tk()` or any reader thread. A duplicate launch exits deterministically without opening a window. Test two-process contention, hard-kill/restart, PID reuse, old-owner release versus successor ownership, close during in-flight reads, and late-result rejection.

## Activation stop conditions

Do not arm the unattended proof if any of the following is true:

- supervised canary receipt is absent, invalid, or not bound to the release;
- another agent, interval, task, service, or process can launch the same contract;
- scheduler readback is not exactly one enabled fingerprint match;
- implementation/release hashes or contract/input hashes drift;
- broker credentials survive the child allowlist, order modules are reachable, or worker tool denial is unproven;
- singleton ABA/crash/restart/duplicate-delivery tests fail;
- prior lifecycle state is nonterminal or unknown;
- VOT cannot show the lifecycle truth or source conflict;
- limits, timeout, receipt publication, or independent review fail.

A failed/unknown proof is not automatically retried or rescheduled. It requires a new explicit operator decision.