# Vesper v20 Ratatui console

Local Windows console for V20. It is password locked and read-only in the
current Observability phase.

## Current truth

- The console starts only its control gateway. It does not start V20, agents,
  research, training, a scheduler, or trading.
- Reviewed reads currently cover native agent profiles, saved risk state,
  repository state, Windows system state, and the TUI event ledger.
- Portfolio, orders, models, data, and memory stay `UNAVAILABLE` until a typed,
  controller-owned read adapter exists. Running screens never use test fixtures.
- Controls shown as unavailable are not executable.
- Authenticated search merges the current snapshot, complete event ledger, and
  stored context notes. The visible timeline snapshot remains capped at 10,000.
- Context-note input remains a local draft until Controls connects exact
  `note.add` storage. Stored notes are revision 1 only; no edit command is
  exposed. Any future revision must update the current row, immutable history,
  and FTS index in one transaction. A note cannot become an agent command.

## Run from the V20 repository root

Requirements: Windows, Rust 1.97, Cargo, and `uv`.

```powershell
$env:CARGO_TARGET_DIR='C:\tmp\v20-ratatui-target'
cargo run --manifest-path 'TUI testing/ratatui-console/Cargo.toml' --locked
```

The first launch asks you to create the console password. Every later launch
asks for it again. Closing the console does not stop V20.

## Main keys

- `1` through `0`: switch among the ten screens
- Arrow keys: move selection or change the focused panel
- `o`: open selected detail
- `Esc`: go back
- `/`: global search
- `f`: edit current-screen search filters
- `e`: toggle impact-only or all timeline events
- `n`: add a context note when the selected record supports notes
- `i`: agent input area; unavailable until its controller path exists
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
$env:CARGO_TARGET_DIR='C:\tmp\v20-ratatui-target'
cargo fmt --manifest-path 'TUI testing/ratatui-console/Cargo.toml' -- --check
cargo clippy --manifest-path 'TUI testing/ratatui-console/Cargo.toml' --all-targets --locked -- -D warnings
cargo test --manifest-path 'TUI testing/ratatui-console/Cargo.toml' --locked
cargo test --manifest-path 'TUI testing/ratatui-console/Cargo.toml' --release --test performance --locked -- --nocapture

$env:TEMP='C:\tmp\v20-tui-observability-temp'
$env:TMP='C:\tmp\v20-tui-observability-temp'
uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-observability-pytest' -o cache_dir='C:\tmp\v20-tui-observability-cache' tests/platform/tui -q
```

The phase-2 performance test measures event reduction, one-panel rendering in a
focused benchmark path, and 10,000-row navigation. Production still uses a
global redraw flag; partial-render cache wiring remains a final Operations gate.
Cached first screen, end-to-end input latency, idle CPU, continuous memory
growth, and packaged-binary timing also belong to final Operations verification
after caching and packaging exist.
