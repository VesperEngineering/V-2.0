# Windows TUI debugging reference

## Reproduction sequence

For a Vesper-style operator terminal:

1. Run the user-facing launcher directly and record its exit code.
2. Run the exact interpreter used by the launcher, for example:
   `D:/vesper/.venv/Scripts/python.exe -m app.operator_terminal --command status --width 120`
3. With that same interpreter, run a controller `start()` + `refresh_once()` probe and a Prompt Toolkit app-construction/render probe using `DummyOutput`.
4. Inspect the launcher log and enumerate visible windows by exact title. Confirm the child window dimensions, not merely the wrapper process.
5. If the window exits with only `FAILED: <Type>`, run the child with debug/redirected stderr where possible; otherwise isolate startup, refresh, app construction, and render callbacks individually.

## Redraw stability

The durable fix for scattered redraw fragments was to remove two overrides from the TUI entry point:

- forced `PROMPT_TOOLKIT_OUTPUT=ansi`
- `mode con: cols=... lines=...`

Windows Terminal's pseudoconsole and Prompt Toolkit then negotiate native output and redraw in place.

## Test-environment workaround

A stale Windows `%TEMP%\\pytest-of-<user>` directory can cause `PermissionError` before assertions run. Use a repository-local base directory:

```text
rm -rf .tmp/pytest-tui
mkdir -p .tmp/pytest-tui
python -m pytest <focused tests> -q --tb=short --basetemp='D:/vesper/.tmp/pytest-tui'
```

Treat this as test infrastructure evidence, not a Vesper behavior failure.

## Dashboard design contract

For a normal comfortable viewport, use:

```text
left:   portfolio/account + market/data + authority + engineering
middle: pipeline + blockers/receipts + continuity/timers
right:  autonomous lanes + bounded live activity + learnings
```

Put blockers directly after pipeline so they remain visible in a normal-height viewport. Keep the activity feed bounded (roughly 6 recent events) and worker-attributed. Coordinator cycle markers should say `Steward`; lane actions should say the configured owner, such as `pipeline — Clarke` or `portfolio — Morgan`.

## Color compatibility

Add semantic Prompt Toolkit classes without removing the existing `state-pass`, `state-fail`, `state-running`, and `state-waiting` contracts. A compatibility test may inspect the returned formatted-text style fragments directly, so preserve those class names while adding activity and worker classes.
