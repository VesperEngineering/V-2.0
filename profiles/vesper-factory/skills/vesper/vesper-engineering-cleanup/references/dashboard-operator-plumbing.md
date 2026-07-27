# Vesper Dashboard Plumbing Audit Pattern

Use this checklist when the GUI looks polished but its operational truth is uncertain. Preserve the current frontend/layout until the data contract, scheduler authority, freshness, and deployment path are proven.

## Trust boundaries to trace

1. **Rendered page → served static root**
   - Identify the process bound to the port, its command line, cwd, and exact static directory.
   - Compare served asset hashes with the intended repository copy.
   - Audit all Startup-folder entries, shortcuts, tray launchers, scheduled wrappers, and refresh scripts for shadow paths.

2. **Header claims → evidence**
   - `HEALTHY`, `Connected`, and `live` must be derived, never literal HTML or unconditional aggregator values.
   - Health should fail closed from critical scheduler outcomes, source freshness, basket admission, portfolio availability, and failed jobs.
   - `/api/status` must report payload generation time, payload age, state, and reasons; HTTP reachability alone is not health.

3. **Freshness layers**
   - Keep browser fetch age, dashboard payload age, factor artifact age, basket age, portfolio snapshot age, and broker-live observation age separate.
   - Derive payload age from `generated_at`; rereading unchanged JSON must not reset it.
   - Transport ISO-8601 timestamps with offsets and format once in `America/New_York`. Do not convert already-local display strings.

4. **Execution authority**
   - Dashboard “Selected Basket” must read the canonical artifact consumed by rebalance, not top raw scores or current holdings.
   - Expose raw factor values separately from governance-weighted contributions. Determine the top factor from deployed weighted contribution; zero-weight diagnostics cannot be presented as deployed drivers.
   - Distinguish target basket, last executed target, snapshot holdings, and live holdings.

5. **Scheduler authority**
   - Discover which scheduler actually owns each job. Do not assume an internal scheduler, Hermes cron, and Windows Task Scheduler are interchangeable.
   - Exclude paused jobs from “active.” Preserve `source`, `enabled`, scheduling state, expected/next time, last run, and outcome separately.
   - Query real Windows task Last Result and action. `Ready` is configuration, not success.
   - A critical pipeline should contain every dependency in fail-closed order (for example OHLCV ingest → scores → basket → dashboard refresh).

6. **Refresh controller**
   - Track every interval ID and clear all of them on settings/phase changes.
   - Reevaluate cadence when premarket becomes open and when visibility changes.
   - Prevent overlapping refresh requests.
   - Use the real API server, not a static `http.server`, when the frontend invokes API routes.

## Safe implementation sequence

1. Capture dirty worktree and deployed-process baseline.
2. Build tight regression tests for each false claim before changing production code.
3. Preserve the visible frontend byte-for-byte in the authoritative repo before retiring a shadow runtime copy.
4. Repair backend provenance, health, freshness, scheduler adapters, and API contracts.
5. Repair frontend binding/timers without reorganizing the layout.
6. Remove duplicate launch authorities only after the intended server starts and serves matching hashes.
7. Verify focused tests, full pytest, API output, browser DOM/console, process command line, served hashes, Windows task Last Result, and source artifacts.
8. Update `docs/STATUS.md` with authoritative paths, scheduler ownership, safety boundaries, and unresolved blockers.

## Common high-value failures

- Two Startup launchers race for the same port; one checks for any `pythonw.exe` rather than the specific process or port.
- Aggregator writes both repository and user-directory copies, hiding deployment drift.
- “Updated 10s ago” means browser fetch age while the payload is hours old.
- Job times already in ET are treated as UTC, producing double conversion or `AM AM`.
- Paused Hermes jobs appear healthy because their historical `last_status` is `ok`.
- Critical Windows backups fail while the page remains green.
- Factor pipeline omits the upstream ingest, so its fail-closed date gate can never self-recover.
- Rebalance main bypasses the tested lock/idempotency/state-machine boundary; passing unit tests do not prove production wiring.

## Completion bar

Do not call the plumbing complete until the running localhost instance is backed by the intended repository process, served assets match disk, health is evidence-derived, canonical artifacts agree with execution, all timers are controlled, targeted and full tests have run, and browser/API verification is clean.
