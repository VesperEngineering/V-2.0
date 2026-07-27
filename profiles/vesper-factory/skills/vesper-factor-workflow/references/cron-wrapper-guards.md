# Cron Wrapper Guards — Pipeline Defense Design

## Architecture

Three sequential cron jobs with strict upstream dependency: **ingest → scores → basket**. No built-in ordering — all three are independent cron triggers. When they slip from scheduled times, they can collide in the wrong order. These guards prevent silent pipeline failures.

## Job Map (2026-07-09)

| Job | Time | File | Guard | 
|---|---|---|---|
| **OHLCV Ingest** | 07:00 Tue-Sat | `massive_sp500_ingest.py` | None — self-contained writer |
| **Factor Scores** | 08:00 daily | `run_all_factors.py` | None — idempotent file writer (writes `data/factor_scores_YYYYMMDD.json`) |
| **Factor Basket** | 08:15 daily | `sector_neutral_basket.py` (via `vesper_factor_basket.py` wrapper) | Polls scores every 10s, max 1hr, requires <30min old |
| **Alpaca Rebalance** | 09:35 M-F | `alpaca_rebalance.py` | Rejects basket if wrong date OR >90min old |

## Basket Wrapper: Poll-and-Retry for Scores

**File:** `C:\Users\bgonn\AppData\Local\hermes\scripts\vesper_factor_basket.py`
**Cron:** `ec44f11e95d3` at 08:15 AM ET (was 08:10, bumped for buffer; also bumped OHLCV ingest from 07:30 to 07:00 for additional runway)
**Retry:** Polls every 10 seconds, retries up to 1 hour (until 9:15 AM). Only proceeds when scores exist AND are less than 30 minutes old.
**Subprocess:** calls `scripts\sector_neutral_basket.py` (not the old no-order-report bridge).

```python
DS = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
SCORES_PATH = f"D:/vesper/data/factor_scores_{DS}.json"
MAX_WAIT = 3600  # 1 hour — retry until 9:15 AM
POLL = 10        # check every 10 seconds

waited = 0
while waited < MAX_WAIT:
    if os.path.exists(SCORES_PATH):
        age = time.time() - os.path.getmtime(SCORES_PATH)
        if age < 1800:  # less than 30 min old
            break
    time.sleep(POLL); waited += POLL
else:
    print("[ERROR] Scores not ready after 1hr"); sys.exit(1)
```

## Rebalance Guard: Reject Stale Basket

**File:** `D:/vesper/scripts/alpaca_rebalance.py`
**Cron:** `42fa880a5460` at 09:35 AM ET M-F

Three checks before any orders — all exit code 1 (visible "error" in cron status):

```python
# 1. No basket file → error
if not basket_path: sys.exit(1)

# 2. Wrong date → error (must match today-1)
expected_date = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
if expected_date not in str(basket_path): sys.exit(1)

# 3. Too old → error (>90 min)
basket_age = time.time() - Path(basket_path).stat().st_mtime
if basket_age > 5400: sys.exit(1)
```

## Key Design Decisions

- **Retry, don't skip.** Basket waits for scores instead of giving up. A missed basket = missed rebalance day.
- **Fail loud, not silent.** Both guards exit code 1 (error), not 0. Cron status shows "error" → visible in dashboard.
- **90-minute freshness window.** Scores 08:00, basket retries until 09:15, rebalance at 09:35. Basket older than 90 min = from a previous day.
- **Scores data date ≠ run date.** `run_all_factors.py` uses `date.today() - 1 day`. On July 8 morning, writes `factor_scores_20260707.json`. **Check file mtime to see if it ran today, not filename date.**

## 4-File Cross-Reference Diagnostic

When investigating pipeline state, cross-reference these four artifacts:

| File | Tells You | Failure Signal |
|---|---|---|
| `data/factor_scores_YYYYMMDD.json` | Did scores compute? | mtime not current = scores didn't run |
| `artifacts/evals/vesper_factor_basket_YYYYMMDD.md` | Did basket generate? | Missing = basket ran before scores |
| `artifacts/evals/alpaca_receipt_YYYYMMDD.json` | Did rebalance fire? | 0 orders = stale basket no-op |
| `artifacts/evals/alpaca_portfolio_YYYYMMDD.json` | Current equity/positions | Divergence from targets = residuals |
