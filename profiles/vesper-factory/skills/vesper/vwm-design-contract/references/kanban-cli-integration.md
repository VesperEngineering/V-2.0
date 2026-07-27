# Kanban CLI Integration for VOT

The Hermes Kanban CLI (`hermes kanban`) provides the full command surface
for building an operator-accessible Kanban interface in the VOT.

## Commands Used by the VOT KANBAN Tab

### List tasks (JSON)
```bash
hermes kanban --board vesper list --json
```
Returns a JSON array of task dicts:
```json
{
  "id": "t_9bdbeb56",
  "title": "implementation",
  "body": null,
  "assignee": "vesper-clarke",
  "status": "blocked",
  "workspace_path": "...",
  "branch_name": null,
  "started_at": 1784256100,
  "completed_at": null,
  "result": null
}
```
Statuses: `running`, `blocked`, `review`, `ready`, `todo`, `done`, `archived`

### Show task detail (JSON)
```bash
hermes kanban --board vesper show <task_id> --json
```
Returns:
```json
{
  "task": { "id": "...", "title": "...", "body": "...", ... },
  "latest_summary": "Agent's last summary of the task...",
  "parents": [...],
  "children": [...],
  "comments": [
    { "author": "vesper-clarke", "body": "...", "created_at": 1784256116 }
  ],
  "events": [
    { "kind": "created", "payload": {...} },
    { "kind": "claimed", "payload": {...} }
  ]
}
```

### Complete a task (approve)
```bash
hermes kanban --board vesper complete <task_id> --result "Approved by Brennan via VOT"
```
Marks the task as done with the given result string.

### Block a task (reject)
```bash
hermes kanban --board vesper block <task_id> "Rejected: <reason>"
```
Blocks the task with a reason. The reason is also appended as a comment.

### Unblock a task
```bash
hermes kanban --board vesper unblock <task_id> --reason "Cleared via VOT"
```
Clears the blocker on a task.

### Comment on a task
```bash
hermes kanban --board vesper comment <task_id> <text> --author brennan
```
Adds a comment visible to the assigned agent on its next board poll.

## Operator Action Patterns

### Approve (complete with confirmation)
```python
def _kanban_action(self, action: str) -> None:
    if action == "approve":
        if not self._confirm("Approve Task",
                             f"Complete task {tid} as approved?"):
            return
        self._kanban_complete(tid, "Approved by Brennan via VOT")
```

### Reject (block with reason prompt)
```python
    elif action == "reject":
        reason = self._prompt("Reject Task",
                              f"Reason for rejecting {tid}:")
        if not reason:
            return
        self._kanban_comment(tid, f"REJECTED: {reason}")
        self._kanban_block(tid, f"Rejected: {reason}")
```

### Comment (entry bar dual-mode)
The entry bar at the bottom of the focus panel serves dual purpose:
- **No task selected:** typing a task ID (starts with `t_`) + Enter selects it
- **Task selected:** typing any other text + Enter sends a comment

```python
def _select_kanban_by_input(self) -> None:
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

## Key Bindings

Bind on `self.root` (not `bind_all`) to avoid interfering with text entry:
```python
self.root.bind("<a>", lambda e: self._kanban_action("approve"))
self.root.bind("<r>", lambda e: self._kanban_action("reject"))
self.root.bind("<u>", lambda e: self._kanban_action("unblock"))
```

## All subprocess calls MUST use CREATE_NO_WINDOW

```python
creationflags=0x08000000
```

Without this, each kanban command flashes a console window.

## Hermes exe path

```python
HERMES_EXE = r"C:\Users\bgonn\AppData\Local\hermes\hermes-agent\venv\Scripts\hermes.exe"
```

## What This Does NOT Do

- **No real-time chat with the agent** — comments are asynchronous. The
  agent sees them on its next board poll.
- **No `kanban log` from the VOT** — `hermes kanban log <task_id>` spawns
  an agent session (too heavy for a UI subprocess). Use `show --json`
  for task detail instead.
- **No promote from the VOT** — `hermes kanban promote` advances a task
  to the next stage, which is a governance action that should require
  explicit confirmation. Not wired in the initial build.
