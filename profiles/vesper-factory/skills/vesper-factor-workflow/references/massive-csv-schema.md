# Massive S3 day_aggs_v1 CSV Schema

Raw files at `s3://flatfiles/us_stocks_sip/day_aggs_v1/YYYY/MM/YYYY-MM-DD.csv.gz`.
Cached locally at `vesper_data/massive/raw/us_stocks_sip/day_aggs_v1/`.

## Columns

| # | Column | Type | Description |
|---|---|---|---|
| 1 | `ticker` | str | Stock symbol (dot-form for class shares: `BRK.B`) |
| 2 | `volume` | float | Dollar volume (price × shares, not share count) |
| 3 | `open` | float | Opening price |
| 4 | `close` | float | Closing price |
| 5 | `high` | float | High price |
| 6 | `low` | float | Low price |
| 7 | `window_start` | int | Epoch timestamp in **nanoseconds** — divide by 1e9 for `datetime.fromtimestamp()` |
| 8 | `transactions` | int | Number of trades in the bar |

## Key gotchas

- **volume is dollar volume, not share volume.** Don't compare raw numbers across differently-priced stocks without normalizing.
- **window_start nanoseconds**: `datetime.fromtimestamp(int(row["window_start"]) / 1e9)`.
- **ticker dot-form**: `BRK.B` not `BRK-B`. Internal code may convert; the CSV has dots.
- All US stocks are in each daily file (~10,000+ tickers). Filter for S&P 500 constituents.

## Ingestion script

`scripts/massive_sp500_ingest.py` downloads from S3 via AWS CLI with `--endpoint-url https://files.massive.com --no-verify-ssl`, filters for `data/sp500_tickers.json` constituents, and writes to `sp500_ohlcv.sqlite` with columns: `ticker, date, close, volume, open, high, low`. The DB drops `window_start` (converted to date string) and `transactions`.

To extend to new columns (e.g., `transactions`), modify the DB schema and ingestion script — the raw CSVs have the data.
