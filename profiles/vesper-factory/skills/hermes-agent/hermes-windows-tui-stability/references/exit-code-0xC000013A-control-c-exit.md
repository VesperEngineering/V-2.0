# Exit Code 0xC000013A — STATUS_CONTROL_C_EXIT

**Decimal:** 3221225786
**Hex:** 0xC000013A
**NTSTATUS:** STATUS_CONTROL_C_EXIT

## What It Means

The process was killed by a **console control event** — Windows
broadcast `CTRL_CLOSE_EVENT` or `CTRL_C_EVENT` to a console process
group, and the process was reaped before any handler could run.

This is **NOT**:
- A network fault
- A bug in user code
- A Hermes code bug (in most cases)
- `STATUS_NETWORK_ACCESS_DENIED` (different NTSTATUS — easy to confuse,
  always verify with `hex(code)`)

## Symptom in the Crash Log

```
[tui-parent] 2026-07-18T04:43:23.160Z [lifecycle] child exit pid=10984 killed=false exitCode=3221225786 signal=null code=3221225786 signal=null
[tui-parent] 2026-07-18T04:43:23.168Z [lifecycle] spawned gateway child pid=11644 ...  # auto-respawn
```

User-visible effect: "all the terminal sessions just quit and everything
shut down" — background terminal sessions bound to the old gateway are
lost, in-flight async delegations are dropped fail-closed.

## Why the TUI Gateway (Not the Scheduled-Task Gateway)

The scheduled-task gateway is hardened — it runs via `wscript.exe` →
`pythonw.exe`, both GUI-subsystem with no console (see
`hermes_cli/gateway_windows.py` lines 446–455 for the documented
rationale).

The TUI's embedded gateway is spawned by `ui-tui/src/gatewayClient.ts`
with console-mode `python.exe`, which **inherits the parent's console
process group**. Any `CTRL_CLOSE_EVENT` / `CTRL_C_EVENT` broadcast to
that group reaps the child with `0xC000013A` **before any Python
signal handler can run** — CPython's `signal` module does NOT map
`CTRL_CLOSE_EVENT` to a catchable signal, so there is no in-process
mitigation possible. The fix must be Node-side.

### Two crash sub-patterns (both same root cause)

1. **Direct kill** (most common): Python child exits with `0xC000013A`
   directly — console control event hit the process group.
2. **EPIPE then kill**: Node parent logs
   `uncaughtException: Error: write EPIPE`, then the child dies with
   `0xC000013A`. The EPIPE is a *symptom* of the child dying from a
   console event (its stdio pipes close as it exits), not a separate
   cause.

## The Fix

Spawn the gateway child **detached** into a new process group with no
inherited console.

**File:** `ui-tui/src/gatewayClient.ts` (~line 356, in
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
  detached: true,        // CREATE_NEW_PROCESS_GROUP — no inherited console
  windowsHide: true,     // no incidental console window flash
})
```

**Also patch the built bundle** for immediate effect without rebuild:
`ui-tui/dist/entry.js` (~line 83610) — same change. `dist/` is
gitignored, so only the source change shows in `git diff`.

### Why This Works

- `detached: true` on Windows calls `CreateProcess` with
  `CREATE_NEW_PROCESS_GROUP`. The child gets its own process group with
  no console attached.
- Console control events broadcast to the PARENT's console group never
  reach the child — same protection the scheduled-task gateway gets
  from pythonw.
- stdio pipes unaffected (still pipe-based, drives the readline parsers).
- `proc.kill()` still works for graceful teardown.
- stdin EOF still routes through `_log_exit("stdin EOF...")` when the
  parent exits.
- On non-Windows, `detached: true` is a harmless no-op.

## What This Does NOT Fix

- Full gateway process crashes (segfault, OOM) — not console-event-driven.
  But the crash log shows zero such events; every crash is `0xC000013A`.
- The scheduled-task gateway — already hardened, no change needed.
- Firecrawl `insufficient_funds` errors — unrelated Nous Portal billing
  issue, not a crash cause.

## Verification After Applying

1. Restart the TUI (close and reopen the terminal). The current gateway
   was spawned with old code; only a fresh launch picks up the patched
   `dist/entry.js`.
2. Check `tui_gateway_crash.log` for a fresh `spawned gateway child`
   line with no subsequent `child exit ... 3221225786`.
3. Trigger a console event that previously crashed it (closing another
   tab in the same Windows Terminal window). The gateway should survive.
4. Monitor over a few days — no new `0xC000013A` exits.

## Verification of the Code Change (Test Suite)

1. `node --check dist/entry.js` — syntax valid
2. `npx tsc --noEmit` — typecheck clean
3. `npx vitest run src/__tests__/gatewayClient.test.ts` — 13/13 passed
4. Full suite: 1108 passed, 9 pre-existing failures (verified pre-existing
   via stash-and-compare)
5. No unit test asserts on `spawn` options — the suite proves you didn't
   break anything, but the runtime fix requires TUI restart + observation.
