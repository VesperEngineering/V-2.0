# Massive Sentiment Factor (finviz_sentiment) — OHLCV DB Pattern

Created 2026-07-07, rewired 2026-07-07 from Yahoo Finance API → Massive OHLCV DB.
Covers 502 S&P 500 tickers, **0.01s**, zero network calls, no API key.

## Why this approach

The WebZ-based `sentiment` factor was limited to 38 tickers (paid subscription cap).
Yahoo Finance v8 chart API worked but required 500+ concurrent HTTP requests (~7s).

**Much simpler**: the Massive `sp500_ohlcv.sqlite` already has daily closes for 502
tickers. Compute today's return cross-sectionally in one SQL query.

## Implementation

```python
import sqlite3

db = "vesper_data/massive/sp500/sp500_ohlcv.sqlite"
uri = f"file:{db}?mode=ro"
conn = sqlite3.connect(uri, uri=True)

# Last two trading dates
dates = conn.execute(
    "SELECT DISTINCT date FROM sp500_ohlcv ORDER BY date DESC LIMIT 2"
).fetchall()
d1, d2 = dates[0]["date"], dates[1]["date"]

# Closes for both dates
rows_today = {r["ticker"]: r["close"] for r in
    conn.execute("SELECT ticker, close FROM sp500_ohlcv WHERE date = ?", (d1,))}
rows_yest = {r["ticker"]: r["close"] for r in
    conn.execute("SELECT ticker, close FROM sp500_ohlcv WHERE date = ?", (d2,))}

# Change % per ticker
scores = {}
for t, c_today in rows_today.items():
    c_yest = rows_yest.get(t)
    if c_yest and c_yest != 0:
        scores[t] = (c_today - c_yest) / c_yest * 100.0

conn.close()
```

Then z-score normalize: `z = (change_pct - mean) / std`.

## Key advantages

| Aspect | Old (Yahoo) | New (Massive) |
|---|---|---|
| Time | ~7s for 500 | **0.01s** |
| Network calls | 500+ HTTP | **Zero** |
| Failure modes | Rate limits, timeouts, DNS | SQL query |
| Cache needed | 5-min TTL | **None** |

## Score combination

The factor registers as `finviz_sentiment` (name didn't change — backward compat with
the dashboard's `sent` column which maps `finviz_sentiment` first, falls back to
`sentiment`). Weight in `run_all_factors.py`:

```python
FACTOR_WEIGHTS = {
    ...
    "finviz_sentiment": 0.5,  # daily return z-score — simple but 502 tickers
}
```

Pipeline timeout: 10s (vastly over-provisioned for 0.01s actual).

## Pitfalls

- **Early-day zeros**: Before 16:00 ET, today's close hasn't happened — the last
  available date is yesterday, so change % is from the previous trading day. This is
  correct (daily sentiment for yesterday), but the Sent column shows zeros or stale
  values if checked mid-session.
- **SQLite locking**: Must use `uri=True` + `mode=ro` — `connect()` with `timeout=30`
  is the correct `sqlite3.connect(f"file:{db}?mode=ro", uri=True)`. Plain connect
  throws "database is locked" if an OHLCV ingest write runs simultaneously.
- **OHLCV freshness**: This factor is only as fresh as the OHLCV DB. If the
  `massive_ohlcv_ingest.py` cron (Vesper OHLCV Ingest, 07:30 Tue-Sat) fails, the
  factor silently computes on stale prices.
