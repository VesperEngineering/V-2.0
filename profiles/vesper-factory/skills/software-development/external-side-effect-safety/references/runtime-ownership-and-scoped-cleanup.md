# Runtime Ownership and Scoped Cleanup

## Cross-process ownership

A thread lock only serializes one process. Any service that owns a singleton ingress stream or remote-mutation authority also needs a process-lifetime OS file lock.

- Acquire the non-blocking lock before database recovery, stream connection, or remote reconciliation.
- Keep the file handle open for the entire runtime and release it in `finally`.
- On Windows, lock a byte with `msvcrt.locking`; on POSIX, use `fcntl.flock(LOCK_EX | LOCK_NB)`.
- Write the current PID only after lock acquisition. PID text is diagnostic; the OS lock—not PID freshness—is authoritative.
- Test with two independently opened handles: the second acquisition must fail until the first releases.
- Test release when startup or runtime raises.

## Account identity before cleanup

A safe endpoint is not enough to identify the intended account. Before cancellation or liquidation:

1. Fetch the authoritative remote account.
2. Require an explicitly configured expected account identifier.
3. Match exact type and value and require an active account state.
4. Perform this check before every cleanup mutation, not only at startup.

Missing, malformed, inactive, or mismatched identity must block all mutation.

## Strategy-scoped cancellation and liquidation

Never use account-wide cancel-all or close-all when the account may contain manual or foreign-strategy assets.

- Load active local ownership from durable intents before remote mutation: ticker, deterministic client order ID, and broker order ID.
- Persist the broker order ID on initial acceptance and every reconciliation path.
- Attribute bracket children through an exact durable parent broker order ID when the broker exposes `parent_order_id`.
- Fetch open orders and positions before mutation. If any cannot be attributed exactly, abort before canceling or closing anything.
- Cancel owned orders individually and verify each matching terminal zero-fill result.
- Re-fetch open orders before closing positions; uncertainty or any unexpected remaining order blocks liquidation.
- Close only preflighted owned tickers, then verify the scoped positions are gone before releasing local reservations or setting an EOD latch.

Dedicated accounts reduce ambiguity but do not replace durable ownership checks.