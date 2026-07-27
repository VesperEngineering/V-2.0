---
name: tkinter-polling-preserve-user-state
description: "When a Tkinter app polls for data, preserve scroll position and selection — don't let the refresh cycle trample what the user is reading or has selected."
version: 1.0.0
author: Hermes Agent
metadata:
  hermes:
    tags: [tkinter, polling, refresh, scroll, selection, ux, vot, vwm]
---

# Tkinter Polling: Preserve User State During Refresh

## The Problem

When a Tkinter desktop app polls for data on a timer (e.g. every 5
seconds), the refresh cycle silently tramples two pieces of user state:

1. **Scroll position** — `text_widget.see(tk.END)` snaps the terminal
   output to the bottom every refresh. If the user scrolled up to read
   provider capacity, issues, or approvals, the refresh yanks them back
   to the bottom mid-read.

2. **Card/row selection** — the refresh re-renders the focus panel with
   the "default" view (primary blocker) instead of the card the user
   clicked on. The user clicks "Candidates", sees it for 5 seconds, then
   it reverts to "Freshness" (the primary blocker) on the next refresh.

Both have the same root cause: the refresh callback doesn't check
whether the user is actively interacting with the view before
overwriting it.

## Fix 1: Preserve Scroll Position

Add a `force_scroll` parameter to the output setter. When `False`
(background refresh), capture the scroll position before the update
and restore it after:

```python
def set_output(text_widget, value, font_fn, *, force_scroll=True):
    was_at_bottom = text_widget.yview()[1] >= 0.995
    view_top = text_widget.yview()[0]
    # ... render the text ...
    if force_scroll and was_at_bottom:
        text_widget.see(tk.END)
    elif not force_scroll:
        text_widget.yview_moveto(view_top)
```

Call with `force_scroll=False` from the background refresh path, and
`force_scroll=True` (default) from user-initiated actions (tab switch,
card click).

## Fix 2: Preserve Card Selection

In the refresh callback (`_apply_snapshot`), check whether a card is
selected. If so, find that card in the new data and keep showing it.
Only fall back to the default (primary blocker) when nothing is
selected or the selected key is no longer in the pipeline:

```python
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

Extract the two display paths into separate methods so both the
initial render and the refresh render call the same code:

- `_show_blocker_in_focus(snap)` — the default view (primary blocker + evidence spine + provider + issues + approvals + cadence + activity)
- `_show_selected_in_focus(row)` — the selected-stage view (just that stage's detail + source)

## Fix 3: Use force_scroll=False on Refresh, True on User Actions

- `_apply_snapshot` (background) → `set_output(..., force_scroll=False)`
- `_select_card` (user click) → `set_output(..., force_scroll=True)`
- `_show_tab` (user tab switch) → `set_output(..., force_scroll=True)`

## General Principle

Any background refresh in a polling Tkinter app must:
1. Capture scroll position before re-rendering text
2. Restore scroll position after (unless user was at bottom and it's a live-follow view)
3. Preserve the selected item across refresh cycles
4. Only snap to bottom if the user was already at the bottom (live-follow semantics)

This applies to VOT, VWM, and any future Tkinter polling app in the
Vesper system.
