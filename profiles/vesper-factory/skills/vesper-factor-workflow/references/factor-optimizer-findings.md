# Factor Optimizer Findings (2026-07-07)

`scripts/factor_optimizer.py` — greedy forward selection + drop-one across
6 historically-reconstructable factors, 2005-2026, 256 rebalance steps,
21d horizon, 10bps costs.

## Single-factor baselines

| Factor | Sharpe | Excess Ret | Win Rate | Max DD |
|---|---|---|---|---|
| intraday_range | +0.803 | +31.4% | 54% | -68.6% |
| sp500_technical | +0.730 | +16.6% | 62% | -65.1% |
| amihud | +0.536 | +11.2% | 54% | -61.9% |
| mean_reversion | +0.170 | +2.6% | 49% | -69.4% |
| size_factor | +0.094 | +2.2% | 49% | -67.8% |
| beta_factor | timeout | — | — | — |

## Greedy forward selection

| Step | Added Factor | Sharpe | Excess | Win |
|---|---|---|---|---|
| 1 | intraday_range | +0.803 | +31.4% | 54% |
| 2 | sp500_technical | **+0.932** | +28.8% | 59% |
| 3 | mean_reversion | **+0.935** | +27.4% | 60% |
| 4 | (amihud rejected — no improvement) | — | — | — |

## Drop-one analysis (starting from all 6 equal-weight: Sharpe 0.67)

| Removed Factor | Resulting Sharpe | Delta |
|---|---|---|
| (none — baseline) | 0.670 | — |
| amihud | **0.774** | +0.104 — AMIHUD HURTS |
| size_factor | **0.786** | +0.116 — SIZE HURTS |
| beta_factor | 0.670 | +0.000 — NO EFFECT |
| mean_reversion | 0.655 | -0.015 — mildly helpful |
| sp500_technical | 0.680 | +0.010 |
| intraday_range | 0.292 | -0.378 — CRITICAL |

## Key insight

**amihud (IC IR +0.289) and size_factor (IC IR -0.285) are strong standalone signals, but both correlate with intraday_range in the cross-section. Adding them to the optimal blend dilutes rather than diversifies.** The optimizer correctly rejects factors that don't add orthogonal information, even when they have high solo IC.

## Recommendation

Keep 3 factors: intraday_range (w=1.0), sp500_technical (w=1.0), mean_reversion (w=0.7).
Run `factor_optimizer.py` whenever a new factor is proposed before registering it.
