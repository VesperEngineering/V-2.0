# FM Validation: The Only Gate That Matters

**Solo IC lies. Every time.** 20+ signals tested across two sessions. Mined signal IC does NOT translate to Fama-MacBeth significance.

## Complete FM Failure Record

| Factor | Solo IC IR / Academic t | FM t-stat | Verdict |
|---|---|---|---|
| range_vol_ratio | **+0.294** (best solo ever) | +1.04 | Failed |
| max_return (Bali 2011) | -5.30 (published) | -1.07 | Failed |
| channel_breakout | -0.151 | +0.02 | Noise |
| gap_vol_20d | +0.098 | -0.04 | Noise |
| gv_cb_interaction | +0.144 | +1.07 | Failed |
| amihud | +0.289 (solo) | -1.77 | Failed |
| sp500_technical | — | +0.58 | Failed |
| massive | — | -0.52 | Failed |

**Pattern**: Solo IC IR up to 0.294 still dies in FM. Academic t=-6.22 still dies. The multivariate controls eat marginal signals.

## The FM Validation Cycle

### 1. Build Factor
- `_compute()` in `app/factors/<name>.py` inheriting from `BaseFactor`
- Use `app/factors/db.py` helpers for SQLite (parameterized queries)
- Source: `vesper_data/massive/sp500/sp500_ohlcv.sqlite`
- Register at informational weight

### 2. Add to FM Script (`scripts/fama_macbeth.py`)
- Add factor name to `factor_names` list
- Add computation logic to `compute_factors()` — numpy ops on panel arrays
- Interaction factors: compute from z-scored parents in the regression loop
- Update `run_all_factors.py` with timeout + initial weight

### 3. Run FM
```
python scripts/fama_macbeth.py
```
Loads 2004-2026 panel (502 tickers x 5662 dates), FRED data, normalized DB. Runs 169+ cross-sectional regressions with Newey-West t-stats (4 lags).

### 4. Run CLEAN FM (critical — see pitfall below)
After demoting failures, run a separate regression with ONLY the validated factors to get undiluted t-stats. See the noise dilution pitfall below.

### 5. Promote or Kill
| t-stat | Action |
|---|---|
| |t| > 2.0 | Promote to 0.5-1.0 weight |
| 1.5 < |t| < 2.0 | Borderline - informational 0.1-0.2 |
| |t| < 1.5 | Kill - weight 0.0 |

### 6. Re-run After Any Factor Set Change
Adding/removing factors shifts ALL t-stats. Always re-run clean FM after demotions.

## Critical Pitfall: Noise Factor Dilution

Adding FM-failed factors to the regression **inflates standard errors on ALL factors**. This can knock real factors below significance:

| Regression | intraday_range t | mean_reversion t | size t |
|---|---|---|---|
| Clean (3 factors only) | **+3.84** | **+2.27** | **-2.24** |
| Polluted (12 factors) | +2.80 | +1.86 (below 2.0!) | -2.43 |

**Always run a clean FM with only the plausible candidates.** The full-factor FM is for discovery; the clean FM is for final weight decisions.

## Interaction Terms Don't Work

Tested 3 interactions among validated factors: ir x size (t=+1.00), ir x mr (t=-0.63), size x mr (t=-0.06). All noise. The factors are individually strong but don't synergize. Don't build interaction factors unless you have an economic theory for why they should interact.

## Hard Rules

- Aggressive culling beats more factors. 3 validated > 20 noisy
- No factor survives at 1d horizon. Edge is 10-21d
- Kill dilutive factors at 0.0. Remove from registry if FM-failed
- Never trust optimizer Sharpe or solo IC over FM t-stats
- FM with Newey-West is the only admission gate
- **Always run clean FM** (only validated factors) after demotions

## Survival Record

20+ signals built and tested -> 3 FM-validated in clean regression:
- intraday_range (t=+3.84) - price dispersion
- size (t=-2.24) - small-cap premium
- mean_reversion (t=+2.27) - short-term reversal

## Current Blend (2026-07-09)

intraday_range 1.0 | size 0.5 | mean_reversion 0.4
Seven informational at 0.1, five FM-failed duds at 0.0.
