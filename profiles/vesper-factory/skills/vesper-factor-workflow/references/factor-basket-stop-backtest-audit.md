# Factor-to-Basket Audit for Historical Stop Backtests

Use this reference when translating Vesper's live factor/basket code into a historical stop-loss experiment. It records the durable audit method and the 2026-07-10 worktree findings; re-check source before relying on snapshot-specific details.

## Audit method

1. Record `git status`, HEAD, staged/unstaged diffs, and generated artifacts before interpreting "current" behavior. Dirty worktrees may combine several strategy generations.
2. Verify generated subprocess/source strings by rendering and parsing them, not merely parsing the parent file. A syntactically valid runner can emit invalid child code.
3. Compare every factor's live implementation with its historical validation implementation. Check formula, sign, window, missing-value handling, z-score `ddof`, and as-of behavior.
4. Prove point-in-time behavior: run the same factor with two distant `date_stamp` values and compare output hashes. Identical hashes usually mean the date argument is ignored.
5. Inspect SQL ordering. Any rolling calculation must explicitly `ORDER BY ticker, date`; observed SQLite index order is not a contract.
6. Expand the blend algebra. Ticker-specific available-factor denominators make scores incomparable when factor coverage differs. Historical tests should use complete cases for the frozen kernel.
7. Trace universe and sector provenance. A current constituent list backfilled through history is survivorship-biased; a current sector map is sector look-ahead.
8. Check split/corporate-action handling with known split dates. Raw split jumps invalidate returns, ATR, gaps, and stop touches.
9. Audit security identity across renames and ticker reuse. A ticker string is not a permanent security identifier: exclude unrelated historical users of a symbol, stitch only verified rename intervals, reject duplicate `(ticker, date)` rows after alias normalization, and fail closed if a held position lacks a price. Validate the equity curve for discontinuities around every alias transition (for example, FB to Meta Platforms' META on 2022-06-09 versus the unrelated older META ETF history).
10. Reconcile basket display weights with actual deployment code, cash reserve, execution timing, and rebalance cadence.
11. Freeze the no-stop baseline first, then apply stops with identical selections, costs, fills, and cooldown rules.

## Defensible reconstruction pattern

For the 2026-07-10 audit, the designated active, locally reconstructable kernel was:

- `intraday_range`: 21-day mean `(high-low)/close`, cross-sectional z-score.
- `size`: negative `log10` of 20-day mean dollar volume, cross-sectional z-score.
- `mean_reversion`: longest up-streak reversal + 10-day reversal + Bollinger position reversal + RSI reversal, then cross-sectional z-score.
- Complete-case composite: `(1.0*z_range + 0.5*z_size + 0.4*z_mean_reversion) / 1.9`.

Do not include sparse informational factors merely because the live runner gives them small weights. If their historical, publication-lag-correct data are unavailable, exclude them from both baseline and stop variants.

Basket logic was "top ticker within each sector, then winners from the four highest-scoring sectors." Call this four-sector diversification, not benchmark sector neutrality. Use point-in-time sectors, unrounded scores, and a deterministic ticker tie-break.

For live-faithful timing, compute from close `t` and execute at the next session open (a daily-bar approximation to the 09:35 order). Preserve the deployed cash reserve; in the audited rebalance code, 95% deployment across four names meant 23.75% per name, despite basket markdown showing 25%.

## Stop overlay specification

Pre-register one canonical design and treat conflicting documents as sensitivity variants:

- Fixed entry stop: ATR(14), `clamp(3*ATR/entry, 12%, 20%)`; 15% fallback.
- Gap below stop: fill at next open; otherwise daily-low touch fills at stop plus declared slippage.
- Day 15 close return `<= 0%`: exit next session open.
- Gap breaker: open `<= -8%` versus prior close.
- Intraday breaker: low reaches `-10%` versus prior close.
- Five-trading-day no-reentry cooldown; no trailing or portfolio-level drawdown stop.
- Process risk exits/cooldowns before target rebalance.

Always report a no-stop matched baseline and predeclared cost/parameter sensitivities. If point-in-time membership and adjusted OHLCV are unavailable, label the result a survivor-cohort diagnostic, not an unbiased S&P 500 backtest.

### Simulation and promotion invariants

Before accepting any result, exercise the portfolio simulator directly—not only factor, selection, and metric helpers—and require these properties:

- Seed the equity curve with initial capital before the first trade. Include first-session P&L and entry costs, then liquidate remaining holdings at the terminal close and include terminal costs/turnover. Terminal liquidation is not a risk-stop event.
- Enforce the maximum holding horizon in the portfolio simulator, not only the pure single-position model. Test the exact exit session and cooldown interaction.
- Keep campaign accounting synchronized with resizing. Additions must update the weighted cost basis and either maintain explicit lots or update the position-level fixed stop with a documented quantity-weighted rule; reductions must not silently reset age or basis.
- Never let absent signal data suppress risk processing. Choose and document one safe policy: Vesper's fail-closed historical pipeline aborts when an open campaign lacks the required score panel or market/prior-close data. Do not silently `continue` past a time-stop or horizon decision.
- Validate breaker ordering in configuration (`gap_threshold <= intraday_threshold`) so an open-through intraday threshold cannot receive an impossible favorable threshold fill.
- Promotion gates must validate required keys, finite values, and metric domains before comparisons. NaN comparisons otherwise fail open. If baseline turnover is zero and candidate turnover is positive, reject or apply an explicitly preregistered absolute rule—never report zero relative increase.
- A passing historical test can authorize only the next observational stage. Hard-code `deployment_approved = false`; full point-in-time provenance may yield `SHADOW_CANDIDATE`, while survivor/static-cohort evidence is capped at diagnostic or shadow-only status.
- Add regression tests for initial/terminal capital accounting, non-finite gate inputs, zero-baseline turnover, maximum horizon, cooldown boundaries, resizing basis/stop updates, missing prior closes/scores, and symbol transitions. Regenerate artifacts only after the final source edit and rerun the direct simulator tests.

## 2026-07-10 snapshot findings to re-check

- `run_all_factors.py` rendered escaped JSON keys into invalid child Python, so the current runner could not produce scores.
- Core factors ignored `date_stamp`; old and new requested dates produced identical hashes.
- Shared OHLCV fetches had no explicit ordering.
- The current 502-name S&P database was built by filtering all history to current constituents; earliest coverage had only 361 of them.
- The sector map was a current Wikipedia snapshot.
- Raw bars showed unadjusted split jumps (e.g. NVDA 2024 and AAPL 2020); available adjusted databases covered only 33 names.
- FM formulas differed from live formulas, omitted a cross-sectional intercept, zero-filled missing exposures, and used full-sample/current-universe information.
- Runner comments, status docs, and FM artifacts disagreed on t-statistics.
- The latest score artifact belonged to an older registry and did not represent the current intended kernel.
- Stop-loss material existed as design documentation only; no stop backtest implementation was present.
