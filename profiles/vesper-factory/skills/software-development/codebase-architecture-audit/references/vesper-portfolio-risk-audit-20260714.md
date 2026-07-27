# Vesper Portfolio Construction & Risk Layer — Read-Only Audit (2026-07-14)

## Active Signal-to-Portfolio Paths

### Path A: Governed Paper Admission Chain (PRIMARY, ACTIVE)

```
paper_factor_source_snapshot.py  →  paper_snapshot_factors.py  →  paper_factor_admission.py  →  champion_score_contract.py  →  intent_portfolio.py  →  run_daily_paper_evidence_loop.py  →  submit_paper_pilot_order.py
```

| Step | File | Lines | Role |
|------|------|-------|------|
| Immutable snapshot | `app/services/paper_factor_source_snapshot.py` | 1-1341 | Frozen 70-session OHLCV backup from S&P 500 SQLite |
| Factor computation | `app/services/paper_snapshot_factors.py` | 1-292 | 3 governed factors: intraday_range (1.0), size (0.5), mean_reversion (0.4). All z-scored. |
| Factor admission | `app/services/paper_factor_admission.py` | 1-801 | Validated per-ticker scoring with required feature coverage, exclusion reasons |
| Champion scoring | `app/services/champion_score_contract.py` | 1-1234 | After-cost calibration bins (L:643-649), full_weight_net_edge, uncertainty-adjusted |
| Intent construction | `app/services/intent_portfolio.py` | 1-652 | Dimensionless long-only weights: `target_weight = net_edge / full_weight_net_edge` (L:278) |
| Daily loop | `scripts/run_daily_paper_evidence_loop.py` | 1-795 | Board gate → data evidence → candidate intent → pretrade → order |
| Order submission | `scripts/submit_paper_pilot_order.py` | 1-253 | AAPL-only, buy-only, ≤$5.00, Alpaca paper endpoint, fail-closed reconciliation (L:74-92) |

### Path B: Legacy Factor Pipeline (PARALLEL, PARTIALLY DISABLED)

```
run_all_factors.py  →  daily_factor_scores.py  →  vesper_factor_integration.py  →  sector_neutral_basket.py  →  alpaca_rebalance.py (DISABLED)
```

| Step | Status |
|------|--------|
| `scripts/run_all_factors.py` | ACTIVE — factor-score artifact generation |
| `app/services/daily_factor_scores.py` | ACTIVE — different factor set (entropy, hurst, realized_vol_z60) |
| `app/services/vesper_factor_integration.py` | ACTIVE — `apply_factor_scores_to_basket()` |
| `scripts/sector_neutral_basket.py` | ACTIVE — 4-name sector-neutral basket, equal 25% weight |
| `scripts/alpaca_rebalance.py` | **DISABLED** — L:64-69 RuntimeError |
| `scripts/alpaca_portfolio.py` | **DISABLED** — L:72-74 SystemExit |

### Path C: Position-Risk Diagnostic (RESEARCH ONLY)

```
backtest_position_risk.py  →  position_risk_backtest.py (run_variant)
```

All 7 risk variants REJECTED. `deployment_approved = false` on every variant.

## Key Findings

### Sizing: Orphaned policy knobs
`paper_application_policy.py` L:40-55 declares `max_ticker_fraction`, `shadow_capital_usd`, `shadow_tier_multiplier`, `min_executable_fraction`, `max_generated_shadow_tiers` — **NEVER CONSUMED** by any sizing function.

### Covariance: None
No covariance or correlation matrix in portfolio construction. No mean-variance optimization, no risk-parity, no minimum-variance.

### Turnover: Research-only
Turnover tracked only in `position_risk_backtest.py`. No turnover budget in the active paper execution path.

### Transaction Costs: Multiple hardcoded values
- Policy declares `commission_bps`, `slippage_bps` but never consumed
- Research scripts use 10 bps (`vesper_backtest_v3.py` L:34) or 15 bps (`position_risk_backtest.py` L:413)

### Sector/Concentration: Research-only
Sector neutrality exists only in research diagnostics. No sector, beta, or concentration controls in the active paper execution path.

### Drawdown: All variants REJECTED
No drawdown breaker, stop-loss, time stop, or gap breaker approved for any execution mode. `STOP_LOSS_DESIGN.md` explicitly NOT AUTHORIZED.

### Dead Code
- `scripts/alpaca_rebalance.py` — RuntimeError at L:64-69
- `scripts/alpaca_portfolio.py` — SystemExit at L:72-74
- `scripts/dd_circuit_breaker.py` — Tested and rejected
- `scripts/regime_filter.py` — Research only, not integrated

### Duplicate Logic
- Sector-neutral selection: `position_risk_backtest.py` L:370-392 AND `sector_neutral_basket.py` L:87-105
- 3-factor scoring: `paper_snapshot_factors.py` L:196-200 AND `position_risk_backtest.py` L:552-621
- Factor z-scoring: `paper_snapshot_factors.py` L:67-85 (ddof=1) AND `position_risk_backtest.py` L:51-56 (ddof=0)

### Versions: 3 backtest scripts
- `vesper_backtest.py` (v1) — superseded, uses old DB path
- `vesper_backtest_v2.py` (v2) — superseded by v3
- `vesper_backtest_v3.py` (v3) — current, research-only

## Smallest Trustworthy Architecture

The active, verified, fail-closed path: `paper_factor_source_snapshot.py` → `paper_snapshot_factors.py` → `paper_factor_admission.py` → `champion_score_contract.py` → `intent_portfolio.py` → `run_daily_paper_evidence_loop.py` → `submit_paper_pilot_order.py`

## Lessons for Future Audits

1. **Search at repo root, not subdirectories.** `search_files` with `path=D:/vesper/app/services` returned 0 results; `path=D:/vesper` worked.
2. **Verify imports exist before assuming they do.** Files import from modules that may only live in `.worktrees/` — use `find` to confirm.
3. **Read governance docs before code.** The board told us `portfolio_construction_and_risk` was "registered without a current lane" — this framed the entire audit.
4. **Distinguish "research only, not integrated" from "dead."** Scripts like `factor_optimizer.py` are research artifacts, not dead code to be deleted.