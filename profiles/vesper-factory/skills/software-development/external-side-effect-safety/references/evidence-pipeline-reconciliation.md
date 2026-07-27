# Evidence Pipeline Reconciliation

Use when a guarded workflow has validators/consumers that depend on dated receipts produced by upstream jobs.

## Required method

1. Enumerate consumer receipt paths and statuses from the gate implementation.
2. Trace each receipt to an explicit producer; a validator without a producer is an incomplete control.
3. Put producers in dependency order in the scheduler: source ingest → source validation → model scores → portfolio selection → candidate evidence → read-only broker/account observations → their validations → pretrade.
4. Bind candidate evidence to the model path that actually runs in the scheduled pipeline. Reject legacy/alternate model reports even when their markdown schema is valid.
5. Require source-date equality across score artifact, basket, candidate receipt, and data receipt. Require factor evidence state and universe checks, not merely non-empty rows.
6. Preserve separate semantics:
   - receipt `PASS`: evidence was produced and structurally validated;
   - operator decision `hold for review` / `no action`: execution authorization is not implied and the path must stop before preflight or remote reads;
   - exact `paper_order` intent: binds symbol, side, amount, date, and operator scope but still does not bypass board/preflight/session guards;
   - pretrade and board gates independently control mutation.
7. Keep generic scheduled surfaces preview/reconciliation-only. A scheduler must not turn a green no-action receipt into mutation authority; route any separately approved non-preview action through the authoritative intent loop.
8. Use one shared accepted-status predicate across the loop, reconciliation monitor, fill/position evidence, portfolio evidence, and validators. Include exact reconciled success; do not let one downstream consumer silently reject a status introduced by the submitter.
9. Before any post-effect remote read, require current market date, accepted submission truth, and exact preflight/submission envelope parity. Recompute the deterministic remote ID and query that identity directly. Verify ID, date, symbol, side, and amount before position reads; never select the latest same-symbol item.
10. Run the full consumer in no-submit mode and verify `First failed step: none`; individual producer exit codes are insufficient. For mutation-capable code, also test holiday and early-close boundaries with one injected market-time value threaded through date and session gates.

## Reusable verification shape

```text
source ingest                         PASS
source/data evidence                  PASS
model score artifact                  PASS
portfolio/basket artifact             PASS
candidate evidence                    PASS
activation packet validation          PASS
read-only account observation         PASS
account observation validation        PASS
pretrade readiness                    PASS
full no-submit loop                   PASS_PREVIEW_ONLY_RECORDED
orders submitted                      0
```

## Failure patterns

- A consumer searches for `operator_data_check_*` or `daily_no_order_report_*`, but the morning job only writes raw data, scores, or a dashboard.
- A legacy candidate generator writes a valid-looking report from a different model/database and silently diverges from the scheduled factor basket.
- A dated receipt is present but refers to a different source session; reject it.
- A green evidence receipt is mistaken for execution approval; keep the operator decision and pretrade gate visible.
- A read-only broker observation is run manually once but omitted from the scheduled chain; the next date fails again.
