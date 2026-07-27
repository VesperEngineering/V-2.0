# Windows TUI debugging reference

## Failure patterns

- `FAILED: ValueError` with no detail is an insufficient error boundary. Capture a redacted traceback to `.hermes/operator_terminal_error.log` and show only safe type/detail in the UI.
- `ValueError: Wrong color format 'activity-meta'` means a Prompt Toolkit fragment used `class:dashboard activity-meta`. Use `class:dashboard class:activity-meta`.
- Direct execution outside Windows Terminal may fail with `NoConsoleScreenBufferError`; this is not proof that the Windows Terminal pseudoconsole path is broken.
- A malformed diagnostic `wt.exe` command can duplicate a working directory (`D:\vesper\vesper`). Keep `-d` and command ordering explicit; validate the actual desktop `.lnk` separately.
- Default Windows pytest temp directories can have stale Windows permissions. Use a repo-local `.tmp/pytest-*` `--basetemp` and do not mistake the environment failure for a test failure.

## Evidence checklist

1. Inspect the launcher source and confirm the executable (`D:/vesper/.venv/Scripts/python.exe`).
2. Run compile, batch status, controller refresh, and application construction with that executable.
3. Run focused layout/controller/hardening pytest with a writable local basetemp.
4. Force a refresh exception and assert: last good snapshot retained, visible state sanitized, log created, secrets redacted.
5. Launch the actual desktop shortcut or launcher; verify a titled `Vesper Operator Terminal` window and the intended physical dimensions.
6. Read the error log after any failure; do not claim success from a launcher wrapper exit code alone.

## UI design contract

- Left: portfolio/account, market/data, authority, engineering.
- Middle: pipeline, blockers/receipts immediately after pipeline, cadence/timers.
- Right: autonomous cycle/lane state, bounded live activity, recent learnings.
- Activity rows identify `Steward` for cycle events and lane owners for work events.
- Activity is a fixed table: right-aligned elapsed time, fixed-width/truncated activity, and a fixed worker column. Never wrap activity rows or worker names; only wrap narrative learnings to the current Autonomous column width with indented continuation lines.
- Use a softer slate-gray base for ordinary text; reserve brighter semantic colors for green pass, red fail/block, amber waiting/stale, blue running, purple delegated, and distinct worker colors.
- After every source edit, rerun the exact current interpreter test command; stale prior pytest output is not evidence for the changed file.
