# Multi-state lifecycle ledger idempotency probes

Use these checks when one immutable receipt may legitimately have several rows such as `PENDING` then `CLOSED`.

## Required model

Split each row into:

- **identity:** receipt hash plus lifecycle state;
- **immutable core:** schema, receipt/contract/candidate identity, decision, and every authority or promotion literal;
- **state-specific fields:** an explicit allowlist of fields that may differ for that transition.

A new state is valid only when its immutable core equals the prior row for that receipt and the state transition is allowed. Do not infer safety merely because each `(receipt_hash, state)` pair is unique.

## Minimal adversarial sequence

1. Append PENDING; expect `True` and one row.
2. Replay exact PENDING; expect `False` and still one row.
3. As the **first** CLOSED attempt, change one immutable field at a time—decision, contract hash, candidate hash, authority, promotion. Every attempt must raise and leave one row.
4. Append exact valid CLOSED; expect `True` and two rows.
5. Replay exact CLOSED; expect `False` and still two rows.
6. Change the existing CLOSED payload; expect a mutation error and still two rows.
7. Pre-seed duplicate exact states, conflicting duplicate states, CLOSED-before-PENDING, and an exact row followed by a conflicting duplicate. Any operation or replay must reject the history rather than returning replay-suppressed.
8. Run many exact concurrent callers through a barrier. Require exactly one `True`, every other result `False`, exactly one durable row, and no malformed or lost write. Repeat for the PENDING→CLOSED transition.

## Implementation ordering

Under the same interprocess lock:

1. read bounded bytes;
2. parse and validate every row and the whole per-receipt state machine;
3. reject duplicates, conflicts, and bad ordering;
4. decide exact replay versus append;
5. append and `fsync`;
6. publish/check any tail anchor before reporting success.

Never return early on the first exact row before validating the remainder of history. Otherwise an exact row can hide a later duplicate or mutation.

## Review interpretation

Passing ordinary unit tests is insufficient when their setup inserts the valid terminal row before attempting a mutated terminal row: that proves only same-state immutability. A successful cross-state mutation probe or any concurrent duplicate/lost-write observation is a release HOLD for a fail-closed ledger.
