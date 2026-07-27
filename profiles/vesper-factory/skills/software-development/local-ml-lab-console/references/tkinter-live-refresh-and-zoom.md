# Tkinter Live Workspace Refresh and Bounded Canvas Zoom

Use this pattern for dashboards that refresh text/event widgets while users read historical entries and for Canvas graphs that need interactive zoom without coordinate drift.

## Preserve event-log reading position

A periodic refresh must not blindly delete and reinsert text. Before updating:

1. Render the next complete text from durable source state.
2. Compare it to the widget's current content; if unchanged, skip replacement entirely.
3. Capture `(first, last) = widget.yview()` before replacement.
4. Treat the user as following live events only when `last` is at or very near `1.0`.
5. Replace the content once.
6. If the user was following the bottom, move to the new bottom. Otherwise restore `first` so manual historical reading does not jump to the top.

Keep the decision policy in a pure helper returning at least:

- whether content changed;
- whether bottom-follow mode was active;
- the fractional position to restore.

Unit-test unchanged content, manual-scroll preservation during append, and bottom-follow behavior. Then test the actual Tk widget because text replacement, idle layout, and `yview()` timing can differ from pure state.

## Bounded Canvas zoom

Do not repeatedly call `canvas.scale()` on already-scaled coordinates. Accumulated scaling drifts geometry, labels, and hit boxes.

Instead:

1. Keep one canonical graph/workspace source state.
2. Store one bounded zoom level (for example, 60%–200%) with predictable increments.
3. On zoom in/out/reset, compute the new bounded level through a pure helper.
4. Clear and redraw every node, edge, label, and hit target from canonical source coordinates multiplied by the current level.
5. Recompute the Canvas scroll region after every redraw so enlarged content remains reachable.
6. Preserve selected-node identity and detail text across redraws.
7. Provide visible `−`, percentage, `+`, and reset/fit controls; optionally bind Ctrl+wheel and explicit pan/scroll gestures.
8. Keep toolbar hints short enough for the actual pane width; verify them visually at the minimum supported layout.

At zoom levels above fit, some virtual graph content will leave the viewport by design. That is acceptable only when horizontal and vertical panning are visible and functional. Keep persistent context such as controls and selected-node details outside the scrollable graph when practical.

## Native Windows Tk integration tests

Pure helpers are necessary but insufficient. Add Windows-only tests that instantiate the real application and verify:

- manual event-log position remains approximately stable after appended content;
- bottom-follow mode reveals new events;
- zoom controls change the displayed level;
- the scrollable extent grows at zoom-in;
- reset restores the baseline level;
- node selection/details survive a zoom redraw.

Use one stable Tk root/application lifecycle for the integration module when repeated root creation is flaky. Call `update_idletasks()` around geometry/yview assertions, and always destroy the root in teardown.

## Live visual acceptance

After tests pass, capture the native window at baseline and zoomed levels. Confirm:

- controls and hints are not clipped;
- labels and metrics remain legible;
- both graph scrollbars are present when needed;
- event-log and metrics panes are unaffected by graph zoom;
- selected-node styling/details persist.

Do not count an attempted background click as evidence unless the visible percentage or widget state actually changed. If automation cannot confirm the click, invoke the same production zoom method in a temporary verifier instance, capture the resulting state, then remove the verifier.

## Pitfalls

- Replacing unchanged log text every polling interval.
- Always scrolling to `1.0`, which steals control from a user reading history.
- Restoring line indices after append instead of fractional `yview`, causing large jumps.
- Repeatedly scaling existing Canvas items.
- Updating geometry without the scroll region or hit targets.
- Unit-testing helpers while never exercising real Tk widgets.
- Treating a synthetic click command as successful without observing changed state.
- Leaving long instructional hints clipped at narrow pane widths.
