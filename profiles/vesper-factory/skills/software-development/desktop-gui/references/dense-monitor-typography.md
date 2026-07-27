# Dense native-monitor typography and safe popup capture

## Use when

A compact Tkinter monitor is operationally correct but relies on 5–7 pt text, the user says labels are difficult to read, or enlarging fonts risks clipping a dense fixed-size layout.

## Typography contract

Treat typography as a coordinated scale, not isolated widget tweaks. For dense Vesper-style operator monitors, use this practical floor unless the user explicitly requests higher density:

- micro/status labels: **8 pt minimum**;
- compact metadata and rail titles: **9 pt**;
- worker names, commands, and main log/output: **10 pt**;
- section headings: **11 pt**;
- selected-task/focus title: **12–13 pt**.

Do not preserve 5–7 pt fonts merely because the reference mockup used them. Visual fidelity includes readable operating truth.

## Change sequence

1. Audit every literal `font=(family, size, ...)` tuple and record the minimum and role hierarchy.
2. Back up a standalone Desktop script before editing.
3. Define a scale contract before replacement. When replacing numeric tuples mechanically, process larger source sizes before smaller ones so a `7 -> 9` replacement is not transformed again by a later `9 -> 10` pass.
4. Scale all related roles together:
   - top-bar values and labels;
   - worker names, titles, ages, and filters;
   - queue/metric values and captions;
   - selected-task metadata;
   - terminal tabs, follow state, and output body;
   - command-palette commands, provider usage, and footer.
5. Increase fixed popup dimensions when larger text introduces wrapping. A move from 430×430 at 7–8 pt to roughly 500×500 at 9–10 pt is a useful starting point, not a universal constant.
6. Keep narrow-rail truncation intentional. The rail may show a compact title, but the selected-task header or detail pane must expose full context.

## Deterministic contract probe

For a standalone Python UI without repository tests, a temporary AST-based pytest can enforce the scale before and after editing:

```python
import ast
from pathlib import Path

source = Path("vesper_worker_monitor.py")
tree = ast.parse(source.read_text(encoding="utf-8"))
sizes = []
for node in ast.walk(tree):
    if not isinstance(node, ast.keyword) or node.arg != "font":
        continue
    value = node.value
    if isinstance(value, ast.Tuple) and len(value.elts) >= 2:
        size = value.elts[1]
        if isinstance(size, ast.Constant) and isinstance(size.value, int):
            sizes.append(size.value)
assert sizes and min(sizes) >= 8
```

Watch the contract fail against the micro-font version, then pass after the coordinated scale. This supplements—never replaces—visual inspection.

## Visual verification

Capture and inspect the actual shortcut-launched HWND after live data has loaded. Check:

- top app bar and provider summary do not crowd or clip;
- worker filters/cards remain distinct;
- queue and focus metrics retain label/value separation;
- terminal tabs and follow state remain aligned;
- main output gains legibility without losing essential evidence;
- the enlarged palette stays within the root and all wrapped provider lines remain visible.

Run syntax and live smoke gates only after the visual direction is accepted or immediately before finalizing/committing, per the creative-UI workflow.

## Safe popup capture

Do not send global hotkeys unless foreground ownership is proven. Windows may reject `SetForegroundWindow`; a subsequent `Ctrl+K` can open a command palette in an unrelated application.

Preferred pattern for Tk apps:

1. Import the real app module in a temporary harness.
2. Instantiate the real `MonitorApp` with the same board/root inputs.
3. Schedule the public popup method (for example `open_command_palette`) with `root.after`.
4. Capture the popup's own native handle from `int(toplevel.winfo_id())` using Win32 `PrintWindow`.
5. Close only the harness instance and leave the verified shortcut-launched final instance open when the user asked to see it.

If keyboard injection is unavoidable, require both a successful foreground switch and an exact foreground-window title check before sending keys. A desktop-region screenshot is not proof that the intended app received the shortcut.

## Common failures

- **Only body text enlarged:** metadata remains unreadable. Fix by scaling the full hierarchy.
- **Fonts enlarged but popup unchanged:** wrapped provider lines overlap or clip. Grow the container and recapture.
- **Global shortcut sent after an unverified focus switch:** an unrelated app reacts. Dismiss the unintended overlay, then use an app-local harness.
- **Rail titles truncate sooner:** keep compact rail summaries but guarantee full context in the focus header/detail pane.
- **Repeated blind replacement cascades sizes:** apply exact role-based edits or replace in descending source-size order.
