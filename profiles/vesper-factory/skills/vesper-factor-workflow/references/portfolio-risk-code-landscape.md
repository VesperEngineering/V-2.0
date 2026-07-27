# Portfolio & Risk Code Landscape (2026-07-14)

Snapshot of what portfolio construction and risk management code actually exists
in D:/vesper, versus what the architecture documentation describes.

## Active Signal→Basket Path (Production)

1. `scripts/run_all_factors.py` — weighted-average z-score blend (FACTOR_WEIGHTS at L54-70),
   universe-gated scorer (load_scoring_universe at L119-140)
2. `scripts/sector_neutral_basket.py` — top-1 ticker per top-4 sectors (L87-105),
   fixed 25% per position (L127), writes `artifacts/evals/sector_basket_{date}.md`
3. `scheduler/backup_pipeline.py` L112-116 — chains both scripts at 08:05 ET weekdays
4. **Optional MVO path** — `python sector_neutral_basket.py --mvo [date]` uses the
   wired covariance + MCP pipeline instead of equal-weight. Default path unchanged.

## What Was Wired Into Production (2026-07-14)

The ~120-line integration gap has been closed. The covariance estimator and MCP
optimizer are now reachable from production basket generation via an optional
`--mvo` flag on `scripts/sector_neutral_basket.py`.

| Layer | Production Status | Code Exists? | Details |
|-------|-------------------|-------------|---------|
| Shrinkage optimizer | **Wired via `--mvo`** | ✅ Built + wired | `app/services/portfolio_covariance.py` — Ledoit-Wolf (2004) shrinkage. Called by `portfolio_basket_integration.py`. |
| Correlation-aware sizing | **Wired via `--mvo`** | ✅ Built + wired | `app/services/portfolio_constructor.py` — `MinimumConcentratedPortfolio` via scipy SLSQP, capped at max_weight=0.25, equal-weight fallback. |
| Integration glue | **Created 2026-07-14** | ✅ New file | `app/services/portfolio_basket_integration.py` (~250 lines): `build_risk_aware_basket()` orchestrates sector selection → OHLCV fetch → Ledoit-Wolf → MCP → risk-aware weights. Full fail-closed fallback chain. |
| HRP alternative | Unwired | ✅ Built | `deploy/src/na/portfolio.py` — Hierarchical Risk Parity. Not yet connected to any production pipeline. |
| Turnover penalty | Missing | ❌ None | No rebalance threshold or trade-cost minimization in objective |
| Transaction cost model | Missing (live) | ⚠️ Field only | `intent_portfolio.py:46` has `expected_cost_rate` field but no model feeds it |
| Beta-adjusted exposure | Missing | ❌ None | Only sector diversity (1-per-sector), no factor exposure control |
| Concentration limits | Implicit only | ⚠️ In MCP via max_weight | 4-name cap + max_weight=0.25 constraint, but no Herfindahl enforcement in production |
| VWAP/TWAP execution | Missing | ❌ None | Paper orders use simple market orders via `submit_paper_pilot_order.py` |

### Integration Bridge Completed

The glue code at `app/services/portfolio_basket_integration.py` orchestrates:

1. **Sector candidate selection** — same top-1-per-top-4-sectors logic (extracted to
   `_select_sector_candidates` for reuse)
2. **OHLCV price fetch** — split-adjusted close prices from `sp500_ohlcv.sqlite`
   via `fetch_adjusted_ohlcv_rows` (63-day default lookback)
3. **Ledoit-Wolf shrinkage** — `LedoitWolfCovariance.from_prices()` produces a
   well-conditioned covariance matrix
4. **MCP optimisation** — `MinimumConcentratedPortfolio.optimize()` with
   long-only, full-investment, max-weight constraints
5. **Fail-closed fallback** — any failure in steps 2–4 drops back to equal-weight
   (0.25 × 4), guaranteeing the scheduler always gets a valid basket

**CLI entry:** `python scripts/sector_neutral_basket.py --mvo [YYYYMMDD]`
**Tests:** `tests/test_portfolio_basket_integration.py` (22 tests, 1.3s)
**Memo:** `artifacts/evals/portfolio_construction_memo_morgan_20260714.md`

The `--mvo` flag is opt-in; the default path is completely unchanged so the
existing scheduler does not need modification until an operator chooses to
enable risk-aware weighting.

## Duplicate / Dead Code (Cleaned 2026-07-14)

| File | Status | Issue |
|------|--------|-------|
| `scripts/vesper_factor_basket.py` | **Archived** → `scripts/archived/` | Dead parser, no scheduler wiring |
| `scripts/alpaca_rebalance.py` | **Archived** → `scripts/archived/` | Disabled exit but still loaded Alpaca creds; mutation surface removed |
| Output conflict | **Resolved** | `sector_neutral_basket.py` now writes `sector_basket_{date}.md` (was `vesper_factor_basket_*.md`) |
| Dashboard | **Updated** | `_last_basket()` reads `sector_basket_*.md`; `gen()` invokes `sector_neutral_basket.py`; `reb()` no longer calls dead Alpaca code |

## Risk Management Code (All Research-Phase)

| Component | File | Status |
|-----------|------|--------|
| Risk policy definitions | `app/services/position_risk.py` L14-37 | Pure dataclasses, broker-free, report-only |
| Risk backtest engine | `app/services/position_risk_backtest.py` (1055 lines) | Survivor-cohort diagnostic; all variants REJECTED |
| Backtest runner | `scripts/backtest_position_risk.py` | Outputs SHADOW_ONLY at best |
| Drawdown breaker | `scripts/dd_circuit_breaker.py` | Proven harmful (Sharpe -0.29, 213 false triggers) |
| Stop-loss design doc | `docs/STOP_LOSS_DESIGN.md` | Explicitly NOT AUTHORIZED — historical draft only |
| Stop registry | None | Referenced in design doc, never created |
| Stop monitor | None | Referenced in design doc, never created |
| Live stop execution | None | `scheduler/backup_pipeline.py` has no risk/stop step |

## Paper Execution Handoff

The bounded paper lane routes through `scripts/run_daily_paper_evidence_loop.py` →
`scripts/submit_paper_pilot_order.py`, which is a **single $5 AAPL buy preview**,
NOT a portfolio rebalance. The accepted-paper basket (`XLK, NFLX, QQQ, IWM, COST`)
is a static five-name selection, not a factor-driven rebalance.

## Governance (Lane Manifest)

`app/services/lane_manifest.py:107-109` registers domain
`portfolio_construction_and_risk` with description "Portfolio sizing,
constraints, concentration, costs, capacity, and risk evidence". Two lanes
are registered under this domain — both in **research-phase** (not active):

| Lane ID | Title | Status | Source of Truth |
|---------|-------|--------|----------------|
| `portfolio_covariance_estimation` | Portfolio Covariance Estimation Lane | research | `app/services/portfolio_covariance.py` |
| `portfolio_construction_mcp` | Portfolio Construction MCP Lane | research | `app/services/portfolio_constructor.py` |

Both lanes carry report-only authority and artifact roots under
`artifacts/evals/` and `out/`. The integration bridge
(`app/services/portfolio_basket_integration.py`) now connects them to production
via the `--mvo` flag on `sector_neutral_basket.py`.

## Parameter Conflicts

- Stop-loss ATR period: skill says ATR(14), repository design doc may say ATR(20)
- `position_risk.py:17-24` defaults: atr_multiplier=3.0, min_stop=12%, max_stop=20%
  (matches what the skill calls the "condensed reference")