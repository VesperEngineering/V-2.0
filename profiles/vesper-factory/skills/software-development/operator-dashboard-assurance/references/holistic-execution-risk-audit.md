# Holistic Execution/Risk/Operations Audit Reference

Use this reference for read-only audits of trading or autonomous execution systems.

## Mutation inventory

Search source, wrappers, CLI dispatch, schedulers, and adapters for:

- `submit_order`, `submit_order`, `create_order`
- `cancel_order`, `cancel_order_by_id`, `replace_order`, `close_position`
- SDK request methods (`POST`, `PUT`, `DELETE`)
- private-client construction and credential loading

For every hit, record the real entrypoint, endpoint/account mode, guard call, policy/config call, and whether the lower-level function is callable independently. A high-level guard does not protect a public mutation primitive.

## Guard checklist

Require all of the following at the mutation boundary, not merely in a CLI wrapper:

- exact broker endpoint and account/mode assertion
- explicit paper/live scope
- current board/approval and market-session gate
- symbol/asset and side restrictions
- finite per-order, per-symbol, aggregate gross/net, and buying-power limits
- stale/unknown open-order policy; never cancel orders without ownership evidence
- deterministic client order ID derived from immutable intent
- one retry-free response-uncertain branch that reconciles by client ID
- durable per-order receipt with request hash, policy hash, response classification, and timestamps
- fail-closed behavior for missing or stale account/data evidence

## Evidence integrity

Do not treat a successful read as a successful fill. Reconcile by exact order identity and require broker terminal status:

- `new`/`accepted`/`pending_new`: no fill
- `partially_filled`: use only `filled_qty`, not requested `qty`
- `filled`: use actual fill quantity and average price
- `canceled`/`expired`/`rejected`: no fill
- unknown or malformed: blocked/unknown, never green

Check source timestamp, observation timestamp, freshness SLA, requested side/notional, client ID, and broker position against local artifacts. Do not select “latest order for symbol” when multiple orders can exist. Local CSV/Markdown evidence must not outrank broker identity or be accepted solely because its status line says `PASS`.

## Scheduler and supervision

Enumerate Windows Task Scheduler tasks, service/startup wrappers, internal schedulers, job registries, and generated status files separately. Verify action, working directory, interpreter, account/logon context, enabled state, last result, next run, history availability, timeout, retry, overlap policy, and output receipt.

Red flags:

- documented `run.py` or job registry absent from the repository
- status generator reads a different scheduler or hard-coded shadow directory
- synchronous scheduler loop blocks heartbeat and other jobs
- timeout uses `subprocess.run` without process-tree termination
- `_RUNNING`/supervision state is displayed but never populated
- successful manual invocation treated as proof of unattended scheduling

## Safe read-only probes

Preferred evidence commands:

```text
python -m compileall -q <runtime packages>
python <scheduler-entrypoint> --status
# AST/static inventory script for mutation calls and guard callers
# fake-transport tests only when explicitly allowed; otherwise provide but do not run
```

During a user-requested read-only audit, do not call broker/data APIs, invoke real or fake order paths, mutate scheduler definitions, regenerate canonical receipts, or edit the issue registry unless explicitly authorized. Report the exact probes run and the resulting evidentiary limits.

## Reporting template

For each finding include:

- severity and concrete operational consequence
- exact path and line range
- mutation/evidence/scheduler data flow
- safe reproduction command or fake-transport test design
- minimal repair at the boundary
- what was deliberately not run

Prioritize alternate unguarded entrypoints, dead policy plumbing, false fill/P&L evidence, and orphaned scheduler workers above cosmetic dashboard issues.
