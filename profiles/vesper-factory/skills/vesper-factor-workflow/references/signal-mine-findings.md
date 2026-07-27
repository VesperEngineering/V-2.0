# Signal Mine — Full IC Results (2026-07-07)

Two-pass exhaustive mining: 27 signals tested across 502 tickers × 245 rebalance steps (2005-2026, 21d horizon).

## Pass 1 (`scripts/signal_mine.py`) — 20 OHLCV Technical Signals

| Signal | IC IR | Mean IC | % Pos | Direction | Verdict |
|---|---|---|---|---|---|
| amihud | +0.289 | +0.030 | 61.2% | BUY | → factor, later REMOVED by optimizer |
| consecutive_up | -0.145 | -0.013 | 45.7% | SHORT | → mean_reversion composite |
| ret_10d | -0.141 | -0.019 | 46.9% | SHORT | → mean_reversion composite |
| rvol_63d | +0.135 | +0.029 | 55.9% | BUY | CONFLICT: sp500_technical uses -rvol |
| intraday_range | +0.117 | +0.018 | 54.3% | BUY | → KING: solo Sharpe 0.803 |
| bb_position | -0.110 | -0.014 | 49.4% | SHORT | → mean_reversion composite |
| rsi_14 | -0.078 | -0.010 | 50.2% | SHORT | → mean_reversion composite |

## Pass 2 (`scripts/signal_mine_v2.py`) — 7 New Signals + SEC + Massive

| Signal | IC IR | Direction | Action |
|---|---|---|---|
| dollar_vol (size) | -0.285 | SHORT | → size_factor, later REMOVED |
| idio_vol_60d | +0.125 | BUY | correlated with intraday_range |
| beta_252d | +0.113 | BUY | → beta_factor, later REMOVED |
| gap_freq_20d | +0.098 | BUY | monitor |

SEC fundamentals: 3,199 tickers, ratios near zero. Not predictive.
Massive normalized DB: no transaction data. Dead end.

## Factor Optimizer (`scripts/factor_optimizer.py`) — 2026-07-07

Greedy forward selection across 6 historically-validated factors:

| Combo | Sharpe | Excess | Win | Max DD |
|---|---|---|---|---|
| intraday_range alone | 0.803 | +31.4% | 54% | -68.6% |
| + sp500_technical | **0.932** | +28.8% | 59% | -65.2% |
| + mean_reversion | **0.935** | +27.4% | 60% | -64.8% |
| All 6 equal-weight | 0.670 | +20.8% | 55% | -67.9% |

**Drop-one**: removing intraday_range drops Sharpe from 0.67 to 0.29.
Removing amihud IMPROVES Sharpe from 0.67 to 0.77. Removing size_factor
IMPROVES to 0.79. These factors DILUTE the blend.

**Key lesson: individual IC ≠ blend value.** Solo IR is a necessary but
NOT sufficient condition. Always run `scripts/factor_optimizer.py`.

## Hyperparameter Lab (`scripts/hyperparam_lab.py`) — 2026-07-07

6-test battery on the 3-factor kernel:

| Test | Finding | Action |
|---|---|---|
| Rebalance freq | 5d Sharpe 0.69 > 21d 0.57 | Keep daily |
| Position sizing | Equal-weight wins | No change |
| SEC fundamentals | Median ratios near zero | Dead end |
| Tick data | No transactions in DB | Dead end |
| Vol-targeting | Higher Sharpe, worse DD — just leverage | Not risk control |
| Walk-forward | 13/15 years positive, mean Sharpe 0.73 | STRATEGY VALIDATED |

## Factor Count This Session: 6 → 11 → 8

Dead factors killed: finviz_sentiment (IC IR 0.001), massive_fund,
technical, google_trends, whale_13f, amihud, size_factor, beta_factor.

**Rule: when IC IR < 0.01 OR optimizer says dilutive, remove from registry.
Don't leave at weight 0.0 — it burns subprocess slots and confuses counts.**
