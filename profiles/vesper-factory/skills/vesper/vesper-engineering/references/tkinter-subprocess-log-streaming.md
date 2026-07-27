# Tkinter Subprocess Log Streaming

Pattern for streaming stdout from a long-running subprocess into a Tkinter `Text` widget without blocking the event loop.

## Use Case

A dashboard button launches `scripts/train_model.py`. The user sees live log output ("Loading bars...", "Training set: X=(...)", "Out-of-sample IC: 0.0421") as it happens.

## Full Implementation

```python
import queue
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime


class DashboardApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self._train_queue: queue.Queue[str] = queue.Queue()
        self._train_thread: threading.Thread | None = None
        # ... build UI including self.train_log (tk.Text) and self.train_btn ...
        self._drain_training_queue()

    def _launch_training(self):
        if self._train_thread is not None and self._train_thread.is_alive():
            self._log_line("Training already running. Please wait.")
            return

        self._log_line("Launching training...")
        self.train_btn.config(state="disabled", text="Training...")

        self._train_thread = threading.Thread(
            target=self._read_training_output, daemon=True
        )
        self._train_thread.start()

    def _read_training_output(self):
        try:
            proc = subprocess.Popen(
                [sys.executable, "scripts/train_model.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            if proc.stdout is None:
                self._train_queue.put("ERROR: Could not open stdout\n")
                return

            for line in proc.stdout:
                self._train_queue.put(line)

            proc.wait()
            self._train_queue.put(f"\nFinished (exit code {proc.returncode})\n")
        except Exception as e:
            self._train_queue.put(f"\nError: {e}\n")
        finally:
            self._train_queue.put("__TRAIN_DONE__")

    def _drain_training_queue(self):
        done = False
        while True:
            try:
                line = self._train_queue.get_nowait()
                if line == "__TRAIN_DONE__":
                    done = True
                    self.train_btn.config(state="normal", text="Train Model")
                else:
                    self._log_line(line.rstrip())
            except queue.Empty:
                break

        self.root.after(200, self._drain_training_queue)

    def _log_line(self, text: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.train_log.configure(state="normal")
        self.train_log.insert("end", f"[{ts}] {text}\n")
        self.train_log.see("end")
        self.train_log.configure(state="disabled")
```

## Key Points

- `subprocess.Popen` with `stdout=subprocess.PIPE` and `text=True` for line-by-line reading.
- `threading.Thread(daemon=True)` so the reader doesn't block Tk or prevent shutdown.
- `queue.Queue` is the only thread-safe bridge; never mutate Tk widgets from the worker thread.
- `root.after(200, drain)` polls the queue from the Tk thread every 200ms.
- `tk.Text` stays in `disabled` state except during the brief insert window to prevent user editing.
- Sentinel string (`__TRAIN_DONE__`) signals completion so the button can be re-enabled.
- The log widget should be inside a `LabelFrame` with a `Scrollbar` for overflow.

## Why Not Other Approaches

- `subprocess.run()` blocks until completion — UI freezes.
- `subprocess.Popen` with `stdout.read()` blocks on full buffer.
- Direct widget mutation from the worker thread — race conditions, Tcl errors.
- `StringIO` redirection — doesn't solve the blocking problem.
