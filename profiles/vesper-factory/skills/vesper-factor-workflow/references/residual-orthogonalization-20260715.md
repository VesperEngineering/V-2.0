# Residual Orthogonalization of Dead Factors

Phase 1 from the surviving-factor-construction research program: decompose each dead FM-failed factor (|t| < 1.5) into a component explained by survivors and an orthogonal residual, then test whether the residual has genuine predictive power.

## Purpose

A factor may fail FM not because its signal is worthless, but because it is colinear with the surviving factors. Removing that shared variance can reveal genuine alpha buried beneath noise.

## Implementation Pattern

### Script location
`scripts/residual_orthogonalization.py` — standalone report-only script. Reuses the exact same OHLCV panel loading, factor computation, and Newey-West infrastructure from `scripts/fama_macbeth.py`.

### Algorithm (per cross-section date)

1. Compute z-scores for all factors (survivors + dead) using the same `compute_factors()` / `compute_interaction_factors()` logic as FM
2. Build survivor design matrix with intercept: `X = [1, size, mean_reversion, intraday_range]`
3. For each dead factor `d`: OLS via `np.linalg.lstsq`:
   ```
   d_score = β₀ + β₁·size + β₂·mean_reversion + β₃·intraday_range + ε
   ```
4. Extract residual `ε`, z-score it cross-sectionally
5. Univariate FM: regress forward 21d returns on the residual z-scores across all dates
6. Compute Newey-West t-stat on the residual coefficient series

### OLS coefficients tracked per date

Per-date stats for each dead factor: `intercept`, `coef_size`, `coef_mean_reversion`, `coef_intraday_range`, `r2`, `n`. Aggregate cross-date averages for memo tables.

### Survivors (from FM 20260714)

| Factor | t-stat | Status |
|--------|--------|--------|
| size | +2.09 | SURVIVE |
| mean_reversion | +2.26 | SURVIVE |
| intraday_range | +1.81 | BORDERLINE |

## Known Results (2026-07-15)

Full results: `artifacts/evals/research_rez_orthogonalization_20260715.md`
JSON data: `artifacts/evals/orthogonalization_20260715.json`

### Key findings

| Factor | Original t | Residual t | Δt | R² with survivors |
|--------|-----------|-----------|-----|-------------------|
| range_vol_ratio | +1.43 | **+1.51** | +0.08 | 0.23 |
| amihud | −0.53 | **+1.42** | +1.95 | 0.23 |
| size_mkt_micro_int | +0.28 | +1.31 | +1.03 | 0.15 |
| sp500_technical | +0.89 | +1.05 | +0.16 | 0.09 |
| intraday_rng_massive_int | +1.45 | +0.86 | −0.59 | 0.47 |
| massive_intraday | +0.70 | +0.78 | +0.08 | 0.76 |
| max_return | −0.77 | −0.61 | +0.16 | 0.46 |

### Thresholds

- No dead factor recovered full significance (|t| > 2.0)
- range_vol_ratio crossed the 1.5 borderline threshold — the only one
- amihud showed the most dramatic improvement (sign flip, +1.95 Δt)
- massive_intraday is 76% explained by intraday_range alone — almost no orthogonal residual

## Key Pitfalls

1. **Interaction factors with a survivor parent get WORSE after orthogonalization.** `intraday_range_massive_interaction` dropped from t=1.45 to t=0.86 because intraday_range is one of the survivors and was the main source of the interaction's predictive power. Do not orthogonalize interaction factors where one parent is a survivor — the OLS strips away the signal.

2. **Factors nearly identical to a survivor have no residual alpha.** `massive_intraday` is 76% explained by `intraday_range` (β=+0.87). The residual is mostly noise. Skip orthogonalization for highly colinear factors (R² > 0.6 with survivors).

3. **Amihud proxy colinearity inflates the interaction-factor R².** Both `size_market_micro_interaction` and `size_insider_interaction` produce identical OLS stats (both use Amihud as proxy). Their R²=0.15 with survivors comes from the size component they share.

4. **Coefficients are not constant.** OLS coefficients vary across 169 dates (stddev ~0.05-0.08). A live pipeline needs rolling-window re-estimation, not fixed coefficients.

## Output Format

Research memo should include:

1. Executive summary with the bottom-line verdict (no factor recovered, or list of recoveries)
2. Methodology (approach, survivors, dead factors, source data)
3. Per-date OLS table (coefficients, R², interpretation)
4. FM-on-residuals table (original t | residual t | Δt | coefficient | % positive)
5. Factor-by-factor analysis with economic interpretation
6. Recommendations (weight promotion, monitoring, next steps)
7. Code changes needed if approved (new factor file, OLS strategy, registry, weights, FM script)
8. Broader implications

## Related References

- `references/surviving-factor-construction-research-20260714.md` — the research doc that motivated this work
- `scripts/residual_orthogonalization.py` — the implementation
- `artifacts/evals/orthogonalization_20260715.json` — structured results
- `artifacts/evals/research_rez_orthogonalization_20260715.md` — full research memo
- `artifacts/evals/research_rez_factor_mortality_20260715.md` — the mortality report that identified orthogonalization as next step