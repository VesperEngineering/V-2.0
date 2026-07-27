# Tkinter Kanban Integration — Operator Action Panel

Pattern for integrating Hermes Kanban task management into a Tkinter
desktop dashboard (VOT). Lets the operator see workforce status, select
tasks, view detail + comments + events, approve/reject/unblock, and
send comments — all inline, no external windows.

## Data Sources (all via `hermes kanban` CLI)

```python
HERMES = r"C:\Users\bgonn\AppData\Local\hermes\hermes-agent\venv\Scripts\hermes.exe"

# Task list (JSON)
subprocess.run([HERMES, "kanban", "--board", "vesper", "list", "--json"])

# Task detail with comments + events (JSON)
subprocess.run([HERMES, "kanban", "--board", "vesper", "show", task_id, "--json"])

# Worker roster (table text — parse manually)
subprocess.run([HERMES, "kanban", "--board", "vesper", "assignees"])

# Add a comment
subprocess.run([HERMES, "kanban", "--board", "vesper", "comment", task_id, text, "--author", "brennan"])

# Complete (approve)
subprocess.run([HERMES, "kanban", "--board", "vesper", "complete", task_id, "--result", "Approved"])

# Block (reject)
subprocess.run([HERMES, "kanban", "--board", "vesper", "block", task_id, reason])

# Unblock
subprocess.run([HERMES, "kanban", "--board", "vesper", "unblock", task_id, "--reason", "Cleared"])
```

**Critical**: all subprocess calls MUST pass `creationflags=0x08000000`
(CREATE_NO_WINDOW) to avoid console window flashing on pythonw.exe apps.

## Architecture

### Tab Structure

Add a dedicated KANBAN tab (not text dumped into DETAIL tab). The tab
has:
- Workforce roster (top)
- Task list (clickable or via entry bar)
- Selected task detail (appears when a task is selected)
- Action prompts (inline, not popups)
- Entry bar (bottom — dual-purpose: task ID selection + comments)

### Workforce Roster

```
WORKFORCE
  ● vesper-thomas     running=1
  ◆ vesper-clarke     blocked=4
  ○ vesper-riley      (idle)
```

Fetch from `hermes kanban assignees` — parse the table output:
```python
for line in result.stdout.strip().splitlines():
    if line.startswith("NAME") or not line.strip():
        continue
    parts = line.split(None, 2)
    if len(parts) >= 3:
        name = parts[0]
        counts = parts[2]  # e.g. "blocked=4" or "(idle)"
        roster.append((name, counts))
```

Status icons:
- `●` = running (agent actively working)
- `◆` = blocked (has blocked tasks)
- `○` = idle (no active work)

### Task Detail View

When a task is selected, fetch `show --json` and render:
```
SELECTED TASK
  ID:       t_9bdbeb56
  Status:   blocked
  Assignee: vesper-clarke
  Title:    implementation
  Body:     (task body text)
  Summary:  (latest_summary from show --json)
  Branch:   (branch_name)

COMMENTS
  vesper-clarke: Missing task contract...
  brennan: I'll review this...

RECENT EVENTS
  [created]
  [claimed]
  [blocked]

ACTIONS:
  [A] Approve (complete)
  [R] Reject (type reason in bar first)
  [U] Unblock
  [ESC] Back to list
  Type in entry bar + Enter to comment
```

### Inline Confirmation (NOT Native Popups)

When the user presses A/R/U, show a confirmation prompt INLINE in the
terminal output — not a `messagebox.askyesno` or `simpledialog`:

```
ACTIONS:
  ⚠ APPROVE this task? [Y] Yes  [N] No  [ESC] Cancel
```

Key bindings:
- `A` → start approve action (shows confirmation)
- `R` → start reject action (shows confirmation)
- `U` → start unblock action (shows confirmation)
- `Y` → confirm the pending action
- `N` → cancel the pending action
- `Escape` → deselect task and return to list

### Entry Bar (Dual-Purpose)

The entry bar at the bottom serves two roles:
- **TASK ID:** (label shown when no task selected) — type a task ID
  starting with `t_` and press Enter to select it
- **COMMENT:** (label changes when a task is selected) — type any text
  and press Enter to send it as a comment

```python
def _select_kanban_by_input(self):
    text = self._kanban_entry_var.get().strip()
    if not text:
        return
    self._kanban_entry_var.set("")
    if self._selected_kanban_id and not text.startswith("t_"):
        # Treat as comment
        self._kanban_comment(self._selected_kanban_id, text)
        self._render_kanban_tab()
    else:
        # Treat as task ID
        self._selected_kanban_id = text
        self._kanban_label.config(text="COMMENT:")
        self._render_kanban_tab()
```

### Reject with Reason

For rejection, the user types the reason in the entry bar FIRST, then
presses R, then Y to confirm. The reason is extracted from the entry bar:

```python
elif action == "reject":
    reason = self._kanban_entry_var.get().strip()
    if reason:
        self._kanban_entry_var.set("")
        self._kanban_comment(tid, f"REJECTED: {reason}")
        self._kanban_block(tid, f"Rejected: {reason}")
    else:
        # Reject without reason
        self._kanban_comment(tid, "REJECTED by Brennan")
        self._kanban_block(tid, "Rejected by operator")
```

## State Management

```python
self._kanban_tasks: list = []          # task list from list --json
self._selected_kanban_id: str | None   # currently selected task
self._kanban_pending_action: str | None  # "approve" | "reject" | "unblock"
self._kanban_entry_var = tk.StringVar()  # entry bar text
```

## Refresh After Actions

After any action (complete/block/unblock/comment), call `self.refresh()`
to re-fetch the task list and update the display. The workforce roster
and task list update every poll cycle (5 seconds).

## Navigation Flow

1. KANBAN tab → shows workforce roster + task list
2. Type task ID in entry bar → Enter → task detail appears
3. Press A/R/U → inline confirmation prompt
4. Press Y to confirm, N to cancel, Escape to back out
5. Type text in entry bar + Enter → sends as comment
6. Escape anytime → deselects task, returns to list

## Limitations

- No live worker log streaming (the `hermes kanban log` command spawns
  an agent session — too heavy for inline use). Use `show --json` for
  task detail, comments, and events instead.
- No real-time agent chat — comments are one-way (operator → task card).
  The agent sees the comment next time it polls the board.
- Task selection is via entry bar (type ID), not clickable cards.
  Clickable cards require a separate card list widget in the rail.
