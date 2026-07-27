# Operator Terminal — Autonomous Panel

The Vesper Operator Terminal (`app/operator_terminal.py`) displays a real-time AUTONOMOUS panel showing the work steward state, lane statuses, and team learnings.

## Data Flow

```
.hermes/steward_state.json   →   load_autonomous_snapshot()   →   TerminalSnapshot.autonomous
.hermes/lanes.json                    (app/services/operator_terminal_status.py)
.hermes/learnings.jsonl
                                      ↓
                            _autonomous_rows()   →   AUTONOMOUS panel
                            (app/operator_terminal_layout.py)
```

## What It Shows

- **Cycle number** — how many steward cycles since start
- **Last action** — which lane ran last and its status (ok/failed/blocked/delegated)
- **Stuck cycles** — consecutive cycles with no forward progress (triggers Thomas escalation at 4)
- **Lane status** — all 7 lanes with icon indicating state:
  - `○ ready` — unblocked, available for dispatch
  - `● blocked` — check command returned non-zero (blocked_if reason shown in lanes.json)
  - `◐ delegated` / `◒ running` — worker has been dispatched
  - `⚠ escalated` — stuck threshold reached, Thomas escalation in progress
- **Team learnings** — last 3 entries from learnings.jsonl

## Refresh & Zoom

- **Refresh every 1 second** (changed from 5s on 2026-07-14 in `app/operator_terminal.py` via `REFRESH_SECONDS = 1.0`).
- **+ and - keys** cycle zoom level (0=focused, 1=balanced, 2=detailed) in `dispatch_dashboard_key()`. Zoom controls column layout density and row count per panel. Header shows current zoom level.
- **Rebalanced layout** (2026-07-14): right column was overcrowded (continuity+project+blockers+engineering+autonomous). Now middle column gets pipeline + continuity/project; right column keeps blockers + engineering + autonomous.
- **Dashboard uses `controller.zoom_level`** stored in `DashboardUiState.zoom_level`. The `DashboardController` exposes `zoom_level` property and `set_zoom()` which clamps to 0–2 and invalidates.

## Code

- `app/services/operator_terminal_status.py`: `AutonomousSnapshot`, `LaneStatus` dataclasses + `load_autonomous_snapshot()`
- `app/operator_terminal_layout.py`: `_autonomous_rows()` render function
- `app/operator_terminal_status.py`: `TerminalSnapshot.autonomous` field (optional)
