# Lifecycle-chain and public-replay final gate

Use this as the last independent evidence gate for a local, fail-closed lifecycle before authorizing canonical integration.

## 1. Work only from exact source and external copies

- Freeze the source commit/tree and tracked-clean status for producer, reviewer, and unattended runner worktrees.
- Copy closed SQLite evidence and replay directories to an approved scratch root before opening or mutating them.
- Keep candidate/evaluation tamper probes in separate copies so each probe has one controlled difference.
- Rehash the canonical source/evidence/profile inputs after all probes.

## 2. Derive the lifecycle hash from source and discovered schema

Do not invent an `event_type` column or reuse a schema from an older generation. Inspect the exact source implementation and `PRAGMA table_info(lifecycle_events)` first.

For the V1 lifecycle implementation, the persisted event row is ordered as:

```text
loop_id, sequence, state, contract_hash, previous_hash,
event_hash, occurred_at, external_id
```

The event digest is SHA-256 of canonical JSON for the payload below, with sorted keys and compact separators:

```python
payload = {
    "loop_id": row["loop_id"],
    "sequence": row["sequence"],
    "state": row["state"],
    "contract_hash": row["contract_hash"],
    "previous_hash": row["previous_hash"],
    "occurred_at": row["occurred_at"],
    "external_id": row["external_id"],
}
expected = sha256(
    json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    .encode("utf-8")
).hexdigest()
```

For every event, verify exact sequence, previous-hash linkage, contract hash, timestamp monotonicity, state progression, external identity, and recomputed digest. Verify the loop row independently against the chain tail.

A pending receipt may embed only the pre-review prefix while the durable database has one later `CLOSED` event. In that case require exact equality between receipt events and the database prefix, then bind the closure receipt to the terminal event hash and reviewer identity.

## 3. Keep logical and physical hashes distinct

A receipt commonly has two different hashes:

- **Logical receipt hash:** hash of canonical receipt content after removing the `receipt_hash` field.
- **Physical receipt SHA:** hash of the exact persisted file bytes, including formatting and terminal newline.

Recompute both independently. Bind review packets, comments, ledgers, and closure receipts to the correct one; never compare the logical hash to a field that promises physical file bytes.

## 4. Run the public receipt-present replay probes

Invoke the real top-level unattended/public replay command with the same source revision, schedule identity, and run identity.

1. **Exact replay copy:** no mutation; require replay `PASS`, the same receipt hash, authority flags false, and no byte changes.
2. **Candidate physical mutation:** append bytes to `candidate.json`; invoke receipt-present replay; require nonzero/HOLD with supporting-evidence mismatch and no repair or overwrite.
3. **Evaluation semantic mutation:** parse `evaluation.json`, change a meaningful field, persist valid JSON, and invoke replay; require nonzero/HOLD with supporting-evidence mismatch and no repair or overwrite.

Also retain raw-only/key-order/whitespace probes when the contract requires byte identity. Semantic and raw-only mutations prove different properties.

## 5. Verify immutable writes and finalizer cross-copy rejection

- Inspect every write-once helper for `getattr(os, "O_BINARY", 0)` on Windows.
- Exercise multiline bytes containing both CRLF and LF, read them back, and require exact equality.
- Require exact replay to return an immutable no-op.
- Call the finalizer guard with a worker candidate whose lifecycle copy differs, then with matching bytes but a mismatched lifecycle digest. Both must reject.

## 6. Join review, ledger, telemetry, and control planes

- Require exactly one worker run and one reviewer run, each bound to the expected profile, session, worktree, branch, commit, and terminal outcome.
- Verify task comments from the actual comments table or official CLI; event payloads may record only comment metadata such as author and length.
- Verify worker model/turn/tool telemetry, physical log hashes, reviewer summary hash, and receipt/provider identity.
- Require ledger framing (`\n` terminator, no blank records), stable identity, and a monotonic review-state transition.
- Prove one-shot cron completion from the execution record plus absence from the active-job store/read-only CLI; verify the wrapper hash and run identity.
- Confirm denied authority, restored profiles, and disabled order-capable tasks from current read-only surfaces.

## 7. Classify checker mistakes correctly

A wrong column name, wrong table join, stale ref, or incorrect assertion in the audit script is a harness defect. Diagnose it against discovered schema/source, fix the scratch-only checker, and rerun the affected phase. Do **not** convert a corrected harness typo into a target HOLD.

Issue a target HOLD only for a reproducible implementation or evidence defect. If the requested response format is exactly `PASS` or `HOLD`, keep diagnostic detail in the scratch report and return only the required token.
