# Monotonic Lifecycle Ledgers and Restartable Closure

Use when one immutable receipt advances through review states and finalization spans SQLite plus JSON/JSONL artifacts.

## Ledger invariants

- A receipt may have multiple physical lifecycle entries. Key each entry by `(receipt_hash, review_state)`, not `receipt_hash` alone.
- Parse and validate the **entire bounded ledger before any idempotent replay return**. Group every row by receipt hash and reject corruption in any group, including groups unrelated to the incoming append; otherwise an exact early row can mask a later mutated close.
- Allow only explicit states and complete physical histories; for example, exactly `[PENDING_INDEPENDENT_REVIEW]` or `[PENDING_INDEPENDENT_REVIEW, INDEPENDENTLY_APPROVED_CLOSED]`. Reject closed-first, pending-after-closed, repeated states, and extra transitions.
- For one receipt hash, all fields except `review_state` must remain identical. Compare canonical JSON bytes rather than Python object equality: Python considers `False == 0` and `1 == 1.0`, while receipt identity must preserve JSON scalar types.
- Reject unknown states, malformed rows, blank/extra records, and duplicate `(receipt_hash, review_state)` rows even when their payloads are identical.
- Only after the whole ledger is valid may an exact replay return “already present” without a write. A changed payload for an existing identity is a conflict.

## Concurrency

Layer two locks around the complete read → full-history validation → duplicate/conflict check → append → flush/fsync sequence:

1. a process-local lock keyed by the resolved ledger path; then
2. an OS-owned interprocess sidecar/file lock.

The local layer matters on Windows: concurrent threads in one process can make `msvcrt.locking` raise `EDEADLK` (`Resource deadlock avoided`) even though the same byte-range lock works across processes. A persistent sidecar file is fine when the kernel lock is released on process death; a crash-sticky existence sentinel is not.

Prove the claim with both threads and real processes:

1. Launch at least 12 threads and 8 processes against absent ledgers with identical payloads.
2. Require exactly one successful append and N-1 exact-replay results in each probe.
3. Require exactly one physical row.
4. Preseed duplicate identities and require fail-closed rejection.
5. Race distinct/conflicting payloads and require one winner plus explicit conflicts—never silent lost updates.

## Single-run independent-review boundary

When a pending receipt must bind a distinct real reviewer task before dispatch, treat reviewer orchestration as part of the evidence protocol:

1. First bind the exact source: pre-create the review branch at the frozen SHA and materialize or verify the reviewer worktree. Assert exact `HEAD`, required frozen inputs, project/workspace identity, and tracked-clean status before dispatch.
2. Establish a **non-runnable admission hold** before task creation. A Kanban label such as `blocked` and even a briefly unsatisfied dependency can be promoted or claimed within seconds by an active gateway. Prefer a supported dispatcher pause, profile cap, or admission mechanism. If a temporary profile hold is the only bounded option, prove no active task uses that profile, preserve it byte-for-byte, and restore it immediately on every success/failure path.
3. Create the reviewer task/worktree identity with zero runs.
4. Build the immutable pending receipt and review packet with that exact reviewer task ID.
5. Publish/comment the exact receipt hash **before** making the reviewer runnable. Task comments are commonly snapshotted when the worker starts; a comment added after claim may appear on the card yet be absent from the worker's initial context.
6. Configure the reviewer with exact test and lint commands scoped to candidate files. A repository-wide lint invocation can surface unrelated historical debt and create a false hold.
7. Release the admission hold and dispatch once. Tell the reviewer that `PENDING_INDEPENDENT_REVIEW`, `verdict=PENDING`, and `approval_granted=false` are the expected object under review—not a missing prerequisite.
8. After terminal state, require exactly one reviewer run, a tracked-clean exact-source worktree, exact source/candidate/receipt hashes, and one terminal verdict claim.
9. If an early hold is automatically retried or the task starts before its packet/comment is complete, preserve all runs as historical evidence but do not use that task as the admissible reviewer. Create a fresh reviewer task and rebuild the still-pending immutable receipt around the new reviewer ID; never mutate the old receipt in place.
10. Restore any temporarily narrowed reviewer profile/tool surface after terminal state, including hold/failure paths, and verify byte-for-byte restoration.

Only after this one-run approval should the closure finalizer bind reviewer run/session identity and advance to `CLOSED`. Invoke closure again and require exact replay with no additional lifecycle event or ledger row.

## Restartable multi-artifact closure

A review finalizer often writes an immutable review result, transitions a lifecycle database, writes a closure receipt, and appends a ledger entry. These cannot be one filesystem/SQLite transaction, so every step must be independently immutable and replay-safe.

- Return failure if a late step fails; never claim closure success from partial artifacts.
- On retry, reconcile exact earlier outputs, skip exact work, and finish the missing step.
- Inject a failure after every boundary and rerun to prove convergence without duplicate events.
- Do not “repair” historical evidence in place. Append the next valid state.
- Any source repair invalidates an earlier exact-SHA review; freeze and independently review the successor again.

## Canonical text hashes

When Windows checkout bytes can differ from Git content, make normalization an explicit signed field in both contract and receipt, for example:

```json
{
  "algorithm": "sha256",
  "text_canonicalization": "crlf_to_lf",
  "scope": "tracked_text_content"
}
```

Use the same canonical hashing helper in prepare, finalize, unattended, and independent-review paths. Test LF and CRLF fixtures produce the same digest, and reject any profile drift even if the outer receipt hash is recomputed.
