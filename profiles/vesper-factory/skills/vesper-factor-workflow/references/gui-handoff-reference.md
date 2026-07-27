# Vesper Dashboard GUI — Handoff Reference

> Use this doc to re-establish context on the dashboard when starting a new
> session or handing off to another agent. The dashboard is the user's primary
> surface for monitoring the autonomous quant system.

## Where it lives
`C:\Users\bgonn\vesper-dashboard\` — served by `server.py` on `0.0.0.0:8080`.
Source also mirrored at `D:\vesper\vesper-dashboard\` for git tracking.

## Current state (v2.1, 2026-07-07)

### What works
- **7-panel Dashboard view**: Factor Leaders (10 rows), Active Jobs (12 jobs),
  Portfolio/Alpaca (real equity + positions from artifact snapshots), Selected
  Basket (top-4), Today's Data (9 data sources), Recent Activity (4 entries)
- **SPA sidebar nav**: 7 views — Dashboard / Factors / Basket / Portfolio /
  Jobs / Logs / Settings — all with live data from `dashboard_data.json`
- **Factors view**: Full 512-row table, click-to-sort columns, ticker search
- **Portfolio view**: Equity curve SVG (from equity_history), positions table
  with unrealized P/L (real data from artifacts/evals/alpaca_portfolio_*.json)
- **Logs view**: Collapsible latest cron output per job, Pop Out button opens
  chrome-less window at `?view=Logs&popout=1`
- **Settings view**: Refresh interval selector (localStorage), factor weights
  reference, Pop Out button
- **Live market clock**: DST-aware ET session, 1s tick updates, "Updated Xs ago"
  counter next to timestamp
- **Market-adaptive refresh**: 15s during open hours, 60s during closed
- **Footer action buttons**: Refresh / Run Pipeline / Rebalance / Run All Jobs
  — all call `/api/*` endpoints, show floating output panel with per-step results
- **Portfolio data is REAL**: reads newest `artifacts/evals/alpaca_portfolio_*.json`,
  builds equity_history from last 30 snapshots, shows day_change from account data

### What was recently fixed
- **Market status**: NO LONGER baked into `dashboard_data.json` (was stale 30min).
  Now computed live in browser (`data-binder.js::tickMarketClock()`, 1s tick).
- **Column headers**: TECH/FUND/WIKI (honest names), not Entropy/Hurst/Vol.
- **Today's Data**: dead Google Trends and Whale 13F removed; SEC Fundamentals,
  Live News, OHLCV Ingest added.
- **Button feedback**: floating `#action-output` panel, not silent flicker.
- **Hardcoded mock killed**: Portfolio was showing fake $106,578.48 — now reads
  real snapshots ($106,053.75 as of 2026-07-07).
- **Morning Briefing + Model Research** agent jobs pinned to deepseek-v4-flash
  (were failing on model-drift guard).
- **All 12 cron jobs**: 10 running successfully, 2 agent jobs pinned (run at
  06:00/06:30 daily).

### Key files
| File | Role |
|---|---|
| `server.py` | Flask-like static + API server on :8080 |
| `aggregator.py` | Reads vesper artifacts → `dashboard_data.json` (also mirrored to C:) |
| `data-binder.js` | All frontend logic (SPA, render, API calls, clock) |
| `index.html` | Static shell (sidebar + bento grid + footer) |
| `dashboard_data.json` | Live data payload (regenerated every 15-30 min) |

### cache-buster rule
Every change to `data-binder.js` must bump `?v=N` in index.html's script tag:
```html
<script src="data-binder.js?v=3"></script>
```
Without this, the browser serves the old JS from cache and "nothing changes."

### Architecture notes
- `data-binder.js` is an IIFE that exports `window.VesperDashboard = {loadData, callApi, showView}`
- Views render from `LAST_DATA` (module-level cache of last fetch) — switching is instant
- Pop-out mode: `?view=X&popout=1` hides `.sidebar` and `.footer`
- Panel-footer buttons map: View All Factors→Factors, View All Jobs→Jobs, etc.
- "More" button → Settings view

### Known issues / backlog
1. **Equity curve needs data**: only ~2 snapshot points so far — becomes meaningful
   after a week of 20:00 M-F Portfolio Snap cron runs. No fix needed, just time.
2. **FinViz sentiment factor not yet in pipeline output**: YahooSentimentFactor
   registered in the registry but a full pipeline run hasn't been tested since.
   Run `cd /d/vesper && $PY scripts/run_all_factors.py` to verify.
3. **Minute-by-minute == 15s poll**: not true SSE/streaming. The user wanted to
   "see data flowing in faster." 15s during market hours was the pragmatic fix.
   True SSE/WebSocket streaming could be built but isn't demanded.
4. **Dashboard SCHEDULE static**: The cron job list in the dashboard is not
   auto-generated — it comes from `sync_cron_status.py` (no_agent, every 15m).
   Don't manually update a hardcoded dict.
5. **Portfolio snapshot path**: Ensure `scripts/alpaca_portfolio.py` runs at 20:00 M-F.
   It was successfully reading artifact files as of last check.
