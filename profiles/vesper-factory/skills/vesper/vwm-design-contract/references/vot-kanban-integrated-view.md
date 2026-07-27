# VOT Kanban Integrated View Patterns

When the Kanban panel is integrated inside the VOT as a view toggle
(not a separate window), these patterns apply.

## View toggle (evidence ↔ kanban)

The KANBAN button in the appbar toggles between two views that share
the same appbar. The body frame is packed/unpacked:

```python
def _open_kanban(self) -> None:
    if not hasattr(self, "_kanban_view"):
        self._build_kanban_view()
    if self._view_mode == "evidence":
        self._view_mode = "kanban"
        self.body.pack_forget()
        self._kanban_view.pack(
            fill=tk.BOTH, expand=True, side=tk.TOP
        )
    else:
        self._view_mode = "evidence"
        self._kanban_view.pack_forget()
        self.body.pack(
            fill=tk.BOTH, expand=True, side=tk.TOP
        )
```

## _kv_ prefix convention

All Kanban view methods and attributes use the `_kv_` prefix to
distinguish them from evidence view methods:

- `self._kv_worker_bar` — worker queue bar frame
- `self._kv_card_list` — task card frame
- `self._kv_canvas` — scrollable canvas for cards
- `self._kv_log` — detail/log text widget
- `self._kv_title`, `_kv_status`, `_kv_meta` — detail StringVars
- `self._kv_follow`, `_kv_auto_follow` — follow toggle state
- `self._kv_comment_var` — comment entry StringVar
- `self._kv_count` — task count StringVar
- `self._kv_last_detail`, `_kv_last_tasks_sig`, `_kv_last_workers_sig`
  — change detection signatures

Methods:
- `_build_kanban_view()` — build the layout (called lazily on first click)
- `_kv_refresh()` — called from `_apply_data` when in kanban view
- `_kv_render_workers(assignees)` — render the worker bar
- `_kv_render_cards(tasks)` — render task cards
- `_kv_select(task_id)` — select a task (fetches detail in background)
- `_kv_render_detail(detail, log)` — render detail + log text
- `_kv_toggle_follow()` — toggle auto-follow
- `_kv_action(action)` — approve/reject/unblock
- `_kv_send_comment()` — send comment

## Refresh wiring

`_kv_refresh()` is called from `_apply_data()` (the evidence snapshot
drain handler) after the evidence view is updated. It only runs when
`_view_mode == "kanban"` and the view has been built:

```python
# In _apply_data, after evidence view update:
self._kv_refresh()
```

`_kv_refresh` fetches assignees and task detail via direct SQLite reads
in the main thread (fast enough at ~1ms each). Task cards use the
already-fetched `self._kanban_tasks` from the background fetch thread.

## Init ordering

ALL `_kv_*` state vars must be initialized in `__init__`, NOT in
`_build_kanban_view()`. The `_kv_refresh` method runs on every polling
cycle, including before the view is built. See the "Init Kanban view
state vars" pitfall in SKILL.md.

## Standalone vs integrated

The standalone `app/vot_kanban.py` (KanbanPanel class) is kept for
independent use, but the primary operator surface is the integrated
view toggle. Both share the same data layer (`app/vot_kanban_data.py`).
