# Vesper Swing hardening audit — 2026-07-10

## Deployment verdict

Vesper Swing is a collection-only validation service, not ready for unattended paper or live deployment. Keep execution explicitly disabled until broker reconciliation, idempotency, ownership, and independent risk scheduling are complete.

## Verified baseline

- One captured session contained 4,488 signals and 4,486 LLM analyses, but zero trades and zero persisted minute bars.
- VWAP remained a firehose: 2,777 signals in one session despite nominal cross/volume gates.
- Massive `AM.*` plus synchronous signal/LLM work in the WebSocket callback produced repeated keepalive timeouts.
- Ollama calls reached 30-second timeouts; malformed/truncated JSON also occurred.
- Alpaca paper connectivity was healthy, but no end-to-end trade lifecycle had been validated.

## Root causes

1. Execution was implicitly active whenever an LLM signal passed.
2. Entry orders were plain market orders; stop/target prices existed only in SQLite.
3. EOD `15:55` was compared to UTC, not `America/New_York`, depended on an exact bar minute, and could be followed by immediate re-entry.
4. Missing direction defaulted bullish; unknown directions became sells. RSI `oversold` therefore mapped incorrectly.
5. The receiver awaited the entire synchronous signal → REST → Ollama → SQLite → Alpaca path, starving WebSocket pings.
6. `minute_bars` existed in the schema but had no write path.
7. `all` and nominal `sp500` universe modes both mapped to `AM.*`; no real downstream universe filter existed.
8. Signal rules were level-triggered without cooldown/re-arm, full warm-up, or reliable source timestamps.
9. There was no fill/order/position/P&L reconciliation, strategy ownership, or duplicate-order protection.

## Hardening implemented

- Stopped the process; backed up database and logs.
- Initialized Git while excluding credentials, config, runtime data, logs, backups, and venv.
- Added pytest coverage using strict RED→GREEN cycles.
- Added fail-closed execution: explicit `enabled: true`, `mode: paper`, and exact Alpaca paper URL are all required. Local config remains disabled.
- Added broker-hosted Alpaca bracket payloads for stop and target legs.
- Added explicit direction mapping: oversold/bullish → buy; overbought/bearish → sell; missing/unknown → reject.
- Added `America/New_York` EOD handling, weekday suppression, once-per-session triggering, and post-cutoff entry rejection.
- Narrowed validation from `AM.*` to a fixed 15-symbol liquid watchlist.
- Added minute-bar persistence before analysis using `(ticker, timestamp)` deduplication. Reconnect/replay duplicates are not evaluated twice.
- Added a bounded bar queue and worker-thread isolation so slow Ollama/API work does not starve the WebSocket event loop.
- Queue overload retains the durable bar while skipping stale live analysis instead of blocking ingress or growing memory without bound.
- Reconnect backoff resets after valid market data resumes.
- A controlled live smoke test authenticated, subscribed to the exact watchlist, persisted live bars, placed zero trades, and left no process running.

## Verification evidence

- Focused project tests passed after the implementation cycles.
- A direct OS-temp ad-hoc harness was created with `tempfile.NamedTemporaryFile`, prefix `hermes-verify-`, under `C:\Users\bgonn\AppData\Local\Temp`.
- The harness directly asserted execution gating, live-endpoint rejection, direction semantics, EDT cutoff, SQLite dedupe, persistence-before-callback ordering, reconnect reset, and event-loop responsiveness during a simulated slow worker.
- The first temp harness could not import `src` because scripts run from the temp directory; the durable fix is to inject the project root into `sys.path` or set an explicit project `PYTHONPATH`. The rerun passed with `AD_HOC_VERIFY_OK` and the temp file was removed.
- Describe this as focused ad-hoc verification, not proof that the full application is deployment-ready.

## Independent review failure and follow-up hardening

The first independent review correctly failed the milestone despite a green test suite. It found that orchestration-level execution checks were bypassable, broker/DB uncertainty still failed open, EOD latched before verified success, bracket legs could race flatten orders, shutdown could abandon queued work while `to_thread` continued, SQLite journaling still ran on the WebSocket loop, reconnect reset waited for a bar, and non-positive queue sizes could create an unbounded queue.

Follow-up changes established these class-level rules:

- Repeat the execution gate inside `PaperTrader.submit_trade()`; unknown positions or P&L block entry.
- EOD `is_due()` is observational. Only `mark_flattened()` mutates state after open orders are canceled, positions are closed, flatness is rechecked, and local rows reconcile successfully.
- An independent periodic risk worker retries EOD even when no bars arrive. Entry, EOD, and shutdown share an execution lock.
- Shutdown stops ingress, sets a runtime no-order flag, stops risk work, discards already-journaled queued analysis, waits for in-flight thread work, then stops workers.
- SQLite journaling runs with `asyncio.to_thread`; journal-before-analysis ordering remains intact.
- Queue sizes must be positive integers; zero, negative, string, `None`, and booleans are rejected.
- Reconnect delay resets after successful authentication/subscription setup and valid bars.
- EOD cancels open/bracket orders before using Alpaca position-close endpoints, then verifies no positions remain; failed attempts return false and remain retryable.

The clean single-instance smoke test persisted additional bars, produced zero trades, showed no new warnings/errors, and left no process. A prior smoke test received Massive close code 1008 because another `start.bat` process was already connected. Identifying its exact Python/cmd process tree and stopping only that tree resolved the issue. This is a durable reason to add a single-instance application lock.

The final EOD lock race was resolved: after acquiring the shared execution lock, the worker rechecks `is_due()` before flattening. The regression suite then passed 31 tests, and a focused OS-temp `hermes-verify-` harness confirmed execution remained disabled and concurrent workers could not double-flatten or double-latch EOD completion. Before handing control back, the agent verified no Swing process was running and the desktop launcher remained collection-only (`execution.enabled: false`, paper mode, fixed watchlist). The user was explicitly cleared to click the desktop icon for data collection—not paper execution.

### Second independent review: deeper race and broker-response defects

A second review failed even after the first hardening pass. The failures and durable fixes were:

- **Pre-cutoff analysis could re-enter after EOD.** Checking `entries_allowed()` only before slow LLM analysis is insufficient. The final order boundary now takes a fresh timestamp and rechecks the entry window inside the shared execution lock.
- **Alpaca cancel-all can return HTTP 207 arrays.** Treating the decoded response as a dict caused `.get()` failures. Cancellation logic must branch on response shape, require every 207 item to carry a 2xx status, and reject unknown shapes.
- **Cancellation acceptance is not cancellation completion.** After DELETE `/v2/orders`, query `GET /v2/orders?status=open`; any surviving order or unknown response blocks flatten completion and leaves the EOD retry armed.
- **Local trade rows were stale risk authority.** Daily-loss enforcement now uses broker account equity versus `last_equity` and returns unknown on missing, malformed, or unavailable broker state. Local SQLite remains research/audit state until full fill reconciliation exists.
- **Risk-worker exceptions killed retries.** Each periodic check catches/logs exceptions and continues. Shutdown also handles an already-failed risk task before draining/discarding queued analysis and waiting for in-flight work.

Regression coverage should reproduce each defect, not merely mock the happy path: slow analysis crossing the cutoff, mixed-success 207 arrays, surviving open orders, malformed broker equity, transient risk exceptions, and shutdown with a failed risk task. Focused ad-hoc verification must be labeled as such; it does not replace the full suite or independent review.

### Third independent review: non-finite broker numbers

A third review found that syntactically valid floating-point values can still represent unknown risk state. `float("nan")`, `float("inf")`, and `float("-inf")` do not raise, while comparisons such as `dollar_value > nan` and `nan >= loss_limit` are false. That allowed unknown buying power to reach order submission and unknown equity to appear below the loss limit.

Durable fix:

- Centralize account-number parsing and require `math.isfinite()` after `float()` conversion.
- Return `None` for missing, malformed, NaN, or infinite cash/equity fields.
- Make `submit_trade()` explicitly reject `None` cash before any comparison or Alpaca POST.
- Require finite, valid current and prior equity before calculating the daily loss.
- Apply the same finite-number rule to market prices before position sizing.
- Parameterize tests and ad-hoc probes across `nan`, `inf`, and `-inf`; prove the broker POST is unreachable for each.

This is a class-level fail-closed rule for any external numeric risk state, not an Alpaca-specific quirk.

### Fourth and fifth independent reviews: malformed success and non-finite timing

Later reviews found that transport success is not sufficient evidence of broker acceptance, and configuration numbers need the same finite-value discipline as broker numbers.

Durable fixes:

- Validate order-creation responses by shape and semantics before touching SQLite: require a mapping, non-empty broker order ID, and a known accepted/pending status. Reject `{}`, arrays (including unexpected 207 payloads), missing/empty IDs, and unknown statuses.
- Record an accepted order as `submitted`, with no entry price. Preserve the signal price only as audit metadata. A broker acknowledgment is not a fill; only reconciliation may populate fill price/time and promote lifecycle state.
- Guard tests against polluting the real local database: monkeypatch `get_db` to raise if malformed-response paths reach persistence. If a RED test does create artifacts, identify and delete only exact test rows, then verify the trade count.
- Validate periodic risk intervals with `math.isfinite(interval) and interval > 0`. NaN and infinities can stall `asyncio.wait_for` and silently disable future EOD retries.
- Bundle a validated S&P constituent snapshot in tracked source as the final offline fallback. Runtime order is live Wikipedia → writable runtime cache → bundled validated snapshot; every layer still enforces uniqueness, symbol syntax, and a 450–550 count.
- Repeated OS-temp harness runs may remain classified as “unverified” by a workspace status hook. Do not inflate them into suite evidence or loop indefinitely: report the successful probe as ad-hoc, state the status mismatch, and rely on the project suite plus independent review for canonical confidence.

### Sixth and seventh independent reviews: worker supervision and durable order intent

Further adversarial review showed that catching exceptions *inside* the periodic risk loop was necessary but not sufficient. Invalid configuration could kill only the background task while the stream continued, and a failed bar task could have its contextual supervisor error masked during shutdown. It also showed that POST-then-persist can leave a broker-accepted order untracked when SQLite fails.

Durable fixes and rules:

- Validate execution-risk configuration synchronously before constructing external services and again at `run()` entry. Require finite positive `max_daily_loss` and `max_position_size`, a positive integer `max_open_positions`, and a finite positive `risk_check_interval_sec`. The trader boundary independently rejects booleans, numeric strings, missing values, zero, negatives, NaN, and infinities.
- Supervise the Massive stream, risk worker, and bar worker with `asyncio.wait(..., return_when=FIRST_COMPLETED)`. Unexpected completion of either worker stops ingress and the stream immediately, activates the runtime no-order gate, and raises a contextual `<worker-name> exited unexpectedly` error.
- Shutdown handles already-failed risk and bar tasks symmetrically. Their raw exceptions are logged/absorbed during cleanup so they cannot mask the supervisor’s contextual failure.
- Treat broker submission and SQLite state as a distributed transaction. Before POST, commit a durable `submitting` row containing a deterministic `client_order_id`, intended quantity, stops/target, and signal price metadata. A pre-intent database failure prevents POST.
- Add `client_order_id` to the broker order. A semantically valid acknowledgment updates the same row to `submitted`, still with no fill price. Fill reconciliation alone may promote it and set actual price/time.
- If the post-acceptance SQLite update fails, send a compensating `DELETE /v2/orders/{order_id}`. If cancellation is uncertain, the durable `submitting` intent remains the restart-reconciliation handle rather than losing the order entirely.
- Tests must cover `get_db`, INSERT, COMMIT, and post-acceptance UPDATE failures, and prove POST ordering plus compensation. Failure-path tests must replace the database dependency so RED tests do not create operator-data artifacts.

### Eighth and ninth independent reviews: idempotent lifecycle reconciliation

Later adversarial review proved that a durable pre-POST intent is only the beginning of safe order lifecycle management. The durable rules are:

- Add `client_order_id` and `broker_order_id` through an additive, repeat-safe SQLite migration. Enforce a unique partial index for non-null client IDs, and test migration from the exact legacy trades schema twice.
- Create intents transactionally with insert-or-recover semantics. Concurrent or restarted attempts for the same deterministic client ID must produce one row; the loser performs broker lookup by client ID and never another POST.
- Preserve ambiguous POST outcomes as `unknown`/`submitting`. A timeout or malformed response can occur after broker acceptance, so it is not evidence of rejection.
- Require exactly one affected row when promoting an intent. Zero-row updates are failures even if commit succeeds. Catch/log connection-close failures separately so cleanup cannot mask commit state or bypass compensation.
- Model broker lifecycle states explicitly. Accepted/pending/new states are submitted; partial and full fills are real open exposure; canceled/expired/rejected are no-exposure only when authoritative finite `filled_qty` is exactly zero. Terminal status alone does not erase a partial fill.
- A compensating DELETE is not proof of no exposure. Verify with a specific-order GET: response ID must match, terminal status must be expected, and filled quantity must be exactly zero; an authoritative 404 is also acceptable. Missing identity, missing quantity, malformed numerics, or any nonzero fill remain uncertain/exposed.
- Reconcile valid `filled` and `partially_filled` responses on both the initial POST path and duplicate/restart lookup path. Never leave a confirmed fill permanently `unknown` merely because it was faster than expected.
- Apply execution safety to every mutating broker path. Disabled mode or a non-paper endpoint blocks entry, compensating cancellation, EOD cancel-all, and liquidation.
- Use non-throwing connection cleanup after EOD reconciliation; a close failure after a successful commit must not trigger repeated flattening or mask completion.

Regression coverage should include ambiguous timeout-after-send, concurrent duplicate intents, zero-row update, insert/update commit failure, close failure, malformed DELETE, mismatched response ID, canceled-with-partial-fill, initial filled response, duplicate filled lookup, disabled EOD, live-endpoint EOD, and repeat-safe legacy migration.

### Tenth review preparation: response binding and concurrent migration

Further adversarial probes exposed three language/database edge cases that generalize beyond Alpaca:

- **Endpoint choice does not prove response identity.** Even a lookup-by-client-ID response must echo the exact expected `client_order_id`. Initial POST and duplicate/restart reconciliation both reject missing or mismatched identity; they must not promote the durable intent based only on an order ID and plausible status.
- **JSON booleans are numeric in Python.** Because `bool` subclasses `int`, `float(False)` silently becomes zero and can falsely prove an order unfilled. Reject booleans before parsing `filled_qty` or any broker/config risk number, then apply finite/range validation.
- **Repeat-safe migration is not concurrency-safe migration.** Two initializers can both observe a missing column before either runs `ALTER TABLE`. Serialize schema discovery plus mutation with `BEGIN IMMEDIATE` or an equivalent process lock, and force a two-thread/process legacy-schema regression test.

Focused regression cases: mismatched/missing client ID on initial POST and duplicate lookup, `filled_qty` values `true`/`false`, and simultaneous migration from the pre-change trades table. These checks complement—but do not replace—a startup sweep for unresolved `submitting`/`unknown` intents.

## Durable engineering lessons

1. **Journal before analyze.** Receiver responsibilities are decode → validate → persist/dedupe → enqueue. Never run LLM, REST, trading, or analysis writes inline.
2. **Bound every queue.** On overload, preserve durable inputs and reject stale work explicitly; do not block ingress or use an unbounded queue.
3. **Order acceptance is not a fill.** Persist broker IDs and reconcile pending, partial, filled, canceled, and rejected states before trusting positions or P&L.
4. **Unknown risk state must fail closed.** API/DB failures must not become “zero positions” or “no daily loss.”
5. **EOD must be independent of bars.** Timezone-correct callback checks are only a fallback; final design needs a scheduler that cancels strategy orders, flattens strategy-owned positions, verifies flatness, retries, and prevents re-entry.
6. **Use strategy ownership and idempotency.** Deterministic `client_order_id` values, broker/database uniqueness, and pending-order checks must prevent retries and repeated signals from stacking exposure. Flatten only strategy-owned quantities.
7. **Use event timestamps.** Persist source, receipt, and evaluation times separately. Forward-return research cannot rely on processing time.
8. **Signals should be transitions, not persistent levels.** Use first cross/first extreme entry/first opening-range break, complete warm-up, and empirically selected cooldown/re-arm rules.
9. **A named universe must be real.** `sp500` must never silently mean `AM.*`; build and snapshot a point-in-time tradeable universe with security-type and liquidity constraints.
10. **Do not tune thresholds without outcomes.** Persist contiguous bars and calculate net 5/15/30/60-minute forward returns, MFE/MAE, spread, slippage, and capacity before expanding the universe or enabling execution.

## Remaining blockers before paper execution

- Continuous broker fill/order reconciliation and restart recovery beyond submission-time lookup.
- Daily realized-P&L reconciliation that fails closed.
- Expected paper account-ID assertion and strategy ownership boundary.
- Per-symbol exposure gates and strategy-owned pending-order checks.
- Marketable-limit/slippage and stale-quote controls.
- Production-grade EOD reconciliation: strategy ownership, actual exit fills/prices/P&L, retry observability, and restart recovery.
- Single-instance process lock before opening the Massive WebSocket.
- Reconnect gap detection and Massive REST backfill.
- Signal cooldown/re-arm, true 09:30 ET opening range, full warm-up, and source timestamps.
- Forward-return/MFE/MAE labels with spread/slippage costs.
- Real Vesper-holdings exclusion.
- Move plaintext credentials to environment/secret storage and rotate if exposed.
