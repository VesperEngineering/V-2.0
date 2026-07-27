# Vesper active-source evidence gate repair

## When this applies

A VOT/Paper Evidence surface reports `FAIL_CLOSED_DATA_EVIDENCE` even though the current local OHLCV/cache receipt says its active-source preflight passed.

## Authority rule

Separate **active source evidence** from **documentation reconciliation**:

- The configured local active-source fields determine freshness gating.
- Board/status-document dates are still parseable reconciliation evidence, but delayed documentation must not make fresh local data fail closed.
- Malformed date fields still fail closed.
- Require local OHLCV and macro cache dates to meet or exceed the expected latest trading date; do not require all five displayed dates to be identical.
- Retain preflight status, result class, and actionability-decision checks. These prevent a merely well-formatted receipt from becoming authority.

## Candidate evidence

Keep the candidate report and its validation distinct. A raw report with no status can use its specifically named validation sibling; do not let unrelated `STATUS: PASS` files substitute for the producer/validator contract. A no-submit preview may record a valid fail-closed pretrade result; it must never submit an order.

## Repair and verification sequence

1. Inspect the generated loop receipt and identify the first failed step.
2. Compare the source receipt's expected/local dates with board dates; determine whether the discrepancy is local-data staleness or documentation lag.
3. Add a hermetic regression with fresh local dates and stale board dates, plus existing stale/malformed local-data cases.
4. Run the focused daily-loop tests, `py_compile`, a narrow Ruff undefined-name gate, and `git diff --check`.
5. Run the exact no-submit daily loop and its cron wrapper. Verify the wrapper receipt is `PASS` and run the health watchdog afterward.
6. Keep an independent pretrade failure visible as `EVIDENCE BLOCKED`; do not “repair” it by creating activation, margin, or freshness artifacts.

## Expected evidence

- EOD wrapper receipt: `status=PASS`.
- Health watchdog: overall healthy.
- Daily loop: can remain `PASS_NO_ORDER_FAIL_CLOSED_RECORDED` when pretrade correctly closes the order path.
- Pretrade receipt explicitly records `Order submitted: false`.
