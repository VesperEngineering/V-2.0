# Drawdown Circuit Breaker — DO NOT USE

## Test (2026-07-08)
Backtested DD breakers with the 3-factor kernel (2005-2026, 257 rebalance steps).

## Results
| Breaker | Sharpe | Max DD | Triggers |
|---|---|---|---|
| None | +0.37 | -35% | 0 |
| Halve at -20%, full cash at -30% | -0.29 | -15% | 213 |
| Full cash at -25% | -0.29 | -15% | 213 |
| Halve at -15%, full at -25% | -0.25 | -11% | 216 |

## Why It Fails
The strategy naturally draws down 15-35% with 52% win rate. A DD breaker triggers during normal volatility, exits at the bottom, misses the recovery. It cannot distinguish "strategy failing" from "normal drawdown period."

## What Works Instead
**Regime filter** — reduce exposure during market conditions that historically kill the strategy (rising rates, high correlation, low cross-sectional dispersion). This is selective and forward-looking, not reactive.

## Script
`scripts/dd_circuit_breaker.py` — reference implementation. Do not deploy.
