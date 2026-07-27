# Paper-Order Crash and Identity Review

Use this matrix when reviewing a staged broker-order lifecycle. The code under review may differ; test invariants, not names.

## Crash Matrix

| Crash point | Required restart behavior |
| --- | --- |
| Before durable intent | No POST occurred; a fresh attempt may begin normally. |
| After `PREPARED`, before POST eligibility | Revalidate the immutable envelope and exact account. Reconcile the deterministic key before deciding whether a POST is still permitted. |
| After `POSTING`, before or during POST | Treat outcome as unknown. Exact-key GET only; never blindly POST. |
| After remote acceptance, before local accepted state | Exact-key reconciliation must recover the accepted effect and persist provider identity. |
| After accepted state, before receipt publication | Rebuild the receipt from validated durable intent plus exact broker reconciliation; do not remain permanently unknown. |
| During receipt publication | A partial/missing receipt must not override or replace durable intent authority. |

For every row, assert the process-level mutation lock is held across intent inspection, reconciliation, optional POST, state publication, and receipt publication. Assert zero duplicate POSTs.

## Exact Identity Checklist

Require all of the following:

- current authenticated account exactly matches the configured expected account;
- remote `account_id`, when present, is validated before any normalization;
- deterministic client/idempotency key matches exactly;
- provider order ID is a non-empty string and its hash matches the durable intent;
- symbol, side, amount/notional, type, TIF, and accepted provider status match exactly;
- provider timestamp parses as a timezone-aware datetime and resolves to the intended trading date in the market timezone;
- accepted/reconciled state is backed by durable intent and exact remote evidence, never by a local receipt alone.

## Deterministic Adversarial Probes

1. Seed a matching `POSTING` intent with no accepted receipt. Invoke restart handling with a fake exact-key GET. The GET count must be one; returning before GET is a recovery failure.
2. Seed an accepted-looking local receipt with no durable accepted/reconciled intent. It must not be returned as broker acceptance.
3. Return a payload with `id: null`. Submission validation and downstream fill validation must both reject it; hashing `str(None)` is a failure.
4. Return an order payload with a wrong explicit `account_id` while the account endpoint reports the expected account. The order must fail exact identity; never overwrite the wrong field before validation.
5. Test a malformed timestamp such as `2026-06-08-not-a-timestamp`; reject it.
6. Test `2026-06-08T01:00:00Z` against New York trading date `20260608`; it belongs to the previous New York date and must be rejected.
7. Inject a crash after remote acceptance but before local receipt persistence, then restart. Require exact reconciliation, durable provider-ID hash, a reconstructed accepted receipt, and exactly one POST total.
8. Invoke each network-capable evidence/reconciliation helper directly—not only through its scheduler—with an accepted historical receipt, a different symbol, a zero amount, and an amount just above the approved cap. Inject a fake session/runner and assert zero account, order, position, or subprocess reads. Caller validation is defense in depth; the helper owns its own read boundary.
9. Return `null` from both the account endpoint and an order object's `account_id`. Also set the configured expectation or durable hash to the value that coercing `None` would produce. Require rejection before comparison, hashing, order GET, or position GET. This catches validators that appear safe under normal configuration but still use `str(value)` as presence validation.
10. Return a timezone-naive timestamp such as `2026-06-08T14:00:00`. Reject it even if the host timezone would map it to the requested market date; `astimezone()` must never supply missing provider timezone evidence.
11. Compare exact monetary identity with decimal semantics. A broker amount such as `5.004` must not satisfy an immutable `5.00` intent through epsilon tolerance, rounding, or float coercion. Validate durable intent `client_order_id`, order type, and TIF before the first broker read.
12. Exercise the public entrypoint during an actual out-of-window clock period while injecting an in-window `now`. Date selection and the imported market-window guard must consume that same effective clock. Patching only the caller's `datetime` is insufficient when an imported guard reads its own clock; pass `now` explicitly through the entire call chain.
13. Enumerate all wrappers/facades that return shared accepted statuses. Seed only an accepted-looking receipt, omit the durable intent, and replace the authoritative submit/reconcile helper with a call counter. The wrapper must not return accepted or `already exists`; a zero helper-call count plus an accepted result proves a receipt-trust bypass even if a later pipeline stage would fail.
14. Probe the idempotency-key builder with over-precision monetary inputs on both sides of a cent boundary (for example `4.999` and `5.00`). Invalid over-precision must be rejected before key construction. Equal keys or payloads prove that float formatting silently changed the immutable envelope. Repeat the probe at every candidate/receipt facade: a `5.00` receipt paired with a requested `4.999` must fail before pretrade or reconciliation. Parse both values through one canonical exact-cent helper; never compare either side with `:.2f` formatting.
15. Fault-inject accepted-intent persistence independently on every acceptance route: a valid POST response, an exact order found during pre-POST reconciliation, and exact reconciliation after a transport error. In each case, make the accepted/reconciled durable write raise after the last uncertain state is already on disk. Require the public return status and receipt to be `unknown`, submission truth to be `unknown`, the last durable state to remain recoverable (`POSTING`/uncertain), and zero extra POSTs. A broad exception handler that records the error but leaves a previously assigned PASS is a critical fail-open.

## Exact-Current Read-Only Harness

1. Record `HEAD` and repository status before inspection. Preserve unrelated pre-existing dirt as evidence; do not clean or stage it.
2. Enumerate every lifecycle POST site and every caller/consumer of shared accepted statuses. A single safe submitter does not make a receipt-trusting facade safe.
3. Run only mocked lifecycle tests with external execution disabled. Use `PYTHONDONTWRITEBYTECODE=1`, pytest `-p no:cacheprovider`, and a UUID-named basetemp under the host's native temp root—not a repository-local scratch path.
4. In the same test command, capture `HEAD` before and after and require equality. If a rebase or fixup lands mid-review, discard the old SHA verdict, inspect the new lifecycle diff, and rerun with a new basetemp.
5. Recheck repository status afterward. Report repository files created/modified separately from the deliberately external pytest basetemp.

## Review Reporting

For a fail-closed review, report only `PASS` or `BLOCK` and exact `file:line` blockers. Keep each blocker tied to a violated safety invariant; omit style nits and speculative refactors. On PASS, include the stable reviewed SHA, focused-test count, native basetemp, external-call statement, and repository-write statement without adding speculative findings.
