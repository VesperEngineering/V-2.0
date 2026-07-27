---
name: authority-closed-observers
description: Build and review local evidence observers, status artifacts, and dashboards that remain report-only and fail closed.
---

# Authority-Closed Observers

## Use when

Use for resident/local observers, evidence ledgers, monitoring status artifacts, worker-lease visibility, or operator UI projections where the process must **observe only** and must not acquire execution authority.

## Contract first

1. Write an explicit denylist before implementation: no dispatch/leases, Kanban mutation, provider calls/spend, scheduler mutation, risk/promotion/deployment, broker/order access, or secrets.
2. Keep the observer separate from any legacy executable runtime, even if that runtime is labelled report-only.
3. Do not expose task, worker, provider, model, dispatch, or scheduler controls in the runner CLI.
4. Make all authority fields literal closed values (`execution_authority=false`, `safe_for_planning=false`, `planning_safety=unavailable`); never compute an aggregate permission score.

## Evidence ingestion and durability

1. Accept only an allowlisted completed source artifact.
2. Bind every observation to the exact source bytes (for example, `sha256:<digest>`); never trust caller-supplied provenance/binding strings by themselves.
3. Persist only bounded, allowlisted summaries—never raw provider output, secrets, or arbitrary payloads.
4. Use an append-only integrity chain. Validate chain continuity, schema, ordering, byte/entry bounds, and duplicate semantics on replay.
5. Serialize concurrent writers with an interprocess lock or an equivalent append protocol. Re-read/revalidate the head while holding the lock. Never compact, overwrite, or silently repair prior evidence in the resident path.
6. When one receipt may have several lifecycle rows, define an immutable-core projection (for example receipt, contract, candidate, decision, and literal authority fields) and require that projection to be identical across states. Keying uniqueness only by `(receipt_hash, lifecycle_state)` prevents same-state edits but otherwise permits cross-state mutation.
7. Treat replay as full-history validation, not an early-return shortcut. Reject duplicate state rows, out-of-order states, and an exact row followed by a conflicting duplicate before returning replay-suppressed. For a terminal transition, exercise the mutated terminal payload *before* inserting the valid terminal row; testing mutation afterward only proves the same-state guard.
8. For a local JSONL chain that must detect isolated valid suffix deletion, publish a second bounded tail anchor with the expected entry count and final entry hash. Replay must require an exact anchor whenever the ledger exists. Atomically replace each file under the same lock; an interruption between the two replacements must leave a mismatch that fails closed, never trigger repair. State precisely that a local actor who can coherently roll back/delete both files is outside this protection.
9. A write, append, replay, or final status-publication failure must produce an explicit unavailable posture; do not return a healthy result when the corresponding artifact was not published.

For concrete adversarial probes for multi-state ledgers, see `references/lifecycle-ledger-idempotency.md`.

## Freshness and UI projection

1. Distinguish **evidence observation time** from **status publication time**. A later process cycle must not make old evidence look newly observed.
2. Parse timezone-aware timestamps. Reject malformed or future timestamps.
3. Apply source-specific TTLs. Expired `FRESH` evidence renders `STALE`; missing or malformed evidence renders `UNAVAILABLE`/`MALFORMED`.
4. Reconcile only the newest valid observation per named source or receipt identity; historical stale entries must not permanently poison a newer valid state.
5. When a writer retains an existing status instead of publishing a candidate, validate the existing artifact against the reader's **entire** bounded schema first: exact keys, size bound, literal authority fields, field types/ranges, and a parseable nonfuture evidence timestamp. A newer malformed, oversized, future-dated, or `UNAVAILABLE` write-time status must never suppress a valid `FRESH`/`STALE` receipt-backed recovery. Preserve a genuinely newer fully valid evidence posture.
6. Keep dashboard consumption one-way: completed artifact → bounded reader → immutable snapshot → read-only projection. Missing/tampered artifacts must be visibly stale/unavailable without changing selection, scroll, or other UI state.

## Candidate refreeze when the Git index is stale

A report-only candidate may have correct working-tree repairs while its staged version is older. Treat this as an integrity boundary, not a mechanical `git add -A` operation.

1. Inspect both `git diff` and `git diff --cached`; enumerate every `AM` path and review each working-tree repair for scope and denied authority.
2. Preserve only the intended source, runner, reader/projection, and test paths. Stage them with explicit path arguments; never stage temp test trees, lock files, emitted receipts, ledgers, artifacts, caches, or unrelated edits.
3. Before calling the candidate frozen, require all of: no tracked working-tree/index mismatch for staged paths, `git diff --cached --check`, an empty staged/untracked intersection, and status output showing no `AM` entries.
4. Run focused tests and broader read-only UI-projection tests **after** final staging, with a dedicated basetemp outside the worktree. Keep the candidate uncommitted and do not equate passing tests with release approval.
5. For any uncommitted candidate another process or agent may still edit, record `HEAD`, changed paths, and `git hash-object` values for every reviewed file before analysis. Recheck them immediately before the verdict. If any changed, discard earlier line references and test evidence and restart from the new diff; tests importing the newer file do not validate source read from the older blob.

See `references/candidate-refreeze-checklist.md` for a compact command-and-evidence checklist.

## Test-first release gates

Write each regression test before the fix and observe RED. At minimum cover:

- forged/mismatched receipt binding;
- oversized allowlisted source receipts rejected by a named byte bound before JSON parsing (and rechecked after read to close a size-change race);
- hostile JSON scalar shapes (lists, objects, booleans) at every schema membership/comparison boundary, proving total unavailable behavior rather than `TypeError`;
- malformed, oversized, truncated, hash-tampered, and ordering-invalid ledger data;
- JSONL final-line and whole-ledger truncation against a retained tail anchor, plus missing, malformed, tampered, and interrupted anchor publication;
- duplicate and concurrent writer/lost-update behavior;
- writer and status-publication failure;
- malformed, future, offset-timezone, and expired timestamps;
- evidence-time versus publication-time preservation;
- absent/tampered artifacts through the dashboard projection;
- AST/runtime boundary scans proving no forbidden authority path is reachable.

Before integration, run focused and full tests with isolated temporary directories, lint/compile/diff checks, an actual operator-UI smoke test if applicable, and a fresh independent authority review. Any reviewer defect blocks integration until repaired and freshly reviewed.

## Reference

See `references/evidence-ledger-review-cases.md` for a compact review matrix and artifact invariants. See `references/local-ledger-tail-anchor.md` for the exact local checkpoint protocol and its security boundary. See `references/status-publication-monotonicity.md` for reader/publisher parity and status-replacement regressions.
