# IC Horizon Sweep Findings (2026-07-07)

## Source
`ic_horizon_sweep.py` — one-shot diagnostic, 5741 trading dates (2003-2026), 502 tickers. Tests intraday_range proxy (high-low/close) at 14 horizons from 1d to 200d.

## Results

| Horizon | IC IR | % Pos | Verdict |
|---|---|---|---|
| 1d | +0.022 | 52% | Noise |
| 5d | +0.037 | 56% | Emerging |
| 10d | +0.072 | 51% | Weak |
| 21d | +0.123 | 54% | Minimum viable |
| 30d | +0.145 | 59% | Solid |
| 50d | +0.211 | 59% | Strong |
| 63d | +0.251 | 60% | Strong |
| 90d | +0.298 | 65% | Very strong |
| **126d** | **+0.347** | **64%** | **Peak** |
| 200d | +0.347 | 63% | Plateau |

## Short-Horizon Sweep (per-factor)

| Horizon | intraday_range | mean_reversion | 12-1 momentum |
|---|---|---|---|
| 1d | -0.046 | +0.016 | +0.035 |
| 2d | +0.021 | +0.016 | +0.008 |
| 3d | +0.042 | +0.076 | -0.033 |
| 5d | +0.032 | +0.057 | +0.030 |
| 7d | +0.037 | +0.093 | +0.096 |
| 10d | +0.006 | +0.080 | +0.121 |
| 14d | +0.053 | +0.096 | +0.089 |
| 21d | +0.100 | +0.051 | +0.065 |

## Key Takeaways

1. **intraday_range signal peaks at 126d (4-6 months).** 21d captures ~35% of available alpha.
2. **mean_reversion is the only short-horizon signal** — peaks at 7-14d (IR +0.09). Does NOT work at 1d.
3. **12-1 momentum works at 10-21d** — classic momentum, not intraday.
4. **No 1d signal exists in our factor set.** All factors need 3+ days to show predictive power. Rentec-style intraday signals require completely different data (order book, tick-level, options flow).
5. **21d is optimal for learning velocity** — 12 observations/year vs 4 at 63d. Keep 21d for now.
6. **If Sharpe plateaus, extend to 63d** — captures more alpha with less turnover.

## Signal Mine v3 — Multi-Horizon Blends (2026-07-08)

9 new signals tested + multi-horizon blends. Source: `scripts/signal_mine_v3.py` (502 tickers, 233 rebalance steps, 21d horizon).

### New Signals
| Signal | IC IR | Verdict |
|---|---|---|
| rev_10d (10d reversal) | **+0.170** | **Strongest single signal found** |
| rev_20d | +0.146 | Very strong |
| mean_rev_7d | +0.101 | Solid |
| intraday_range | +0.100 | Baseline |
| vol_price_corr | -0.063 | Weak |
| rev_3d | +0.024 | Noise |
| ar1_coef | -0.031 | Noise |
| dispersion | NaN | Noise |
| tail_risk | NaN | Noise |

### Multi-Horizon Blends (21d forward)
| Blend | IC IR | vs Baseline |
|---|---|---|
| blend_21d+10d (intraday_range + rev_10d) | **+0.165** | +65% gain |
| blend_21d+7d | +0.135 | +35% gain |
| blend_21d+3d | +0.078 | -22% (dilutes) |

### Actionable
- **10d reversal is the best single signal ever found.** mean_reversion factor should weight 10d as primary, not 5d.
- **blend_21d+10d** is the optimal 2-factor combo.
- 3d reversal dilutes. 7d is additive but weaker than 10d.
- All microstructure signals (AR(1), volume-price correlation, dispersion, tail risk) are noise.

The live IC tracker uses 21d forward horizon (switched from 1d, 2026-07-07). 1d was too noisy — even validated signals looked like noise. The tracker needs ~10 observations before IC IR stabilizes at 21d, and ~30 for a reliable reading. First reading expected ~Aug 5, 2026 (21 trading days from first July 6 snapshot). Reliable by mid-September.
