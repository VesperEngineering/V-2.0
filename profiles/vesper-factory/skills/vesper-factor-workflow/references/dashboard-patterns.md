# Dashboard Tkinter Patterns

## `_lscores(path=None)` pattern

The `_lscores()` method accepts an optional `path` argument so `rerank()` can load scores from a specific file:

```python
def _lscores(self, path=None):
    for r in self.st.get_children(): self.st.delete(r)
    p = path or _last_scores()
    ...
```

Without this, calling `self._lscores(sp)` in `rerank()` raises `TypeError: takes 1 positional argument but 2 were given`.

## Python 3.10 datetime compatibility

Use `timezone.utc` instead of `UTC` for cross-version compatibility:

```python
# OK for Python 3.11+
from datetime import UTC

# Compatible with Python 3.10+
from datetime import timezone
# then use timezone.utc everywhere
```

The explicit `timezone.utc` form works on all Python versions >= 3.6.

## Live activity feed in Today's Data panel

Added 2026-07-06: The `_lactiv()` method posts live entries to the Today's Data feed when buttons trigger subprocesses:

```python
def _lactiv(self, source: str, msg: str, ok: bool = True):
    ts = datetime.now().strftime("%H:%M:%S")
    icon = "\u2713" if ok else "\u2717"
    self.ft.insert("", 0, tags=("odd",), values=(ts, f"{icon} {source}", msg))
    while len(self.ft.get_children()) > 50:
        self.ft.delete(self.ft.get_children()[-1])
```

Called from `_run()` — "starting…" at the start, "completed" or "exit N" on finish.
Most recent entry is always at the top (insert at position 0).
Max 50 entries to prevent unbounded growth.

## Subprocess Python environment mismatch

Dashboard buttons that run subprocesses (1. Scores, 4. Alpaca, Run All) call `subprocess.run(["python", "scripts/..."], ...)`. The `python` command in the terminal's PATH may resolve to a **different Python version/venv** than the Hermes agent environment. This causes `ModuleNotFoundError` for packages like `dotenv` that are installed in the Hermes venv but not in the stray 3.10 venv.

On this Windows machine, the stray venv is `C:\Users\bgonn\veyr-music\heartlib\.venv\` (Python 3.10). The Hermes agent venv is `C:\Users\bgonn\AppData\Local\hermes\hermes-agent\venv\` (Python 3.11).

To verify which Python the scripts use:
```bash
python -c "import sys; print(sys.executable)"
```

If it shows the wrong path, the fix is to either:
- Install the missing package in the stray venv: `pip install python-dotenv`
- Or use the Hermes Python explicitly: `/path/to/hermes/python scripts/script.py`

## Pre-commit hook side effects

The `.pre-commit-config.yaml` includes `ruff-format` which reformats all code on `git commit`. This converts compact one-liner style (semicolons, inline blocks) into expanded multi-line style. The reformatting is safe (no logic changes) but can change line counts and make the diff look larger than expected. To bypass pre-commit:

```bash
git commit --no-verify -m "message"
```

## Timeout guard for flaky factors

The `Registry.run()` wraps factor execution in `concurrent.futures.ThreadPoolExecutor` with a 30-second timeout. The worker thread is NOT killed when the timeout fires — it continues running its I/O in the background. This is acceptable because:
- Python's GIL prevents true parallelism
- The leaked thread is a single short-lived HTTP request
- The executor reclaims it when garbage-collected

Pattern:

```python
import concurrent.futures
with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
    fut = ex.submit(factor.compute, **kwargs)
    return fut.result(timeout=30)
```

## Cron shell script path

Hermes cron jobs resolve `script` relative to `~/AppData/Local/hermes/scripts/`. The shell script must EXIST at that path BEFORE the cron job is created:
- Creating the script after the cron job does NOT fix a `last_status: error`
- Remove and recreate the cron job after the script file exists
- Use forward slashes in the path (backslashes get mangled: `C:Usersbgonn...`)