# Trust Audit Checklist

## Operator questions

- [ ] What happened?
- [ ] What changed?
- [ ] What needs attention?
- [ ] What happens next and when?
- [ ] Can each important number be trusted?
- [ ] Is evidence available for a follow-up question?

## Global truth bar

- [ ] Overall health is derived, not hardcoded
- [ ] Worst subsystem state propagates upward
- [ ] Scheduler heartbeat and identity
- [ ] Last complete pipeline result, duration, and receipt
- [ ] Dashboard payload generation time and age
- [ ] Source-data timestamps and ages
- [ ] External system/feed connectivity and snapshot age
- [ ] Current mode/account and authority boundary
- [ ] Incident count and next expected action

## Data and deployment lineage

- [ ] Exact running process, command, cwd, static root, API base
- [ ] Running artifact matches repository source
- [ ] No shadow/legacy deployment copies
- [ ] Raw candidate, approved output, and observed external state are distinct
- [ ] Every major widget has source, timestamp, transformation, cadence, fallback, and error behavior

## Refresh

- [ ] Browser fetch age is not mislabeled as data age
- [ ] Cadence changes correctly at session boundaries
- [ ] Settings changes do not leak duplicate timers
- [ ] Hidden-tab and sleep/resume behavior is safe
- [ ] Long aggregation cannot block all serving
- [ ] Last-known-good data becomes visibly stale/degraded

## Scheduler and pipeline

- [ ] Expected versus actual run
- [ ] Start, finish, duration, retries, and running state
- [ ] Missed-run detection with grace period
- [ ] Failed stage and concise error
- [ ] Output artifact, row count, freshness, and validation
- [ ] Dependency state and next safe action
- [ ] Timezones are explicit and converted exactly once

## Autonomous trading/risk

- [ ] Raw scores are not labeled as execution basket
- [ ] Tradability/universe validation is visible
- [ ] Actual factor contributions and deployed weights
- [ ] Broker mode/account, timestamp, and connectivity
- [ ] Target versus actual weights and drift
- [ ] Open/rejected orders and rebalance receipt
- [ ] Gross/net/beta exposure
- [ ] Sector caps, concentration, stops, and risk headroom
- [ ] P/L definitions
- [ ] Drawdown includes observation count
- [ ] Turnover, costs/slippage, and benchmark context

## Control safety

- [ ] Labels match endpoint behavior
- [ ] High-impact actions show exact scope and mode
- [ ] Preconditions and risk checks are visible
- [ ] Idempotency/retry behavior is known
- [ ] Result receipt is shown

## Repair priority

1. Unify source and deployment.
2. Replace false reassurance with derived health.
3. Expose source timestamps and age.
4. Correct authoritative source selection and stage boundaries.
5. Repair scheduler, refresh, and timezone truth.
6. Add exception-first incidents and domain risk state.
7. Refine visual hierarchy after trust is established.