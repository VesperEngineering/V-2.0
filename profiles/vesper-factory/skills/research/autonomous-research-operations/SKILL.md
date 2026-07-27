---
name: autonomous-research-operations
description: Run long-lived, evidence-first technical research programs with visible HUDs, fixed experiment queues, and fail-closed gates.
version: 1.0.0
---

# Autonomous Research Operations

Use for user-directed research programs that run while the user works elsewhere, especially GPU/ML experiments.

## Operating principles

1. **Separate compute from scientific autonomy.** Run predeclared GPU replications back-to-back; do not let a scheduler invent or retune hypotheses.
2. **Close claims, not projects.** A failed simplicity baseline closes that exact input/objective branch. Pivot only by changing information, relational structure, or a separately stated question.
3. **Every nonlinear model gets an equal-information simple baseline** (PCA, linear model, or explicit observable baseline).
4. **Document before advancing.** Every run writes a machine-readable artifact and a concise verdict: VALIDATED, PARTIAL, INVALIDATED, or BLOCKED.
5. **Fail closed.** Missing artifact, failed process, leaked data provenance, or ambiguous dependency blocks the queue rather than skipping ahead.

## Queue design

Maintain a JSON manifest with per-item: ID, title, status, dependencies, frozen script path, required artifact, primary metric, and stop rule. The worker leases only one dependency-satisfied item, writes a receipt, and never creates items.

Statuses: `PENDING`, `RUNNING`, `COMPLETE`, `BLOCKED`, `CLOSED`.

Use a continuous worker for contiguous approved batches. Use cron only as a watchdog; never start a second worker.

## User-facing HUD

Prefer a stable, plain terminal display over decorative dashboards. Show:
- current script, phase, elapsed time, and real GPU telemetry;
- a small architecture line or grid;
- evidence bars with actual numbers;
- completed results and queue rows (including stop rules);
- explicit distinction between validated representation facts and unvalidated economic/trading claims.

Avoid terminal clear loops that blink. Use a real live renderer or a fixed redraw method. Never display invented progress. Emit explicit post-epoch phases: encoding, aggregation, evaluation, statistics, artifact writing, done.

## ML interpretation pitfalls

- A stable latent **subspace** does not imply a stable coordinate. Unconstrained neural embeddings can rotate or flip sign across seeds. Test subspace/probe stability or alignment, not claims like “dimension 8 means volatility.”
- A high correlation with severely negative R² means ordering/descriptive information, not a calibrated forecast.
- Parameter sweeps must be preregistered and fully reported; do not pick a winner using an examined holdout.
- A simple baseline winning is a successful result. Stop the exact complexity claim and preserve the receipt.

## Three eras of autonomous operations (lesson learned)

When building an autonomous operations system, avoid these two failed patterns:

### Era 1: Bare scripts with no safety (failed)

Standalone cron jobs that run scripts directly. No run locks (jobs can overlap). No safety guards (nothing prevents accidental mutations). No receipts (no proof a job ran). No alerting (failures are silent). No retry logic. This approach was abandoned within weeks.

### Era 2: LLM-driven agent cron jobs (failed)

Agent-driven cron jobs with skills, models, and workdir assignment. Consumed tokens on every run. No run locks. No safety guards. Agent output went to session logs, not durable artifacts. No alerting. All jobs were paused within 2 weeks — the approach was abandoned because it was expensive and unaccountable.

### Era 3: No-agent scripts with safety harness (working)

No-agent cron scripts wrapped in a uniform safety harness: envelope → run lock → safety guard → receipt. Zero token cost. Every job produces durable JSON receipts. Fail-closed on safety violations. Alert dispatching to messaging platforms. Monthly review is advisory only — human approves all promotions.

**The lesson:** Autonomous execution works when the human owns the queue, the protocol, and the authority boundary. The agent/cron owns execution within those bounds. Every run is receipt-backed. Every failure is visible. Every promotion is human-approved. Trying to prompt AI agents into working alone without guidance is the wrong frame — what works is governed autonomy with human oversight at the boundaries.

## Research handoff checklist

Before leaving a program unattended:
1. Ensure work is isolated from production systems.
2. Freeze queue entries and dependencies.
3. Verify worker/HUD launch and visible post-epoch messages.
4. Require JSON artifact + README/log verdict before completion.
5. On return, report the evidence ledger, not just activity or GPU time.

See `references/user-hud-and-autonomy.md` for user-facing presentation preferences.
