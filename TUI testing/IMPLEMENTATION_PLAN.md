# V20 Textual vs Ratatui Bakeoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build two matching, read-only V20 terminal dashboards and choose a framework from fresh tests and measurements.

**Architecture:** The Python/Textual and Rust/Ratatui apps each have a typed JSON layer, a fixed V20 command adapter, one refresh worker, and matching screens. Shared JSON files define labels, colors, fixtures, and benchmark settings. A PowerShell runner checks both apps and writes comparable result files.

**Tech Stack:** Python 3.11.15, uv 0.11.32, Textual 8.2.8, Rust 1.97.0, Ratatui 0.30.2, Crossterm 0.29.0, Tokio 1.53.1, PowerShell.

## Global Constraints

- Put every new or changed repository file under `TUI testing`.
- Do not change V20 source, settings, dependencies, state, runs, or protected data.
- Live calls use direct arguments: `uv run --locked vesper-agent --json <command>` from the V20 root.
- Allow only `active`, `approvals`, `knowledge-status`, `status`, `receipts`, and `evidence`.
- Require `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$` for run IDs and reject `.` and `..`.
- Never invoke a shell from either adapter.
- Stop each V20 command after five seconds and clean up its full process tree.
- Use a five-second live refresh interval. Never overlap refreshes; keep at most one extra request.
- First failure means `UNAVAILABLE`. A later failure means `STALE` and keeps the last good data.
- Use the same 80x24 and 120x36 screen sizes, 100/1,000/10,000-row fixtures, and 2 Hz/5 Hz benchmark loads.
- Pin direct framework dependencies and commit both lock files.
- Python runtime: `textual==8.2.8`. Python test stack: `pytest==8.4.2`, `pytest-asyncio==1.4.0`, `pytest-textual-snapshot==1.1.0`, `ruff==0.16.0`.
- Rust runtime: `ratatui==0.30.2`, `tokio==1.53.1`, `serde==1.0.229`, `serde_json==1.0.151`. Rust snapshot stack: `insta==1.48.0`.
- Keep benchmark output honest: command time is separate from parse, model, and render time.
- Use test-first changes and commit after each task passes.

---

## File Map

```text
TUI testing/
|-- DESIGN.md                         approved scope
|-- IMPLEMENTATION_PLAN.md            this plan
|-- README.md                         setup, launch, tests, results
|-- .gitignore                        local build and temporary files
|-- shared/
|   |-- contract.md                   exact JSON and failure rules
|   |-- ui-contract.json              shared copy, keys, colors, sizes
|   |-- benchmark-spec.json           shared loads and sample counts
|   `-- fixtures/
|       |-- active.json
|       |-- approvals.json
|       |-- knowledge-status.json
|       |-- status-run-001.json
|       |-- receipts-run-001.json
|       |-- evidence-run-001.json
|       `-- benchmark/active-{100,1000,10000}.json
|-- python-textual/
|   |-- pyproject.toml
|   |-- uv.lock
|   |-- src/v20_tui_textual/
|   |   |-- __init__.py
|   |   |-- cli.py
|   |   |-- models.py
|   |   |-- parsing.py
|   |   |-- adapter.py
|   |   |-- refresh.py
|   |   |-- widgets.py
|   |   |-- app.py
|   |   `-- benchmark.py
|   `-- tests/
|       |-- conftest.py
|       |-- snapshot_app.py
|       |-- test_models.py
|       |-- test_adapter.py
|       |-- test_refresh.py
|       |-- test_app.py
|       |-- test_snapshots.py
|       |-- test_benchmark.py
|       `-- test_live_smoke.py
|-- rust-ratatui/
|   |-- Cargo.toml
|   |-- Cargo.lock
|   |-- src/
|   |   |-- lib.rs
|   |   |-- main.rs
|   |   |-- model.rs
|   |   |-- parsing.rs
|   |   |-- adapter.rs
|   |   |-- refresh.rs
|   |   |-- app.rs
|   |   |-- ui.rs
|   |   `-- bin/bench.rs
|   `-- tests/
|       |-- contract.rs
|       |-- adapter.rs
|       |-- refresh.rs
|       |-- ui.rs
|       `-- live_smoke.rs
|-- scripts/
|   |-- generate_fixtures.py
|   |-- test_generate_fixtures.py
|   |-- verify_parity.py
|   |-- test_verify_parity.py
|   |-- run-tests.ps1
|   `-- run-benchmarks.ps1
`-- results/
    |-- textual.json
    |-- ratatui.json
    |-- gates.json
    `-- COMPARISON.md
```

## Shared Interfaces

Both apps use these names and meanings:

```text
Freshness = LOADING | FRESH | STALE | UNAVAILABLE
CommandName = active | approvals | knowledge-status | status | receipts | evidence
OverviewSnapshot = active runs + pending approvals + knowledge counts + command timings
RunDetail = status payload + receipts payload + evidence payload
CommandFailure = timeout | exit | json | schema | unavailable | cancelled
```

Both result files use this top-level JSON shape:

```json
{
  "schema_version": 1,
  "implementation": "textual-or-ratatui",
  "environment": {},
  "inputs": {},
  "measurements": [],
  "gates": {},
  "artifacts": {}
}
```

---

### Task 1: Shared contracts and deterministic fixtures

**Files:**
- Create: `TUI testing/.gitignore`
- Create: `TUI testing/shared/contract.md`
- Create: `TUI testing/shared/ui-contract.json`
- Create: `TUI testing/shared/benchmark-spec.json`
- Create: `TUI testing/scripts/generate_fixtures.py`
- Create: `TUI testing/scripts/test_generate_fixtures.py`
- Create: `TUI testing/shared/fixtures/*.json`

**Interfaces:**
- Produces: one byte-identical fixture set used by both apps.
- Produces: `build_active_payload(count: int) -> dict[str, object]`.
- Produces: screen names, keys, labels, colors, breakpoint, and benchmark settings.

- [ ] **Step 1: Write the failing generator test**

```python
import json
import unittest
from pathlib import Path

from generate_fixtures import build_active_payload


class FixtureTests(unittest.TestCase):
    def test_requested_row_count_and_stable_ids(self) -> None:
        payload = build_active_payload(100)
        self.assertEqual(len(payload["active"]), 100)
        self.assertEqual(payload["active"][0]["run_id"], "run-000001")
        self.assertEqual(payload["active"][-1]["run_id"], "run-000100")

    def test_benchmark_spec_has_required_loads(self) -> None:
        root = Path(__file__).resolve().parents[1]
        spec = json.loads((root / "shared/benchmark-spec.json").read_text("utf-8"))
        self.assertEqual(spec["row_counts"], [100, 1000, 10000])
        self.assertEqual(spec["update_rates_hz"], {"normal": 2, "stress": 5})
```

- [ ] **Step 2: Run the test and confirm the missing module/file failure**

Run: `python "TUI testing/scripts/test_generate_fixtures.py" -v`

Expected: FAIL because `generate_fixtures` or the shared JSON files do not exist.

- [ ] **Step 3: Add the shared JSON and fixture generator**

Use these fixed values in `ui-contract.json`:

```json
{
  "title": "V20 Console",
  "mode": "LIVE / READ-ONLY",
  "screens": ["Overview", "Runs", "Approvals"],
  "keys": {"1": "Overview", "2": "Runs", "3": "Approvals", "r": "Refresh", "space": "Pause", "/": "Filter", "t": "Theme", "?": "Help", "q": "Quit"},
  "breakpoint_columns": 100,
  "terminal_sizes": [[80, 24], [120, 36]],
  "colors": {"accent": "#4DA3FF", "fresh": "#4FD17B", "stale": "#FFB454", "unavailable": "#FF5D73", "dark_bg": "#10151C", "light_bg": "#F4F7FA"}
}
```

Use these generator rules:

```python
def build_active_payload(count: int) -> dict[str, object]:
    return {
        "active": [
            {
                "run_id": f"run-{index:06d}",
                "task_id": f"task-{index:06d}",
                "status": ("running" if index % 2 else "validation"),
                "repository_revision": f"rev-{index:06d}",
                "created_at": "2026-08-01T12:00:00+00:00",
                "active_execution": None,
            }
            for index in range(1, count + 1)
        ]
    }
```

Write JSON with UTF-8, sorted keys, compact separators, and one final newline.

- [ ] **Step 4: Generate and verify all fixtures**

Run: `python "TUI testing/scripts/generate_fixtures.py"`

Run: `python "TUI testing/scripts/test_generate_fixtures.py" -v`

Expected: PASS; benchmark files contain exactly 100, 1,000, and 10,000 rows.

- [ ] **Step 5: Check formatting and commit**

Run: `git diff --check -- "TUI testing"`

Commit: `test: add shared TUI contracts and fixtures`

---

### Task 2: Python typed models and JSON parsing

**Files:**
- Create: `TUI testing/python-textual/pyproject.toml`
- Create: `TUI testing/python-textual/uv.lock`
- Create: `TUI testing/python-textual/src/v20_tui_textual/__init__.py`
- Create: `TUI testing/python-textual/src/v20_tui_textual/models.py`
- Create: `TUI testing/python-textual/src/v20_tui_textual/parsing.py`
- Create: `TUI testing/python-textual/tests/conftest.py`
- Create: `TUI testing/python-textual/tests/test_models.py`

**Interfaces:**
- Produces: immutable `ActiveRunSummary`, `ApprovalSummary`, `KnowledgeCounts`, `OverviewSnapshot`, `RunDetail`, and `CommandFailure` dataclasses.
- Produces: `parse_active`, `parse_approvals`, `parse_knowledge`, and `parse_run_detail`.

- [ ] **Step 1: Add project metadata and failing parser tests**

Use this package boundary:

```toml
[build-system]
requires = ["uv_build>=0.11.32,<0.12"]
build-backend = "uv_build"

[project]
name = "v20-tui-textual"
version = "0.1.0"
requires-python = ">=3.11,<3.12"
dependencies = ["textual==8.2.8"]

[project.scripts]
v20-tui-textual = "v20_tui_textual.cli:main"
v20-tui-textual-bench = "v20_tui_textual.benchmark:main"

[dependency-groups]
dev = ["pytest==8.4.2", "pytest-asyncio==1.4.0", "pytest-textual-snapshot==1.1.0", "ruff==0.16.0"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = ["live: invokes only approved read-only V20 CLI commands"]
```

Write tests that assert valid fixtures parse, missing top-level keys fail, a row
without `run_id` fails, optional fields may be absent, and unknown fields remain
available through `raw`.

- [ ] **Step 2: Lock dependencies and confirm tests fail**

Run: `uv lock --project "TUI testing/python-textual"`

Run: `uv run --project "TUI testing/python-textual" --locked pytest "TUI testing/python-textual/tests/test_models.py" -q`

Expected: FAIL because model and parser functions do not exist.

- [ ] **Step 3: Add immutable models and strict outer-shape parsing**

Use these signatures:

```python
@dataclass(frozen=True, slots=True)
class ActiveRunSummary:
    run_id: str
    status: str
    task_id: str | None
    repository_revision: str | None
    created_at: str | None
    active_execution: Mapping[str, object] | None
    raw: Mapping[str, object]

def parse_active(payload: object) -> tuple[ActiveRunSummary, ...]: ...
def parse_approvals(payload: object) -> tuple[ApprovalSummary, ...]: ...
def parse_knowledge(payload: object) -> KnowledgeCounts: ...
def parse_run_detail(status: object, receipts: object, evidence: object) -> RunDetail: ...
```

Reject a wrong top-level type, missing required collection, wrong collection
type, missing/invalid run ID, non-integer knowledge count, or mismatched detail
run IDs. Preserve unrecognized nested fields only in `raw`.

- [ ] **Step 4: Run focused tests**

Run: `uv run --project "TUI testing/python-textual" --locked pytest "TUI testing/python-textual/tests/test_models.py" -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat: add Textual data contracts`

---

### Task 3: Python fixed command adapter and process cleanup

**Files:**
- Create: `TUI testing/python-textual/src/v20_tui_textual/adapter.py`
- Create: `TUI testing/python-textual/tests/test_adapter.py`
- Create: `TUI testing/python-textual/tests/process_tree_fixture.py`

**Interfaces:**
- Produces: `validate_run_id(value: str) -> str`.
- Produces: `ReadCommand` enum with exactly six values.
- Produces: `V20CliAdapter.fetch(command, run_id=None) -> CommandResult`.
- Produces: `V20CliAdapter.close() -> Awaitable[None]`.

- [ ] **Step 1: Write failing allowlist, failure, timeout, and cleanup tests**

```python
def test_build_argv_is_fixed_and_shell_free(repo_root: Path) -> None:
    adapter = V20CliAdapter(repo_root, uv_path="uv")
    assert adapter.argv(ReadCommand.ACTIVE) == (
        "uv", "run", "--locked", "vesper-agent", "--json", "active"
    )

@pytest.mark.parametrize("value", ["", ".", "..", "a/b", "a b", "x" * 129])
def test_run_id_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(ValueError):
        validate_run_id(value)
```

Also test nonzero exit before JSON parsing, bad JSON, bad schema, bounded stderr,
five-second timeout through an injected short timeout, cancellation, and parent
plus grandchild removal on Windows.

- [ ] **Step 2: Run tests and confirm failure**

Run: `uv run --project "TUI testing/python-textual" --locked pytest "TUI testing/python-textual/tests/test_adapter.py" -q`

Expected: FAIL because the adapter does not exist.

- [ ] **Step 3: Implement direct process execution**

Use `asyncio.create_subprocess_exec` with `stdin=DEVNULL`, captured stdout and
stderr, `cwd=v20_root`, and `CREATE_NEW_PROCESS_GROUP` on Windows. Track each
owned PID. Use `asyncio.wait_for(proc.communicate(), timeout=5.0)`.

Check results in this order:

```text
spawn error -> timeout/cancel -> nonzero exit -> JSON decode -> schema parse
```

On timeout, cancellation, or close: send `CTRL_BREAK_EVENT`, wait 250 ms, then
run `%SystemRoot%\System32\taskkill.exe /PID <pid> /T /F` and await both
processes. Never show raw stderr; keep a sanitized summary of at most 240 chars.

- [ ] **Step 4: Run focused and Windows process-tree tests**

Run: `uv run --project "TUI testing/python-textual" --locked pytest "TUI testing/python-textual/tests/test_adapter.py" -q`

Expected: PASS and no fixture parent or grandchild remains.

- [ ] **Step 5: Commit**

Commit: `feat: add safe Textual V20 adapter`

---

### Task 4: Python refresh controller

**Files:**
- Create: `TUI testing/python-textual/src/v20_tui_textual/refresh.py`
- Create: `TUI testing/python-textual/tests/test_refresh.py`

**Interfaces:**
- Consumes: `V20CliAdapter` and typed parser functions.
- Produces: `SnapshotState(snapshot, freshness, fetched_at, error)`.
- Produces: `RefreshCoordinator.request()`, `set_paused()`, and `close()`.

- [ ] **Step 1: Write failing state and concurrency tests**

Use a fake source with two `asyncio.Event` barriers. Assert:

```python
await coordinator.request()
assert coordinator.state.freshness is Freshness.FRESH

# Three requests during one blocked fetch produce one active and one queued fetch.
assert source.max_in_flight == 1
assert source.call_count == 2
```

Also assert first failure is unavailable, later failure retains the exact last
snapshot as stale, success replaces the snapshot in one assignment, pause stops
timer requests, and close cancels owned work.

- [ ] **Step 2: Run tests and confirm failure**

Run: `uv run --project "TUI testing/python-textual" --locked pytest "TUI testing/python-textual/tests/test_refresh.py" -q`

Expected: FAIL because the controller does not exist.

- [ ] **Step 3: Implement one worker plus one queued bit**

Use this public state:

```python
class Freshness(StrEnum):
    LOADING = "LOADING"
    FRESH = "FRESH"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"

@dataclass(frozen=True, slots=True)
class SnapshotState:
    snapshot: OverviewSnapshot | None
    freshness: Freshness
    fetched_at: float | None
    error: CommandFailure | None
```

Protect start/queue decisions with one lock. Do not hold the lock during I/O.
After a fetch ends, run once more only when the queued bit is set.

- [ ] **Step 4: Run focused tests**

Run: `uv run --project "TUI testing/python-textual" --locked pytest "TUI testing/python-textual/tests/test_refresh.py" -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat: add Textual refresh state machine`

---

### Task 5: Python matched dashboard shell

**Files:**
- Create: `TUI testing/python-textual/src/v20_tui_textual/widgets.py`
- Create: `TUI testing/python-textual/src/v20_tui_textual/app.py`
- Create: `TUI testing/python-textual/src/v20_tui_textual/cli.py`
- Create: `TUI testing/python-textual/tests/test_app.py`

**Interfaces:**
- Consumes: `SnapshotState`, `RunDetail`, and `ui-contract.json` values.
- Produces: `V20Console(App[None])` with Overview, Runs, and Approvals views.
- Produces: CLI flags `--repo-root`, `--fixture-root`, and `--no-auto-refresh`.

- [ ] **Step 1: Write failing Pilot interaction tests**

```python
async def test_navigation_filter_theme_and_pause(fixture_source) -> None:
    app = V20Console(fixture_source, auto_refresh=False)
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.press("2")
        assert app.current_view == "runs"
        await pilot.press("/")
        assert app.query_one("#filter").has_focus
        await pilot.press("t")
        assert app.theme_name == "light"
        await pilot.press("space")
        assert app.paused is True
```

Add tests for all three screens, empty/loading/fresh/stale/unavailable states,
run lookup, detail tabs, sorting, table selection, help, mouse row selection,
80x24/120x36 layouts, and `q` cleanup.

- [ ] **Step 2: Run tests and confirm failure**

Run: `uv run --project "TUI testing/python-textual" --locked pytest "TUI testing/python-textual/tests/test_app.py" -q`

Expected: FAIL because the app and widgets do not exist.

- [ ] **Step 3: Build the three-screen app**

Use:

- `ContentSwitcher(initial="overview")` for screen changes;
- `DataTable(cursor_type="row", zebra_stripes=True)` for runs and approvals;
- `TabbedContent` with State, Receipts, Evidence, and Raw JSON tabs;
- `HORIZONTAL_BREAKPOINTS = [(0, "-narrow"), (100, "-wide")]`;
- `Sparkline` for recent command and refresh times;
- a five-second `Timer` for automatic refresh;
- a non-exclusive Textual worker that calls the refresh controller;
- built-in dark/light themes with the shared accent/status colors;
- a modal help screen listing only the shared keys.

Keep the matching labels, keys, and colors in a small typed constants module so
the installed wheel does not need the source tree. Task 13 compares those
constants with `ui-contract.json`.

Do not register a command palette action or binding for any write operation.

- [ ] **Step 4: Run behavior tests at both sizes**

Run: `uv run --project "TUI testing/python-textual" --locked pytest "TUI testing/python-textual/tests/test_app.py" -q`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat: build matched Textual dashboard`

---

### Task 6: Python snapshots and live smoke boundary

**Files:**
- Create: `TUI testing/python-textual/tests/snapshot_app.py`
- Create: `TUI testing/python-textual/tests/test_snapshots.py`
- Create: `TUI testing/python-textual/tests/test_live_smoke.py`
- Create: `TUI testing/python-textual/tests/snapshots/`

**Interfaces:**
- Produces: fixed wide/narrow, dark/light, stale, and unavailable SVG snapshots.
- Produces: opt-in live tests that call only three summary commands.

- [ ] **Step 1: Write snapshot and live allowlist tests**

```python
def test_wide_overview(snap_compare) -> None:
    assert snap_compare("snapshot_app.py", terminal_size=(120, 36))

@pytest.mark.live
async def test_live_summary_commands(v20_repo_root: Path) -> None:
    adapter = V20CliAdapter(v20_repo_root)
    results = [await adapter.fetch(command) for command in SUMMARY_COMMANDS]
    assert all(result.ok for result in results)
```

Require `V20_REPO_ROOT` for live tests. Default test runs exclude the `live`
marker. The summary set is exactly active, approvals, and knowledge-status.

- [ ] **Step 2: Run one snapshot without update and confirm it has no baseline**

Run: `uv run --project "TUI testing/python-textual" --locked pytest "TUI testing/python-textual/tests/test_snapshots.py::test_wide_overview" -q`

Expected: FAIL because no approved SVG exists.

- [ ] **Step 3: Create and inspect the fixed snapshots**

Run: `uv run --project "TUI testing/python-textual" --locked pytest "TUI testing/python-textual/tests/test_snapshots.py" --snapshot-update -q`

Open the generated SVGs as files and confirm titles, status labels, colors,
tables, details, and help are readable. Then rerun without `--snapshot-update`.

- [ ] **Step 4: Run the live smoke test separately**

Run from PowerShell with `V20_REPO_ROOT` set to the current repository, then:

`uv run --project "TUI testing/python-textual" --locked pytest "TUI testing/python-textual/tests/test_live_smoke.py" -m live -q`

Expected: PASS with no run-changing command.

- [ ] **Step 5: Commit**

Commit: `test: verify Textual screens and live reads`

---

### Task 7: Python benchmark and package

**Files:**
- Create: `TUI testing/python-textual/src/v20_tui_textual/benchmark.py`
- Create: `TUI testing/python-textual/tests/test_benchmark.py`

**Interfaces:**
- Produces: `v20-tui-textual-bench --spec <path> --output <path>`.
- Produces: `results/textual-internal.json` matching the shared result shape.

- [ ] **Step 1: Write failing benchmark result tests**

Assert that a two-iteration test run records the spec hash, fixture hash, row
count, terminal size, sample count, median, p95, and separate parse/model/UI
times. Reject zero samples, missing fixtures, and an output path outside the
given result root.

- [ ] **Step 2: Run tests and confirm failure**

Run: `uv run --project "TUI testing/python-textual" --locked pytest "TUI testing/python-textual/tests/test_benchmark.py" -q`

Expected: FAIL because the benchmark entrypoint does not exist.

- [ ] **Step 3: Add deterministic measurements**

Use `perf_counter_ns`, `statistics.median`, and this nearest-rank p95 rule:

```python
def p95(samples: list[int]) -> int:
    ordered = sorted(samples)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]
```

Use `run_test(size=(width, height))`, apply one typed snapshot, and wait for
`pilot.pause()` before ending the UI sample. Run the shared warmups first. Test
2 Hz and 5 Hz update loops and record missed updates plus maximum input delay.

- [ ] **Step 4: Run tests and build the wheel**

Run: `uv run --project "TUI testing/python-textual" --locked pytest "TUI testing/python-textual/tests" -m "not live" -q`

Run: `uv run --project "TUI testing/python-textual" --locked ruff check "TUI testing/python-textual/src" "TUI testing/python-textual/tests"`

Run: `uv build --project "TUI testing/python-textual" --out-dir "TUI testing/python-textual/dist"`

Expected: all tests pass and wheel/sdist files exist.

- [ ] **Step 5: Commit**

Commit: `perf: add Textual benchmark and package`

---

### Task 8: Rust typed models and JSON parsing

**Files:**
- Create: `TUI testing/rust-ratatui/Cargo.toml`
- Create: `TUI testing/rust-ratatui/Cargo.lock`
- Create: `TUI testing/rust-ratatui/src/lib.rs`
- Create: `TUI testing/rust-ratatui/src/model.rs`
- Create: `TUI testing/rust-ratatui/src/parsing.rs`
- Create: `TUI testing/rust-ratatui/tests/contract.rs`

**Interfaces:**
- Produces: Rust types with the same names and field meanings as Task 2.
- Produces: `parse_active`, `parse_approvals`, `parse_knowledge`, and `parse_run_detail`.

- [ ] **Step 1: Add Cargo metadata and failing contract tests**

Use:

```toml
[package]
name = "v20-tui-ratatui"
version = "0.1.0"
edition = "2024"
rust-version = "1.97"

[dependencies]
ratatui = { version = "=0.30.2", default-features = false, features = ["crossterm_0_29", "layout-cache"] }
tokio = { version = "=1.53.1", features = ["macros", "rt", "process", "time", "sync", "io-util"] }
serde = { version = "=1.0.229", features = ["derive"] }
serde_json = "=1.0.151"

[dev-dependencies]
insta = "=1.48.0"

[[bin]]
name = "v20-tui"
path = "src/main.rs"

[[bin]]
name = "v20-tui-bench"
path = "src/bin/bench.rs"
```

Tests must read the same six contract fixtures as Python and assert the same
accept/reject behavior, optional fields, and raw unknown fields.

- [ ] **Step 2: Run tests and confirm failure**

Run: `cargo test --manifest-path "TUI testing/rust-ratatui/Cargo.toml" --test contract --locked`

Expected: FAIL because model and parser modules do not exist.

- [ ] **Step 3: Add Serde models and explicit outer checks**

Use `serde_json::Value` for raw data. Use custom parse functions returning
`Result<T, ContractError>` so wrong top-level values and missing fields map to
the same categories as Python.

```rust
pub fn parse_active(value: Value) -> Result<Vec<ActiveRunSummary>, ContractError>;
pub fn parse_approvals(value: Value) -> Result<Vec<ApprovalSummary>, ContractError>;
pub fn parse_knowledge(value: Value) -> Result<KnowledgeCounts, ContractError>;
pub fn parse_run_detail(status: Value, receipts: Value, evidence: Value)
    -> Result<RunDetail, ContractError>;
```

- [ ] **Step 4: Run focused tests and formatting**

Run: `cargo fmt --manifest-path "TUI testing/rust-ratatui/Cargo.toml" -- --check`

Run: `cargo test --manifest-path "TUI testing/rust-ratatui/Cargo.toml" --test contract --locked`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat: add Ratatui data contracts`

---

### Task 9: Rust fixed command adapter and process cleanup

**Files:**
- Create: `TUI testing/rust-ratatui/src/adapter.rs`
- Create: `TUI testing/rust-ratatui/tests/adapter.rs`
- Optional only when the real tree test proves direct cleanup insufficient: add Windows `windows-sys==0.61.2` target dependency.

**Interfaces:**
- Produces: `validate_run_id(&str) -> Result<&str, RunIdError>`.
- Produces: six-value `ReadCommand` enum.
- Produces: `V20CliAdapter::fetch` and `V20CliAdapter::close` async methods.

- [ ] **Step 1: Write failing allowlist, error, timeout, and tree tests**

Mirror every Task 3 case. Assert this exact active argv:

```rust
assert_eq!(
    adapter.argv(ReadCommand::Active, None)?,
    ["uv", "run", "--locked", "vesper-agent", "--json", "active"]
);
```

Use the same parent/grandchild fixture and prove both PIDs disappear.

- [ ] **Step 2: Run tests and confirm failure**

Run: `cargo test --manifest-path "TUI testing/rust-ratatui/Cargo.toml" --test adapter --locked`

Expected: FAIL because the adapter does not exist.

- [ ] **Step 3: Implement direct Tokio process execution**

Use `tokio::process::Command`, direct `.args`, `.current_dir(repo_root)`, piped
output, null stdin, and `.kill_on_drop(true)`. Read stdout/stderr concurrently
with a one-megabyte cap. Select between completion, cancellation, and five-second
timeout. Apply the same failure order and 240-character safe message limit as
Python.

- [ ] **Step 4: Prove full Windows cleanup and close the gap if needed**

Run the real parent/grandchild test. If Tokio kills only the immediate child,
add a Windows Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, assign the
spawned process, retain the handle, and close it on timeout or shutdown. Rerun
until neither PID survives.

Run: `cargo test --manifest-path "TUI testing/rust-ratatui/Cargo.toml" --test adapter --locked`

Expected: PASS with no surviving fixture process.

- [ ] **Step 5: Commit**

Commit: `feat: add safe Ratatui V20 adapter`

---

### Task 10: Rust refresh controller

**Files:**
- Create: `TUI testing/rust-ratatui/src/refresh.rs`
- Create: `TUI testing/rust-ratatui/tests/refresh.rs`

**Interfaces:**
- Consumes: typed adapter results.
- Produces: `SnapshotState` and `RefreshHandle`.
- Produces: `spawn_refresh_worker(source, interval) -> RefreshHandle`.

- [ ] **Step 1: Write failing state and concurrency tests**

Use a fake source with Tokio barriers. Assert fresh, unavailable, stale with the
same retained snapshot, one active fetch, one queued fetch, pause, automatic
interval, and awaited shutdown.

- [ ] **Step 2: Run tests and confirm failure**

Run: `cargo test --manifest-path "TUI testing/rust-ratatui/Cargo.toml" --test refresh --locked`

Expected: FAIL because the refresh module does not exist.

- [ ] **Step 3: Add one sequential worker**

Use `tokio::sync::mpsc::channel(1)` for refresh requests, a watch channel for
the latest immutable state, and a cancellation channel for shutdown. A full
request channel means one request is already waiting; discard further requests.
Never spawn one fetch per request.

- [ ] **Step 4: Run focused tests**

Run: `cargo test --manifest-path "TUI testing/rust-ratatui/Cargo.toml" --test refresh --locked`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat: add Ratatui refresh state machine`

---

### Task 11: Rust matched dashboard shell and interactions

**Files:**
- Create: `TUI testing/rust-ratatui/src/app.rs`
- Create: `TUI testing/rust-ratatui/src/ui.rs`
- Create: `TUI testing/rust-ratatui/src/main.rs`
- Create: `TUI testing/rust-ratatui/tests/ui.rs`

**Interfaces:**
- Consumes: shared UI values and `SnapshotState`.
- Produces: `AppState::handle_event`, `ui::render`, and the `v20-tui` binary.

- [ ] **Step 1: Write failing state-transition and buffer tests**

```rust
#[test]
fn keys_match_the_shared_contract() {
    let mut app = fixture_app();
    app.handle_key(key('2'));
    assert_eq!(app.screen, Screen::Runs);
    app.handle_key(key('t'));
    assert_eq!(app.theme, ThemeName::Light);
}

#[test]
fn wide_overview_contains_read_only_banner() {
    let backend = TestBackend::new(120, 36);
    let mut terminal = Terminal::new(backend).unwrap();
    terminal.draw(|frame| render(frame, &mut fixture_app())).unwrap();
    assert!(buffer_text(terminal.backend().buffer()).contains("LIVE / READ-ONLY"));
}
```

Cover screens, sort/filter, direct run lookup, detail tabs, selection, help,
mouse, pause, theme, 80x24/120x36 layouts, stale/unavailable, and quit cleanup.

- [ ] **Step 2: Run tests and confirm failure**

Run: `cargo test --manifest-path "TUI testing/rust-ratatui/Cargo.toml" --test ui --locked`

Expected: FAIL because app and UI modules do not exist.

- [ ] **Step 3: Build the event loop and matching render tree**

Use `ratatui::init()` and always call `ratatui::restore()`. Enable and disable
mouse capture. Poll Crossterm every 50 ms, handle only key presses, drain queued
events, read refresh state without blocking, and redraw after state or input
changes.

Use `Tabs`, stateful `Table`, `Sparkline`, `Paragraph`, and `Block`. At widths
below 100, put details below the table; otherwise put details to its right.
Define local dark/light `Theme` values from `ui-contract.json` colors.
Compile the matching labels, keys, and colors as typed constants so the release
executable is standalone. Task 13 compares them with `ui-contract.json`.

- [ ] **Step 4: Add and verify Insta snapshots**

Snapshot wide/narrow, dark/light, stale, and unavailable buffers with
`insta::assert_snapshot!`. Inspect new `.snap` files, accept only the intended
output, then rerun without update mode.

Run: `cargo test --manifest-path "TUI testing/rust-ratatui/Cargo.toml" --test ui --locked`

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat: build matched Ratatui dashboard`

---

### Task 12: Rust live smoke, benchmark, and package

**Files:**
- Create: `TUI testing/rust-ratatui/src/bin/bench.rs`
- Create: `TUI testing/rust-ratatui/tests/live_smoke.rs`
- Modify: `TUI testing/rust-ratatui/Cargo.toml`

**Interfaces:**
- Produces: `v20-tui-bench --spec <path> --output <path>`.
- Produces: `results/ratatui-internal.json` matching Task 7.

- [ ] **Step 1: Write failing benchmark and opt-in live tests**

Match Task 7 result assertions and Task 6 live command allowlist. Skip live
tests unless `V20_REPO_ROOT` is set.

- [ ] **Step 2: Run tests and confirm benchmark failure**

Run: `cargo test --manifest-path "TUI testing/rust-ratatui/Cargo.toml" --locked`

Expected: FAIL because the benchmark binary is missing.

- [ ] **Step 3: Add deterministic headless measurements**

Reuse production parsing, state updates, filtering, navigation, and `render`
with `TestBackend`. Use `Instant` and the same nearest-rank p95 rule. Record the
same names, units, row counts, sizes, warmups, iterations, 2 Hz/5 Hz results,
spec hash, and fixture hashes as Python.

- [ ] **Step 4: Run tests, live smoke, and release build**

Run: `cargo fmt --manifest-path "TUI testing/rust-ratatui/Cargo.toml" -- --check`

Run: `cargo clippy --manifest-path "TUI testing/rust-ratatui/Cargo.toml" --all-targets --locked -- -D warnings`

Run: `cargo test --manifest-path "TUI testing/rust-ratatui/Cargo.toml" --locked`

Run with `V20_REPO_ROOT` set: `cargo test --manifest-path "TUI testing/rust-ratatui/Cargo.toml" --test live_smoke --locked -- --ignored`

Run: `cargo build --manifest-path "TUI testing/rust-ratatui/Cargo.toml" --release --locked --bin v20-tui`

Expected: all checks pass and `v20-tui.exe` exists.

- [ ] **Step 5: Commit**

Commit: `perf: add Ratatui benchmark and package`

---

### Task 13: Cross-framework parity and benchmark runner

**Files:**
- Create: `TUI testing/scripts/verify_parity.py`
- Create: `TUI testing/scripts/test_verify_parity.py`
- Create: `TUI testing/scripts/run-tests.ps1`
- Create: `TUI testing/scripts/run-benchmarks.ps1`
- Create: `TUI testing/README.md`

**Interfaces:**
- Consumes: both lock files, test results, binaries, internal benchmark JSON, and shared contracts.
- Produces: `results/textual.json`, `results/ratatui.json`, and `results/gates.json`.

- [ ] **Step 1: Write failing parity/result validation tests**

Test that both implementations expose the same six commands, screens, keys,
labels, colors, sizes, fixtures, measurement names, and result schema. Test
that a missing gate, fixture hash mismatch, or result written outside `results`
fails with a nonzero exit.

- [ ] **Step 2: Run the tests and confirm failure**

Run: `python "TUI testing/scripts/test_verify_parity.py" -v`

Expected: FAIL because the verifier does not exist.

- [ ] **Step 3: Add the parity verifier and test runner**

`run-tests.ps1` must:

1. capture `git status --porcelain` outside `TUI testing`;
2. run generator tests and parity tests;
3. run Python lint and non-live tests;
4. run Rust fmt, Clippy, and non-live tests;
5. run both live smoke suites;
6. compare the outside status with the starting value;
7. write exact commands, exit codes, durations, and gate results.

Stop on the first failed command, but still write the failed gate receipt.

- [ ] **Step 4: Add the external benchmark runner**

`run-benchmarks.ps1` must run both internal benchmark binaries, then measure:

- cold installed-command start to first fixture frame;
- test, build, and install time;
- peak working set and CPU from `Get-Process` samples;
- Python installed environment and wheel size;
- Rust release executable size;
- direct dependency count and source line count.

Use at least three warmups and twenty measured samples from
`benchmark-spec.json`. Save all raw samples, not only summaries.

- [ ] **Step 5: Run verifier tests and commit**

Run: `python "TUI testing/scripts/test_verify_parity.py" -v`

Expected: PASS.

Commit: `test: add matched TUI verification runner`

---

### Task 14: Fresh verification, scoring, and recommendation

**Files:**
- Create: `TUI testing/results/textual.json`
- Create: `TUI testing/results/ratatui.json`
- Create: `TUI testing/results/gates.json`
- Create: `TUI testing/results/COMPARISON.md`
- Modify: `TUI testing/README.md`

**Interfaces:**
- Consumes: all test, live, package, and benchmark evidence.
- Produces: one evidence-backed decision with no preselected winner.

- [ ] **Step 1: Run the complete fresh test gate**

Run: `& "TUI testing/scripts/run-tests.ps1"`

Expected: every mandatory gate is recorded; any failure makes that framework
ineligible until repaired and rerun.

- [ ] **Step 2: Run the complete benchmark**

Run: `& "TUI testing/scripts/run-benchmarks.ps1"`

Expected: both final JSON files contain the same input hashes, sample counts,
measurement names, and environment facts.

- [ ] **Step 3: Inspect the apps and raw results**

Launch each app against shared fixtures, then against the approved live summary
commands. Check both terminal sizes, all keys, mouse selection, dark/light
themes, stale/unavailable messages, direct run lookup, and clean exit.

- [ ] **Step 4: Score only from evidence**

For each 1-5 score, cite exact result JSON keys or source files. Calculate:

```text
weighted total =
  integration score / 5 * 25
+ customization score / 5 * 25
+ performance score / 5 * 25
+ testability score / 5 * 15
+ packaging score / 5 * 10
```

A failed mandatory gate overrides the total. If both pass and totals differ by
less than 5 points, report the result as close and explain which V20 priority
breaks the tie. Do not hide a slower result, higher memory use, larger package,
or harder UI change.

- [ ] **Step 5: Write the final comparison and rerun scope checks**

`COMPARISON.md` must include environment, gate table, feature table, raw metric
table, five scored areas, limits, winner, backup choice, and the next smallest
production step.

Run: `git diff --check -- "TUI testing"`

Run: `git status --short -- "TUI testing"`

Verify the status outside `TUI testing` matches the captured starting status.

- [ ] **Step 6: Commit the evidence and report**

Commit: `docs: record V20 TUI bakeoff decision`

---

## Final Acceptance Check

- Both apps provide Overview, Runs, and Approvals with matching behavior.
- Both adapters expose only the six approved read-only commands.
- Timeout, stale, unavailable, queued refresh, and descendant cleanup tests pass.
- Python Pilot/SVG and Rust TestBackend/Insta checks pass at both sizes.
- Both opt-in live smoke suites pass against the same V20 checkout.
- Benchmark inputs and sample counts match exactly.
- Raw results, gate results, score reasons, and recommendation are committed.
- No tracked repository file outside `TUI testing` changed during implementation.
