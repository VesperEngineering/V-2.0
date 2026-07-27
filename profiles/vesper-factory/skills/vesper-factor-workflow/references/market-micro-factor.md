# Market Microstructure Factor (`market_micro`)

Built 2026-07-08. Sources from Massive normalized OHLCV (`day_aggs_coverage_expanded.sqlite`, 776K rows, 19K tickers, 2003–2026).

## Normalized DB Schema

Table: `day_aggs`
| Column | Type | Notes |
|---|---|---|
| `ticker` | TEXT | Primary key part 1 |
| `ticker_upper` | TEXT | Indexed |
| `as_of_date` | TEXT | `YYYY-MM-DD`, indexed |
| `open` | REAL | |
| `high` | REAL | |
| `low` | REAL | |
| `close` | REAL | |
| `volume` | REAL | Share volume (not dollar) |
| `window_start` | INTEGER | Nanoseconds epoch |
| `transactions` | INTEGER | Trade count |
| `source_key` | TEXT | S3 path |
| `source_sha256` | TEXT | |

Primary key: `(ticker, window_start)`. Indices on `ticker`, `ticker_upper`, `as_of_date`.

Ticker stats (as of 2026-06-18): 19,115 distinct, 12,209 on latest date, 8,262 with 21+ days (93d max).

## Three Sub-Signals

1. **Amihud Illiquidity** (21d window, inverted): `mean(abs(ret) / dollar_vol)` → inverted so liquid names score higher. Raw values cluster near 0 for liquid stocks — use rank-based z-score.
2. **Turnover / Liquidity** (approximate): market_cap / close → shares from reference DB (33 tickers only). Fallback: `log(avg dollar volume)` over 21d.
3. **VWAP Deviation** (21d window): `(close − VWAP) / VWAP` where VWAP ≈ (H+L+C)/3. Close > VWAP = bullish.

## Normalization Strategy

**All three sub-signals use rank-based z-score** (`_rank_zscore`). This is non-negotiable for microstructure factors:
- Amihud is zero-inflated (liquid stocks ≈ 0, raw z-score max is +0.0147 — useless)
- Turnover is log-normal (heavy right tail — AAPL/MSFT dominate raw z-score)
- VWAP deviation has long-tailed outliers

Rank-based approach: `pd.Series.rank(pct=True)` → z-score the ranks → well-behaved [−1.73, +1.73] per signal.

**Do NOT use raw z-score for any sub-signal of a microstructure/liquidity factor.** It produces extreme clusters in the combined distribution that winsorization cannot fix.

## Winsorization Pitfall

When sub-signals use raw z-scores (not rank-based), the combined score produces clusters of identical values in the tails. Winsorization at (0.01, 0.99) clips ALL top 80 tickers to the same score — tops are indistinguishable. Even (0.0025, 0.9975) clips 20. The root cause is the raw distribution skew, not the winsorization percentile.

**Fix**: rank-based normalization for all sub-signals, then final z-score WITHOUT winsorization. The combined distribution is naturally bounded (max ~±2.6) and requires no clipping.

## Results
- **7,994 tickers scored** (300+ target easily met)
- Distribution: mean ≈ 0, std ≈ 1, skew −0.123
- Top: large-cap liquid (KO +2.58, X +2.36, CVS +2.23)
- Bottom: illiquid warrants (IW.WS −2.61, DCTHW −2.61)
- Registered in v1.3 registry (13 factors, 8 data sources)
