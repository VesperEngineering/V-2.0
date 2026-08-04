# V20 Ratatui Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Populate all ten screens with truthful controller-owned snapshots, live events, search, drill-down, notes, and explicit stale or unavailable states.

**Architecture:** Python projection ports translate existing V20 stores into strict view models and one versioned `ConsoleSnapshot`. A SQLite event store under LocalAppData records TUI-visible events without becoming portfolio or broker truth. Rust reduces snapshots and ordered events, virtualizes large tables, and renders the approved layouts.

**Tech Stack:** Phase 1 stack plus Python SQLite, Windows read APIs from pywin32, Rust Ratatui stateful widgets, Serde, and Insta.

**Status:** Approved; preflight corrections incorporated.

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
- All stored and wire timestamps are canonical UTC and render in
  `America/New_York`.
- `state_version` tracks presentation snapshots. `control_version` and
  `control_hash` change only when controller facts that can authorize or reject
  a command change. Clocks, metrics, filters, layout, chat, and notes never
  change the control pair.
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
- Every screen has `freshness`, `as_of_utc`, `source`, and `error` fields.
- `ConsoleSnapshot` adds `control_version: int` and
  `control_hash: Sha256Hex`. The hash is canonical JSON over only capability,
  approval, data/model/portfolio/code/evidence, reconciliation, incident, and
  other command-prerequisite facts selected by `ControlStateBuilder`.

```python
class ScreenView(StrictModel):
    freshness: Freshness
    as_of_utc: datetime | None
    source: NonEmptyStr
    error: str | None

class CommandSpecView(StrictModel):
    command_type: NonEmptyStr
    payload_model: NonEmptyStr
    capability_id: SafeId
    reason_rule: Literal["forbidden", "optional", "required"]
    confirmation_level: Literal["none", "confirm", "double-confirm", "typed-live"]


class ConsoleSnapshot(StrictModel):
    shell: ShellSnapshot
    control_version: NonNegativeInt
    control_hash: Sha256Hex
    command_specs: tuple[CommandSpecView, ...]
    impact: ImpactView
    portfolio: PortfolioView
    orders: OrdersView
    agents: AgentsView
    models: ModelsView
    timeline: TimelineView
    risk: RiskView
    data: DataView
    memory: MemoryView
    system: SystemView

class EventPayload(StrictModel):
    entity_type: NonEmptyStr
    entity_id: SafeId
    operation: Literal["upsert", "remove"]
    entity: EventEntity | None
```

Each named screen view subclasses `ScreenView` and owns a tuple of the exact row
types below; no view accepts a generic `dict` row. `EventEntity` is the closed
union of those row models. Task 1 adds `MessageType.EVENT = "event"` and maps it
only to `EventPayload`.

- [ ] **Step 1: Write Python model and Rust fixture tests**

```python
def test_console_snapshot_requires_all_ten_views(full_snapshot_payload) -> None:
    snapshot = ConsoleSnapshot.model_validate(full_snapshot_payload)
    assert snapshot.portfolio.rows[0].symbol == "AAPL"
    payload = dict(full_snapshot_payload)
    payload.pop("orders")
    with pytest.raises(ValidationError):
        ConsoleSnapshot.model_validate(payload)


def test_phase_two_snapshot_has_neutral_empty_command_specs(full_snapshot_payload) -> None:
    payload = {**full_snapshot_payload, "command_specs": []}
    snapshot = ConsoleSnapshot.model_validate(payload)
    assert snapshot.command_specs == ()
```

Rust must deserialize the same fixture and reject the same missing fields and
unknown fields.

```rust
#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct CommandSpecView {
    pub command_type: String,
    pub payload_model: String,
    pub capability_id: String,
    pub reason_rule: ReasonRule,
    pub confirmation_level: ConfirmationLevel,
}

pub struct ConsoleSnapshot {
    // existing exact fields
    pub command_specs: Vec<CommandSpecView>,
}

#[test]
fn python_command_specs_fixture_matches_rust_contract() {
    let snapshot: ConsoleSnapshot = fixture("console_snapshot_empty_command_specs.json");
    assert!(snapshot.command_specs.is_empty());
}
```

- [ ] **Step 2: Run both contract suites and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-observability-temp'; $env:TMP='C:\tmp\v20-tui-observability-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-observability-pytest' -o cache_dir='C:\tmp\v20-tui-observability-cache' tests/platform/tui/test_views.py -q`

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
    occurred_at_utc: datetime
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

`DecimalString` is a finite base-10 string with no exponent. Add these exact
strict contracts; every timestamp validator requires UTC and each model forbids
unknown fields through `StrictModel`:

```python
class FillRow(StrictModel):
    fill_id: NonEmptyStr
    quantity: DecimalString
    price: DecimalString
    fee: DecimalString
    filled_at_utc: datetime

class OrderRow(StrictModel):
    order_id: NonEmptyStr
    symbol: NonEmptyStr
    side: Literal["buy", "sell"]
    quantity: DecimalString
    status: Literal["proposed", "approved", "submitted", "partial", "filled", "rejected", "cancelled"]
    submitted_at_utc: datetime | None
    broker_order_id: str | None
    fills: tuple[FillRow, ...]
    expected_price: DecimalString | None
    actual_price: DecimalString | None
    reconciliation: Literal["pending", "matched", "mismatch", "unavailable"]

class ModelOpinionRow(StrictModel):
    model_id: NonEmptyStr
    regime: NonEmptyStr
    confidence: float
    as_of_utc: datetime

class CandidateRow(StrictModel):
    candidate_id: NonEmptyStr
    family: NonEmptyStr
    strategy: Literal["ml_model", "momentum"]
    status: Literal["training", "evaluating", "passed", "failed", "rejected", "active", "rollback"]
    evidence_ids: tuple[NonEmptyStr, ...]
    created_at_utc: datetime

class RiskLimitRow(StrictModel):
    limit_id: NonEmptyStr
    current_value: DecimalString
    proposed_value: DecimalString | None
    status: Literal["within", "violated", "pending", "unavailable"]

class ApprovalRow(StrictModel):
    approval_id: NonEmptyStr
    state: Literal["pending", "approved", "held", "rejected", "rework", "stale"]
    reason: str | None
    evidence_ids: tuple[NonEmptyStr, ...]
    requested_at_utc: datetime

class SourceRow(StrictModel):
    source_id: NonEmptyStr
    freshness: Freshness
    as_of_utc: datetime | None
    age_seconds: float | None
    coverage: str | None
    error: str | None
    consumers: tuple[NonEmptyStr, ...]

class EvidenceRow(StrictModel):
    evidence_id: NonEmptyStr
    evidence_type: NonEmptyStr
    source: NonEmptyStr
    created_at_utc: datetime
    sha256: Sha256Hex

class MemoryRow(StrictModel):
    memory_id: NonEmptyStr
    status: Literal["core", "archived"]
    summary: NonEmptyStr
    evidence_ids: tuple[NonEmptyStr, ...]
    updated_at_utc: datetime

class ServiceRow(StrictModel):
    service_id: NonEmptyStr
    state: Literal["running", "paused", "stopped", "failed", "unavailable"]
    health_reason: str | None
    observed_at_utc: datetime

class MetricRow(StrictModel):
    metric_id: NonEmptyStr
    value: float | None
    unit: NonEmptyStr
    freshness: Freshness
    observed_at_utc: datetime | None

class ReturnComponentRow(StrictModel):
    component: Literal["price", "dividends", "cash-interest", "fees", "sp500-total-return"]
    value: DecimalString

class AlertRow(StrictModel):
    alert_id: NonEmptyStr
    severity: Literal["info", "active", "waiting", "urgent", "resolved"]
    summary: NonEmptyStr
    created_at_utc: datetime
    resolved_at_utc: datetime | None

EventEntity = (
    PortfolioRow | AgentCard | TimelineRow | FillRow | OrderRow |
    ModelOpinionRow | CandidateRow | RiskLimitRow | ApprovalRow | SourceRow |
    EvidenceRow | MemoryRow | ServiceRow | MetricRow | ReturnComponentRow |
    AlertRow
)
```

Use decimal strings for broker quantities or money that must round-trip exactly;
use floats only for display metrics.

`AgentCard.stage == "failed"` is retained as source truth but renders in the
Done column with an explicit `FAILED` word and symbol. It never creates an
unapproved fifth active-work column.

- [ ] **Step 4: Replace `ShellSnapshot` snapshot payload with `ConsoleSnapshot`**

Keep the phase-1 shell fields unchanged. The gateway emits one complete initial
snapshot and event payloads containing `entity_type`, `entity_id`, `operation`,
and the complete replacement entity.

- [ ] **Step 5: Run both contract suites and verify GREEN**

Run: `$env:TEMP='C:\tmp\v20-tui-observability-temp'; $env:TMP='C:\tmp\v20-tui-observability-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-observability-pytest' -o cache_dir='C:\tmp\v20-tui-observability-cache' tests/platform/tui/test_views.py -q`

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test contract --locked`

Expected: both PASS against byte-identical JSON fixtures.

- [ ] **Step 6: Commit**

```powershell
git add -- 'vesper/platform/tui/views.py' 'vesper/platform/tui/contracts.py' 'tests/platform/tui/test_views.py' 'TUI testing/ratatui-console/src/contract.rs' 'TUI testing/ratatui-console/tests/contract.rs'
git commit -m "feat(tui): define complete operations views"
```

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

```python
class EventStore:
    def append(self, event: EventInput) -> StoredEvent: ...
    def since(self, sequence: int, limit: int) -> tuple[StoredEvent, ...]: ...
    def search(self, query: str, filters: EventFilters, limit: int) -> tuple[StoredEvent, ...]: ...


class NoteStore:
    def add(self, target: NoteTarget, body: str, visibility: NoteVisibility, author: SafeId) -> NoteView: ...
    def list(self, target: NoteTarget) -> tuple[NoteView, ...]: ...
```

- [ ] **Step 1: Write migration, ordering, replay, and note tests**

Assert schema creation, monotonic sequence, replay returning the original row,
conflicting replay rejection, 10,000-row pagination, UTC timestamps, private and
shared visibility, target types `stock`, `order`, `approval`, `agent-event`, and
no command field in the note schema.

```python
def test_event_replay_and_note_boundary(tmp_path) -> None:
    events = EventStore(tmp_path / "events.db")
    assert events.append(EVENT) == events.append(EVENT)
    note = NoteStore(tmp_path / "events.db").add(TARGET, "context", NoteVisibility.PRIVATE, "operator")
    assert "command" not in note.model_fields
```

- [ ] **Step 2: Run tests and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-observability-temp'; $env:TMP='C:\tmp\v20-tui-observability-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-observability-pytest' -o cache_dir='C:\tmp\v20-tui-observability-cache' tests/platform/tui/test_event_store.py tests/platform/tui/test_notes.py -q`

Expected: FAIL because stores are absent.

- [ ] **Step 3: Implement SQLite stores under LocalAppData**

Use WAL mode, foreign keys, `busy_timeout=5000`, explicit transactions, an
append-only event table, FTS5 search, and a current-notes table with immutable
note history. This phase admits revision-1 notes only and exposes no edit
command. Any future revision must update the current row, immutable history,
and FTS index in one transaction. Store JSON payloads with sorted keys. Reject
bodies above 8,000 characters and queries above 256 characters.

```python
def append(self, event: EventInput) -> StoredEvent:
    with self._connection:
        existing = self._by_event_id(event.event_id)
        return self._require_same_event(existing, event) if existing else self._insert_next_sequence(event)
```

- [ ] **Step 4: Run tests and verify GREEN**

Run: `$env:TEMP='C:\tmp\v20-tui-observability-temp'; $env:TMP='C:\tmp\v20-tui-observability-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-observability-pytest' -o cache_dir='C:\tmp\v20-tui-observability-cache' tests/platform/tui/test_event_store.py tests/platform/tui/test_notes.py -q`

Expected: PASS including reopen and concurrent-reader tests.

- [ ] **Step 5: Commit**

```powershell
git add -- 'vesper/platform/tui/event_store.py' 'vesper/platform/tui/notes.py' 'tests/platform/tui/test_event_store.py' 'tests/platform/tui/test_notes.py'
git commit -m "feat(tui): store timeline events and notes"
```

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
- Every port returns `SourceSample[T](value, freshness, observed_at_utc, source, error)`.
- Produces `UnavailablePort(reason)` for every missing source.

```python
@dataclass(frozen=True, slots=True)
class SourceSample(Generic[T]):
    value: T | None
    freshness: Freshness
    observed_at_utc: datetime | None
    source: str
    error: str | None


class ReadPort(Protocol, Generic[T]):
    def read(self) -> SourceSample[T]: ...


class UnavailablePort(Generic[T]):
    def __init__(self, reason: NonEmptyStr) -> None: ...
    def read(self) -> SourceSample[T]: ...
```

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

```python
def test_repository_projection_never_runs_write_commands(projection, subprocess_spy) -> None:
    projection.read()
    assert all(argv[0] == "git" and argv[1] in {"status", "rev-parse", "worktree", "rev-list"} for argv in subprocess_spy.argv)
    assert subprocess_spy.shell_calls == []
```

- [ ] **Step 2: Run projection tests and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-observability-temp'; $env:TMP='C:\tmp\v20-tui-observability-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-observability-pytest' -o cache_dir='C:\tmp\v20-tui-observability-cache' tests/platform/tui/projections -q`

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

```python
def read(self) -> SourceSample[RepositoryView]:
    status = run_checked(["git", "status", "--porcelain=v1"], timeout=5)
    revision = run_checked(["git", "rev-parse", "HEAD"], timeout=5)
    return SourceSample(RepositoryView(status=status, revision=revision), Freshness.FRESH, utc_now(), "git", None)
```

- [ ] **Step 4: Prove no forbidden constructors or write commands are reachable**

Monkeypatch broker creation, `TradingEngine`, scheduler start, and every
`LocalPlatformService` write method to raise. Wrap subprocess creation with an
argv-classifying spy: allow only the exact read-only Git commands defined by
`RepositoryProjection` and the exact `nvidia-smi --query-gpu=...` command above;
raise on every other executable or argv. Assert the allowlisted read commands
occur as expected and broker, scheduler, trainer, protected-path, shell, Git
write, and arbitrary process launches remain zero.

- [ ] **Step 5: Run projection tests and verify GREEN**

Run: `$env:TEMP='C:\tmp\v20-tui-observability-temp'; $env:TMP='C:\tmp\v20-tui-observability-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-observability-pytest' -o cache_dir='C:\tmp\v20-tui-observability-cache' tests/platform/tui/projections -q`

Expected: PASS with protected path access spies reporting zero calls.

- [ ] **Step 6: Commit**

```powershell
git add -- 'vesper/platform/tui/ports.py' 'vesper/platform/tui/projections/__init__.py' 'vesper/platform/tui/projections/native_platform.py' 'vesper/platform/tui/projections/legacy_state.py' 'vesper/platform/tui/projections/repository.py' 'vesper/platform/tui/projections/windows_system.py' 'tests/platform/tui/projections/test_native_platform.py' 'tests/platform/tui/projections/test_legacy_state.py' 'tests/platform/tui/projections/test_repository.py' 'tests/platform/tui/projections/test_windows_system.py'
git commit -m "feat(tui): project current V20 truth safely"
```

### Task 4: Aggregate snapshots and live event streams

**Files:**
- Create: `vesper/platform/tui/snapshot.py`
- Create: `vesper/platform/tui/stream.py`
- Modify: `vesper/platform/tui/gateway.py`
- Create: `tests/platform/tui/test_snapshot.py`
- Create: `tests/platform/tui/test_stream.py`

**Interfaces:**
- Produces: `SnapshotBuilder.build(previous=None) -> ConsoleSnapshot`.
- Produces: `ControlStateBuilder.build(samples) -> ControlState(version, hash)`.
- Produces: `ProjectionLoop.run(stop_event) -> None`.
- Produces ordered `event` envelopes and resnapshot after gaps.

```python
@dataclass(frozen=True, slots=True)
class ControlState:
    version: int
    hash: Sha256Hex


class SnapshotBuilder:
    def build(self, previous: ConsoleSnapshot | None = None) -> ConsoleSnapshot: ...


class ControlStateBuilder:
    def build(self, samples: Mapping[str, SourceSample[object]]) -> ControlState: ...


class ProjectionLoop:
    def run(self, stop_event: threading.Event) -> None: ...
```

- [ ] **Step 1: Write freshness, ordering, and coalescing tests**

Use a fake clock and fake ports. Assert first failure unavailable, later failure
stale with retained value, recovery fresh, one state-version increment per
visible change, no increment for byte-identical samples, and a control-version
increment only for canonical command-prerequisite changes. Assert 1-second CPU,
GPU, clock, and process updates leave the control pair unchanged. Also assert 50
ms coalescing, fast 1-second and slow 5-second schedules, and no overlapping read
per port.

```python
def test_control_pair_ignores_metrics_but_changes_for_authority(snapshot_builder) -> None:
    first = snapshot_builder.build()
    metrics_only = snapshot_builder.build(previous=first, samples=changed_metrics())
    assert metrics_only.control_hash == first.control_hash
    changed = snapshot_builder.build(previous=metrics_only, samples=changed_approval())
    assert changed.control_hash != first.control_hash
```

- [ ] **Step 2: Run tests and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-observability-temp'; $env:TMP='C:\tmp\v20-tui-observability-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-observability-pytest' -o cache_dir='C:\tmp\v20-tui-observability-cache' tests/platform/tui/test_snapshot.py tests/platform/tui/test_stream.py -q`

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
events by entity key before assigning that client's next sequence. Assign
contiguous per-client sequence numbers only to envelopes that enter the queue.
Never drop approvals, alerts, orders, reconciliation, or chat events. If the
queue cannot preserve a required event, disconnect with `resnapshot-required`
rather than skip it. Tests replace at least three pending metric events and
assert the client receives no artificial sequence gap.

```python
def build(self, previous: ConsoleSnapshot | None = None) -> ConsoleSnapshot:
    samples = self._read_all_without_overlap()
    views = self._project_complete_views(samples, previous)
    control = self._control_builder.build(samples)
    return ConsoleSnapshot(**views, control_version=control.version, control_hash=control.hash, command_specs=())
```

- [ ] **Step 5: Run tests and verify GREEN**

Run: `$env:TEMP='C:\tmp\v20-tui-observability-temp'; $env:TMP='C:\tmp\v20-tui-observability-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-observability-pytest' -o cache_dir='C:\tmp\v20-tui-observability-cache' tests/platform/tui/test_snapshot.py tests/platform/tui/test_stream.py -q`

Expected: PASS including reconnect after a forced sequence gap.

- [ ] **Step 6: Commit**

```powershell
git add -- 'vesper/platform/tui/snapshot.py' 'vesper/platform/tui/stream.py' 'vesper/platform/tui/gateway.py' 'tests/platform/tui/test_snapshot.py' 'tests/platform/tui/test_stream.py'
git commit -m "feat(tui): stream versioned V20 projections"
```

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

```rust
impl SnapshotReducer {
    pub fn apply_snapshot(&mut self, snapshot: ConsoleSnapshot) -> ReduceOutcome;
    pub fn apply_event(&mut self, event: EventEnvelope) -> Result<ReduceOutcome, SequenceGap>;
}

impl<T> VirtualTable<T> {
    pub fn visible_range(&self, height: usize) -> Range<usize>;
}
```

- [ ] **Step 1: Write reducer and 10,000-row tests**

Assert event order, duplicate idempotency, sequence-gap resnapshot flag, stale
state display, selection stability by entity ID, sorting without source mutation,
and visible-range rendering limited to viewport rows plus two overscan rows.

```rust
#[test]
fn snapshot_replaces_command_specs_atomically() {
    let mut reducer = SnapshotReducer::default();
    reducer.apply_snapshot(snapshot_with_specs(vec![spec("note.add")]));
    assert_eq!(reducer.state().command_specs[0].command_type, "note.add");
    reducer.apply_snapshot(snapshot_with_specs(vec![]));
    assert!(reducer.state().command_specs.is_empty());
}
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test reducer --test virtual_table --locked`

Expected: FAIL because reduction and virtualization are absent.

- [ ] **Step 3: Implement indexed state and shared widgets**

Keep `Vec` display order plus `HashMap<String, usize>` entity lookup. Replace one
entity in place for events; use a fresh vector only for sort/filter changes.
Every status badge renders symbol, word, and color.

```rust
pub struct ReducedState {
    pub snapshot: ConsoleSnapshot,
    pub command_specs: HashMap<String, CommandSpecView>,
}

fn replace_command_specs(state: &mut ReducedState, specs: &[CommandSpecView]) {
    state.command_specs = specs.iter()
        .cloned()
        .map(|spec| (spec.command_type.clone(), spec))
        .collect();
}
```

- [ ] **Step 4: Run tests and verify GREEN**

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test reducer --test virtual_table --locked`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add -- 'TUI testing/ratatui-console/src/reducer.rs' 'TUI testing/ratatui-console/src/virtual_table.rs' 'TUI testing/ratatui-console/src/detail.rs' 'TUI testing/ratatui-console/src/widgets/mod.rs' 'TUI testing/ratatui-console/src/widgets/status.rs' 'TUI testing/ratatui-console/src/widgets/cards.rs' 'TUI testing/ratatui-console/src/widgets/weights.rs' 'TUI testing/ratatui-console/src/widgets/timeline.rs' 'TUI testing/ratatui-console/tests/reducer.rs' 'TUI testing/ratatui-console/tests/virtual_table.rs'
git commit -m "feat(tui): reduce and virtualize live state"
```

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

```rust
pub fn render_impact(frame: &mut Frame<'_>, area: Rect, view: &ImpactView, state: &ScreenState);
pub fn render_portfolio(frame: &mut Frame<'_>, area: Rect, view: &PortfolioView, state: &ScreenState);
pub fn render_orders(frame: &mut Frame<'_>, area: Rect, view: &OrdersView, state: &ScreenState);
```

- [ ] **Step 1: Write screen buffer and behavior tests**

Test all holdings visible through scrolling, unchanged neutral rows, changed-cell
highlight, full-rebalance highlight through reconciling, no row move before a
confirmed-rank event, row move after that event, Today/Since Rebalance/Since
Start toggles, S&P 500 total-return comparison, equal return components, risk
metrics, symbol history, partial fills, fees, slippage, and mismatch owner. The
selected performance period must persist and every portfolio row must be stock,
ETF, or cash.

```rust
#[test]
fn portfolio_moves_only_after_confirmed_execution_rank() {
    assert_eq!(symbols(render_portfolio_view(rows_with_proposal_only())), vec!["AAPL", "MSFT"]);
    assert_eq!(symbols(render_portfolio_view(rows_with_confirmed_rank())), vec!["MSFT", "AAPL"]);
}
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test screens_market --locked`

Expected: FAIL because screens are absent.

- [ ] **Step 3: Render with exact unavailable behavior**

When portfolio or order sources are unavailable, retain the full layout and show
the source reason in its panel. Do not insert sample holdings. Opening a symbol
pins current facts and shows its ordered event history.

```rust
pub fn render_portfolio(frame: &mut Frame<'_>, area: Rect, view: &PortfolioView, state: &ScreenState) {
    frame.render_stateful_widget(portfolio_table(view, state), area, &mut state.table.clone());
}
```

- [ ] **Step 4: Approve wide, standard, large-text, and narrow snapshots**

Run: `$env:INSTA_UPDATE='new'; cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test screens_market --locked`

Inspect each `.snap.new`, accept only reviewed snapshots, then clear
`INSTA_UPDATE`.

- [ ] **Step 5: Run screen tests and verify GREEN**

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test screens_market --locked`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add -- 'TUI testing/ratatui-console/src/screens/mod.rs' 'TUI testing/ratatui-console/src/screens/impact.rs' 'TUI testing/ratatui-console/src/screens/portfolio.rs' 'TUI testing/ratatui-console/src/screens/orders.rs' 'TUI testing/ratatui-console/src/ui.rs' 'TUI testing/ratatui-console/tests/screens_market.rs'
git commit -m "feat(tui): render portfolio impact and orders"
```

### Task 7: Render Agents, Models, and Timeline

**Files:**
- Create: `TUI testing/ratatui-console/src/screens/agents.rs`
- Create: `TUI testing/ratatui-console/src/screens/models.rs`
- Create: `TUI testing/ratatui-console/src/screens/timeline.rs`
- Create: `TUI testing/ratatui-console/tests/screens_agents.rs`

**Interfaces:**
- Produces Jira board `Queued | Running | Waiting | Done` plus Backlog.
- Produces final/per-model regime opinions and candidate table.
- Produces impact-first timeline with `e` all-events toggle.

```rust
pub fn render_agents(frame: &mut Frame<'_>, area: Rect, view: &AgentsView, state: &ScreenState);
pub fn render_models(frame: &mut Frame<'_>, area: Rect, view: &ModelsView, state: &ScreenState);
pub fn render_timeline(frame: &mut Frame<'_>, area: Rect, view: &TimelineView, state: &ScreenState);
```

- [ ] **Step 1: Write screen tests for every approved state**

Cover urgent-card ordering inside its real stage, hidden chats until open, plan
and evidence detail, model disagreement `UNCERTAIN`, retention labels, and the
hidden event count. A failed card must appear in Done, retain `stage="failed"`,
and display `FAILED` with a non-color status symbol.

```rust
#[test]
fn failed_agent_stays_in_done_with_failed_label() {
    let buffer = render_agents_view(agent_view("failed"));
    assert!(buffer.contains("Done"));
    assert!(buffer.contains("! FAILED"));
}
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test screens_agents --locked`

Expected: FAIL because screens are absent.

- [ ] **Step 3: Implement fixed layouts and detail overlays**

The Agents board uses card columns only when terminal width supports them;
narrow mode uses one stage at a time without changing stage data. Timeline uses
impact events by default and displays the count excluded by that filter.

```rust
pub fn render_agents(frame: &mut Frame<'_>, area: Rect, view: &AgentsView, state: &ScreenState) {
    render_stage_columns(frame, area, ["queued", "running", "waiting", "done"], view, state);
}
```

- [ ] **Step 4: Inspect and approve all snapshots**

Generate both themes, three text modes, and wide/narrow snapshots. Inspect before
accepting them.

Run: `$env:INSTA_UPDATE='new'; cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test screens_agents --locked`

- [ ] **Step 5: Run screen tests and verify GREEN**

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test screens_agents --locked`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add -- 'TUI testing/ratatui-console/src/screens/agents.rs' 'TUI testing/ratatui-console/src/screens/models.rs' 'TUI testing/ratatui-console/src/screens/timeline.rs' 'TUI testing/ratatui-console/tests/screens_agents.rs'
git commit -m "feat(tui): render agent model and timeline views"
```

### Task 8: Render Risk, Data, Memory, and System

**Files:**
- Create: `TUI testing/ratatui-console/src/screens/risk.rs`
- Create: `TUI testing/ratatui-console/src/screens/data.rs`
- Create: `TUI testing/ratatui-console/src/screens/memory.rs`
- Create: `TUI testing/ratatui-console/src/screens/system.rs`
- Create: `TUI testing/ratatui-console/tests/screens_system.rs`

**Interfaces:**
- Consumes exact `RiskView`, `DataView`, `MemoryView`, and `SystemView` contracts from Task 1.
- Produces fixed wide layouts and narrow one-panel focus layouts for those four views.

- [ ] **Step 1: Write screen tests for every approved state**

Cover resolved alert persistence, risk current/proposed values, stale approval,
source age/coverage/consumers, memory core/archive/change history, service
metrics, source-control state, and explicit unavailable fields. Assert each
status has a word or symbol independent of color.

```rust
#[test]
fn unavailable_system_source_keeps_panel_and_reason() {
    let buffer = render_system_view(unavailable_system("GPU adapter missing"));
    assert!(buffer.contains("UNAVAILABLE"));
    assert!(buffer.contains("GPU adapter missing"));
}
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test screens_system --locked`

Expected: FAIL because the four screens are absent.

- [ ] **Step 3: Implement exact layouts and unavailable panels**

```rust
pub fn render_risk(frame: &mut Frame<'_>, area: Rect, view: &RiskView, state: &ScreenState);
pub fn render_data(frame: &mut Frame<'_>, area: Rect, view: &DataView, state: &ScreenState);
pub fn render_memory(frame: &mut Frame<'_>, area: Rect, view: &MemoryView, state: &ScreenState);
pub fn render_system(frame: &mut Frame<'_>, area: Rect, view: &SystemView, state: &ScreenState);
```

Implement each function with the same exact rule:

```rust
fn render_source_panel(frame: &mut Frame<'_>, area: Rect, freshness: Freshness, reason: Option<&str>) {
    let body = reason.unwrap_or("No current source value.");
    frame.render_widget(Paragraph::new(format!("{} {}", freshness.label(), body)), area);
}
```

System groups hardware, runtime, source control, backup, recovery, and
notification health without implying disabled controls work. An unavailable
source keeps its panel and renders its exact source reason.

- [ ] **Step 4: Generate and inspect snapshots**

Run: `$env:INSTA_UPDATE='new'; cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test screens_system --locked`

- [ ] **Step 5: Run screen tests and verify GREEN**

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test screens_system --locked`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add -- 'TUI testing/ratatui-console/src/screens/risk.rs' 'TUI testing/ratatui-console/src/screens/data.rs' 'TUI testing/ratatui-console/src/screens/memory.rs' 'TUI testing/ratatui-console/src/screens/system.rs' 'TUI testing/ratatui-console/tests/screens_system.rs'
git commit -m "feat(tui): render risk data memory and system views"
```

### Task 9: Add global search, filters, notes, and drill-down

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

```python
class SearchService:
    def search(self, query: str, filters: SearchFilters, limit: int = 100) -> tuple[SearchResult, ...]: ...
```

```rust
impl SearchState {
    pub fn update_query(&mut self, query: String, now: Instant) -> Option<SearchRequest>;
    pub fn apply_results(&mut self, request_id: u64, rows: Vec<SearchResult>);
    pub fn open_selected(&self) -> Option<NavigationTarget>;
}
```

- [ ] **Step 1: Write search ranking and routing tests**

Assert exact symbol match first, exact ID second, prefix third, FTS rank after
that, 100-result limit, 256-character query limit, filter persistence by screen,
opening a result routes to the owning screen/entity, and note submission cannot
create a command envelope.

```python
def test_search_is_bounded_and_notes_are_context_only(search, note_store) -> None:
    assert len(search.search("A", SearchFilters(), limit=100)) <= 100
    assert "command" not in note_store.add(TARGET, "watch", NoteVisibility.SHARED, "operator").model_fields
```

- [ ] **Step 2: Run tests and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-observability-temp'; $env:TMP='C:\tmp\v20-tui-observability-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-observability-pytest' -o cache_dir='C:\tmp\v20-tui-observability-cache' tests/platform/tui/test_search.py tests/platform/tui/test_notes.py -q`

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test search --locked`

Expected: FAIL because search is absent.

- [ ] **Step 3: Implement debounced search**

Debounce for 100 ms, cancel superseded local search requests, show result type,
timestamp, and source, and retain keyboard/mouse parity. Shared notes are marked
`context only` in their detail view.

```python
def search(self, query: str, filters: SearchFilters, limit: int = 100) -> tuple[SearchResult, ...]:
    query = require_bounded_query(query, 256)
    return tuple(self._rank(query, filters)[: min(limit, 100)])
```

- [ ] **Step 4: Run tests and verify GREEN**

Run: `$env:TEMP='C:\tmp\v20-tui-observability-temp'; $env:TMP='C:\tmp\v20-tui-observability-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-observability-pytest' -o cache_dir='C:\tmp\v20-tui-observability-cache' tests/platform/tui/test_search.py tests/platform/tui/test_notes.py -q`

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test search --locked`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add -- 'vesper/platform/tui/search.py' 'tests/platform/tui/test_search.py' 'TUI testing/ratatui-console/src/search.rs' 'TUI testing/ratatui-console/src/app.rs' 'TUI testing/ratatui-console/src/input.rs' 'TUI testing/ratatui-console/tests/search.rs'
git commit -m "feat(tui): add search drilldown and notes"
```

### Task 9b: Search controller history and stored notes

**Files:**
- Modify: `vesper/platform/tui/contracts.py`
- Modify: `vesper/platform/tui/search.py`
- Modify: `vesper/platform/tui/gateway.py`
- Modify: `vesper/platform/tui/cli.py`
- Modify: `vesper/platform/tui/event_store.py`
- Modify: `vesper/platform/tui/notes.py`
- Modify: `vesper/platform/tui/sqlite_ledger.py`
- Modify: `tests/platform/tui/test_contracts.py`
- Modify: `tests/platform/tui/test_search.py`
- Modify: `tests/platform/tui/test_gateway.py`
- Modify: `tests/platform/tui/test_event_store.py`
- Modify: `tests/platform/tui/test_notes.py`
- Modify: `TUI testing/ratatui-console/src/contract.rs`
- Modify: `TUI testing/ratatui-console/src/search.rs`
- Modify: `TUI testing/ratatui-console/src/state.rs`
- Modify: `TUI testing/ratatui-console/src/app.rs`
- Modify: `TUI testing/ratatui-console/src/ui.rs`
- Modify: `TUI testing/ratatui-console/tests/contract.rs`
- Modify: `TUI testing/ratatui-console/tests/search.rs`
- Modify: `TUI testing/ratatui-console/tests/state.rs`
- Modify: `TUI testing/ratatui-console/tests/input.rs`

**Interfaces:**
- Produces authenticated read-only `search-request` and `search-results` wire messages.
- Produces `GlobalSearchService` that merges the current snapshot, the complete
  append-only event ledger, and stored context notes.
- Adds `note` as a typed search kind while retaining exact-stock, exact-ID,
  prefix, and FTS ordering.
- Requires one exact search record type: `portfolio-row`, `agent-card`,
  `model-opinion-row`, `candidate-row`, `order-row`, `approval-row`,
  `timeline-row`, `evidence-row`, `memory-row`, `source-row`, `repository-row`,
  or `note`.
- Produces a deterministic event-admission seam for later controller-owned
  order, approval, agent, and portfolio transitions. It never derives history
  by comparing snapshots.

- [ ] **Step 1: Write full-history and authentication regressions**

Insert 10,001 events so the oldest event is outside the snapshot window, then
prove global search still returns it before and after a restart. Prove Private
and Shared notes are searchable only after authentication and remain
`context_only`. An authenticated viewer may search without Take Control; a
locked session receives no result. Cover prefix rank, filters, hostile FTS text,
deduplication, duplicate IDs with different kinds, and the 100-result limit.
Also prove same-ID records with the same broad kind survive when their exact
record types differ, including model-opinion/candidate and source/repository.

- [ ] **Step 2: Add a strict v1-to-v2 ledger migration and note FTS**

Migrate only a valid V20-owned version-1 ledger. Add `note_search` and populate
it in the same transaction as note creation. Any future revision must update
the current note, immutable history, and FTS rows in one transaction. Verify
schema and content before committing the migration. Validate every note payload against
its columns and immutable history, then verify exact FTS row/content parity
inside the migration transaction. A corrupt, foreign, or newer ledger must fail
closed without modification.

- [ ] **Step 3: Implement controller-owned merged search**

Add bounded `SearchRequestPayload` and `SearchResultsPayload` contracts with an
echoed request ID and indexed state version. Require `record_type` on every
result. Merge snapshot, EventStore, and NoteStore results, deduplicate by
`(record_type, record_id)` using case-insensitive ID comparison, and return at
most 100.
The gateway validates authentication and owns all access to the persistent
stores. Search performs no broker, scheduler, training, or protected-data read.

- [ ] **Step 4: Route Rust debounce through the gateway**

Keep the existing 100 ms debounce and stale-request suppression, but send the
typed request to the gateway instead of treating the bounded snapshot as the
production history index. Render visible server errors without substituting
local fixture data. Keep a local index only for isolated tests or an explicitly
labeled disconnected fallback that cannot claim full history.

- [ ] **Step 5: Add deterministic history admission**

Provide a transaction-bound API that admits authoritative controller events
with deterministic IDs, receipt/evidence links, idempotent replay, and conflict
rejection. Controls Task 4 must use this seam for enabled operator transitions;
later conversation and memory stores must register their own bounded search
sources. Typed order history stays unavailable until a reviewed authoritative
source exists.

- [ ] **Step 6: Run focused and boundary verification**

Run the Python contract, ledger, event, note, gateway, and search suites. Run
the Rust contract, search, state, and input suites. Repeat the read-boundary
proof with all broker, scheduler, training, and protected-path counters at zero.

- [ ] **Step 7: Commit**

```powershell
git add -- 'vesper/platform/tui/contracts.py' 'vesper/platform/tui/search.py' 'vesper/platform/tui/gateway.py' 'vesper/platform/tui/cli.py' 'vesper/platform/tui/event_store.py' 'vesper/platform/tui/notes.py' 'vesper/platform/tui/sqlite_ledger.py' 'tests/platform/tui/test_contracts.py' 'tests/platform/tui/test_search.py' 'tests/platform/tui/test_gateway.py' 'tests/platform/tui/test_event_store.py' 'tests/platform/tui/test_notes.py' 'TUI testing/ratatui-console/src/contract.rs' 'TUI testing/ratatui-console/src/search.rs' 'TUI testing/ratatui-console/src/state.rs' 'TUI testing/ratatui-console/src/app.rs' 'TUI testing/ratatui-console/src/ui.rs' 'TUI testing/ratatui-console/tests/contract.rs' 'TUI testing/ratatui-console/tests/search.rs' 'TUI testing/ratatui-console/tests/state.rs' 'TUI testing/ratatui-console/tests/input.rs'
git commit -m "feat(tui): search complete controller history"
```

### Task 10: Verify refresh performance and safety

**Files:**
- Modify: `tests/platform/tui/test_gateway.py`
- Create: `TUI testing/ratatui-console/tests/performance.rs`
- Create: `TUI testing/ratatui-console/README.md`

**Interfaces:**
- Produces phase-2 benchmark receipts for event reduction, changed-panel render,
  and 10,000-row navigation. Cached-first-screen, input, idle CPU, and continuous
  memory measurements belong to phase 4 after cache and packaging exist.

```rust
pub struct BenchmarkReceipt {
    pub name: String,
    pub samples_ns: Vec<u64>,
    pub median_ns: u64,
    pub p95_ns: u64,
    pub max_ns: u64,
}

pub fn benchmark_reducer(fixture: &ConsoleSnapshot, warmups: usize, samples: usize) -> BenchmarkReceipt;
pub fn benchmark_changed_panel(fixture: &ConsoleSnapshot, warmups: usize, samples: usize) -> BenchmarkReceipt;
```

- [ ] **Step 1: Add deterministic performance tests**

Use 10,000 timeline rows, 1,000 holdings, 1,000 orders, and 500 agent cards.
Measure 100 warm iterations after 10 warmups. Assert p95 event reduction under
25 ms and p95 changed-panel render under 50 ms in `--release` tests. Instrument
the dirty-panel set and backend cell writes: a one-panel event must invoke only
that panel renderer and must not mark or rewrite the full screen. Record measured
values even when a threshold fails.

```rust
#[test]
fn release_reducer_and_panel_budgets_are_recorded() {
    let reducer = benchmark_reducer(&large_fixture(), 10, 100);
    let panel = benchmark_changed_panel(&large_fixture(), 10, 100);
    assert!(reducer.p95_ns < 25_000_000);
    assert!(panel.p95_ns < 50_000_000);
    assert_eq!(dirty_panel_calls(), 1);
}
```

- [ ] **Step 2: Run the release performance test and verify RED**

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --release --test performance --locked -- --nocapture`

Expected: FAIL because benchmark instrumentation is absent.

- [ ] **Step 3: Implement bounded benchmark instrumentation**

Implement the two exact functions above with `Instant`, record every raw sample,
sort a copy for median/p95/max, and expose dirty-panel renderer call counts plus
backend cell-write counts. Never hide or discard a threshold miss.

```rust
pub fn benchmark_reducer(fixture: &ConsoleSnapshot, warmups: usize, samples: usize) -> BenchmarkReceipt {
    for _ in 0..warmups { reduce_once(fixture); }
    BenchmarkReceipt::from_samples("reducer", (0..samples).map(|_| timed_ns(|| reduce_once(fixture))).collect())
}
```

- [ ] **Step 4: Run performance test and verify GREEN**

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --release --test performance --locked -- --nocapture`

Expected: PASS with raw measurements printed.

- [ ] **Step 5: Run all Python TUI tests**

Run: `$env:TEMP='C:\tmp\v20-tui-observability-temp'; $env:TMP='C:\tmp\v20-tui-observability-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-observability-pytest' -o cache_dir='C:\tmp\v20-tui-observability-cache' tests/platform/tui -q`

Expected: PASS.

- [ ] **Step 6: Run complete Rust checks**

Run: `cargo fmt --manifest-path "TUI testing/ratatui-console/Cargo.toml" -- --check`

Run: `cargo clippy --manifest-path "TUI testing/ratatui-console/Cargo.toml" --all-targets --locked -- -D warnings`

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --locked`

- [ ] **Step 7: Run the read-boundary proof**

Run: `$env:TEMP='C:\tmp\v20-tui-observability-temp'; $env:TMP='C:\tmp\v20-tui-observability-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-observability-pytest' -o cache_dir='C:\tmp\v20-tui-observability-cache' tests/platform/tui/projections tests/platform/tui/test_gateway.py -q`

Expected: PASS with broker, scheduler, training, and protected-path access spy
counts all zero. Launch the console against current V20 and confirm unavailable
portfolio/order areas stay unavailable rather than showing fixtures.

- [ ] **Step 8: Commit**

```powershell
git add -- 'tests/platform/tui/test_gateway.py' 'TUI testing/ratatui-console/tests/performance.rs' 'TUI testing/ratatui-console/README.md'
git commit -m "test(tui): verify complete read-only console"
```

## Phase acceptance

- All ten screens render real, stale, or unavailable data truthfully.
- The default Impact screen uses the approved portfolio-dominant layout.
- Portfolio row movement follows confirmed executed rank only.
- Agent cards use the approved Jira-style stages.
- Timeline defaults to impact and exposes all events with `e`.
- Search, filters, notes, mouse, keyboard, and drill-down work.
- Global search finds complete persisted event history and stored context notes,
  including records older than the 10,000-row snapshot window.
- Search preserves same-ID records of different exact types and never collapses
  model opinions with candidates or sources with repositories.
- Sequence gaps force a snapshot; required events are never silently dropped.
- No broker, scheduler, training, or protected-data path was accessed.
- Python, Rust, snapshot, and performance checks have fresh receipts.
