# Google Trends Factor Implementation

## Overview
Uses `pytrends` (free, no API key) to fetch 30-day search interest for tickers.
Z-score normalized across the universe. High search volume often precedes volatility.

## Module
`app/factors/trends.py` — `GoogleTrendsFactor(BaseFactor)`

## Key Details
- Requires `pip install pytrends`
- Query one ticker at a time (batches of 5 can return empty results)
- Timeframe: `"today 1-m"` (30 days of weekly data)
- Returns integer search interest (0-100 scale)
- Z-score normalized: `(value - mean) / std`
- Cached to `data/google_trends/trends_YYYYMMDD.json`
- Registered in Registry as `google_trends`

## First Run Results (18 tickers)
```
V: +1.74  PG: +1.55  KO: +1.51  DIS: +1.29  HD: +1.02
COST: +0.53  AMD: +0.18  GOOGL: +0.03  META: -0.16  BAC: -0.39
```

## API Pattern
```python
from pytrends.request import TrendReq
p = TrendReq(hl="en-US", tz=360, timeout=10)
p.build_payload(["AAPL"], cat=0, timeframe="today 1-m", geo="", gprop="")
data = p.interest_over_time()
score = int(data["AAPL"].iloc[-1])  # Last week's value
```

## Troubleshooting
- **Empty results**: pytrends can be flaky. Retry with a single ticker, not a batch
- **Slow**: ~3 seconds per ticker. For 20 tickers, expect ~60 seconds total
- **Rate limiting**: pytrends has built-in backoff, but very large batches may get blocked
- **isPartial column**: Always present in returned data; dropna() handles it