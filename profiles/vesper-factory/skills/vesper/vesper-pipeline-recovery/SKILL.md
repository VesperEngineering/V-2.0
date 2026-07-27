---
name: vesper-pipeline-recovery
description: "Diagnose and fix the Vesper daily factor pipeline — OHLCV staleness, lane monopolization, missing .bat launchers, telemetry recency gates, and scheduled task failures."
category: vesper
---

# Vesper Pipeline Recovery

Diagnose and fix stalled or broken Vesper daily factor pipelines. The pipeline runs daily at 08:05 ET via a Windows Scheduled Task. When it breaks, the entire evidence program stalls.

## Pipeline Architecture

The ordered morning chain (defined in `D:\vesper\scheduler\backup_pipeline.py`):

```
ohlcv_ingest → data_evidence → factor_scores → sector_neutral_basket →
dashboard_refresh → candidate_evidence → activation_packet →
activation_packet_validation → margin_observation → margin_observation_validation
```

Orchestrated by:
- **`scheduler/backup_pipeline.py`** — Python orchestrator with lock, timeout, ordered steps
- **`scheduler/windows_factor_pipeline.bat`** — Windows batch launcher (called by scheduled task)
- **`scheduler/install_windows_factor_task.ps1`** — PowerShell installer for the scheduled task
- **`scheduler/windows_factor_pipeline_task.xml`** — Task Scheduler template

## Trigger Conditions

User reports:
- "Pipeline is blocked" or "OHLCV is stale"
- Factor scores not updating
- Steward cycles report `pipeline blocked` continuously
- "No orders placed" / evidence state stuck
- Lane monopolization (pipeline runs every 15min instead of daily)

## Diagnosis Checklist

Run these checks in order:

### 1. Check OHLCV freshness (what the alert actually reads)

The `health_data_freshness` alert does NOT read the SQLite DB. `scripts/cron_health_watchdog.py::_check_data_freshness` reads `docs/VESPER_FACT_BASE.json` → `board.local_ohlcv_date` and compares to today (`MAX_OHLCV_AGE_DAYS = 4`). That JSON is **manually maintained** — no pipeline step or service writes it — so it can lag behind the real DB even when the pipeline is healthy. Verify against the real DB before correcting the JSON.

Real DB check (table is `sp500_ohlcv`, NOT `ohlcv`):

```bash
python -c "
from pathlib import Path
import sqlite3
db = Path('vesper_data/massive/sp500/sp500_ohlcv.sqlite')
if not db.exists():
    print('DB MISSING')
else:
    conn = sqlite3.connect(str(db))
    max_date = conn.execute('SELECT MAX(date) FROM sp500_ohlcv').fetchone()[0]
    print(f'OHLCV max date: {max_date}')
    conn.close()
"
```

Fact-base check:

```bash
python -c "import json; print(json.load(open('docs/VESPER_FACT_BASE.json'))['board']['local_ohlcv_date'])"
```

If DB is fresh but JSON is stale → minimal verified edit of `local_ohlcv_date` (+ `last_updated`) in the JSON, then re-run `python scripts/cron_health_watchdog.py` to confirm `data_freshness: healthy`. Do NOT touch other board fields (basket, execution flags) — governance-gated. If the DB itself is stale, the pipeline cannot score — fix the pipeline first, JSON second.

### 1b. Scheduled-task clone confusion (critical)

The Windows scheduled task `\Vesper Factor Scores Backup` runs the bat at `C:\Users\bgonn\AppData\Local\VesperFactorRuntime\scheduler\windows_factor_pipeline.bat` — a **second clone**, not `D:\vesper`. The watchdog and Hermes cron wrappers read `D:\vesper`. Always check which clone you're diagnosing: the task's Last Result tells you about the VFR clone; the alert tells you about D:\vesper.

When running `backup_pipeline.py` manually from git-bash, PYTHONPATH must be a **Windows-style** path — MSYS paths in env vars are passed through unchanged and Windows Python silently ignores them, producing `ModuleNotFoundError: No module named 'app'` at the data_evidence step:

```bash
cd /d/vesper && PYTHONUTF8=1 PYTHONPATH="D:/vesper" .venv/Scripts/python.exe scheduler/backup_pipeline.py
```

Also: a tracked background terminal session may report `exit 15` (SIGTERM) while the real Windows python processes detach and keep running — verify with `powershell.exe -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\""` before assuming failure or deleting `logs/backup_pipeline.lock`.

### 2. Check factor score freshness

```bash
ls -lt vesper_data/factor_scores_*.json | head -3
```

Stale scores (3+ days old) mean the telemetry lane will block at the recency gate.

### 3. Check the scheduled task

```powershell
schtasks /Query /TN "\Vesper Factor Scores Backup" /V /FO LIST
```

Key fields to verify:
- **Last Run Time** — when did it last run?
- **Last Result** — 0 = success, non-zero = failure
- **Next Run Time** — is it scheduled for tomorrow 08:05 ET?
- **Logon Mode** — must NOT be "Interactive only" (task fails if user not logged in)
- **Run with Highest Privileges** — should match the install

### 4. Check the pipeline log

```bash
tail -50 logs/windows_factor_pipeline.log
```

Look for the last `COMPLETED OK` or `FAILED exit=...` line.

### 5. Check the batch file exists and is tracked

Check if `scheduler/windows_factor_pipeline.bat` exists on disk AND is tracked in git:

```bash
git status scheduler/windows_factor_pipeline.bat
git ls-files scheduler/windows_factor_pipeline.bat
```

An untracked `.bat` file (shown as `??` in git status) means the scheduled task silently fails and the file is lost on fresh clone.

### 6. Check lane monopolization

If the pipeline runs every 15min on the same data, check if the `ALREADY_SCORED` gate is present in lanes.json:

```bash
grep -A2 'ALREADY_SCORED' .hermes/lanes.json
```

If missing, the pipeline lane has no "already did this work today" check and monopolizes the rotation.

### 7. Check VESPER_FACT_BASE.json for false-green dates

```bash
cat docs/VESPER_FACT_BASE.json | python -c "import sys,json; d=json.load(sys.stdin); print('board local_ohlcv_date:', d.get('board',{}).get('local_ohlcv_date','?'))"
```

If this claims a recent date but the actual DB is stale, the board has a false-green signaling bug.

### 8. Check the pipeline lock

```bash
ls -la logs/backup_pipeline.lock 2>/dev/null || echo "No lock (OK — pipeline not running)"
```

A stale lock file can block the pipeline. Remove it manually if the process is definitely dead.

## Common Failures and Fixes

### A. "Missing .bat file" — scheduled task runs, exit code 1 every day

**Symptom:** OHLCV goes stale, scheduled task returns exit code 1, `windows_factor_pipeline.log` shows no entries or early failure.

**Fix:** Create the missing `scheduler/windows_factor_pipeline.bat` from the template:

```batch
@echo off
setlocal EnableExtensions
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "PYTHONPATH=%ROOT%"
set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
set "LOG_DIR=%ROOT%\logs"
set "LOG=%LOG_DIR%\windows_factor_pipeline.log"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
cd /d "%ROOT%" || exit /b 90

>>"%LOG%" echo [%date% %time%] Starting Vesper Factor Pipeline
if not exist "%PYTHON%" (
    >>"%LOG%" echo [%date% %time%] FAILED missing interpreter=%PYTHON%
    exit /b 91
)
"%PYTHON%" --version >>"%LOG%" 2>&1
"%PYTHON%" scheduler\backup_pipeline.py >>"%LOG%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
if %EXIT_CODE% neq 0 (
    >>"%LOG%" echo [%date% %time%] FAILED exit=%EXIT_CODE%
) else (
    >>"%LOG%" echo [%date% %time%] COMPLETED OK
)
exit /b %EXIT_CODE%
```

**Critical:** Add the .bat to git immediately — an untracked launcher is lost on fresh clone:

```bash
git add scheduler/windows_factor_pipeline.bat
git commit -m "fix: track missing windows factor pipeline bat launcher"
```

### B. "Stale OHLCV" — data is 3+ days behind

**Symptom:** OHLCV max date is 3+ days old. Pipeline scores produce no new data.

**Diagnosis:** First check the log, then run the ingest step manually:

```bash
python scripts/massive_sp500_ingest.py
```

If that succeeds, re-run the full pipeline:

```bash
python scheduler/backup_pipeline.py
```

If the scheduled task is broken, re-install it:

```powershell
# From an elevated PowerShell (Run as Administrator):
cd D:\vesper
scheduler\install_windows_factor_task.ps1
```

### B1. "Refresh OHLCV now" — distinguish the latest published session from today

When the operator requests an immediate OHLCV refresh, run the canonical ingest only (not the full factor/basket chain unless separately requested):

```bash
cd /d/vesper
PYTHONUTF8=1 PYTHONPATH="D:/vesper" .venv/Scripts/python.exe scripts/massive_sp500_ingest.py
```

Then verify the actual database state rather than inferring freshness from the ingest exit code:

```bash
PYTHONUTF8=1 PYTHONPATH="D:/vesper" .venv/Scripts/python.exe -c "
from pathlib import Path
import sqlite3, json
p = Path('vesper_data/massive/sp500/sp500_ohlcv.sqlite')
c = sqlite3.connect(p)
latest = c.execute('SELECT MAX(date) FROM sp500_ohlcv').fetchone()[0]
rows = c.execute('SELECT COUNT(*) FROM sp500_ohlcv WHERE date = ?', (latest,)).fetchone()[0]
c.close()
fb = json.loads(Path('docs/VESPER_FACT_BASE.json').read_text())['board']
print('OHLCV_MAX=', latest, 'LATEST_SESSION_ROWS=', rows, 'FACT_BASE=', fb.get('local_ohlcv_date'))
"
```

The ingest intentionally starts from **yesterday** and downloads the last five available weekdays. Around the current market close, the current-day Massive flatfile may still be unpublished; do not claim the data is current through today merely because the refresh returned zero. Probe the exact current-day source once when needed, then report either:
- current-day source published → ingest it and verify its 502-row session; or
- `NOT_PUBLISHED` → canonical DB is current through the immediately preceding published XNYS session, with the current-day bar pending publication.

Do not overwrite `docs/VESPER_FACT_BASE.json` when the verified DB date already matches it, especially if that file has concurrent unrelated edits. Run `cron_health_watchdog.py` afterward to verify the freshness reader remains healthy.

### C. "Lane monopolization" — pipeline runs every 15min

**Symptom:** Steward cycles 20+ consecutive pipeline runs, all on the same OHLCV date. Portfolio, governance, research lanes never get a turn.

**Fix:** Add an `ALREADY_SCORED` gate to the pipeline lane check in `.hermes/lanes.json`. The check should verify the score file for the current OHLCV max date doesn't already exist before running the pipeline.

Also add an `ALREADY_RECORDED` gate to the telemetry lane to prevent telemetry re-runs.

### D. "Telemetry recency gate blocked"

**Symptom:** Telemetry check passes on stale data because it tests file existence, not freshness.

**Fix:** The telemetry check must validate that scores are ≤ 3 days old. Example check expression:

```python
from pathlib import Path; import json; from datetime import date
scores = sorted(Path('vesper_data').glob('factor_scores_*.json'))
latest = json.loads(scores[-1].read_text())
score_date = date(int(latest['date'][:4]), int(latest['date'][4:6]), int(latest['date'][6:8]))
assert (date.today() - score_date).days <= 3, f'scores stale: {latest[\"date\"]}'
```

### E. "False-green board date or freshness parser"

**Symptom:** `VESPER_FACT_BASE.json` claims `local_ohlcv_date` is recent, but the actual SQLite DB is days behind — or a board/status parser reports a historical date after the current freshness summary is absent, duplicated, or malformed.

**Fail-closed rule:** A current freshness summary is authoritative. Its absence, more than one summary entry, or any malformed summary entry must resolve the affected freshness domain to `unknown`. Never fall back to historical `Local OHLCV date` or `Local macro-cache date` labels; a stale fallback turns malformed current evidence into a false-green state.

**Fix:** Make the board update/parser read the real DB max date and validate exactly one well-formed current summary before accepting it. Reject missing, duplicate, mixed-validity, and malformed summaries. Correct stale JSON only after the parser contract is repaired. Verify after fix:

```bash
python -c "from pathlib import Path; import sqlite3; c=sqlite3.connect(str(Path('vesper_data/massive/sp500/sp500_ohlcv.sqlite'))); print(c.execute('SELECT MAX(date) FROM ohlcv').fetchone()[0])"
```

Add regression coverage for: missing summary → `unknown`; duplicate summary → `unknown`; mixed malformed + valid summary → `unknown`; one valid summary → exact current values.

### F. "Interactive only" scheduled task constraint

**Symptom:** Task only runs when user is logged in. It misses scheduled runs overnight or after reboot.

**Fix:** Re-install the task from an elevated PowerShell. The installer prompts for the Windows account password (PIN is not accepted):

```powershell
scheduler\install_windows_factor_task.ps1
```

### G. "Pipeline lock stale" — backup_pipeline.lock blocks the next run

**Symptom:** `backup_pipeline.py` returns exit code 75 (`PipelineAlreadyRunningError`).

**Fix:** Verify the pipeline process is truly dead, then remove the lock:

```bash
tasklist | findstr python
del logs\backup_pipeline.lock
```

## Lane Rotation System

The lanes.json defines priority-ordered lanes that the Steward processes in sequence:

| Priority | Lane | Owner | Gate |
|----------|------|-------|------|
| 1 | pipeline | clarke | ALREADY_SCORED check |
| 2 | telemetry | clarke | ALREADY_RECORDED + recency |
| 3 | portfolio | morgan | work_packet completion_evidence |
| 4 | governance | riley | always ready |
| 5 | research | rez | always ready |
| 6 | code_health | clarke | pytest exit code |
| 10 | strategic | thomas | always ready |

Without `ALREADY_SCORED` and `ALREADY_RECORDED` gates, priority 1 and 2 lanes monopolize the rotation every 15min.

## Verification

After any fix:
1. Check `logs/windows_factor_pipeline.log` for `COMPLETED OK`
2. Check OHLCV max date matches expected
3. Check `ls -t vesper_data/factor_scores_*.json | head -1` has today's date
4. Run `python scheduler/backup_pipeline.py --dry-run` to verify all step scripts exist
5. Verify the .bat file is tracked in git
