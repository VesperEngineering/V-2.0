# Security, Scheduler, and Closure Gates

Use this reference when repairing an operator dashboard that fronts scheduled pipelines or trading/account state.

## Minimal threat-model probe

1. Record the server bind address; `0.0.0.0` is LAN exposure, not a localhost detail.
2. Inspect CORS headers and all state-changing routes.
3. Classify routes as read-only observation, bounded local artifact refresh, configuration mutation, or execution/order authority.
4. Default to loopback and deny execution/order routes unless the user has explicitly approved a remote-control security design.
5. Verify with real HTTP requests: allowed reads, allowed POST refreshes, forbidden GET mutations, and forbidden order actions.

## Payload health probe

Build a fixture whose embedded health says `HEALTHY` but whose generation time is far beyond the refresh SLA. The status API must return down/degraded with a stale-payload reason. This proves API reachability cannot preserve historical green state.

## Execution-artifact parity probe

Test more than filename and row count:

- an older artifact touched more recently than the canonical one;
- heading/date mismatch;
- missing or mismatched source-session provenance;
- stale and future modification times;
- duplicate tickers among the expected number of rows;
- malformed symbols.

The dashboard and execution path must accept and reject the same fixtures. Prefer one shared pure loader/validator. For injectable directories, use `receipt_dir=None` and resolve the current default inside the function; `receipt_dir=CONSTANT` binds too early for monkeypatching.

## Scheduler probes

- Call cron eligibility twice within one matching minute; only the first call may reserve the trigger.
- Test winter and summer Eastern conversions with `ZoneInfo("America/New_York")`.
- Give a task `Last Result = 0` but an old last-run timestamp; health must fail closed.
- Preserve failed task state until an unattended successful run produces a new receipt.

## Review closure checklist

After independent review fixes:

1. Run focused regression tests.
2. Run the full suite.
3. Regenerate the authoritative payload.
4. Restart the exact deployed process.
5. Verify bind address, CORS behavior, and allowed/denied routes.
6. Verify browser bundle version, rendered health, source labels, and timers.
7. Only then issue a trustworthy verdict. If interrupted after step 1, report focused green evidence but keep runtime/full-suite verification open.
