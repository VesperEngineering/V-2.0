---
name: vesper-interaction-factors
description: Build, register, and evaluate interaction factors between surviving and dead Fama-MacBeth factors in Vesper's factor pipeline.
category: vesper
---

# Vesper Interaction Factor Workflow

Construct interaction factors (product of z-scores) between surviving FM factors (|t| > 2.0) and dead factors, register them in the daily pipeline, and evaluate via FM regression.

## Latest FM Evidence (2026-07-14)

Run: `python scripts/fama_macbeth.py` — split-adjusted OHLCV, 11-factor regression, 169 steps, 2004-01-01 to 2026-07-13.

**Surviving (|t| > 2.0):**
- **size** (t=+2.09) — log dollar volume (negated, small-cap premium). Sign flipped from t=-2.43 (old raw-OHLCV FM) to t=+2.09. Split-adjusted prices change dollar volume calculation, and the 11-factor regression with 9 additional controls shifts the sign. Still significant.
- **mean_reversion** (t=+2.26) — crossed significance threshold with split-adjusted data (was +1.86 in old raw FM).

**Borderline (|t| 1.5–2.0):**
- **intraday_range** (t=+1.81) — dropped from t=+2.80 (old FM). Split-adjusted data + more controls weakened it.

**Failed (|t| < 1.5):**
- intraday_range_massive_interaction (t=+1.45) — 498 tickers, 169 steps
- range_vol_ratio (t=+1.43) — weakly positive, unchanged
- sp500_technical (t=+0.89) — was +1.72 in old FM
- max_return (t=-0.77) — lottery-effect signal, weak
- massive_intraday (t=+0.70)
- amihud (t=-0.53) — was +0.58
- size_market_micro_interaction (t=+0.28)
- size_insider_interaction (t=+0.28) — Amihud proxy (no historical SEC EDGAR data available for 2004-2026)

**All 3 interaction factors failed FM (|t| < 1.5).** None merited weight promotion. They remain at weight 0.0.

## Prior FM Evidence (2026-07-07, raw OHLCV, 7 factors)
- **intraday_range** (t=+4.10) — prior best factor; weakened by split-adjusted data + more controls
- **size** (t=-2.62) — sign flipped with split-adjusted data and 11-factor regression
- **mean_reversion** (t=+2.00) — borderline in old FM, now significant

## Reference Implementations (4 concrete examples)

### Template: `gv_cb_interaction.py` (existing)
| Aspect | Detail |
|--------|--------|
| File | `app/factors/gv_cb_interaction.py` |
| Parents | gap_vol_20d × channel_breakout (both OHLCV) |
| Coverage | ~500 tickers (S&P admitted) |
| IC IR | +0.144 at 21d (mined) |

### 1. `size_market_micro_interaction` (2026-07-15)
| Aspect | Detail |
|--------|--------|
| File | `app/factors/size_market_micro_interaction.py` |
| Parents | size (surviving) × market_micro (dead, weight=0.1) |
| Coverage | ~363 tickers (intersection of S&P size + broad market_micro) |
| Rationale | Microstructure signals vary by market cap — small caps have wider spreads and different liquidity dynamics |
| Pipeline | ADMITTED, weight=0.0 |

### 2. `size_insider_interaction` (2026-07-15)
| Aspect | Detail |
|--------|--------|
| File | `app/factors/size_insider_interaction.py` |
| Parents | size (surviving) × sec_insider_v2 (dead, weight=0.1) |
| Coverage | ~89 tickers (limited by SEC Form 4 filing activity) |
| Rationale | Insider signals are more informative in small caps with fewer analysts |
| Pipeline | ADMITTED, weight=0.0 |

### 3. `intraday_range_massive_interaction` (2026-07-15)
| Aspect | Detail |
|--------|--------|
| File | `app/factors/intraday_range_massive_interaction.py` |
| Parents | intraday_range (surviving) × massive_intraday (dead, weight=0.1) |
| Coverage | ~498 tickers |
| Rationale | Extreme order flow in high-volatility environments may produce outsized predictive power |
| Pipeline | ADMITTED, weight=0.0 |

## Key Files
- `app/factors/registry.py` — factor registration
- `scripts/run_all_factors.py` — daily pipeline with weights + timeouts
- `app/factors/base.py` — BaseFactor + FactorResult + zscore()
- `app/factors/gv_cb_interaction.py` — existing interaction factor (reference pattern)
- `app/factors/size_market_micro_interaction.py` — size × market_micro
- `app/factors/size_insider_interaction.py` — size × insider
- `app/factors/intraday_range_massive_interaction.py` — intraday_range × massive_intraday
- `scripts/fama_macbeth.py` — FM regression (inline factor computation)
- `artifacts/evals/fama_macbeth_*.json` — FM results

## Implementation Pattern

Interaction factors follow a consistent pattern. No factory class is needed — concrete subclasses of `BaseFactor` are simpler and more auditable:

```python
from app.factors.base import BaseFactor, FactorResult
from app.factors.surviving_factor import SurvivingFactor
from app.factors.dead_factor import DeadFactor


class MyInteractionFactor(BaseFactor):
    name = "my_interaction"
    required_data: list[str] = []

    def _compute(self, *, root=".", date_stamp=None, universe=None, **kwargs):
        surv = SurvivingFactor()
        dead = DeadFactor()
        surv_result = surv._compute(root=root, date_stamp=date_stamp, universe=universe)
        dead_result = dead._compute(root=root, date_stamp=date_stamp, universe=universe)
        if not surv_result.scores or not dead_result.scores:
            return FactorResult(scores={}, metadata={"status": "WARNING"})
        common = set(surv_result.scores) & set(dead_result.scores)
        raw = {t: surv_result.scores[t] * dead_result.scores[t] for t in common}
        final = self.zscore(raw)
        return FactorResult(scores=final, metadata={
            "status": "SUCCESS",
            "scored_count": len(final),
            "source": self.name,
            "parents": [surv.name, dead.name],
        })
```

### Registration Steps
1. **Create the factor file** following the pattern above
2. **Import in `app/factors/registry.py`** and add to `_default.register_all()`
3. **Add timeout** in `scripts/run_all_factors.py`'s `FACTOR_TIMEOUTS` (30-45s depending on parent complexity)
4. **Add zero weight** (0.0) in `FACTOR_WEIGHTS` — required by `ensure_registered_weights()` validation
5. **Add zero weight** (0.0) in `GOVERNED_FACTOR_WEIGHTS` in `app/services/paper_snapshot_factors.py` — **CRITICAL.** If this dict is not updated, the paper admission pipeline silently ignores the new factor. The factor is registered in the pipeline but never admitted to the governed basket, and no error is raised.
6. Do NOT add to `REQUIRED_CORE_FACTORS`
7. Do NOT add a positive live weight — that's a governance decision

**Verification:** After registration, run the drift check to confirm parity:
```python
from scripts.run_all_factors import FACTOR_WEIGHTS
from app.services.paper_snapshot_factors import GOVERNED_FACTOR_WEIGHTS
run_names = set(FACTOR_WEIGHTS.keys())
gov_names = set(GOVERNED_FACTOR_WEIGHTS.keys())
assert run_names == gov_names, f"GOVERNED drift: {run_names - gov_names}"
print(f"All {len(run_names)} factor names match between run_all and paper_snapshot ✓")
```

### Coverage Characteristics
Coverage varies by the narrowest parent:
- **OHLCV × OHLCV**: ~500 tickers (S&P admitted universe)
- **OHLCV × SEC**: ~80-400 tickers (limited by SEC filing activity)
- **OHLCV × market_micro**: ~360 tickers (intersection of S&P 500 with broad Massive panel — market_micro covers 7400+ tickers, but the scoring universe gate restricts to S&P 500)
- **OHLCV × wiki**: ~500 tickers (mostly S&P coverage)

## Adding to FM Regression
In `scripts/fama_macbeth.py`, add interaction terms as products of inline z-scores for OHLCV-based pairs. For non-OHLCV factors (SEC, wiki, FRED), run FM on stored daily scores. Always include parent factors as controls to avoid collinearity.

## Expected Outcome (Empirical — 2026-07-14)

**Actual result: 0/3 interaction factors survived FM** (all |t| < 1.5). This contradicts the Borri et al. (2025) prediction that 3-5 out of ~28 pairs should survive. Possible explanations:

1. **The inline FM proxy doesn't capture the real parent factor.** `size_market_micro_interaction` used Amihud from the S&P 500 OHLCV panel, not the full `market_micro` factor from the normalized DB. The real market_micro includes turnover and VWAP components that may carry more signal.
2. **SEC insider data is unavailable historically.** `size_insider_interaction` used the same Amihud proxy — it's identical to `size_market_micro_interaction`, not a real insider interaction. Without a historical SEC EDGAR database, this can't be tested properly.
3. **The interaction signal is weak in the time domain.** Even the OHLCV×OHLCV pair (`intraday_range_massive_interaction`, t=+1.45) barely registers. The pairwise interaction effect may be real but small, requiring more data or a different test design.

**Recommendation:** keep interaction factors at weight 0.0, test via live IC tracker, re-evaluate after 60 days of live data. Do not build more interaction factors until portfolio/risk layer is complete.

## Pitfalls
- **Coverage varies by parent** — SEC-insider interactions have narrow coverage (~89 tickers) because the insider factor is sparse. This is expected but reduces FM statistical power.
- **Interaction factors can be collinear with parents** — always include parent factors as controls in FM regression. The product z-score is not orthogonal to its parents.
- **GOVERNED_FACTOR_WEIGHTS is a separate surface from FACTOR_WEIGHTS** — adding a factor to `FACTOR_WEIGHTS` in `run_all_factors.py` does NOT automatically admit it to the governed basket. The dict `GOVERNED_FACTOR_WEIGHTS` in `app/services/paper_snapshot_factors.py` is a separate, independent copy. If you add a factor to `FACTOR_WEIGHTS` but forget `GOVERNED_FACTOR_WEIGHTS`, the paper admission pipeline silently ignores it. Always update both, then verify with the drift check snippet in Registration Steps above. This was the root cause of the 3 interaction factors (size_market_micro_interaction, size_insider_interaction, intraday_range_massive_interaction) being silently absent from the governed basket for 6+ steward cycles (2026-07-15).
- **Non-OHLCV factors (SEC, wiki) can't use fast inline FM path** — need stored-score approach.
- **Walk-forward validation needed** — single full-sample FM may overfit. Cross-validate within rolling windows.
- **Start all interaction weights at 0.0** — only promote to positive weight after FM validation.
- **Do not use a factory class** — concrete subclasses are simpler to debug, easier to test individually, and more auditable. Each factor gets its own file.
- **SEC insider data has no historical record** — `sec_insider_v2` scores are only available for the current lookback window (30 days from today). There is no cached historical EDGAR data. Any FM regression that requires `size_insider_interaction` at historical dates (2004-2026) must use a proxy or skip the factor. The `sec_insider_v2_scores.json` in `vesper_data/insider_trades/` is a single-date snapshot only.
- **Standalone FM scripts need `_SPLIT_ADJ_CACHE` pattern** — when loading `split_adjustments.json` in a standalone script (not running through `app.factors.db`), use a module-level global variable, not `Path._cache` attribute. `Path` objects in Python 3.11+ don't support arbitrary attribute assignment. Pattern:
  ```python
  _SPLIT_ADJ_CACHE: dict | None = None
  def _load_split_adjustments() -> dict:
      global _SPLIT_ADJ_CACHE
      if _SPLIT_ADJ_CACHE is not None:
          return _SPLIT_ADJ_CACHE
      ...
  ```
- **Inline FM proxies for non-OHLCV factors are approximations** — the FM script computes Amihud from the S&P 500 OHLCV panel as a proxy for `market_micro`. This captures only the Amihud illiquidity component, not the full turnover + VWAP blend. FM results for `size_market_micro_interaction` and `size_insider_interaction` are lower bounds on the true interaction effect.

## Post-Implementation Lifecycle

After building and registering interaction factors, the governance pipeline is:

### 1. Governance Audit (Riley)
Before any FM validation or weight promotion, an independent governance audit checks:
- **Pattern consistency**: concrete subclass (not factory), `BaseFactor` inheritance, `_compute()` signature
- **Split-adjustment**: uses `fetch_adjusted_ohlcv_rows` (not raw `fetch_ohlcv_rows`)
- **Z-score convention**: cross-sectional z-score → product → z-score again
- **Error handling**: empty parent results return `FactorResult(scores={}, ...)` with WARNING status
- **Metadata**: `parents` field lists both parent factor names
- **Registry**: registered in `registry.py` and `FACTOR_WEIGHTS` at weight 0.0
- **Pipeline**: importable without errors, subprocess timeout configured

Audit findings go to `artifacts/evals/governance_audit_<topic>_<date>.md`.

### 2. Fama-MacBeth Validation (Rez)
After audit passes, schedule FM regression for all interaction factors:
- Run `scripts/fama_macbeth.py` with interaction factors as test assets
- Include parent factors as controls (fail closed on collinearity)
- 2005-2026 data, 21d forward horizon, Newey-West t-stats
- Apply the |t| > 2.0 keep / |t| < 1.5 kill rule
- Sparse factors (e.g. SEC-insider, ~89 tickers) have reduced statistical power — document this limitation

### 3. Weight Promotion Decision
```
FM |t| > 2.0  → promote to positive weight (start at 0.1–0.2, observe)
FM |t| < 1.5  → keep at 0.0 (kill candidate, retire on next cleanup cycle)
Borderline     → keep at 0.0, add to live IC tracker, re-evaluate in 30 days
```

When promoting:
- Update `FACTOR_WEIGHTS` in `scripts/run_all_factors.py`
- Remove from `REQUIRED_CORE_FACTORS` if it was added there (it shouldn't have been)
- Re-run FM regression to confirm the new weight doesn't degrade the blend
- Update all three date sources: `PROJECT_ADVANCEMENT.md`, `docs/VESPER_FACT_BASE.json`, `docs/STATUS.md`

### 4. Live IC Tracker (Factors FM Can't Validate)
SEC-insider and other sparse-data factors can't achieve FM statistical power. Validate them via the rolling 21d forward IC IR in production. If the live IC IR drops below 0.02, alert and consider retiring.

## References
- Borri et al. (2025) — Higher-Order Asset Pricing Factors via Forward Selection FM (arXiv:2503.23501)
- `artifacts/evals/research_rez_20260714.md` — full research survey on surviving factor construction methods
- `artifacts/evals/research_rez_interaction_implementation_20260715.md` — implementation report (3 factors built, tested, verified)
- `app/factors/gv_cb_interaction.py` — existing interaction factor reference
- `app/factors/size_market_micro_interaction.py` — size × market_micro
- `app/factors/size_insider_interaction.py` — size × insider
- `app/factors/intraday_range_massive_interaction.py` — intraday_range × massive_intraday