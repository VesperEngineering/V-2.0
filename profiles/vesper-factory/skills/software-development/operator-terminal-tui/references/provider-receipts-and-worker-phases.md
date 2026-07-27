# Provider receipts and worker phases

## Why this exists

A coordinator event is not evidence of a model invocation. `cycle`, `delegated`, and local `started` events can be produced without any provider request or spend.

## Required evidence model

Use separate streams:

```text
worker activity → coordination/local execution evidence
provider receipt → model invocation/token/cost evidence
provider account telemetry → account-wide usage evidence
```

Only a fresh provider `started` receipt may produce `ACTIVE`. The terminal should derive:

- `COORDINATING`: local Steward cycle
- `DELEGATED`: work signaled; no dispatch receipt
- `QUEUED`: dispatch waiting
- `WORKING_LOCAL`: local work without provider evidence
- `ACTIVE`: fresh provider receipt/lease
- `COMPLETED`, `FAILED`: terminal provider/task receipt
- `STALE`: provider lease expired without terminal receipt
- `IDLE`: blocked, skipped, or no recent evidence

## Receipt ledger pattern

Use an append-only, hash-chained JSONL ledger such as:

```text
.hermes/provider_request_events.jsonl
```

Store only bounded metadata: event ID, timestamp, worker, lane, provider, model, provider request ID, token counts, cost, receipt path, verification status, and hash. Never store credentials, authorization headers, raw prompts, or full responses.

Validate the full chain on read. A malformed or tampered ledger must fail closed rather than silently producing activity.

## Spend reconciliation

Display account-wide provider usage separately from Vesper-attributed usage:

```text
account usage:       provider telemetry total
Vesper-attributed:   sum of completed provider receipts
unattributed:        account usage minus matched receipts, or UNKNOWN
```

Do not report `$0.00` when attribution is missing; report `UNKNOWN` or `unattributed`. A configured model allocation is not evidence that a request occurred.

## Investigation recipe

When the terminal appears busy but tokens do not move:

1. Inspect the worker activity log and count states by worker.
2. Inspect the provider ledger for matching `started`/terminal receipts.
3. Query provider account telemetry without exposing credentials.
4. Compare timestamps and provider request IDs.
5. Report the three-way distinction: local activity, provider calls, and billable spend.
6. Add a regression test proving delegation remains `DELEGATED` until a provider receipt exists.

## Verification

After editing any telemetry or status source, run fresh focused tests against the current workspace—not only a previously passing command—and run compilation plus `git diff --check`. Report the actual pass count and any broader-suite timeout separately.
