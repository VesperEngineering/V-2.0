# Evidence-ledger review matrix

| Surface | Required invariant | Minimal regression |
|---|---|---|
| Intake | Artifact is allowlisted and completed | Wrong path/schema yields no accepted event |
| Binding | Stored binding equals SHA-256 of actual source bytes | Modify source after collection; append is unavailable |
| Ledger | Each row links to validated prior hash | Tamper one hash or truncate a line; replay unavailable |
| Ordering | No ambiguous head selection | Duplicate and older/newer ordering cases are explicit |
| Durability | No overwrite/repair under competing writers | Concurrent append test detects lost event or chain fork |
| Freshness | Evidence timestamp, not publication time, drives state | Later status write keeps original evidence time |
| Time parsing | Aware, finite, non-future values only | Malformed, offset, future, and expired timestamps fail closed |
| Status | Healthy return requires successful status publication | Simulate final write failure; result unavailable |
| UI | Evidence posture is display-only | Missing/tampered artifact renders stale/unavailable; no action control appears |
| Authority | No executable reachability | AST/runtime scan finds no dispatch, provider, Kanban, scheduler, broker/order, risk, deployment, promotion, or secret path |

## Suggested status vocabulary

Use an explicit bounded vocabulary such as `FRESH`, `STALE`, `MISSING`, `MALFORMED`, `CONTRADICTORY`, `UNAVAILABLE`, and `UNKNOWN`. Do not equate a readable file, a running process, or a recent publication timestamp with evidence freshness.
