# Fama-MacBeth Regression Results (2026-07-14)

**Script**: `scripts/fama_macbeth.py`
**Data**: Split-adjusted OHLCV (via `fetch_adjusted_ohlcv_rows` pattern from `app/factors/db.py`)
**Method**: Two-pass cross-sectional regression with Newey-West standard errors (4 lags)
**Period**: 2004-01-01 to 2026-07-13, 21d forward horizon, 21d rebalance step, 169 steps
**Factors tested**: 11 factors (7 OHLCV-based + 3 interaction + 1 proxy)

## Results

| Factor | Coefficient | NW t-stat | % Positive | Significant? | N |
|--------|------------|-----------|-----------|-------------|---|
| **mean_reversion** | +0.0014 | **+2.26** | 54% | YES | 169 |
| **size** | +0.0025 | **+2.09** | 62% | YES | 169 |
| intraday_range | +0.0034 | +1.81 | 51% | BORDER | 169 |
| intraday_range_massive_interaction | +0.0055 | +1.45 | 51% | no | 169 |
| range_vol_ratio | +0.0195 | +1.43 | 57% | no | 169 |
| sp500_technical | +0.0009 | +0.89 | 59% | no | 169 |
| max_return | -0.0019 | -0.77 | 53% | no | 169 |
| massive_intraday | +0.0007 | +0.70 | 50% | no | 169 |
| amihud | -0.0292 | -0.53 | 49% | no | 169 |
| size_market_micro_interaction | +0.0074 | +0.28 | 52% | no | 169 |
| size_insider_interaction | +0.0074 | +0.28 | 52% | no | 169 |

## Key Changes from Prior FM (2026-07-07)

| Factor | Old t (raw) | New t (split-adj) | Change |
|--------|------------|-------------------|--------|
| intraday_range | **+4.10** | +1.81 | Dropped from strong to borderline |
| size | **-2.43** | +2.09 | Sign flipped, still significant |
| mean_reversion | +1.86 | **+2.26** | Crossed significance threshold |
| sp500_technical | +1.72 | +0.89 | Weakened |
| amihud | +0.58 | -0.53 | Weakened |
| massive | -1.70 | +0.70 (massive_intraday) | Replaced with composite |

**Three new interaction factors all failed** (|t| < 1.5). The Borri et al. (2025) pairwise interaction effect was not replicated in this inline FM test.

## Key Findings

- **mean_reversion is now the strongest factor** (t=+2.26). It was borderline in the old FM. Split-adjusted data and 11-factor controls improved its standing.
- **size remains significant** but flipped sign (from t=-2.43 to t=+2.09). The old FM used raw `log10(dollar_volume)` while the new FM uses the SizeFactor convention of `-log10(avg_dollar_volume)` over 20 days. The negated form plus split-adjusted prices produces the sign reversal.
- **intraday_range dropped sharply** from t=+4.10 to +1.81. Split-adjusted prices and 9 additional control factors (including range_vol_ratio and massive_intraday which share similar range-based signals) absorbed its predictive power.
- **All 3 interaction factors failed** — pairwise products of z-scored factors did not produce priced non-linear effects in this test.
- **Mean cross-sectional R² = -0.10.** Noise dominates — expected for factor models.
- **2 of 11 factors are statistically significant** (|t| > 2.0). This is consistent with the historical pattern where ~80% of factors fail FM.

## FM vs Optimizer vs IC Analysis

| Method | Best factors | Limitation |
|--------|------------|-----------|
| Rank IC | sp500_technical, amihud | Doesn't control for multicollinearity |
| Optimizer | intraday_range, sp500_technical, mean_reversion | Inflated Sharpe (0.93 vs actual 0.57) |
| **Fama-MacBeth** | **size, mean_reversion** | **Gold standard** — heteroskedasticity- and autocorrelation-robust |

## When to Run

Run `python scripts/fama_macbeth.py` after ANY factor change. It's the final arbiter of statistical significance. If a factor has |t| < 2.0 and the optimizer says it helps, trust FM — drop the factor.

On a 502t × 5666d panel (split-adjusted), the script completes in ~17s.

## Split-Adjustment in FM

The FM script loads `split_adjustments.json` from `vesper_data/split_adjustments.json` and applies cumulative forward factors to all price columns (open, high, low, close) before computing any factor signals. This is critical because:

- **Dollar volume changes** with split adjustment — a 2:1 split halves the price and changes volume counts, altering dollar-volume-based signals (size, amihud, range_vol_ratio)
- **Range-based signals shift** — splits compress high-low ranges proportionally, so raw ranges are comparable across time only after adjustment
- **Return-based signals are unaffected** — returns are ratio-based and split-invariant, but factors that mix returns with prices (e.g., amihud = abs(ret)/dvol) are affected

The `_SPLIT_ADJ_CACHE` pattern uses a module-level global variable (not `Path._cache`) because Python 3.11+ `Path` objects don't support arbitrary attribute assignment.

## SEC Insider Data Limitation

The `sec_insider_v2` factor has no historical record — `sec_insider_v2_scores.json` covers only the current lookback window. For `size_insider_interaction` in the FM, the Amihud proxy from the S&P 500 OHLCV panel is used as a fallback. This means the FM result for `size_insider_interaction` is identical to `size_market_micro_interaction` and does not capture any insider-trading-specific effect.

## Optimizer Inflation Pitfall

The factor optimizer (`scripts/factor_optimizer.py`) inflated Sharpe by z-scoring sub-signals within each backtest step (a form of look-ahead bias). The actual backtest produced Sharpe 0.57 for the 3-factor kernel, not 0.93. Never report optimizer Sharpe numbers without comparing against the actual backtest. The optimizer is useful for RANKING factors but NOT for absolute Sharpe estimates.