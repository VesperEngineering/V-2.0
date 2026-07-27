# Position-Risk Backtest Accounting and Campaign Invariants

Use this reference when a daily-rebalance portfolio backtest overlays per-position stops, time exits, cooldowns, or holding horizons.

## Equity-Curve Accounting

A return series must include the capital state before the first executable trade.

- Seed the equity curve with `initial_equity` on the pre-trade/session-zero date.
- Record entry transaction costs in the first post-trade equity point.
- At the end of the requested window, liquidate remaining positions at the declared terminal price and charge exit costs.
- Replace the final marked-to-market point with post-liquidation cash so total return includes terminal costs.
- Exclude administrative terminal liquidation from risk-stop counts, but include its turnover and costs.

Without the initial point, the first entry cost disappears from `pct_change`; without terminal liquidation, variants with different ending holdings are not cost-comparable.

## Campaign State Under Daily Resizing

A daily target-weight rebalance can add to an already-open campaign. Do not leave campaign state frozen at the first fill.

For an addition:

- update weighted cost basis using old quantity/basis and added quantity/fill price;
- update the effective fixed stop consistently (weighted existing stop and the new lot's pre-registered stop is a conservative position-level approximation; separate lots are more exact);
- preserve the original campaign start index if the holding horizon applies to the continuous campaign;
- do not change average basis on a partial reduction.

Use the updated basis for time-stop return and realized/worst-position loss. Do not use a stale first-fill price after resizing.

## Session and Horizon Invariants

- Encode the maximum holding horizon explicitly in configuration and test the exact exit session.
- Exact-day time stops are safe only when every held-position session is processed.
- Never silently `continue` past a session while positions are open because scores, bars, or prior closes are missing.
- Either process risk and mark-to-market without rebalancing, or fail closed with a typed data error. Vesper's diagnostic currently chooses fail-closed behavior for missing score panels while holding.
- Missing current held prices and missing prior closes must fail closed; substituting the current open for an unavailable prior close changes gap semantics.
- Apply cooldown from the actual exit index and test the first eligible re-entry index.

## Configuration Admission

Validate policy relationships before simulation, not inside individual branches. At minimum:

- positive finite initial equity;
- deployment fraction in the admitted range;
- non-negative finite costs;
- valid stop-distance ordering;
- positive time and maximum-holding horizons with coherent ordering;
- non-negative cooldown;
- overnight gap threshold no looser than the intraday breaker threshold.

## Promotion-Gate Numerics

Promotion logic must fail closed on non-finite baseline or candidate metrics. Ratio gates need explicit zero-denominator behavior: positive candidate turnover against a zero-turnover baseline is a failure, not an undefined ratio that bypasses the gate.

## Simulator Integrity Invariants Learned from Independent Audit

A portfolio-level risk simulator needs tests beyond the pure single-position model:

- **Never sell a new entry above the market.** If a candidate opens through an enabled gap/intraday threshold, reject the entry before rebalancing. Defensively, use the open when `open <= trigger`; only a later low-touch may fill at the trigger. Exercise this through the portfolio simulator, not just a pure stop helper.
- **Rebalance reductions before additions.** A one-pass score-ordered loop makes exposure and returns depend on ranking order because early additions can consume cash before later trims. Build target quantities, execute exits/reductions, then additions. Test that score swaps which preserve equal-weight membership leave results unchanged.
- **A fixed campaign stop may tighten but never widen.** After adding shares, compute the documented blended candidate stop and retain `max(existing_stop, blended_stop)` for a long position.
- **Apply the real warm-up rule in the consumed score path.** Testing a helper's 60-session gate is insufficient if the portfolio consumes another panel builder. Assert the first eligible date directly on the consumed panel.
- **Keep flat warm-up sessions in the equity curve.** Record unchanged cash for every requested session before the first signal so annualization and risk statistics use real elapsed sessions.
- **Separate executable prices from return accounting.** Use split-adjusted OHLC for entries, exits, ATR, gaps, and stop touches. Reconcile the total-return series into per-share cash dividends for overnight holders; do not value new shares at an absolute cumulative total-return price.
- **Corporate actions are identity events, not only scale factors.** For the 2014 Google class split, pre-split GOOG belongs to the post-split GOOGL lineage and needs the split scale applied before stitching; post-split GOOG begins a separate class. Assert unique ticker/date rows and inspect extreme returns after normalization.
- **Validate OHLC ordering and short metric series.** Fail closed unless `low <= open/close <= high`; return finite volatility for a single-return series.
- **Hash the implementation that generated evidence.** Persist simulator, runner, design, database, sector-map, and alias-policy identities. Mark regenerated evidence as awaiting independent review when audited files changed after review dispatch.

If any of these defects is found, invalidate prior economic interpretations immediately. A conservative no-go may remain operationally safe, but it is not a decision-grade rejection until the exact frozen rerun is independently verified.

## Regression Sequence

Build one vertical TDD slice at a time:

1. initial-equity/entry-cost accounting;
2. terminal liquidation and costs;
3. maximum holding horizon;
4. weighted campaign basis and non-widening fixed stop after additions;
5. impossible new-entry breaker fill and gap-through-open handling;
6. score-order-invariant two-pass rebalancing;
7. consumed-path warm-up eligibility and flat-session accounting;
8. executable-price versus dividend/total-return accounting;
9. effective-dated corporate-action identity and duplicate checks;
10. missing-score/bar/prior-close failures and OHLC integrity;
11. threshold-order validation;
12. non-finite, short-series, and zero-baseline promotion gates;
13. implementation/source hash verification on the generated artifact.

Run each new test RED, implement the minimum fix, run it GREEN, then run the complete position-risk test group. Re-run and replace historical diagnostic artifacts after accounting or horizon semantics change; old metrics are invalid even if the CLI still exits successfully.
