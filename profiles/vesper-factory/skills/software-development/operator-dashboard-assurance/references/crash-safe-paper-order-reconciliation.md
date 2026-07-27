# Crash-safe paper-order reconciliation

Use this checklist when a bounded paper-order path must remain exactly once across process crashes, transport ambiguity, and local receipt-write failure.

## Durable state contract

- Hold the daily cross-process lock while reading or changing order lifecycle state.
- Atomically persist an immutable same-day intent **before** POST. Include date, exact envelope, deterministic client-order ID, expected account hash, and lifecycle state.
- Treat `PREPARED`, `POSTING`, `UNKNOWN`, `ACCEPTED`, and `RECONCILED` as latches against a different same-day envelope.
- Recover an existing intent before evaluating a new candidate or capacity.
- A local Markdown/JSON receipt is evidence metadata, never proof that the broker accepted an order.

## Recovery contract

For any prior intent or locally accepted receipt:

1. Load credentials only from the approved paper-account context.
2. Verify the current account through the provider account endpoint.
3. GET the deterministic client-order ID; never POST during recovery.
4. Require the broker object to match account ID, provider order ID, client-order ID, symbol, side, decimal notional, order type, TIF, accepted lifecycle status, and New York trading date.
5. Only then write `RECONCILED` intent and receipt.
6. A 404 after `POSTING`/`UNKNOWN`, timeout, rate limit, server error, malformed JSON, or semantic mismatch remains `ORDER_STATUS_UNKNOWN`; it must not clear the attempt latch.

## Identity pitfalls

- Reject provider IDs unless they are nonempty strings. Never use `str(value)` as presence validation: JSON `null` becomes the nonempty string `"None"` and can produce a stable but false hash.
- Never overwrite a broker-returned `account_id` with the expected account before validation. Compare the provider value as returned.
- Parse provider timestamps as valid timezone-aware ISO datetimes, convert to `America/New_York`, then compare `YYYYMMDD`. Prefix matching accepts malformed timestamps and UTC dates that belong to the previous New York session.
- Bind downstream fill, position, and portfolio evidence to both account and provider-order hashes. Do not read positions until exact order identity is proven.

## Minimum adversarial tests

- Crash after POST acceptance but before receipt write; a changed same-day envelope remains blocked.
- `POSTING` intent plus exact broker order recovers without POST.
- Accepted local receipt plus broker 404 remains unknown.
- Null provider order ID is rejected even when its stringified hash matches.
- Explicit wrong broker account is rejected and is never replaced locally.
- Malformed timestamp and UTC timestamp on the previous New York date are rejected.
- Same-symbol unrelated order cannot satisfy fill or position evidence.

Run the focused lifecycle tests first, then the complete suite from a clean committed-tree view.