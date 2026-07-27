# Session Record — VOT Kanban Dead-Code Removal (2026-07-18)

The session that produced the `remove-dead-code` skill. Kept as a
reference for the exact cut pattern, the `patch` corruption, and the
recovery via `sed`.

## Task

> Remove dead Kanban code from `app/vot_tk.py` and `app/vot_tk_focus.py`.
> These methods were superseded by the integrated Kanban view (`_kv_*`
> methods) and `vot_kanban_data.py`.

## Files

- `D:/vesper-wt-vot-command-deck/app/vot_tk.py` — 1600 → 1220 lines
- `D:/vesper-wt-vot-command-deck/app/vot_tk_focus.py` — 241 → 240 lines

## Inventory (the Phase-1 list)

### Removed from `vot_tk.py`
- **6 keyboard bindings:** `<a>`, `<r>`, `<u>`, `<Escape>`, `<y>`, `<n>`
- **2 state variables:** `_kanban_entry_var`, `_kanban_pending_action`
- **1 UI element:** the focus-panel TASK ID/COMMENT entry bar (in `_build`)
- **1 tab case:** `if tab == "kanban":` branch in `_show_tab`
- **12 dead methods:**
  - `_fetch_kanban_tasks` (call site retargeted to
    `from app.vot_kanban_data import fetch_tasks`)
  - `_fetch_kanban_assignees`
  - `_fetch_kanban_show`
  - `_kanban_comment`
  - `_render_kanban_tab`
  - `_select_kanban_by_input`
  - `_kanban_deselect`
  - `_kanban_action`
  - `_kanban_confirm`
  - `_kanban_complete`
  - `_kanban_block`
  - `_kanban_unblock`
  - `_hermes_path` (only used by the removed methods)

### Removed from `vot_tk_focus.py`
- The `("kanban", "KANBAN")` entry in the tabs dict

### Kept (per task spec)
- All `_kv_*` methods (the integrated Kanban view)
- `_open_kanban` + the KANBAN button wiring in appbar
- `build_kanban_section` / `render_kanban_cards` calls in the rail
- `_select_kanban_task` (rail click handler) — **retargeted** to open the
  integrated view via `_open_kanban` + `_kv_select` instead of the removed
  `_show_tab("kanban")`

## Replacement verification

`app/vot_kanban_data.py` confirmed to provide:
`fetch_tasks`, `fetch_assignees`, `fetch_task_detail`, `fetch_worker_log`,
`kanban_complete`, `kanban_block`, `kanban_unblock`, `kanban_comment` —
covering the full surface of the removed methods.

## The `patch` corruption (the key pitfall)

After removing the dead methods one at a time, a final `patch` call was
attempted to delete the contiguous block of remaining dead methods
(`_fetch_kanban_assignees` through `_hermes_path`) in one shot. The
`patch` tool's fuzzy matcher matched only the
`def _fetch_kanban_assignees` **signature line** and replaced it with
`def close`, leaving the entire orphaned method body in place. The file
ended up with:

```
def close(self):           # <-- corrupted: was _fetch_kanban_assignees
    """Fetch the worker roster via hermes kanban assignees."""
    import subprocess
    hermes = self._hermes_path()
    ...                   # body of _fetch_kanban_assignees
def _fetch_kanban_show(self, task_id): ...
... all the other dead methods ...
def close(self):           # <-- the real close, further down
    """Close the window and cancel pending refresh/drain timers."""
    ...
```

`grep -n "^    def "` immediately revealed the duplication — two
`def close` definitions and a method whose docstring didn't match its name.

## Recovery via `sed`

Once the exact line range of the corrupted/dead block was confirmed
(lines 1192–1530, where 1531 was the real `def close` to keep):

```bash
sed -i '1192,1530d' app/vot_tk.py
grep -n "^    def close\|^    def _show_tab\|^def main" app/vot_tk.py
# → _show_tab at 1167, close at 1192, main at 1208. Clean.
```

## Concurrent-edit import drop

Mid-session, a sibling subagent's edit dropped `format_provider_usage`
from the `from app.vot_tk_appbar import …` line. `ruff check` flagged
F821 "undefined name `format_provider_usage`" at line 935 — a call site
in the *kept* `_apply_snapshot` method. The fix was to restore the
import (the call site was legitimate; the import was what got lost),
NOT to remove the call site. This is the concurrent-edit pitfall
documented in the parent skill.

## Verification output

```
$ ruff check app/vot_tk.py app/vot_tk_focus.py
All checks passed!

$ python -c "from app.vot_tk import VotTkApp; print('OK')"
OK
```

## Lesson distilled

1. **Inventory before cutting** — naming every keep/remove item out
   loud caught the `_select_kanban_task` retargeting need before it
   became a runtime crash.
2. **`patch` is for small unique edits; `sed -i 'START,ENDd'` is for bulk
   method deletion** — the fuzzy matcher will corrupt a big replace.
3. **No shims** — the first instinct was to leave a deprecated wrapper;
   the task said remove, so the wrapper was deleted and the call site
   retargeted.
4. **F821 from a symbol you didn't touch = dropped import, not dead
   call site** — restore the import, don't delete the call.
