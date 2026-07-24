# Portfolio-rule ablation — 2026-07-22

**Scope:** no-submit ML-model backtests only. The model artifact, risk settings, broker behavior, and configuration were unchanged. Each run used the refreshed local OHLCV store through 2026-07-21, daily rebalance, and the existing 120-calendar-day runner window.

| Portfolio rules | Final equity | Return |
|---|---:|---:|
| top 10, exit rank 50 (configured baseline) | $93,843.78 | -6.16% |
| top 10, exit rank 10 | $96,009.85 | -3.99% |
| top 5, exit rank 10 | $94,366.94 | -5.63% |

**Result:** tighter exits materially reduced the loss, but no evaluated portfolio rule was profitable before costs. This is a retrospective diagnostic, not a fresh promotion holdout; it does not justify deployment or a production-parameter change.

Evidence logs:
- `reports/portfolio_ablation_top10_exit50.log`
- `reports/portfolio_ablation_top10_exit10.log`
- `reports/portfolio_ablation_top5_exit10.log`
