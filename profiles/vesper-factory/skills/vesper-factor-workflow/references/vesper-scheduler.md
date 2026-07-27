# Vesper Scheduler — Self-Contained Job Daemon

Built 2026-07-09 to replace the Hermes cron dependency. Supports sub-second intervals, market-hours-only flags, and runs independently of the Hermes agent.

## Architecture

The scheduler is a Python daemon at `D:/vesper/scheduler/`:

```
scheduler/
├── __init__.py   # Daemon loop (500ms tick), job model, cron + interval parsing
├── run.py        # Entry point
├── jobs.json     # 8 job definitions
└── logs/         # Per-run log files per job
```

It runs as a single process that ticks every 500ms, checking which jobs should fire. Each job runs in its own subprocess.

## Schedule Formats

**Interval** — parseable suffix:
- `"5s"` — every 5 seconds
- `"30s"` — every 30 seconds
- `"1m"`, `"15m"`, `"1h"` — minute/hour intervals

**Cron** — standard 5-field: `min hour dom month dow`
- `"0 7 * * 2-6"` — 7:00 AM, Tue-Sat
- `"35 9 * * 1-5"` — 9:35 AM, Mon-Fri
- `"0 8-17 * * 1-5"` — hourly 8-5 weekdays

**Market-hours-only flag** (`"market_hours_only": true`): only runs during US equity market hours (9:30 AM – 4:00 PM ET, weekdays).

## Jobs Managed

| Job | Schedule | Type |
|---|---|---|
| OHLCV Ingest | 0 7 * * 2-6 | cron |
| Factor Scores | 0 8 * * 0-6 | cron |
| Factor Basket | 15 8 * * 0-6 | cron (calls sector_neutral_basket.py) |
| Alpaca Rebalance | 35 9 * * 1-5 | cron |
| Portfolio Snapshot | 5s, market hours | interval |
| Dashboard Refresh | 5s | interval |
| News Backfill | 0 9 * * 0-6 | cron |
| Live News | 0 8-17 * * 1-5 | cron |

The portfolio snapshot and dashboard refresh both run every 5 seconds (vs Hermes cron minimum of 1 minute). Both use interval scheduling, which Hermes cron cannot do.

## Key Design Decisions

1. **Subprocess isolation**: Each job runs via `subprocess.run()`. A hung job times out after its configured timeout without blocking the daemon loop.

2. **No external dependencies**: Pure stdlib — no Celery, no Redis, no RQ. Single-file daemon.

3. **Hermes cron redundancy**: Hermes cron jobs for the same pipeline steps are left running. They become harmless redundancy — the scheduler fires first, Hermes fires a minute later as a duplicate that does nothing.

4. **Per-job logs**: Each run writes to `scheduler/logs/<JobName>_YYYYMMDD_HHMMSS.log` with status, elapsed time, stdout, and stderr. The scheduler also logs to `scheduler/logs/scheduler.log`.

## Run Modes

```bash
python scheduler/run.py              # Foreground (debug, Ctrl+C to stop)
pythonw scheduler/run.py             # Background (Windows, no window)
python scheduler/run.py --status     # One-shot: print jobs + next runs as JSON
python scheduler/run.py --debug      # Verbose logging
```

## Windows Startup Installation

A single Task Scheduler entry launches it at boot:

```bash
schtasks /create /tn "Vesper Scheduler" /tr "pythonw D:\vesper\scheduler\run.py" /sc onstart /f
```

## System Tray Icon

`vesper-dashboard/tray_icon.py` provides a system tray indicator using `pystray`:
- **Green V** = server running, dashboard live at localhost:8080
- **Red V** = server down
- Right-click menu: Open Dashboard, Restart Server, Exit
- Auto-starts server if not running
- Health check every 5s

```bash
pythonw vesper-dashboard/tray_icon.py   # Launch tray icon (background)
```

## Dashboard Integration

The aggregator (`vesper-dashboard/aggregator.py`) reads scheduler logs for:
- **Active Jobs panel** — `load_active_jobs()` reads `scheduler/jobs.json` + latest log per job
- **Recent Activity panel** — `load_recent_activity()` reads all log files, deduplicates consecutive same-job entries

## Pitfalls

- **Cron range in hour field**: `"8-17"` can't be `int()`'d — must check `"-" not in hour` before parsing
- **Timezone on log timestamps**: Log timestamps are ET (EDT, -4). Must `.replace(tzinfo=timezone(timedelta(hours=-4)))` when parsing to avoid naive vs aware datetime subtraction errors
- **pythonw vs python**: Use `pythonw` for background launch — `python` opens a visible terminal window

## Why Not Hermes Cron?

Hermes cron was the original scheduler but has three constraints:
1. **1-minute minimum granularity** — can't do 5s or 30s intervals
2. **Hermes-dependent** — pipeline stops when Hermes closes
3. **Path mangling on Windows** — `.sh` scripts break with backslash stripping; requires `.py` wrappers

The Vesper Scheduler fixes all three: sub-second intervals, Hermes-independent, and runs native Python directly.
