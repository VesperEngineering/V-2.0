# Vesper Session 2026-07-09 — Scheduler, Pipeline Guards, Dashboard, FM Sprint

## Vesper Scheduler (self-contained daemon)

Built `scheduler/` to replace Hermes cron dependency. Supports cron expressions and interval schedules (5s, 30m, 1h). Market-hours-only flag for intraday jobs. 500ms tick loop, subprocess isolation per job.

**Files:**
- `scheduler/__init__.py` — daemon, Job class, cron/interval parsing, market hours detection
- `scheduler/run.py` — entry point (`pythonw` for background, `--status` for one-shot)
- `scheduler/jobs.json` — 8 jobs: OHLCV (7AM cron), Scores (8AM), Basket (8:15AM), Rebalance (9:35AM), Portfolio (5s interval, market hours), Dashboard Refresh (5s), News (9AM), Live News (hourly 8-5)
- `scheduler/logs/` — per-run logs `<JobName>_YYYYMMDD_HHMMSS.log`
- `docs/scheduler-reference.md` — full reference

**Live test:** Portfolio snapshot fired every 5s (0.9s each), dashboard refresh every 5s. 8 jobs loaded and parsed correctly.

## Pipeline Guards

### Basket retry guard (`vesper_factor_basket.py` wrapper)
Polls for `factor_scores_YYYYMMDD.json` every 10s for up to 1 hour. Requires file <30min old. If scores slip late, basket waits and generates when ready. No more skipped baskets.

```python
MAX_WAIT = 3600  # 1 hour — retry until 9:15 AM
POLL = 10       # check every 10 seconds
```

### Rebalance freshness guard (`alpaca_rebalance.py`)
Two guards:
1. **Date guard**: basket filename must contain expected date (today - 1)
2. **Freshness guard**: basket file must be < 90 minutes old

Both exit with error code 1 (not silent skip).

### OHLCV ingest moved to 7:00 AM
Was 7:30 AM, collided with scores at 8:00. Now 1hr head start.

## Sector-Neutral Basket — SP500 Filter

`sector_neutral_basket.py` must skip tickers not in `sp500_sectors.json`. Without filter, non-SP500 stocks with 1 factor at 0.1 weight outscore SP500 names with 8+ factors (smaller denominator in weighted average). Example: X (US Steel) with only `market_micro` stole a basket slot, got "Unknown" sector.

Fix:
```python
sec = sectors.get(tkr)
if sec is None:
    continue  # skip non-SP500 tickers
```

## Alpaca Sell Order — Exact Quantity

`round(qty, 4)` rounds UP when 5th decimal ≥ 5, causing `insufficient qty available` errors. Fix: pass raw `qty` directly.

```python
# WRONG — round up can exceed available
req = MarketOrderRequest(symbol=ticker, qty=round(qty, 4), ...)

# CORRECT — exact precision
req = MarketOrderRequest(symbol=ticker, qty=qty, ...)
```

## FM Regression — macro_fred and market_micro

Extended `fama_macbeth.py` with:
- `load_fred_data()` — fetches T10Y2Y, UNRATE, CPIAUCSL from FRED graph CSV (free, no API key)
- `compute_macro_fred()` — sector-conditional exposure maps, backward-fill for monthly data
- `load_normalized()` + `compute_market_micro()` — Amihud, turnover, VWAP from normalized DB

**Results (169 regressions, 2005-2026):**
- macro_fred: t = -1.89 (borderline miss, stays at 0.1)
- market_micro: could not compute — normalized DB only has 2003 + 2026 data
- sec_insider_v2: cannot FM-validate — SEC Form 4 is real-time only

**FRED CSV header gotcha:** Uses `observation_date`, not `DATE`. Filter: `if row[0] in ("observation_date", "DATE"): continue`

**Timezone pitfall:** `datetime.strptime` returns naive datetime. Must `.replace(tzinfo=_ET)` before subtracting from aware `now`.

## Factor Weights — FM-Calibrated

`FACTOR_WEIGHTS` in `run_all_factors.py` updated to reflect FM results:
- 2 primary (intraday_range 1.0, mean_reversion 0.7)
- 3 zeroed (sp500_technical, massive, insider/sentiment)
- 5 informational at 0.1 (sec_fundamentals, wiki_attention, sec_insider_v2, market_micro, macro_fred)

Also added `FACTOR_TIMEOUTS` entries for sec_insider_v2 (180s), market_micro (15s), macro_fred (30s).

## Dashboard Updates

### Live portfolio endpoint (`/api/portfolio-live`)
`server.py` — fetches live from Alpaca API, 5s server-side cache. JS polls every 10s during market hours.

### Tray icon (`tray_icon.py`)
pystray icon — green/red "VD" text, auto-restarts server if down, right-click menu. Desktop launcher: `Vesper Dashboard.bat` (also in Windows Startup folder).

### Aggregator reads scheduler logs
`load_active_jobs()` and `load_recent_activity()` now parse `scheduler/logs/` instead of `cron_status.json`. Shows 8 Vesper Scheduler jobs, real run logs with relative timestamps, deduplicated.

## Test Cleanup

~260 dead template test files removed. ~310 → 51 files. 252 tests passing in ~13s (was 70s+ with failures).

## Documents Created

- `docs/STATUS.md` — living project status board (factors, pipeline, portfolio, rules, next actions)
- `docs/vesper_strategy_analysis_20260708.md` — full strategy report (architecture, FM results, roadmap, alignment with top quant firms)
- `docs/scheduler-reference.md` — scheduler docs
