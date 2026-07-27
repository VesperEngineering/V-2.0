# Vesper Scheduler — Reference

Self-contained job scheduler in `scheduler/` that replaces Hermes cron as the primary pipeline timer.

**Why:** Hermes cron only fires when Hermes is running, has 1-minute minimum granularity, and ties Vesper to this platform. The Vesper scheduler runs independently via `pythonw scheduler/run.py`.

## Key Capability: Sub-Second Granularity

Interval schedules (`5s`, `30s`, `1m`) enable portfolio snapshots every 5 seconds — previously impossible with Hermes cron's 1-minute floor. Combined with `market_hours_only: true`, intraday jobs run only during 9:30 AM–4:00 PM ET.

## Schedule Formats

- **Interval:** `"5s"`, `"30s"`, `"1m"`, `"15m"`, `"1h"`
- **Cron:** 5-field `"min hour dom month dow"` with `*` and `N-M` ranges
- **Flag:** `"market_hours_only": true`

## Current Jobs (scheduler/jobs.json)

| Job | Schedule | Type |
|---|---|---|
| OHLCV Ingest | 0 7 * * 2-6 | cron |
| Factor Scores | 0 8 * * 0-6 | cron |
| Factor Basket | 15 8 * * 0-6 | cron |
| Alpaca Rebalance | 35 9 * * 1-5 | cron |
| Portfolio Snapshot | 5s | interval, market-hours-only |
| Dashboard Refresh | 5s | interval |

## Install at Boot (Windows)

```bash
schtasks /create /tn "Vesper Scheduler" /tr "pythonw D:\vesper\scheduler\run.py" /sc onstart /f
```