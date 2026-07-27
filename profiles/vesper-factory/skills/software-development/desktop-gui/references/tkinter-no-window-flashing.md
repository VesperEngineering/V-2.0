# CREATE_NO_WINDOW: Suppress Console Flashing in pythonw Tkinter Apps

## Problem

When a `pythonw.exe` Tkinter desktop app (like VOT, VWM, or the
dedicated Kanban panel) polls data via subprocess calls (git, file
checks, `hermes kanban` CLI), each `subprocess.run()` or
`subprocess.Popen()` without `creationflags` creates a new console
window on Windows. The window flashes open and closes within
milliseconds, producing a distracting flicker every poll cycle
(e.g. every 2–5 seconds).

## Root Cause

`pythonw.exe` is a GUI-subsystem executable with no console. When it
spawns a console-mode subprocess (like `python.exe`, `git.exe`,
`cmd.exe`, `hermes.exe`), Windows allocates a new console for the
child process. That console window appears briefly before the
subprocess exits.

## Fix: Global subprocess monkeypatch

Patch `subprocess.run` AND `subprocess.Popen` at the module level
early in app startup, before any service-layer code runs:

```python
def _patch_subprocess(self) -> None:
    import sys
    if sys.platform != "win32":
        return
    import subprocess as sp
    _NW = 0x08000000
    _orig_run = sp.run
    _orig_popen = sp.Popen

    def _nwr(*a, **kw):
        kw["creationflags"] = kw.get("creationflags", 0) | _NW
        return _orig_run(*a, **kw)

    class _NWP(_orig_popen):
        def __init__(s, *a, **kw):
            kw["creationflags"] = kw.get("creationflags", 0) | _NW
            super().__init__(*a, **kw)

    sp.run = _nwr
    sp.Popen = _NWP
```

Call this in `__init__` before any data-fetching threads start.

## Also: Pass CREATE_NO_WINDOW in data modules

Even with the global patch, explicitly pass
`creationflags=0x08000000` in data-helper modules (e.g.
`vot_kanban_data.py`) that call `subprocess.run` directly. This
belt-and-suspenders approach ensures no flashing even if the global
patch runs late or the data module is imported before the patch.

```python
_NO_WINDOW = 0x08000000

def _run(args, timeout=15):
    result = subprocess.run(
        args, capture_output=True, text=True,
        timeout=timeout, creationflags=_NO_WINDOW,
    )
    return result.stdout
```

## Why a global patch (not per-call)

The Vesper service layer has ~30 `subprocess.run` call sites. Patching
each one individually is impractical and fragile — new call sites
re-introduce the flashing. The global patch covers all of them in one
place, including future additions.

## Why we evolved from the runner-only patch

The first attempt patched only `_default_runner` in
`operator_workspace_activity.py`. That covered the Vesper service
layer's calls but missed the `hermes kanban` CLI calls in
`vot_kanban_data.py` and any other direct `subprocess.run` calls.
The global `sp.run`/`sp.Popen` patch is the correct universal fix.

## Verification

After applying the fix, launch the app with `pythonw.exe` and watch
for one minute (covering multiple poll cycles). No console windows
should flash. The app's data should still refresh normally — the
subprocesses still run, they just don't create visible windows.

## Applies To

Any `pythonw.exe` Tkinter/PySide6 desktop app on Windows that spawns
subprocesses for data polling:

- VOT (Vesper Operator Terminal) — `app/vot_tk.py`
- VOT Kanban Panel — `app/vot_kanban.py`
- VWM (Vesper Worker Monitor) — has its own per-call fix
- Any monitoring dashboard that shells out for data
