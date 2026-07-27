---
name: windows-tkinter-no-console-flash
description: "Suppress console window flashing when a pythonw.exe Tkinter app spawns subprocesses on Windows."
version: 1.0.0
author: Hermes Agent
metadata:
  hermes:
    tags: [windows, tkinter, subprocess, console, flash, pythonw]
---

# Suppress Console Window Flashing on Windows (pythonw + subprocess)

## Problem

When a Tkinter desktop app runs via `pythonw.exe` (no console), every
`subprocess.run()` / `subprocess.Popen()` call in the process creates a
**new console window** that flashes on screen for a fraction of a second
then closes. For an app that polls every few seconds (like VOT's 5s
snapshot refresh), this produces 4-5 flashing terminal windows per cycle.

## Root Cause

`pythonw.exe` is a GUI-subsystem binary with no attached console. When
a child process is spawned without `CREATE_NO_WINDOW`, Windows allocates
a new console for the child. The child runs, exits, and the console
window disappears — producing the flash.

## Fix: Global subprocess monkeypatch

Patch `subprocess.run` and `subprocess.Popen` at the module level early
in app startup, before any service-layer code runs:

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

Call this in `__init__` before any service-layer imports or polling starts.

## Why a global patch (not per-call)

The Vesper service layer has ~30 `subprocess.run` call sites across
`app/services/`. Patching each one individually is impractical and
fragile — new call sites would re-introduce the flashing. The global
monkeypatch covers all of them in one place, including future additions.

The VWM (`vesper_worker_monitor.py`) uses `CREATE_NO_WINDOW` on its own
`run_command` helper, but that only covers its own calls — not the
Vesper service layer it invokes. The global patch is the VOT-specific
solution for when the app calls into a service layer it doesn't control.

## Important

- The flag value is `0x08000000` (`CREATE_NO_WINDOW`), not
  `subprocess.CREATE_NO_WINDOW` (which may not exist on non-Windows or
  older Python). Using the literal hex value is safer.
- This must run BEFORE any service-layer code imports or runs, otherwise
  modules that captured a reference to the original `subprocess.run`
  (e.g. `from subprocess import run`) won't be patched. In practice,
  most code uses `subprocess.run(...)` (attribute access), which is
  patched correctly.
- If a service module does `from subprocess import run`, that local
  `run` won't be patched. Patch the module's attribute too if needed:
  `import app.services.operator_workspace_activity as _wsa; _wsa._default_runner = _no_window_run`
