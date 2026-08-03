# V20 Ratatui Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Populate all ten screens with truthful controller-owned snapshots, live events, search, drill-down, notes, and explicit stale or unavailable states.

**Architecture:** Python projection ports translate existing V20 stores into strict view models and one versioned `ConsoleSnapshot`. A SQLite event store under LocalAppData records TUI-visible events without becoming portfolio or broker truth. Rust reduces snapshots and ordered events, virtualizes large tables, and renders the approved layouts.

**Tech Stack:** Phase 1 stack plus Python SQLite, Windows read APIs from pywin32, Rust Ratatui stateful widgets, Serde, and Insta.

## Global Constraints

- Complete `2026-08-03-v20-ratatui-foundation.md` first.
- Read current V20 state through Python projection ports only.
- Do not construct `AlpacaBroker`, call a broker client, start `TradingEngine`, or start a scheduler.
- `vesper/data/massive/` and `vesper/data/model_research/` remain read-only and are not scanned by the TUI.
- A source with no controller-owned adapter returns `UNAVAILABLE` and a plain reason.
- A source that fails after one valid sample keeps that sample as `STALE` with age and error.
- Stream urgent alerts, approvals, agent events, orders, portfolio changes, and chats when a source supplies them.
- Poll visible system/market metrics every 1 second and slower sources every 5 seconds.
- Coalesce events for at most 50 milliseconds before one render.
- Table virtualization must keep at least 10,000 records responsive.
- Notes are Private or Shared with Agents. They are TUI context records only and
  never execute commands.
- All timestamps are stored in UTC and rendered in America/New_York.
- Run every pytest command with `TEMP` and `TMP` set to
  `C:\tmp\v20-tui-observability-temp`, `--basetemp
  C:\tmp\v20-tui-observability-pytest`, and `-o
  cache_dir=C:\tmp\v20-tui-observability-cache`.
- Use deterministic fixtures; no test accesses credentials, accounts, or live brokers.
- Use test-first changes and one Conventional Commit per task.

---

## File map

```text
vesper/platform/tui/
|-- views.py                       all ten screen view models
|-- ports.py                       read-only source protocols
|-- event_store.py                 ordered SQLite event history
|-- snapshot.py                    projection aggregation and freshness
|-- stream.py                      polling, diffing, and event coalescing
|-- search.py                      bounded cross-screen search
|-- notes.py                       private/shared context notes
`-- projections/
    |-- __init__.py
    |-- native_platform.py         runs, approvals, agents, journals, evidence
    |-- legacy_state.py            validated read of saved engine state only
    |-- repository.py              config/model/source-control read facts
    `-- windows_system.py          CPU/GPU/memory/disk/process read facts

tests/platform/tui/
|-- test_views.py
|-- test_event_store.py
|-- test_snapshot.py
|-- test_stream.py
|-- test_search.py
|-- test_notes.py
`-- projections/
    |-- test_native_platform.py
    |-- test_legacy_state.py
    |-- test_repository.py
    `-- test_windows_system.py

TUI testing/ratatui-console/src/
|-- reducer.rs
|-- virtual_table.rs
|-- search.rs
|-- detail.rs
|-- widgets/
|   |-- mod.rs
|   |-- status.rs
|   |-- cards.rs
|   |-- weights.rs
|   `-- timeline.rs
`-- screens/
    |-- mod.rs
    |-- impact.rs
    |-- portfolio.rs
    |-- orders.rs
    |-- agents.rs
    |-- models.rs
    |-- timeline.rs
    |-- risk.rs
    |-- data.rs
    |-- memory.rs
    `-- system.rs
```

### Task 1: Define the complete read-view contract

**Files:**
- Create: `vesper/platform/tui/views.py`
- Modify: `vesper/platform/tui/contracts.py`
- Create: `tests/platform/tui/test_views.py`
- Modify: `TUI testing/ratatui-console/src/contract.rs`
- Modify: `TUI testing/ratatui-console/tests/contract.rs`

**Interfaces:**
- Produces `ImpactView`, `PortfolioView`, `OrdersView`, `AgentsView`, `ModelsView`, `TimelineView`, `RiskView`, `DataView`, `MemoryView`, and `SystemView`.
- Produces one `ConsoleSnapshot` containing the shell plus all ten views.
- Every screen has `freshness`, `as_of`, `source`, and `error` fields.

- [ ] **Step 1: Write Python model and Rust fixture tests**

```python
def test_console_snapshot_requires_all_ten_views(full_snapshot_payload) -> None:
    snapshot = ConsoleSnapshot.model_validate(full_snapshot_payload)
    assert snapshot.portfolio.rows[0].symbol == "AAPL"
    payload = dict(full_snapshot_payload)
    payload.pop("orders")
    with pytest.raises(ValidationError):
        ConsoleSnapshot.model_validate(payload)
```

Rust must deserialize the same fixture and reject the same missing fields and
unknown fields.

- [ ] **Step 2: Run both contract suites and verify RED**

Run: `uv run --locked python -m pytest tests/platform/tui/test_views.py -q`

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test contract --locked`

Expected: FAIL because screen views are absent.

- [ ] **Step 3: Implement exact shared row types**

Use these core fields:

```python
class PortfolioRow(StrictModel):
    symbol: NonEmptyStr
    description: str | None
    asset_type: Literal["stock", "etf", "cash"]
    quantity: DecimalString
    price: DecimalString | None
    market_value: DecimalString | None
    current_weight: float
    proposed_weight: float | None
    approved_weight: float | None
    change_state: Literal["unchanged", "proposed", "approved", "executing", "reconciling"]
    confirmed_rank: int | None
    reconciliation: Literal["not-required", "pending", "matched", "mismatch", "unavailable"]


class AgentCard(StrictModel):
    work_id: NonEmptyStr
    agent: NonEmptyStr
    title: NonEmptyStr
    stage: Literal["backlog", "queued", "running", "waiting", "done", "failed"]
    priority: int
    urgent: bool
    elapsed_seconds: float | None
    model: str | None
    affected_areas: tuple[str, ...]


class TimelineRow(StrictModel):
    event_id: NonEmptyStr
    occurred_at: datetime
    impact: bool
    severity: Literal["info", "active", "waiting", "urgent", "resolved"]
    summary: NonEmptyStr
    agent_id: str | None
    symbol: str | None
    model_id: str | None
    approval_id: str | None
    order_id: str | None
    evidence_ids: tuple[str, ...]
```

Define `DecimalString` as a finite base-10 string with no exponent. Define
equally strict rows for orders, fills, model opinions, candidates, risk
limits, approvals, sources, evidence, memories, services, metrics, return
components, and alerts. Use decimal strings for broker quantities or money that
must round-trip exactly; use floats only for display metrics.

- [ ] **Step 4: Replace `ShellSnapshot` snapshot payload with `ConsoleSnapshot`**

Keep the phase-1 shell fields unchanged. The gateway emits one complete initial
snapshot and event payloads containing `entity_type`, `entity_id`, `operation`,
and the complete replacement entity.

- [ ] **Step 5: Run both contract suites and verify GREEN**

Expected: both PASS against byte-identical JSON fixtures.

- [ ] **Step 6: Commit**

Commit: `feat(tui): define complete operations views`

### Task 2: Persist ordered console events and context notes

**Files:**
- Create: `vesper/platform/tui/event_store.py`
- Create: `vesper/platform/tui/notes.py`
- Create: `tests/platform/tui/test_event_store.py`
- Create: `tests/platform/tui/test_notes.py`

**Interfaces:**
- Produces: `EventStore.append(event) -> StoredEvent` with idempotent event IDs.
- Produces: `EventStore.since(sequence, limit) -> tuple[StoredEvent, ...]`.
- Produces: `EventStore.search(query, filters, limit) -> tuple[StoredEvent, ...]`.
- Produces: `NoteStore.add(target, body, visibility, author) -> NoteView`.
- Produces: `NoteStore.list(target) -> tuple[NoteView, ...]`.

- [ ] **Step 1: Write migration, ordering, replay, and note tests**

Assert schema creation, monotonic sequence, replay returning the original row,
conflicting replay rejection, 10,000-row pagination, UTC timestamps, private and
shared visibility, target types `stock`, `order`, `approval`, `agent-event`, and
no command field in the note schema.

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run --locked python -m pytest tests/platform/tui/test_event_store.py tests/platform/tui/test_notes.py -q`

Expected: FAIL because stores are absent.

- [ ] **Step 3: Implement SQLite stores under LocalAppData**

Use WAL mode, foreign keys, `busy_timeout=5000`, explicit transactions, an
append-only event table, FTS5 search, and a mutable notes table with an immutable
note-history table. Store JSON payloads with sorted keys. Reject bodies above
8,000 characters and queries above 256 characters.

- [ ] **Step 4: Run tests and verify GREEN**

Expected: PASS including reopen and concurrent-reader tests.

- [ ] **Step 5: Commit**

Commit: `feat(tui): store timeline events and notes`

### Task 3: Add truthful Python projection ports

**Files:**
- Create: `vesper/platform/tui/ports.py`
- Create: `vesper/platform/tui/projections/__init__.py`
- Create: `vesper/platform/tui/projections/native_platform.py`
- Create: `vesper/platform/tui/projections/legacy_state.py`
- Create: `vesper/platform/tui/projections/repository.py`
- Create: `vesper/platform/tui/projections/windows_system.py`
- Create: `tests/platform/tui/projections/test_native_platform.py`
- Create: `tests/platform/tui/projections/test_legacy_state.py`
- Create: `tests/platform/tui/projections/test_repository.py`
- Create: `tests/platform/tui/projections/test_windows_system.py`

**Interfaces:**
- Produces protocols `AgentReadPort`, `PortfolioReadPort`, `OrderReadPort`, `ModelReadPort`, `RiskReadPort`, `DataReadPort`, `MemoryReadPort`, and `SystemReadPort`.
- Every port returns `SourceSample[T](value, freshness, observed_at, source, error)`.
- Produces `UnavailablePort(reason)` for every missing source.

- [ ] **Step 1: Write fake-port and real-read projection tests**

```python
def test_missing_port_is_explicitly_unavailable() -> None:
    sample = UnavailablePort("No controller-owned order feed is configured.").read()
    assert sample.freshness is Freshness.UNAVAILABLE
    assert sample.value is None
    assert sample.error == "No controller-owned order feed is configured."
```

Native-platform tests use temporary persistence and verify active runs,
approvals, agent roster, queue, journals, evidence, and knowledge status. Legacy
state tests use a temporary `engine_state.json`, reject symlinks, bad JSON,
future timestamps, negative quantities, and files outside the configured root.

- [ ] **Step 2: Run projection tests and verify RED**

Run: `uv run --locked python -m pytest tests/platform/tui/projections -q`

Expected: FAIL because ports are absent.

- [ ] **Step 3: Implement read-only adapters**

`NativePlatformProjection` opens `LocalPlatformService` only for its existing
read methods and opens journal persistence for verified sessions. It never calls
create, resume, approve, reject, cancel, enqueue, run-agent, or knowledge-sync.

`LegacyStateProjection` reads only the configured saved state file and labels it
`legacy saved engine state`; it never claims broker reconciliation. Proposed and
approved weights remain `None`. Orders remain unavailable without a typed order
feed.

`RepositoryProjection` reads branch, revision, porcelain status, worktrees,
unpushed count, approved strategy name, and active model metadata through direct
argument subprocesses with five-second timeouts. It never runs a write command.

`WindowsSystemProjection` uses Windows process/system APIs and `shutil.disk_usage`.
GPU and temperature use direct `nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits` when present; failure marks GPU fields unavailable without failing CPU/memory/disk.

- [ ] **Step 4: Prove no side-effect constructors or commands are reachable**

Monkeypatch broker creation, `TradingEngine`, scheduler start, process launch,
and every `LocalPlatformService` write method to raise. All read tests must pass.

- [ ] **Step 5: Run projection tests and verify GREEN**

Expected: PASS with protected path access spies reporting zero calls.

- [ ] **Step 6: Commit**

Commit: `feat(tui): project current V20 truth safely`

### Task 4: Aggregate snapshots and live event streams

**Files:**
- Create: `vesper/platform/tui/snapshot.py`
- Create: `vesper/platform/tui/stream.py`
- Modify: `vesper/platform/tui/gateway.py`
- Create: `tests/platform/tui/test_snapshot.py`
- Create: `tests/platform/tui/test_stream.py`

**Interfaces:**
- Produces: `SnapshotBuilder.build(previous=None) -> ConsoleSnapshot`.
- Produces: `ProjectionLoop.run(stop_event) -> None`.
- Produces ordered `event` envelopes and resnapshot after gaps.

- [ ] **Step 1: Write freshness, ordering, and coalescing tests**

Use a fake clock and fake ports. Assert first failure unavailable, later failure
stale with retained value, recovery fresh, one state-version increment per
visible change, no increment for byte-identical samples, 50 ms coalescing, fast
1-second and slow 5-second schedules, and no overlapping read per port.

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run --locked python -m pytest tests/platform/tui/test_snapshot.py tests/platform/tui/test_stream.py -q`

Expected: FAIL because aggregation is absent.

- [ ] **Step 3: Implement immutable snapshot replacement**

Build every view completely before publishing. Keep confirmed portfolio rank
from the last reconciled executed state; do not reorder on price-only changes.
When no reconciled rank exists, retain the prior display order and then use
symbol order for new rows; show rank source as unavailable. Derive Impact rows
only when a journal/event chain names an affected model,
symbol, weight, risk, approval, or order. Put other events in full Timeline only.

- [ ] **Step 4: Wire authenticated gateway subscriptions**

Each client has an outbound queue of 256 envelopes. Coalesce replaceable metric
events by entity key. Never drop approvals, alerts, orders, reconciliation, or
chat events. If the queue cannot preserve a required event, disconnect with
`resnapshot-required` rather than skip it.

- [ ] **Step 5: Run tests and verify GREEN**

Expected: PASS including reconnect after a forced sequence gap.

- [ ] **Step 6: Commit**

Commit: `feat(tui): stream versioned V20 projections`

### Task 5: Add Rust reduction and virtualized shared widgets

**Files:**
- Create: `TUI testing/ratatui-console/src/reducer.rs`
- Create: `TUI testing/ratatui-console/src/virtual_table.rs`
- Create: `TUI testing/ratatui-console/src/detail.rs`
- Create: `TUI testing/ratatui-console/src/widgets/mod.rs`
- Create: `TUI testing/ratatui-console/src/widgets/status.rs`
- Create: `TUI testing/ratatui-console/src/widgets/cards.rs`
- Create: `TUI testing/ratatui-console/src/widgets/weights.rs`
- Create: `TUI testing/ratatui-console/src/widgets/timeline.rs`
- Create: `TUI testing/ratatui-console/tests/reducer.rs`
- Create: `TUI testing/ratatui-console/tests/virtual_table.rs`

**Interfaces:**
- Produces `SnapshotReducer::apply_snapshot` and `apply_event`.
- Produces `VirtualTable<T>::visible_range(height)` without cloning all rows.
- Produces shared status badge, card board, weight columns, timeline, and detail overlay.

- [ ] **Step 1: Write reducer and 10,000-row tests**

Assert event order, duplicate idempotency, sequence-gap resnapshot flag, stale
state display, selection stability by entity ID, sorting without source mutation,
and visible-range rendering limited to viewport rows plus two overscan rows.

- [ ] **Step 2: Run tests and verify RED**

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test reducer --test virtual_table --locked`

Expected: FAIL because reduction and virtualization are absent.

- [ ] **Step 3: Implement indexed state and shared widgets**

Keep `Vec` display order plus `HashMap<String, usize>` entity lookup. Replace one
entity in place for events; use a fresh vector only for sort/filter changes.
Every status badge renders symbol, word, and color.

- [ ] **Step 4: Run tests and verify GREEN**

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat(tui): reduce and virtualize live state`

### Task 6: Render Impact, Portfolio, and Orders

**Files:**
- Create: `TUI testing/ratatui-console/src/screens/mod.rs`
- Create: `TUI testing/ratatui-console/src/screens/impact.rs`
- Create: `TUI testing/ratatui-console/src/screens/portfolio.rs`
- Create: `TUI testing/ratatui-console/src/screens/orders.rs`
- Modify: `TUI testing/ratatui-console/src/ui.rs`
- Create: `TUI testing/ratatui-console/tests/screens_market.rs`

**Interfaces:**
- Produces approved Impact layout A.
- Produces executed-rank Portfolio with Current, Proposed, and Approved columns.
- Produces Orders grouped by symbol and newest first within each group.

- [ ] **Step 1: Write screen buffer and behavior tests**

Test all holdings visible through scrolling, unchanged neutral rows, changed-cell
highlight, full-rebalance highlight through reconciling, no row move before a
confirmed-rank event, row move after that event, Today/Since Rebalance/Since
Start toggles, S&P 500 total-return comparison, equal return components, risk
metrics, symbol history, partial fills, fees, slippage, and mismatch owner. The
selected performance period must persist and every portfolio row must be stock,
ETF, or cash.

- [ ] **Step 2: Run tests and verify RED**

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test screens_market --locked`

Expected: FAIL because screens are absent.

- [ ] **Step 3: Render with exact unavailable behavior**

When portfolio or order sources are unavailable, retain the full layout and show
the source reason in its panel. Do not insert sample holdings. Opening a symbol
pins current facts and shows its ordered event history.

- [ ] **Step 4: Approve wide, standard, large-text, and narrow snapshots**

Run the screen test in Insta update mode, inspect each new snapshot, then rerun
without update mode.

- [ ] **Step 5: Commit**

Commit: `feat(tui): render portfolio impact and orders`

### Task 7: Render Agents, Models, Timeline, Risk, Data, Memory, and System

**Files:**
- Create: `TUI testing/ratatui-console/src/screens/agents.rs`
- Create: `TUI testing/ratatui-console/src/screens/models.rs`
- Create: `TUI testing/ratatui-console/src/screens/timeline.rs`
- Create: `TUI testing/ratatui-console/src/screens/risk.rs`
- Create: `TUI testing/ratatui-console/src/screens/data.rs`
- Create: `TUI testing/ratatui-console/src/screens/memory.rs`
- Create: `TUI testing/ratatui-console/src/screens/system.rs`
- Create: `TUI testing/ratatui-console/tests/screens_operations.rs`

**Interfaces:**
- Produces Jira board `Queued | Running | Waiting | Done` plus Backlog.
- Produces final/per-model regime opinions and candidate table.
- Produces impact-first timeline with `e` all-events toggle.
- Produces the remaining approved read views.

- [ ] **Step 1: Write screen tests for every approved state**

Cover urgent-card ordering inside its real stage, hidden chats until open, plan
and evidence detail, model disagreement `UNCERTAIN`, retention labels, hidden
event count, resolved alert persistence, risk current/proposed values, stale
approval, source age/coverage/consumers, memory core/archive/change history,
service metrics, source-control state, and explicit unavailable fields.

- [ ] **Step 2: Run tests and verify RED**

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test screens_operations --locked`

Expected: FAIL because screens are absent.

- [ ] **Step 3: Implement fixed layouts and detail overlays**

The Agents board uses card columns only when terminal width supports them;
narrow mode uses one stage at a time without changing stage data. Timeline uses
impact events by default and displays the count excluded by that filter. System
groups hardware, runtime, source control, backup, recovery, and notification
health without implying disabled controls work.

- [ ] **Step 4: Inspect and approve all snapshots**

Generate both themes, three text modes, and wide/narrow snapshots. Inspect before
accepting them.

- [ ] **Step 5: Commit**

Commit: `feat(tui): render complete operations views`

### Task 8: Add global search, filters, notes, and drill-down

**Files:**
- Create: `vesper/platform/tui/search.py`
- Create: `tests/platform/tui/test_search.py`
- Create: `TUI testing/ratatui-console/src/search.rs`
- Modify: `TUI testing/ratatui-console/src/app.rs`
- Modify: `TUI testing/ratatui-console/src/input.rs`
- Create: `TUI testing/ratatui-console/tests/search.rs`

**Interfaces:**
- Produces bounded search across stock, agent, model, order, approval, event, evidence, memory, and source records.
- Produces per-screen filters and `o` detail overlay.
- Produces Private/Shared note editor with no command path.

- [ ] **Step 1: Write search ranking and routing tests**

Assert exact symbol match first, exact ID second, prefix third, FTS rank after
that, 100-result limit, 256-character query limit, filter persistence by screen,
opening a result routes to the owning screen/entity, and note submission cannot
create a command envelope.

- [ ] **Step 2: Run tests and verify RED**

Run Python and Rust focused search tests.

- [ ] **Step 3: Implement debounced search**

Debounce for 100 ms, cancel superseded local search requests, show result type,
timestamp, and source, and retain keyboard/mouse parity. Shared notes are marked
`context only` in their detail view.

- [ ] **Step 4: Run tests and verify GREEN**

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat(tui): add search drilldown and notes`

### Task 9: Verify refresh performance and safety

**Files:**
- Modify: `tests/platform/tui/test_gateway.py`
- Create: `TUI testing/ratatui-console/tests/performance.rs`
- Create: `TUI testing/ratatui-console/README.md`

**Interfaces:**
- Produces phase-2 benchmark receipts for first cached frame, event reduction, render, input, CPU, and memory.

- [ ] **Step 1: Add deterministic performance tests**

Use 10,000 timeline rows, 1,000 holdings, 1,000 orders, and 500 agent cards.
Measure 100 warm iterations after 10 warmups. Assert p95 event reduction under
25 ms and p95 changed-panel render under 50 ms in `--release` tests. Record
measured values even when a threshold fails.

- [ ] **Step 2: Run all Python TUI tests**

Run: `uv run --locked python -m pytest tests/platform/tui -q`

Expected: PASS.

- [ ] **Step 3: Run Rust checks and release performance tests**

Run: `cargo fmt --manifest-path "TUI testing/ratatui-console/Cargo.toml" -- --check`

Run: `cargo clippy --manifest-path "TUI testing/ratatui-console/Cargo.toml" --all-targets --locked -- -D warnings`

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --locked`

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --release --test performance --locked -- --nocapture`

- [ ] **Step 4: Run the read-boundary proof**

Run tests with broker, scheduler, training, and protected-path access spies. The
expected call count is zero. Launch the console against current V20 and confirm
that unavailable portfolio/order areas stay unavailable rather than showing
fixtures.

- [ ] **Step 5: Commit**

Commit: `test(tui): verify complete read-only console`

## Phase acceptance

- All ten screens render real, stale, or unavailable data truthfully.
- The default Impact screen uses the approved portfolio-dominant layout.
- Portfolio row movement follows confirmed executed rank only.
- Agent cards use the approved Jira-style stages.
- Timeline defaults to impact and exposes all events with `e`.
- Search, filters, notes, mouse, keyboard, and drill-down work.
- Sequence gaps force a snapshot; required events are never silently dropped.
- No broker, scheduler, training, or protected-data path was accessed.
- Python, Rust, snapshot, and performance checks have fresh receipts.
