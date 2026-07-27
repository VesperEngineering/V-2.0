# Vesper Quant Research Path — Active Inventory (2026-07-14)

Read-only inventory of the canonical `D:/Vesper` research pipeline. Use this
to separate active production paths from stale research artifacts during any
future audit or cleanup.

## Active Pipeline (what actually runs daily)

| Stage | Entry Point | Path |
|-------|------------|------|
| Factor scoring (automated) | `scripts/run_all_factors.py` | `D:/Vesper/scripts/run_all_factors.py` |
| Factor admission (paper) | `scripts/run_paper_factor_admission.py` | `D:/Vesper/scripts/run_paper_factor_admission.py` |
| No-order + PO-007 report | `scripts/advance_accepted_paper_observation_cycle_from_no_order_report.py` | `D:/Vesper/scripts/` |
| Daily paper evidence loop | `scripts/run_daily_paper_evidence_loop.py` | `D:/Vesper/scripts/run_daily_paper_evidence_loop.py` (795 lines, single canonical entry) |
| Operator surface | `app/operator_terminal.py` | `D:/Vesper/app/operator_terminal.py` |

**Critical architectural observation:** `run_daily_paper_evidence_loop.py` does
NOT import any factor, backtest, or position_risk module. It parses candidates
from the no-order report markdown and generates evidence CSVs. The factor →
score → champion → intent chain is a separate upstream path.

### Daily loop import chain

```
run_daily_paper_evidence_loop.py
  imports: gui_job_runtime, generate_daily_paper_portfolio_evidence,
           generate_paper_fill_position_evidence, submit_paper_pilot_order,
           validate_daily_paper_portfolio_evidence, validate_paper_fill_position_evidence,
           validate_paper_pilot_pretrade_readiness, execution_guard
  does NOT import: factors, position_risk, backtest modules, intent_portfolio,
                   champion_score_contract, paper_factor_admission
```

### Factor scoring flow (upstream from daily loop)

```
run_all_factors.py → sp500_ohlcv.sqlite → 15 registered factors → factor_scores_YYYYMMDD.json
run_paper_factor_admission.py → paper_factor_source_snapshot.py → paper_snapshot_factors.py
  → paper_factor_admission.py → champion_score_contract.py → intent_portfolio.py
```

### Data sources by path

| Source | Path | Active? |
|--------|------|---------|
| Primary OHLCV | `vesper_data/massive/sp500/sp500_ohlcv.sqlite` → table `sp500_ohlcv` | YES |
| Factor score output | `vesper_data/factor_scores_YYYYMMDD.json` | YES (daily) |
| Massive adapters | `vesper_data/massive/adapters/total_return_ohlcv_adapter_*.sqlite` | Canonical: `20260701T182524Z` |
| Massive adjusted | `vesper_data/massive/adjusted/day_aggs_*.sqlite` | Canonical: `20260701T182524Z` |
| Massive total_return | `vesper_data/massive/total_return/day_aggs_total_return_*.sqlite` | Canonical: `20260701T182524Z` |
| Massive normalized | `vesper_data/massive/normalized/day_aggs_coverage_expanded_20*.sqlite` | Research only |

## Bloat and Stale Paths

### Duplicate/versioned scripts (active caller: NONE found)

- `scripts/vesper_backtest.py` + `_v2.py` + `_v3.py` — three versions, only v3 plausibly active
- `scripts/signal_mine.py` + `_v2.py` + `archived/research/signal_mine_v3.py` + `_v4.py` — four versions
- `scripts/ic_lab.py` + `_v2.py` — two versions

### Stale Massive data stores (~337 MB + 151 GB research)

- `adapters/` — 3 copies (20260622, 20260701T182338Z, 20260701T182524Z) = 99 MB
- `adjusted/` — 4 copies = 109 MB
- `total_return/` — 3 copies = 137 MB
- `normalized/` — 151 GB year-partitioned research data

### Retired/dead code surfaces

- `app/pages/00-12_*.py` — 13 retired Streamlit pages (marked RETIRED per CODING_STANDARDS.md L:90)
- `deploy/nova.py`, `deploy/trade.py` — legacy blocked per AGENTS.md L:73
- `deploy/cli/trade_runner.py`, `deploy/cli/train.py`, `deploy/cli/crypto.py` — gated
- `deploy/src/na/transformer_backtest.py`, `transformer_training.py` — historical
- `deploy/src/na/strategies/crypto/` — unrelated to paper equity evidence
- ~200+ Qlib research/diagnostic services under `app/services/qlib_*.py` — single-use experiments
- ~100+ massive diagnostic services under `app/services/massive_*.py` — research artifacts

### Service-to-test ratio

- 382 service files, 519 test files
- Most services are research/diagnostic with no integration into the daily loop
- File counts: ~502 scripts, only ~7 in the active daily chain

## Three Highest-Value Validity Risks

### RISK 1: PIT Universe / Survivorship Bias (CRITICAL)

- **Path:** `app/services/paper_factor_source_snapshot.py` L:41-62 (SNAPSHOT_SQL)
- **Path:** `app/services/position_risk_backtest.py` L:6-8, L:28-48
- **Evidence:** SNAPSHOT_SQL queries `sp500_ohlcv WHERE date = :source_session` — picks
  current S&P 500 members, not historical PIT membership. `position_risk_backtest.py`
  L:6-8 explicitly admits results are "labeled survivor-cohort diagnostics because the
  universe and sector map are not point-in-time S&P 500 membership data." The
  `BacktestDataProvenance` has `point_in_time_membership: bool` and `point_in_time_sectors: bool`
  that `admit_backtest_data()` checks but never passes `True` for.
- **Active caller:** `run_paper_factor_admission.py` L:97, `run_all_factors.py` L:32,
  `position_risk_backtest.py`
- **Action:** Build PIT S&P 500 constituent history; add admission gate; join factor scores
  against PIT membership.

### RISK 2: Label Timing / Same-Session Information Leakage (HIGH)

- **Path:** `app/services/paper_factor_source_snapshot.py` L:41-62 (snapshot includes source session close)
- **Path:** `app/services/paper_snapshot_factors.py` L:88-99 (factor computation uses source session data)
- **Path:** `app/services/position_risk_backtest.py` L:59-129 (`compute_factor_scores` filters `date <= as_of` including as_of close)
- **Evidence:** Factor features use the source session's own `close` price. If forward-return
  labels start from that same close, the model sees its own label. No purge/embargo gap
  between information window and label window. SESSION_LIMIT=70 lookback includes the
  source session itself.
- **Active caller:** `run_paper_factor_admission.py` L:67-87, `run_all_factors.py`
- **Action:** Add 1-session embargo: features use `date < :source_session`, labels start
  from `:source_session`. Verify champion calibration bin labels align.

### RISK 3: Cost Model Disconnected from Factor/Intent Pipeline (HIGH)

- **Path:** `app/services/paper_application_policy.py` L:38-39, L:82-83, L:281-286
  (hardcoded `commission_bps=10.0`, `slippage_bps=5.0`)
- **Path:** `app/services/paper_snapshot_factors.py` L:18-34 (raw z-scores, no cost deduction)
- **Path:** `app/services/champion_score_contract.py` L:36-59 (calibration bins with
  `after_cost_edge`, `expected_cost`, `cost_model_id`)
- **Path:** `app/services/intent_portfolio.py` L:44-48 (uses `calibrated_after_cost_edge`,
  `expected_cost_rate` from calibration)
- **Evidence:** Policy hardcodes costs but factor computation never applies them. The gap
  is bridged by champion calibration bins, but no validation ties the active calibration's
  `cost_model_id` back to the current policy. Calibration and policy cost models can drift
  silently.
- **Active caller:** `champion_score_contract.py` → `intent_portfolio.py` → daily paper loop
- **Action:** Gate `champion_score_contract.py` L:150-200 to compare
  `calibration.cost_model_id` against active `PaperExecutionPolicy.cost_model_id` and fail
  closed on mismatch. Validate calibration bin `expected_cost` against policy cost parameters.