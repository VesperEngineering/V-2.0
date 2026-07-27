# Factor-Level IC Analysis — v2.2 (2026-07-07)

Full history cross-sectional rank IC: 502 tickers, 256 rebalance steps,
21-day horizon, 2005-01 to 2026-07.

## Results

| Signal | Mean IC | IC IR | % Pos | t-stat | n | Verdict |
|---|---|---|---|---|---|---|
| mom_12_1 | +0.0124 | +0.067 | 57.8% | +1.06 | 256 | ✅ Best |
| sp500_technical blend | +0.0086 | +0.051 | 55.9% | +0.81 | 256 | ✅ Core |
| str_rev (-5d) | +0.0077 | +0.049 | 56.6% | +0.79 | 256 | ✅ Additive |
| massive_proxy | +0.0054 | +0.033 | 54.7% | +0.53 | 256 | ✅ Weak |
| **raw daily return z-cross** | **+0.0001** | **0.001** | **50.4%** | **+0.01** | **256** | **❌ ZERO** |
| volsurge | -0.0081 | -0.113 | 43.8% | -1.81 | 256 | ⚠️ Invert |
| lowvol (-rvol) | -0.0299 | -0.124 | 45.3% | -1.99 | 256 | ⚠️ Invert |

## Weight derivation

Weights = IC IR × 12 (approx), floored at 0.1, capped at 1.0:
- sp500_technical: 1.0 (IR 0.05)
- sec_fundamentals: 0.6 (theoretical — not historically reconstructable from OHLCV alone)
- massive: 0.5 (IR 0.03)
- finviz_sentiment (sector-relative): 0.4 (orthogonal, unvalidated — not the same as raw daily return which had zero IC)
- wiki_attention: 0.3 (unverifiable historically — contemporary data only)
- insider: 0.3 (sparse, unvalidated)
- sentiment: 0.2 (38 tickers, unvalidated)

## Key insight

**Sector-relative strength ≠ raw daily return z-cross-section.** The
raw daily return had IC 0.0001 (zero signal). Replaced with within-sector
z-scoring on 2026-07-07 — this signal is orthogonal to momentum/technical
factors because it captures relative performance within peer groups.

finviz_sentiment weight was 0.0 for 1 commit, then restored to 0.4 after
rewrite to sector-relative. The old 0.5 weight was based on wrong premise
(raw return has signal — it doesn't).

## Non-verifiable factors

SEC fundamentals (394 tickers): theoretically strong (revenue growth,
margin, ROE, asset turnover) but cannot be reconstructed historically
from OHLCV DB. Needs the EDGAR sec_facts database which only covers
the current filing window. Conservative 0.6 weight.

Wiki attention, sentiment (WebZ), insider: all contemporary data only.
Conservative weights until live IC analysis accumulates enough data.