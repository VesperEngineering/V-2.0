---
name: evidence-observability-release
description: Build and release report-only evidence/observability systems without accidentally creating authority or presenting stale evidence as healthy.
---

# Evidence & Observability Release

## Use when

Use for a report-only observer, evidence ledger, local status receipt, operator dashboard/System Spine projection, worker-lease visibility, or any service described as read-only, non-dispatching, or fail-closed.

## Core rule

Labels and booleans such as `report_only=True` or `execution_authority=False` are necessary but never proof. Prove the reachable code paths, source lineage, freshness, durable-write semantics, and UI consumption.

## Implementation sequence

1. **Define authority denial first.** Make forbidden imports/calls explicit: dispatch/runtime, provider/network spend, Kanban mutation, scheduler, risk, promotion, deployment, broker/order, and secret access. Keep the observer separate from any existing execution daemon, even if that daemon is nominally “report-only.”
2. **TDD one vertical slice at a time.** Write a test, run it red, then implement the smallest green path. Test both successful evidence and failed/malformed evidence before adding UI.
3. **Bind every observation to actual evidence.** Read only allowlisted completed artifacts. Verify the artifact’s digest and exact receipt binding; do not trust caller-supplied provenance strings, event IDs, or hashes.
4. **Make freshness explicit.** A displayed `FRESH` state requires valid timestamp, `freshness=FRESH`, bounded age, no future time, and an accepted binding. Inconsistent state/freshness is stale or unavailable. Reconcile only the newest valid observation per source so historical stale entries do not permanently poison later valid evidence.
5. **Honor ledger semantics.** If the contract says append-only, use append-only durability rather than full-file replacement, compaction, or automatic repair. Replay must reject malformed JSON, hash-chain discontinuity, out-of-order rows, oversize artifacts, and truncated/partial records fail-closed. Define and test writer concurrency behavior.
6. **Fail closed on publication.** If writing a required receipt/status artifact fails, return `UNAVAILABLE`/failure; never return the computed healthy posture merely because in-memory reconciliation succeeded.
7. **Prove the consumer path.** Attach the result to the dashboard snapshot/read model and create a distinct read-only UI domain. Missing, malformed, stale, or tampered evidence must visibly render unavailable/stale. Preserve UI selection, scroll, and no-flicker behavior.
8. **Release review.** Stage only scoped files; run focused tests, full relevant UI tests, lint, compile, diff check, and an actual UI smoke launch. Then obtain an independent review that traces authority reachability and evidence lineage. Any defect blocks integration; repair test-first and obtain a fresh review.

## Mandatory test matrix

- forbidden-import/reachability scan for every denied capability;
- allowlisted artifact, digest, and exact receipt-binding mismatch;
- missing, malformed, oversized, tampered, truncated, and out-of-order ledger data;
- duplicate/idempotent evidence and concurrent writer policy;
- future, stale, malformed, and inconsistent `state`/`freshness` timestamps;
- status/publication I/O failure;
- recovery from older stale evidence to newer valid evidence;
- dashboard/UI projection of ready, stale, and unavailable states without authority changes.

## Pitfalls

- Do not extend an existing daemon that owns task selection, leases, runtime execution, or provider transports just because it carries a report-only label.
- Atomic replacement is not append-only. It can be appropriate for a summary receipt, but not for a ledger whose contract forbids rewrite/compaction.
- Do not swallow receipt-write exceptions. A healthy return with no published receipt is a false health signal.
- Do not treat nonempty strings as provenance validation.
- A green focused suite does not replace independent review of semantic authority and evidence boundaries.
