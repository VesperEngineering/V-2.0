# CPU Cross-Sectional Ranking Milestone Lifecycle

Use this reference for a bounded research milestone that must progress from a simple factor baseline through classical CPU models while preserving an untouched holdout and a restart-safe experiment trail.

## Build order

1. **Bind the control plane first.** Record the canonical repository, isolated worktree/branch, objective card, authority class, and one active owner. Do not create the unattended schedule yet.
2. **Freeze the smallest complete scientific contract.** Bind membership/data hashes, feature availability, label horizon, rebalance cadence, entry/hold buffers, costs, walk-forward windows, holdout dates, seeds, CPU/thread limits, metrics, and decision thresholds.
3. **Materialize a content-addressed point-in-time panel.** Prefer adjusted local data. Bind a derived dataset hash and manifest rather than trusting mutable source paths. Record coverage by date and source lineage.
4. **Prove one thin vertical slice before expanding infrastructure.** Tests should cover strict protocol loading, dataset replay/tamper checks, past-only features, exact horizon labels, buffered selection, costs, and deterministic evaluation. Then execute the simple baseline end to end and persist its candidate, evaluation, decision, receipt, ledger row, and board update.
5. **Only after the baseline slice is verified, add trained candidates.** Run one bounded Ridge candidate, then one fixed XGBoost configuration. No sweep or result-conditioned retuning is allowed unless a new contract is frozen before inspecting its evaluation.
6. **Install recurrence only after a supervised experiment passes.** The recurring worker must check the board, acquire one singleton lease, reconcile interrupted state, and execute at most one predeclared candidate. A natural no-op/one-run probe must be read back before claiming scheduler proof.
7. **Open the final holdout once.** Only a pre-holdout candidate that passes every frozen gate may be evaluated on the holdout. Persist the holdout-open event and never reuse it for tuning.

## Point-in-time panel safeguards

- Membership must be evaluated as of each signal date, not from a current constituent list.
- Report both universe coverage and missing/delisted-name handling. A membership file plus current-only prices is not a complete point-in-time panel.
- Prefer split-adjusted prices. A raw-price fallback may infer common split ratios only under a declared recipe; record every inferred event, quarantine unresolved jumps, and fail closed when coverage or continuity falls below the contract.
- Use exact five-session target dates and ensure train labels end inside the training window. Test labels must end inside their test window.
- A derived panel replay is valid only when the protocol hash, membership hash, source manifest, and physical dataset hash all agree.

## Evidence per experiment

Every admitted experiment must leave:

- immutable candidate specification;
- deterministic evaluation with per-window and aggregate metrics;
- `KEEP`, `REJECT`, or `HOLD` decision with gate-level reasons;
- self-verifying receipt bound to source, protocol, data, model/runtime versions, and exact artifact bytes;
- append-only experiment-ledger entry plus an independently anchored count/final hash;
- champion update only for an explicit `KEEP` and never as automatic production promotion;
- concise research summary and supported Kanban update.

## Interaction-budget discipline

A finite agent/tool budget is part of the run budget. Do not spend most of it on broad discovery, framework polish, or parallel infrastructure before one complete experiment exists. At roughly half the available budget, stop expanding scope and drive the smallest supervised slice through real execution and readback.

Before starting any long background job, persist its process/session ID, exact command, expected outputs, timeout, and verification command in a resumable checkpoint. A job that was merely launched but whose exit and artifacts were not read back is `HOLD_AUDIT_INCOMPLETE`, not success.

## Completion boundary

A green unit-test subset is not milestone completion. Completion requires real-data artifact readback, deterministic replay, authority-boundary verification, a supervised experiment, recurrence proof when requested, and—only after pre-holdout qualification—the one-time untouched-holdout result.
