# Split-Adjusted OHLCV for Vesper Factors

## Problem
The primary OHLCV database (`sp500_ohlcv.sqlite`) contains **raw unadjusted prices**.
Stock splits (e.g. NVDA 10:1 on 2024-06-10) produce massive non-economic price
discontinuities that factors interpret as real returns.

## Detection Pattern

Detect splits by scanning for large single-day price drops matching standard
split ratios (2:1, 3:1, 4:1, 5:1, 7:1, 10:1, 20:1) within a ±2% tolerance.

**CRITICAL**: iterate **backward** through the price series. Forward iteration
applies cumulative adjustment factors to the wrong dates.

```python
STANDARD_RATIOS = {2: 0.5, 3: 1/3, 4: 0.25, 5: 0.2, 7: 1/7, 10: 0.1, 20: 0.05}
TOLERANCE = 0.02

def is_likely_split(forward_ratio):
    for n, expected in STANDARD_RATIOS.items():
        if abs(forward_ratio - expected) < TOLERANCE:
            return n
    return None

# Iterate BACKWARD from most recent date
cum_factor = 1.0
for j in range(len(rows) - 1, -1, -1):
    date = rows[j]['date']
    ticker_adj[date] = cum_factor
    if j > 0:
        forward_ratio = rows[j]['close'] / rows[j-1]['close']
        n = is_likely_split(forward_ratio)
        if n is not None:
            cum_factor *= (1.0 / n)  # applied to OLDER dates
```

## Validation
Validate against the known adjusted DB (`vesper_data/massive/adjusted/`):
- NVDA 10:1 (2024-06-10): pre-split factor 0.1, adjusted_close ~$122 (smooth)
- AAPL 4:1 (2020-08-31): pre-split factor 0.25, adjusted_close ~$125
- AMZN 20:1 (2022-06-06): pre-split factor 0.05, adjusted_close ~$122

## Integration (db.py)

Two public functions added to `app/factors/db.py`:

- `fetch_adjusted_ohlcv_rows(conn, date_list, extras=(), root=".")`
  Drop-in replacement for `fetch_ohlcv_rows`. Returns `list[dict]` with
  split-adjusted close/open/high/low columns. Same `r['close']` access.

- `get_split_adjustment(ticker, date, root=".")`
  Single (ticker, date) lookup for raw-SQL consumers.

Adjustment factors cached in `vesper_data/split_adjustments.json` (240 splits
across 174/502 tickers, regenerable from primary DB).

## Factor Updates
Each factor needs one import change:
```python
# Before
from app.factors.db import fetch_ohlcv_rows, ...
rows = fetch_ohlcv_rows(conn, date_list)
# After
from app.factors.db import fetch_adjusted_ohlcv_rows, ...
rows = fetch_adjusted_ohlcv_rows(conn, date_list)
```
Factors using raw SQL (not `db.py` helpers) use `get_split_adjustment()` to
multiply close prices inline.

## See also
- `app/factors/db.py` — `fetch_adjusted_ohlcv_rows`, `get_split_adjustment`
- `vesper_data/split_adjustments.json` — cached adjustment factors
- `vesper_data/massive/adjusted/` — known-good adjusted DB for validation (33 tickers)