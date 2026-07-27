# Layer 4 Implementation — Guarded Continuity

Built: 2026-07-17/18
Tests: 95 total (15 new for Layer 4)
Verification: all passing, ruff F+E9 clean, py_compile clean

## Retry policy module

**File:** `app/services/retry_policy.py`

Frozen `RetryDecision` dataclass with `evaluate_retry(error, attempt, max_retries=2)`.

### NO_RETRY_PATTERNS (safety wins, never retry)
- `no-submit safety violation`
- `no_submit`
- `safety`
- `run lock held`
- `GPU OOM` / `OOM`
- `data-freshness breach`
- `stale data`
- `run-lock conflict`

### RETRYABLE_PATTERNS (transient, safe to retry)
- `timeout` / `timed out`
- `connection` / `network`
- `temporary file lock`
- `transient`
- `retry`

### Decision logic
1. If remaining retries <= 0 → HOLD ("max retries exhausted")
2. If no error → HOLD ("no error recorded — manual investigation")
3. Check NO_RETRY_PATTERNS first (case-insensitive substring match) → HOLD
4. Check RETRYABLE_PATTERNS → retry
5. Default → HOLD ("unknown error type")

### Test cases (15 tests)
- No error → no retry
- Safety violation → no retry
- GPU OOM → no retry
- Run lock → no retry
- Timeout → retry
- Network error → retry
- Unknown error → no retry
- Max retries exhausted
- Second attempt still retries on timeout
- Third attempt exhausted
- Remaining decrements
- Data freshness breach → no retry
- Stale data → no retry
- RetryDecision.to_dict
- Frozen dataclass

## Monthly review script

**File:** `scripts/cron_monthly_review.py`

Collects daily EOD receipts from `artifacts/evals/daily_paper_evidence_loop_*.json` for the past 30 days.

### Status matching bug fixed
Initial implementation used `"PASS" in status` which double-counted `PASS_NO_ORDER_FAIL_CLOSED_RECORDED` as both PASS and FAIL. Fixed to use `status.startswith("PASS")` / `status.startswith("FAIL")` / `status.startswith("HELD")`.

### Recommendation rules
- `total == 0` → HOLD ("no daily receipts found")
- `fail_count > total * 0.3` → REJECT
- `pass_count < total * 0.5` → HOLD
- Otherwise → APPROVE

### Live test result (2026-07-18)
```
[monthly-review] Monthly Review: APPROVE
  Receipts: 6
  Pass: 5  Fail: 1  Held: 0
  Reason: 5/6 daily loops passed — evidence supports continuation
  Advisory only — Brennan decides promotion.
```

Evidence packet written to `artifacts/cron/evidence/monthly_review_202607.json`.

## Cron wiring

**Script:** `vesper_monthly_review.sh` in `~/.hermes/scripts/`
**Cron job ID:** `ba04ced1de00`
**Schedule:** `0 9 1 * *` (9 AM on 1st of month)
**Delivery:** local (saved to receipts)
**Next run:** 2026-08-01 09:00 ET
