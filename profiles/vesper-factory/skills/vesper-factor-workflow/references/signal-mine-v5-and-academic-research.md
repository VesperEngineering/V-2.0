# Signal Mine v5 + Academic Research (2026-07-09)

## Signal Mine v5 — 25 Candidate IC Scan

Script: `scripts/signal_mine_v5.py`
Method: Cross-sectional Spearman IC, 1117 rebalance steps, 2004-2026, 21d horizon, 502 tickers.

### Top Signals by Solo IC

| Signal | IC mean | IC IR | t-stat | %Pos | Built as Factor? |
|---|---|---|---|---|---|
| range_vol_ratio | +0.0293 | **+0.294** | +9.81 | 64% | Yes -> FM failed (t=+1.04) |
| vol_concentration | +0.0139 | +0.180 | +6.02 | 57% | No (likely correlated with size) |
| max_drawdown_20 | -0.0238 | -0.150 | -5.02 | 44% | No (likely correlated with mean_reversion) |
| ret_range_20 | +0.0279 | +0.143 | +4.78 | 56% | No (likely correlated with intraday_range) |
| close_location | -0.0112 | -0.093 | -3.11 | 48% | No |
| range_skew | +0.0112 | +0.093 | +3.11 | 52% | No (mirror of close_location) |
| overnight_return | -0.0087 | -0.071 | -2.37 | 50% | No |
| extreme_return_count | +0.0041 | +0.070 | +2.36 | 53% | No |
| ret_kurt_20 | +0.0052 | +0.070 | +2.35 | 53% | No |
| abnormal_vol | -0.0043 | -0.060 | -2.02 | 47% | No |
| vol_weighted_ret | -0.0079 | -0.060 | -2.01 | 50% | No |
| zero_return_days | -0.0031 | -0.060 | -2.00 | 49% | No |
| vol_trend | -0.0042 | -0.060 | -1.99 | 47% | No |
| closing_strength | -0.0060 | -0.057 | -1.91 | 50% | No |

### Signals below significance (|t| < 1.9)
gap_reversal, gap_skew, price_persistence, ret_autocorr_1, up_dn_vol_ratio,
overnight_intraday_ratio, ret_autocorr_5, vol_ratio_5_20, price_accel, ret_skew_20

### Key Finding

range_vol_ratio had IC IR 0.294 — the strongest solo signal ever found in Vesper — and still failed FM (t=+1.04). This confirms that solo IC, no matter how strong, does not predict FM survival. The top candidates (vol_concentration, max_drawdown_20, ret_range_20) are likely correlated with existing validated factors (size, mean_reversion, intraday_range) and would probably also fail FM.

## Academic Literature Research (Subagent)

### Top Academic Signals (with published evidence)

1. **MAX** (Bali et al. 2011, JFE) — t=-5.30 to -6.22. Max daily return over 21d.
   - Built as `max_return` factor -> FM t=-1.07 -> FAILED
   - Captures lottery/skewness preference, not volatility
2. **AB_NR** (Akbas et al. 2022) — t~3.5-4.0. Overnight positive / intraday reversal frequency.
   - NOT built (complex pattern detection, lower priority)
3. **Overnight return** (Lou et al. 2019) — signed cumulative level.
   - Mined: IC IR -0.071, t=-2.37. Below FM threshold.
4. **Return skewness** (Harvey & Siddique 2000) — third moment.
   - Mined: IC IR +0.042, t=+1.39. Below significance.
5. **VCV** (Lof & van Bommel 2023) — std(vol)/mean(vol).
   - Related to neg_vol_cv which we mined: IC IR -0.180, t=-6.02. Strong solo but likely correlated with size.
6. **Zero-return days** (Lesmond et al. 1999) — stale pricing proxy.
   - Mined: IC IR -0.060, t=-2.00. Borderline solo.
7. **Up/down volume ratio** (LMSW 2002) — directional volume asymmetry.
   - Mined: IC IR +0.002, t=+0.07. Pure noise.

### Academic vs Empirical Crossover

| Academic Signal | Mined? | Solo IC IR | FM Result |
|---|---|---|---|
| MAX | Built directly | — | t=-1.07 FAILED |
| Overnight return | Yes | -0.071 | Not tested (below solo threshold) |
| Return skewness | Yes | +0.042 | Not tested (below solo threshold) |
| Zero-return days | Yes | -0.060 | Not tested (below solo threshold) |
| Vol CV (= VCV) | Yes (neg_vol_cv) | -0.180 | Not tested (correlated with size) |

### Lesson

Academic papers report univariate or bivariate results. FM is multivariate. A signal that's significant in a univariate academic test can be completely subsumed by existing factors. The academic literature is a source of IDEAS, not validation. FM is the only validation that matters for Vesper.

## Remaining Unbuilt Academic Candidates

If we exhaust OHLCV-only signals and want to try more:

1. **AB_NR** (Akbas 2022) — overnight positive / intraday reversal frequency. Complex but academically strong (t~3.5-4.0). Would need intraday open/close pattern detection.
2. **Hurst exponent** — long-memory parameter. Different mathematical framework (rescaled range analysis). Not yet mined.
3. **Compound signals** — the mine tested linear signals. Nonlinear transformations (threshold effects, regime conditioning) might find edge that linear IC misses. But this risks overfitting.
