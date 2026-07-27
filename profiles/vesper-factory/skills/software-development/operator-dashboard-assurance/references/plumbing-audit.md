# Plumbing Audit Reference

## Evidence map

For each displayed field, record:

| Displayed field | Authoritative source | Observed at | Payload generated at | Transformation | Fallback | Consumer |
|---|---|---|---|---|---|---|

A field is not trustworthy until all columns are known.

## High-value failure patterns

### Shadow deployment

The repository is edited and tested, but the live URL serves a copied directory or different frontend. Determine the process and serving root before editing. Unify to one source and verify the URL after restart.

### False freshness

A counter such as “updated 10s ago” measures the last browser fetch while the payload was generated hours ago. Compute payload age from `generated_at`; preserve distinct source timestamps for scores, broker data, and market data.

### Hardcoded reassurance

`HEALTHY`, `Connected`, or `live` is constant or based only on HTTP success. Derive an overall state from required components and include machine-readable reasons. Missing scheduler heartbeat, empty execution artifacts, or stale required inputs must fail closed.

### Basket/state conflation

Raw top scores, approved execution basket, and broker holdings are displayed as if they are one object. Keep all three separate. The approved basket must come from the same canonical artifact consumed by the rebalance/execution code.

### Scheduler ambiguity

Multiple schedulers, backup tasks, or logfile stores disagree. Choose one authority and expose heartbeat plus per-job evidence. Validate standard cron Sunday-zero semantics; Python `datetime.weekday()` uses Monday-zero and requires conversion.

### Live endpoint that is actually cached or empty

Require response fields for source, observation timestamp, error state, and consistent counts. A failed live fetch may show a snapshot only if the fallback is labeled explicitly.

### Browser transition bug

Refresh policy is selected only at page initialization. A page opened pre-market may remain on the pre-market cadence after market open. Re-evaluate policy on state transitions and clear every prior timer before creating replacements.

## Regression targets

- Canonical execution artifact parser preserves ticker, sector, score, weight, date, source, and path.
- Real factor contributions survive aggregation; top factor is calculated from actual numeric details.
- Stale/missing scheduler heartbeat cannot yield green health.
- API status reports payload age and derived reasons.
- Standard cron `1-5` matches Monday-Friday and rejects Saturday.
- Live account contract includes explicit source, UTC timestamp, and consistent position count.
- Payload writer writes only to the requested authoritative deployment path.
- Browser header age is based on payload generation time, not fetch time.

## Verification ladder

1. Focused regression tests pass.
2. Adjacent targeted suites pass.
3. Full suite passes or baseline differences are documented.
4. Server starts from repository source.
5. HTTP responses confirm source, freshness, and health contracts.
6. Browser confirms the same values without console errors.
7. Process/launcher inspection confirms restart durability.

Do not skip steps 4–7 when claiming that an operator dashboard is trustworthy.
