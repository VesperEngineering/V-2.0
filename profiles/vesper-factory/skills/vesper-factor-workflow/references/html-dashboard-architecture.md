# HTML Dashboard Architecture

## Server (`server.py`)
- Binds `0.0.0.0:8080`, serves static + API endpoints
- API endpoints: `/api/refresh` (POST/GET runs aggregator), `/api/status`, `/api/portfolio-live` (Alpaca live data)
- `/api/portfolio-live` uses 30s server-side cache to avoid blocking the single-threaded handler
- Initial cache seeded with `{"equity": None, "loading": True}` to prevent blocking on first call
- Uses `HTTPServer` + custom `DashboardHandler` extending `SimpleHTTPRequestHandler`

## Data flow
1. Cron jobs (`.py` scripts, `no_agent: true`) write factor scores, portfolio snapshots, etc.
2. `aggregator.py` reads all data sources → `dashboard_data.json` (200KB with 512-ticker all_factors)
3. `data-binder.js` fetches `dashboard_data.json` every 5s during market hours, 60s off-hours
4. JS calls `/api/refresh` (POST) on the same cadence to keep aggregator fresh
5. JS calls `/api/portfolio-live` every 10s for live Alpaca P&L during market hours

## Cache busting
- DO NOT use `?v=N` query params — Python's http.server treats `?` as part of the filename
- Instead: copy JS to `data-binder-vN.js` (increment N on each change) and update `<script src>` in HTML
- Use Python string replace, not `patch` tool (patch mangles compact code)
- Verify with `node -c` after each change

## "Still nothing" debugging checklist
1. Is server running? `netstat -ano | grep :8080`
2. API working? `curl http://127.0.0.1:8080/api/status`
3. JS serving? `curl http://127.0.0.1:8080/data-binder-vN.js`
4. JS syntax? `node -c data-binder-vN.js`
5. HTML has correct `<script src="data-binder-vN.js">`?
6. **"use strict" bug**: any undeclared variable assignment in the IIFE throws ReferenceError, crashes ALL rendering silently. Declare with `var` at top of IIFE.
7. Add visible debug counter: `LOAD_COUNT` incrementing in header confirms JS is running

## Timestamps
- All data stored in UTC. JS converts to ET via `fmtTime()`:
  - Parses HH:MM, subtracts 4h (EDT) or 5h (EST), converts to 12h AM/PM
- Recent Activity uses `relTime()` showing "3m ago", "2h ago", ticking every 1s via `tickRelTimes()`
- 1s intervals: `tickMarketClock`, `tickUpdateCounter`, `tickRelTimes`

## Compact layout
- Override CSS variables at end of stylesheet: `--header-height: 32px`, `--footer-height: 28px`
- Metric cards: padding 8px (was 20px), font 18px (was 24px)
- Table cells: padding 2px (was 5px), font 10px (was 11px)
- All gaps halved, sidebar narrowed to 180px

## Live portfolio
- `renderPortfolioLive()` updates equity, P&L, positions from `/api/portfolio-live`
- `renderBasketLive()` replaces Selected Basket with actual Alpaca positions + live P&L
- Both called from 10s polling interval during market hours

## Active Jobs sorting
- `renderActiveJobs()` sorts by actual next run time (accounts for day-of-week: Mon, M-F, T-S)
- Shows countdown column: "3h 15m", "5d 12h"
- Uses `nextRunMs()` to parse "HH:MM [dow]" into actual datetime
