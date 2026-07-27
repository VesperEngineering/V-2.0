# SP500 Expansion Reference (v1.1 — July 2026)

## What was done
Expanded Vesper from 21-ticker universe to full S&P 500 (493 tickers).

## Ingestion pipeline
- **Script**: `scripts/massive_sp500_ingest.py`
- **Source**: Massive S3 at `s3://flatfiles/us_stocks_sip/day_aggs_v1/YYYY/MM/YYYY-MM-DD.csv.gz`
- **Method**: AWS CLI (`C:/Program Files/Amazon/AWSCLIV2/aws.exe`) with `--endpoint-url https://files.massive.com --no-verify-ssl`
- **Credentials**: `MASSIVE_S3_ACCESS_KEY_ID` + `MASSIVE_S3_SECRET_ACCESS_KEY` from `.env`
- **Must call** `dotenv.load_dotenv()` before subprocess — the env vars aren't set otherwise
- **Filter**: Downloads daily CSV (~310KB gzip containing ALL US tickers ~5000+), filters for SP500 only
- **Database**: `vesper_data/massive/sp500/sp500_ohlcv.sqlite`
- **Schema**: `sp500_ohlcv(ticker, date, close, volume, open, high, low)`

## Current coverage (verified 2026-07-07)
- **464 distinct tickers** (some SP500 constituents not in Massive's active universe)
- **57,485 rows** (2026-01-02 to 2026-07-02)
- **461 tickers have >20 trading days** (enough for 21-day lookback)
- Top tickers have 125 trading days each
- Average ~461 rows per trading day across the date range

## Massive daily CSV structure
```
Columns: ticker, volume, open, close, high, low, window_start, transactions
window_start: nanosecond Unix timestamp (e.g. 1782446400000000000)
Daily file size: ~310KB gzipped
Contains: ALL US tickers (~5000+), not just SP500
```

## Key gotcha: window_start is nanoseconds
Massive CSV `window_start` field uses nanosecond Unix timestamps:
```
1782446400000000000  →  2026-07-01  (divide by 1e9)
```
Convert with: `datetime.fromtimestamp(int(row["window_start"]) / 1e9)`

## Key gotcha: AWS CLI path on Windows
The Python `subprocess` call needs the full Windows path with `.exe`:
```python
AWS = "C:/Program Files/Amazon/AWSCLIV2/aws.exe"
```
Not `/c/Program Files/...` or `aws` (resolves to wrong Python on this system).

## Key gotcha: env vars for subprocess
Must pass `{**os.environ, "AWS_ACCESS_KEY_ID": ..., "AWS_SECRET_ACCESS_KEY": ...}` to `subprocess.run(env=...)`. The `.env` file values are NOT automatically in `os.environ` — `dotenv.load_dotenv()` must be called first.

## SP500 Technical Factor
- **File**: `app/factors/sp500_technical.py`
- Scores 459 tickers in 0.2 seconds
- Features: entropy (sign distribution), hurst (rescaled range), rvol (5d/20d vol ratio), momentum (20d return)
- Z-scored independently per factor, combined: hurst + momentum - rvol*0.5, then z-scored again
- Top tickers: TECH (4.74), POOL (2.82), COO (2.64), CAH (2.58) — value/trending names
- Bottom: KLAC (-3.44), CE (-2.05), WDC (-2.00), META (-1.99) — mean-reverting/volatile

## Factor coverage imbalance (CRITICAL)
As of v1.1, the combined score for ~430 tickers is based ONLY on `sp500_technical`:
- `sp500_technical`: 459/474 non-zero
- `sentiment`: 30/474 non-zero
- `wiki_attention`: 30/474 non-zero
- `massive`: 29/474 non-zero
- `massive_fund`: 21/474 non-zero
- `insider`: 5/474 non-zero
- `technical`, `google_trends`, `whale_13f`: 0/474 non-zero

This means tickers like TECH, POOL, COO rank highly ONLY because their technical momentum is strong — they have zero sentiment, wiki, or fundamental signal. AAPL and GOOGL get a richer multi-factor score, but this creates an apples-to-oranges ranking. **Expanding factor coverage to 460+ tickers is the highest-leverage improvement available.**

Priority for expansion:
1. `wiki_attention`: Currently limited to 30 hardcoded tickers. Wikipedia REST API is free, no rate limit. Could cover all 493 instantly.
2. `sentiment`: WebZ covers 30 tickers. FinViz could be expanded, or use RSS news + NLP for all SP500.
3. `massive_fund`: Only 33 tickers have reference data. Use SEC EDGAR companyfacts (4.3M facts in analyst DB) or Massive API batch queries.

## Ticker list
- **File**: `data/sp500_tickers.json`
- Source: Wikipedia "List of S&P 500 companies"
- 493 tickers as comma-separated string under `tickers` key
- Some missing from Massive (e.g. newly added constituents): ~29 not found in daily files

## How to extend to 2024-2025
Modify the download loop in `massive_sp500_ingest.py` to iterate over earlier years/months. Each year is ~250 trading days × 310KB = ~77MB compressed. Download all, filter, ingest.

The ingestion script already handles incremental downloads (skips files that exist locally). Just expand the year/month range.

## Score output format (v1.1)
```json
{
  "status": "SUCCESS",
  "date": "20260706",
  "scored_count": 474,
  "scored": [
    {"ticker": "AAPL", "score": 0.611, "details": {"sp500_technical": 0.834, "sentiment": 0.98, ...}},
    ...
  ],
  "top_10": [{"ticker": "AAPL", "score": 0.611}, ...],
  "factor_features": ["technical", "sentiment", "insider", "whale_13f", "massive", "massive_fund", "sp500_technical", "wiki_attention"]
}
```

Score distribution: mean=0.000, std=0.143, range [-0.560, 0.611] across 474 tickers.
