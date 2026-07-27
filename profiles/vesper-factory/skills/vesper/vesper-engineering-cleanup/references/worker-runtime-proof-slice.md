# Worker Runtime Proof Slice

Use this sequence when converting a documented Vesper workforce into a real model-backed worker without widening authority.

## Contract

```text
queued -> claimed -> needs_review -> completed
```

- `delegated` or `claimed` means only that a packet was durably recorded.
- `ACTIVE` requires a fresh provider `started` receipt.
- `needs_review` requires the declared artifact, a physical receipt, and explicit `PASS` verification.
- `completed` requires an independent reviewer; the worker cannot review itself.

## RED -> GREEN order

1. Write tests for exactly-once claim, missing artifact/receipt, declared-artifact mismatch, independent review, and hash-chain tampering.
2. Run the focused tests and observe the expected failure before adding production code.
3. Implement the append-only task ledger and lifecycle transitions.
4. Add a provider adapter only after the local lifecycle is green.
5. Use an injectable fake transport for provider tests; do not spend credits or require credentials in CI.
6. Emit separate provider lifecycle events with worker, lane, model, request ID, usage, receipt path, and verification. Never store secrets or raw prompts.
7. Write the model artifact and a PASS receipt only after validating non-empty provider content, token consistency, and repository-contained paths.
8. Integrate Steward only through an explicit packet runtime (for example `rez_model`). Leave legacy signal-only packets unchanged.
9. If the credentialed path is unavailable, record `failed`, suppress duplicate dispatch, and report the blocker. Never silently switch providers or fabricate a live run.
10. Pass the declared input receipt's bounded content to the model. A path name alone gives a remote model no repository access and can produce generic refusal or speculation; missing/unreadable inputs must be explicit.
11. On Windows, resolve inference credentials in this order: process environment, Vesper `.env`, then Hermes `%LOCALAPPDATA%/hermes/.env`. `OPENROUTER_MANAGEMENT_API_KEY` is usage telemetry, not an inference key. Never print, copy, or commit credential values.

## Verification

Run the focused lifecycle/provider/Steward tests, Python compilation, and `git diff --check`. A green fake-transport suite proves mechanics only. Do not call the workforce real until a real provider request, artifact, receipt, and independent review have all been observed.
