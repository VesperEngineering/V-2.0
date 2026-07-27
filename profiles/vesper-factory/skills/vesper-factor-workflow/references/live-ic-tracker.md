# Live IC Tracker — Architecture & Data Flow

Records each pipeline run's factor scores and computes rolling rank IC
as forward returns become available. Solves the "wiki/insider/sentiment
can't be backtested" problem by accumulating live evidence.

## Data Flow

```
run_all_factors.py
  → writes factor_scores_YYYYMMDD.json
  → calls record_snapshot() from app.services.live_ic_tracker
    → appends to data/factor_score_history.jsonl

aggregator.py (every 30m via Dash Refresh cron)
  → load_live_ics() calls compute_live_ics()
    → reads factor_score_history.jsonl
    → for each snapshot pair, loads OHLCV close prices
    → computes forward return = close_next / close_today - 1
    → computes Spearman rank IC per factor per pair
    → returns {ic_data: {factor: {mean_ic, ic_ir, pct_positive, n, latest_ic}}}
  → output: dashboard_data.json → "live_ics" key
```

## Dashboard Display

```
┌──────────────────────────────────────────────────┐
│ Live Factor ICs                          (rolls daily) │
├──────────┬─────────┬──────────┬───────┬────────┬──────┤
│ Factor   │ IC IR   │ Mean IC  │ % Pos │ Latest │  N   │
├──────────┼─────────┼──────────┼───────┼────────┼──────┤
│ sp500_t… │ +0.051  │ +0.00855 │  56%  │ 0.0092 │ 256  │
│ massive  │ +0.033  │ +0.00538 │  55%  │ 0.0041 │ 256  │
│ finviz_… │ +0.004  │ +0.00038 │  52%  │ 0.001  │ 256  │
├──────────┴─────────┴──────────┴───────┴────────┴──────┤
│ 2 snapshots · 6 IC pairs · updates each pipeline run  │
└──────────────────────────────────────────────────┘
```

## Key Files

- `app/services/live_ic_tracker.py` — record_snapshot() and compute_live_ics()
- `data/factor_score_history.jsonl` — JSON-lines, one snapshot per pipeline run
- `data/sp500_sectors.json` — sector map used by load_live_ics for date alignment

## Gotchas

1. **Needs 2+ real pipeline runs** with different dates before IC rows populate.
   Synthetic scores with `date` values not in the OHLCV DB produce 0 rows.

2. **Date alignment matters**: forward return = close[next_date] / close[snapshot_date] - 1.
   Both dates must exist in `sp500_ohlcv.sqlite`. Runs with the same date are deduplicated.

3. **The aggregator's sys.path must include D:/vesper** to import `app.services.live_ic_tracker`.
   The aggregator runs from `C:/Users/bgonn/vesper-dashboard/` — if the import fails,
   it silently returns `n_snapshots: 0`.

4. **Spearman rank IC** is the metric — robust to outliers. Require ≥5 observations per
   factor per snapshot pair.
