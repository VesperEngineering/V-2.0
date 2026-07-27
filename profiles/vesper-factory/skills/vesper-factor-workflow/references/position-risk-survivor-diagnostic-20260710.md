# Position-Risk Survivor-Cohort Diagnostic — 2026-07-10

Use this as a dated diagnostic record, not a deployment gate. Re-run against current source and data before relying on the metrics.

## Scope and authority

- Report-only and broker-free: no account, order, scheduler, network, promotion, or live-trading authority.
- Data: 21 sector-covered names from the active-universe adjusted store, 2003-09-10 through 2026-06-30.
- Biases: current constituent survivor cohort and current sector labels; no point-in-time membership or sectors.
- Strongest possible status: diagnostic/shadow-only. `deployment_approved` must remain false.

## Durable implementation corrections

Before trusting a stop diagnostic:

1. Use split-adjusted `adjusted_open/high/low/close` for executable stop levels and fills. Do not use total-return-adjusted OHLC for stop touches.
2. Use the frozen population standard deviation (`ddof=0`) for cross-sectional factor z-scores when the recipe specifies population z-scores.
3. Include the established one-way cost assumption: 10 bps commission plus 5 bps slippage = 15 bps. Also run a zero-cost sanity comparison to distinguish economic failure from cost drag.
4. Count actual ATR/gap/intraday/time risk exits separately from maximum-horizon exits. A baseline with only horizon exits must report zero stop events.
5. Seed initial equity, charge first entry and terminal liquidation costs, update campaign basis and fixed stops after additions, and fail closed on missing held prices, prior closes, or signal panels.
6. Validate policy relationships at configuration admission: positive finite equity, deployment in `(0,1]`, non-negative finite costs, coherent stop bounds and horizons, non-negative cooldown, and gap threshold no looser than the intraday threshold.
7. Store source hashes, price-basis labels, provenance flags, and explicit non-deployment language in the receipt.

## Independent-audit invalidation

The first artifact and its provisional gap/intraday interpretation were invalidated after an independent three-agent review found:

- impossible same-day fills that bought below an already-breached threshold and sold above the market;
- score-order-dependent cash allocation from additions preceding later reductions;
- fixed campaign stops widening after additions;
- 21-session rather than 60-session score admission in the consumed panel;
- omitted flat warm-up sessions and non-finite short-series volatility;
- a GOOG/GOOGL 2014 class-split identity discontinuity;
- omitted dividend return despite a materially different total-return series;
- no implementation hashes tying the artifact to changing untracked source.

A conservative operational no-go survived, but the earlier metrics were not decision-grade and must not be cited.

## Code-hashed repaired rerun awaiting independent verification

The frozen 15-bps rerun repaired the defects above, used split-adjusted executable OHLC plus total-return-reconciled cash dividends, normalized the Google class split, and persisted simulator/runner/design/data identities.

| Variant | Sharpe | Max DD | Worst day | Risk exits | Gate |
|---|---:|---:|---:|---:|---|
| Baseline | 0.67 | -54.7% | -12.7% | 0 | baseline |
| ATR only | 0.63 | -70.4% | -13.0% | 256 | rejected |
| Opening-gap only | 0.72 | -56.4% | -11.3% | 75 | rejected |
| Intraday only | 0.62 | -57.1% | -11.3% | 168 | rejected |
| Gap + intraday | 0.61 | -60.2% | -11.1% | 211 | rejected |
| Time only | 0.67 | -55.3% | -12.4% | 404 | rejected |
| Combined | 0.54 | -63.0% | -11.1% | 596 | rejected |

The repaired selected-position gap study recorded 211 events, a five-session median rebound of about +1.3%, and a 54.5% positive rate. This supports whipsaw as a mechanism, but remains survivor-cohort evidence.

## Interpretation

- Every frozen overlay still fails the maximum-drawdown gate. Do not tune neighboring thresholds after this result.
- Opening-gap-only has slightly higher Sharpe than baseline but worsens drawdown; it is not promotable.
- The earlier apparent intraday-only benefit disappeared after mechanical and accounting repairs.
- The result still cannot establish an unbiased S&P 500 conclusion because membership and sectors are current/static.
- The artifact status is `REPAIRED_RERUN_AWAITING_INDEPENDENT_REVIEW`. Do not call the issue verified closed or the canonical specification definitively rejected until a fresh reviewer verifies the exact persisted hashes and original impossible-fill reproduction.

## Verification snapshot

The repaired focused suite reported 56 passing tests; Python compilation, focused diff checks, GOOG/GOOGL duplicate checks, and persisted source-hash readback passed. These are author-side checks, not independent closure.