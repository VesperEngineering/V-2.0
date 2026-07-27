# Freshness and Execution-Authority Reconciliation

Use this after restoring a stale market-data pipeline or changing dashboard/scheduler plumbing.

## Admission sequence

1. Compute the required prior XNYS session from the exchange calendar.
2. Query the exact active OHLCV database and table for `MAX(date)`.
3. Run ingest only through the existing approved provider path; never print credential values.
4. Run the fail-closed artifact chain in order: ingest → scoring → basket → dashboard.
5. Verify, independently of exit code:
   - DB max date equals required session;
   - score payload embeds that session and has finite/non-empty admitted core factors;
   - basket filename, heading, source provenance, cardinality, ticker uniqueness/syntax, and age match the production rebalance loader;
   - dashboard payload reports the same artifact and remains honest about unrelated blockers.
6. Treat non-core factor rejection as an explicit warning requiring later repair; it does not prove the whole pipeline stale, but it must not disappear from receipts.

## Retained Windows-task context

For a non-order factor task, `schtasks /run` is an acceptable retained-context probe. Poll until it leaves `Running`, then require:

- `Last Result == 0`;
- task action points to the intended repository wrapper;
- wrapper log shows every pipeline step completed;
- artifact checks above pass.

This proves principal/interpreter/cwd mechanics, not natural-schedule reliability. Observe the next scheduled run separately.

## Authority cross-check before unblocking

A fresh valid basket may activate an order task that previously failed closed. Before allowing that transition:

| Surface | Required evidence |
|---|---|
| Board | Exact selected basket/strategy, paper/live scope, account scope, and bounded authority interpretation |
| Scheduler | Exact enabled task action and trigger |
| Entry point | Trace from wrapper to `main()` and identify the first broker read/order submission |
| Artifact | Prove the scheduled order path consumes the board-approved artifact, not merely a technically valid different basket |

If the board names one accepted-paper basket while the scheduler submits another factor basket, treat it as an execution-authority mismatch even when both are paper-only. Recommend pausing or preview-only conversion. Obtain the user's decision before scheduler mutation. Never trigger the order-bearing task merely to see whether it works.

## Safe monitoring

Schedule read-only checks after natural cycles. They may inspect task result, logs, provenance, and existing receipts, but must not trigger tasks, call broker APIs, submit/cancel orders, or disclose account/credential values.
