# Survivor-Cohort Stop Diagnostic Review — 2026-07-10

Use this dated reference when reviewing `position_risk_survivor_diagnostic` artifacts or similar daily-bar stop overlays. It records concrete defects and reusable audit probes; re-check current source and regenerate evidence after any fix.

## Decision framing

Separate two conclusions:

1. A flawed negative diagnostic may still justify an operational no-go (do not promote to shadow/paper/live).
2. It is not decision-grade evidence that the stop family is economically harmful, even for the survivor cohort, until source identity, execution mechanics, and artifact/source reproducibility pass.

Do not turn a no-go into a broad research rejection.

## Concrete defects found

### New-entry breaker can create an impossible profitable fill

The portfolio simulator selected and bought new names at the current open, then applied the intraday breaker using the prior close. If the open was already below the breaker threshold, it could buy below the threshold and sell at the higher threshold later in the same code path.

Synthetic reproduction: prior close 100, current open 85, low 80, breaker 90. The simulator bought at 85 and sold at 90, manufacturing +5.88% gross return. Read-only tracing found 12 such fills in `gap_only` and 11 in `combined` for the reviewed run.

Required invariant: for a newly entered position, no same-session stop fill may exceed entry price merely because the threshold was crossed before entry. Explicitly define whether to skip entry, exit at entry/open, or begin breaker monitoring only after entry; test that rule directly.

### GOOG/GOOGL identity and corporate action were not normalized

The supposedly split-adjusted panel showed GOOG adjusted close falling from 56.755 to 28.487 on 2014-04-03 (-49.8%) during the class-share distribution. Pre-event GOOG cannot be naively continued as post-event GOOG while GOOGL is introduced as another security. This contaminates returns, ATR, factor z-scores, and cross-sectional population even when GOOG is not held that day.

Required identity audit must cover more than FB/META:

- scan the largest absolute adjusted close-to-close returns after loader normalization;
- reconcile every known rename, ticker reuse, split, spin-off, and share-class transition with an effective-dated security map;
- verify that the normalized series reflects the economic entitlement across the event;
- assert uniqueness by security/date and inspect cross-sectional population changes around transitions.

A database column named `adjusted_*` does not prove adjustment completeness.

### Artifact/source drift obscured stop counts

The artifact counted mandatory horizon exits as `stop_events`, so baseline reported 547 stops despite having no optional stop controls. Source later distinguished horizon exits from actual risk-stop events. Economic metrics reproduced, but event counts did not represent re-entry churn cleanly.

Required artifact provenance:

- simulator and CLI hashes (or immutable commit plus clean-worktree proof);
- database and classification hashes;
- exact CLI arguments and cost assumption;
- separate counts for administrative horizon exits, optional risk exits, rebalance exits, and terminal liquidation;
- generation timestamp after the final source/test change.

If scoped source changes during review, timestamp the finding and require a fresh frozen rerun.

## Suspicious-metric checklist

- Convert cumulative turnover to annual one-way turnover. The reviewed baseline was about 1,554x cumulative / 68.5x per year; combined was about 80.9x per year.
- Run the single canonical all-in cost assumption before judging economics. Moving from 10 to 15 bps cut baseline total wealth from about 95.3x initial to 43.8x initial.
- Report max-drawdown peak and trough dates. In the reviewed run every variant's maximum drawdown began at the 2007-10-23 peak, so the gate was dominated by one GFC path.
- Reconcile apparently conflicting outcomes: gap/combined improved worst day and combined improved realized worst campaign loss, while Sharpe and drawdown worsened. Attribute whipsaw, cooldown, missed rebounds, and crisis exposure with a trade ledger.
- Distinguish realized campaign loss from maximum adverse excursion; include costs consistently.
- Report actual daily eligible-universe size and sector count, not only union cohort size. The reviewed score universe varied from 16 to 21 to 20 names and covered only seven sectors.
- Count selection concentration by ticker and economic issuer. Separate GOOG/GOOGL rows can double-represent Alphabet in cross-sectional normalization even when sector selection allows only one class.
- Scan portfolio return tails and normalized security return tails after every run.
- Include paired daily-return deltas, fixed subperiod attribution, risk-exit frequency, and cooldown/re-entry churn. Aggregate Sharpe/DD alone are insufficient.

## Bounded non-mining follow-up

The next experiment should be one code-frozen audit replication, not a stop-parameter sweep:

1. Correct only proven mechanical/data defects (entry/breaker ordering and effective-dated corporate-action identity).
2. Freeze the existing stop distances, horizons, cooldown, variants, and economic gate.
3. Use one preregistered canonical all-in cost (15 bps in the reviewed source); do not grid-search costs or thresholds.
4. Emit source hashes, trade/event ledger, equity curves, maximum adverse excursion, and explicit zero-impossible-fill assertions.
5. Predeclare interpretation: if all variants still fail, reject that canonical fixed-stop specification for this cohort and do not tune nearby values. A pass can only nominate a separate point-in-time replication.

## Useful read-only probes

- Recompute metrics in memory rather than writing a replacement artifact.
- Use a tiny synthetic two-session fixture to prove entry/fill ordering.
- Instrument the running function in memory (for example, tracing the intraday-exit line) to count threshold fills above same-day entry without editing source.
- Query OHLC ordering invariants, then separately scan adjusted close-return extremes; valid OHLC ordering does not catch identity/corporate-action discontinuities.
- Re-run the focused tests after observing final source state, but verify that tests explicitly cover the defects above rather than relying only on a green count.
