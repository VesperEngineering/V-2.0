# Operator Terminal: Live Feed, Layout, and Color

## Approved three-column information architecture

At comfortable widths, organize the overview left-to-right as:

1. **Left — system health:** Portfolio / Account, Market / Data, Status / Authority, Engineering.
2. **Middle — evidence and blockers:** Pipeline, Blockers / Receipts, Continuity / Cadence, Project / Timers.
3. **Right — active work:** Autonomous, full-height.

Keep Blockers / Receipts immediately below Pipeline. A long Pipeline → Cadence → Timers → Blockers stack can push urgent blockers below a normal 50-line viewport. The operator scan should be `system state -> evidence/blockers -> active work`.

## Bounded live activity feed

The current safe foundation is the append-only `.hermes/steward_log.jsonl`. The renderer should expose only a bounded tail (typically 6–10 rows) under a `LIVE ACTIVITY` heading. Each row should include:

```text
<age> <status> <lane> — <worker>
```

Examples:

```text
10m54s delegated portfolio — Morgan
 6m58s cycle     cycle 24 — 7 lanes — Steward
 6m58s started   pipeline — Clarke
```

Resolve worker ownership from `.hermes/lanes.json`; do not infer it from a guessed naming convention. Cycle records are coordinator events and must be labeled `Steward`, not `unassigned`. Historical delegation and current action must remain distinguishable.

A future worker-level stream may append structured events to `.hermes/activity.jsonl`, but the UI must not claim worker progress unless an actual event exists. Operational activity is appropriate; raw model prompts, chain-of-thought, credentials, and unfiltered tool output are not.

## Restrained semantic color palette

Use color for hierarchy and state, not decoration:

- pass/completed: green (`#42d392`)
- blocked/failed: red (`#ff5c5c`)
- stale/waiting: amber (`#f0b35a`)
- running/started: blue (`#60a5fa`)
- delegated: purple (`#c084fc`)
- worker accents: stable, distinguishable accents for Clarke, Morgan, Riley, Rez, Thomas, and Steward

Preserve the existing `class:state-pass`, `class:state-fail`, and `class:state-running` style-token contract while adding activity/worker classes. Keep the plain text renderer bounded and readable if terminal color is unavailable.

## Verification

Run syntax checks and the focused terminal suite with a repository-local pytest base directory when the Windows default temp root is inaccessible:

```bash
python -m py_compile app/operator_terminal_layout.py app/operator_terminal.py
python -m pytest tests/test_operator_terminal_layout.py tests/test_operator_terminal_hardening.py tests/test_operator_terminal_controller.py -q --tb=short --basetemp='D:/vesper/.tmp/pytest-dashboard-color'
```

Verify the rendered plain text at approximately 180x50 contains `ENGINEERING` in the left column, `BLOCKERS / RECEIPTS` in the middle, `AUTONOMOUS` on the right, and `LIVE ACTIVITY` with worker-attributed rows. A passing scheduler or pipeline does not imply the dashboard is healthy; preserve distinct status layers.
