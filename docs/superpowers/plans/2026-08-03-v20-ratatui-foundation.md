# V20 Ratatui Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a password-locked Ratatui application with the approved fixed shell, ten navigable screens, and a secure versioned connection to a Python control gateway.

**Architecture:** Python owns contracts, authentication, control ownership, and V20 state. Rust connects through a current-user-only Windows named pipe, reduces snapshots and events into local view state, and renders without writing V20 state. Phase 1 exposes only connection, lock, layout, and read-only shell capabilities.

**Tech Stack:** Python 3.11.15, Pydantic 2, pywin32 312, Rust 1.97.0 edition 2024, Ratatui 0.30.2, Crossterm 0.29.0, Tokio 1.53.1, Serde, Insta.

## Global Constraints

- Execute from an isolated worktree based on reviewed commit `9b958a5` or its reviewed descendant.
- Preserve the user's existing dirty main worktree.
- Windows is the only supported operating system in this phase.
- Use `qwen:64k` only; this phase does not start Qwen or any V20 runtime.
- Rust never imports, edits, or opens authoritative V20 databases.
- Python never opens a broker, account, scheduler, model trainer, or protected data source in this phase.
- Use pipe name `\\.\pipe\vesper-v20-tui-{sid_hash_16}`, where `sid_hash_16`
  is the first 16 lowercase hexadecimal characters of the logon SID SHA-256.
- Allow the signed-in logon SID only in the pipe DACL. Do not use the default named-pipe security descriptor.
- Frames are `4-byte unsigned big-endian length + UTF-8 JSON` with a 1,048,576-byte maximum payload.
- Protocol schema version is integer `1`.
- IDs crossing the wire must match
  `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$` and may not be `.` or `..`.
- Store console state below `%LOCALAPPDATA%\Vesper\v20\tui`.
- Run every pytest command with `TEMP` and `TMP` set to
  `C:\tmp\v20-tui-foundation-temp`, `--basetemp
  C:\tmp\v20-tui-foundation-pytest`, and `-o
  cache_dir=C:\tmp\v20-tui-foundation-cache`.
- Password derivation uses `hashlib.scrypt` with a 16-byte random salt, `n=32768`, `r=8`, `p=1`, `dklen=32`, and `maxmem=67108864`.
- Store only version, salt, scrypt parameters, and verifier. Never store or log the password.
- Closing the TUI does not start, stop, pause, or change V20.
- Use test-first changes and one Conventional Commit per task.

---

## File map

```text
vesper/platform/tui/
|-- __init__.py              public gateway package
|-- contracts.py             strict wire and shell contracts
|-- protocol.py              frame encoding and message decoding
|-- auth.py                  scrypt verifier and control lease
|-- pipe_security.py         current-logon SID and pipe DACL
|-- pipe_server.py           pywin32 duplex server
|-- gateway.py               connection/session coordinator
`-- cli.py                   control-only gateway entrypoint

tests/platform/tui/
|-- test_contracts.py
|-- test_protocol.py
|-- test_auth.py
|-- test_pipe_security.py
|-- test_pipe_server.py
`-- test_gateway.py

TUI testing/ratatui-console/
|-- Cargo.toml
|-- Cargo.lock
|-- src/
|   |-- lib.rs
|   |-- main.rs
|   |-- contract.rs
|   |-- transport.rs
|   |-- launcher.rs
|   |-- state.rs
|   |-- app.rs
|   |-- input.rs
|   |-- layout.rs
|   |-- theme.rs
|   `-- ui.rs
`-- tests/
    |-- contract.rs
    |-- transport.rs
    |-- state.rs
    |-- input.rs
    `-- snapshots.rs
```

### Task 1: Pin the Windows transport dependency

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Test: `tests/platform/test_dependencies.py`

**Interfaces:**
- Produces: `pywin32==312` on Windows only.
- Preserves: the existing Python 3.11 range and all current locked packages.

- [ ] **Step 1: Add the failing dependency assertion**

```python
import tomllib
from pathlib import Path


def test_tui_windows_transport_is_pinned() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    dependencies = tuple(project["project"]["dependencies"])
    assert "pywin32==312; sys_platform == 'win32'" in dependencies
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `uv run --locked python -m pytest tests/platform/test_dependencies.py -q`

Expected: FAIL because pywin32 is absent.

- [ ] **Step 3: Add and lock the dependency**

Add this exact project dependency:

```toml
"pywin32==312; sys_platform == 'win32'",
```

Run: `uv lock`

- [ ] **Step 4: Verify GREEN**

Run: `uv run --locked python -m pytest tests/platform/test_dependencies.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `build(tui): pin Windows pipe support`

### Task 2: Define strict wire and shell contracts

**Files:**
- Create: `vesper/platform/tui/__init__.py`
- Create: `vesper/platform/tui/contracts.py`
- Create: `tests/platform/tui/test_contracts.py`

**Interfaces:**
- Produces enum `MessageType`: `client-hello`, `server-hello`, `auth-setup`, `auth-unlock`, `auth-result`, `snapshot-request`, `snapshot`, `event`, `command`, `command-receipt`, `protocol-error`, `ping`, `pong`.
- Produces enum `Freshness`: `loading`, `fresh`, `stale`, `unavailable`.
- Produces enum `OperatingMode`: `stopped`, `shadow`, `paper`, `live`.
- Produces enum `CapabilityState`: `enabled`, `read-only`, `disabled`.
- Produces models `CapabilityView`, `HeaderView`, `AlertView`, `ShellSnapshot`, `WireEnvelope`, and the thirteen typed payload models.
- Every model uses `ConfigDict(extra="forbid", frozen=True, strict=True)`.

- [ ] **Step 1: Write contract rejection and round-trip tests**

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from vesper.platform.tui.contracts import MessageType, WireEnvelope


def test_envelope_round_trips_and_rejects_unknown_fields() -> None:
    value = WireEnvelope(
        schema_version=1,
        message_id="server:1",
        sequence=1,
        state_version=0,
        timestamp=datetime(2026, 8, 3, tzinfo=timezone.utc),
        message_type=MessageType.SERVER_HELLO,
        payload={"server_version": "0.1.0", "requires_setup": True},
    )
    assert WireEnvelope.model_validate_json(value.model_dump_json()) == value
    with pytest.raises(ValidationError):
        WireEnvelope.model_validate({**value.model_dump(), "secret": "x"})
```

Also test naive timestamps, timestamps whose UTC offset does not match
America/New_York at that instant, blank IDs, negative sequences, schema versions
other than `1`, invalid enum values, and secret-like unknown fields.

- [ ] **Step 2: Run the contract test and verify RED**

Run: `uv run --locked python -m pytest tests/platform/tui/test_contracts.py -q`

Expected: FAIL because the package does not exist.

- [ ] **Step 3: Implement the exact shell types**

Use these field signatures:

```python
class CapabilityView(StrictModel):
    capability_id: NonEmptyStr
    state: CapabilityState
    reason: NonEmptyStr | None = None


class HeaderView(StrictModel):
    operating_mode: OperatingMode
    data_freshness: Freshness
    data_age_seconds: float | None
    regime_label: str
    regime_confidence: float | None
    portfolio_value: float | None
    next_rebalance_at: datetime | None
    rebalance_blockers: tuple[str, ...]
    active_agent: str | None
    agent_queue_length: int
    qwen_state: str
    qwen_context_percent: float | None
    eastern_time: datetime
    market_session: str


class ShellSnapshot(StrictModel):
    state_version: int
    generated_at: datetime
    header: HeaderView
    alerts: tuple[AlertView, ...]
    capabilities: tuple[CapabilityView, ...]
```

`WireEnvelope.payload` remains a JSON object. `decode_payload(envelope)` maps
every `MessageType` to one exact Pydantic payload model and rejects mismatches.

- [ ] **Step 4: Run contract tests and export a schema receipt**

Run: `uv run --locked python -m pytest tests/platform/tui/test_contracts.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat(tui): define secure console contracts`

### Task 3: Implement bounded frame encoding

**Files:**
- Create: `vesper/platform/tui/protocol.py`
- Create: `tests/platform/tui/test_protocol.py`

**Interfaces:**
- Produces: `encode_frame(envelope: WireEnvelope) -> bytes`.
- Produces: `FrameDecoder.feed(chunk: bytes) -> tuple[WireEnvelope, ...]`.
- Produces: `ProtocolViolation(code: str, safe_message: str)`.

- [ ] **Step 1: Write split, joined, malformed, and oversized frame tests**

```python
def test_decoder_handles_split_and_joined_frames(server_hello, ping) -> None:
    body = encode_frame(server_hello) + encode_frame(ping)
    decoder = FrameDecoder()
    assert decoder.feed(body[:3]) == ()
    assert decoder.feed(body[3:11]) == ()
    assert decoder.feed(body[11:]) == (server_hello, ping)
```

Assert that zero length, length above `1_048_576`, invalid UTF-8, invalid JSON,
wrong schema, and wrong payload produce safe codes without echoing input bytes.

- [ ] **Step 2: Run the protocol tests and verify RED**

Run: `uv run --locked python -m pytest tests/platform/tui/test_protocol.py -q`

Expected: FAIL because framing is absent.

- [ ] **Step 3: Implement one bounded byte buffer**

Use `struct.Struct(">I")`, retain incomplete bytes, decode complete frames in
order, and clear the buffer after any fatal frame violation. Never allocate the
declared body until its length passes the maximum check.

- [ ] **Step 4: Run the tests and verify GREEN**

Run: `uv run --locked python -m pytest tests/platform/tui/test_protocol.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat(tui): add bounded wire framing`

### Task 4: Add password setup, unlock, and control lease

**Files:**
- Create: `vesper/platform/tui/auth.py`
- Create: `tests/platform/tui/test_auth.py`

**Interfaces:**
- Produces: `PasswordStore.setup(password: str, confirmation: str) -> None`.
- Produces: `PasswordStore.verify(password: str) -> bool`.
- Produces: `ControlLease.acquire(client_id: str) -> LeaseStatus`.
- Produces: `ControlLease.release(client_id: str) -> None`.
- Produces lease statuses `controller`, `viewer`, and `transferred`.

- [ ] **Step 1: Write authentication and lease tests**

```python
def test_password_store_keeps_only_verifier(tmp_path) -> None:
    store = PasswordStore(tmp_path / "auth.json")
    store.setup("correct horse", "correct horse")
    assert store.verify("correct horse") is True
    assert store.verify("wrong") is False
    body = (tmp_path / "auth.json").read_text(encoding="utf-8")
    assert "correct horse" not in body
    assert set(json.loads(body)) == {"version", "salt", "n", "r", "p", "dklen", "verifier"}
```

Cover first-run setup, confirmation mismatch, empty password, atomic file
replacement, corrupt verifier fail-closed, one controller, viewer, explicit
Take Control after release, no implicit takeover, no idle timeout, manual lock,
and password required after every close/reopen.

- [ ] **Step 2: Run the tests and verify RED**

Run: `uv run --locked python -m pytest tests/platform/tui/test_auth.py -q`

Expected: FAIL because auth is absent.

- [ ] **Step 3: Implement scrypt and constant-time verification**

Use `os.urandom(16)`, `hashlib.scrypt`, `hmac.compare_digest`, Base64 for binary
fields, `tempfile.mkstemp`, `fsync`, and `os.replace`. Reject passwords above
1,024 UTF-8 bytes. Keep lease state in gateway memory only.

- [ ] **Step 4: Run the tests and verify GREEN**

Run: `uv run --locked python -m pytest tests/platform/tui/test_auth.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat(tui): protect console access and ownership`

### Task 5: Create the current-user Windows named pipe

**Files:**
- Create: `vesper/platform/tui/pipe_security.py`
- Create: `vesper/platform/tui/pipe_server.py`
- Create: `tests/platform/tui/test_pipe_security.py`
- Create: `tests/platform/tui/test_pipe_server.py`

**Interfaces:**
- Produces: `current_logon_sid() -> str` from the token group carrying `SE_GROUP_LOGON_ID`.
- Produces: `pipe_name(logon_sid: str) -> str`.
- Produces: `current_user_security_attributes() -> pywintypes.SECURITY_ATTRIBUTES`.
- Produces: `WindowsPipeServer.serve(handler, stop_event) -> None`.

- [ ] **Step 1: Write SID, DACL, isolation, and duplex tests**

Test the SID hash deterministically. On Windows, inspect the created pipe DACL
with `GetSecurityInfo` and assert the logon SID has data read/write, attribute,
extended-attribute, synchronization, and read-control rights but not
`FILE_CREATE_PIPE_INSTANCE`. Everyone, Anonymous, and Network must have no
allowed access. Connect a same-user client and round-trip two framed messages.
Starting a second first-instance server must fail.

- [ ] **Step 2: Run the tests and verify RED**

Run: `uv run --locked python -m pytest tests/platform/tui/test_pipe_security.py tests/platform/tui/test_pipe_server.py -q`

Expected: FAIL because pipe support is absent.

- [ ] **Step 3: Implement explicit Windows security**

Use `OpenProcessToken`, `GetTokenInformation(TokenGroups)`, and
`SE_GROUP_LOGON_ID` to select the logon SID. Build a protected DACL granting
that SID `FILE_READ_DATA`, `FILE_WRITE_DATA`, `FILE_READ_ATTRIBUTES`,
`FILE_WRITE_ATTRIBUTES`, `FILE_READ_EA`, `FILE_WRITE_EA`, `READ_CONTROL`, and
`SYNCHRONIZE`. Do not grant `FILE_APPEND_DATA`, which maps to pipe-instance
creation. Do not pass `None` security attributes. Use `CreateNamedPipe` with
duplex byte mode, first-instance protection, four instances, and 1 MiB
input/output buffers. Each accepted connection gets one worker thread; all V20
calls remain outside those transport threads.

- [ ] **Step 4: Run the Windows integration tests**

Run: `uv run --locked python -m pytest tests/platform/tui/test_pipe_security.py tests/platform/tui/test_pipe_server.py -q`

Expected: PASS with no remaining pipe handle.

- [ ] **Step 5: Commit**

Commit: `feat(tui): secure the local Windows pipe`

### Task 6: Coordinate gateway sessions

**Files:**
- Create: `vesper/platform/tui/gateway.py`
- Create: `vesper/platform/tui/cli.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `tests/platform/tui/test_gateway.py`

**Interfaces:**
- Produces script: `vesper-tui-gateway`.
- Produces: `Gateway.handle(client_id: str, envelope: WireEnvelope) -> tuple[WireEnvelope, ...]`.
- Produces: `Gateway.snapshot() -> ShellSnapshot`.
- Emits monotonically increasing server sequence and state version.

- [ ] **Step 1: Write the session state-machine tests**

Assert this order: `client-hello -> server-hello -> auth-setup or auth-unlock ->
auth-result -> snapshot-request -> snapshot`. Reject snapshot or command before
unlock. Assert a viewer receives the same snapshot but cannot send commands.
Assert ping works while locked and does not reveal state.

- [ ] **Step 2: Run the gateway tests and verify RED**

Run: `uv run --locked python -m pytest tests/platform/tui/test_gateway.py -q`

Expected: FAIL because the gateway is absent.

- [ ] **Step 3: Implement a control-only gateway**

The phase-1 snapshot sets mode `stopped`, all data values unavailable, and every
V20 action capability disabled with reason `Phase 1 provides the secure console
shell only.` The serving CLI accepts only `--state-root`, `--pipe-name`, and
`--parent-pid`. An exclusive `--print-pipe-name` mode prints the current logon
SID-derived pipe name and exits before opening state. It never constructs
`TradingEngine` or `LocalPlatformService`. It exits after the parent is gone and
no clients remain for 30 seconds.

- [ ] **Step 4: Run gateway and dependency tests**

Run: `uv run --locked python -m pytest tests/platform/tui tests/platform/test_dependencies.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat(tui): serve locked console sessions`

### Task 7: Build the Rust transport and gateway launcher

**Files:**
- Create: `TUI testing/ratatui-console/Cargo.toml`
- Create: `TUI testing/ratatui-console/Cargo.lock`
- Create: `TUI testing/ratatui-console/src/lib.rs`
- Create: `TUI testing/ratatui-console/src/contract.rs`
- Create: `TUI testing/ratatui-console/src/transport.rs`
- Create: `TUI testing/ratatui-console/src/launcher.rs`
- Create: `TUI testing/ratatui-console/tests/contract.rs`
- Create: `TUI testing/ratatui-console/tests/transport.rs`

**Interfaces:**
- Produces: `Envelope`, `MessageType`, `ShellSnapshot`, and matching Serde types.
- Produces: `PipeTransport::connect(name, timeout)`, `send`, and `recv`.
- Produces: `GatewayLauncher::connect_or_start(repo_root) -> PipeTransport`.

- [ ] **Step 1: Create the manifest and failing cross-language fixture tests**

Pin:

```toml
[package]
name = "vesper-ratatui-console"
version = "0.1.0"
edition = "2024"
rust-version = "1.97"

[dependencies]
crossterm = "=0.29.0"
ratatui = { version = "=0.30.2", default-features = false, features = ["crossterm_0_29", "layout-cache"] }
serde = { version = "=1.0.229", features = ["derive"] }
serde_json = "=1.0.151"
tokio = { version = "=1.53.1", features = ["io-util", "macros", "net", "process", "rt-multi-thread", "sync", "time"] }
windows-sys = { version = "=0.61.2", features = ["Win32_Foundation"] }

[dev-dependencies]
insta = "=1.48.0"
```

Rust tests load JSON emitted by Python contract fixtures and assert unknown
fields, wrong schema, negative versions, and oversized frames are rejected.

- [ ] **Step 2: Run Cargo tests and verify RED**

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --locked`

Expected: FAIL because modules are absent.

- [ ] **Step 3: Implement retrying pipe transport and direct launch**

Use Tokio `ClientOptions::new().open`. Retry `ERROR_PIPE_BUSY` every 50 ms for
three seconds. First run `uv run --locked vesper-tui-gateway
--print-pipe-name` without a shell, cap stdout at 256 bytes, and validate the
returned pipe-name prefix. If that pipe is not found, launch this exact direct
argv without a shell:

```rust
fn start_gateway(
    repo_root: &Path,
    state_root: &Path,
    pipe_name: &str,
) -> std::io::Result<tokio::process::Child> {
    let parent_pid = std::process::id().to_string();
    tokio::process::Command::new("uv")
        .current_dir(repo_root)
        .args(["run", "--locked", "vesper-tui-gateway", "--state-root"])
        .arg(state_root)
        .args(["--pipe-name", pipe_name, "--parent-pid", &parent_pid])
        .spawn()
}
```

Capture no password in argv or environment. Keep the child handle only when
this TUI started it. Framing must match Python byte-for-byte.

- [ ] **Step 4: Run format, lint, and transport tests**

Run: `cargo fmt --manifest-path "TUI testing/ratatui-console/Cargo.toml" -- --check`

Run: `cargo clippy --manifest-path "TUI testing/ratatui-console/Cargo.toml" --all-targets --locked -- -D warnings`

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --locked`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat(tui): connect Ratatui to the gateway`

### Task 8: Build locked state and fixed navigation

**Files:**
- Create: `TUI testing/ratatui-console/src/state.rs`
- Create: `TUI testing/ratatui-console/src/app.rs`
- Create: `TUI testing/ratatui-console/src/input.rs`
- Create: `TUI testing/ratatui-console/src/main.rs`
- Create: `TUI testing/ratatui-console/tests/state.rs`
- Create: `TUI testing/ratatui-console/tests/input.rs`

**Interfaces:**
- Produces enum `Screen`: `Impact`, `Portfolio`, `Orders`, `Agents`, `ModelsRegime`, `Timeline`, `RiskApprovals`, `DataEvidence`, `Memory`, `System`.
- Produces enum `AccessState`: `Locked`, `FirstRun`, `Controller`, `Viewer`.
- Produces `AppState::reduce(envelope)` and `AppState::handle(InputEvent)`.

- [ ] **Step 1: Write reducer and input tests**

```rust
#[test]
fn number_keys_select_all_ten_screens_after_unlock() {
    let mut state = controller_state();
    for (key, expected) in [('1', Screen::Impact), ('9', Screen::Memory), ('0', Screen::System)] {
        state.handle(InputEvent::Char(key));
        assert_eq!(state.screen, expected);
    }
}
```

Cover locked input isolation, masked password entry, first-run confirmation,
`o`, `Esc`, `/`, `f`, `:`, `i`, `Enter`, `?`, `q`, viewer Take Control, state
version replacement, sequence gap resnapshot, protocol error lockout, manual
Lock TUI, and remaining unlocked across an arbitrarily long fake-clock idle.

- [ ] **Step 2: Run tests and verify RED**

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test state --test input --locked`

Expected: FAIL because app state is absent.

- [ ] **Step 3: Implement one event loop and safe terminal restore**

Use `ratatui::init()` and guarantee `ratatui::restore()` through a guard. Poll
Crossterm every 50 ms, process only key-press events, enable mouse capture after
unlock, and redraw only when input or state changes. `q` sends no runtime
command.

- [ ] **Step 4: Run focused tests**

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test state --test input --locked`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat(tui): add locked console navigation`

### Task 9: Render the accessible fixed shell

**Files:**
- Create: `TUI testing/ratatui-console/src/layout.rs`
- Create: `TUI testing/ratatui-console/src/theme.rs`
- Create: `TUI testing/ratatui-console/src/ui.rs`
- Create: `TUI testing/ratatui-console/tests/snapshots.rs`
- Create: `TUI testing/ratatui-console/tests/snapshots/`

**Interfaces:**
- Produces themes `WarmWhite` and `Charcoal`.
- Produces display modes `Compact`, `Standard`, and `LargeText`.
- Produces wide fixed grid and narrow one-panel focus layout.

- [ ] **Step 1: Write buffer and accessibility snapshot tests**

Use `TestBackend` at `160x48`, `120x36`, `100x30`, and `80x24`. Snapshot locked,
first-run, controller, viewer, urgent, and resolved states in both themes and all
three text modes. Assert every colored state also includes a word or symbol.

- [ ] **Step 2: Run snapshots and verify RED**

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test snapshots --locked`

Expected: FAIL because layout and UI are absent.

- [ ] **Step 3: Implement the six-part shell**

Render header, permanent navigation, persistent alerts, screen body, agent
input, and key/status footer in that order. Use red urgent, yellow waiting, blue
active, green healthy/resolved, warm white text, and charcoal surfaces. Do not
use blink or animation. Persist theme, text mode, visible columns, and panel
sizes to `%LOCALAPPDATA%\Vesper\v20\tui\preferences.json` through atomic
replacement.

- [ ] **Step 4: Inspect and approve snapshots**

Run: `$env:INSTA_UPDATE='new'; cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test snapshots --locked`

Inspect every `.snap`, rename `.snap.new` only after checking labels and
alignment, clear `INSTA_UPDATE`, then rerun the test normally.

- [ ] **Step 5: Run the complete phase gate**

Run: `uv run --locked python -m pytest tests/platform/tui tests/platform/test_dependencies.py -q`

Run: `cargo fmt --manifest-path "TUI testing/ratatui-console/Cargo.toml" -- --check`

Run: `cargo clippy --manifest-path "TUI testing/ratatui-console/Cargo.toml" --all-targets --locked -- -D warnings`

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --locked`

Expected: all checks PASS; opening and closing the shell leaves V20 stopped.

- [ ] **Step 6: Commit**

Commit: `feat(tui): render the accessible console shell`

## Phase acceptance

- Password setup and unlock hide all dashboard state until success.
- A second TUI is a viewer until Take Control succeeds.
- The pipe DACL admits only the current logon session.
- No TCP listener exists.
- All ten screen keys work in wide and narrow terminals.
- Themes and text modes are readable and persistent.
- Every V20 action is visibly disabled with one plain reason.
- Closing the TUI leaves V20 unchanged.
- Python and Rust checks pass from clean build/test state.
