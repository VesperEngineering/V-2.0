# Massive Data Lab — 2026-07-07

Four tests on newly available Massive datasets using `sp500_ohlcv.sqlite` (502 tickers, 2005-2026, 21d horizon, 256 rebalance steps).

## Test 1: Liquidity/Turnover Signals

| Signal | Mean IC | IC IR | % Positive | Interpretation |
|---|---|---|---|---|
| **Amihud illiquidity** | +0.034 | **+0.325** | 63.3% | Strongest new signal. Higher illiquidity → higher forward returns. |
| Dollar volume surge | -0.010 | -0.131 | 42.6% | Anti-predictive. High volume days reverse. |
| Simple turnover | -0.006 | -0.086 | 48.0% | Noise. |

**Amihud (2002)**: mean(|daily return| / dollar_volume) over 21-day window. Implemented as `app/factors/amihud.py` — 500 tickers in <1s.

## Test 2: Total Return DB

Massive normalized DB has 8,646 tickers. Dividends add ~2%/yr to S&P 500 returns. For proper backtest, swap source to `total_return/day_aggs_total_return_*.sqlite`.

## Test 3: Sub-Period Stability

| Period | Sharpe | Win Rate | Excess | Steps |
|---|---|---|---|---|
| 2005-2012 | +0.43 | 55% | +9.0% | 94 |
| 2013-2019 | +0.30 | 57% | +5.0% | 83 |
| **2020-2026** | **+1.13** | **65%** | **+42.3%** | 77 |

Signal getting stronger — no decay.

## Test 4: Factor Correlation Matrix

All pairwise < 0.5. No redundancy across 7 active factors.
