# Read-only worker monitor: Command Split reference

## Use when

A user supplies an HTML/mockup direction for a native worker monitor and wants the command-split composition: worker rail on the left, selected worker/task focus on the right, and a terminal-first evidence surface.

## Implementation contract

1. Inspect the reference and name the accepted visual direction before editing. Translate the visual hierarchy into semantics:
   - left rail: worker/task identity, state, task title, filters, queue counts;
   - focus header: selected worker, task ID, workspace/branch, status, start time;
   - terminal body: complete output by default, with a separate task-brief/input view;
   - unsupported evidence classes: explicit unavailable state.
2. Preserve the source-of-truth boundary. For a Hermes Kanban monitor, use read-only list JSON for task inventory, task card body/result for input, and the complete task log for output. Do not add dispatch, claim, block, archive, completion, shell, or approval controls to a visibility view.
3. On an external Desktop script, create a timestamped `.bak-*` copy before the first edit. Verify the backup count/path before continuing.
4. Prefer a deterministic method-boundary rewrite for a compact Tkinter file when several methods must change. Replace from an exact `def` marker to the next exact `def` marker in memory, write once, then compile. Fuzzy multi-line patching can consume adjacent loop headers or method definitions; if that happens, stop applying incremental patches and restore the whole affected method atomically.
5. Track Tk callback IDs:
   - store the queue-drain `after()` ID and refresh `after()` ID;
   - guard refresh/drain callbacks with `_closing`;
   - on `WM_DELETE_WINDOW`, set `_closing`, cancel both IDs with `after_cancel`, then `root.destroy()`.
6. Make time units visible in code. If the UI says polling every two seconds, use `POLL_SECONDS = 2` and schedule `after(POLL_SECONDS * 1000, refresh)`.

## HTML-to-native visual fidelity loop

When the user says the supplied HTML is the target, use a rendered visual comparison—not source inspection alone.

1. **Confirm the exact artifact first.** Distinguish similarly named apps, scripts, and shortcuts before editing. Inspect the actual Desktop `.lnk`, its target script, arguments, working directory, and icon.
2. **Render the reference at a known viewport.** Use an installed Chromium-compatible browser in headless mode to produce a PNG of the local HTML. Record the CSS frame rectangle, not the surrounding design-study page.
3. **Capture the native window itself.** Find the titled HWND with `EnumWindows` and capture it with Win32 `PrintWindow`. A desktop-region screenshot can contain unrelated overlapping or always-on-top windows even after `SetForegroundWindow`.
4. **Compare equal pixel rectangles.** Crop the HTML frame and native client area to the same dimensions, place them side by side at 1:1 scale, and inspect geometry before colors or micro-typography. CSS frame dimensions map to the native **client area**; window borders/title bar make the outer HWND larger.
5. **Translate composition, not widget category.** If the reference shows custom worker cards, do not keep a `Treeview` merely because the input is tabular. For a worker-centric rail, group task cards by assignee, choose one representative task by explicit status/recency priority, retain the real total task count, and filter over grouped workers.
6. **Use sample content only as layout evidence.** Preserve live assignees, statuses, titles, counts, paths, and log output. Never copy mock metrics such as files changed or checks passed unless an authoritative source exists; substitute real sourced metrics in the same visual slots.
7. **Extract exact tokens and rhythm.** Carry CSS colors, rail width, bar/header heights, padding, borders, and font hierarchy into named Tk constants. Fix the largest measured mismatch per pass, re-capture, and repeat.
8. **Clean terminal presentation without changing evidence.** Strip ANSI control sequences before display, retain complete log text, and use text tags only for visual emphasis. Do not summarize away emitted evidence.
9. **Brand both launch and window surfaces.** A shortcut `IconLocation` does not guarantee the Tk title-bar icon. Set the `.lnk` icon and call `root.iconbitmap(...)` when supported.
10. **Keep read-only controls real.** A reference command-palette button should open a functional palette of safe view/refresh/copy actions or be relabeled; do not ship decorative dead controls.

A successful pass records: reference PNG, native PNG, optional 1:1 side-by-side image, live data smoke output, actual shortcut properties, native close acceptance, and zero remaining monitor PIDs.

## Verification gates

Run all of these against the same interpreter used by the launcher:

```bash
D:/vesper/.venv/Scripts/python.exe -m py_compile C:/Users/<user>/Desktop/vesper_worker_monitor.py
export PATH='D:/vesper/.venv/Scripts':"$PATH"
D:/vesper/.venv/Scripts/python.exe C:/Users/<user>/Desktop/vesper_worker_monitor.py \
  --board vesper --root D:/vesper --smoke-test
```

The smoke test must use the same list/log functions as the GUI and report real task and log counts. A withdrawn Tk root is not enough to prove widget construction; launch the real window with `pythonw.exe` under a bounded external probe.

## Native X/PID probe on Windows

`Get-Process.MainWindowTitle` is not sufficient when a `pythonw.exe` launcher/shim spawns a child interpreter: the titled Tk window may belong to the child PID. Use Win32 `EnumWindows`, `GetWindowThreadProcessId`, `IsWindowVisible`, and `GetWindowText` to find the exact visible HWND whose title is `Vesper Worker Monitor`.

Then send a real close request:

```text
PostMessage(hwnd, WM_CLOSE=0x0010, 0, 0)
```

Before launching, record existing processes whose command line contains the monitor script. After launch, identify newly-created matching PIDs, find the titled HWND across those PIDs, send `WM_CLOSE`, and poll the command-line process set until all newly-created monitor PIDs are gone. If the probe times out, terminate only the PIDs created by that probe and report the harness failure separately from an application failure.

Successful evidence should include the exact window title, window PID/handle, whether `WM_CLOSE` was accepted, and that the new monitor PID set is empty. This proves the actual top-right X path, not merely that the Python source compiles.

## Truthful refresh behavior

Keep the last successful task summary and complete log visible while a background fetch runs. Cache logs by task ID and only repaint when fetched content differs. Do not claim `LIVE` from a refresh timer alone; label the monitor read-only and distinguish displayed output from approval or execution evidence.

## Common failure modes

- A visual reference is implemented as a cosmetic restyle while the data lineage or input/output boundary changes. Fix by writing the data contract before laying out widgets.
- `POLL_SECONDS = 2_000` is mistaken for two seconds. Fix by using milliseconds explicitly in `after()`.
- Closing Tk with only `root.destroy` leaves callbacks/subprocess work unmanaged. Fix by tracking callback IDs and making the close path idempotent. For subprocesses that can outlive the GUI, track and terminate them separately; daemon threads alone are not a shutdown guarantee.
- `MainWindowTitle` is blank because the visible Tk HWND belongs to a child interpreter. Fix by enumerating visible top-level HWNDs and mapping them to PIDs.
- A fuzzy patch drops `for`/`while` headers or `def` lines. Fix by backing up, replacing complete method boundaries deterministically, compiling immediately, and only then running the live smoke/window probes.
