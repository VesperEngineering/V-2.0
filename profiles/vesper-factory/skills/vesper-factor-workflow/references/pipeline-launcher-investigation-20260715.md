# Pipeline Launcher Investigation — 2026-07-15

## Symptom

OHLCV data stale since 2026-07-10 (Friday). Pipeline lane blocked:
```
ValueError: latest OHLCV date 2026-07-10 does not match required XNYS session 2026-07-13
```

The Monday/Tuesday (Jul 13-14) sessions never arrived even though the Windows scheduled task `\Vesper Factor Scores Backup` was configured "Daily" at 08:05 ET. Task `Last Result` = 1 (failure).

## Root Cause

The scheduled task references `D:\vesper\scheduler\windows_factor_pipeline.bat` — a file that **did not exist on disk**. The file was never in git. The task ran daily but returned exit code 1 silently with no visible error output.

## Verification Pattern

```bash
# 1. Check the task configuration
schtasks /query /tn "Vesper Factor Scores Backup" /fo LIST /v
#   → Look at "Task To Run" for the actual executable path

# 2. Verify the referenced file exists
ls -la scheduler/windows_factor_pipeline.bat

# 3. Check the Python pipeline implementation exists and is ready
python scheduler/backup_pipeline.py --dry-run
# Expected output:
#   READY ohlcv_ingest scripts/massive_sp500_ingest.py timeout=600s
#   READY factor_scores scripts/run_all_factors.py timeout=300s
#   READY sector_neutral_basket scripts/sector_neutral_basket.py timeout=60s
#   READY dashboard_refresh vesper-dashboard/aggregator.py timeout=120s
# Exit code 0 = all 4 pipeline scripts present
```

## Fix

Create `scheduler/windows_factor_pipeline.bat`:

```batch
@echo off
cd /d "D:\vesper"
echo [%date% %time%] Starting Vesper Factor Pipeline >> logs\windows_pipeline.log 2>&1
python scheduler\backup_pipeline.py >> logs\windows_pipeline.log 2>&1
set EXIT_CODE=%ERRORLEVEL%
if %EXIT_CODE% neq 0 (
    echo [%date% %time%] FAILED exit=%EXIT_CODE% >> logs\windows_pipeline.log 2>&1
) else (
    echo [%date% %time%] COMPLETED OK >> logs\windows_pipeline.log 2>&1
)
exit /b %EXIT_CODE%
```

## Scheduler Constraints (Pre-existing)

From `schtasks /query /tn "Vesper Factor Scores Backup" /fo LIST /v`:

| Field | Value |
|-------|-------|
| Logon Mode | Interactive only |
| Stop On Battery | Yes |
| No Start On Batteries | Yes |
| Run As User | bgonn |

The task won't fire if the user is logged out or the laptop is on battery.

## Database Proof Points

```
OHLCV DB: D:/vesper/vesper_data/massive/sp500/sp500_ohlcv.sqlite
  Table: sp500_ohlcv
  Rows: 2,479,293
  Tickers: ~502
  Min date: 2003-09-10
  Max date: 2026-07-10 (raw, unadjusted)

Score artifact: vesper_data/factor_scores_20260710.json
  scored_count: 8057 (pre-universe-gate — no universe/external fields)
```

## pytest `--basetemp` Workaround

When running pytest from a cron/service context, `C:\Users\<user>\AppData\Local\Temp\pytest-of-<user>` may be inaccessible (PermissionError on `os.scandir`). Use `--basetemp` to redirect:

```bash
python -m pytest tests/test_scheduler_backup_pipeline.py --basetemp=D:/vesper/.pytest_tmp
```

This is a hardened path the cron process can write to. Clean up the temp dir periodically.
