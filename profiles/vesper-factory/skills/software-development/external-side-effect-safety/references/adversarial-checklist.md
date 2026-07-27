# Adversarial Checklist

## Remote/local transaction

- Durable intent is committed before POST.
- Intent has a unique persisted idempotency key.
- Connect, insert, and commit failure before POST produce zero remote calls.
- Update affects exactly one row.
- Update/commit failure after acceptance triggers compensation while retaining a reconcilable intent.
- Close/cleanup exceptions never mask the primary transaction result.

## Response and state validation

- Require exact remote ID and expected client/idempotency key.
- Treat timeout, malformed body, missing identity, and unknown state as `unknown`.
- Cover accepted, pending, partial, filled, canceled, expired, and rejected states.
- Reject missing, boolean, non-finite, negative, or malformed quantities.
- For cached/configured identifier lists, require the original JSON element type and a domain-specific grammar; never `str()` arbitrary values or accept punctuation-only identifiers.
- Persist partial/filled outcomes as exposure, not merely submitted or rejected.

## Duplicate and recovery behavior

- Sequential and concurrent retries produce one durable intent and at most one POST.
- Duplicate retry performs reconciliation only.
- Reconciliation cannot use an unrelated remote object.
- Crash-recovered unknown/submitting intents are reconciled at startup and periodically.
- Unresolved recovery gates new mutations while monitoring, reconciliation, and verified-flat cleanup remain operational.
- Verified-flat cleanup releases every exposure-bearing/uncertain state that can retain a reservation, not only the happy-path `submitted`/`open` states.

## Capacity reservation and limits

- Enumerate every scarce limit consumed before final settlement: position/order slots, cash, inventory, rate quota, credit, or concurrency permits.
- Recover an existing idempotency key first; a duplicate must reconcile without consuming another reservation.
- In one serialized transaction, read active local intents, reject unknown legacy reservation values, enforce remote current state plus local reservations, and insert the new reservation.
- Pending, unknown, partial, and locally-open outcomes retain reservations until authoritative reconciliation or verified-flat cleanup releases them; assume remote balances and positions may lag immediate fills.
- Test sequential and concurrent distinct intents at the exact limit; assert one durable reservation and at most the allowed remote mutations.
- Test each limit independently so an earlier position/slot rejection does not hide a cash/inventory reservation defect.
- Exercise rollback and commit failures; no remote mutation may occur unless the reservation commit succeeded.

## Compensation and cancellation

- Validate DELETE semantics, then query the specific object.
- Require matching identity, terminal state, and finite non-boolean zero affected quantity.
- Treat mismatched identity, partial fill, malformed response, and 404 as unresolved unless the API contract independently proves zero effect.
- Keep unresolved exposure durable and visible to operators.

## Execution boundaries

- Test disabled mode and wrong/live endpoint on every mutation method.
- Include scheduled cleanup, EOD, shutdown, and cancellation—not just normal submission.
- Confirm tests and reviews make zero real external calls.

## Concurrency and workers

- Hold one lock across the remote action and its success latch.
- Before periodic reconciliation, set the mutation gate false immediately so a newly arriving mutation cannot win the lock while reconciliation is queued.
- In asyncio services, dispatch one synchronous helper with `asyncio.to_thread`; that helper acquires the shared `threading.Lock` and retains it across remote snapshot retrieval, all local intent updates, and publication of the result. Never acquire `threading.Lock` on the event-loop thread and then await.
- While another thread holds the lock, start reconciliation and assert: the gate is already false, a short asyncio heartbeat fires, and shutdown/supervision remain responsive.
- Block reconciliation mid-call and concurrently attempt submission plus verified-flat/EOD cleanup; assert neither proceeds until reconciliation releases the lock.
- Reproduce the dangerous stale sequence (`unknown -> verified-flat closed -> late pending/open`) and assert the closed state cannot be resurrected after the EOD/cleanup latch is set.
- Raise during reconciliation; assert the helper releases the lock while the mutation gate stays false.
- Run concurrent scheduler/EOD calls; assert one mutation.
- Unexpected critical-worker exit stops ingress and preserves the contextual failure.
- Shutdown handles already-failed workers without masking the supervisor error.

## Schema migration

- Test migration from the exact prior schema.
- Run migration twice.
- Run migration concurrently.
- Serialize discovery plus ALTER/index creation; verify unique indexes afterward.

## Evidence before commit

- Exact staged diff reviewed.
- Relevant suite and compile/lint checks pass.
- Focused direct probe exercises the newest invariant.
- Temporary fixtures are removed and local DB state restored.
- Independent reviewer returns no security concerns or logic errors.
