# Entry-Point Restart and JSONL Framing Probes

Use these probes when a lifecycle implementation claims restart safety, exact replay, or append-only evidence integrity. Component tests alone are insufficient: test the same public entry point the scheduler or supervisor invokes.

## Distinguish complete replay from crash recovery

A successful second call after a terminal receipt exists proves only **complete-receipt replay**. It does not prove recovery from intermediate durable states.

For each durable boundary in the real entry point:

1. Run only in unique scratch outside the source worktree.
2. Inject a process-equivalent failure immediately after the boundary (for example after dispatch, candidate persistence, evaluation, review preparation, DB closure, closure-receipt write, and ledger append).
3. Remove the injection and invoke the **same public entry point** with the same source, schedule/task identity, and run/idempotency key.
4. Require convergence to the intended terminal receipt without duplicate events/artifacts, or a receipt-backed explicit `HELD` result with bounded retry consumption.
5. Reject invalid backward-transition errors, stranded accepted/review-ready states, unreceipted partial success, and a scheduler path that simply starts from `CREATED` again.
6. Compare durable event history and all immutable artifact bytes before/after retry.

A state-aware orchestrator should inspect the durable state and execute only the remaining legal suffix. Do not unconditionally replay `start -> dispatch -> running` after a restart.

## JSONL physical framing policy

Validate framing before parsing or appending:

- an empty file is valid;
- reject embedded blank/whitespace-only records, duplicate JSON object keys, malformed/truncated records, and extra records;
- bound total bytes and row count before parsing;
- validate the complete history before returning an idempotent replay result;
- choose one explicit policy for a valid final JSON record that lacks a terminal newline:
  - **strict:** reject the append and leave all bytes unchanged; or
  - **tolerant framing:** while still holding the same writer lock, prepend exactly one line separator to the next canonical row before append.

Never append a new object directly after an unterminated object. Otherwise a function can return success while producing `}{` on one physical line—a silent evidence-corruption bug. Test the chosen policy explicitly:

1. Seed one otherwise-valid row with no terminal newline.
2. Attempt a distinct append.
3. Under strict policy, require a fail-closed error and byte-for-byte unchanged ledger. Under tolerant policy, require two independently parseable rows with exactly one separator between them.
4. In both policies, seed an embedded blank line and require a no-write failure.

## Immutable restart identity and suffix completion

Persist the first canonical orchestration contract before the first lifecycle transition. On retry, reload and validate those exact bytes instead of regenerating time-dependent fields such as `issued_at` and `expires_at`; otherwise a delayed retry changes the contract hash and strands a valid durable state.

Do not let an existing receipt trigger an unconditional early success return. Before reporting replay success:

1. validate the receipt and its source/schedule/run/worktree identity;
2. validate the persisted contract and require its hash to equal the receipt binding;
3. validate the durable lifecycle database and exact event chain;
4. idempotently materialize any missing post-receipt review packet;
5. append or replay-suppress the exact ledger row only after complete ledger validation.

Add process-equivalent failures after evaluation, after review preparation, after receipt write, after packet write, and after ledger append. Retry through the real public entry point with both the same wall clock and a later wall clock. Require the same contract hash, no duplicate lifecycle events, and a complete artifact suffix.

### Clock-stable expiry tests

Expiry-aware restart tests must not embed an absolute date that will eventually become stale during a later review. Anchor the first invocation to an injected `now` captured at test start, advance the injected clock by a relative delta, and keep the validator clock consistent with that contract. Prefer one explicit timezone-aware `now` passed through contract construction and validation; if separate modules call their own `datetime.now`, patch every clock source or refactor to dependency injection. Run a boundary case at or beyond expiry separately and assert the documented fail-closed outcome. A regression that passes only before its literal timestamp expires is not durable evidence.

## Concurrency probe

After framing and full-history checks pass:

- synchronize at least 12 threads and 8 spawned processes with a barrier;
- race identical pending appends and then identical closed appends;
- require exactly one writer and N-1 replay suppressions per wave;
- require physical states exactly `PENDING...`, then `...CLOSED`;
- repeat multiple rounds to catch timing-sensitive lock defects.

## Read-only review hygiene

Set `PYTHONDONTWRITEBYTECODE=1`, disable pytest cache (`-p no:cacheprovider`), and direct `TMP`/`TEMP` plus `--basetemp` to unique external scratch. Re-check source `HEAD` and tracked cleanliness after all probes. Keep injected artifacts and scripts outside the reviewed worktree.
