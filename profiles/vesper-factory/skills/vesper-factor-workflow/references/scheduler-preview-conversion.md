# Converting an Order Scheduler to a Safe Preview Lane

Use this pattern when a data/factor pipeline is healthy but its scheduled broker task has broader authority than the board grants.

## Safety objective

Preserve the schedule and operational evidence while making broker side effects structurally unreachable. A preview is not merely an execution script with a casual `dry_run` branch; it should have a dedicated entry point and wrapper that contain no submission or cancellation call path.

## Conversion sequence

1. **Snapshot current authority.** Export/query the task name, trigger, principal/logon type, action, last result, and next run. Read the called wrapper and trace its Python entry point through `main()`.
2. **Write the preview contract first.** Test that the preview:
   - validates the exact prior-session basket and target shape;
   - reads open orders, equity, positions, and asset admission only;
   - fails closed on open orders, shorts, malformed targets, or unavailable liquidation quantity;
   - computes proposed reductions before proposed buys;
   - returns `mode: preview_only` and `orders_submitted: false`;
   - never calls submit or cancel methods.
3. **Separate the executable surface.** Add a dedicated preview script and a dedicated scheduler wrapper. Do not route the scheduler through the order-capable connector with a defaultable flag.
4. **Make the task name truthful.** Rename/recreate the task as `... Preview`; update dashboard task allowlists and monitoring jobs. A green task called “Rebalance” is misleading when it cannot trade.
5. **Remove the old route.** Only after the preview task is created and its action verified, delete the old order-bearing task and remove its wrapper so a later operator cannot select it accidentally.
6. **Write durable evidence.** The wrapper log and JSON receipt should record the source basket, digest, target tickers, proposed orders, `preview_only`, and `orders_submitted=false` without credentials or account identifiers.
7. **Verify retained context.** Manually trigger the preview task through Windows Task Scheduler, not directly, and verify `Last Result = 0`, wrapper log, receipt fields, and the configured next run.
8. **Verify the broker independently.** Query same-day paper order history read-only and confirm zero orders. A task result or missing receipt alone cannot prove no submission occurred.
9. **Verify the GUI.** Refresh the aggregator and confirm the visible job is named Preview, reports OK, and system health no longer treats the retired execution task as failed.
10. **Observe one natural cycle.** A manual Task Scheduler trigger proves principal/interpreter/cwd/action wiring, not trigger reliability. Keep the natural-cycle observation open until the scheduled run completes.

## Regression checks

- Unit test proposed-order math using a broker double whose `submit_order` and cancellation methods raise immediately.
- Static safety test that the preview source contains no submission/cancellation call expressions and the wrapper invokes only the preview entry point.
- Dashboard plumbing test that the authoritative Windows task tuple contains the Preview task, not the retired execution task.
- Full test suite and task XML/query verification after mutation.

## Common pitfalls

- **Freshness changes authority in practice.** Repairing data can turn a previously failing order task into an active path; reconcile authority before declaring the system ready.
- **`dry-run` is ambiguous.** A flag inside an execution connector can be omitted, inverted, or bypassed. Prefer structural separation.
- **Task names are operator controls.** Do not leave an order-sounding name on a no-submit task.
- **Comments can defeat static deny tests.** If a test forbids the legacy executable string, avoid repeating that exact path even in wrapper comments; describe it as the order-execution connector.
- **Preview health is not trading approval.** A green preview task proves scheduling and read-only planning only. Re-enabling submissions requires a separate machine-readable board/strategy/account/notional gate and explicit approval.
