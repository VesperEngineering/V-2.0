# Local Operator Console Control-Plane Safety

Use this checklist when a dashboard server can invoke local scripts or display broker/account/system data.

## Default exposure boundary

- Bind the HTTP server to `127.0.0.1`, not `0.0.0.0`, unless network access is explicitly approved.
- Do not emit wildcard CORS headers by default.
- Keep state-changing behavior on explicit POST routes. A GET request must never refresh data, run a pipeline, mutate a scheduler, or place/cancel orders.
- Maintain a small route allowlist by method and path, and regression-test it.
- Return an explicit fail-closed response (normally 403) for prohibited high-impact routes.

## Authority boundary

Observability approval does not grant execution authority. Do not expose broker/order/rebalance, scheduler mutation, model promotion, risk/target changes, credential handling, or destructive cleanup merely because a callable script exists in the repository.

If the layout must stay stable, retain the control as a disabled button labeled with the authority state (for example, `Rebalance Locked`) and remove its event handler. Verify in the rendered DOM that the button is disabled and has no action binding.

## Verification probes

Check both code and the running service:

1. Socket/listener is loopback-only.
2. Read-only status/live endpoints return expected contracts.
3. State-changing GET returns no action (404/405).
4. Approved bounded POST succeeds.
5. Prohibited order/destructive POST returns 403.
6. Browser control is disabled and has no handler.
7. No secrets, account identifiers, or credential values appear in logs or API errors.

## Live-versus-snapshot rendering

A static payload may initially render a persisted snapshot while a separate endpoint later supplies live data. Make the source and observation timestamp visible. Once live data is recent, periodic payload refreshes must not overwrite it with the older snapshot; track last-live observation time or centralize source priority. Never let broker holdings overwrite a canonical target basket.

## Deployment and audit-path drift

When an entrypoint or product name is retired, search not only launchers but also audit scanners, allowlists, validators, and default-surface inventories for the old path. A full-suite failure may reveal that the audit itself still scans the retired file. Update the audit to the active entrypoint and rerun both the focused audit tests and the full suite.
