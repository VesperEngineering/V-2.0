# SEC Insider v2 Factor

## Overview

`app/factors/sec_insider_v2.py` — `SECInsiderV2Factor(name='sec_insider_v2')`

DB-backed SEC insider transaction factor. Uses `security_master` (4,591 active CIK→ticker
mappings) for universe, scrapes SEC EDGAR daily Form 4 indices for filings, classifies
buys/sells from filing XML, detects insider buying clusters, and returns cross-sectional
z-scores.

## Key metrics (30-day lookback, 2026-07-08)

| Metric | Value |
|--------|-------|
| Filings processed | 5,734 |
| Tickers scored | **886** |
| Unique z-scores | 126 |
| Clustered tickers | 123 |

## Database findings

**`sec_filings` has ZERO Form 4 data.** Only 8-K (1.2M), 10-Q (466K), 10-K (146K).
When building a factor that needs insider transaction data, you MUST scrape SEC EDGAR
directly — the analyst DB doesn't have it.

**`security_master` is the CIK→ticker gold mine** — 4,603 tickers, all with CIK mappings
and `is_active` flags. Query:
```sql
SELECT DISTINCT cik, ticker FROM security_master
WHERE cik IS NOT NULL AND ticker IS NOT NULL AND is_active = 1
```

## Architecture

```
security_master (DB) → CIK→ticker map (4,591 entries)
         ↓
SEC EDGAR daily index → Form 4 filings (30-day window)
         ↓
Filing XML download → transactionCode extraction (P/A = buy, S/D = sell)
         ↓
Aggregation per ticker → buy/sell counts + cluster detection
         ↓
Scoring: sign(net) × √|net| × ln(total+1) × cluster_bonus
         ↓
Cross-sectional z-score via BaseFactor.zscore()
```

## Scoring formula

```
raw_score = sign(buys - sells) × sqrt(|buys - sells|) × ln(total + 1) × cluster_bonus
```

Components:
- **Direction**: sign of net (positive for net buying)
- **Conviction**: sqrt of net count — more trades = more signal
- **Volume scaling**: ln(total + 1) — differentiates heavy from sparse activity
- **Cluster bonus**: 1.5× when 3+ distinct insider buys hit the same ticker within 7 days

Without volume weighting (plain net_ratio = (buys - sells)/total), z-scores collapse to
only ~62 unique values because most tickers have net_ratio = 1.0 (all buys). The sqrt×log
weighting spreads the distribution to 126 unique z-scores.

## CIK map fallback chain

1. `security_master` table (primary — 4,591 tickers)
2. `data/insider_trades/cik_ticker_map_v2.json` (persistent cache)
3. `https://www.sec.gov/files/company_tickers.json` (last resort, ~10K tickers but no
   `is_active` filtering)

## Buy/Sell classification

- **Buy**: transactionCode P (Purchase), A (Acquisition)
- **Sell**: transactionCode S (Sale), D (Disposition)
- **Ignored**: M (exercise/conversion), F (tax withholding) — informational, not
  directional

Classification cache: `data/insider_trades/filing_cache_v2.json` (6,006 entries as of
2026-07-08). Re-downloads only on cache miss.

## Caching

| File | Purpose |
|------|---------|
| `data/insider_trades/cik_ticker_map_v2.json` | CIK→ticker map |
| `data/insider_trades/filing_cache_v2.json` | filename → transactionCode |
| `data/insider_trades/sec_insider_v2_scores.json` | Latest scores + raw detail |

## Integration

Registered in `app/factors/registry.py` as `SECInsiderV2Factor()`. Factor name:
`sec_insider_v2`. No `required_data` — fully self-contained (DB read + SEC scrape).

## Compared to original insider factor

| | `insider` (v1) | `sec_insider_v2` |
|---|---|---|
| Universe | S&P 500 (~500) from `sp500_tickers.json` | 4,591 from `security_master` DB |
| Lookback | 7 days | 30 days (configurable) |
| Batch cap | 300 filings | No cap — all matched filings |
| Clusters | No | Yes — 3+ buyers in 7 days = 1.5× bonus |
| Scoring | net_ratio only | Volume-weighted + cluster bonus |
| Typical coverage | ~90 tickers | ~886 tickers |
| CIK map | SEC endpoint + JSON cache | DB (primary) → cache → SEC endpoint |
