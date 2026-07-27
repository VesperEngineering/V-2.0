# Factor Lifecycle & Governance Rules

## Lifecycle Pipeline

Every factor follows this strict sequence:

```
Build → Solo Backtest → Fama-MacBeth Validation → Keep or Kill → Cleanup
```

### 1. Build
Implement in `app/factors/` with a concrete `_compute()` method inheriting from `BaseFactor`. Register in `registry.py`. Use **parameterized SQL** (`?` placeholders, never `.format()` on date lists) when querying SQLite.

### 2. Solo Backtest
Run IC analysis and portfolio backtest. Positive IC IR is necessary but NOT sufficient — solo backtests overfit.

### 3. Fama-MacBeth Validation (Gold Standard)
Regression of forward returns against the factor + ALL other live factors. Newey-West t-stats:
- **|t| > 2.0** → Keep, promote to meaningful weight (0.7–1.0)
- **1.5 < |t| < 2.0** → Keep at informational weight (≤0.2), re-evaluate
- **|t| < 1.5** → Kill entirely. Remove from registry.
- **|t| < 0.0** (negative t) → Immediate deletion. Hurts alpha.

**Critical:** Solo IC IR and optimizer Sharpe are NOT substitutes for FM.

### 4. Live-IC-Only Factors (SEC, Micro, FRED)
Factors without historical coverage (e.g. SEC filings, normalized DB with gaps) cannot run Fama-MacBeth. Use the Live IC Tracker instead:
- Run live IC tracker for 3+ months
- Track rolling 21-day IC IR
- Only promote if rolling IC IR stays > 0.04
- Document in STATUS.md as "Pending Validation"

### 5. Cleanup (Most-Overlooked Step)
After every FM round:
- **Remove 0.0-weight factors from registry.py** — they still consume compute daily
- **Delete orphan factor files** from `app/factors/` that aren't in registry.py
- **Update STATUS.md** with the latest FM results
- **Run the full test suite** to catch any hardcoded references

## Coding Standards for Factors

### SQL: Always Parameterized
```python
# GOOD — parameterized query
rows = conn.execute(
    "SELECT ticker, date, close FROM sp500_ohlcv WHERE date IN ({})".format(
        ",".join("?" * len(date_list))
    ),
    date_list,  # passed as parameters, not injected
)

# BAD — string formatting with date values
# .format() on date lists is a landmine if the query ever accepts user input
```

### SQL: Shared Helpers
Extract repeated SQLite connection + date-fetching patterns into `data_loader.py` or a `factors/db.py` helper. Do NOT duplicate the same `SELECT DISTINCT date` → load rows → close pattern across every factor.

### Score Output
Always output z-scored scores. Use `self.zscore()` for well-behaved distributions. Use rank-based z-score (`_rank_zscore` pattern from market_micro.py) for zero-inflated or heavy-tailed distributions like Amihud illiquidity.

## Common Pitfalls

1. **Dead factors linger on disk.** Always check for orphan `.py` files in `app/factors/` that aren't in `registry.py`. Delete them.
2. **0.0-weight factors waste compute.** They run in the pipeline every day but can never affect the basket. Remove them.
3. **Weight ≠ registered.** A factor at weight 0.0 in `run_all_factors.py` still gets computed via `get_registry()`. The registry dict is the source of truth for what runs.
4. **Solo backtests lie.** A factor that looks great alone often fails FM when controlled for intraday_range and mean_reversion.
5. **Negative FM t-stat means the factor HURTS.** Don't keep it "for research." Delete it.
