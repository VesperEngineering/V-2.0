# Dashboard JS Debugging (data-binder.js)

## Symptom: "Nothing flowing" — timer ticks but panels show static HTML

### Root cause: `"use strict"` + undeclared variable

The IIFE at line 7 enables strict mode:
```js
(function () {
  "use strict";
```

Any assignment to an undeclared variable inside a render function throws
ReferenceError. This crashes the entire `loadData()` try/catch before any
panel gets rendered. The 1-second `tickMarketClock` and `tickUpdateCounter`
intervals keep running because they're independent — this creates the
illusion that "the timer works but nothing else does."

### Fix checklist

1. All variables added inside `loadData()`, `renderHeader()`, or any
   render function MUST be declared with `var` at the top of the IIFE
   (near lines 9-15, alongside `LAST_DATA`, `REFRESH_MS`, etc.)

2. After adding variables, verify:
   ```bash
   node -c data-binder.js        # syntax check
   grep -c "var " data-binder.js # count declarations
   ```

3. Bump the cache-buster in index.html:
   ```html
   <script src="data-binder.js?v=N"></script>  <!-- increment N -->
   ```

4. Add a diagnostic badge to `renderHeader`:
   ```js
   var LOAD_COUNT = 0;  // declared at IIFE top
   // ... inside renderHeader:
   LOAD_COUNT++;
   // Create visible element showing version + count
   ```

5. Hard-refresh browser: Ctrl+Shift+R

### Other common causes of empty panels

- **Wrong server process**: `python -m http.server` doesn't handle API routes.
  Must use `server.py`. Check: `curl localhost:8080/api/status` — should
  return JSON, not HTML error page.

- **Stale cached JS**: Browser serves old `data-binder.js` even after
  changes. Fix: bump the version query param and hard-refresh.

- **Schema mismatch**: Aggregator outputs keys that JS doesn't read.
  Check `dashboard_data.json` keys match what `renderFactorLeaders` expects.
  The mapping: `entropy←details.sp500_technical`, `hurst←details.sec_fundamentals`,
  `vol←details.wiki_attention`, `sent←details.finviz_sentiment`,
  `insider←details.insider`, `massive←details.massive`.

- **Port collision**: Two processes on :8080. Kill duplicates:
  `taskkill /F /PID <pid>`.
