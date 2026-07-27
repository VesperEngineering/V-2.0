## Feature Pipeline Optimization

When `calculate_features()` is called per ticker in a loop (30-500 tickers),
the bottleneck is the macro loader (`src/na/data/macro_loader.py`), which is
called per ticker and does expensive alignment each time. Two fixes:

### 1. Deduplicate macro index before reindex

The macro cache can produce duplicate-date entries (from parquet loads with
duplicate indices). The `get_macro_features_for_dates()` function's
`reindex(expanded_index)` call crashes with "cannot reindex on an axis with
duplicate labels." Fix in `macro_loader.py`, after `_normalize_macro_frame()`:

```python
macro_df = macro_df[~macro_df.index.duplicated(keep="last")]
```

One line, eliminates 30 duplicate-label crashes per full analysis run.
Verified with 31/31 transformer + feature test suites passing.

### 2. Timestamp-keyed feature cache

All tickers in Vesper's OHLCV pipeline share the same date index, so the
aligned macro features (shape N×4 for VIX/TNX/oil/USD) are IDENTICAL for
every ticker. Cache by `(start_timestamp, length, backfill_start)`:

```python
_macro_feature_cache: dict[tuple, np.ndarray] = {}

def get_macro_features_for_dates(...):
    cache_key = (int(target_dates[0]), len(target_dates), backfill_start)
    if cache_key in _macro_feature_cache:
        return _macro_feature_cache[cache_key]
    # ... alignment ...
    _macro_feature_cache[cache_key] = result
    return result
```

Reduces per-ticker macro alignment from ~30 calls to 1 call. Combined with
the dedup fix, 30-ticker factor IC analysis completes with zero macro errors
(was 30 failures). Transformer/feature/target test suites pass unchanged.
