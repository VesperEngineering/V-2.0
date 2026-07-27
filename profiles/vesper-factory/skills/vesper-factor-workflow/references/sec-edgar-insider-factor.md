# SEC EDGAR Insider Factor (Form 4)

Implements the Rentec-inspired principle: publicly available data that everyone overlooks.

## Data Flow

```
SEC daily index (free, no API key)
    → form.YYYYMMDD.idx (fixed-width, ~9000 lines per day)
    → Filter: form type == "4" (insider transaction)
    → Filter: CIK in our universe tickers (43 tickers)
    → For each filing: download first 4KB of .txt filing
    → Extract <transactionCode> from XML
    → Score: (buys - sells) / (buys + sells)
    → Cache filing HTML to avoid redownloads
```

## CIK → Ticker Mapping

SEC provides a master list at `https://www.sec.gov/files/company_tickers.json`
Format: `{"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}`
Key: pad `cik_str` to 10 digits with `zfill(10)`.
Cached at `data/insider_trades/cik_ticker_map.json` (~8000 companies).

## Daily Index Fixed-Width Format

Header:
```
Form Type   Company Name                                                  CIK
     Date Filed  File Name
```

Data line example:
```
4         325 CAPITAL LLC                                          1873893     20260702    edgar/data/1873893/0000921895-26-001748.txt
```

## Transaction Codes

| Code | Meaning | Classification |
|------|---------|---------------|
| P | Purchase | Buy |
| S | Sale | Sell |
| A | Grant/Award | Buy (neutral, counted as buy) |
| M | Exercise of derivative | Buy |
| D | Disposition | Sell |
| F | Tax withholding (sell to cover) | Sell |

## Filing XML Pattern

```xml
<nonDerivativeTransaction>
    <transactionCoding>
        <transactionFormType>4</transactionFormType>
        <transactionCode>A</transactionCode>
    </transactionCoding>
</nonDerivativeTransaction>
```

## Key files

- `app/factors/insider.py` — Factor class + index parsing + filing classification
- `scripts/insider_trades.py` — Thin CLI wrapper
- `data/insider_trades/insider_scores.json` — Daily scores (auto-generated)
- `data/insider_trades/filing_cache.json` — Cached filing classifications
- `data/insider_trades/cik_ticker_map.json` — CIK → ticker mapping

## Performance

- First run: ~10s for 23 filings across 1 day (downloads + classifies each)
- Subsequent runs: ~1s (cache hit) + new filings only
- Bounded to 50-100 filings per run for responsiveness