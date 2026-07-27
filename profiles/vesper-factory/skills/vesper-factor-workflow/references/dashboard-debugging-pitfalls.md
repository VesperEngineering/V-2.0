# Dashboard and Runtime Truth Debugging

Use this when the Vesper GUI, localhost API, scheduled pipeline, or broker evidence disagree. Treat the system as separate layers; never infer one layer from another.

## 1. Separate the layers

1. **Market-data/factor pipeline** — OHLCV ingest, factor scoring, basket generation, dashboard aggregation.
2. **Dashboard server/runtime** — which process owns port 8080 and which directory it serves.
3. **Browser renderer** — which exact JS assets/version were loaded and whether rendering raised errors.
4. **Windows/Hermes scheduling** — task action, retained execution context, Last Result, and natural scheduled receipts.
5. **Broker/order evidence** — broker order history and owned receipts/state.

A successful internal pipeline does not prove the GUI is serving repository code. A broken or stale GUI does not prove factor scripts failed. `BLOCKED` can be a truthful safety state while the GUI and data pipeline are healthy.

## 2. Identify the actual server before debugging HTML

Check every listener, not just whether port 8080 responds:

```text
netstat -ano | findstr :8080
```

For each listener PID, inspect process and parent command lines. On Windows, a shadow server may bind `0.0.0.0:8080` while the authoritative server binds `127.0.0.1:8080`; both can appear simultaneously and requests may reach different implementations depending on address.

Verify runtime identity using all of:

- listener address (`127.0.0.1`, not `0.0.0.0`);
- process command line and parent chain;
- `/api/status` schema (derived status, generation time, age, reasons);
- served script URLs/version from `document.scripts`;
- distinctive payload fields such as `selected_basket.execution_valid`;
- browser-rendered status and console errors.

Do not accept `HTTP 200` or static `HEALTHY` text as identity or health proof.

## 3. Eliminate shadow deployment resurrection

Disabling one launcher is insufficient if an already-running orphan server remains. Kill the exact shadow process tree after proving its command line. Then verify that no `0.0.0.0:8080` listener remains.

The authoritative source is `D:\vesper\vesper-dashboard`; historical `C:\Users\bgonn\vesper-dashboard` code must not own the port or receive payload mirrors.

A tray supervisor must launch the server by absolute script path. Health checks should validate the expected API contract/source identity, not merely any 200 response on port 8080.

## 4. Desktop/startup launcher pitfall

Do not use `tasklist | findstr pythonw` as an "already running" test. Any unrelated `pythonw.exe` causes a false positive and the launcher opens a dead or wrong dashboard.

A robust launcher should:

1. request `/api/status` on `127.0.0.1`;
2. verify `server == "vesper-dashboard"` and the expected contract/version;
3. if invalid, terminate only a proven shadow dashboard process tree;
4. launch `D:\vesper\vesper-dashboard\tray_icon.py` by absolute path;
5. wait for the identity-aware health check;
6. open `http://127.0.0.1:8080`.

On OneDrive-redirected Windows desktops, inspect the actual Desktop path. For this environment the visible launcher is under `C:\Users\bgonn\OneDrive\Desktop`, not the local Desktop folder.

## 5. Prove whether an order happened

Task `Last Result`, missing logs, and missing receipts are useful but not definitive. For the user-facing question “did it trade?”, query the paper broker’s same-day order history read-only and report only non-secret fields/counts. Cross-check:

- broker same-day orders;
- owned rebalance state/receipt files;
- Windows task Last Run/Last Result;
- wrapper log.

Do not infer “no orders” from a failed task alone: a process can fail after submission but before writing a receipt.

## 6. Freshness recovery contract

Run and verify the dependency chain:

1. ingest through the immediately preceding XNYS session;
2. query the active SQLite table’s `MAX(date)`;
3. score with matching source-session provenance;
4. generate the exact prior-session basket;
5. validate heading, provenance, age/future skew, cardinality, uniqueness, and ticker syntax using the same loader as rebalance;
6. refresh the dashboard;
7. inspect the generated payload rather than relying on process exit alone.

A factor may fail independently while the pipeline admits non-core results. Surface that explicitly; do not silently call every factor healthy.

## 7. Scheduler authority versus strategy authority

A valid fresh basket and successful scheduled process are not enough to authorize paper orders. Before enabling a rebalance task, reconcile:

- board-approved strategy/lane;
- selected basket and basket producer;
- account and paper-only scope;
- maximum notional/envelope;
- source-session and artifact digest;
- machine-readable approval gate checked before broker access.

If the board describes a different basket or lane than the scheduled script consumes, pause or convert the task to preview/no-submit. Do not let freshness repair accidentally open an unrelated order path.

## 8. Browser truth checks

After changing JS, bump the query version and verify the exact URL via `document.scripts`. Check rendered values and console errors after at least one refresh interval. Distinguish payload generation age from browser-fetch age.

Use `Intl.DateTimeFormat` with `America/New_York`; do not hand-code DST offsets. Keep target basket and live broker positions separate.

## 9. Server safety contract

- bind loopback only;
- no wildcard CORS;
- no order-bearing dashboard endpoint;
- stale payload overrides embedded healthy status;
- use `ThreadingHTTPServer` or otherwise ensure broker polling cannot block all requests;
- live portfolio errors must be explicit and must not resemble valid empty holdings;
- manual order controls remain disabled unless separately approved.
