# Live Subprocess Log in Tkinter

Embed a real-time terminal/log view inside a Tkinter dashboard by streaming a subprocess stdout into a `Text` widget via a background thread and `queue.Queue`.

## When to use

- Training scripts, backtests, or data pipelines that run for minutes
- Any long-running CLI command whose output the operator should monitor in real time
- Avoids blocking the Tk event loop

## Pattern

### 1. Queue + thread plumbing

```python
import queue, subprocess, sys, threading

self._train_queue: queue.Queue[str] = queue.Queue()
self._train_thread: threading.Thread | None = None
```

### 2. Launch subprocess in a daemon thread

```python
def _launch_training(self):
    if self._train_thread is not None and self._train_thread.is_alive():
        self._log_line("Already running.")
        return

    self._train_thread = threading.Thread(
        target=self._read_training_output, daemon=True
    )
    self._train_thread.start()
```

### 3. Reader thread: stdout → queue

```python
def _read_training_output(self):
    proc = subprocess.Popen(
        [sys.executable, "scripts/train_model.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    for line in proc.stdout:
        self._train_queue.put(line)
    proc.wait()
    self._train_queue.put(f"\nFinished (exit {proc.returncode})\n")
    self._train_queue.put("__TRAIN_DONE__")
```

### 4. Tk main thread: queue → Text widget

Call every 200ms via `after()`:

```python
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
```

### 5. Safe Text insertion

Only the Tk thread touches widgets:

```python
def _log_line(self, text: str):
    ts = datetime.now().strftime("%H:%M:%S")
    self.train_log.configure(state="normal")
    self.train_log.insert("end", f"[{ts}] {text}\n")
    self.train_log.see("end")      # auto-scroll
    self.train_log.configure(state="disabled")
```

## Widget setup

```python
log_frame = tk.LabelFrame(main, text="Training Log", bg=BG, fg=FG, ...)
self.train_log = tk.Text(log_frame, wrap="word", font=("Cascadia Mono", 9),
                         bg=BG, fg=FG, state="disabled", ...)
```

## Button state guard

Disable the launch button while running to prevent duplicate subprocesses:

```python
self.train_btn.config(state="disabled", text="Training...")
# re-enable when __TRAIN_DONE__ arrives
```

## Pitfalls

- **Do NOT read stdout directly in a Tk callback** — freezes the UI.
- **Do NOT forget `daemon=True`** on the reader thread — orphaned processes on window close.
- **`stderr=subprocess.STDOUT`** merges stderr into the same stream so errors are visible.
- **Use `text=True` and `bufsize=1`** for line-buffered text mode; binary mode requires manual decode.
- **Always `see("end")`** after insert, otherwise the operator must manually scroll.
