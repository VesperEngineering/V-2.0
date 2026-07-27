---
name: local-ml-lab-console
description: "Build a lightweight, local-only Windows desktop console for bounded ML experiments. Native Tkinter front-end, WSL JSON bridge, Canvas-based training visualizations, and honest evaluation state."
category: software-development
---

# Local ML Lab Console

A lightweight, local-only Windows desktop console for bounded ML experiments
(model training, evaluation, dataset review). The stack is intentionally
small:

- **Native Windows Tkinter** for the GUI (avoids WSL/curses TTY failures).
- **WSL JSON bridge** to pull durable state from the Linux side where the GPU,
  virtual environment, and large artifacts live.
- **Canvas-based visualizations** for training progression that grow and light
  up as the run advances.
- **Honest state rendering** — no fake progress, no market/trading claims.

## When to use this skill

- You need a simple Windows desktop launcher for a local GPU experiment.
- The heavy lifting (PyTorch, CUDA, adapters, datasets) lives in WSL.
- You want status, findings, and progress visible without SSH or terminal
  windows.
- The user explicitly asked for a "simple TUI" or desktop console.

## Core architecture

```
Windows Desktop (.lnk)
  └─ pythonw.exe scripts/windows/model_lab_console.py
       ├─ Tkinter UI (status, controls, Canvas graph, activity log)
       └─ subprocess.run([wsl.exe, -d, Distro, --, bash, -lc, exporter])
            └─ WSL side: scripts/wsl/export_state.py → stdout JSON
```

Do not use `\\wsl.localhost\...` mounts or raw `wsl.exe` curses/TUI scripts.
Both are brittle. The exporter is the stable contract.

## Pattern 1: WSL state exporter

`scripts/wsl/export_state.py` reads durable run state and emits JSON:

```python
from pathlib import Path
import json

root = Path.home() / "vesper-model-storage"
state_root = root / "runs" / "state"

current = json.loads((state_root / "current.json").read_text(encoding="utf-8")) if (state_root / "current.json").is_file() else None

events = []
if (state_root / "events.jsonl").is_file():
    for line in (state_root / "events.jsonl").read_text(encoding="utf-8").splitlines()[-20:]:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

print(json.dumps({"current": current, "events": events}, default=str))
```

Key points:
- Keep the exporter read-only; it must never mutate run state.
- Include the latest report/evaluation summaries if the UI needs them for
  rich visualizations.
- Use `default=str` for non-serializable values (datetime, Path, etc.).

## Pattern 2: Windows caller with CREATE_NO_WINDOW

```python
import subprocess
from pathlib import Path

WSL = Path(r"C:\Windows\System32\wsl.exe")
EXPORTER = (
    "source /home/brennan/vesper-model-storage/venv/bin/activate && "
    "python /home/brennan/vesper-model-lab/scripts/wsl/export_state.py"
)

result = subprocess.run(
    [str(WSL), "-d", "Ubuntu-24.04", "--", "bash", "-lc", EXPORTER],
    capture_output=True,
    text=True,
    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    timeout=15,
)
if result.returncode != 0:
    raise RuntimeError(f"WSL exporter failed: {result.stderr}")
payload = json.loads(result.stdout)
```

Use `bash -lc` and explicitly activate the WSL virtual environment. A bare
`python` invocation often fails with `command not found` because the shortcut
shell has no activated environment.

## Pattern 3: Native Tkinter app skeleton

```python
import tkinter as tk
from tkinter import ttk

class ModelLabConsole(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Model Lab v0.1.0")
        self.geometry("780x560")
        self.configure(bg="#1e1e1e")
        self._build()
        self.after(2000, self._refresh)

    def _build(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#1e1e1e")
        style.configure("TLabel", background="#1e1e1e", foreground="#d4d4d4")

        header = ttk.Frame(self)
        header.pack(fill=tk.X, padx=14, pady=12)
        ttk.Label(header, text="MODEL LAB", font=("Segoe UI", 16, "bold")).pack(side=tk.LEFT)

        self.status = tk.StringVar(value="Connecting…")
        ttk.Label(header, textvariable=self.status).pack(side=tk.RIGHT)

        self.body = tk.Text(self, bg="#111111", fg="#d4d4d4", font=("Consolas", 10), state=tk.DISABLED)
        self.body.pack(fill=tk.BOTH, expand=True, padx=14, pady=6)

        controls = ttk.Frame(self)
        controls.pack(fill=tk.X, padx=14, pady=(6, 12))
        ttk.Button(controls, text="Run training", command=self._request_training).pack(side=tk.LEFT)
        ttk.Button(controls, text="Refresh", command=self._refresh).pack(side=tk.LEFT, padx=(8, 0))

    def _refresh(self) -> None:
        # load_snapshot() wraps the WSL exporter call
        current, events, notice = load_snapshot()
        self.status.set(notice)
        self._set_text(dashboard_text(current, events))

    def _set_text(self, text: str) -> None:
        self.body.configure(state=tk.NORMAL)
        self.body.delete("1.0", tk.END)
        self.body.insert("1.0", text)
        self.body.configure(state=tk.DISABLED)

    def _request_training(self) -> None:
        # delegate to a WSL training bridge script
        pass
```

Use `pythonw.exe` in the desktop shortcut to avoid a console window flash.

## Pattern 4: Desktop shortcut

```powershell
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut('C:\Users\bgonn\Desktop\Model Lab.lnk')
$lnk.TargetPath = 'C:\Users\bgonn\AppData\Local\hermes\hermes-agent\venv\Scripts\pythonw.exe'
$lnk.Arguments = '"C:\Users\bgonn\Desktop\Vesper-Model-Lab\scripts\windows\model_lab_console.py"'
$lnk.WorkingDirectory = 'C:\Users\bgonn\Desktop\Vesper-Model-Lab'
$lnk.Save()
```

Verify the shortcut actually opens a responsive window:

```powershell
Invoke-Item 'C:\Users\bgonn\Desktop\Model Lab.lnk'
Start-Sleep -Seconds 5
Get-Process | Where-Object { $_.MainWindowTitle -like '*Model Lab*' } |
    Select-Object -First 1 |
    Select-Object ProcessName, MainWindowTitle, Responding
```

## Pattern 5: Canvas-based training progression graph

Replace the static `BASE → LoRA → EVAL` text with a node-link graph that
lights up as stages complete. See `references/training-graph-canvas.md` for
the full implementation.

High-level shape:
- Center hub: run ID.
- Satellite nodes: Dataset, Base model, LoRA, Loss curve, Holdout eval,
  Benchmark eval, Report.
- Directed edges show pipeline flow.
- Node color indicates status: pending (gray), active (blue), complete (green).
- Each node has a detail label: train count, final loss, pass rates, etc.
- A caption below interprets the current state in plain language.

This gives the user both the "growing over time" visual and a textual
interpretation.

## Workflow: present choices before implementing UI

When the user asks for a new visualization or UI element, **present design
choices first and wait for approval before writing production Tkinter code.**

The signal phrases:
- "Research a better way to display X"
- "I want it to look like this"
- "Can you make the UI more informative?"

Recommended choices to offer:
1. **Metrics inside nodes** — compact, preserves graph structure.
2. **Stage banner + metrics strip** — clear separation, uses more space.
3. **Live event log stream** — maximum info, less visual structure.
4. **Expandable dashboard card** — most informative, more complex.
5. **Graph/node-link view** — like Obsidian, grows over time.

Wait for the user's direction, then implement. Do not jump straight to code
when the user is still deciding on the visual approach.

## Pattern 6: honest evaluation state

The console must not claim improvement that isn't evidenced. Examples of
honest captions:

- "Adapter 2/50 on benchmark; base 0/50. Execution-safe for both."
- "Mechanics baseline complete; corpus too small for quality claims."
- "Training in progress; evaluation pending."

Keep evaluation scores visible and source-linked (manifest hashes, report
paths).

## Guarded WSL GPU evaluation and crash recovery

A dashboard state such as `EVALUATING` is not process authority. After a timeout
or unexpected reboot, verify the exact WSL process and matching receipt before
calling the run live. If no process exists, treat the state as stale/interrupted;
an abrupt reboot can bypass the evaluator's exception handler and leave no
`FAILED` state or crash dump.

For retries, launch exactly one evaluator and protect both resource boundaries:

- set a conservative PyTorch per-process allocator fraction below the user's
  total VRAM limit;
- monitor total `nvidia-smi` memory and host RAM from Windows;
- stop the exact evaluator on either ceiling, and terminate the WSL distro only
  as a last resort when no unrelated WSL workload is authorized;
- continue waiting on the same PID after orchestration wait timeouts—never start
  another evaluator merely because deterministic generation is slow;
- verify the evaluation receipt, manifest hash, detail counts, final state, and
  Windows console smoke-test before reporting completion.

See `references/guarded-wsl-evaluation.md` for the full preflight, watchdog,
stale-state diagnosis, shutdown, and verification procedure.

## Anti-patterns

- **WSL curses/TUI shortcuts** — `wsl.exe ./curses_app.sh` via `.lnk` fails
  with empty `TERM` and `nocbreak() returned ERR`. Use native Tkinter.
- **UNC path mounts** — `\\wsl.localhost\...` behavior is unreliable across
  Windows versions and sleep/resume. Use the WSL exporter.
- **Duplicate evaluator retries** — a wait timeout is not evaluator failure.
  Never launch another base-versus-adapter process while the first may be live.
- **Reactive-only GPU caps** — a watchdog samples after allocation. Pair it
  with a lower per-process allocator cap and leave headroom below total VRAM.
- **Fake progress** — do not animate or claim progress before state receipts
  exist.
- **Implementing UI before approval** — when the user asks for options,
  present options first.

## References

- `references/wsl-json-bridge.md` — detailed exporter and caller patterns.
- `references/training-graph-canvas.md` — Canvas node-link graph
  implementation for training progression.
- `references/tkinter-live-refresh-and-zoom.md` — preserve manual event-log
  reading position during refresh, bounded source-state Canvas zoom, native Tk
  integration tests, and visual acceptance checks.
- `references/present-ui-choices.md` — template for presenting UI options
  before implementation.
- `references/guarded-wsl-evaluation.md` — single-process GPU guard,
  crash/stale-state diagnosis, receipt verification, and safe WSL cleanup.
