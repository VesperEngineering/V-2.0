# Fail-Closed Streaming Pipeline Patterns

Use these patterns for real-time market-data services whose downstream workers enforce execution safety.

## Universe resolution

- Named universes must resolve to explicit symbols; never map `sp500` or another curated universe to `AM.*`.
- Validate uniqueness, ticker syntax, and a plausible cardinality range.
- Resolution order: live authoritative/free source → last valid runtime cache → bundled validated snapshot.
- If every source is invalid, abort startup. Do not silently broaden scope.

## Synchronous startup validation

Validate before constructing or starting network services:

- Bounded queue sizes: exact positive integers; reject booleans.
- Worker/retry intervals: numeric, `math.isfinite(value)`, and `value > 0`.
- Risk limits and position sizes: numeric, finite, and positive.
- Position-count limits: exact positive integers.

Keep defensive validation at the final execution boundary too. Python comparisons with `NaN` are usually false, so checks such as `loss >= limit` and `order_value > cash` can fail open unless both values are finite.

## Critical-task supervision

Create explicit tasks for the stream, analysis worker, and risk worker. Wait with first-completion semantics. If a critical worker ends before intentional shutdown:

1. Stop accepting bars.
2. Set the shutdown execution gate.
3. Tell the stream to stop and cancel/await its task.
4. Preserve bars already durably journaled; deliberately discard queued stale analysis.
5. Await in-flight thread work so it observes the shutdown gate before order submission.
6. Propagate the worker failure so the process exits visibly and can be restarted.

Catching per-iteration transient exceptions inside a worker is still useful; supervision handles unexpected worker termination.

## Broker-boundary shape validation

HTTP success alone is not acceptance evidence. For submitted orders:

- Require a mapping/object response, a non-empty broker order ID, and a known accepted state.
- Reject lists, `{}`, missing/empty IDs, unknown states, and unexpected multi-status payloads.
- Record acceptance as `submitted`, not `open` or `filled`; leave fill price empty until reconciliation.
- For bulk cancellation, inspect every 207 item and then query open orders to verify none remain.

## Verification matrix

Use both automated tests and direct ad-hoc probes for:

- `NaN`, `+Inf`, and `-Inf` in every numeric broker/config field.
- Malformed success responses and partial 207 failures.
- Risk worker exits while the stream is active.
- Analysis beginning before cutoff and reaching the execution lock after cutoff.
- Offline universe startup using the bundled snapshot.
- Duplicate process/connection behavior and clean single-instance restart.
