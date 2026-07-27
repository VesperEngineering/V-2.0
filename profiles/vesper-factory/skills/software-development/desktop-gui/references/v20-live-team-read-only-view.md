# V20 Live Team — Read-Only Dashboard View

## Purpose

Add a truthful, lightweight operator view of Hermes Kanban workers to an existing V20 Tkinter dashboard. The view answers: **Who is working, on what, for how long, what evidence has appeared, and what happens next?** It does not control workers.

## Source contract

Use read-only Hermes Kanban surfaces for board `v20`:

- inventory/current task: `hermes kanban --board v20 list --json`
- selected task history/output: `hermes kanban --board v20 log <task_id>`
- when needed for run identity/heartbeat, use read-only task/run detail; never infer activity solely from assignment or an old event.

Keep card input/body separate from emitted output. Sanitize credentials, tokens, connection strings, environment values, and unrelated absolute user paths before display. State visibly that worker output is intentionally emitted activity and receipts, not hidden model reasoning.

## Current-state derivation

Maintain one row per approved worker. Derive current state from the newest structured task/run evidence and apply an age cutoff:

- active run with current heartbeat → `RUNNING`
- dependency-ready task → `WAITING`
- unmet prerequisite or explicit blocked result → `BLOCKED`
- latest bounded task completed with passing evidence → `COMPLETE`
- no current work → `IDLE`
- execution failure → `FAILED`
- stale claimed/started event without a current run → `IDLE — last event Xm ago`, never `RUNNING`

A lane owner or assignee is not automatically active. A completed task remains history after a successor starts; do not count both as concurrent workers.

## Recommended layout

Use one `Live Team` button in the existing appbar. Open a dedicated `Toplevel` that reuses the main dashboard's palette and fonts.

- **Top/left worker rail:** status dot, worker name, bounded task title, elapsed age.
- **Selected-worker header:** task ID, current state, started/heartbeat time, predecessor and successor.
- **Main output pane:** selected task's sanitized emitted log/receipt stream.
- **Activity strip:** bounded recent handoffs, starts, completions, blockers, and receipts.
- **Boundary label:** `READ ONLY — emitted worker output, not hidden reasoning; logs are not approval evidence`.

Do not spawn terminal processes to create the visual. The terminal look is a `Text` projection of existing evidence.

## Polling and rendering

- Poll approximately every two seconds in one non-overlapping background worker.
- Return immutable/plain snapshot data through a queue; mutate widgets only on the Tk thread.
- Preserve the last good snapshot through transient failures and show a visible stale/error marker.
- Preserve selected worker/task and output scroll position. Auto-follow only if the operator was already at the bottom.
- Use stable signatures and redraw only changed rows/text.
- Stop and join polling with a bounded close path; cancel all `after` callbacks.

## Animation contract

Animation must communicate real state:

- slow pulse only while a current run is genuinely active;
- quarter-wheel spinner only during a real refresh in flight;
- short highlight only when a new handoff or receipt arrives;
- static status dots for waiting/blocked/complete/idle.

Never simulate terminal typing, invent percent complete, animate idle workers, or keep stale `RUNNING` events moving.

## Authority boundary

The view must not call or expose dispatch, claim, block/unblock, complete, archive, approve/reject, comment, schedule, shell, broker, risk, deployment, or promotion operations. Displaying a card, log, or receipt grants no authority.

## Lean implementation shape

For an existing dashboard, prefer:

1. one `worker_monitor.py` module containing pure snapshot/state derivation plus the Tk view;
2. a small appbar button/window lifecycle hook in the current dashboard app;
3. one focused test module for state derivation, stale activity, redaction, and read-only command construction.

Do not add a service, web server, database copy, new top-level folder, or one process per worker.

## Acceptance matrix

Verify:

- zero, one, and several workers/tasks;
- running, waiting, blocked, complete, idle, failed, and stale-start states;
- selected task preserved across refresh;
- first poll failure followed by successful recovery;
- long task titles and long output at minimum/default geometry;
- redaction fixtures for common secret patterns;
- no mutation commands/routes/widgets in the view;
- no extra worker or terminal processes spawned;
- pulse stops when the run completes or heartbeat ages out;
- actual window launch, two refresh cycles, worker selection, scroll preservation, and clean close.

## Exact companion-window release closure

A hidden-root Tk test proves construction but not the operator click path. For a dashboard button that opens a `Toplevel`:

1. Launch the actual dashboard and capture the parent window with the `Live Team` button visible.
2. Invoke the button, then re-enumerate native windows. The companion is a separate HWND and may not appear when recapturing only the parent.
3. Capture the exact companion by PID/window ID and inspect populated rows, selected output, the read-only boundary label, minimum geometry, and clipping.
4. Select a second worker and verify the visible task/output identity changes. Store an explicit `profile -> task_id` mapping; never reconstruct identity from rendered Treeview labels.
5. Verify no new terminal or worker process was spawned merely for display.
6. Close the companion and parent through their real lifecycle handlers and confirm canceled polling/animation callbacks do not fire after destruction.

Do not claim operator-ready from focused tests, a hidden-root construction probe, or a parent-window screenshot that does not show the companion. State the exact remaining live gate instead.

## Vertical TDD slices

Use small RED→GREEN slices: pure current-state projection; credential redaction/output bounds; button creates the correctly titled read-only companion; selecting a worker switches the exact task identity; then a live board snapshot and visible window probe. This catches selection-mapping defects before visual polish and avoids writing the whole monitor horizontally before any behavior is proven.
