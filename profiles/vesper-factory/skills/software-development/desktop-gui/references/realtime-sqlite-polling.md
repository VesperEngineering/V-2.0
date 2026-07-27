# Real-Time Tkinter Polling — Direct SQLite + Signature Diffing

## Problem

When a Tkinter dashboard polls for data on a timer (e.g. every 500ms),
the naive approach spawns subprocesses (e.g. `hermes kanban list --json`)
on every cycle. This causes:
- Console window flashing (even with CREATE_NO_WINDOW, the process
  creation overhead is visible)
- CPU contention from process spawning
- UI flicker from re-rendering widgets every cycle
- Timestamp display flicker (updating a clock label every 500ms)

## Solution: Direct SQLite Reads

Instead of spawning CLI subprocesses, open the underlying database
directly with a read-only URI connection:

```python
import sqlite3

KANBAN_DB = Path(
    r"C:\Users\bgonn\AppData\Local\hermes"
    r"\kanban\boards\vesper\kanban.db"
)

def _db():
    """Open a read-only connection."""
    conn = sqlite3.connect(
        f"file:{KANBAN_DB}?mode=ro", uri=True
    )
    conn.row_factory = sqlite3.Row
    return conn

def fetch_tasks():
    """Instant read — no subprocess, no flashing."""
    conn = _db()
    cur = conn.execute(
        "SELECT id, title, assignee, status, ... "
        "FROM tasks ORDER BY ..."
    )
    tasks = [dict(r) for r in cur]
    conn.close()
    return tasks
```

Key points:
- `mode=ro` prevents accidental writes
- `sqlite3.Row` gives dict-like access
- Reads are <1ms — truly instant
- No subprocess overhead, no console flashing
- Write operations (complete/block/unblock/comment) still use the
  CLI for audit trail — only reads go through SQLite directly

## Solution: Signature-Based Change Detection

Even with instant reads, re-rendering all widgets every 500ms causes
flicker. Only re-render when the data actually changed:

```python
def _tasks_signature(self, tasks):
    """Compact string that changes when task data changes."""
    return "|".join(
        f"{t['id']}:{t['status']}"
        for t in tasks
        if t.get("status") not in ("archived", "done")
    )

def _assignees_signature(self, assignees):
    """Compact signature for worker roster."""
    return "|".join(f"{n}:{c}" for n, c in assignees)

def _apply_data(self, data):
    tasks, assignees = data
    tasks_sig = self._tasks_signature(tasks)
    workers_sig = self._assignees_signature(assignees)
    tasks_changed = tasks_sig != self._last_tasks_sig
    workers_changed = workers_sig != self._last_workers_sig
    self.tasks = tasks
    self.assignees = assignees
    if workers_changed:
        self._render_workers()
        self._last_workers_sig = workers_sig
    if tasks_changed:
        self._render_cards()
        self._last_tasks_sig = tasks_sig
    self._refresh_id = self.root.after(500, self.refresh)
```

**Pitfall**: Do NOT use `str(assignees) != str(self.assignees)` for
change detection — dict ordering and float precision cause false
positives, leading to re-render every cycle = flicker. Always use
a compact, deterministic signature.

**Pitfall**: Do NOT filter tasks to only `running/blocked/review/ready`
— tasks in `todo` or `triage` will disappear and confuse the user.
Show everything that isn't `archived` or `done`.

If the signature hasn't changed, no widgets are destroyed or recreated.
The UI stays completely still until something actually changes.

## Solution: Static Sync Label

When polling at 500ms intervals, do NOT show a timestamp that updates
every cycle. The seconds field will skip and flicker:

```python
# BAD — flickers every 500ms
ts = datetime.now().strftime("%H:%M:%S")
self.sync_var.set(f"SYNC {ts}")

# GOOD — static label, no flicker
self.sync_var.set("LIVE")
```

Only show a timestamp if the poll interval is ≥5 seconds (where the
timestamp changes at most once per cycle). For sub-second polling,
use a static indicator like "LIVE" or "●".

## Solution: Preserve Detail Scroll Position

When a task is selected and its detail/log is being re-rendered on
every poll cycle, the scroll position snaps to top. Fix by:
1. Only re-render when the detail text actually changed
2. Capture scroll position before re-render and restore after

```python
def _render_detail(self, detail, log):
    # Build text...
    text = "\n".join(lines) + "\n"

    # Skip if unchanged
    if text == self._last_detail_text:
        return
    self._last_detail_text = text

    # Preserve scroll
    view_top = self.log_text.yview()[0]
    self.log_text.configure(state=tk.NORMAL)
    self.log_text.delete("1.0", tk.END)
    # ... insert text with tags ...
    self.log_text.configure(state=tk.DISABLED)
    self.log_text.yview_moveto(view_top)
```

## Solution: Auto-Follow Toggle

For worker logs that stream new output, implement an auto-follow
toggle that the user can turn off by scrolling up:

```python
# Default: auto-follow ON
self._auto_follow = True

# When user scrolls up, disable follow
def _on_log_scroll(self, event):
    self.log_text.yview_scroll(
        int(-event.delta / 120), "units"
    )
    at_bottom = self.log_text.yview()[1] >= 0.995
    if not at_bottom and self._auto_follow:
        self._auto_follow = False
        self.follow_var.set("FOLLOW ○")

# FOLLOW button re-enables
def _toggle_follow(self):
    self._auto_follow = not self._auto_follow
    if self._auto_follow:
        self.follow_var.set("FOLLOW ●")
        self.log_text.see(tk.END)
    else:
        self.follow_var.set("FOLLOW ○")

# In _render_detail, after rebuilding text:
if self._auto_follow:
    self.log_text.see(tk.END)
else:
    self.log_text.yview_moveto(view_top)
```

## Solution: Agent-Specific Issue Prefixes

When displaying task titles, the user wanted agent-specific prefixes
instead of the generic `VQ-`:

```python
_AGENT_PREFIX = {
    "vesper-engineer": "VE-",
    "vesper-clarke": "VC-",
    "vesper-riley": "VR-",
    "vesper-morgan": "VM-",
    "vesper-rez": "VZ-",
    "vesper-thomas": "VT-",
    "vesper-steward": "VS-",
}

def _relabel(self, text, assignee):
    prefix = self._AGENT_PREFIX.get(assignee, "VQ-")
    if prefix == "VQ-":
        return text
    return re.sub(r"\bVQ-", prefix, text)
```

This is display-only — the actual Kanban data is untouched.

## Solution: Include Idle Agents in Worker Roster

The worker bar should show ALL known agents, not just those with
tasks. Agents with zero tasks are "idle" — the user needs to see
who's available:

```python
known = [
    "vesper-clarke", "vesper-engineer",
    "vesper-morgan", "vesper-riley",
    "vesper-rez", "vesper-steward",
    "vesper-thomas",
]
# Add agents with tasks from SQLite, then add known agents with no tasks
existing = {a for a, _ in roster}
for agent in known:
    if agent not in existing:
        roster.append((agent, "idle"))
```

## Solution: Scrollbar Styling (VOT convention)

Grey slider on charcoal trough — not white:

```python
sb = tk.Scrollbar(
    ca, bg=CHARCOAL, troughcolor="#111314",
    bd=0, highlightthickness=0,
    activebackground=LINE, relief="flat",
)
```

Bind mouse wheel recursively on all child widgets so scrolling
works anywhere in the panel, not just on the scrollbar:

```python
def _bind(w, tid=t.get("id")):
    w.bind("<Button-1>", lambda e, k=tid: select(k))
    w.bind("<MouseWheel>", lambda e: canvas.yview_scroll(
        int(-e.delta / 120), "units"
    ))
    for child in w.winfo_children():
        _bind(child)
```

## Kanban DB Schema

The Hermes Kanban SQLite database has these tables:
- `tasks` — id, title, body, assignee, status, priority, created_at,
  started_at, completed_at, workspace_path, branch_name, result,
  session_id, block_kind
- `task_comments` — author, body, created_at, task_id
- `task_events` — kind, payload, created_at, task_id
- `task_runs` — attempt history (profile, outcome, elapsed, summary)
- `task_links` — parent→child dependencies
- `task_handoffs` — atomic handoff receipts

Worker logs are stored as files at:
`~/.hermes/kanban/boards/<board>/logs/<task_id>.log`

## Architecture Pattern

```
┌─────────────────────────────────────────┐
│  Tkinter Main Thread (event loop)       │
│  ├── after(500ms) → refresh()           │
│  ├── after(150ms) → _drain()            │
│  └── UI rendering (only on change)      │
├─────────────────────────────────────────┤
│  Background Thread                      │
│  ├── SQLite reads (instant, <1ms)       │
│  ├── queue.Queue → main thread          │
│  └── CLI calls for writes (audit trail) │
└─────────────────────────────────────────┘
```

- Reads: direct SQLite (instant, no subprocess)
- Writes: `hermes kanban` CLI (audit trail, CREATE_NO_WINDOW)
- Rendering: only when signature changes
- Sync label: static ("LIVE"), not a ticking timestamp
