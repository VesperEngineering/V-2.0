# HTML Dashboard (Standalone) — Live Data Pipeline

A self-contained HTML dashboard for Vesper that serves at `http://localhost:8080`
and auto-refreshes with live data from Vesper's JSON output files.

## File Layout

```
C:\Users\bgonn\vesper-dashboard\
├── index.html              # Dashboard UI (1,500 lines, 37 KB, pure HTML/CSS)
├── data-binder.js          # Live data binding (8 KB, no framework deps)
├── aggregator.py           # Python data pipeline (17 KB)
└── dashboard_data.json     # Auto-generated JSON consumed by frontend

D:\vesper\vesper-dashboard\
└── dashboard_data.json     # Mirror copy (written by aggregator)
```

## Architecture

```
D:\vesper\data\factor_scores_*.json ──┐
D:\vesper\artifacts\evals\vesper_factor_basket_*.md ──┤
D:\vesper\artifacts\evals\daily_no_order_report_*.md ──┤
D:\vesper\data\insider_trades\*.json ──┤
D:\vesper\data\news_sentiment\*.json ──┤  aggregator.py  →  dashboard_data.json
D:\vesper\data\google_trends\*.json ───┤
D:\vesper\data\wiki_attention\*.json ──┤
D:\vesper\data\whale_13f\*.json ───────┘
                                              │
                                              ▼
                                    data-binder.js (fetch + render)
                                              │
                                              ▼
                                    index.html (live dashboard)
```

## How to Run

```bash
# 1. Start the dashboard server (unified static + API)
cd C:\Users\bgonn\vesper-dashboard && python server.py --port 8080

# 2. Generate fresh data
python aggregator.py

# 3. Open browser
http://localhost:8080
```

The dashboard auto-refreshes every 30 seconds via `setInterval` in `data-binder.js`.
A cron job (`9f351f5960d3`) runs the aggregator every 30 minutes.

## Dashboard Server (`server.py`)

Replaces `python -m http.server 8080` with a unified server that serves static
files AND API endpoints for the footer action buttons. Binds to `0.0.0.0:8080`
to avoid IPv6-only binding issues on Windows.

### API Endpoints

| Endpoint | Method | Action |
|----------|--------|--------|
| `/api/status` | GET | Health check |
| `/api/refresh` | GET/POST | Run aggregator, return result |
| `/api/run-pipeline` | POST | Factor scores → basket → aggregator |
| `/api/rebalance` | POST | Run Alpaca rebalance |
| `/api/run-all-jobs` | POST | Refresh aggregator |

### Footer Button Wiring

```html
<button class="btn" onclick="window.VesperDashboard.loadData()">Refresh</button>
<button class="btn" onclick="window.VesperDashboard.callApi('run-pipeline', this)">Run Pipeline</button>
<button class="btn" onclick="window.VesperDashboard.callApi('rebalance', this)">Rebalance</button>
```

```javascript
// data-binder.js exports:
window.VesperDashboard = {
  loadData: loadData,     // re-fetch dashboard_data.json
  callApi: callApi,       // POST to /api/<endpoint>, show "✓ Done" / "✗ Error"
};
```

`callApi()` disables the button during the request, shows "⏳ Working...", then
"✓ Done" (green) or "✗ Error" (red) with a 1.5–2s timeout before resetting.
After success, triggers `loadData()` after 2s to pick up fresh data.

### Desktop Launcher Pattern

```bat
@echo off
cd /d C:\Users\bgonn\vesper-dashboard
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8080 ^| findstr LISTENING') do taskkill /F /PID %%a 2>nul
start /min python server.py --port 8080
timeout /t 3 /nobreak >nul
start http://localhost:8080
```

## Data Aggregator Pattern (`aggregator.py`)

The aggregator reads multiple Vesper data sources and consolidates them into a
single `dashboard_data.json` consumed by the frontend. Key patterns:

### File discovery
```python
def _latest_json(glob_pattern: str) -> Path | None:
    files = sorted(DATA_DIR.glob(glob_pattern),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None

def _latest_md_skip_validation(directory, glob_pattern):
    """Skip *_validation.md files when finding latest report."""
    files = sorted(directory.glob(glob_pattern),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files:
        if "_validation" not in f.stem:
            return f
    return None
```

### Parsing markdown tables for tickers/weights
```python
# Extract from "| Ticker | Target Weight | ..." tables
for line in text.splitlines():
    cols = [c.strip().strip("`") for c in line.split("|")]
    if len(cols) >= 3 and cols[1].isupper():
        weight_str = cols[2].rstrip("%")
        weights[cols[1]] = float(weight_str)
```

### Building freshness from file timestamps
```python
mtime = datetime.fromtimestamp(sf.stat().st_mtime, tz=timezone.utc)
entries.append({"time": f"{mtime.hour} UTC", "source": "Factor Scores", ...})
```

### Dual-format details compatibility

`run_all_factors.py` writes per-factor details keyed by factor **name** (e.g. `technical`,
`massive`, `insider`). Older manual runs used metric keys (`entropy`, `hurst`,
`realized_vol_z60_lag1`). The aggregator must handle both:

```python
details = item.get("details", {})
leaders.append({
    "entropy": round(details.get("entropy") or details.get("technical", 0), 3),
    "hurst":   round(details.get("hurst", 0), 3),
    "vol":     round(details.get("realized_vol_z60_lag1") or details.get("vol", 0), 3),
    "sent":    round(details.get("sentiment", 0), 3),
    "insider": round(details.get("insider", 0), 3),
    "massive": round(details.get("massive", 0), 3),
})
```

The `or` pattern works because `details.get("entropy")` returns `0` (falsy) when
missing in new format, falling through to `details.get("technical", 0)`.

## JavaScript Data Binder Pattern (`data-binder.js`)

Uses DOM traversal to find elements without requiring IDs — the HTML stays
clean and the JS is self-healing across layout changes.

### Finding elements by heading text
```javascript
function findTbodyAfter(text) {
  var hdrs = $$(".panel-title");
  for (var i = 0; i < hdrs.length; i++) {
    if (hdrs[i].textContent.trim().startsWith(text)) {
      var panel = hdrs[i].closest(".panel");
      return panel ? $("tbody", panel) : null;
    }
  }
  return null;
}
```

### Rendering pattern
```javascript
function renderFactorLeaders(data) {
  var tbody = findTbodyAfter("Factor");
  tbody.innerHTML = data.leaders.map(function(r) {
    return "<tr><td class='ticker'>" + r.ticker + "</td>...</tr>";
  }).join("");
}
```

### Auto-refresh
```javascript
loadData();
setInterval(loadData, 30000);  // every 30 seconds
```

## JSON Data Schema

```json
{
  "generated_at": "2026-07-06T19:02:43Z",
  "last_update": "19:02:43 UTC",
  "market_status": "CLOSED",          // OPEN | PRE-MARKET | AFTER HOURS | CLOSED
  "mode": "PAPER",
  "system": "HEALTHY",
  "version": "v2.0.0",
  "factor_leaders": {
    "leaders": [{
      "rank": 1, "ticker": "AAPL", "score": 1.0767,
      "entropy": 2.324, "hurst": 0, "vol": 0, "sent": 0.98, "insider": 0
    }, ...],
    "date": "20260706",
    "scored_count": 43,
    "freshness_hours": 5.3,
    "is_stale": false
  },
  "selected_basket": {
    "entries": [{
      "rank": 1, "ticker": "COST", "score": 0.6227, "weight_pct": 16.67
    }, ...],
    "date": "20260703"
  },
  "portfolio": {
    "equity": 106578.48, "cash": 5329.04,
    "buying_power": 304815.00, "positions_count": 6,
    "portfolio_pl": null, "day_pl": null
  },
  "active_jobs": [
    {"job": "Factor Scores", "next": "02:00", "last": "19:02:43", "status": "idle"},
    ...
  ],
  "todays_data": [
    {"time": "19 UTC", "source": "Factor Scores", "result": "43 tickers"},
    ...
  ],
  "recent_activity": [
    {"time": "19:02:43", "msg": "Scores 20260706", "highlight": true},
    ...
  ]
}
```

## Design System (CSS Custom Properties)

```css
:root {
  --bg-primary: #0a0a0a;    --bg-secondary: #0d0d0d;
  --bg-card: #111111;       --bg-elevated: #1a1a1a;
  --border-primary: #1f1f1f;
  --text-primary: #ffffff;  --text-muted: #888888;  --text-dim: #666666;
  --accent-green: #22c55e;  --accent-blue: #3b82f6;  --accent-red: #ef4444;
  --sidebar-width: 220px;   --header-height: 48px;  --footer-height: 44px;
  --radius-card: 8px;       --radius-button: 4px;
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --font-mono: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
}
```

All tweaks to colors, spacing, or typography go through these variables — the
entire dashboard restyles from one place.

## Desktop Launcher Pattern

Create a `.bat` file on the Desktop for one-click dashboard access:

```bat
@echo off
cd /d C:\Users\bgonn\vesper-dashboard
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8080 ^| findstr LISTENING') do taskkill /F /PID %%a 2>nul
start /min python -m http.server 8080
timeout /t 2 /nobreak >nul
start http://localhost:8080
```

Key behaviors:
- Kills stale server on :8080 before starting fresh (prevents `Address already in use`)
- `start /min` runs the server minimized (no lingering terminal window)
- `timeout /t 2` gives the server time to bind before browser opens
- File extension MUST be `.bat` not `.sh` on Windows (right-click → run)

## After-Close Utility Patterns

The dashboard must feel alive when markets are closed. Two patterns:

### Market Open Countdown (client-side in data-binder.js)
```javascript
function countdownToNextOpen() {
  var now = new Date();
  var next = new Date(now);
  next.setUTCHours(14, 30, 0, 0);  // 9:30 AM ET
  if (now >= next) next.setUTCDate(next.getUTCDate() + 1);
  while (next.getUTCDay() === 0 || next.getUTCDay() === 6) next.setUTCDate(next.getUTCDate() + 1);
  var diff = next - now;
  var hrs = Math.floor(diff / 3600000);
  var mins = Math.floor((diff % 3600000) / 60000);
  if (hrs < 0) return "● Market Open";
  return "⏳ Next open in " + hrs + "h " + String(mins).padStart(2,'0') + "m";
}
```

Rendered in header as: `⏳ Next open in 12h 52m` (grey) or `● Market Open` (green).

### Real Cron Job Status (aggregator sidecar pattern)

The aggregator can't directly query Hermes cron jobs. Instead, use a sidecar JSON file:

```
cronjob(action='create', name='Sync Cron Status', schedule='every 1h')
  → writes cron_status.json with real job statuses
aggregator.py reads cron_status.json → includes in dashboard_data.json
data-binder.js renders with red/green/grey status dots
```

`cron_status.json` schema:
```json
{
  "updated": "2026-07-07T01:32:00Z",
  "jobs": [
    {"job": "Factor Scores", "next": "02:00", "last": "02:00:03 Jul 06", "status": "error"},
    {"job": "Morning Briefing", "next": "06:00", "last": "06:09:08 Jul 06", "status": "ok"}
  ]
}
```

Status mapping: `ok` → grey dot + "OK", `error` → red dot + "ERROR", `running` → green dot + "RUNNING", `idle` → grey dot + "IDLE".

- **Tkinter** (`scripts/factor_dashboard.py`): Previous implementation, full tkinter/ttk app
- **HTML** (`vesper-dashboard/index.html`): Current live dashboard, served via HTTP
- The CSS custom properties map 1:1 to the Tkinter dashboard's color constants
- The HTML dashboard replaced the Tkinter one as the primary monitoring surface

## Build Workflow (for future visual reference work)

When building a dashboard from a screenshot reference:
1. `vision_analyze` the screenshot with a forensic question about every pixel detail
2. Build the full layout as a single self-contained HTML file
3. `browser_navigate` to verify structure renders
4. `browser_vision` to visually audit against the reference
5. Iteratively compact with `patch` tool until all panels fit the target viewport
6. For 1920×1080 dashboards with bento-grid layouts, expect ~803px content height
7. Wire aggregator.py to Vesper data sources, output `dashboard_data.json`
8. Build data-binder.js with DOM-traversal pattern, add `setInterval` for auto-refresh
9. Schedule cron job to refresh aggregator periodically

### Pitfall: Adding IDs to non-unique metric-value spans

When adding IDs to card metrics for JS data binding, `patch` tool matches fail because
`<span class="metric-value">$106,578.48</span>` appears in BOTH the card and the portfolio
panel. Use surrounding context lines that include the parent `metric-label` to disambiguate:

```python
# WRONG — matches both card and portfolio panel
patch(old_string='<span class="metric-value">$106,578.48</span>', new_string='<span class="metric-value" id="val-equity">$—</span>')

# RIGHT — context from parent metric-label makes it unique
patch(old_string='<span class="metric-label">Equity</span>\n        <span class="metric-value">$106,578.48</span>',
      new_string='<span class="metric-label">Equity</span>\n        <span class="metric-value" id="val-equity">$—</span>')
```

When IDs still fail to apply, verify with `browser_console`: `Array.from(document.querySelectorAll('.metric-value')).map(el => el.id || 'NONE')`.