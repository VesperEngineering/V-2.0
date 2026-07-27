# Worker Recommendation Verification

When a cron session arrives and reads team_memory entries claiming a previous worker's recommendations were applied (e.g. "weights adjusted, dead factors removed"), **do not trust the memory at face value**. The team_memory entry may have been written by a worker that reported completion but hadn't actually applied the changes, or the changes may have been overwritten by a later session.

## Verification Pattern

After reading a worker's artifact (mortality report, governance audit, etc.), verify the recommendations were applied by inspecting the actual code state:

```python
# 1. Read the worker's recommendations from its artifact
#    (e.g. research_rez_factor_mortality_20260715.md)
# 2. Extract the expected changes: weights, factor removals, governance sync

# 3. Check actual FACTOR_WEIGHTS vs. expected
from scripts.run_all_factors import FACTOR_WEIGHTS
print(FACTOR_WEIGHTS)  # Confirm weights match the report's recommendations

# 4. Check GOVERNED_FACTOR_WEIGHTS for drift
from app.services.paper_snapshot_factors import GOVERNED_FACTOR_WEIGHTS
run_keys = set(FACTOR_WEIGHTS.keys())
gov_keys = set(GOVERNED_FACTOR_WEIGHTS.keys())
assert run_keys == gov_keys, f"DRIFT: only_in_run={run_keys-gov_keys}, only_in_gov={gov_keys-run_keys}"
assert all(FACTOR_WEIGHTS[k] == GOVERNED_FACTOR_WEIGHTS[k] for k in run_keys)

# 5. Check registry count matches expected
from app.factors.registry import get_registry
print(f"Registry: {len(get_registry().names)} factors")

# 6. Confirm dead factors are actually gone
dead_factors = {"max_return", "amihud", "sp500_technical", ...}
assert not dead_factors & set(FACTOR_WEIGHTS.keys()), f"Still present: {dead_factors & set(FACTOR_WEIGHTS.keys())}"
```

## When to Apply

Apply this verification whenever a prior session's team_memory entry claims work was done that changes the factor registry, weights, or governed weights. The verification is cheap (3-4 Python imports, ~1 second) and prevents accepting stale or incorrect state.

## Why Not Just Trust Team Memory

- Team memory is written by the same agent that may have been interrupted mid-apply
- A worker can report "completed" while its actual code changes failed silently
- A later session or steward action may have overwritten the changes
- The team_memory entry may be a summary from a different worker that only *recommended* changes without implementing them

## Example from Cycle 34

In steward cycle 34, team_memory reported "Rez mortality report recommendations applied: weights adjusted, 5 dead factors removed." Verification showed:
- FACTOR_WEIGHTS confirmed: intraday_range=0.6, size=0.7, mean_reversion=0.6 ✅
- 5 dead factors (max_return, amihud, sp500_technical, massive_intraday, range_vol_ratio) absent from weights ✅
- GOVERNED_FACTOR_WEIGHTS matched FACTOR_WEIGHTS exactly (no drift) ✅
- 15 factors remained in registry ✅

Only after all four checks passed was the work accepted as verified.