# Vesper Daily Operations & Morning Briefing

## Overview
After the factor pipeline runs (factor scores, sector basket), the daily morning briefing compiles key outputs into a scan-ready summary. This reference documents the data sources, file layout, and interpretation rules as of July 2026.

## Project Layout
All paths below are relative to `D:\vesper` (Windows) or `/d/vesper` (git-bash).

| Component | Path | Format |
|---|---|---|
| Factor scores | `vesper_data/factor_scores_YYYYMMDD.json` | JSON |
| Sector basket | `artifacts/evals/sector_basket_YYYYMMDD.md` | MD |
| Pipeline receipt | `artifacts/evals/factor_run_status_YYYYMMDD_hhmmss.json` | JSON |
| Telemetry baseline | `vesper_data/telemetry_baseline_*.json` | JSON |
| Steward state | `.hermes/steward_state.json` | JSON |
| Team learnings | `.hermes/learnings.jsonl` | JSONL |

## Morning Briefing Composition

### 1. Pipeline Status
- Check latest `factor_run_status_*.json` for `evidence_state` (READY / DEGRADED / BLOCKED)
- If BLOCKED: report which required core factor failed
- If DEGRADED: report which weighted factor was rejected

### 2. Factor Scores
- Read `scored_count` from latest `factor_scores_YYYYMMDD.json`
- Compare to `universe_size` (should be ~502)
- Check `external_factor_tickers_excluded` — should be > 0 if market_micro contributes
- Top 3 tickers and scores

### 3. Sector Basket
- Source from latest `sector_basket_YYYYMMDD.md`
- 4 tickers, 1 per top-4 sectors
- If missing, check if `sector_neutral_basket.py` needs to run

### 4. Telemetry
- Run `scripts/telemetry_baseline.py` or check its output
- Count paper evidence days accumulated
- If zero, note that monthly review target is unreachable

### 5. Steward Health
- Read `.hermes/steward_state.json`:
  - `steward_cycle` — how many cycles since start
  - `last_action_status` — ok / failed / no_work
  - `stuck_cycles` — if > 4, escalate to Thomas
- Read last 3 entries from `.hermes/learnings.jsonl` for team knowledge

### 6. Alerts Checklist
| Condition | Output |
|---|---|
| No scores file exists | ⚠️ No scores found — run Daily Pipeline |
| Scores >48h old | ⚠️ Scores are stale — run Daily Pipeline |
| evidence_state = DEGRADED | ⚠️ Factor pipeline degraded — check rejection reasons |
| evidence_state = BLOCKED | 🔴 Pipeline blocked — core factors failed |
| stuck_cycles > 4 | ⚠️ All lanes blocked — escalate to Thomas |
| Telemetry days = 0 | ⚠️ No paper evidence accumulated yet |

### 7. Recommendation
- **Nothing to do** — scores fresh, evidence READY, steward healthy
- **Run Daily Pipeline** — stale or missing scores
- **Escalate to Thomas** — all lanes stuck for multiple cycles
- **Review Alpaca paper account** — if telemetry baseline reports errors