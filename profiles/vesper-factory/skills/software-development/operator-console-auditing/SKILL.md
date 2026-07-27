---
name: operator-console-auditing
description: Audit dashboards for autonomous systems, schedulers, trading systems, and data pipelines by tracing displayed claims to authoritative sources, timestamps, refresh behavior, deployment state, and actionable evidence.
version: 1.0.0
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [dashboard, observability, operator-console, qa, data-lineage, autonomous-systems]
---

# Operator Console Auditing

## When to use

Use this skill when reviewing a GUI that supervises an unattended or autonomous system. It complements general visual dogfooding by testing whether the console tells operational truth rather than merely rendering plausible numbers.

Typical targets include trading dashboards, schedulers, data pipelines, agent systems, infrastructure consoles, and long-running services.

## Required outcome

Determine whether an operator can answer, without opening source code:

1. What happened?
2. What changed since the last authoritative state?
3. What needs attention now?
4. What happens next, and when?
5. Can each important value be trusted?
6. What evidence should accompany a follow-up question or incident report?

Preserve visual qualities the user already likes. Prioritize truth, lineage, and exceptions before recommending cosmetic redesign.

## Workflow

### 1. Inspect the running surface

- Open the actual application and capture its visual hierarchy.
- Check browser console errors after navigation and important interactions.
- Visit each operational page: overview, jobs, logs/evidence, portfolio/state, settings, and controls.
- Record prominent claims such as `HEALTHY`, `CONNECTED`, `LIVE`, last update, next run, and current mode.
- Do not activate execution, rebalance, deployment, or other side-effecting controls during an audit.

### 2. Identify what is actually deployed

Do not assume localhost serves the current repository.

- Identify the process, command line, working directory, static root, API base, generated bundle, scheduler wrapper, and aggregator script serving or producing the page.
- Search for duplicate GUI copies, legacy dashboards, generated distributions, and shadow deployment directories.
- Compare running responses with repository implementations.
- When duplicate copies write identical payloads, use payload-shape fingerprints (for example top-4 versus top-10 behavior) plus wrapper paths to prove which implementation actually ran; identical output hashes alone do not prove source parity.
- Check the exact frontend bundle referenced by HTML separately from the backend/aggregator copy.
- Flag any path where a developer could change and test one copy while operators continue seeing another.

### 3. Build a widget lineage table

For every major widget, determine:

- Displayed claim/value
- Authoritative source artifact or API
- Source timestamp and timezone
- Transformation or aggregation
- Browser polling cadence
- Backend/source refresh cadence
- Fallback behavior
- Failure/staleness presentation

Distinguish browser fetch age, payload generation age, source-data age, and external-system snapshot age. A browser rereading an old JSON file is not live data.

### 4. Verify health semantics

Trace every green state to its computation.

- Is it hardcoded, inferred, or measured?
- Does overall health reflect the worst relevant subsystem?
- Can last-known-good data remain green after an endpoint fails?
- Are scheduler, data, broker/feed, pipeline, and execution health separately visible?
- Does `connected` mean DOM loaded, backend reachable, or authoritative external system reachable?

Treat hardcoded or presentation-only reassurance as a high-severity trust defect.

### 5. Audit refresh behavior

Measure each layer separately:

- UI clock/tick
- Browser payload polling
- Backend aggregation
- Upstream data generation
- External API/feed polling

Test boundary transitions such as pre-session to open, hidden/visible tab, sleep/resume, and settings changes. Look for initialization-only cadence decisions, leaked duplicate intervals, long refresh calls blocking a single-threaded server, and silently retained stale data.

### 6. Audit scheduler and pipeline truth

A useful Jobs page should show:

- Authoritative scheduler identity and heartbeat
- Expected run, actual start, finish, duration, status, retries, and current-running state
- Missed-run detection with an SLA/grace period
- Failed stage and concise diagnostic
- Output artifact/receipt, row-count validation, and freshness
- Dependencies and next safe action

For a read-only scheduler investigation, enumerate every plausible authority separately: OS task scheduler, application daemon/job store, agent cron, services, and startup launchers. Treat live scheduler state as execution truth and config/status documents as intent. For each task capture enabled/runtime state, logon context, schedule, last run/result, next run, exact action, power restrictions, and multiple-instance policy. **Verify the task action path exists on disk** — a task with `Status: Ready` and `Last Result: 1` often points to a missing or renamed wrapper file. Trace wrapper commands through each pipeline stage and resolve symlinks/junctions before deciding which data root is updated.

Correlate task state with process command lines, logs, output mtimes, receipts, and read-only datastore queries. A successful out-of-schedule run proves the command path, not unattended scheduling. Check whether scheduler history is enabled; if history is unavailable and `Last Run` was overwritten, state that evidentiary limit rather than reconstructing an unsupported timeline. Never trigger a task merely to tighten the feedback loop during a read-only audit.

A logfile containing `ok` does not prove current scheduler health. Verify timezone semantics and detect double conversion of already-local timestamps. See `references/read-only-scheduler-audit.md` for an evidence checklist and Windows-oriented probes.

### 7. Audit domain authority boundaries

Separate pipeline stages that look similar but carry different authority. For trading systems, explicitly distinguish:

- Raw score leaders
- Universe/tradability-approved candidates
- Portfolio-construction output
- Risk-approved execution basket
- Submitted/open/filled orders
- Actual broker holdings

Never present raw candidates as approved actions without visible validation gates.

For autonomous trading/risk consoles, also inspect:

- Broker mode/account, connectivity, snapshot timestamp, and age
- P/L definitions
- Target versus actual weights and drift
- Pending/rejected orders and last rebalance receipt
- Gross/net and beta-adjusted exposure
- Sector limits, concentration, stops, and risk headroom
- Turnover, cost/slippage, drawdown observation count, and benchmark context
- Signal date, actual factor contributions, deployed weights, and exclusion reasons

### 8. Test control labels and production wiring against behavior

For each control, compare its label with the endpoint implementation and observed result. Flag controls such as `Run All Jobs` that only refresh an aggregator. High-impact actions must expose mode/account, proposed changes, risk checks, idempotency, and evidence.

Do not assume tested safety helpers are used by the real entry point. Trace `main()` or the deployed handler through the lock, validation, idempotency, durable state, and receipt path. Add a regression test that makes the unsafe/direct lower-level path fail and asserts the production entry point invokes the tested side-effect boundary.

### 9. Enforce the local control-plane boundary

Treat the running dashboard server as part of the audit, not just a static-file host.

- Bind to loopback by default; network-wide listeners require explicit need and approval.
- Avoid wildcard CORS on a local control plane.
- Keep GET routes read-only and use an explicit method/path allowlist.
- Do not expose broker/order, scheduler mutation, promotion, risk/target, credential, or destructive actions merely because a repository script exists.
- If layout stability matters, preserve a prohibited control as disabled and clearly labeled, remove its handler, and verify that state in the rendered DOM.
- Exercise the running service: approved read/bounded-write routes should work, state-changing GET should not, and prohibited high-impact POST should fail closed (normally 403).
- When live data supersedes a persisted snapshot, make source/timestamp visible and prevent frequent payload refreshes from overwriting the recent live value. Never let broker holdings overwrite the canonical target artifact.

See `references/local-control-plane-safety.md` for a reusable route, listener, control, and deployment-drift checklist.

### 10. Report in trust-first order

Lead with a direct verdict: trustworthy, degraded, or not yet trustworthy. Then report:

1. Critical contradictions and false reassurance
2. Deployment/source-of-truth drift
3. Data lineage and freshness defects
4. Scheduler/refresh/timezone defects
5. Missing operator information
6. Visual or accessibility issues
7. One prioritized repair sequence

For each important finding include the displayed claim, underlying implementation/source, current observed value, and operational consequence.

## Pitfalls

- Do not equate a clean console with an operationally trustworthy console.
- Do not recommend faster global polling as a substitute for per-source freshness and SLAs.
- Do not treat zeros, blanks, or em dashes as harmless when a hidden source actually contains a contribution or error.
- Do not infer scheduler liveness from old logs.
- **Do not treat `Status: Ready` + missing action file as a healthy task.** A Windows scheduled task can show `Status: Ready`, a populated `Next Run Time`, and `Status: Enabled` while silently returning exit code 1 every run because its "Task To Run" path does not exist on disk. The scheduler considers the task enabled; the OS cannot launch a missing binary. Cross-check the action path against the filesystem — not just against git or configuration.
- Do not redesign a layout the user likes before repairing the truth layer.
- **A freshness check that displays a date but never compares it to now can never fail.** A watchdog that reads e.g. `local_ohlcv_date` and returns `healthy` with the date as a cosmetic detail string is a structural false-green. Verify the comparison expression actually exists, and prove the check can go red with a stale fixture.
- **A PASS receipt for a no-op is not lane health.** Batch/bridge loops that record `action: no_queue` or `candidates_found: 0` with status PASS get counted as healthy by receipt-age watchdogs while the lane produces nothing. Distinguish IDLE (nothing to do) from productive PASS, and verify that a producer for the consumed queue/artifact directory actually exists.
- **Receipt staleness thresholds must be schedule- and calendar-aware.** A fixed hour threshold (e.g. 48 h) against a weekday-only schedule guarantees false stale alerts every weekend. Derive the deadline from the job's cron schedule, not a constant.
- **Dry-run and manual receipts are not scheduled-run proof.** Check receipt provenance (e.g. a `dry_run` flag in metrics, or the cron registry's `last_run_at` for the owning job) before treating a receipt as unattended health evidence.
- **An alert delivery path that has never fired is unverified, not healthy.** If dispatcher history shows zero dispatches, say the path is unproven and recommend one synthetic test alert rather than assuming reachability.
- **A failed alert delivery must stay pending — never be archived as sent.** Dispatcher designs that "move to dispatched regardless, to prevent infinite retry" silently lose exactly the alerts raised during an outage, the worst moment to lose them. Retry-safety belongs in a bounded attempts counter (then park in a `failed/` quarantine), not in dropping the alert.
- **Repairing a false-green check doubles as the alert-chain integration test.** The first truthful degraded verdict produces the first real alert the delivery path has ever carried. After shipping such a fix, watch the next dispatcher receipt — expect the first real delivery attempt to expose unconfigured platforms or durability bugs, and verify failed alerts remain pending.
- **When the LLM/agent layer is paused, check who watches the board.** Blocked/needs-input cards can sit indefinitely because the steward owning escalation is paused and deterministic watchdogs only watch files/receipts. Look for a deterministic blocked-age check or report the escalation gap explicitly.
- Do not click side-effecting controls merely to test whether they work.
- **Do not overstate a verdict from a narrow check.** A clean lint + focused-test + single-refresh pass proves those layers only — not release readiness. If a broader audit or another agent's report exists with a different verdict, reconcile scope before declaring "verified" or "up-to-date"; say exactly what you did and did not check. Overstated assurance is a first-class trust defect.

## Supporting references

- See `references/tk-operator-app-verification.md` for a read-only layered verification battery for a Tkinter operator app (VOT): dirty-tree check, lint/syntax/import, Windows pytest temp + cross-mount workaround, live SQLite/provider data validation, a real Tk instantiation + refresh-drain smoke test, verdict discipline, and concurrent-session baseline-vs-working-tree failure classification (stash → baseline → restore).
- See `references/trust-audit-checklist.md` for a compact reusable checklist and reporting priorities.
- See `references/trading-data-truth-plumbing.md` for authority ladders, freshness fields, factor-contribution rules, universe/tradability gates, duplicate-deployment probes, and tight regression tests for trading dashboards.
- See `references/local-control-plane-safety.md` for loopback binding, API method/route allowlists, disabled high-impact controls, live-versus-snapshot priority, and retired-entrypoint audit drift.