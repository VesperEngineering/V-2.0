# S&P 500 Universe Expansion (2026-07-06)

## Ticker list
- Source: Wikipedia List of S&P 500 companies
- 481 tickers with CIK mapping at `data/sp500_tickers.json`
- Format: `{"tickers": "MMM,AOS,ABT,...,ZTS"}`

## Massive S3 Ingestion — DONE (457 tickers ingested)

### Source
- **Endpoint**: `files.massive.com` S3 bucket (`flatfiles/us_stocks_sip/day_aggs_v1/`)
- **AWS CLI**: `C:/Program Files/Amazon/AWSCLIV2/aws.exe` (Windows full path required)
- **Credentials**: `MASSIVE_S3_ACCESS_KEY_ID` + `MASSIVE_S3_SECRET_ACCESS_KEY` from `.env`
- **Format**: gzipped CSVs with columns: ticker, volume, open, close, high, low, window_start, transactions
- **Date format**: `window_start` is nanoseconds since epoch → `datetime.fromtimestamp(int(val)/1e9).strftime("%Y-%m-%d")`

### Pipeline
`scripts/massive_sp500_ingest.py` — downloads recent CSVs, filters for SP500 tickers, inserts into SQLite.

### Critical pitfalls for AWS CLI subprocess
1. **AWS_ENV MUST inherit from os.environ**: `{**os.environ, "AWS_ACCESS_KEY_ID": ..., "AWS_SECRET_ACCESS_KEY": ...}` — without `**os.environ`, AWS CLI can't find PATH or config
2. **dotenv.load_dotenv() BEFORE os.getenv()**: env vars only available after loading .env
3. **Each daily CSV covers ALL tickers**: one 315KB file contains ~10,000 tickers — no per-ticker downloads needed
4. **Use `aws s3 cp` not `sync`**: `sync` tries to list all objects first, slow on large buckets

### Results
- **457 tickers** per file (of 481 SP500 names)
- **2,285 rows** across 5 trading days (Jun 26 - Jul 2, 2026)
- **Database**: `vesper_data/massive/sp500/sp500_ohlcv.sqlite`
- **Schema**: `sp500_ohlcv(ticker TEXT, date TEXT, close REAL, volume REAL, open REAL, high REAL, low REAL, PRIMARY KEY(ticker, date))`

### Current state
- Technical factors run on 17-ticker universe via active-universe OHLCV
- 457 tickers of OHLCV available at `sp500_ohlcv.sqlite` but not yet wired into factor pipeline
- Reference DB: market_cap, sector, employees for 33 tickers
- **Next step**: Rewire `_load_ohlcv()` or build SP500 technical factor to use `sp500_ohlcv.sqlite`

## Live news scraper
- `scripts/live_news.py` — RSS feeds from MarketWatch + Yahoo Finance
- 71 articles in 0.4s, cron runs hourly 8am-5pm ET Mon-Fri
- **Company name matching** (528-entry name→ticker map) replaces ticker-symbol-only matching
- Some false positives from common-word company names (HAS=Hasbro, ARE=Alexandria RE, LOW=Lowe's, NOW=ServiceNow)
- Output: `data/news_live/live_YYYYMMDD.json` with scores + headlines per ticker

## Alpaca live P&L
- `scripts/alpaca_live.py` — real-time portfolio snapshot from Alpaca API
- Market-hours detection: `is_market_open()` checks 13:30-20:00 UTC Mon-Fri
- Output: `artifacts/evals/alpaca_portfolio_YYYYMMDD.json` with history accumulation
- Dashboard `_lport` reads this for live equity/P&L display

## Massive Fundamentals v2
- `app/factors/massive_fund.py` — market cap + momentum + sector from Massive databases
- Registered as 8th factor alongside `massive` v1
- 29 tickers scored using market cap (size) and 20-day momentum
- Uses `ticker_overview` (reference DB) and `adjusted_day_aggs` (adjusted DB)
