# Atomic Multi-Write Handoffs

Use this reference when a caller needs to turn an immutable reviewed artifact into a downstream task, receipt, notification, or external action via multiple durable writes.

## The invariant

If the contract says “exactly one downstream object and exactly one upstream receipt,” prove that invariant across all cut points—not only on the happy path:

| Cut point | Required behavior |
|---|---|
| Before create | No downstream object; retry may create one. |
| After create, before receipt | Retry must find/recover the same object or fail closed. |
| After receipt | Retry must return the same binding and write nothing. |
| Concurrent same-key callers | One owns the transition; the other returns the same binding or fails closed. |
| Restart between writes | No duplicate object or receipt; unresolved state remains observable. |

## Verify the real idempotency contract

Do not infer atomicity from an `idempotency-key` argument. Read the authoritative implementation/schema and answer:

1. Is the key protected by a database uniqueness constraint or compare-and-set?
2. Is lookup and insert in the same write transaction?
3. Does the operation return a durable existing identity after a crash/retry?
4. Are all dependent writes (object, receipt/event, transition row) in the same transaction?

A preflight `SELECT` followed later by `INSERT` is not atomic. It can race even if a CLI help string promises deduplication. A process-local lock reduces overlap but cannot close a crash window, cover another host, or make independent backend writes transactional.

## Test harness requirements

Use a **stateful** fake/integration harness:

- return a fresh ID for every actual create attempt;
- persist every card and every receipt in lists, not just a final result;
- inject failure after each write;
- run two callers synchronized at each pre-write boundary;
- assert cardinality (`len(cards) == 1`, `len(receipts) == 1`) and exact identity binding.

Never use a fake that always returns the same ID, or a set-only assertion: both can mask duplicated creates.

## Safe designs

Preferred, in order:

1. **One backend transaction:** a dedicated transition command/service atomically reserves the key, creates/reuses the downstream task, and appends the receipt/event.
2. **Transactional outbox:** transactionally persist the intent plus an outbox row; a reconciler delivers it idempotently and records exact remote identity.
3. **Durable compare-and-set state machine:** reserve a transition row before external work; retries reconcile that row, never reissue an unresolved effect.

If none exists, retain the workflow as preview/shadow-only and report the architecture blocker. Do not label it exactly-once or use it to grant execution authority.
