# Holistic Quant-Firm Audit Reference

Use this reference when a Vesper review is broad, co-founder-level, or asks what should be done next.

## Priority order

1. Contain every mutation-capable path that bypasses the shared execution boundary. A paper endpoint is not authorization. Retire legacy rebalance/trade helpers or block them before credential/client construction.
2. Verify evidence truth before strategy quality: distinguish producer execution status, data integrity, research acceptance, promotion authority, and execution authority.
3. Audit research validity: explicit ticker/date joins, point-in-time membership and sectors, listing/delisting coverage, release-vintage timing, walk-forward state reset, chronological execution, realized turnover, spread/impact, and geometric performance metrics.
4. Audit model identity: registry path/hash, scoring ensemble, schema/code identity, current picks, model runs, outcomes, snapshots, and rollback manifests must agree.
5. Audit operations: scheduler authority, real Task Scheduler Last Result, process-tree supervision, receipt freshness/schema/provenance, operator unknown-state behavior, and board/status synchronization.

## Canonical scan procedure

- Capture `git status --short --branch` and `git diff --stat` before edits.
- Treat the canonical root as production evidence. Exclude `.git`, `.venv`, `.worktrees`, `artifacts/`, `data/`, caches, browser scratch, and generated outputs from broad scans.
- Search production paths (`app`, `deploy`, `scripts`, `scheduler`) and tests/docs separately. Historical worktrees are an operational drift finding, not canonical code evidence.
- Collect tests before running broad suites. Use an external pytest basetemp when the repository artifact path or OS temp path is permission-contaminated.
- Dispatch bounded independent audits by research, execution, and governance; require exact paths, severity, reproduction, minimal repair, and boundary impact.

## Finding record

Each issue should contain:

- Stable `VQ-YYYYMMDD-NNN` ID.
- Severity and status (`Reproduced`, `Contained`, `Partially remediated`, `Verified closed`).
- Exact component/path and evidence.
- Operational/economic impact.
- Minimal safe repair or quarantine action.
- Exact focused verification and any known full-suite limitations.
- Explicit statement of whether broker/provider/model/scheduler/authority side effects occurred.

## Research red flags

- `shift(-horizon)` labels stored as lists or independently dropped arrays: preserve and join by `(ticker, timestamp)`.
- Fixed present-day benchmark lists in historical tests: require dated security-master membership and delisting coverage.
- Observation date used as macro availability date: require release timestamp and vintage.
- “Best horizon/features” selected in the same evaluation output: freeze selection before the evaluation window.
- Gross returns without realized weights, turnover, entry/exit price, spread, impact, or liquidity limits: do not call the result investable.
- Arithmetic mean annualization for equity growth: use geometric CAGR; keep Sharpe/Sortino conventions explicit.
- A receipt with `status=PASS` but nested acceptance/promotion failure: separate execution, integrity, acceptance, and authority fields.

## Execution containment patterns

- On ambiguous POST outcomes, use deterministic client IDs, reconcile by exact ID, and keep unresolved state as `ORDER_STATUS_UNKNOWN`; never retry by issuing a second POST.
- Require exact client/order identity and terminal fill status before producing fill evidence. Requested quantity is not filled quantity.
- Retire unguarded lower-level mutation primitives rather than relying on callers to remember a guard.
- Block private exchange execution before credential loading/client construction until an exchange-specific approval contract exists.
- Treat missing/unknown/stale kill-switch or execution evidence as blocked/unknown, never clear.

## Stop handling

If the user says `/stop`, “stop,” or equivalent, cancel the active todo state and do not continue tools, edits, tests, commits, pushes, or delegated work. A late async completion is informational only; acknowledge it without resuming.
