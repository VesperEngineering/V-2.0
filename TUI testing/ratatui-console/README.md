# Vesper v20 Ratatui console

Local Windows console for V20. It is password locked. Reads and commands stay
behind the Python controller; the Rust client never calls V20 services directly.

## Current truth

- The console starts only its control gateway. It does not start V20, agents,
  research, training, a scheduler, or trading.
- Reviewed reads currently cover native agent profiles, saved risk state,
  repository state, Windows system state, and the TUI event ledger.
- Portfolio, orders, and data stay `UNAVAILABLE` until a typed,
  controller-owned read adapter exists. Models stay unavailable until V20 owns
  one active/rollback/candidate/regime registry. Running screens never use test
  fixtures.
- Memory reads the existing managed working-memory ledger in strict read-only
  mode. It shows current entries and committed change history; invalid or
  uncommitted state makes the screen unavailable without creating files.
- Controls shown as unavailable are not executable. Their exact server reason
  is visible.
- Failed Windows toast cleanup survives incident switches and restarts in a
  bounded queue of 64 opaque alert IDs. Overflow keeps new urgent truth,
  records generic notification-health failure, and drops the oldest cleanup ID.
- Authenticated search merges the current snapshot, complete event ledger,
  stored context notes, and full bounded archived-memory content. Results expose
  summaries only. On a memory result or Memory-screen row, `o` asks the
  controller for that one current document using its exact reviewed ID and
  timestamp. Loading, changed, and unavailable states stay visible; no archive
  batch is sent to the console. The visible timeline snapshot remains capped at
  10,000.
- Context notes, alert dismissals, layout resets, pending approval decisions,
  and bounded agent enqueue are the currently reviewed command adapters. Every
  command is bound to the reviewed control version/hash and an idempotent
  command ID.
- A locked command is rejected by the protocol and never stored. After unlock,
  durable receipts cover accepted, rejected, running, completed, failed, and
  cancelled states. An exact authenticated replay returns the original receipt
  without rerunning the effect or changing its original client audit record.
- Broker, trading, Live, risk-setting, model promotion, runtime, service,
  scheduler, backup, restore, and push effects remain disabled.

## Current command capability matrix

`Conditional` means the named local adapter exists, but the controller still
requires Take Control, fresh state, an exact selection, valid confirmation, and
all command-specific prerequisites. `Disabled` means no effect adapter exists.

| Command | Confirmation | Current state | Controller reason |
|---|---|---|---|
| `note.add` | none | Conditional | Exact selected stock, order, approval, or agent-event target required. |
| `alert.dismiss` | none | Conditional | Only a resolved alert can be dismissed; its reviewed ID and creation time must still match at admission. |
| `layout.reset` | none | Conditional | The controller records the exact reviewed screen reset; the client applies it only after a completed receipt. |
| `approval.approve` | confirm | Conditional | Fresh platform runtime and exact pending run/checkpoint required. |
| `approval.hold` | confirm | Conditional | Fresh platform runtime and exact pending run/checkpoint required. |
| `approval.reject` | confirm | Conditional | Fresh platform runtime and exact pending run/checkpoint required. |
| `approval.rework` | confirm | Disabled | No reviewed approval rework queue adapter is configured. |
| `agent.send-message` | none | Disabled | No controller-owned agent message port is configured. |
| `agent.enqueue` | confirm | Conditional | Fresh platform runtime and an approved autonomous agent role required. |
| `agent.pause` | confirm | Disabled | No controller-owned pause port is configured. |
| `agent.stop` | confirm | Disabled | The selected work item has no reviewed stop adapter. |
| `agent.retry` | confirm | Disabled | No controller-owned retry port is configured. |
| `agent.set-priority` | confirm | Disabled | No controller-owned priority port is configured. |
| `risk.propose-limit` | confirm | Disabled | No controller-owned risk settings port is configured. |
| `trading.pause` | confirm | Disabled | No controller-owned trading control port is configured. |
| `trading.emergency-stop` | double-confirm | Disabled | No controller-owned trading control port is configured. |
| `service.pause` | confirm | Disabled | No reviewed service supervisor is configured. |
| `service.restart` | confirm | Disabled | No reviewed service supervisor is configured. |
| `runtime.start` | confirm | Disabled | No reviewed runtime manager is configured. |
| `runtime.stop-safe` | confirm | Disabled | No reviewed runtime manager is configured. |
| `runtime.stop-force` | double-confirm | Disabled | No reviewed runtime manager is configured. |
| `runtime.prepare-shutdown` | confirm | Disabled | No reviewed runtime manager is configured. |
| `mode.switch` | confirm | Disabled | No reviewed runtime mode manager is configured. |
| `mode.leave-live` | confirm | Disabled | No reviewed runtime mode manager is configured. |
| `mode.enable-live` | typed-live | Disabled | Live broker activation is not configured or authorized. |
| `model.request-promotion` | confirm | Disabled | No reviewed model promotion port is configured. |
| `model.request-rollback` | confirm | Disabled | No reviewed model rollback port is configured. |
| `memory.compress-now` | none | Disabled | No controller-owned context compression port is configured. |
| `backup.create` | confirm | Disabled | No controller-owned backup command adapter is configured. |
| `backup.restore` | double-confirm | Disabled | No controller-owned backup command adapter is configured. |
| `source-control.push` | confirm | Disabled | No reviewed source-control push adapter is configured. |

## Run the packaged console

The package still uses this V20 checkout and its locked Python environment.
From the repository root:

```powershell
.\dist\tui\vesper-ratatui-console.exe
```

Runtime requirements: Windows and `uv`. Rust and Cargo are needed only to build
or test the package.

Optional current-user Start Menu shortcut:

```powershell
.\scripts\install-tui-shortcut.ps1 -ConfirmInstall
```

That explicit flag creates `Vesper V20 TUI.lnk` only for the current Windows
account. The build does not install it automatically.

## Run from source at the V20 repository root

Build requirements: Windows, Rust 1.97, Cargo, and `uv`.

```powershell
$tuiWorkRoot = Join-Path ([IO.Path]::GetTempPath()) 'vesper-v20-ratatui-run'
$env:CARGO_TARGET_DIR = Join-Path $tuiWorkRoot 'cargo-target'
cargo run --manifest-path 'TUI testing/ratatui-console/Cargo.toml' --locked
```

The first launch asks you to create the console password. Every later launch
asks for it again. Closing the console does not stop V20.

## Main keys

- `1` through `0`: switch among the ten screens
- Arrow keys: move selection or change the focused panel
- `o`: open selected detail; on a Memory row/result, load its exact full content
- `Esc`: go back
- `/`: global search
- `f`: edit current-screen search filters
- `e`: toggle impact-only or all timeline events
- `n`: add a context note when the selected record supports notes
- `:`: open the current screen's complete action list
- `Enter`: activate the selected action or submit focused text
- `Left` / `Right`: choose Cancel or Confirm in a confirmation dialog
- `i`: open the separate agent selector and per-agent chat history; sending stays disabled until a controller message adapter exists
- `?`: open the keyboard and status help panel
- `q`: close only the console

## Architecture and safety

The Rust client talks to the Python gateway through a current-user Windows
named pipe. The gateway owns authentication, sessions, snapshots, and event
storage. Projection adapters expose `read()` only. Missing or invalid sources
fail closed: the screen says `UNAVAILABLE` instead of guessing or substituting
data.

Console state lives under the current Windows account in
`%LOCALAPPDATA%\Vesper\v20\tui`. Password text is never stored or passed on the
command line. The gateway stores only a salted scrypt verifier.

## Verification

Keep build and test artifacts outside the repository.

```powershell
$tuiWorkRoot = Join-Path ([IO.Path]::GetTempPath()) ('vesper-v20-ratatui-verify-' + [Guid]::NewGuid().ToString('N'))
$environmentBefore = [ordered]@{
    TEMP = [Environment]::GetEnvironmentVariable('TEMP', 'Process')
    TMP = [Environment]::GetEnvironmentVariable('TMP', 'Process')
    UV_CACHE_DIR = [Environment]::GetEnvironmentVariable('UV_CACHE_DIR', 'Process')
    CARGO_TARGET_DIR = [Environment]::GetEnvironmentVariable('CARGO_TARGET_DIR', 'Process')
    LOCALAPPDATA = [Environment]::GetEnvironmentVariable('LOCALAPPDATA', 'Process')
}
try {
    $env:TEMP = Join-Path $tuiWorkRoot 'temp'
    $env:TMP = $env:TEMP
    $env:UV_CACHE_DIR = Join-Path $tuiWorkRoot 'uv-cache'
    $env:CARGO_TARGET_DIR = Join-Path $tuiWorkRoot 'cargo-target'
    $env:LOCALAPPDATA = Join-Path $tuiWorkRoot 'local-app-data'
    $pytestTemp = Join-Path $tuiWorkRoot 'pytest'
    $pytestCache = Join-Path $tuiWorkRoot 'pytest-cache'
    New-Item -ItemType Directory -Force $env:TEMP, $env:UV_CACHE_DIR, $env:CARGO_TARGET_DIR, $env:LOCALAPPDATA, $pytestTemp, $pytestCache | Out-Null

    cargo fmt --manifest-path 'TUI testing/ratatui-console/Cargo.toml' -- --check
    cargo clippy --manifest-path 'TUI testing/ratatui-console/Cargo.toml' --all-targets --locked -- -D warnings
    cargo test --manifest-path 'TUI testing/ratatui-console/Cargo.toml' --locked
    cargo test --manifest-path 'TUI testing/ratatui-console/Cargo.toml' --release --locked --test performance production_renderer_performance_gates_are_recorded -- --exact --nocapture --test-threads=1
    cargo test --manifest-path 'TUI testing/ratatui-console/Cargo.toml' --release --locked --test cached_unlock_probe real_dpapi_cached_unlock_reaches_the_backend_and_reaps_the_probe -- --ignored --exact --nocapture --test-threads=1
    cargo test --manifest-path 'TUI testing/ratatui-console/Cargo.toml' --release --locked --test performance idle_tick_component_ten_minute_entrypoint -- --ignored --exact --nocapture --test-threads=1
    cargo test --manifest-path 'TUI testing/ratatui-console/Cargo.toml' --release --locked --test retained_memory retained_memory_one_hour_entrypoint -- --ignored --exact --nocapture --test-threads=1
    uv run --locked python -m pytest --basetemp $pytestTemp -o "cache_dir=$pytestCache" tests/platform/tui -q
}
finally {
    foreach ($entry in $environmentBefore.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process')
    }
}
```

Production uses a committed full-frame buffer with full-width regional redraws.
The release performance test records raw samples for cache projection, events,
input, 10,000-row navigation, long chat, and shutdown. The separate ignored
probe covers the real current-user DPAPI cache and Python gateway. The 10-minute
idle Tick/render component CPU and one-hour retained-memory tests are ignored by
default and must be run explicitly for a release receipt. The idle component
test does not measure Crossterm, ConPTY, or the complete Windows process loop;
those need a separate real-terminal measurement.
The retained-memory gate starts after the 480-message logical retention window
is established. A test-only allocator measures live bytes for the 10 MiB gate;
Windows PrivateUsage and initialization growth are reported as information only.
