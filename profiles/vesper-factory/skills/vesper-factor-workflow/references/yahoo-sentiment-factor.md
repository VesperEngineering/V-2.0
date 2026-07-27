# Yahoo Sentiment Factor — SUPERSEDED

**This approach was superseded on 2026-07-07 by `MassiveSentimentFactor`**
(`app/factors/finviz_sentiment.py`) which uses the local Massive OHLCV DB
instead of the Yahoo Finance API. See `references/massive-sentiment-factor.md`.

Old approach preserved below for reference only (switched because Massive OHLCV
is 0.01s vs 7s, zero network calls vs 500+ HTTP, no rate limits).

---

## Old approach: Yahoo Finance v8 chart API
- Endpoint: `https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1d&interval=1d`
- Returns JSON with `chart.result[0].meta.regularMarketPrice` and `chartPreviousClose`
- Compute change % = `(current - prev_close) / prev_close * 100`
- No API key required; standard browser User-Agent works

## Concurrency pattern
```python
from concurrent.futures import ThreadPoolExecutor, as_completed
MAX_WORKERS = 20
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
    fut_map = {ex.submit(fetch, t): t for t in tickers}
    for fut in as_completed(fut_map):
        ...
```
20 concurrent → ~7s for 500 tickers.

## Cache
5-min TTL per ticker JSON cache at `data/yahoo_sentiment_cache/<TICKER>.json`.

## Pitfalls (old approach)
- Yahoo may rate-limit if >20 concurrent
- The `chartPreviousClose` key name — some responses use `previousClose`; handle both
- Market-hours only: if called when market is closed, change % is from last close
