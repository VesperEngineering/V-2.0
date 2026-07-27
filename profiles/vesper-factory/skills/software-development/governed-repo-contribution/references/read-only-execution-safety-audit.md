# Read-only broker/execution safety audit

Use this reference when auditing Alpaca or other broker-facing execution code without credentials, network calls, or source edits.

## Audit matrix

| Boundary | Required question | Fail-closed expectation |
|---|---|---|
| Pre-submit gate | Is the final guard on the side-effect boundary? | Direct lower-level calls cannot bypass scope, account, mode, symbol, side, notional, or session checks. |
| Endpoint selection | Is the scheme/hostname exact? | Parse and compare exact allowlisted origin; never use substring checks. |
| Session gate | Does the calendar know holidays and early closes? | Unknown calendar/session state blocks submission. Weekday plus fixed hours is insufficient. |
| POST outcome | Can the broker accept while the client sees an exception? | Distinguish rejected, confirmed accepted, and unknown. Unknown blocks automatic retry. |
| Idempotency | Can a retry be tied to the first attempt? | Deterministic unique client order ID; reconcile before retry. |
| Reconciliation | Is evidence tied to the submitted order? | Match exact order/client ID, not merely most recent order for a symbol. |
| Fill semantics | Does PASS mean confirmed fill? | Require broker status `filled` and valid filled quantity/price; pending/canceled/partial states remain non-PASS unless explicitly modeled. |
| Test coverage | Are dangerous paths represented? | Include ambiguous transport failure, holiday/early close, lookalike host, pending/canceled orders, multiple same-symbol orders, and direct lower-level invocation. |

## High-value reproduction patterns

### Ambiguous POST result

Inject a fake transport that records that the broker accepted the payload and then raises a timeout. The expected result is `ORDER_STATUS_UNKNOWN` (or equivalent), never `FAIL_CLOSED_NO_ORDER`, and a retry must be refused until reconciliation.

### Lookalike endpoint

Probe the guard with `https://paper-api.alpaca.markets.evil.invalid`. It must reject without making a request. Also test HTTP, live host, userinfo, alternate ports, and unexpected paths if the configuration accepts full URLs.

### Calendar boundary

Probe a known exchange holiday and an early-close date during nominal weekday hours. Both must be blocked. Probe the regular open and close boundaries, including timezone-offset datetimes.

### Wrong order selected for evidence

Return two same-symbol orders: a recently submitted pending order and an older filled order, or two orders with different client IDs. Evidence must match the submitted order identity and must not report the unrelated order as the fill.

## Reporting

For each finding record the exact path and line range, severity, trigger/input, observed behavior, operational consequence, and one minimal fix. Separate source behavior from test-harness/setup failures. A test that cannot collect or clean up is evidence about validation reliability, not proof that the audited behavior passed or failed.
