---
name: vesper-windows-integration
description: "Patterns for Windows-native integration in Vesper — scheduled tasks, batch launchers, PowerShell installers, shortcuts, VBS launchers, and git-tracking requirements."
category: vesper
---

# Vesper Windows Integration

Canonical patterns for wiring Vesper services into Windows — scheduled tasks, batch launchers, shortcuts, and installer scripts. Every pattern here was burned in by real failures (missing .bat files, interactive-only logon constraints, lost launchers on fresh clone).

## Core Principle: Track Everything

Every `.bat`, `.ps1`, `.vbs`, and `.cmd` file in `scheduler/` and `scripts/` **must be tracked in git**. An untracked Windows launcher is a silent failure waiting to happen — the scheduled task returns exit code 1 every day, the pipeline stalls, and the file disappears on the next fresh clone.

```bash
# Check tracking status
git ls-files scheduler/*.bat scheduler/*.ps1 scheduler/*.xml
git ls-files scripts/*.bat scripts/*.ps1 scripts/*.vbs scripts/*.cmd
```

If any are missing, `git add` them immediately.

## Pattern 1: Scheduled Task Pipeline Launcher (.bat)

**Location:** `scheduler/windows_factor_pipeline.bat`
**Purpose:** Entry point called by Windows Task Scheduler daily at 08:05 ET.
**Called by:** Task `\Vesper Factor Scores Backup`

Template:

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

>>"%LOG%" echo [%date% %time%] Starting [JOB NAME]
>>"%LOG%" echo [%date% %time%] User=%USERNAME% Host=%COMPUTERNAME%

if not exist "%PYTHON%" (
    >>"%LOG%" echo [%date% %time%] FAILED missing interpreter=%PYTHON%
    exit /b 91
)

"%PYTHON%" scheduler\backup_pipeline.py >>"%LOG%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"

if %EXIT_CODE% neq 0 (
    >>"%LOG%" echo [%date% %time%] FAILED exit=%EXIT_CODE%
) else (
    >>"%LOG%" echo [%date% %time%] COMPLETED OK
)
exit /b %EXIT_CODE%
```

Key conventions:
- `%~dp0..` resolves to the repo root regardless of where the .bat lives
- Always uses `.venv\Scripts\python.exe` (not system Python)
- Logs to `logs/windows_*.log` with timestamps
- Exit codes: 90 = cd failed, 91 = missing interpreter, otherwise the script's exit code

## Pattern 2: Scheduled Task Installer (.ps1)

**Location:** `scheduler/install_windows_factor_task.ps1`
**Purpose:** Install or re-install the scheduled task from an XML template.
**Requires:** Elevated PowerShell (Run as Administrator)

Template:

```powershell
$ErrorActionPreference = "Stop"

# Verify admin
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this installer from an elevated Administrator PowerShell."
}

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path.TrimEnd("\")
$templatePath = Join-Path $PSScriptRoot "windows_factor_pipeline_task.xml"
$template = [IO.File]::ReadAllText($templatePath)
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$sid = $identity.User.Value
$userName = $identity.Name

# Substitute placeholders (defined in the XML template)
$rendered = $template.Replace("__VESPER_USER_SID__", $sid).Replace("__VESPER_ROOT__", $root)

# Write rendered XML to temp, then create task
$tempPath = Join-Path ([IO.Path]::GetTempPath()) ("vesper-task-{0}.xml" -f [guid]::NewGuid())
[IO.File]::WriteAllText($tempPath, $rendered, [Text.UTF8Encoding]::new($false))
schtasks.exe /Create /TN "\Vesper Factor Scores Backup" /XML $tempPath /RU $userName /RP "*" /F
```

## Pattern 3: Scheduled Task XML Template (with placeholders)

**Location:** `scheduler/windows_factor_pipeline_task.xml`
**Purpose:** XML template for `schtasks.exe /Create /XML`.
**Placeholders:** `__VESPER_USER_SID__`, `__VESPER_ROOT__`

Key settings in the template:
- `<LogonType>Password</LogonType>` — NOT InteractiveOnly (task runs even when user is logged out)
- `<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>` — runs on battery
- `<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>` — doesn't stop on battery
- `<ExecutionTimeLimit>PT2H</ExecutionTimeLimit>` — 2-hour max
- `<StartWhenAvailable>true</StartWhenAvailable>` — catches up after missed runs
- `<CalendarTrigger>` with `<DaysInterval>1</DaysInterval>` — daily at 08:05 ET

## Pattern 4: Desktop Shortcut (.lnk via PowerShell)

Creates a `.lnk` on the Windows desktop that launches `pythonw.exe` with the right arguments:

```powershell
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\Vesper Foo.lnk")
$Shortcut.TargetPath = "D:\vesper\.venv\Scripts\pythonw.exe"
$Shortcut.Arguments = '"D:\vesper\.local\desktop-tools\vesper-foo\foo.py" --board vesper --root "D:\vesper"'
$Shortcut.WorkingDirectory = "D:\vesper"
$Shortcut.WindowStyle = 7  # 7 = Minimized, 1 = Normal, 3 = Maximized
$Shortcut.Description = "Launch Vesper Foo"
$Shortcut.IconLocation = "D:\vesper\assets\foo.ico"
$Shortcut.Save()
```

**NOTE:** The GUI shortcut scripts at `scripts/create_operator_gui_shortcut.ps1` etc. are RETIRED. Current operator surface is `python -m app.operator_terminal`.

## Pattern 5: WSL Launcher Shortcut (.lnk via PowerShell)

When launching a WSL script from a Windows desktop shortcut:

```powershell
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\Vesper Foo.lnk")
$Shortcut.TargetPath = "wsl.exe"
$Shortcut.Arguments = "/home/brennan/vesper-autoresearch/scripts/foo.sh"
$Shortcut.WorkingDirectory = "/home/brennan/vesper-autoresearch"
$Shortcut.WindowStyle = 7
$Shortcut.Description = "Open Vesper Foo"
$Shortcut.Save()
```

**Important:** If the script uses `xdg-open` to open a browser, it will fail from a WSL shortcut because `xdg-open` can't reach the Windows browser. Instead, create a companion `.bat`:

```batch
@echo off
start /B wsl /home/brennan/vesper-autoresearch/scripts/foo.sh > NUL 2>&1
timeout /t 2 /nobreak > NUL
start http://127.0.0.1:PORT/page.html
```

## Pattern 6: PowerShell After-Close Runner (.ps1)

**Location:** `scripts/run_after_close_ingest_and_checks.ps1`
**Purpose:** Post-market-close ingestion and validation run. Can be called from a scheduled task or run manually.

Convention:
- Parameters with sensible defaults (`$Today`, `$Python`, `$MacroDays`, `$OhlcvDays`, etc.)
- `Resolve-RepoRoot` helper to find the repo root
- `Ensure-PythonPath` helper to find the Python interpreter with fallback paths
- `Run-Step` helper that invokes Python, checks exit code, and throws on failure
- Steps labeled with `==> STEP_NAME` for clear log output

## Pattern 7: Windows After-Close Batch (.bat)

**Location:** `scripts/run_after_close_ingest_and_checks.ps1` (PowerShell wrapper)
**Called by:** could be scheduled or manual

For a pure batch launcher calling a single Python script:

```batch
@echo off
setlocal EnableExtensions EnableDelayedExpansion
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
set "SCRIPT=%ROOT%\scripts\script.py"
set "LOG=%ROOT%\logs\script.log"
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
echo [%date% %time%] Starting>>"%LOG%"
"%PYTHON%" "%SCRIPT%" >>"%LOG%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
if not "!EXIT_CODE!"=="0" (
    echo [%date% %time%] FAILED exit=!EXIT_CODE!>>"%LOG%"
    exit /b !EXIT_CODE!
)
echo [%date% %time%] COMPLETED>>"%LOG%"
exit /b 0
```

Note `EnableDelayedExpansion` with `!EXIT_CODE!` syntax when referencing the variable inside the same block.

## Tkinter Desktop App Patterns

Vesper's Tkinter desktop apps (VOT, VWM) run via `pythonw.exe` and have
Windows-specific integration needs: suppressing console flashing from
subprocess calls, worktree venv/.env setup, polling state preservation,
and desktop shortcuts. See `references/tkinter-desktop-patterns.md` for
all four patterns.

## Verification Checklist

After creating or modifying any Windows integration file:

1. **Is the file tracked in git?** `git ls-files <path>` — if not, `git add` it
2. **Does the .bat find the right Python?** Check `.venv\Scripts\python.exe` exists
3. **Does the scheduled task run non-interactively?** Verify `<LogonType>` is NOT `InteractiveOnly`
4. **Does the scheduled task run on battery?** Check `<StopIfGoingOnBatteries>` and `<DisallowStartIfOnBatteries>` are both `false`
5. **Does the VBS launcher exist?** Note: all `start_operator_gui_*.vbs` files are RETIRED — use `python -m app.operator_terminal` instead
6. **For WSL → Browser shortcuts:** Check if `xdg-open` is used and replace with the `.bat` + `start http://...` pattern

## Files Inventory (active/in-use)

| File | Purpose | Tracked? |
|------|---------|----------|
| `scheduler/windows_factor_pipeline.bat` | Daily pipeline launcher (08:05 ET) | ✔ Required |
| `scheduler/windows_paper_reconciliation.bat` | Paper reconciliation monitor | ✔ Required |
| `scheduler/windows_rebalance_preview.bat` | Paper evidence preview (no-submit) | ✔ Required |
| `scheduler/install_windows_factor_task.ps1` | Elevated scheduled task installer | ✔ Required |
| `scheduler/windows_factor_pipeline_task.xml` | Task XML template w/ placeholders | ✔ Required |
| `scripts/run_after_close_ingest_and_checks.ps1` | Post-market-close runner | Optional |
| `scripts/start_operator_gui_desktop.cmd` | Operator terminal desktop launcher | Active |
| `scripts/install_vot_tk_shortcut.ps1` | Native VOT (app.vot_tk) desktop shortcut → `VOT.lnk` | ✔ Required |

## Pattern 8: Native VOT (Tkinter) Desktop Shortcut

`scripts/install_vot_tk_shortcut.ps1` creates `VOT.lnk` on the Desktop for the
native `app.vot_tk` Tkinter app (contract: `docs/vot-tk-contract.md`). Mirrors
Pattern 4 but launches a module, not a script path:

- **Target:** `.venv\Scripts\pythonw.exe` (no console window)
- **Arguments:** `-m app.vot_tk --root "<repo-root>"` (module form; `--root` defaults to `D:/vesper`)
- **WorkingDirectory:** canonical repo root
- **IconLocation:** `assets\vesper-operator-terminal.ico,0`
- Pre-validates `pythonw.exe`, the icon, and `app\vot_tk.py` exist before writing.

Run/verify:
```powershell
pwsh -NoProfile -File .\scripts\install_vot_tk_shortcut.ps1
# read back the .lnk to confirm TargetPath/Arguments/WorkingDirectory/IconLocation
```

**Verify a REAL launch** (not just a headless build): launch via
`Invoke-Item <lnk>`, then confirm a `pythonw.exe -m app.vot_tk` process whose
`MainWindowHandle -ne 0`. A 1-thread, no-handle process means Tk never mapped a
window (launched detached — use `Invoke-Item`, not bare `Start-Process`). Bring it
forward with `SetForegroundWindow` before screen-capturing, else you photograph
whatever window is on top. Visually confirm: title shows semantic `VOT vX.Y.Z`,
no white/native scrollbars, no console window.

## Pitfalls

- **pytest on Windows dies on a locked temp dir** — `PermissionError: Access is
  denied ...\Temp\pytest-of-<user>` when pytest scans its rootdir. Workaround
  (git-bash): `mkdir -p /tmp/votpytest && TMPDIR=/tmp/votpytest TEMP=/tmp/votpytest TMP=/tmp/votpytest python -m pytest ... -p no:cacheprovider`.
  This is environmental, not a code failure — don't misread it as a red suite.

- **Don't point pytest TMPDIR inside the repo** — it breaks tests that assert
  the system temp is OUTSIDE the repo. MSYS `/tmp/...` lands on the `C:` mount
  while the repo is on `D:` → `ValueError: path is on mount 'C:', start on
  mount 'D:'` (`os.path.relpath` cross-mount); and `D:\repo\.pytest_run` is
  inside the repo → `rel()`/outside-path checks fail. Both look like real test
  failures but are temp-location artifacts. Correct temp: **same drive as the
  repo, outside the repo root** —
  `mkdir -p /d/pytest_tmp && export TMPDIR="D:\\pytest_tmp" TEMP="D:\\pytest_tmp" TMP="D:\\pytest_tmp"`,
  then `rm -rf /d/pytest_tmp` after. A test that only fails under a redirected
  TMPDIR is environmental; re-run under the correct temp before counting it red.
