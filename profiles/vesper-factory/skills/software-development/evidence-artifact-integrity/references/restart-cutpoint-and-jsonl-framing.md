# Restart Cut-Point and JSONL Framing Review

Use this recipe for receipt-producing runners that combine a durable lifecycle database, immutable artifacts, and an append-only JSONL ledger.

## JSONL framing matrix

Run all probes while exercising the real writer lock:

1. empty ledger;
2. one valid row ending in `\n`;
3. one valid final row with no terminal newline;
4. malformed JSON and unknown lifecycle state;
5. duplicate state identity;
6. `CLOSED` first and reverse `CLOSED -> PENDING` history;
7. immutable-field mutation across states;
8. JSON scalar-type mutation (`false` versus `0`, `1` versus `1.0`);
9. exact replay;
10. unrelated append into a ledger containing any corrupt receipt history;
11. same-process thread contention;
12. independent-process contention.

For a valid non-empty file lacking a final newline, the writer must either fail closed without changing bytes or write a separator before the next canonical row. Returning success after concatenating two JSON objects is corruption even if the pre-append history parsed correctly.

After every append or replay, parse every physical line, assert the exact row count, and verify the full per-receipt lifecycle invariant before releasing the lock.

## Durable crash-cut matrix

Inject one crash after each durable boundary:

- immutable contract persisted;
- lifecycle created/classified;
- dispatch identity bound;
- candidate persisted;
- evaluation persisted;
- decision transitioned;
- review-ready transitioned;
- receipt persisted;
- review packet persisted;
- ledger appended;
- independent closure persisted.

Rerun the same immutable invocation identity after each crash. The runner must inspect durable state and execute only missing transitions. It must not blindly restart at dispatch, append duplicate events, reopen terminal state, overwrite immutable artifacts, or generate a successor.

Persist and reuse one immutable contract before the first state transition. If issuance or expiry timestamps are regenerated on retry, the contract hash can drift and truthful recovery becomes impossible.

## Clock and expiry matrix

Freeze every module that consumes time, not only the top-level runner. Prefer an injected `now` value; otherwise patch the runner, contract validator, lifecycle validator/store, and any receipt freshness validator to one shared clock. Derive `T0` at test runtime rather than embedding a date that will soon expire.

Probe at least:

1. immediate replay at `T0`;
2. restart within the admission window (`T0 + epsilon`);
3. in-flight reconciliation after expiry (`T0 + expiry + epsilon`);
4. exact replay of a completed receipt after expiry.

Expiry may reject a brand-new admission. It must not strand or relabel a previously admitted immutable run. A test that advances only the runner clock while the validator uses real wall time does not prove delayed restart and can change from green to red while the suite is running.

## Expected replay outcomes

Test these through the public runner/CLI that owns the idempotency decision, not only through a lower-level controller method. Enumerate every early return that can emit replay `PASS`, especially the receipt-present fast path, and prove each reaches the same companion validator.

- Final receipt present and valid: return exact replay only after validating every contract-required companion and the durable lifecycle binding.
- Durable state ahead of artifacts: deterministically regenerate only the missing artifacts from persisted contract/input identity.
- Artifact present but state behind: validate exact bytes, then complete the missing transition once.
- Identity/hash mismatch or malformed persisted state: hold fail-closed; never repair by overwriting.
- Stale lease: transition according to the explicit stale-lease contract, not by restarting execution.

## Required-companion mutation matrix

After producing a valid completed run, independently replace, truncate, delete, and cross-copy each required artifact: contract, candidate, evaluation, review packet, lifecycle database/event chain, receipt, and ledger row/anchor. Reinvoke the exact run identity through the **top-level public entrypoint** after each mutation. Include semantically equivalent raw-byte changes—trailing newline, indentation/key order, and LF/CRLF—because schema or object equality can hide a broken content binding. Replay may return `PASS` only if the artifact still validates exactly or an explicitly permitted deterministic recovery reconstructs it and revalidates the complete set. A receipt's embedded candidate/result does not make mutated on-disk `candidate.json` or `evaluation.json` acceptable when the contract declares those files required. If a controller-level mutation test passes but the receipt-present runner returns before calling the controller, the workflow remains `HOLD`.

## Source-bound proof reset

Real worker, reviewer, unattended, and scheduler evidence is bound to the executable source SHA. Any executable-source repair after a proof invalidates that proof for final acceptance. Preserve old evidence as historical, then rerun the exact-source proof chain; never relabel old receipts as evidence for the new SHA.
