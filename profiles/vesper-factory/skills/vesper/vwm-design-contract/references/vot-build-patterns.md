# VOT Tkinter Build Patterns

Required patterns when building a VWM-mirroring Tkinter app for Vesper.

## 1. CREATE_NO_WINDOW global subprocess patch

pythonw.exe has no console. Every `subprocess.run`/`Popen` in the Vesper
service layer creates a new console window that flashes and closes. With
5-second polling, this produces 4-5 flashing windows per cycle.

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

Call in `__init__` before `self.refresh()`. Do NOT attempt per-call patches
(~30 subprocess sites in the service layer).

**Also:** Any ad-hoc subprocess calls (e.g. Kanban fetching — see pattern #7)
must also pass `creationflags=0x08000000` explicitly, since the global patch
only covers `subprocess.run`/`Popen` at the module level. Calls made through
other code paths that captured a reference before the patch won't be covered.

## 2. Recursive click binding on cards

Cards must bind `<Button-1>` on ALL child widgets, not just the frame.
Mirrors VWM's `_bind_row`:

```python
def _bind_recursive(widget, task_key):
    widget.bind("<Button-1>", lambda e, k=task_key: on_select(k))
    widget.configure(cursor="hand2")
    for child in widget.winfo_children():
        _bind_recursive(child, task_key)

_bind_recursive(card, row.key)
```

Without this, clicks on labels inside `body_frame` don't propagate —
cards feel "sticky and not always responsive."

## 3. Polling preserve-user-state

Background refresh must NOT trample:
- **Scroll position** — capture `yview()[0]` before re-render, restore after.
  Only `see(tk.END)` if the user was already at the bottom AND it's a
  user-initiated action (not background refresh).
- **Card selection** — if `self.selected_key` is set, find it in the new
  pipeline and keep showing it. Only fall back to the primary blocker when
  nothing is selected or the key disappeared from the pipeline.

```python
# In set_output:
def set_output(text_widget, value, font_fn, *, force_scroll=True):
    was_at_bottom = text_widget.yview()[1] >= 0.995
    view_top = text_widget.yview()[0]
    # ... render text ...
    if force_scroll and was_at_bottom:
        text_widget.see(tk.END)
    elif not force_scroll:
        text_widget.yview_moveto(view_top)

# In _apply_snapshot:
if self.selected_key:
    selected_row = next((r for r in pipeline if r.key == self.selected_key), None)
    if selected_row:
        self._show_selected_in_focus(selected_row)
    else:
        self.selected_key = None
        self._show_blocker_in_focus(snap)
else:
    self._show_blocker_in_focus(snap)
```

Call `set_output(..., force_scroll=False)` from background refresh,
`force_scroll=True` from user actions (card click, tab switch).

## 4. Icon creation (SVG → PNG → ICO via Pillow)

cairosvg needs the native cairo library which isn't installed on Windows.
Use Pillow instead:

```python
from PIL import Image, ImageDraw

size = 256
img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Warm-white field
draw.rectangle([0, 0, size, size], fill=(238, 234, 225, 255))

# Full-height orange rail
draw.rectangle([28, 0, 40, size], fill=(255, 120, 25, 255))

# Charcoal V (scale SVG polygon points from 1024 to 256)
def s(v): return int(v * 256 / 1024)
draw.polygon([
    (s(280), s(220)), (s(405), s(220)),
    (s(525), s(650)),
    (s(645), s(220)), (s(770), s(220)),
    (s(525), s(900)),
], fill=(20, 23, 24, 255))

# Multi-size ICO
img.save(path, format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])
```

## 5. Desktop shortcut update

Update `.lnk` to point at the new Tkinter app:

```python
import win32com.client  # or use PowerShell WScript.Shell COM
ws = win32com.client.Dispatch("WScript.Shell")
lnk = ws.CreateShortcut(r"C:\Users\bgonn\Desktop\VOT.lnk")
lnk.TargetPath = r"D:\vesper\.venv\Scripts\pythonw.exe"
lnk.Arguments = "-m app.vot_tk"
lnk.WorkingDirectory = r"D:\vesper-wt-vot-command-deck"
lnk.IconLocation = r"D:\vesper\assets\vesper-operator-terminal.ico,0"
lnk.Save()
```

Or via PowerShell:
```powershell
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut('C:\Users\bgonn\Desktop\VOT.lnk')
$lnk.TargetPath = 'D:\vesper\.venv\Scripts\pythonw.exe'
$lnk.Arguments = '-m app.vot_tk'
$lnk.WorkingDirectory = 'D:\vesper-wt-vot-command-deck'
$lnk.IconLocation = 'D:\vesper\assets\vesper-operator-terminal.ico,0'
$lnk.Save()
```

## 6. Worktree venv symlink + .env copy

A Vesper worktree (`D:/vesper-wt-vot-command-deck`) doesn't inherit
`.venv` or `.env` from the main repo. Both are needed:

**`.venv` symlink** (the launcher expects `ROOT/.venv/Scripts/python.exe`):
```bash
cd D:/vesper-wt-vot-command-deck
cmd.exe /c "mklink /D .venv D:\vesper\.venv"
```

**`.env` copy** (service layer reads `ROOT/.env` for API keys):
```bash
cp D:/vesper/.env D:/vesper-wt-vot-command-deck/.env
```

`.env` is gitignored so the copy won't be committed. `.venv` is a symlink
and won't be committed either (but git will show it as untracked — add it
to `.git/info/exclude` if it bothers you).

Without `.env`, provider usage will show "unavailable" because
`openrouter_usage.py` can't read `VESPER_OPENROUTER_USAGE_ENABLED` or
`OPENROUTER_MANAGEMENT_API_KEY`.

## 7. Kanban data fetching from Tkinter

The VOT fetches Kanban tasks separately from the snapshot, using the
`hermes kanban --board vesper list --json` CLI command. This runs as a
subprocess in the background fetch thread:

```python
def _fetch_kanban_tasks(self) -> list:
    """Fetch Kanban tasks via hermes kanban --json."""
    import json
    import subprocess

    try:
        hermes = str(
            Path(
                r"C:\Users\bgonn\AppData\Local\hermes"
                r"\hermes-agent\venv\Scripts\hermes.exe"
            )
        )
        result = subprocess.run(
            [hermes, "kanban", "--board", "vesper",
             "list", "--json"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(self.project_root),
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        if result.returncode != 0:
            return []
        return json.loads(result.stdout)
    except Exception:
        return []
```

The result is a list of task dicts with fields: `id`, `title`, `body`,
`assignee`, `status` (running/blocked/review/ready/todo/done/archived),
`workspace_path`, `branch_name`, `started_at`, `completed_at`, `result`.

**Appbar counters** (ACTIVE/QUEUED/BLOCKED) should reflect Kanban task
counts, not pipeline stage counts. Pipeline stages are evidence gates,
not work items.

**Detail tab** should include a WORKFORCE / KANBAN section listing
active/blocked/review/ready tasks with status, assignee, task ID, and
title. Also include a NEXT SAFE section with `snap.next_safe_task`.

## 8. Provider usage: use string fields, not numeric

The `ProviderAccountingSnapshot` has both string and numeric usage fields:

| Field | Type | When populated |
|-------|------|----------------|
| `openai_usage` | str | Always — readable summary |
| `openrouter_usage` | str | Always — readable summary |
| `openai_remaining_percent` | float \| None | Only when Codex OAuth exposes quota |
| `openrouter_remaining_budget_usd` | float \| None | Only when management key is configured |

**Use the string fields for the appbar** — they always have a readable
value. The numeric fields are often `None` (when management account access
isn't enabled or Codex OAuth doesn't expose quota), which produces `OAI — · OR —`.

```python
# Correct: use string fields
oai = pa.openai_usage or "OAI unavailable"
orr = pa.openrouter_usage or "OR unavailable"
oai_short = oai.replace("OpenAI Codex ", "OAI ").split("  ")[0][:40]
orr_short = orr.replace("OpenRouter ", "OR ").split("  ")[0][:40]
self.usage_var.set(f"{oai_short}  ·  {orr_short}")

# Wrong: numeric fields are often None
oai = f"{pa.openai_remaining_percent:.0f}%"  # crashes when None
```

## 9. Direct SQLite reads for real-time polling

When the user demands "real-time, no delay at all," subprocess-based
polling (`hermes kanban list --json`) is too slow — each call takes
0.5-1s. The fix: read the Kanban SQLite database directly.

**Database path:**
```
C:\Users\bgonn\AppData\Local\hermes\kanban\boards\vesper\kanban.db
```

**Read-only connection (safe — can't accidentally write):**
```python
import sqlite3
conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
```

**Tables:** `tasks`, `task_comments`, `task_events`, `task_links`,
`task_runs`, `task_attachments`, `task_handoffs`

**Tasks query (ordered by status priority):**
```sql
SELECT id, title, body, assignee, status, priority,
       created_at, started_at, completed_at,
       workspace_path, branch_name, result, session_id,
       block_kind
FROM tasks
ORDER BY CASE status
  WHEN 'running' THEN 0
  WHEN 'blocked' THEN 1
  WHEN 'review' THEN 2
  WHEN 'ready' THEN 3
  WHEN 'todo' THEN 4
  WHEN 'done' THEN 5
  WHEN 'archived' THEN 6
  ELSE 7 END, assignee, id
```

**Assignee counts (for worker bar):**
```sql
SELECT assignee, status, COUNT(*) as cnt
FROM tasks WHERE status != 'archived'
GROUP BY assignee, status
```

**Task detail (with comments + events):**
```sql
-- Task
SELECT * FROM tasks WHERE id = ?
-- Comments
SELECT author, body, created_at
FROM task_comments WHERE task_id = ?
ORDER BY created_at
-- Events (last 10)
SELECT kind, payload, created_at
FROM task_events WHERE task_id = ?
ORDER BY created_at DESC LIMIT 10
```

**Worker logs:** Read directly from the log file, NOT
`hermes kanban log` (which spawns an agent session):
```python
log_path = (
    Path(r"C:\Users\bgonn\AppData\Local\hermes"
         r"\kanban\boards\vesper\logs")
    / f"{task_id}.log"
)
if log_path.exists():
    return log_path.read_text(encoding="utf-8", errors="replace")[:5000]
```

**Writes still use CLI** (for audit trail):
`kanban_complete`, `kanban_block`, `kanban_unblock`, `kanban_comment`
— all via `subprocess.run` with `creationflags=0x08000000`.

**Polling interval with direct SQLite:** 500ms (`root.after(500, ...)`)\nfeels real-time. Direct SQLite reads take ~1ms, so there's no\nsubprocess pileup or CPU concern.\n\n## 10. Signature-based change detection (prevent flicker)\n\nEven with instant SQLite reads, re-rendering all widgets every 500ms\ncauses flicker. Only re-render when data actually changed:\n\n```python\ndef _tasks_signature(self, tasks):\n    return \"|\".join(\n        f\"{t['id']}:{t['status']}\"\n        for t in tasks\n        if t.get(\"status\") in (\"running\", \"blocked\", \"review\", \"ready\")\n    )\n\ndef _apply_data(self, data):\n    tasks, assignees = data\n    tasks_changed = (\n        self._tasks_signature(tasks) != self._last_tasks_sig\n    )\n    workers_changed = str(assignees) != str(self.assignees)\n    self.tasks = tasks\n    self.assignees = assignees\n    if workers_changed:\n        self._render_workers()\n    if tasks_changed:\n        self._render_cards()\n        self._last_tasks_sig = self._tasks_signature(tasks)\n    self._refresh_id = self.root.after(500, self.refresh)\n```\n\nSame pattern for detail/log text — skip re-rendering if identical.\n\n## 11. Static sync label (not a ticking timestamp)\n\nWhen polling at 500ms, do NOT show a timestamp that updates every\ncycle. The seconds field skips and flickers:\n\n```python\n# BAD — flickers every 500ms\nself.sync_var.set(f\"SYNC {datetime.now():%H:%M:%S}\")\n\n# GOOD — static label\nself.sync_var.set(\"LIVE\")\n```\n\nAlso: do NOT set intermediate states like \"SYNCING…\" on every cycle —\nthese cause the label to blink. Just silently fetch and update only\nwhen data changes.\n\n## 12. Agent-specific issue prefixes\n\nUser wanted `VQ-` replaced with agent-specific prefixes:\n\n| Agent | Prefix |\n|-------|--------|\n| vesper-engineer | `VE-` |\n| vesper-clarke | `VC-` |\n| vesper-riley | `VR-` |\n| vesper-morgan | `VM-` |\n| vesper-rez | `VZ-` |\n| vesper-thomas | `VT-` |\n| vesper-steward | `VS-` |\n\nDisplay-only relabeling via `re.sub(r\"\\bVQ-\", prefix, text)`.\n\n## 14. Kanban section inside the VOT rail

The Kanban task list appears inside the VOT's left rail, below the
pipeline evidence spine, separated by a thin warm-white line. This
lets the operator see tasks alongside pipeline stages without opening
the separate Kanban panel.

**Separator:** `tk.Frame(rail, bg=WARM, height=1)` — 1px warm-white
line with `padx=24, pady=(8,0)`.

**Card filtering:** Show ALL non-archived, non-done tasks (including
`todo` and `triage` statuses). If you filter to only
`running/blocked/review/ready`, tasks appear to "disappear" when
they transition to `todo` after being unblocked.

**Click behavior:** Clicking a Kanban task card in the rail switches
the focus panel to the KANBAN tab and shows the task detail. This is
handled by `_select_kanban_task` which sets `_selected_kanban_id`
and calls `_show_tab("kanban")`.

**Scrollbar:** Grey-on-charcoal (`bg=CHARCOAL`, `troughcolor="#111314"`)
with recursive mousewheel binding on all card children.

See also: `references/vot-kanban-panel-patterns.md` for the dedicated
Kanban panel window patterns.

## 15. Dedicated Kanban panel architecture\n\nWhen the operator needs full Kanban management (not just read-only),\nbuild a **separate Tkinter window** (`app/vot_kanban.py`) with:\n\n- **Appbar**: orange rail + VESPER / KANBAN CONTROL + LIVE label\n- **Worker bar**: agent status dots (●◆○) from `fetch_assignees()`\n- **Left panel**: clickable task cards with scrollbar\n- **Right panel**: task detail (title, status, body, summary,\n  comments, events, worker log) — scroll-preserved\n- **Action bar**: APPROVE/REJECT/UNBLOCK buttons + comment entry\n\nKey design decisions the user made:\n- **Buttons over keyboard shortcuts** for primary actions\n- **No native popups** — everything inline (no `messagebox`/`simpledialog`)\n- **Escape** to deselect and return to empty state\n- **Scrollbar** on the card list (not just MouseWheel)\n- **Real-time** via direct SQLite + signature diffing\n- Separate window runs alongside the main VOT\n\nData layer split: `vot_kanban_data.py` (SQLite reads + CLI writes)\nseparate from `vot_kanban.py` (UI). This keeps the data layer testable\nand reusable.
