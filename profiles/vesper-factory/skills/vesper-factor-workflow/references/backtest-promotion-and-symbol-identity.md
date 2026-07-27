# Backtest Promotion Gates and Symbol-Identity Safety

Use this reference when a historical strategy or risk-control backtest is intended to influence deployment.

## Promotion Ladder

A backtest is necessary but never sufficient for live deployment:

1. **Unit tests** prove mechanics and edge-case behavior.
2. **Historical diagnostic** can reject an idea or nominate it for further evaluation.
3. **Report-only shadow mode** computes hypothetical actions but cannot place orders.
4. **Paper execution** validates broker behavior, ordering, partial fills, reconciliation, and recovery.
5. **Small live allocation** requires both economic and operational evidence.

Encode the maximum allowed stage in the result artifact. A historical run must always report `deployment_approved: false`; live authorization belongs to a separate, explicit governance action.

## Pre-register the Gate

Freeze thresholds before observing candidate results. At minimum compare candidate versus the identical no-overlay baseline on:

- out-of-sample Sharpe degradation;
- relative maximum-drawdown improvement;
- worst-day and worst-position loss;
- turnover and estimated costs;
- stop frequency and re-entry churn.

Do not tune stop distances or acceptance thresholds after seeing the first result. Failed variants remain failed unless a source-level implementation or data defect invalidates the run.

## Data Quality Caps the Conclusion

Split-adjusted prices alone are insufficient. A deployment-grade historical result also requires:

- point-in-time membership;
- point-in-time sectors/classifications;
- enforced signal cutoff;
- next-session execution for close-derived signals;
- deterministic selection and tie-breaking;
- complete held-position valuation on every session.

A current-constituent survivor cohort may reject a policy and may, at most, nominate it for report-only shadowing. Label it explicitly; never call it an unbiased index backtest.

## Symbol Identity Is Not Just a String

Ticker reuse and renames can silently create impossible returns. A concrete failure mode occurred around the Facebook rename:

- Facebook used `FB` through 2022-06-08 and `META` from 2022-06-09.
- An unrelated ETF had previously used `META`.
- Naively grouping on ticker created an internal gap and stale shares; dropping the missing holding from equity and later restoring it produced a fake +618% portfolio day.

Safe procedure:

1. Maintain an effective-dated security-identity map, not a global string replacement.
2. Exclude rows belonging to an unrelated prior security before stitching a rename.
3. Resolve transition-date duplicates deterministically using source identity/provenance—not `drop_duplicates(keep='last')` without evidence.
4. Assert uniqueness on `(security_id, date)` after normalization.
5. If any held security lacks an admitted bar, fail closed. Never omit it from portfolio equity.
6. Scan the largest positive and negative daily portfolio returns after every run. Investigate implausible jumps before evaluating economics.
7. Add a regression fixture spanning every normalized rename and prove equity continuity across the effective date.

## Required Artifact Fields

Persist enough evidence to reproduce and audit the decision:

- source paths and checksums;
- data date range, row count, and security count;
- provenance booleans for adjustment, membership, sectors, and cutoff;
- exact risk and cost configuration;
- baseline and fixed-variant metrics;
- stop reason counts;
- pre-registered gate thresholds and failures;
- limitations and maximum promotion stage;
- `broker_access: false` for historical and shadow diagnostics.

A green process only proves the program exited. Inspect return tails, continuity, source coverage, and the resulting artifact before accepting the run.
