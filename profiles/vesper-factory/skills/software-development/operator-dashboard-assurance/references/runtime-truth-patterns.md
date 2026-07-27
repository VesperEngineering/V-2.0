# Runtime Truth Repair Patterns

Use these patterns when a dashboard looks healthy but its operational claims may be stale, shadowed, or sourced from different authorities.

## Deployment authority inventory

Enumerate and verify all of these independently:

1. HTTP server process, command line, cwd, and static root
2. HTML-referenced frontend bundle and cache-busting version
3. Aggregator/refresh wrapper and its cwd
4. Generated payload destination(s)
5. Login/startup launchers, tray process, service, or container
6. Scheduled-task actions and logon mode
7. Any duplicate source or shadow deployment trees

A safe consolidation disables or redirects competing launchers and shadow writes. Copying fixes to two trees preserves ambiguity.

## Freshness vocabulary

Keep separate fields and labels for:

- `fetched_at`: when the browser read a response
- `generated_at`: when the dashboard payload was produced
- `source_observed_at`: when upstream data was observed
- `artifact_session`: market/business session represented by an artifact
- `broker_observed_at`: live external account observation
- `snapshot_at`: persisted last-known account state

A successful HTTP read updates only `fetched_at`. It must not reset payload or source age.

## Fail-closed health composition

Derive headline health from critical components and preserve reasons:

- `BLOCKED`: required scheduler/task failed, expected artifact absent/stale, artifact provenance invalid, or a required execution guard failed
- `DEGRADED`: optional/current-state source unavailable while safe persisted evidence remains
- `HEALTHY`: every required component proved current and valid

Reachability (`HTTP 200`) is a component fact, not system health.

## Artifact identity and provenance

Validate the exact artifact consumed by execution, including:

- canonical path/pattern
- expected row count and unique identifiers
- artifact date/session
- source-data session embedded in the artifact
- match between artifact date and embedded source session where contract requires it

Do not regenerate an execution basket from raw dashboard rankings.

## Refresh controller pattern

Maintain explicit handles for payload, backend-refresh, and live-source timers. Before changing cadence:

1. clear every handle
2. derive the current phase
3. install one interval per source
4. guard each request with an in-flight flag
5. reevaluate on phase transition and `visibilitychange`

Expose a small diagnostic method returning phase, active timer booleans, and current payload timestamp for browser verification.

## Live versus snapshot arbitration

A common race is: live broker data renders, then a faster payload poll overwrites it with yesterday's snapshot. Fix by:

- tracking the last successful live observation
- suppressing snapshot rendering while live data is recent
- labeling the visible source and observation time
- failing visibly when live retrieval errors
- never using live holdings to overwrite a target-basket widget

## Deterministic browser-helper tests

When the frontend has no test framework, extract pure helpers into a UMD/CommonJS-compatible module and test them with `node -e` or a small Node test. Good targets:

- ISO → named-timezone formatting
- payload-age arithmetic
- market-open/closed refresh plans
- source-priority decisions

Then verify the integrated page with the browser console: exact bundle URL, derived status text, payload-age text, timer state, source label, and absence of JS errors.

## Scheduled-task readback

After mutating a task, read back:

- action/command path
- enabled state
- next run
- account/logon mode
- last result

Do not clear or reinterpret the previous failure result. A new successful unattended receipt is the proof that credentials/logon context survived the mutation.
