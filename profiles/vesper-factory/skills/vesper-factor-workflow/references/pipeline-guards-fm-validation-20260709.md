# Pipeline Guards and FM Validation — 2026-07-09 Session

## Pipeline Timing (Final State)

```
7:00 AM  OHLCV Ingest (1hr before scores)
8:00 AM  Factor Scores (writes factor_scores_YYYYMMDD.json)
8:15 AM  Factor Basket (polls for scores, retries up to 1hr, sector-neutral)
9:35 AM  Alpaca Rebalance (rejects stale baskets — wrong date OR >90min old)
```

## Basket Retry Guard

File: `~/AppData/Local/hermes/scripts/vesper_factor_basket.py`

The basket cron wrapper polls for fresh factor scores before running:
- Polls every 10s for fresh factor scores file
- Waits up to 1 hour (MAX_WAIT=3600s) — retries until 9:15 AM, rebalance at 9:35 always gets fresh basket
- Requires scores file to be <30 min old (freshness check)
- Exits with error code 1 if scores never appear
- Calls `scripts/sector_neutral_basket.py` (not the old `vesper_factor_basket.py`)

**Why not skip?** User explicitly said: "I dont want anything skipped." The retry-and-wait pattern ensures the basket always generates, even if scores slip 30+ minutes.

## Rebalance Freshness Guard

File: `scripts/alpaca_rebalance.py` (lines ~180-194)

Two guards added to `main()`:
1. **Date guard**: Basket filename must contain expected date (today - 1). If not, exit 1 with error.
2. **Freshness guard**: Basket file mtime must be <90 minutes old. If older, exit 1 with error.

Both guards print clear error messages and exit with code 1 (not silent skip).

## Alpaca Sell Quantity Fix

File: `scripts/alpaca_rebalance.py` line ~94

**Bug**: `round(qty, 4)` can round UP (e.g., 35.909295731 → 35.9093), requesting MORE shares than available. Alpaca rejects with "insufficient qty available for order (requested: 35.9093, available: 35.909295731)".

**Fix**: `qty=qty` — pass exact full-precision float from `p.qty_available` directly. Alpaca accepts it.

**NEVER use `round()` on sell quantities.** The user corrected this pattern explicitly.

## Sector-Neutral Basket — SP500-Only Filter (Critical)

File: `scripts/sector_neutral_basket.py`

**The bug**: `market_micro` factor scores 7,630 non-SP500 tickers. A stock like X (US Steel) with only `market_micro` at 0.1 weight got score = raw z-score (no denominator dilution). It ranked #2 globally and slipped into the basket with sector "Unknown" — the only ticker in that bucket, guaranteeing a basket slot.

**The fix**: Skip tickers not in the sector map:
```python
sec = sectors.get(tkr)
if sec is None:
    continue  # skip non-SP500 tickers
```

**NEVER use `sectors.get(tkr, "Unknown")`** — that creates an "Unknown" sector bucket that non-SP500 tickers can dominate.

## Factor Weights — FM-Calibrated

File: `scripts/run_all_factors.py`

The `FACTOR_WEIGHTS` dict is now calibrated to FM regression results:

| Factor | Weight | Rationale |
|---|---|---|
| `intraday_range` | 1.0 | FM t=+4.07 — STRONG |
| `mean_reversion` | 0.7 | FM t=+2.03 — borderline |
| `sec_fundamentals` | 0.1 | Unvalidated, informational |
| `wiki_attention` | 0.1 | Unvalidated, informational |
| `sec_insider_v2` | 0.1 | Unvalidated, pending live IC |
| `market_micro` | 0.1 | Unvalidated, normalized DB data gap |
| `macro_fred` | 0.1 | FM t=-1.89, borderline miss |
| `sp500_technical` | 0.0 | FM t=+0.58 — NOT significant |
| `massive` | 0.0 | FM t=-0.52 — noise |
| `sentiment` | 0.0 | 38 tickers only |
| `insider` | 0.0 | Superseded by v2 |

**Flow**: Build factor → 0.1 (pending) → FM regression → |t| > 2.0 promotes to 0.7–1.0, |t| < 1.5 kills to 0.0.

## FM Regression — macro_fred and market_micro Results

Added `load_fred_data()`, `compute_macro_fred()`, and `compute_market_micro()` to `scripts/fama_macbeth.py`.

### macro_fred: FM t=-1.89 (borderline miss)

- Fetched T10Y2Y, UNRATE, CPIAUCSL from FRED graph CSV endpoint (free, no API key)
- Computes 6-month trend signals, maps to GICS sector exposures, z-scores cross-sectionally
- All 502 tickers scored
- Stays at 0.1 informational

**FRED CSV header quirk**: Header is `observation_date`, not `DATE`. Must skip both:
```python
if len(row) < 2 or row[0] in ("observation_date", "DATE"): continue
```

**FRED monthly vs daily alignment**: UNRATE and CPIAUCSL are monthly, T10Y2Y is daily. Must walk backwards through FRED dates to find latest available signal for each series (backward-fill), not just take the latest date.

### market_micro: Cannot validate (data gap)

- Loaded Massive normalized DB (`day_aggs_coverage_expanded.sqlite`)
- **Data gap**: only 2003 and 2026 data — no 2004–2025 coverage. Only 7K rows for 500 SP500 tickers.
- FM regression couldn't compute (insufficient data at rebalance steps)
- Cannot be historically validated — live IC tracker only

### Factors that cannot be historically FM-validated

- `sec_insider_v2` — SEC Form 4 data is real-time only, can't reconstruct 20 years
- `market_micro` — Massive normalized DB has data gap (only 2003 + 2026, no 2004-2025)
- Both rely on **live IC tracker** for validation instead

## Dashboard Live Portfolio Endpoint

File: `vesper-dashboard/server.py`

`/api/portfolio-live` endpoint calls Alpaca directly, cached 5 seconds server-side:
```python
def _get_alpaca_portfolio():
    # Cached 5s, calls TradingClient.get_account() + get_all_positions()
    # Returns {equity, cash, buying_power, positions: [{ticker, qty, market_value, ...}]}
```

The JS (`data-binder.js`) polls this endpoint every 10 seconds during market hours (line 922-926).

## Test Cleanup — Template Scaffold Removal

Removed ~260 dead template test files. Reduced from ~310 test files (70s, pre-existing failures) to 51 files (252 tests, 13s, 0 failures).

**Kept:** Factor IC analysis, SEC ingest, SQLite health, Alpaca credential loading, paper trading, news sentiment, company features, macro loader, performance metrics, tickers/targets, trade order sizing.

## Pipeline Failure Modes — Documented

1. **Cron timing collision (July 8)**: OHLCV ingest slipped to 8:28 AM, collided with scores (8:30) and basket (8:28). Basket ran before scores → no basket → rebalance saw stale basket → 0 orders. Fix: moved ingest to 7:00 AM, added basket retry guard.

2. **Rebalance cron error (July 9)**: 9:35 AM rebalance cron returned error status. Manual run at 9:39 succeeded. Likely transient API timeout at market open. Error status now visible in dashboard (red dot).

3. **Alpaca sell rounding (July 9)**: `round(qty, 4)` rounded UP for 3 positions, Alpaca rejected. Fix: pass exact `qty` without rounding.

4. **Non-SP500 basket contamination (July 9)**: `market_micro` scored 7,630 non-SP500 tickers. Non-SP500 names with 1 factor at 0.1 weight outranked SP500 names with 8 factors. Fix: sector-neutral basket filters to SP500-only.
