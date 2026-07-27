# HTML Dashboard Debugging Patterns

## ⚠️ RULE #1: Timer ticks but panels frozen = undeclared var in strict mode
**Symptom**: market clock + countdown update every second, but ALL data panels show static HTML fallback.  
**Root cause**: `"use strict"` + undeclared variable assignment = `ReferenceError` that crashes the entire `loadData()` try/catch before any renderer runs.  
**Fix**: Declare ALL variables at IIFE top with `var`.  
**Verify**: Add `"vN · load #" + counter` badge to `renderHeader` — if counter never increments, renders are crashing.

## JavaScript Strict Mode Traps
- `"use strict"` at the top of the IIFE means ANY undeclared variable assignment throws `ReferenceError`
- This crashes the ENTIRE render pipeline silently — `loadData().then()` calls all renderers in a single `try/catch`, so one failure kills everything
- **Fix**: Always declare variables with `var` at the top of the IIFE scope
- **Debug technique**: Add a visible load counter (`v5 · load #N`) in `renderHeader()` — if it doesn't increment, JS isn't rendering

## Server Port Collisions
- Two Python processes listening on `:8080` → browser gets `ERR_EMPTY_RESPONSE`
- The `.bat` launcher must `taskkill /F` all PIDs on the port before starting
- Check with: `netstat -ano | grep ":8080" | grep LISTENING`

## Server Blocking (Single-Threaded HTTP)
- `SimpleHTTPRequestHandler` is single-threaded — any blocking call (Alpaca API) hangs ALL requests
- **Fix for live endpoints**: Use a cache with 30s TTL + initialize with dummy data so first request returns instantly
- Pattern:
  ```python
  _cache = {"equity": None, "loading": True}
  _cache_time = 0
  
  def fetch():
      if _cache and time.time() - _cache_time < 30:
          return _cache
      # ... blocking API call ...
      _cache = result
      _cache_time = time.time()
      return result
  ```

## JS Cache Busting
- Query strings (`?v=5`) are unreliable — browsers may still serve cached version
- **Nuclear option**: Rename the file (`data-binder-v6.js`) and update the HTML `<script>` tag
- Always verify with: `curl -s "http://127.0.0.1:8080/data-binder-vN.js" | head -3`

## Windows Desktop Path
- The actual Desktop is `C:\Users\<user>\OneDrive\Desktop` — NOT `C:\Users\<user>\Desktop`
- Check with: `powershell -Command "[Environment]::GetFolderPath('Desktop')"`
- Launcher `.bat` and `.url` files go on the OneDrive Desktop

## Time Display
- All backend timestamps are UTC 24-hour format
- Convert in JS to user's local time (ET) using `fmtTime()` helper
- For recent activity, use relative times ("3m ago") that tick every 1s via `setInterval(tickRelTimes, 1000)`
- DST detection: `(new Date()).getTimezoneOffset() === 240` → EDT (UTC-4), else EST (UTC-5)

## Dashboard Refresh Architecture
| Component | Refresh | Source |
|-----------|---------|--------|
| Market clock + status | 1s | Browser JS (live) |
| "Updated Xs ago" | 1s | Browser JS counter |
| Activity timestamps | 1s | Relative time ticker |
| Factor Leaders, Jobs, Basket | 5s | `dashboard_data.json` fetch |
| Aggregator trigger | 5s (market) / 60s (off) | POST `/api/refresh` |
| **Live Portfolio P&L** | **10s (market)** | GET `/api/portfolio-live` (Alpaca API direct) |
| Cron aggregator fallback | 1m | Cron job |
| Portfolio snapshot | 5m (market) / daily (off) | Cron job |

## Patch Tool Workaround
- The `patch` tool mangles indentation on compact/one-liner style code
- **Use Python `str.replace()` or `sed` instead** for surgical edits
- For HTML edits: write a small Python script, run it, then cleanup

## Silent Render Failures — Debug Checklist
1. Check JS syntax: `node -c data-binder.js`
2. Check JS served matches file: `curl -s http://127.0.0.1:8080/data-binder.js | grep "function_name"`
3. Check `dashboard_data.json` is valid: `curl -s ... | python -c "import json; json.load(sys.stdin)"`
4. Check `renderHeader` runs: add visible counter
5. Check browser console (F12) for errors
6. Check HTML `<script>` tag references the right file
7. Check server is running: `netstat -ano | grep ":8080"`
