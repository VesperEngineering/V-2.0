# Walk-Forward Backtest v1.0

Script: `scripts/vesper_backtest.py`
Output: `artifacts/evals/vesper_backtest_v1.json`

## Methodology
- **Universe**: 21 large-cap equities (AAPL, MSFT, GOOGL, ..., XOM)
- **Factors**: entropy + hurst + realized_vol (same as technical factor)
- **Scoring**: z-score sum of all 3 features, pick top 5
- **Horizon**: 5 trading days forward return
- **Baseline**: equal-weight average of all universe tickers
- **Sampling**: ~every 42 trading days (49 samples over 2018-2026)
- **OHLCV data**: From `artifacts/db/sqlite-analyst.db` via `_load_ohlcv()`
- **Price data**: Uses daily close prices, forward date is index + 5

## Results (technical factors only)
| Metric | Value |
|---|---|
| Pick Sharpe | 0.86 |
| Bench Sharpe | 0.83 |
| Excess Sharpe | 0.28 |
| Win rate | 45% |
| Best excess | +5.15% |
| Worst excess | -3.92% |
| Cumulative excess | +1.35% |

## Interpretation
Modest positive signal. The technical factors (entropy + hurst + vol) slightly outperform the universe average over 8 years. Excess Sharpe of 0.28 with a 45% win rate means the model is right less than half the time, but wins are larger than losses.

## Limitations
- Technical factors only — no sentiment, insider, trends, or whale signals
- Sampled dates (not every trading day)
- Fixed 5-day horizon
- Cross-sectional ranking only (no position sizing or weighting)
- OHLCV data only goes to 2026-07-02

## Run
```bash
cd /d/vesper && python scripts/vesper_backtest.py
```

## Next improvements
- Add all 6 registry factors (need historical sentiment/insider/trends data)
- Use weighted scoring instead of equal-weight
- Add position sizing based on score magnitude
- Run daily (not sampled) for full history
- Add sector and factor exposure constraints