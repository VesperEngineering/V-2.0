# Cron Dedup + FM Sprint Session (2026-07-09)

## Hermes Cron Dedup

9 Hermes cron jobs were paused because they duplicated the Vesper Scheduler's 8 jobs. Both systems were running the same pipeline simultaneously, causing:
- Double execution of every pipeline step
- Conflicting dashboard_data.json writes (two different scripts)
- Failing Alpaca rebalance double-firing
- Stale portfolio snapshot at 8pm vs live every 5s

### Paused Hermes Jobs
- OHLCV Ingest, Factor Scores, Factor Basket, Alpaca Rebalance
- News Backfill, Live News, Portfolio Snapshot (both 8pm + market hours)
- Dashboard Data Refresh (every 1m)

### Remaining Hermes Jobs (3)
- Vesper Research Engineer — weekly academic paper scan (LLM-driven)
- Sync Cron Status — dashboard status updates every 15m
- Weekend Reminder — one-shot stop-loss reminder

### Rule
Vesper Scheduler (`scheduler/`) is sole pipeline authority. Hermes cron should only run jobs that require LLM reasoning or that the scheduler can't do.

## FM Sprint Summary

### What was built and tested

5 new factors built from mined signals + academic literature:
- channel_breakout (mined IC IR -0.151)
- gap_vol_20d (mined IC IR +0.098)
- gv_cb_interaction (mined IC IR +0.144)
- range_vol_ratio (mined IC IR +0.294 — best solo ever)
- max_return (Bali 2011, published t=-6.22)

All 5 failed FM. Zero new validated factors from this session.

### What was discovered
- size_factor (t=-2.24) was resurrected — previously deleted as "dilutive" but FM says it's significant
- mean_reversion (t=+2.27) is significant in clean regression but drops below 2.0 when noise factors pollute the regression
- Interaction terms (ir x size, ir x mr, size x mr) are all noise

### Signal Mine v5
25 candidate signals tested across 1117 cross-sections (2004-2026). Top findings:
- range_vol_ratio: IC IR +0.294 (t=+9.81) -> FM failed
- vol_concentration: IC IR +0.180 -> likely correlated with size
- max_drawdown_20: IC IR -0.150 -> likely correlated with mean_reversion
- ret_range_20: IC IR +0.143 -> likely correlated with intraday_range

### Academic Research
Subagent scanned literature (Bali 2011, Akbas 2022, Lou 2019, Harvey & Siddique 2000, etc.). Top academic signals (MAX, AB_NR, overnight return, return skewness) were either built and failed or mined and showed weak solo IC.

### Final Blend
```
intraday_range  1.0  (FM t=+3.84)
size            0.5  (FM t=-2.24)
mean_reversion  0.4  (FM t=+2.27)
```
3 FM-validated factors. 7 informational at 0.1. 5 FM-failed at 0.0. 15 total in registry.

### Key Lessons (durable)
1. Solo IC IR up to 0.294 can still fail FM. No solo threshold predicts FM survival.
2. Published academic t-stats (up to -6.22) can fail FM. Academic literature provides ideas, not validation.
3. Adding noise factors to FM inflates SEs on real factors. Always run clean FM after demotions.
4. Interaction terms among validated factors are noise. Don't build them without economic theory.
5. The optimizer's "dilutive" label for size was wrong. FM overrides optimizer. Always.
