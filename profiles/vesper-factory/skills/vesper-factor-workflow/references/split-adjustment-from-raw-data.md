# Split Adjustment from Raw OHLCV Data

Technique for detecting and correcting stock-split price discontinuities
in any OHLCV database without external corporate-action data.

## Detection

Scan each ticker's price history for single-day close-price ratios that
match standard split patterns:

| Split | Forward ratio (next/prev) | Tolerance |
|-------|--------------------------|-----------|
| 2:1   | 0.50                     | ±0.02     |
| 3:1   | 0.333                    | ±0.02     |
| 4:1   | 0.25                     | ±0.02     |
| 5:1   | 0.20                     | ±0.02     |
| 7:1   | 0.143                    | ±0.02     |
| 10:1  | 0.10                     | ±0.02     |
| 20:1  | 0.05                     | ±0.02     |

AIG's 2008 crash (0.392 ratio) won't match any standard split ratio
and is correctly excluded. Real splits produce near-exact ratios.

## Adjustment factor computation

Iterate **backward** from the most recent date with `cum_factor = 1.0`:

```python
for j in range(len(rows) - 1, -1, -1):
    date = rows[j]['date']
    adjustments[date] = cum_factor      # assign BEFORE modifying
    if j > 0:
        forward_ratio = rows[j]['close'] / rows[j-1]['close']
        n = is_likely_split(forward_ratio)
        if n:
            cum_factor *= (1.0 / n)     # applies to OLDER dates
```

Forward-adjustment means all prices are at the most-recent scale.
NVDA's 10:1 split: pre-split $1,208.88 becomes $120.89 (×0.1).
Post-split $121.79 stays $121.79 (×1.0).

## Application

Multiply **price columns only** (close, open, high, low) by the
adjustment factor. Volume is shares — not price-scaled, so leave
it unadjusted. Validate against a known adjusted source.

## Vesper-specific

Adjustment map saved at `vesper_data/split_adjustments.json`.
`app/factors/db.py` provides `fetch_adjusted_ohlcv_rows()` and
`get_split_adjustment()` for transparent integration. Factors
use `fetch_adjusted_ohlcv_rows` in place of `fetch_ohlcv_rows`.

240 splits detected across 174 of 502 tickers (2026-07-14).