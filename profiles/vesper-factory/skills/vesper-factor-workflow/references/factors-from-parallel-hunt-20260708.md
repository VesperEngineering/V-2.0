# Factors Built via Parallel Agent Hunt — 2026-07-08

5 DeepSeek Pro agents dispatched via `delegate_task` to hunt for new factors simultaneously.

## Results

| # | Source | Factor File | Class | Name | Tickers | Time | Status |
|---|---|---|---|---|---|---|---|
| 1 | FRED API | `app/factors/macro_fred.py` | MacroFREDFactor | `macro_fred` | 502 | 0.3s | ✅ |
| 2 | Massive S3 OHLCV | `app/factors/massive_intraday.py` | MassiveIntradayFactor | `massive_intraday` | 498 | 0.1s | ✅ |
| 3 | SEC EDGAR DB | `app/factors/sec_insider_v2.py` | SECInsiderV2Factor | `sec_insider_v2` | 886 | 10s | ✅ |
| 4 | Wikipedia REST | `app/factors/wiki.py` (patch) | WikiFactor | `wiki_attention` | — | — | 🔄 pending |
| 5 | Massive normalized DB | `app/factors/market_micro.py` | MarketMicrostructureFactor | `market_micro` | — | — | 🔄 pending |

## Factor Details

### macro_fred
- Fetches FRED graph CSV (free, no API key): T10Y2Y (yield spread), UNRATE, CPIAUCSL
- Maps macro signals to GICS sector exposures
- All tickers in same sector get same score (sector tilt, not stock differentiation)
- Top sector at run: Energy +2.04σ; bottom: Real Estate −1.88σ

### massive_intraday
- 3 sub-signals from Massive OHLCV: intraday volatility (21d range/close), gap risk (abs(open-close)/close), volume spike (-log ratio vs 20d avg)
- ALL signals computed from OHLCV columns already in sp500_ohlcv.sqlite
- Columns beyond OHLCV in raw CSV: `window_start` (nanoseconds), `transactions` (trade count)

### sec_insider_v2
- 4,591 CIK→ticker mappings from security_master in analyst DB
- Classifies Form 4 filings as buy/sell via XML transactionCode
- Cluster bonus: 1.5× multiplier when 3+ insiders buy same ticker within 7 days
- Scoring: sign(net) × √|net| × ln(total+1) × cluster_bonus
- 10× coverage of v1 insider factor (886 vs 86 tickers)

## Concurrency Pitfall
All 3 agents patched `registry.py` — last one won, dropping the other two registrations.
**Fix**: orchestrator rebuilt registry.py after all agents returned. See the Registry Concurrency Pitfall in SKILL.md.
