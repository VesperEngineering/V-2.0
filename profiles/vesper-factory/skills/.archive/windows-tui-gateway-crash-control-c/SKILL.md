---
name: windows-tui-gateway-crash-control-c
description: "Diagnose and fix Hermes TUI gateway crashes with Windows exit code 3221225786 / 0xC000013A (STATUS_CONTROL_C_EXIT)."
version: 1.0.0
author: Hermes Agent
metadata:
  hermes:
    tags: [hermes, windows, tui, gateway, crash, troubleshooting, stability]
---

# Windows TUI Gateway Crash — 0xC000013A / STATUS_CONTROL_C_EXIT

## Symptom

The Hermes TUI's embedded gateway child process dies unexpectedly and
auto-respawns. In `~/AppData/Local/hermes/logs/tui_gateway_crash.log`,
repeated lines like:

```
[tui-parent] 2026-07-18T04:43:23.160Z [lifecycle] child exit pid=10984 killed=false exitCode=3221225786 signal=null code=3221225786 signal=null
[tui-parent] 2026-07-18T04:43:23.168Z [lifecycle] spawned gateway child pid=11644 ...
```

User-visible effect: "all the terminal sessions just quit and everything
shut down" — background terminal sessions bound to the old gateway are
lost, in-flight async delegations are dropped fail-closed (preserved in
`state.db` but not delivered to any session).

## Root Cause

**Exit code `3221225786` = `0xC000013A` = `STATUS_CONTROL_C_EXIT`.**
This is NOT a network fault and NOT a bug in user code. It is the code
Windows uses when a process is killed by a **console control event**
(`CTRL_CLOSE_EVENT`, `CTRL_C_EVENT`) broadcast to a console process
group.

The scheduled-task gateway (Telegram/Discord/etc.) is hardened against
this — it runs via `wscript.exe` → `pythonw.exe`, both GUI-subsystem
with no console (see `hermes_cli/gateway_windows.py` lines 446–455).

The TUI's embedded gateway is a DIFFERENT process. It is spawned by
`ui-tui/src/gatewayClient.ts` with `spawn(python, ['-m',
'tui_gateway.entry'], { stdio: ['pipe','pipe','pipe'] })` using
console-mode `python.exe`, which **inherits the parent's console process
group**. Any `CTRL_CLOSE_EVENT` / `CTRL_C_EVENT` broadcast to that group
(tab close, stray Ctrl+C in the wrong window, EA AntiCheat filter events,
console window close) reaps the child with `0xC000013A` **before any
Python signal handler can run** — CPython's `signal` module does NOT map
`CTRL_CLOSE_EVENT` to a catchable signal, so there is no in-process
mitigation possible.

### Two crash sub-patterns (both same root cause)

1. **Direct kill** (most common): Python child exits with `0xC000013A`
   directly — console control event hit the process group.
2. **EPIPE then kill**: Node parent logs
   `uncaughtException: Error: write EPIPE`, then the child dies with
   `0xC000013A`. The EPIPE is a *symptom* of the child dying from a
   console event (its stdio pipes close as it exits), not a separate
   cause.

## Verification

1. Confirm the crash code:
   ```bash
   python -c "print(hex(3221225786))"  # → 0xc000013a
   ```
2. Check the crash log for the recurring pattern:
   ```bash
   grep -E "child exit.*3221225786" ~/AppData/Local/hermes/logs/tui_gateway_crash.log | tail -20
   ```
3. Confirm the scheduled-task gateway is NOT affected (it uses
   pythonw):
   ```bash
   hermes gateway status
   # Should show PID running cleanly, no recent restarts
   ```

## Fix (Applied 2026-07-18)

Spawn the gateway child **detached** into a new process group with no
inherited console. This is the Node-side equivalent of the
pythonw/wscript hardening the scheduled-task gateway already uses.

**File:** `ui-tui/src/gatewayClient.ts` (around line 356, in
`startSpawnedGateway`)

**Before:**
```typescript
this.proc = spawn(python, ['-m', 'tui_gateway.entry'], { cwd, env, stdio: ['pipe', 'pipe', 'pipe'] })
```

**After:**
```typescript
this.proc = spawn(python, ['-m', 'tui_gateway.entry'], {
  cwd,
  env,
  stdio: ['pipe', 'pipe', 'pipe'],
  detached: true,        // CREATE_NEW_PROCESS_GROUP on Windows — no inherited console
  windowsHide: true,     // no incidental console window flash
})
```

**Also patch the built bundle** so the fix takes effect without a
rebuild:
- `ui-tui/dist/entry.js` (around line 83610) — same change.

The source file is git-tracked; `dist/` is gitignored, so only the
source change shows in `git diff`.

### Why this works

- `detached: true` on Windows calls `CreateProcess` with
  `CREATE_NEW_PROCESS_GROUP`. The child gets its own process group with
  no console attached.
- Console control events broadcast to the PARENT's console group never
  reach the child — the exact same protection the scheduled-task
  gateway gets from pythonw.
- stdio pipes are unaffected (still pipe-based, still drives the
  readline parsers).
- `proc.kill()` still works for graceful teardown.
- stdin EOF still routes through `_log_exit("stdin EOF...")` when the
  parent exits — the clean shutdown path is preserved.
- On non-Windows platforms, `detached: true` is a harmless no-op (the
  child is already in its own session via the POSIX spawner).

## What This Does NOT Fix

- **Full gateway process crashes** (not console-event-driven) — if the
  Python gateway itself segfaults or OOMs, this won't help. But the
  crash log shows zero such events; every crash is `0xC000013A`.
- **The scheduled-task gateway** — already hardened, no change needed.
- **Firecrawl `insufficient_funds` errors** — unrelated; a Nous Portal
  billing issue, not a crash cause.

## Recovering Dropped Work After a Crash

- **Background terminal sessions** (`processes.json` → `[]`): gone.
  Cannot recover. Use `terminal(background=true, notify_on_complete=true)`
  or cron jobs for work that must survive crashes.
- **Async delegations dropped fail-closed**: preserved in `state.db`
  with their delegation IDs (e.g. `deleg_9df9fefd`). Queryable via
  the delegation records. The fail-closed log entry:
  `async-delegation completion deleg_XXX has no live owner ... dropping
  from injection instead of delivering to session ... (result remains in
  the delegation records)`.
- **Session history**: intact in `state.db` (SQLite + FTS5). Use
  `session_search` to recover conversation context.

## Verification After Applying the Fix

1. Restart the TUI (close and reopen the terminal/hermes session).
2. Confirm the new gateway child is running detached — check
   `tui_gateway_crash.log` for a fresh `spawned gateway child` line
   with no subsequent `child exit ... 3221225786`.
3. Try to trigger a console event that previously crashed it (closing
   another tab in the same Windows Terminal window, etc.). The gateway
   should survive.
4. Monitor over a few days — the crash log should show no new
   `0xC000013A` exits.

## Key Files

- `ui-tui/src/gatewayClient.ts` — TUI gateway spawner (source of fix)
- `ui-tui/dist/entry.js` — built bundle (patch for immediate effect)
- `tui_gateway/entry.py` — Python gateway entry (signal handlers; note
  `CTRL_CLOSE_EVENT` is NOT in the signal map — that's why the Node-side
  fix is required, not a Python-side `SetConsoleCtrlHandler`)
- `hermes_cli/gateway_windows.py` — scheduled-task gateway (already
  hardened via pythonw/wscript; documents the same `0xC000013A` issue
  at lines 446–455)
- `~/AppData/Local/hermes/logs/tui_gateway_crash.log` — crash log
