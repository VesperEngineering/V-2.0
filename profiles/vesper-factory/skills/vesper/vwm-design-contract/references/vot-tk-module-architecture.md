# VOT Tkinter Module Architecture

## File layout

```
app/vot_tk.py          # Main app (VotTkApp), snapshot loading, data binding
app/vot_tk_palette.py  # VWM color constants (exact hex from VWM source)
app/vot_tk_fonts.py    # FontManager — shared font cache + text scaling
app/vot_tk_appbar.py   # 64px appbar: brand, brackets, counters, sync
app/vot_tk_rail.py     # 350px left rail: evidence spine cards + queue box
app/vot_tk_focus.py    # Right focus: blocker, metrics, tabs, terminal
```

## Launch

```bash
cd D:/vesper-wt-vot-command-deck
export PATH='D:/vesper/.venv/Scripts':"$PATH"
"D:/vesper/.venv/Scripts/pythonw.exe" -m app.vot_tk --root "D:/vesper-wt-vot-command-deck"
```

## Screenshot capture (for visual verification)

```bash
powershell.exe -NoProfile -Command "
Add-Type -AssemblyName System.Drawing
\$proc = Get-Process pythonw | Where-Object {\$_.MainWindowTitle -match 'Vesper Operator'}
\$hwnd = \$proc.MainWindowHandle
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class WinApi {
  [DllImport(\"user32.dll\")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
}
'@
\$r = New-Object WinApi+RECT
[WinApi]::GetWindowRect(\$hwnd, [ref]\$r) | Out-Null
\$w = \$r.R - \$r.L; \$h = \$r.B - \$r.T
\$bmp = New-Object System.Drawing.Bitmap(\$w, \$h)
\$g = [System.Drawing.Graphics]::FromImage(\$bmp)
\$g.CopyFromScreen(\$r.L, \$r.T, 0, 0, (New-Object System.Drawing.Size(\$w, \$h)))
\$bmp.Save('C:\Users\bgonn\Desktop\vot_tk.png', [System.Drawing.Imaging.ImageFormat]::Png)
"
```

## Snapshot loader wiring (gotchas)

`load_dashboard_snapshot()` requires 5 keyword-only arguments. Calling it with
just `root` raises `TypeError: missing 4 required keyword-only arguments`.

### Correct import paths (verified)

```python
from app.services.operator_terminal_status import load_dashboard_snapshot
from app.services.operator_codex_activity import CodexActivityTracker
from app.services.operator_workspace_activity import (
    WorkspaceEventTracker,
    WindowsDirectoryEventSource,
    GitActivityTracker,  # GitActivityTracker is here, NOT in a separate module
)
from app.services.operator_provider_telemetry import build_provider_telemetry_supervisor
```

### Pitfall: module name

`operator_workspace_activity` (not `operator_workspace_events`).
`GitActivityTracker` lives in `operator_workspace_activity`, not
`operator_git_activity`.

### Correct invocation

```python
root = project_root.resolve()
observed = datetime.now().astimezone()
codex_tracker = CodexActivityTracker(root)
workspace_tracker = WorkspaceEventTracker(root, started_at=observed)
git_tracker = GitActivityTracker(root)
event_source = WindowsDirectoryEventSource(root)
provider_supervisor = build_provider_telemetry_supervisor(root)

snap = load_dashboard_snapshot(
    root,
    codex_tracker=codex_tracker,
    workspace_tracker=workspace_tracker,
    git_tracker=git_tracker,
    event_source=event_source,
    provider_telemetry=provider_supervisor.snapshot(),
)
```

This pattern mirrors how `DashboardController.__init__` in
`app/operator_terminal.py:134-155` constructs the trackers.

## Threading model (mirrors VWM)

- `POLL_SECONDS = 5` (VWM uses 2; VOT uses 5 since operator state changes less frequently)
- Background thread calls `_fetch_snapshot()` → puts `("snapshot", snap)` on `queue.Queue`
- Main thread drains queue every 150ms via `root.after(150, self._drain_queue)`
- `root.after(POLL_SECONDS * 1000, self.refresh)` schedules next poll
- `WM_DELETE_WINDOW` cancels both after-ids before `root.destroy()`

## Visual refinements (applied after first build)

### Status dot state mapping

Pipeline stages use states like `stale`, `missing_source`, `waiting`, `not_due`,
`not_configured` — not just `running`/`fail`/`pass`. The `_state_dot()` function
in `vot_tk_rail.py` must handle all of these:

```python
if s in {"running", "active"}:       → filled WARM oval
elif s in {"fail","failed","blocked","missing","missing_source"}: → filled STATE_FAIL red
elif s in {"pass","passed","ready","complete"}: → filled STATE_PASS green
elif s in {"stale"}:                 → filled STATE_WAITING amber
elif s in {"waiting","not_due","not_configured"}: → hollow SOFT outline
else:                                → hollow SOFT
```

### Label compaction (avoid clipping in 350px rail)

Stage labels like "Paper Order or Explicit No-Order Evidence" are too long for
the rail. Compact with ellipsis at 42 chars (label) and 52 chars (detail):

```python
label_text = row.label if len(row.label) <= 42 else row.label[:39] + "…"
detail_text = row.detail if len(row.detail) <= 52 else row.detail[:49] + "…"
```

### Metrics source truncation

The metrics grid cells are 90px minwidth. Source paths like
`PROJECT_ADVANCEMENT.md` overflow. Truncate to 25 chars:

```python
src = blocker.source_path or "—"
metrics["source"].set(src[:25] + "…" if len(src) > 25 else src)
```

### Sync indicator (CONNECTING → SYNC)

Only show CONNECTING… before the first successful snapshot. Use a
`_first_loaded` flag:

```python
def refresh(self):
    if not self._first_loaded:
        self.sync_var.set("READ ONLY  ·  CONNECTING…")

def _apply_snapshot(self, snap):
    self._first_loaded = True
    self.sync_var.set(f"READ ONLY  ·  SYNC {self.last_sync}")
```

### Orange rail accent

Add a full-height 3px orange bar on the left edge of the appbar, in addition
to the `▌` character in the brand mark:

```python
rail_accent = tk.Frame(appbar, bg=ORANGE, width=3)
rail_accent.pack(side=tk.LEFT, fill=tk.Y)
```

### Card visual separation

Unselected cards need subtle borders to look like discrete cards, not a plain
list. Use `LINE` border + slightly different bg (`#0f1112` vs `#111314`):

```python
bg = SELECTED_BG if selected else "#0f1112"
highlightbackground=LINE_2 if selected else LINE
```
