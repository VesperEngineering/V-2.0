# VOT Kanban Panel Patterns

Additional patterns learned while building and iterating on the
dedicated Kanban operator panel (`app/vot_kanban.py`).

## 1. Task card status visibility — show all non-archived, non-done

If the card list filters to only `running/blocked/review/ready`, tasks
with `todo` or `triage` status are invisible. When a `blocked` task gets
unblocked (becoming `todo`), it appears to "disappear."

**Fix:** Show ALL non-archived, non-done tasks:
```python
active = [
    t for t in tasks
    if t.get("status") not in ("archived", "done")
]
```

Also update `_tasks_signature` to include all non-archived, non-done
tasks so the card list re-renders when any of them changes status.

## 2. Assignees signature — use proper string, not dict comparison

Do NOT use `str(assignees) != str(self.assignees)` for change detection.
Dict ordering can cause false positives on every cycle, making the worker
bar flicker.

**Fix:** Use a compact string signature:
```python
def _assignees_signature(self, assignees) -> str:
    return "|".join(f"{n}:{c}" for n, c in assignees)
```

## 3. All known agents must appear in the worker bar

The SQLite `GROUP BY assignee` only returns agents that have tasks.
Agents with zero tasks (idle agents like `vesper-steward`,
`vesper-thomas`) won't appear at all.

**Fix:** Maintain a known-agents list and append idle ones:
```python
known = [
    "vesper-clarke", "vesper-engineer",
    "vesper-morgan", "vesper-riley",
    "vesper-rez", "vesper-steward",
    "vesper-thomas",
]
existing = {a for a, _ in roster}
for agent in known:
    if agent not in existing:
        roster.append((agent, "idle"))
```

Also handle `None` assignee values: `a = r["assignee"] or "unassigned"`

## 4. KANBAN button in VOT appbar opens Toplevel

The VOT appbar has a KANBAN button that opens the dedicated Kanban
panel as a `Toplevel` window. Both run side by side.

```python
# In vot_tk_appbar.py — build_appbar creates the button:
kanban_btn = tk.Button(appbar, text="KANBAN", ...)
appbar.kanban_btn = kanban_btn

# In vot_tk.py — wire it:
appbar = build_appbar(...)
if hasattr(appbar, "kanban_btn"):
    appbar.kanban_btn.configure(command=self._open_kanban)

def _open_kanban(self):
    from app.vot_kanban import KanbanPanel
    win = tk.Toplevel(self.root)
    KanbanPanel(win)
```

## 5. Detail panel scroll preservation with content change detection

Only re-render the log text when the content actually changed. This
prevents scroll resets on every poll cycle when the content is identical.

```python
# In _render_detail:
if text == self._last_detail_text:
    return  # skip re-render entirely
self._last_detail_text = text

view_top = self.log_text.yview()[0]
# ... rebuild text widget ...
if self._auto_follow:
    self.log_text.see(tk.END)
else:
    self.log_text.yview_moveto(view_top)
```

## 6. Auto-follow toggle pattern

The log output area needs auto-follow that the user can toggle:

1. Default: ON — new content scrolls to bottom
2. Scrolling up: turns OFF — free scroll
3. Click FOLLOW button: turns back ON — snaps to bottom

```python
def _on_log_scroll(self, event):
    self.log_text.yview_scroll(int(-event.delta/120), "units")
    at_bottom = self.log_text.yview()[1] >= 0.995
    if not at_bottom and self._auto_follow:
        self._auto_follow = False
        self.follow_var.set("FOLLOW ○")
```

## 7. Worker bar height — 44px minimum

38px clips text vertically. Use 44px with `pady=9` inside cells.

## 8. Task card colors — match VOT exactly

Unselected: `bg="#0d0f10"` (not `#0f1112` — slightly too light)
Selected: `bg=SELECTED_BG` (`#1a1d1e`)
Borders: `LINE` unselected, `LINE_2` selected
