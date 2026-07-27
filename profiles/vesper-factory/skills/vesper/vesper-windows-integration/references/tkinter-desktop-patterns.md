# Tkinter Desktop App Patterns for Vesper

Patterns for running Tkinter desktop apps (VOT, VWM, future tools) on
Windows with pythonw.exe. These complement the scheduled-task and
batch-launcher patterns in the main skill.

## 1. CREATE_NO_WINDOW — suppress console flashing

`pythonw.exe` has no console. Every `subprocess.run`/`Popen` in the
Vesper service layer creates a new console window that flashes and
closes. With 5-second polling, this produces 4-5 flashing windows per
cycle.

**Fix:** Globally monkeypatch `subprocess.run` and `subprocess.Popen`
at app startup, before any service-layer code runs:

```python
def _patch_no_window_subprocess(self) -> None:
    import sys
    if sys.platform != "win32":
        return
    import subprocess
    _CREATE_NO_WINDOW = 0x08000000
    _original_run = subprocess.run
    _original_popen = subprocess.Popen

    def _no_window_run(*args, **kwargs):
        flags = kwargs.get("creationflags", 0)
        kwargs["creationflags"] = flags | _CREATE_NO_WINDOW
        return _original_run(*args, **kwargs)

    class _NoWindowPopen(_original_popen):
        def __init__(self, *args, **kwargs):
            flags = kwargs.get("creationflags", 0)
            kwargs["creationflags"] = flags | _CREATE_NO_WINDOW
            super().__init__(*args, **kwargs)

    subprocess.run = _no_window_run
    subprocess.Popen = _NoWindowPopen
```

Call in `__init__` before `self.refresh()`. Do NOT attempt per-call
patches (~30 subprocess sites in the service layer).

## 2. Worktree venv and .env setup

A Vesper git worktree (e.g. `D:/vesper-wt-vot-command-deck`) is a
separate working directory. It does NOT inherit `.venv` or `.env`
from the main repo. Both are needed for any Vesper app that:
- Imports from `app.services.*` (needs the venv's installed packages)
- Reads provider usage or credentials (needs `.env`)

**venv:** Symlink the main repo's venv (requires admin on Windows,
so use `cmd.exe /c mklink`):

```bash
cd D:/vesper-wt-vot-command-deck
cmd.exe /c "mklink /D .venv D:\\vesper\\.venv"
```

**.env:** Copy it (symlinks need admin; `.env` is gitignored so
copying is safe):

```bash
cp D:/vesper/.env D:/vesper-wt-vot-command-deck/.env
```

**Verify .env works:**
```bash
python -c "from app.services.openrouter_usage import get_usage; u=get_usage(); print(u.error, u.remaining_budget_usd)"
```
If `error` is empty and `remaining_budget_usd` is a number, it's working.

## 3. Polling preserve-user-state

When a Tkinter app polls for data on a timer, the refresh cycle must
NOT trample:
- **Scroll position** — capture `yview()[0]` before re-render, restore
  after. Only `see(tk.END)` if the user was already at the bottom AND
  it's a user-initiated action.
- **Card selection** — if `self.selected_key` is set, find it in the
  new data and keep showing it. Only fall back to the default when
  nothing is selected or the key disappeared.

See `vwm-design-contract` skill → `references/vot-build-patterns.md`
pattern #3 for the exact code.

## 4. Desktop shortcut for Tkinter apps

Update `.lnk` to point at `pythonw.exe -m app.vot_tk`:

```powershell
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut('C:\Users\bgonn\Desktop\VOT.lnk')
$lnk.TargetPath = 'D:\vesper\.venv\Scripts\pythonw.exe'
$lnk.Arguments = '-m app.vot_tk'
$lnk.WorkingDirectory = 'D:\vesper-wt-vot-command-deck'
$lnk.IconLocation = 'D:\vesper\assets\vesper-operator-terminal.ico,0'
$lnk.Save()
```

Note: `WorkingDirectory` must be the worktree (where the code lives),
not the main repo. The `-m app.vot_tk` flag tells Python to run the
module, which requires the worktree to be the cwd.

## 5. Launch-and-verify a `.lnk` desktop app (post-install smoke test)

After writing an installer, prove the shortcut actually launches a
visible, console-less window — don't stop at "the .lnk was written."

1. **Launch it** via `Invoke-Item` and give Tk time to build + first poll:
   ```powershell
   Invoke-Item "C:\Users\bgonn\Desktop\VOT.lnk"; Start-Sleep -Seconds 10
   ```
2. **Confirm a real window mapped.** A `pythonw.exe` process with the right
   `CommandLine` is NOT enough — a headless/orphan launch has a process but
   `MainWindowHandle -eq 0` and ~1 thread. Require a nonzero handle and a title:
   ```powershell
   Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" |
     Where-Object { $_.CommandLine -match 'app.vot_tk' } |
     ForEach-Object { Get-Process -Id $_.ProcessId } |
     Select-Object Id, MainWindowTitle, MainWindowHandle, @{n='Threads';e={$_.Threads.Count}}
   ```
   Healthy = `MainWindowHandle -ne 0`, non-empty `MainWindowTitle` (check it
   carries the semantic version, e.g. `VOT v0.1.0`), Threads > 1.
3. **Foreground + screen-capture to verify rendering** (no white/native
   scrollbar, no console window, dark theme). Bring to front with
   `SetForegroundWindow`/`ShowWindow(SW_RESTORE)` via a tiny P/Invoke, then
   `CopyFromScreen` to a PNG and inspect it visually.
4. **Launch from an interactive-ish shell.** `Invoke-Item` from a
   non-interactive/background shell can produce the orphan-process-no-window
   outcome above; if you get a handle of 0 with 1 thread, that's the cause,
   not an app bug. Re-launch and re-check before concluding the app is broken.
5. **Clean up the instance you launched** (`Stop-Process` on the PID you
   started) — but confirm you're killing YOUR launch, not a pre-existing
   user instance (match on start time / the PID returned at launch).
