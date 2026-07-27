# Cron Migration to Factor Registry

## What Changed
The 02:00 UTC cron job was migrated from `daily_factor_scores.py` (direct call)
to `scripts/run_all_factors.py` (uses the Registry).

## New Entry Point
`scripts/run_all_factors.py`:
```python
from app.factors.registry import get_registry
reg = get_registry()
for name in reg.names:
    try:
        r = reg.run(name, root=str(ROOT), date_stamp=ds, timeout=30)
        results[name] = r
    except Exception as e:
        print(f"  {name}: SKIPPED — {e}")
# Merges all factor scores via equal-weight average
# Writes same data/factor_scores_YYYYMMDD.json format
```

## Why
- New factors are auto-discovered via Registry
- No need to update cron script when adding factors
- Consistent interface: every factor takes `root` + `date_stamp`
- 30-second timeout per factor prevents hung factors (Google Trends) from stalling the pipeline

## Current Factors in Registry (6 as of 2026-07-06)
```python
_default.register_all(
    TechnicalFactor(),     # entropy, hurst, realized_vol         ✅ 14 tickers
    SentimentFactor(),     # WebZ + FinViz news                  ✅ 30 tickers
    InsiderFactor(),       # SEC Form 4 (free)                    ✅ 4 tickers
    GoogleTrendsFactor(),  # Google search volume (rate-limited)  ⏸️ 429
    WhaleFactor(),         # 13F hedge fund filings               🔲 SEC search
    WikiFactor(),          # Wikipedia pageviews                  ✅ 30 tickers
)
```

## Backward Compatibility
- Old `daily_factor_scores.py` still works but is no longer the cron entry point
- Output format is identical: `data/factor_scores_YYYYMMDD.json`
- Dashboard reads from the same file path

## Timeout Guard
Each factor run has a 30-second timeout via `ThreadPoolExecutor`:
```python
def run(self, name: str, timeout: int = 30, **kwargs) -> FactorResult | None:
    factor = self._factors.get(name)
    try:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(factor.compute, **kwargs)
            return fut.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        print(f"  ! {name}: timed out after {timeout}s, skipping")
        return None
```

## Adding a New Factor
1. Create `app/factors/myfactor.py` with a class inheriting `BaseFactor`
2. Implement `_compute()` returning `FactorResult(scores={...}, metadata={...})`
3. Import and register in `app/factors/registry.py` (both `import` line and `register_all()` call)
4. Add to dashboard's Today's Data feed (`_lfeed` in `scripts/factor_dashboard.py`)
5. Next cron run auto-discovers it