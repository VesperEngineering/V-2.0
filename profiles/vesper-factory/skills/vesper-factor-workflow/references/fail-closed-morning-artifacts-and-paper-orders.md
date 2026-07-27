# Fail-Closed Morning Artifacts and Paper-Order Reconciliation

Use this pattern whenever Vesper turns market data into a dated score artifact, basket, dashboard update, or paper order.

## 1. Admit the source session before computing

1. Resolve the operational date in `America/New_York`, then resolve the immediately preceding XNYS session from an exchange calendar. Never use the host's `date.today()` or `today - 1 day`; UTC/host rollover, Mondays, and holidays break them.
2. Verify early closes against the exchange's published calendar. Do not infer them as “the previous session before an observed holiday”: when a holiday is observed Friday or Monday, that heuristic invents false early closes. For a local rule, evaluate July 3 and December 24 themselves and include them only when they are sessions, plus the day after Thanksgiving; retain published fixtures for supported years.
3. Query the actual source used by the factors (`MAX(date)` in the active OHLCV table).
4. Require exact equality between source max date and required XNYS session.
5. Return nonzero before running factors or touching downstream artifacts if they differ.
6. Derive the artifact filename date from the admitted source date, not wall-clock time.

A process exit of zero proves mechanics only. It does not prove source freshness, factor completeness, symbol identity, sector correctness, or economic readiness.

## 2. Make provenance part of every artifact contract

A score artifact should carry both its canonical `date` and `source_ohlcv_date`. A basket must:

- require those fields to agree with its requested date;
- embed a human-readable source-session marker in the body;
- use the same session in its filename and heading;
- independently revalidate ticker syntax and numeric finiteness (`NaN` and `±Infinity` are invalid), even when the producer already validates them;
- require exactly the intended number of distinct symbols/sectors;
- fail rather than reuse or silently relabel an old artifact.

Every trust boundary validates independently: producer validation does not excuse consumer validation. The consumer must verify both filename and embedded provenance. Modification time alone is not proof: touching an old file must not make it admissible. Publish JSON/markdown and durable state atomically so a killed process cannot expose a partial artifact.

## 3. Orchestrate as one bounded chain

For `scores -> basket -> dashboard`:

- run each step sequentially;
- propagate the first nonzero exit;
- apply a timeout per step;
- terminate the **entire descendant process tree** on timeout before releasing the pipeline lock. `subprocess.run(..., timeout=...)` kills only the direct child; on Windows use a Job Object or an equivalent tree kill such as `taskkill /T /F`, and on POSIX start a new process group/session and kill the group;
- use an OS-released singleton/advisory lock to prevent overlap;
- make `--dry-run` check only prerequisites, never claim data readiness;
- do not invoke the broker connector as a generic pipeline test.

Prove tree cleanup with a real regression harness that launches parent → sleeping grandchild, forces timeout, and asserts the grandchild PID is no longer live. If a parent script generates child Python, compile/test the generated payload separately. Parent-file syntax checks cannot detect malformed generated code.

## 4. Derive freshness from the real schedule

Compare the actual scheduler times before choosing a freshness limit. The limit must exceed:

`scheduled gap + normal upstream runtime + bounded jitter`

while remaining tight enough to reject a prior cycle. A 90-minute limit cannot support an 08:05 producer and a 09:40 consumer because the scheduled gap alone is 95 minutes. Keep exact source-session provenance as the primary guard; mtime is only a secondary bounded-window check.

## 5. Reconcile paper orders with durable ownership and recovery

Submission/fill ordering alone is not enough. The connector needs a crash-recoverable state machine:

1. Acquire an OS-level **rebalance process lock** before crossing the broker side-effect boundary; keep it until broker state and durable run state agree.
2. Bind the run state to signal date, exact target list, and a cryptographic basket digest. A changed same-date basket is manual review, not an automatic retry.
3. If durable state already says `COMPLETED` for the exact basket, return a no-op. Never submit again.
4. Require paper mode and an open exchange/broker clock.
5. Validate every symbol through the broker asset endpoint. If sizing uses notional orders, require both `tradable` and `fractionable`; perform this before any reduction.
6. Query open orders. Recover orders owned by prior durable state first; otherwise abort on unknown open orders—never globally cancel protective or unrelated orders.
7. Snapshot equity and positions.
8. Before each submission, atomically append intent to durable state with a deterministic, attempt-scoped `client_order_id`, phase, symbol, side, and amount. Then call the broker. This ordering covers “broker accepted, local response lost.”
9. On a lost response, lookup by the pre-journalled client ID. Never assume an exception means no order exists.
10. Submit reductions/liquidations first, poll every reduction to terminal broker status, and require `FILLED` before buys.
11. Refresh positions, verify off-target exposure, recompute deficits, submit buys, and require terminal fills.
12. On rejection, timeout, unreadable response, or process recovery, enumerate only journal-owned orders; cancel nonterminal owned orders, confirm each reaches a terminal state, then snapshot positions again. If lookup/cancellation/confirmation is uncertain, persist `MANUAL_REVIEW` and block automatic retries.
13. Distinguish at least `RUNNING`, `FAILED_CLEAN`, `MANUAL_REVIEW`, and `COMPLETED`. A crash-recovered run increments an attempt number so client IDs are not reused.
14. Write append-only/unique receipts; never overwrite a fixed daily receipt. Mark durable completion as the idempotency barrier and include order states plus before/after positions.
15. Redact secrets/account identifiers from console and durable errors, bound error text, and write state atomically (`temp + flush/fsync + replace`).

A retry is safe only when it starts from broker truth and a reconciled durable journal. A helper implementation is not operational until the real `main()`/scheduler entry point acquires the lock and routes through it. Tests for internal functions do not prove production integration.

## 6. Logging and symbol checks

- Never log API-key prefixes, account numbers, account IDs, or full broker payloads.
- Log redacted admission status, symbols, public order state, and aggregate values only when needed.
- Do not silently "fix" a suspicious ticker. Check the authoritative universe snapshot and read-only broker/reference metadata. A tradable symbol can still be the wrong company; provenance must establish identity.

## 7. Verification matrix

Run all four layers:

1. **Focused RED/GREEN tests:** exchange-timezone rollover, published early-close fixtures, stale/future files, missing provenance, malformed/nonfinite scores, unknown weights, asset fractionability, unknown open orders, concurrent rebalance lock contention, completed-run no-op, lost submission responses, rejected/timeout fills, owned-order cancellation confirmation, sell-before-buy ordering, process-tree timeouts, and pipeline singleton contention.
2. **Real fail-closed probe:** deliberately use the current source state; if stale, confirm the score and wrapper commands return nonzero before downstream writes.
3. **Real lifecycle harnesses:** use a real parent→grandchild timeout test; for broker behavior use fakes that model “accepted then response lost,” orders that never fill, cancellation races, and recovery from persisted state. Assert not just raised errors but broker cancellations, terminal confirmations, persisted statuses, position snapshots, and no second submission after completion.
4. **SDK-shape check:** instantiate installed request models and inspect method signatures so passing fakes do not hide API mismatch. Confirm broker support for `client_order_id` lookup, cancellation, fractionability metadata, and request-field limits.
5. **Entrypoint proof:** trace the real `main()`/scheduled action to the hardened coordinator. A safe helper that the production entry point bypasses is unfinished work.
6. **Repository gates:** focused tests, full suite with baseline comparison, lint, compilation, diff check, and a scoped static scan for secrets, identifier logging, global cancellation, direct-child-only timeout handling, fixed-name receipt overwrite, and fallback live weights.

Independent reviews are snapshots. If code changes after dispatch, reconcile every finding against current files and dispatch a fresh final review. Do not represent a still-running, stale, failed, or truncated review as approval. Do not mark remediation complete until the final review passes and the exact post-review code has been rerun.

## 2026-07-10 incident snapshot

The first Windows task returned zero and produced a July 9-labeled basket, but the active database ended July 8. The corrected gate required the prior July 9 XNYS session and returned nonzero before basket/dashboard. The old basket was quarantined by adding embedded source provenance. The same review also exposed a 95-minute schedule versus 90-minute age conflict, blanket order cancellation, swallowed broker failures, account-identifier logging, and buy-before-fill reconciliation.

A second independent review then rejected the “hardened” revision because order-fill polling still lacked process-level locking, durable idempotency, response-loss recovery, owned-order cleanup, fractionability admission, and full process-tree timeout handling. It also caught consumer-side nonfinite scores, host-timezone date use, and false early closes generated from observed-holiday heuristics. The remediation session proved the calendar/artifact/fractionability/process-tree slices, and built a durable broker coordinator, but reached its execution limit before wiring production `main()` through that coordinator and rerunning final gates. The durable lesson is completion discipline: implementation present on disk is not production protection until the actual entry point uses it and the post-integration suite plus fresh independent review pass.

These are class-level failure modes; apply the checks above to every future pipeline revision.
