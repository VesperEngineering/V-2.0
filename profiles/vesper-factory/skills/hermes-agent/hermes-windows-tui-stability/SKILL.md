---
name: hermes-windows-tui-stability
description: "Diagnose and fix Hermes TUI/gateway crashes on Windows — crash log analysis, NTSTATUS exit codes, console-control-event kills, and recovery of dropped work."
version: 1.1.0
author: Hermes Agent
metadata:
  hermes:
    tags: [hermes, windows, tui, gateway, crash, stability, troubleshooting, ntstatus]
---

# Hermes Windows TUI/Gateway Stability

Diagnose and fix crashes of the Hermes TUI's embedded gateway on Windows.
The TUI gateway is a child Python process spawned by the Node-based TUI
parent; when it dies, background terminal sessions and in-flight async
delegations are lost. This skill covers the diagnostic workflow, known
crash codes and their fixes, and recovery of dropped work.

## When to Load

- User reports "all terminal sessions quit" or "everything shut down"
- `tui_gateway_crash.log` shows recurring `child exit` lines
- TUI gateway auto-respawned (fresh `spawned gateway child` entries)
- One of several intentional concurrent TUIs repeatedly receives OAuth `HTTP 401`, `token_expired`, or stale-token errors
- Any Hermes TUI/gateway instability on Windows

## The Architectural Split (Critical)

There are TWO gateway processes on Windows — understanding which one
crashed determines the fix:

1. **Scheduled-task gateway** (Telegram/Discord/etc.): runs via
   `wscript.exe` → `pythonw.exe`, both GUI-subsystem with no console.
   Already hardened against console control events. Check with
   `hermes gateway status`. If this is crashing, it's a different
   class of problem.

2. **TUI embedded gateway**: spawned by `ui-tui/src/gatewayClient.ts`
   via `spawn(python, ['-m', 'tui_gateway.entry'], ...)`. Uses
   console-mode `python.exe` and **inherits the parent's console
   process group**. This is the one that crashes with console control
   events. Crash log entries prefixed `[tui-parent]` are this process.

## Diagnostic Workflow

1. **Read the crash log:**
   ```bash
   tail -50 ~/AppData/Local/hermes/logs/tui_gateway_crash.log
   ```

2. **Identify the exit code.** Look for `child exit pid=XXXX exitCode=NNN`.
   Convert to hex to get the NTSTATUS:
   ```bash
   python -c "print(hex(3221225786))"  # → 0xc000013a
   ```

3. **⚠️ DO NOT assert NTSTATUS meanings from memory.** NTSTATUS codes
   are easy to confuse. Always compute `hex(code)` and verify against
   an authoritative source before diagnosing. Asserting a wrong meaning
   (e.g. calling `0xC000013A` "STATUS_NETWORK_ACCESS_DENIED" when it's
   actually `STATUS_CONTROL_C_EXIT`) sends the entire investigation
   down the wrong path and erodes user trust in the diagnosis.

4. **Check the Hermes source for documented crash codes.**
   `hermes_cli/gateway_windows.py` documents known Windows crash
   patterns in its comments (particularly around console control events
   and `0xC000013A`, lines ~446–455).

5. **Identify which gateway crashed** — TUI (console python.exe, prefix
   `[tui-parent]`) or scheduled-task (pythonw). The fix differs.

6. **Run the diagnostic script** — `scripts/diagnose-tui-crashes.sh`
   gives a quick summary of crash patterns and whether the fix is applied.

## Scheduled-task restart duplication

On Windows, manually running a one-time restart task with `schtasks /Run` does **not** consume or remove a future `TimeTrigger`. If an agent creates a task with a later `StartBoundary` and then runs it immediately, Windows can restart the gateway again at the scheduled boundary. After an approved immediate restart, delete the temporary scheduled task and its XML from an external process, then verify `schtasks /Query /TN <name>` reports that it no longer exists. Never claim the restart is one-shot merely because the manual run succeeded.

## Known Crash Codes

- **`0xC000013A` (STATUS_CONTROL_C_EXIT) / `3221225786`**: Console
  control event killed the gateway child. See
  `references/exit-code-0xC000013A-control-c-exit.md` for the full
  diagnosis and fix. Most common TUI gateway crash on Windows.

## Concurrent OAuth 401 Without Stopping Parallel Work

Multiple Hermes TUIs are a valid operating pattern. If only one session receives `token_expired`, identify the failing session ID and compare its worker start time with the successful auth refresh time. Do **not** tell the user to close every TUI or restart unrelated design/backend work.

Use the least-disruptive sequence:

1. Confirm stored auth is currently valid with `hermes auth status <provider>`.
2. Find the exact failing session in `agent.log`/`errors.log`.
3. Run `hermes auth reset <provider>` and `/retry` in that TUI only.
4. If needed, quit and resume only the failing session with `hermes --resume <session-id> --tui`.
5. Re-login only if a newly started session still fails.
6. Restart the messaging gateway only when the gateway itself is the failing owner.

See `references/concurrent-oauth-token-refresh.md` for the single-use refresh-token race, process/session correlation, exact commands, and reporting contract.

## Recovery of Dropped Work

- **Background terminal sessions** (`processes.json` → `[]`): gone.
  Cannot recover. Use `terminal(background=true, notify_on_complete=true)`
  or cron jobs for work that must survive crashes.
- **Async delegations dropped fail-closed**: preserved in `state.db`
  with their delegation IDs. The fail-closed log entry reads
  `async-delegation completion deleg_XXX has no live owner ... result
  remains in the delegation records`. Queryable from the delegation
  records.
- **Session history**: intact in `state.db` (SQLite + FTS5). Use
  `session_search` to recover conversation context.

## Verification Pattern (Prove You Didn't Break Anything)

When applying a fix to the TUI source:

1. Run the targeted test file: `npx vitest run src/__tests__/gatewayClient.test.ts`
2. Run `node --check` on the built dist: `node --check dist/entry.js`
3. Run `tsc --noEmit` for typecheck
4. Run the full suite: `npx vitest run`
5. **To prove failures are pre-existing** (not caused by your change):
   stash the patch (`git stash push <file>`), re-run the failing tests,
   confirm same failures, then `git stash pop`. This isolates your
   change's impact definitively.

## Key Files

- `~/AppData/Local/hermes/logs/tui_gateway_crash.log` — primary crash log
- `ui-tui/src/gatewayClient.ts` — TUI gateway spawner (source)
- `ui-tui/dist/entry.js` — built bundle (what actually runs; gitignored)
- `tui_gateway/entry.py` — Python gateway entry (signal handlers)
- `hermes_cli/gateway_windows.py` — scheduled-task gateway (documents
  known crash codes in comments)

## Support Files

- `references/exit-code-0xC000013A-control-c-exit.md` — full diagnosis
  and fix for the STATUS_CONTROL_C_EXIT crash
- `references/concurrent-oauth-token-refresh.md` — diagnose and recover one stale OAuth session without stopping other intentional TUIs
- `scripts/diagnose-tui-crashes.sh` — quick crash-log analysis and fix
  verification
