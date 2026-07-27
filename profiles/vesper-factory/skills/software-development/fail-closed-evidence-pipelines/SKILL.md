---
name: fail-closed-evidence-pipelines
description: Build and review report-only evidence collectors, integrity-linked ledgers, and read-only operator projections without creating authority paths.
---

# Fail-Closed Evidence Pipelines

## Use when

Use for local observers, evidence ledgers, status receipts, world-state readers, and dashboard projections that must remain report-only—especially where stale/malformed evidence must be visible rather than healthy-looking.

## Workflow

1. **Map authority first.** List prohibited imports and paths: dispatch/runtime, providers, Kanban mutation, scheduling, promotion, risk, deployment, broker/order, and secrets. Add AST/import boundary tests before implementation.
2. **Define one completed-evidence contract.** Allowlist source path, schema, timestamp, provenance, and exact receipt binding. Never accept a caller-supplied provenance/binding string as trustworthy evidence.
3. **Validate source before persistence.** Hash the exact completed allowlisted receipt and require the event binding to equal that digest. Reject missing, altered, oversized, malformed, future-dated, or schema-invalid input as explicit unavailable/malformed posture.
4. **Write append-only under one process-safe critical section.** Do not compact, repair, or replace the evidence ledger in the resident process. Bound input/replay size; integrity-link each entry; hold an OS-released interprocess lock across read → validate → replay/conflict check → append → flush/fsync; fail closed on partial, duplicate, tampered, unordered, or cross-state-mutated entries. Validate physical framing before parsing. Choose and test one explicit missing-terminal-newline policy: either reject the append byte-for-byte unchanged, or—if a final unterminated JSON record is valid for the format—write exactly one separator before the next canonical row while still holding the lock. Never concatenate records. Reject embedded blank records and duplicate JSON keys. For lifecycle ledgers, key physical events by `(receipt_hash, state)` while requiring every non-state field to remain invariant and every transition to be monotonic.
5. **Prove recovery through the real entry point.** A successful replay after a complete receipt proves only terminal replay. Persist the first immutable orchestration contract before lifecycle transitions and reuse those exact bytes across retry; rebuilding dynamic `issued_at`/`expires_at` values changes the contract hash. Inject failures after each durable boundary, then call the same scheduler/supervisor entry point with the same identity. It must resume the legal suffix or emit a receipt-backed bounded `HELD`; component-level controller recovery does not excuse an orchestrator that unconditionally restarts early transitions. A receipt-first replay path must also validate its supporting contract and durable event chain, then idempotently finish any missing review packet or ledger suffix before returning success. When recovery may occur after contract expiry, keep first-admission and reconciliation validation explicit: reconciliation may skip only the expiry comparison, and only a fully validated durable lifecycle snapshot with the exact canonical contract hash may activate it. A persisted contract/receipt alone never grants this bypass. See `references/delayed-expiry-reconciliation-review.md` for the external exact-snapshot recipe and the missing/corrupt/wrong-hash/future-issued/cross-artifact adversarial matrix.
6. **Reconcile current posture carefully.** Select only the latest valid evidence per named source/identity. `state=FRESH` is insufficient: require fresh freshness, parseable nonfuture timestamp, and age inside the defined freshness budget. Old stale events must not permanently prevent recovery once newer valid evidence exists.
7. **Publish atomically and propagate failure.** A successful collection must return `UNAVAILABLE` if its required report/status publication fails. Never swallow status-write errors and return `FRESH`.
8. **Expose read-only in the desk.** Attach only strict bounded status/ledger readers to the terminal snapshot and a separate System/History domain. Missing/malformed evidence must be visibly `UNAVAILABLE`/`STALE`; no control callbacks, authority scores, or health inference.
9. **Run independent authority review before integration.** Treat lifecycle, provenance, stale-state, and reachability defects as release blockers. For review-gated canaries, bind the pending receipt to a pre-created distinct reviewer task, prevent automatic pre-hash dispatch, and require one reviewer run; a hold-plus-retry task is historical evidence, not an admissible single-run approval.
10. **Order final audits by release-blocking value.** Immediately after freezing source/evidence and creating the external exact snapshot, run the focused suite, critical lint, and the smallest public-entry-point adversarial probes that can independently force `HOLD`—especially raw-byte-only candidate/evaluation replay mutations, delayed crash recovery, wrong-hash lifecycle activation, and duplicate/concurrent reconciliation. Capture opening schedule/profile manifests before any long evidence reconstruction, then audit the canary/unattended/VOT chains, and reserve enough calls for closing manifests and drift comparison. Make every phase restartable from scratch artifacts. If an execution ceiling interrupts any required gate, report an incomplete-audit `HOLD`; richly validated happy-path evidence cannot substitute for an unexecuted adversarial gate.

## Test-first coverage

Write and observe RED tests for:

- forged or mismatched receipt hash/binding;
- tampered/hash-discontinuous/malformed/oversized ledger;
- future, stale, and `FRESH`+`STALE` contradictory event fields;
- recovery when a newer valid observation supersedes older stale history;
- append/write and required status-publication failures;
- exact replay only after full-ledger validation; replay masking a later mutated row; unrelated append into corrupt history; closed-first/reverse order; JSON scalar-type mutation such as `false` versus `0`; malformed/duplicate lifecycle rows; missing-terminal-newline under the chosen explicit reject-or-separator policy; embedded blank records; duplicate JSON keys; and both 12-thread plus real 8-process append races;
- injected failure after every multi-artifact finalization boundary followed by retry through the real scheduler/supervisor entry point—not only direct component-method recovery—including delayed retry with a changed wall clock, a crash after evaluation, and a crash after receipt but before packet/ledger publication; require exact persisted-contract reuse, complete supporting-evidence validation, suffix repair without duplicate events, convergence, or a receipt-backed bounded `HELD`;
- explicit canonical text-hash profile drift, including LF/CRLF equivalence;
- forbidden-import/reachability checks; and
- VOT missing/stale rendering while preserving selection and scroll state.

### Fixture dependency rule

When tightening an upstream validator, refresh downstream test fixtures so they satisfy the new prerequisite before forcing the downstream fault. Otherwise a test may pass because the earlier validation failed, not because its intended lifecycle behavior is correct.

## Pitfalls

- An atomic full-file replacement is not an append-only ledger.
- A first-match replay return is not idempotency if later ledger rows have not been validated.
- A valid receipt alone is not a complete replay boundary: verify the persisted contract and durable event chain, and finish any missing packet/ledger suffix before reporting replay success.
- Rebuilding a contract with fresh timestamps on retry silently changes lifecycle identity; persist the first contract and reuse its exact canonical bytes.
- A restart test with a literal absolute issue/expiry timestamp eventually becomes time-dependent and can fail only because review happened later. Inject one timezone-aware clock, advance it relatively, and test expiry boundaries separately.
- Python object equality is not a typed JSON identity comparison (`False == 0`).
- A task branch name alone does not prove source binding; verify the materialized worktree `HEAD` and frozen inputs before dispatch.
- A blocked card is not necessarily non-runnable under an active gateway; attach the exact pending receipt/comment before releasing a real admission hold. Restoring an assignable profile may itself promote the card, so finish every source/worktree/run-count check first.
- A nonzero coordinator exit does not imply no durable effects: task creation, lifecycle finalization, or receipt comments may have committed before result formatting failed. Reconcile by immutable IDs before any retry.
- A reviewer summary is not sufficient evidence. Inspect persisted telemetry and require an exact final zero-exit gate; an earlier failed probe is acceptable only when an equivalent unweakened retry passes and no forbidden persistent write occurred.
- If a later exact-source review holds a source used by an unattended run, preserve the run as `HELD_SUPERSEDED`, remove stale positive projections, and rerun from the corrected source.
- Literal booleans such as `execution_authority=false` do not establish provenance by themselves.
- Do not reuse an existing “report-only” daemon merely because its label sounds safe; inspect whether it owns leases, calls runtimes/providers, or performs selection.
- A dashboard reader must not make a source look fresh merely because a status artifact exists.

See `references/v3-5-observer-review.md` for a compact observer checklist, `references/lifecycle-ledger-closure.md` for monotonic review-ledger, interprocess-locking, partial-finalization recovery, and canonical text-hash patterns, `references/entrypoint-restart-jsonl-framing.md` for public-entry-point crash probes and explicit JSONL framing policies, and `references/exact-source-worker-reviewer-admission.md` for race-free Hermes task/worktree/reviewer admission.
