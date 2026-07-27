# Subprocess Queue Pattern for Tkinter Dashboards

Launch long-running Python scripts (training, backtesting) from a Tkinter dashboard without blocking the UI thread, and stream stdout live into a `Text` widget.

## Pattern

```python
import queue
import subprocess
import sys
import threading
import tkinter as tk

class DashboardApp:
    def __init__(self, root):
        self.root = root
        self._queue = queue.Queue()
        self._thread = None
        self._drain()

    def launch(self):
        if self._thread and self._thread.is_alive():
            return  # already running
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()

    def _read(self):
        proc = subprocess.Popen(
            [sys.executable, "scripts/long_task.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in proc.stdout:
            self._queue.put(line)
        proc.wait()
        self._queue.put(f"\nFinished (exit {proc.returncode})\n")
        self._queue.put("__DONE__")

    def _drain(self):
        while True:
            try:
                line = self._queue.get_nowait()
                if line == "__DONE__":
                    self._thread = None
                else:
                    self._insert(line)
            except queue.Empty:
                break
        self.root.after(200, self._drain)

    def _insert(self, text):
        self.text_widget.configure(state="normal")
        self.text_widget.insert("end", text)
        self.text_widget.see("end")
        self.text_widget.configure(state="disabled")
```

## Key rules

- **Tk thread safety:** Only the Tk main thread mutates widgets. Background threads push into `queue.Queue`; Tk drains via `root.after()`.
- **Done sentinel:** Use a sentinel string (`__DONE__`) so the Tk thread knows when to re-enable buttons.
- **Button state:** Disable the launch button while running; re-enable on `__DONE__`.
- **Multiple jobs:** Use separate queues/threads per job type (training vs backtest) but share one log widget.
- **No polling loops in the agent:** When launching a 20+ second job from a dashboard, the agent should NOT poll `terminal()` repeatedly. Use `background=true, notify_on_complete=true` for agent-side long jobs, or let the dashboard subprocess run independently.

## Tool-call discipline

When the agent itself needs to run a long command (e.g., `python scripts/train_model.py`), use:

```python
terminal(
    command="python scripts/train_model.py",
    background=True,
    notify_on_complete=True,
)
```

This counts as **1 tool call**, runs asynchronously, and pings completion. Do NOT poll `terminal()` every few seconds — that burns tool-call budget for no benefit.

For progress monitoring without polling, redirect the script to a log file (`--log-file`) and `tail` it if needed, or wait for the completion notification.
