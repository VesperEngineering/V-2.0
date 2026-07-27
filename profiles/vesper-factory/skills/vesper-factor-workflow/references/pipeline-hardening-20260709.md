# Pipeline Hardening & Infrastructure — Session 2026-07-09

## Vesper Scheduler — Self-Contained, Hermes-Independent

Built 2026-07-09. Replaces Hermes cron as the primary job scheduler. Supports:
- **Cron expressions** (5-field: `0 8 * * 0-6`)
- **Interval schedules** (`5s`, `30s`, `1m`, `1h`) — sub-second granularity impossible with Hermes cron
- **market_hours_only flag** — only runs during US equity market hours (9:30 AM–4:00 PM ET, weekdays)
- **Subprocess isolation** per job with configurable timeout
- **Per-run log files** at `scheduler/logs/<JobName>_YYYYMMDD_HHMMSS.log`

Entry point: `pythonw scheduler/run.py` (background, no window). Add to Windows startup via `schtasks /create /tn "Vesper Scheduler" /tr "pythonw D:\vesper\scheduler\run.py" /sc onstart`.

### Files
- `scheduler/__init__.py` — Daemon loop (500ms tick), cron + interval parsing, subprocess isolation, per-run logging
- `scheduler/run.py` — Entry point (`--status` for one-shot dump, `--debug` for verbose)
- `scheduler/jobs.json` — 8 job definitions

### Jobs (as of 2026-07-09)
| Name | Schedule | Type | Script |
|---|---|---|---|
| OHLCV Ingest | `0 7 * * 2-6` | cron | `scripts/massive_sp500_ingest.py` |
| Factor Scores | `0 8 * * 0-6` | cron | `scripts/run_all_factors.py` |
| Factor Basket | `15 8 * * 0-6` | cron | `scripts/sector_neutral_basket.py` |
| Alpaca Rebalance | `35 9 * * 1-5` | cron | `scripts/alpaca_rebalance.py` |
| Portfolio Snapshot | `5s` | interval, market hours only | `scripts/alpaca_portfolio.py` |
| Dashboard Refresh | `5s` | interval | `vesper-dashboard/aggregator.py` |
| News Backfill | `0 9 * * 0-6` | cron | `scripts/backfill_news_sentiment.py` |
| Live News | `0 8-17 * * 1-5` | cron | `scripts/live_news.py` |

### Dashboard aggregator integration
`aggregator.py` now reads active jobs and recent activity from scheduler logs:
- `load_active_jobs()` parses `scheduler/jobs.json` for definitions and `scheduler/logs/` for last-run status
- `load_recent_activity()` scans log files, extracts result lines, deduplicates consecutive same-job entries, formats relative timestamps
- No longer reads from `cron_status.json`

## Pipeline Guards — Retry, Never Skip

**User directive: "I don't want anything skipped."** Pipeline jobs must retry/wait for dependencies, never silently skip.

### 1. Basket retry guard
Cron wrapper at `~/AppData/Local/hermes/scripts/vesper_factor_basket.py`:
- Polls every 10s for up to 1 hour (3600s) for factor scores file to appear and be fresh (< 30 min old)
- Only exits with error if 1hr passes with no scores
- Basket job at 8:15 AM will wait until ~9:15 AM for scores if needed
- Rebalance at 9:35 AM always gets a fresh basket

### 2. Rebalance freshness guard
In `scripts/alpaca_rebalance.py` `main()`:
- **Date guard**: Basket filename must contain yesterday's date (`expected_date = today - 1 day`). If not, `sys.exit(1)`.
- **Age guard**: Basket file must be < 90 minutes old (5400s). If older, `sys.exit(1)`.
- Both use `sys.exit(1)` (error), never `sys.exit(0)` (silent skip)

### 3. OHLCV ingest timing
Moved from 7:30 AM to 7:00 AM (cron `0 7 * * 2-6`) to give 1hr head start before scores at 8:00 AM. Previous collision: all three jobs (ingest, scores, basket) bunched up at 8:28 AM.

## Alpaca Sell Order — Exact Quantity, Never Round

`round(qty, 4)` can round UP past the available quantity, causing `insufficient qty available for order` errors.

**Example**: `round(35.909295731, 4)` = 35.9093, but available is 35.909295731 — Alpaca rejects.

**Fix**: Pass raw full-precision `qty` to `MarketOrderRequest(qty=qty)`. Alpaca accepts arbitrary precision. Do NOT use `round()`, `math.floor()`, or any truncation.

## Sector-Neutral Basket — SP500-Only Filter

The basket script MUST filter to S&P 500 tickers only (those with a sector mapping in `data/sp500_sectors.json`).

Without this filter:
- Non-SP500 tickers with only 1 factor at 0.1 weight can outscore SP500 names with 8 factors
- A non-SP500 ticker with no sector mapping gets slotted into "Unknown" sector — the only ticker in that bucket, guaranteeing a basket slot
- Example: X (US Steel) scored 2.36 from only `market_micro` (0.1 weight), outranking SP500 stocks with 8+ factors because the weighted-average denominator dilutes multi-factor scores

**Fix in `sector_neutral_basket.py`**: `sec = sectors.get(tkr); if sec is None: continue` — skip any ticker not in the sector map.

## Fama-MacBeth Script — FRED Data Quirks

When adding FRED macro data to `fama_macbeth.py`:
1. **Header is `observation_date`**, not `DATE` — the free graph CSV endpoint returns this header
2. **Monthly series (UNRATE, CPIAUCSL) need backward-fill** — daily rebalance dates won't match monthly FRED dates. Walk backwards through FRED dates to find the latest available signal for each series ≤ rebalance date.
3. **T10Y2Y is daily** — no backward-fill needed, but forward-fill missing values (holidays)
4. **macro_fred FM result (2026-07-09)**: t=-1.89, borderline miss. Stays at 0.1 informational weight. 35% positive months, negative coefficient.

## market_micro Cannot Be FM-Validated — Data Gap

The Massive normalized DB (`day_aggs_coverage_expanded.sqlite`) has data only for 2003 and 2026 — no 2004-2025 history. This means `compute_market_micro()` produces empty results at most rebalance dates in the FM regression. The factor is live-IC-tracker-only, same as `sec_insider_v2` (SEC Form 4 is real-time, not historical).

## Dead Test Cleanup — 310 → 51 Files

Removed ~260 template/scaffold test files inherited from the project's original template. These tested infrastructure Vesper doesn't use: `qlib_*`, `tree_ranker_baseline_*`, `massive_total_return_model_skill_*`, `cadence_*`, `executive_snapshot_*`, `governance_*`, `operator_*`, etc. Test suite went from 70s with 2 pre-existing failures to 14s with 252/252 passing. If template test files reappear (from merge or scaffold update), delete them.

## Dashboard Tray Icon — pystray

`vesper-dashboard/tray_icon.py` provides a system tray icon using `pystray` + `Pillow`:
- Green dot = server running, red dot = server down
- Health check every 5s via `GET /api/status`
- Auto-starts server if not running
- Right-click menu: Open Dashboard, Restart Server, Exit
- Desktop launcher: `Vesper Dashboard.bat` — starts tray icon + server + opens browser, survives browser close
- Auto-starts on boot via Windows Startup folder

**Pitfall**: Killing all `pythonw.exe` processes kills both the tray icon AND the server. They're separate processes. To restart cleanly: kill by PID (from `netstat -ano | findstr :8080 | findstr LISTENING`), not by image name.

## Dashboard Live Portfolio Endpoint

`/api/portfolio-live` in `server.py` calls Alpaca directly with a 5-second server-side cache. The dashboard JS polls this every 10s during market hours.

**Pitfall**: When modifying `server.py`, you MUST restart the server process — it doesn't hot-reload. Kill by PID, then relaunch with `pythonw server.py --port 8080` or via the tray icon's "Restart Server" menu item.

## STATUS.md — Living Document

`docs/STATUS.md` is the user's go-to reference for project state. Update after every work session. One page: active factors, pending validation, dead factors, pipeline state, portfolio, key rules, next actions. User reads it between sessions to orient.

## Factor Weights — FM-Only Drives Blend (2026-07-09)

`run_all_factors.py` FACTOR_WEIGHTS cleaned to FM-validated only:
- `intraday_range`: 1.0 (FM t=+4.07)
- `mean_reversion`: 0.7 (FM t=+2.03)
- `sp500_technical`: 0.0 (FM t=+0.58, NOT significant — former anchor demoted)
- `massive`: 0.0 (FM t=-0.52, noise)
- `sentiment`: 0.0, `insider`: 0.0 (superseded/unvalidated)
- All unvalidated factors (`sec_insider_v2`, `market_micro`, `macro_fred`, `sec_fundamentals`, `wiki_attention`): 0.1 informational only

**Rule**: Weight 0.1 = parking spot (pending FM). Weight 0.0 = killed (FM-failed). Weight ≥ 0.7 = FM-validated (|t| > 2.0).
