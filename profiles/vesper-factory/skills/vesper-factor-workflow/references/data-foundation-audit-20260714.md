# Vesper Data Foundation Audit — 2026-07-14

Read-only audit by Data Steward (Thomas). Paper-only, fail-closed.

## Active Data Storage Paths

| Path | Type | Schema | Rows | Date Range | Status |
|------|------|--------|------|------------|--------|
| `vesper_data/massive/sp500/sp500_ohlcv.sqlite` | SQLite | `sp500_ohlcv(ticker TEXT, date TEXT, close REAL, volume REAL, open REAL, high REAL, low REAL)` | 2,479,293 | 2003-09-10 → 2026-07-10 | ✅ Primary active |
| `vesper_data/market_data/sqlite-analyst.db` | SQLite | `ohlcv_data(ticker, timestamp INTEGER, open, high, low, close, volume, timeframe)` | 5,031 | 2020-01-02 → 2026-01-09 | ⚠️ Legacy |
| `vesper_data/market_data/cache_macro_yq.parquet` | Parquet | Macro (VIX, TNX, oil, USD) | ~2y lookback | Last write Jan 12 2026 | Macro cache |
| `vesper_data/sp500_tickers.json` | JSON | `{"tickers": "A,AAPL,..."}` | 502 tickers | 2026-07-07 snapshot | Universe |
| `vesper_data/sp500_sectors.json` | JSON | `{"AAPL": "Information Technology", ...}` | 502 tickers | Current Wikipedia scrape | Sectors |
| `vesper_data/factor_scores_YYYYMMDD.json` | JSON | Scored tickers + factor details | 1,249-8,057 tickers | Per-run | Factor artifacts |
| `vesper_data/massive/adjusted/` | SQLite | Adjusted + total-return day aggs | 2,712 rows | Limited universe | Unused by factors |
| `vesper_data/massive/total_return/` | SQLite | Total-return adjusted day aggs | 2,712 rows | Limited universe | Unused by factors |
| `vesper_data/massive/reference/` | SQLite | Corporate actions (splits, dividends) | 33 tickers | Reference only | Unused by factors |
| `vesper_data/massive/normalized/` | SQLite | Expanded coverage (19K+ tickers) | Varies | Year-partitioned | Used by market_micro only |

Active data symlink: `data → vesper_data` (Windows junction)

## Finding 1: Raw Unadjusted Prices with Split Jumps (CRITICAL)

**The primary OHLCV database contains raw, unadjusted prices.** Stock splits create ~90% price drops that factors interpret as real negative returns.

**Reproduction proof — NVDA 10:1 split (June 7→10, 2024):**
```
NVDA 2024-06-07: close=1208.88  (pre-split)
NVDA 2024-06-10: close=121.79   (post-split, ~90% non-economic drop)
```

**All 11 factors read raw prices from this DB — none use adjusted data:**

| Factor | File | Line | DB Path |
|--------|------|------|---------|
| mean_reversion | `app/factors/mean_reversion.py` | L:35 | `sp500_ohlcv.sqlite` |
| intraday_range | `app/factors/intraday_range.py` | L:30 | `sp500_ohlcv.sqlite` |
| massive_intraday | `app/factors/massive_intraday.py` | L:34 | `sp500_ohlcv.sqlite` |
| channel_breakout | `app/factors/channel_breakout.py` | via db.py | `sp500_ohlcv.sqlite` |
| gap_volatility | `app/factors/gap_volatility.py` | via db.py | `sp500_ohlcv.sqlite` |
| gv_cb_interaction | `app/factors/gv_cb_interaction.py` | via db.py | `sp500_ohlcv.sqlite` |
| size_factor | `app/factors/size_factor.py` | via db.py | `sp500_ohlcv.sqlite` |
| max_return | `app/factors/max_return.py` | via db.py | `sp500_ohlcv.sqlite` |
| range_vol_ratio | `app/factors/range_vol_ratio.py` | via db.py | `sp500_ohlcv.sqlite` |
| sp500_technical | `app/factors/sp500_technical.py` | L:14 | `sp500_ohlcv.sqlite` |
| massive (legacy) | `app/factors/massive.py` | L:24 | `sp500_ohlcv.sqlite` |

**Adjusted data exists but is unused:** `vesper_data/massive/adjusted/` and `vesper_data/massive/total_return/` contain split/dividend adjustment factors, but only 2,712 rows for a tiny active universe. No factor reads from them.

**Impact:** Every stock that split (NVDA, AMZN, GOOGL, AAPL, TSLA, etc.) generates false returns, false volatility, false ATR, false stop triggers. The backtest skill warns about this — and the live system is doing it.

## Finding 2: Cross-Universe Score Merging (CRITICAL)

**`market_micro` reads from a different database** (`day_aggs_coverage_expanded.sqlite`, 19K+ tickers across all US exchanges) while other factors read from `sp500_ohlcv.sqlite` (502 S&P 500 tickers). The score combiner at `scripts/run_all_factors.py` L:327-345 merges ALL tickers from ALL factors into a single cross-sectional z-score ranking.

**Evidence:**
- July 10 factor scores: 8,057 tickers scored (not 502)
- Top 3: `IAUX` (small-cap gold miner), `TSM` (ADR), `ALIT` (mid-cap) — none are S&P 500 constituents
- `market_micro` brings its own universe; the weighted-average blend uses the union

**Impact:** Market-cap-agnostic microstructure signals (Amihud illiquidity, spread-based measures) will put nano-caps at extremes of every z-scored ranking. Cross-sectional scores across different universes are statistically incomparable.

## Finding 3: No Point-in-Time Membership / No Delisting Tracking (HIGH)

- `sp500_tickers.json`: built from Wikipedia's *current* constituent table on 2026-07-07
- `sp500_sectors.json`: same Wikipedia scrape, no historical membership dates
- No file tracks when tickers entered/left the S&P 500
- No delisting flags anywhere
- `security_master` table is defined in `sqlite_loader.py` but has zero populated rows
- `massive_reference_corporate_actions_*.sqlite` covers only 33 tickers

**Survivorship bias:** Any backtest using the full 2003-2026 history with current constituents excludes delisted, acquired, and removed stocks — overstating historical returns.

## Finding 4: Dual SQLite Infrastructure (MEDIUM)

Two parallel tracking systems with diverging schemas:
- **Active:** `sp500_ohlcv.sqlite` — TEXT dates, 2.48M rows, 502 tickers
- **Legacy:** `sqlite-analyst.db` — INTEGER timestamps, 5,031 rows, `ohlcv_data` table
- `deploy/src/na/data/loader.py` queries the legacy schema (dead code path)
- `scripts/build_sp500_db.py` outputs to a third path (`artifacts/db/sp500_ohlcv.db`) with yet another schema (`ohlcv_1d`)

## Finding 5: Duplicate Ingest Scripts (LOW/MEDIUM)

| Script | Output | Status |
|--------|--------|--------|
| `scripts/massive_sp500_ingest.py` | `vesper_data/massive/sp500/sp500_ohlcv.sqlite` | Active (backup_pipeline) |
| `scripts/build_sp500_db.py` | `artifacts/db/sp500_ohlcv.db` | Stale, hardcoded date 2026-07-06 |
| `scripts/backfill_sp500_history.py` | `sp500_ohlcv.sqlite` (history) | Manual only |

## Finding 6: Macro Data — No Vintage Tracking (LOW)

- Macro loader: `deploy/src/na/data/macro_loader.py` — yahooquery, free, no API key
- Cache: `cache_macro_yq.parquet`, 12-hour freshness window
- No versioning, provenance, or revision tracking
- In-memory global `_MEMOIZED_MACRO_DF` — no audit trail for which vintage was used

## Freshness Architecture

**Strong guard:** `scripts/run_all_factors.py` L:118-140 — `resolve_signal_date()` requires `MAX(date)` from OHLCV DB equals previous XNYS session. Pipeline fails closed if stale.

**Gaps:**
- Only 5 lines in `factor_score_history.jsonl` (Jul 6-10)
- No automated freshness report for macro, sector, or insider data
- No timestamp/vintage audit trail for any non-OHLCV source

## Reproduction Commands (Read-Only)

```bash
# Verify raw prices with split jumps
python -c "import sqlite3; c=sqlite3.connect('D:/vesper/vesper_data/massive/sp500/sp500_ohlcv.sqlite'); print(c.execute(\"SELECT date,close FROM sp500_ohlcv WHERE ticker='NVDA' AND date BETWEEN '2024-06-07' AND '2024-06-10'\").fetchall())"

# Verify universe leakage
python -c "import json; s=json.load(open('D:/vesper/vesper_data/factor_scores_20260710.json')); sp=set(json.load(open('D:/vesper/vesper_data/sp500_tickers.json'))['tickers'].split(',')); sc=set(x['ticker'] for x in s['scored']); print(f'Total scored: {len(sc)}, SP500: {len(sp)}, Outside: {len(sc-sp)}')"

# Verify adjusted data is unused by any factor
grep -rn "adjusted\|total_return\|corporate_action" app/factors/*.py scripts/run_all_factors.py

# Verify security_master is empty
python -c "import sqlite3; c=sqlite3.connect('D:/vesper/vesper_data/market_data/sqlite-analyst.db'); print('tables:', [r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()])"
```