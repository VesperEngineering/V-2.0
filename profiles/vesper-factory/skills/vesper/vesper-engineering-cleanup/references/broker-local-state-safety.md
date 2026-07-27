# Broker and Local-State Safety Review

Use this checklist for Vesper changes that mutate Alpaca state, persist order state, or rely on critical background workers.

## Execution authority

Apply the same enable/mode/endpoint/account guard at every broker-mutating method—not only signal submission. Enumerate scheduled EOD cleanup, cancel-all, liquidation, retries, shutdown handlers, and compensation paths. Probe disabled mode and live endpoints and assert zero mutation calls.

## Durable intent and idempotency

A broker call and SQLite cannot be atomic. Use a durable intent/outbox:

1. Commit a unique deterministic `client_order_id` intent before POST.
2. Send that ID to Alpaca.
3. Reconcile broker acceptance into local state without claiming a fill.
4. On retry/restart, get-or-create the intent and query Alpaca by client ID; never blindly POST again.
5. Keep timeout, transport error, and malformed response as `unknown`/`submitting`. These outcomes may mean Alpaca accepted the order.

Required adversarial probes:

- DB open/insert/commit failure before POST => zero broker calls.
- Broker acceptance followed by DB open/update/commit failure => durable unresolved intent plus verified compensation or reconciliation.
- UPDATE rowcount zero => failure, never success.
- Connection close failure cannot mask the primary result or bypass compensation.
- Duplicate and concurrent retry => one intent and at most one POST.
- Existing migration => unique partial index present on upgraded databases, not only fresh schema.

## Compensation

Validate compensation as strictly as submission. `{}` or a generic non-error dictionary is not proof. After DELETE, query authoritative order state and require canceled/expired/rejected/not-found. If verification fails, preserve an unresolved intent and surface it to reconciliation/operator controls.

## Worker supervision

Treat stream, risk, persistence, and queue workers as a supervision group. First unexpected completion must stop ingress and broker mutation. Shutdown must collect already-failed tasks without replacing the contextual supervisor error. Test each critical worker independently; symmetry cannot be assumed.

## Numeric risk configuration

For strict positive numeric limits, reject booleans, numeric strings, NaN, Infinity, zero, and negatives. Validate synchronously before starting external services and retain defensive checks at the final mutation boundary.

## Review stopping rule

For broker-mutating changes, a fixed review-cycle limit is not an authorization to commit. Continue independent adversarial review until it passes, or leave execution disabled and escalate unresolved blockers. Never paper-smoke, commit, or enable execution under a failed verdict.
