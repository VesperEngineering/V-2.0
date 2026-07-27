# Broker Protective-Order Safety Review

Use this reference when reviewing stop-loss, take-profit, liquidation, or rebalance architecture that can mutate broker orders. The broker is the source of truth; local files are projections, not execution authority.

## Core invariants

1. **Coverage:** every broker-confirmed long quantity has exactly one owned protective closing order covering the remaining quantity, except during a short, explicit maintenance transition guarded by a lease and watchdog.
2. **No competing exits:** a resting stop, local gap breaker, rebalance sell, and operator flatten must not independently close the same quantity.
3. **Fill-driven state:** accepted/submitted is not filled. Position and stop quantities advance only from broker fills/partial fills or reconciliation.
4. **Idempotent intent:** every logical action has a deterministic client order ID/version. After timeout or crash, query by ID before retrying.
5. **Broker-authoritative recovery:** startup and periodic reconciliation compare broker positions, open orders, replacement lineage, and local state. Resolve orphan stops, uncovered positions, stale records, and unknown outcomes before new entries.
6. **Single writer:** serialize rebalance, cancel/replace, and emergency exits with account/symbol leases. Multiple schedulers or manual invocations must not duplicate actions.
7. **Protective kill switch:** disabling new execution must preserve existing protective orders unless an operator explicitly chooses cancel/flatten.

## Review checklist

### Order ownership and lifecycle

- Reject any `cancel all open orders` pattern. Cancel only orders in the application's client-order-ID namespace.
- Model `new`, `accepted`, `partially_filled`, `filled`, `rejected`, `canceled`, `expired`, `done_for_day`, `pending_cancel`, `pending_replace`, and `replaced`.
- Track `replaces` / `replaced_by` lineage and wait for broker acknowledgement before trusting replacement state.
- Update protection after every add/reduce fill; do not protect only the latest delta.
- Use decimal quantities/strings at broker precision, not binary float round-trips.
- Verify order-type/TIF support separately for whole, fractional, extended-hours, and advanced orders.

### Stop and emergency-exit interaction

- A broker stop and local emergency market sell are competing writers unless coordinated.
- Before a local exit, reconcile current position and stop state, then use one serialized transition. Never mark closed on order acceptance.
- Explicitly define precedence among hard stop, gap breaker, time stop, rebalance exit, and operator action.
- Broker stop-market prices are triggers, not loss guarantees; gaps, halts, and liquidity can produce worse fills.

### Persistence and recovery

- Prefer a transactional event journal/state machine (for example SQLite WAL) over mutable JSON as the authority surface.
- If JSON is exposed to dashboards, derive it atomically from authoritative state and attach freshness/health metadata.
- Durable session counters must survive process restart. A module global does not work when a scheduler starts a fresh subprocess each interval.
- Audit writes should be immutable or append-only and include intent ID, order ID lineage, fill quantities/prices, data timestamps, and reconciliation result.

### Market data and calendar

- Quotes contain bid/ask; previous close normally comes from a timestamp-validated snapshot/bar. Do not assume a quote object contains previous close.
- Use eligible trades with freshness, session, feed, halt, and crossed-market checks for trigger logic. A wide/stale bid is not a stop-election trade.
- Distinguish opening-gap logic from intraday-decline logic; avoid predicates where one threshold subsumes another.
- Use an exchange calendar and timezone database, including DST, holidays, and early closes. Validate cron day-of-week conventions.

### Scheduler and liveness

- A polling interval is not a latency guarantee if jobs run synchronously.
- Timeouts create ambiguous broker outcomes when submission may have succeeded before process termination.
- Require a singleton lease, heartbeat, event-stream health, REST catch-up, and alerts for uncovered quantity, rejected/expired stops, or reconciliation drift.
- Treat a 5-second monitor as supervisory/reconciliation logic where possible; broker-resident protection should not depend on workstation uptime.

### Backtest realism

- Do not simulate every touched stop as a fill at the stop price.
- If the session opens through a sell stop, model an open-or-worse fill plus slippage; include halts and thin liquidity.
- Intraday event ordering requires intraday data or conservative ambiguity rules.
- Test correlated basket gaps; `weight × stop distance` is not a hard portfolio-loss cap.

## Deployment gates

### P0 — before unattended broker-connected paper execution

- Authority manifest/board explicitly opens the exact order lifecycle and account envelope.
- Central execution guard covers creation, cancel, replace, status reads, and sells—not just entries.
- Coverage, single-writer, idempotency, reconciliation, calendar, fractional/TIF, and alerting invariants pass tests.

### P1 — before supervised paper pilot

Run fault injection for crash-after-submit, timeout ambiguity, duplicate daemon, partial entry/exit fills, cancel/replace race, simultaneous stop and gap trigger, add/reduce rebalance, stale data, event-stream disconnect, holiday/DST/early close, corporate action, halt, and GTC expiry. Run shadow/report-only comparison first.

### P2 — before broader unattended use

Require a multi-session paper soak with forced restarts/network loss, operator runbooks, immutable evidence, heartbeat/dead-man alarms, and demonstrated startup recovery from stale or empty local state.

## Vesper-specific review cues

- `scripts/alpaca_rebalance.py` historically canceled all open orders and submitted notional adjustments; any protective-order proposal must remove global cancellation and become fill-driven.
- The internal scheduler historically used fixed UTC offset/weekday checks and synchronous subprocess execution; do not rely on its nominal interval without calendar and liveness validation.
- Current bounded paper authority can be much narrower than a proposed basket-wide stop lifecycle. The board and central execution guard must open the exact future lane before broker mutations.
- A stop design using notional entries plus fractional GTC stops must verify broker support; Alpaca documentation has distinguished whole-quantity GTC from fractional DAY support.
