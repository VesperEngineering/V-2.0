# Vesper Dashboard v2.1 — SPA Architecture (2026-07-07)

The HTML dashboard at `C:\Users\bgonn\vesper-dashboard\` is a single-window SPA.
**User preference (explicit)**: ONE window with sidebar view switching; Logs and
Settings additionally get "Pop Out" buttons opening separate chrome-less browser
windows for side-by-side debugging. Do NOT build separate apps/pages.

## File roles
- `index.html` — static shell (dashboard bento grid + sidebar + footer). Bump the
  cache-buster `<script src="data-binder.js?v=N">` on EVERY data-binder change or
  the browser serves the stale script and "nothing changes".
- `data-binder.js` — all logic. IIFE, no framework. Exports `window.VesperDashboard
  = {loadData, callApi, showView}`.
- `aggregator.py` — writes `dashboard_data.json` (both to `D:\vesper\vesper-dashboard\`
  and the serving dir `C:\Users\bgonn\vesper-dashboard\`). Run by cron every 30m
  and by `/api/refresh`.
- `server.py` — static + API on :8080. Subprocesses use `sys.executable` (Hermes
  venv). `run-pipeline` timeout must be ≥300s (insider factor scans full universe).

## SPA view switching pattern
- `ensureViewHost()` snapshots the original `.main` children (dashboard panels)
  into `dashboardNodes`, appends a hidden `#spa-view-host` div.
- `showView(name)`: toggles `.nav-item.active` by button text, hides/shows
  dashboardNodes vs viewHost, calls `renderView(name)` for non-Dashboard views.
- Views render from `LAST_DATA` (module-level cache of last fetched JSON) so
  switching is instant; `loadData()` re-renders the current view after each poll.
- Panel-footer buttons map to views: `{"View All Factors": "Factors", "View All
  Jobs": "Jobs", "View Portfolio": "Portfolio", "Manage Basket": "Basket",
  "View All Data": "Logs", "View Full Logs": "Logs"}`; "More" → Settings.

## Pop-out mode
`popOut(view)` opens `?view=X&popout=1` via `window.open` (980x760, no toolbar).
On init `applyPopoutMode()` reads URL params; popout=1 hides `.sidebar` and
`.footer`; the view renders after first data load (via `pendingView`).

## Minute-by-minute refresh (v2.1, 2026-07-07)
During market-hours the dashboard polls every **15s** (not the fixed 30s/60s from
Settings). `restartRefreshTimer()` calls `usMarketState(new Date()).isOpen` and
sets 15s open / 60s closed. The Settings dropdown still overrides the base interval
(15s min).

A "Updated Xs ago" counter appears next to the header timestamp, driven by
`tickUpdateCounter()` on a 1s interval — this gives real-time feel without SSE.
The counter resets every `loadData()` call. The header timestamp itself (`last_update`
from dashboard_data.json) is refreshed on each poll.

## FinViz sentiment column
`finviz_sentiment` (Yahoo-backed, 500+ tickers) is mapped to "Sent" in the Factors
view labels alongside the old `sentiment` (WebZ, 38 tickers). The aggregator prefers
`finviz_sentiment` over `sentiment` in the leader board `sent` column.

## CRITICAL pitfall: live vs baked data
Anything time-sensitive (market OPEN/PRE-MARKET/CLOSED badge, countdown) MUST be
computed live in the browser (`tickMarketClock()`, 1s interval) — NOT read from
`dashboard_data.json`, which only refreshes on the 30-min cron. This exact bug
caused "PRE-MARKET" showing after open and contradictory countdowns.

DST-aware ET session logic (in JS): compute 2nd-Sunday-March / 1st-Sunday-November
DST bounds, ET = UTC-4 (DST) or UTC-5; session minutes: OPEN 570–960 (9:30–16:00),
PRE 240–570, AFTER 960–1200, else CLOSED; weekday check on ET date.

## Data payload sections (aggregator v2.1)
- `factor_leaders.leaders[]` — keys are now `tech/fund/wiki/sent/insider/massive`
  (honest names). data-binder has back-compat fallback to old `entropy/hurst/vol`.
- `all_factors` — `{rows: [{rank,ticker,score,n_factors,<factor cols>}], factors: [names], date}`
  full 512-row table for the Factors view (client-side sort + ticker search).
- `portfolio` — REAL data from newest `artifacts/evals/alpaca_portfolio_*.json`
  (`account` + `positions`); `equity_history` from last 30 snapshots drives the
  sparkline + Portfolio-view equity curve. The old hardcoded mock is gone — never
  reintroduce mock fallbacks that mask missing data.
- `logs` — latest output file per cron job from
  `C:/Users/bgonn/AppData/Local/hermes/cron/output/<job_id>/` (title parsed from
  `# Cron Job:` header line, 3000-char tail). Powers the Logs view.

## Action feedback (footer buttons)
`callApi()` opens a floating `#action-output` panel (fixed bottom-right) and
prints per-step results (`result.steps[]` → "✓ step\noutput"). Never rely on
button-text flicker alone as feedback for a 90s+ pipeline run.

## Factors view interaction details
- Sort state in module vars `FACTOR_SORT {col,dir}`, filter in `FACTOR_FILTER`.
- Search input re-renders on every keystroke — must save/restore focus +
  `selectionStart` or the input loses focus after one character.
- Column labels map: sp500_technical→Tech, sec_fundamentals→Fund,
  wiki_attention→Wiki, sentiment→Sent, insider→Insider, massive→Massive.

## Settings view
Refresh interval persisted to `localStorage["vesper.refreshMs"]`; factor weights
displayed read-only (source of truth = `scripts/run_all_factors.py::FACTOR_WEIGHTS`).
