# Tkinter refresh-stable logs and zoomable canvases

Use these patterns for periodically refreshed operator consoles where the user must be able to read history and inspect a graph without refreshes fighting them.

## Preserve a Text widget's reading position

The common failure is unconditional `delete()` + `insert()` on every poll. Tk resets the viewport to the beginning even when the content did not change.

Before replacement:

1. Build the complete next text value.
2. Read current content with `text.get("1.0", "end-1c")`.
3. Capture `(first, last) = text.yview()`.
4. If content is unchanged, do nothing.
5. Treat `last >= 0.999` as “following the bottom.”
6. If content changed, replace it once, call `update_idletasks()`, then:
   - move to `1.0` only when the old view was already at the bottom (or the widget was empty);
   - otherwise restore `first` with `yview_moveto(first)`.

Keep the decision in a pure helper so unchanged, manual-scroll, and follow-bottom behavior can be unit-tested without Tk.

```python
def event_log_update_state(
    current_text: str,
    next_text: str,
    yview: tuple[float, float],
) -> tuple[bool, float | None]:
    if current_text == next_text:
        return False, None
    first, last = yview
    if not current_text or last >= 0.999:
        return True, 1.0
    return True, min(max(first, 0.0), 1.0)
```

Regression-test the real widget too: load enough lines to overflow, move to a nonzero fraction, append an event, refresh, and assert the first fraction remains approximately equal. This catches widget semantics that a pure helper cannot.

## Bounded graph zoom with pan

Keep a scalar zoom value and always redraw from source graph state. Do not repeatedly call `Canvas.scale()` on already-scaled items; cumulative transforms drift and complicate selection state.

Recommended contract:

- explicit `−`, `+`, and `Reset` controls;
- a percentage label;
- Ctrl+mouse-wheel support;
- readable bounds such as 60%–200%;
- horizontal and vertical scrollbars;
- `scrollregion` larger than the viewport above 100%;
- selected-node identity stored separately and reused after redraw.

```python
def bounded_zoom(current: float, delta: float) -> float:
    return round(min(max(current + delta, 0.6), 2.0), 2)
```

For redraw:

1. Read viewport dimensions with safe fallbacks because an unmapped canvas reports `1`.
2. Compute virtual dimensions from viewport × zoom and set `scrollregion`.
3. Compute node positions, radii, fonts, edge widths, and arrows from the scalar zoom.
4. Delete/recreate from the authoritative graph state.
5. Recenter after an explicit zoom change, but do not recenter on ordinary refreshes or selection redraws; that would fight operator panning.

At zoom >100%, clipping portions of virtual graph content is expected only when scrollbars clearly permit panning. Keep toolbar controls outside the scrollable canvas so they never disappear.

## Tk regression harness

For Windows-specific GUI tests:

- import the launcher module by path;
- replace asynchronous refresh with a no-op before constructing the app;
- create a mapped window and set alpha to `0.0` before `update()` so real geometry and widget semantics exist without visible distraction;
- reuse one Tk root per test module when possible;
- destroy the root in fixture teardown.

A withdrawn canvas is not suitable for item-binding tests because it has no mapped `current` item. Use mapped-but-transparent instead.

Test both layers:

- pure policy tests for bounds and scroll decisions;
- real Tk tests for `Text.yview()`, canvas `scrollregion`, Reset, and wheel bindings.

## Native visual acceptance

After automated tests:

1. launch the real Windows app;
2. capture the exact window (for example with `PrintWindow`) at 100% and at one zoomed level;
3. verify controls, labels, legends, scrollbars, selection details, and adjacent panes;
4. do not claim a synthetic background click worked unless the percentage/state visibly changed;
5. shorten toolbar hints rather than allowing one-character clipping at minimum pane width.
