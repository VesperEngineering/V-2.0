# Fail-Closed Factor Pipeline Debugging

Use this when a scheduled factor pipeline appears healthy but fresh scores, baskets, receipts, or dashboard state are missing.

## Trace the complete dependency chain

Inspect each boundary in order:

1. **Trigger state** — verify the daemon process and the actual Windows Task Scheduler entries independently. A status command that instantiates fresh in-memory jobs does not prove the daemon is alive.
2. **Task action** — read the exact wrapper or command configured in Task Scheduler. Confirm its interpreter, working directory, schedule, logon mode, and exit-code behavior.
3. **Artifact lineage** — compare score date, basket date, receipt date, modification time, and current market session. A downstream freshness guard can make a broken upstream chain look safely idle.
4. **No-side-effect readiness** — provide a `--dry-run` that lists required scripts/files in dependency order without computing signals or placing broker orders.
5. **Safe end-to-end run** — execute only the no-order chain (scores → basket → dashboard), then inspect the produced artifacts. Test broker execution separately and only with explicit scope.

## Failure rules

- A wrapper must return the failing child's nonzero exit code; a final `echo` must not turn failure into Task Scheduler result `0`.
- Stop immediately when a required stage fails. Do not generate a basket from missing or stale same-date scores.
- Declare the **core factor set** that defines the live strategy. Require non-empty outputs from every core factor before publishing scores. Optional factors may fail only if the artifact records that fact and the strategy denominator remains unchanged.
- Write artifacts atomically after admission passes; do not overwrite the last good artifact during a partial run.
- A downstream stale-artifact guard is necessary but is not evidence that upstream automation works.

## Generated subprocess payloads

A parent Python file can compile while the string passed to `python -c` is invalid. For generated child code:

1. Extract payload construction into a named function.
2. Unit-test `compile(payload, "<factor-subprocess>", "exec")`.
3. Probe one real factor and report child return code, stderr, status, and score count.
4. Preserve child stderr on failure; do not collapse syntax errors, timeouts, and data errors into one generic `SKIPPED` message.
5. Make the parent process return nonzero when core-factor admission fails.

## Patch discipline during recovery

After each source patch, re-read the exact region, inspect the diff, run `py_compile` or equivalent, then run the narrow regression test. If a fuzzy patch changes adjacent control flow or indentation, restore the last green state before any further behavior change. Never leave a scheduler-critical file syntactically broken at a turn boundary.

## Broker boundary

Morning-pipeline verification must not call Alpaca rebalance. Never globally cancel open orders: reconcile only strategy-owned orders, because protective stops or other writers may coexist. Keep signal production, basket publication, and broker execution as separately verifiable stages.
