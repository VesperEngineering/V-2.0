# V20 Ratatui Governed Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add every approved button and command path while enabling only actions backed by a current controller-owned capability and returning a durable accepted or rejected receipt for every request.

**Architecture:** A Python command registry binds typed commands to capability checks, stale-state checks, authority validation, handlers, and an idempotent receipt store. Rust renders enabled and disabled controls from server capabilities, gathers risk-based confirmation, and never decides permission locally. Existing governed-platform actions are the first real handlers; trading, broker, risk, training, and runtime lifecycle use explicit unavailable ports until separately authorized adapters pass their contracts.

**Tech Stack:** Phase 1 and 2 stack plus Python command policies, SQLite receipts, registry-bound strict Pydantic payloads, and Ratatui modal controls.

**Status:** Approved; preflight corrections incorporated.

## Global Constraints

- Complete the foundation and observability plans first.
- A visible button is not evidence that its backend is enabled.
- Python is the final authority for every state-changing request.
- Rust sends the reviewed `control_version`, reviewed `control_hash`, command ID,
  reason, confirmation proof, and typed payload. It never sends operator identity.
- The gateway binds operator identity from the authenticated Windows pipe
  session and stores it in immutable `CommandContext`.
- Reject a mismatched control pair before any handler runs. Presentation version
  and event sequence never authorize commands.
- Safe reversible actions need no confirmation; state-changing actions need one confirmation; destructive/emergency actions need two; Live requires typed `ENABLE LIVE`.
- Cancel is selected by default in every confirmation.
- No second password is requested after the TUI is unlocked.
- An authenticated viewer may send the foundation `lease-request` without a
  current lease. All governed commands require the current lease. Take Control
  succeeds only after the prior controller releases it and is never implicit.
- Never expose credentials, environment values, or secrets in a receipt.
- Do not add a real broker, account, order, risk-setting, training, scheduler, or Live adapter in this plan.
- Tests for unavailable authority use fakes and assert zero legacy-runtime calls.
- Run every pytest command with `TEMP` and `TMP` set to
  `C:\tmp\v20-tui-controls-temp`, `--basetemp
  C:\tmp\v20-tui-controls-pytest`, and `-o
  cache_dir=C:\tmp\v20-tui-controls-cache`.
- Use test-first changes and one Conventional Commit per task.

---

## File map

```text
vesper/platform/tui/
|-- command_contracts.py       command payloads and receipts
|-- command_policy.py          risk, capability, and stale-state checks
|-- command_store.py           idempotent durable receipts
|-- command_registry.py        command-to-handler mapping
|-- operator_decisions.py      Hold/Rework records and notes
`-- command_ports.py           explicit service/risk/runtime/broker ports

tests/platform/tui/
|-- test_command_contracts.py
|-- test_command_policy.py
|-- test_command_store.py
|-- test_command_registry.py
|-- test_operator_decisions.py
`-- test_command_boundaries.py

TUI testing/ratatui-console/src/
|-- command.rs
|-- controls.rs
|-- confirm.rs
`-- screens/
    |-- risk.rs
    |-- agents.rs
    |-- system.rs
    `-- models.rs

TUI testing/ratatui-console/tests/
|-- command.rs
|-- controls.rs
`-- confirm.rs
```

### Task 1: Define command and receipt contracts

**Files:**
- Create: `vesper/platform/tui/command_contracts.py`
- Modify: `vesper/platform/tui/contracts.py`
- Create: `tests/platform/tui/test_command_contracts.py`
- Modify: `TUI testing/ratatui-console/src/contract.rs`
- Create: `TUI testing/ratatui-console/tests/command.rs`

**Interfaces:**
- Produces enum `ConfirmationLevel`: `none`, `confirm`, `double-confirm`, `typed-live`.
- Produces enum `ReceiptStatus`: `accepted`, `rejected`, `running`, `completed`, `failed`, `cancelled`.
- Produces `CommandRequest`, `CommandReceipt`, and one strict payload model per command.

- [ ] **Step 1: Write strict payload and secret rejection tests**

```python
def test_command_binds_reviewed_state_and_reason() -> None:
    request = CommandRequest(
        command_id="client-1:42",
        command_type="approval.reject",
        reviewed_control_version=19,
        reviewed_control_hash="7c222fb2927d828af22f592134e8932480637c0d1a3a6c9f5d6f0f975f6e3f43",
        reason="Evidence is stale",
        payload={"run_id": "run-1", "checkpoint_id": "cp-1"},
    )
    assert request.reviewed_control_version == 19
    assert "operator_id" not in request.model_fields


@pytest.mark.parametrize("command_type", tuple(PAYLOAD_MODELS))
def test_each_command_binds_only_its_exact_payload_model(command_type, valid_payloads) -> None:
    request = CommandRequest.model_validate({
        "command_id": f"client-1:{command_type}",
        "command_type": command_type,
        "reviewed_control_version": 19,
        "reviewed_control_hash": "7c222fb2927d828af22f592134e8932480637c0d1a3a6c9f5d6f0f975f6e3f43",
        "reason": valid_reason(command_type),
        "payload": valid_payloads[command_type],
    })
    assert type(request.payload) is PAYLOAD_MODELS[command_type]


@pytest.mark.parametrize("command_type", tuple(PAYLOAD_MODELS))
def test_each_command_rejects_a_different_payload_model(command_type, valid_payloads) -> None:
    wrong_type = next(t for t in PAYLOAD_MODELS if PAYLOAD_MODELS[t] is not PAYLOAD_MODELS[command_type])
    wrong_payload = PAYLOAD_MODELS[wrong_type].model_validate(valid_payloads[wrong_type])
    with pytest.raises(ValidationError, match="payload-model-mismatch"):
        CommandRequest.model_validate({
            "command_id": f"client-1:{command_type}",
            "command_type": command_type,
            "reviewed_control_version": 19,
            "reviewed_control_hash": "7c222fb2927d828af22f592134e8932480637c0d1a3a6c9f5d6f0f975f6e3f43",
            "reason": valid_reason(command_type),
            "payload": wrong_payload,
        })


def test_controls_snapshot_publishes_all_command_specs(base_snapshot) -> None:
    snapshot = base_snapshot.model_copy(update={"command_specs": COMMAND_SPECS})
    assert len(snapshot.command_specs) == 31
    assert {row.command_type for row in snapshot.command_specs} == set(PAYLOAD_MODELS)
```

```rust
#[test]
fn rust_reads_all_python_command_specs() {
    let snapshot: ConsoleSnapshot = fixture("controls_snapshot.json");
    assert_eq!(snapshot.command_specs.len(), 31);
    assert_eq!(snapshot.command_specs[0].payload_model, "NoteAddPayload");
}
```

Reject blank reasons where required, unknown command types, unknown payload
fields, account secrets, credential-like fields, negative control versions,
non-SHA-256 control hashes, any client-supplied operator field, and payloads
above 64 KiB. Rust must accept and reject the same fixtures.

- [ ] **Step 2: Run Python and Rust contract tests and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-controls-temp'; $env:TMP='C:\tmp\v20-tui-controls-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-controls-pytest' -o cache_dir='C:\tmp\v20-tui-controls-cache' tests/platform/tui/test_command_contracts.py -q`

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test command --locked`

Expected: FAIL because command contracts are absent.

- [ ] **Step 3: Define the exact command catalog**

```text
note.add
alert.dismiss
layout.reset
approval.approve
approval.hold
approval.reject
approval.rework
agent.send-message
agent.enqueue
agent.pause
agent.stop
agent.retry
agent.set-priority
risk.propose-limit
trading.pause
trading.emergency-stop
service.pause
service.restart
runtime.start
runtime.stop-safe
runtime.stop-force
runtime.prepare-shutdown
mode.switch
mode.leave-live
mode.enable-live
model.request-promotion
model.request-rollback
memory.compress-now
backup.create
backup.restore
source-control.push
```

Use these exact Python contracts; every payload class extends the foundation
`StrictModel`. Payload binding is registry-driven, not a Pydantic discriminated
union:

```python
GitRevision = Annotated[str, StringConstraints(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")]
ScreenName = Literal["impact", "portfolio", "orders", "agents", "models-regime", "timeline", "risk-approvals", "data-evidence", "memory", "system"]
CommandType = Literal[
    "note.add", "alert.dismiss", "layout.reset", "approval.approve",
    "approval.hold", "approval.reject", "approval.rework",
    "agent.send-message", "agent.enqueue", "agent.pause", "agent.stop",
    "agent.retry", "agent.set-priority", "risk.propose-limit",
    "trading.pause", "trading.emergency-stop", "service.pause",
    "service.restart", "runtime.start", "runtime.stop-safe",
    "runtime.stop-force", "runtime.prepare-shutdown", "mode.switch",
    "mode.leave-live", "mode.enable-live", "model.request-promotion",
    "model.request-rollback", "memory.compress-now", "backup.create",
    "backup.restore", "source-control.push",
]
ReasonRule = Literal["forbidden", "optional", "required"]
ConfirmationLevelValue = Literal["none", "confirm", "double-confirm", "typed-live"]

class EmptyPayload(StrictModel): pass
class NoteAddPayload(StrictModel):
    target_type: Literal["stock", "order", "approval", "agent-event"]
    target_id: SafeId
    body: Annotated[str, StringConstraints(min_length=1, max_length=8000)]
    visibility: Literal["private", "shared"]
class AlertDismissPayload(StrictModel):
    alert_id: SafeId
    created_at_utc: UtcDateTime
class LayoutResetPayload(StrictModel): screen: ScreenName | None = None
class ApprovalPayload(StrictModel): run_id: SafeId; checkpoint_id: SafeId
class ApprovalReworkPayload(ApprovalPayload): evidence_ids: tuple[SafeId, ...]
class AgentMessagePayload(StrictModel):
    agent_id: SafeId
    text: Annotated[str, StringConstraints(min_length=1, max_length=8000)]
    selected_entity_type: str | None = None
    selected_entity_id: SafeId | None = None
class AgentEnqueuePayload(StrictModel):
    agent_id: SafeId
    title: NonEmptyStr
    objective: Annotated[str, StringConstraints(min_length=1, max_length=8000)]
    priority: Annotated[int, Field(ge=0, le=100)]
class AgentWorkPayload(StrictModel): work_id: SafeId
class AgentStopPayload(AgentWorkPayload): workflow_run_id: SafeId | None = None
class AgentPriorityPayload(AgentWorkPayload): priority: Annotated[int, Field(ge=0, le=100)]
class RiskLimitPayload(StrictModel):
    limit_id: SafeId
    proposed_value: DecimalString
    evidence_ids: tuple[SafeId, ...]
class ServicePayload(StrictModel): service_id: SafeId
class RuntimeStartPayload(StrictModel):
    mode: Literal["shadow", "paper"]
    activation_receipt_id: SafeId
class ModeSwitchPayload(StrictModel): target_mode: Literal["shadow", "paper"]
class EnableLivePayload(StrictModel): desired_portfolio_id: SafeId
class ModelDecisionPayload(StrictModel):
    candidate_id: SafeId
    evidence_ids: tuple[SafeId, ...]
class CompressMemoryPayload(StrictModel): agent_id: SafeId
class BackupCreatePayload(StrictModel):
    destination: Annotated[str, StringConstraints(min_length=1, max_length=32767)]
class BackupRestorePayload(StrictModel):
    archive: Annotated[str, StringConstraints(min_length=1, max_length=32767)]
    preview_hash: Sha256Hex
    safety_backup_receipt_id: SafeId
class SourceControlPushPayload(StrictModel): expected_revision: GitRevision

class ConfirmationProof(StrictModel):
    first_confirmed: bool = False
    second_confirmed: bool = False
    typed_text: str | None = None
    bound_preview_hash: Sha256Hex | None = None

PAYLOAD_MODELS: Mapping[CommandType, type[StrictModel]] = MappingProxyType({
    "note.add": NoteAddPayload,
    "alert.dismiss": AlertDismissPayload,
    "layout.reset": LayoutResetPayload,
    "approval.approve": ApprovalPayload,
    "approval.hold": ApprovalPayload,
    "approval.reject": ApprovalPayload,
    "approval.rework": ApprovalReworkPayload,
    "agent.send-message": AgentMessagePayload,
    "agent.enqueue": AgentEnqueuePayload,
    "agent.pause": AgentWorkPayload,
    "agent.stop": AgentStopPayload,
    "agent.retry": AgentWorkPayload,
    "agent.set-priority": AgentPriorityPayload,
    "risk.propose-limit": RiskLimitPayload,
    "trading.pause": EmptyPayload,
    "trading.emergency-stop": EmptyPayload,
    "service.pause": ServicePayload,
    "service.restart": ServicePayload,
    "runtime.start": RuntimeStartPayload,
    "runtime.stop-safe": EmptyPayload,
    "runtime.stop-force": EmptyPayload,
    "runtime.prepare-shutdown": EmptyPayload,
    "mode.switch": ModeSwitchPayload,
    "mode.leave-live": ModeSwitchPayload,
    "mode.enable-live": EnableLivePayload,
    "model.request-promotion": ModelDecisionPayload,
    "model.request-rollback": ModelDecisionPayload,
    "memory.compress-now": CompressMemoryPayload,
    "backup.create": BackupCreatePayload,
    "backup.restore": BackupRestorePayload,
    "source-control.push": SourceControlPushPayload,
})

COMMAND_DECISIONS: Mapping[CommandType, tuple[ReasonRule, ConfirmationLevelValue]] = MappingProxyType({
    "note.add": ("forbidden", "none"),
    "alert.dismiss": ("forbidden", "none"),
    "layout.reset": ("forbidden", "none"),
    "approval.approve": ("optional", "confirm"),
    "approval.hold": ("required", "confirm"),
    "approval.reject": ("required", "confirm"),
    "approval.rework": ("required", "confirm"),
    "agent.send-message": ("forbidden", "none"),
    "agent.enqueue": ("required", "confirm"),
    "agent.pause": ("required", "confirm"),
    "agent.stop": ("required", "confirm"),
    "agent.retry": ("required", "confirm"),
    "agent.set-priority": ("required", "confirm"),
    "risk.propose-limit": ("required", "confirm"),
    "trading.pause": ("required", "confirm"),
    "trading.emergency-stop": ("required", "double-confirm"),
    "service.pause": ("required", "confirm"),
    "service.restart": ("required", "confirm"),
    "runtime.start": ("required", "confirm"),
    "runtime.stop-safe": ("required", "confirm"),
    "runtime.stop-force": ("required", "double-confirm"),
    "runtime.prepare-shutdown": ("required", "confirm"),
    "mode.switch": ("required", "confirm"),
    "mode.leave-live": ("required", "confirm"),
    "mode.enable-live": ("required", "typed-live"),
    "model.request-promotion": ("required", "confirm"),
    "model.request-rollback": ("required", "confirm"),
    "memory.compress-now": ("forbidden", "none"),
    "backup.create": ("optional", "confirm"),
    "backup.restore": ("required", "double-confirm"),
    "source-control.push": ("required", "confirm"),
})

class CommandRequest(StrictModel):
    command_id: SafeId
    command_type: CommandType
    reviewed_control_version: NonNegativeInt
    reviewed_control_hash: Sha256Hex
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)] | None
    confirmation: ConfirmationProof | None = None
    payload: SerializeAsAny[StrictModel]

    @model_validator(mode="before")
    @classmethod
    def bind_payload_model(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        command_type = value.get("command_type")
        if not isinstance(command_type, str):
            raise ValueError("unknown-command")
        payload_type = PAYLOAD_MODELS.get(command_type)
        if payload_type is None:
            raise ValueError("unknown-command")
        raw_payload = value.get("payload")
        if isinstance(raw_payload, StrictModel):
            if type(raw_payload) is not payload_type:
                raise ValueError("payload-model-mismatch")
            return value
        if not isinstance(raw_payload, dict):
            raise ValueError("payload-object-required")
        return {**value, "payload": payload_type.model_validate(raw_payload)}

    @model_validator(mode="after")
    def require_exact_payload_model(self) -> "CommandRequest":
        if type(self.payload) is not PAYLOAD_MODELS[self.command_type]:
            raise ValueError("payload-model-mismatch")
        return self

COMMAND_SPECS: tuple[CommandSpecView, ...] = tuple(
    CommandSpecView(
        command_type=command_type,
        payload_model=PAYLOAD_MODELS[command_type].__name__,
        capability_id=command_type,
        reason_rule=COMMAND_DECISIONS[command_type][0],
        confirmation_level=COMMAND_DECISIONS[command_type][1],
    )
    for command_type in PAYLOAD_MODELS
)

class CommandReceipt(StrictModel):
    command_id: SafeId
    status: ReceiptStatus
    code: SafeId
    safe_message: str
    accepted_at_utc: datetime | None
    finished_at_utc: datetime | None
    result: dict[str, JsonValue] | None

class CommandMessagePayload(StrictModel): request: CommandRequest
class CommandReceiptPayload(StrictModel): receipt: CommandReceipt
```

Add `MessageType.COMMAND = "command"` mapped only to
`CommandMessagePayload`, and `MessageType.COMMAND_RECEIPT = "command-receipt"`
mapped only to `CommandReceiptPayload`.

Take Control and Lock TUI use the foundation `lease-request` and `lock-request`
session messages. They are not governed V20 commands. `lock-request` must
invalidate server authentication and release the lease before returning
`lock-result`; the same pipe must unlock again before any snapshot or request.

Implement the exact payload model, capability ID, reason rule, and confirmation
level from `TUI testing/RATATUI_DESIGN.md` section 4.4. That decision table is
authoritative and complete; the catalog must contain exactly those 31 rows.
Keep the catalog in Python and transmit it in the snapshot; Rust does not
hard-code permission.

- [ ] **Step 4: Run contract tests and verify GREEN**

Run: `$env:TEMP='C:\tmp\v20-tui-controls-temp'; $env:TMP='C:\tmp\v20-tui-controls-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-controls-pytest' -o cache_dir='C:\tmp\v20-tui-controls-cache' tests/platform/tui/test_command_contracts.py -q`

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test command --locked`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add -- 'vesper/platform/tui/command_contracts.py' 'vesper/platform/tui/contracts.py' 'tests/platform/tui/test_command_contracts.py' 'TUI testing/ratatui-console/src/contract.rs' 'TUI testing/ratatui-console/tests/command.rs'
git commit -m "feat(tui): define governed command contracts"
```

### Task 2: Enforce capability, lease, and stale-state policy

**Files:**
- Create: `vesper/platform/tui/command_policy.py`
- Create: `tests/platform/tui/test_command_policy.py`

**Interfaces:**
- Produces: `CommandPolicy.authorize(context, request, spec) -> AuthorizationDecision`.
- Produces stable rejection codes: `locked`, `viewer`, `unknown-command`, `capability-disabled`, `stale-state`, `reason-required`, `confirmation-missing`, `typed-confirmation-mismatch`, `prerequisite-failed`.

```python
@dataclass(frozen=True, slots=True)
class CommandContext:
    operator_id: SafeId
    client_id: SafeId
    authenticated: bool
    owns_control_lease: bool
    control_version: int
    control_hash: Sha256Hex
    capabilities: Mapping[SafeId, CapabilityView]
    prerequisites: Mapping[str, JsonValue]


class CommandPolicy:
    def authorize(self, context: CommandContext, request: CommandRequest, spec: CommandSpecView) -> AuthorizationDecision: ...
```

- [ ] **Step 1: Write a policy decision table test**

Create one parameter row for every rejection code and one row for every command
catalog entry. Assert each command's exact capability, reason rule, and
confirmation level. Assert policy checks occur in this order: authenticated,
control lease, command known, capability enabled, reviewed control version and
hash current, reason present, confirmation valid, prerequisites current. Lease
and lock session messages are tested in foundation and never enter this policy.

```python
@pytest.mark.parametrize("code", ["locked", "viewer", "unknown-command", "capability-disabled", "stale-state", "reason-required", "confirmation-missing", "typed-confirmation-mismatch", "prerequisite-failed"])
def test_policy_rejects_before_handler(code, policy_case) -> None:
    decision = policy_case(code).authorize()
    assert decision.code == code
    assert policy_case(code).handler_calls == 0
```

- [ ] **Step 2: Run policy tests and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-controls-temp'; $env:TMP='C:\tmp\v20-tui-controls-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-controls-pytest' -o cache_dir='C:\tmp\v20-tui-controls-cache' tests/platform/tui/test_command_policy.py -q`

Expected: FAIL because policy is absent.

- [ ] **Step 3: Implement a pure policy object**

The policy receives immutable `CommandContext(operator_id, client_id,
control_version, control_hash, capabilities, prerequisites)` and performs no
handler calls, file writes, or logging of payload values. `mode.enable-live`
accepts only exact case-sensitive `ENABLE LIVE`. A changed data, model,
portfolio, code, evidence, reconciliation, incident, or approval prerequisite
changes the control pair and makes the reviewed command stale. CPU/GPU metrics,
clocks, layout, filters, chat, notes, and other presentation-only changes do not.

```python
def authorize(self, context: CommandContext, request: CommandRequest, spec: CommandSpecView) -> AuthorizationDecision:
    for check in (self._authenticated, self._lease, self._known, self._capability, self._control_pair, self._reason, self._confirmation, self._prerequisites):
        if rejection := check(context, request, spec):
            return rejection
    return AuthorizationDecision.allow()
```

- [ ] **Step 4: Run tests and verify GREEN**

Run: `$env:TEMP='C:\tmp\v20-tui-controls-temp'; $env:TMP='C:\tmp\v20-tui-controls-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-controls-pytest' -o cache_dir='C:\tmp\v20-tui-controls-cache' tests/platform/tui/test_command_policy.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add -- 'vesper/platform/tui/command_policy.py' 'tests/platform/tui/test_command_policy.py'
git commit -m "feat(tui): enforce command authority policy"
```

### Task 3: Store idempotent command receipts

**Files:**
- Create: `vesper/platform/tui/command_store.py`
- Create: `tests/platform/tui/test_command_store.py`

**Interfaces:**
- Produces exact methods:

```python
class CommandStore:
    def reject(self, request_hash: Sha256Hex, safe_request_metadata: SafeRequestMetadata, decision: AuthorizationDecision, rejected_at_utc: datetime) -> CommandReceipt: ...
    def accept(self, request: CommandRequest, context: CommandContext, handler_key: SafeId, accepted_at_utc: datetime) -> CommandReceipt: ...
    def claim(self, command_id: SafeId, worker_id: SafeId, lease_expires_at_utc: datetime) -> CommandReceipt | None: ...
    def finish(self, command_id: SafeId, status: ReceiptStatus, result: dict[str, JsonValue] | None, finished_at_utc: datetime) -> CommandReceipt: ...
    def get(self, command_id: SafeId) -> CommandReceipt | None: ...
    def list(self, limit: int, cursor: SafeId | None) -> tuple[CommandReceipt, ...]: ...
    def expired_running(self, now_utc: datetime) -> tuple[CommandReceipt, ...]: ...
```

- [ ] **Step 1: Write replay, conflict, crash, and redaction tests**

Assert every typed policy rejection is durably recorded; exact replay returns
the original rejected or accepted receipt; conflicting use of one command ID is
rejected; accepted-without-finish reopens as `running`; expired worker claims
are listed for recovery; terminal states cannot change; receipts survive reopen;
and safe results exclude keys matching `secret`, `token`, `password`,
`credential`, and `api_key`. Store only safe command metadata for rejected
requests, never rejected payload values.

```python
def test_conflicting_replay_never_repeats_effect(store, request) -> None:
    original = store.accept(request, CONTEXT, "handler", UTC_NOW)
    assert store.accept(request, CONTEXT, "handler", UTC_NOW) == original
    with pytest.raises(CommandConflict):
        store.accept(request.model_copy(update={"payload": OTHER_PAYLOAD}), CONTEXT, "handler", UTC_NOW)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-controls-temp'; $env:TMP='C:\tmp\v20-tui-controls-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-controls-pytest' -o cache_dir='C:\tmp\v20-tui-controls-cache' tests/platform/tui/test_command_store.py -q`

Expected: FAIL because the store is absent.

- [ ] **Step 3: Implement the receipt ledger**

Use SQLite WAL and one transaction for request hash plus the accepted or rejected
receipt. Hash canonical request JSON with SHA-256. Store context-bound operator
identity, control pair, handler key, worker claim, and status transitions in an
append-only receipt-events table and the latest status in a materialized command
row. A worker must claim an accepted command before calling a handler.

```python
def accept(self, request, context, handler_key, accepted_at_utc):
    request_hash = sha256(canonical_json(request)).hexdigest()
    with self._transaction():
        return self._insert_or_replay(request.command_id, request_hash, context, handler_key, accepted_at_utc)
```

- [ ] **Step 4: Run tests and verify GREEN**

Run: `$env:TEMP='C:\tmp\v20-tui-controls-temp'; $env:TMP='C:\tmp\v20-tui-controls-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-controls-pytest' -o cache_dir='C:\tmp\v20-tui-controls-cache' tests/platform/tui/test_command_store.py -q`

Expected: PASS including process-reopen tests.

- [ ] **Step 5: Commit**

```powershell
git add -- 'vesper/platform/tui/command_store.py' 'tests/platform/tui/test_command_store.py'
git commit -m "feat(tui): persist command receipts"
```

### Task 4: Route current safe platform actions

**Files:**
- Create: `vesper/platform/tui/command_ports.py`
- Create: `vesper/platform/tui/operator_decisions.py`
- Create: `vesper/platform/tui/command_registry.py`
- Modify: `vesper/platform/tui/gateway.py`
- Create: `tests/platform/tui/test_operator_decisions.py`
- Create: `tests/platform/tui/test_command_registry.py`

**Interfaces:**
- Produces protocol `PlatformCommandPort` for command-ID-bound approve, reject,
  cancel, enqueue, and read-current-state.
- Produces protocol `AgentActionPort` for send-message, pause, stop, retry, and
  set-priority. Its default implementation returns explicit disabled reasons.
- Produces protocol `RecoverableCommandPort.recover(command_id) ->
  Literal["not-started", "completed", "failed", "unknown"]`.
- Produces protocols whose default implementations return explicit disabled capability for risk, trading, runtime, service, model, backup, memory, and source control.
- Produces: `CommandRegistry.execute(context, request) -> CommandReceipt`.
- Produces: `CommandRegistry.recover_running(now_utc) -> tuple[CommandReceipt, ...]`.

```python
class PlatformCommandPort(Protocol):
    def approve_run(self, command_id: SafeId, run_id: SafeId, checkpoint_id: SafeId) -> PortResult: ...
    def reject_run(self, command_id: SafeId, run_id: SafeId, checkpoint_id: SafeId, reason: str) -> PortResult: ...
    def cancel_run(self, command_id: SafeId, run_id: SafeId, reason: str) -> PortResult: ...
    def enqueue(self, command_id: SafeId, payload: AgentEnqueuePayload) -> PortResult: ...
    def read_current_state(self) -> ControlState: ...

class AgentActionPort(Protocol):
    def send_message(self, command_id: SafeId, payload: AgentMessagePayload) -> PortResult: ...
    def pause(self, command_id: SafeId, work_id: SafeId) -> PortResult: ...
    def stop(self, command_id: SafeId, payload: AgentStopPayload) -> PortResult: ...
    def retry(self, command_id: SafeId, work_id: SafeId) -> PortResult: ...
    def set_priority(self, command_id: SafeId, payload: AgentPriorityPayload) -> PortResult: ...

class RecoverableCommandPort(Protocol):
    def recover(self, command_id: SafeId) -> Literal["not-started", "completed", "failed", "unknown"]: ...

class CommandRegistry:
    def execute(self, context: CommandContext, request: CommandRequest) -> CommandReceipt: ...
    def recover_running(self, now_utc: datetime) -> tuple[CommandReceipt, ...]: ...

class MessageRoutingPort(Protocol):
    def route(self, text: str, screen: ScreenName, selected_entity: EntityRef | None) -> AgentRouteView: ...
```

- [ ] **Step 1: Write handler-spy and disabled-port tests**

Test `approval.approve` calls exactly one `approve_run`, `approval.reject` calls
exactly one `reject_run`, and agent enqueue calls exactly one bounded queue
method. Test a stale request calls no handler. Test all disabled ports return the
configured reason and call no legacy object. Test send-message, pause, stop,
retry, and priority are disabled unless an explicit agent-action adapter supplies
that exact method. Test crashes before claim, after claim/before handler, after
handler/before finish, and after finish. Recovery must produce one terminal
receipt without repeating a completed effect.

Contract fakes must also prove the future enabled semantics: a tighter approved
risk limit becomes effective immediately, blocks new risk when violated, and
creates a corrective plan whose broker orders still need approval; a higher
limit changes permission without forcing a trade. Pause Trading leaves existing
orders alone. Emergency Stop requests cancellation of every open order. Safe
Stop drains/checkpoints, Force Stop uses the second warning, and service recovery
tries one safe restart before raising an alert.

```python
def test_stale_request_calls_no_port(registry, stale_context, request, port_spy) -> None:
    receipt = registry.execute(stale_context, request)
    assert receipt.code == "stale-state"
    assert port_spy.calls == []
```

- [ ] **Step 2: Run tests and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-controls-temp'; $env:TMP='C:\tmp\v20-tui-controls-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-controls-pytest' -o cache_dir='C:\tmp\v20-tui-controls-cache' tests/platform/tui/test_operator_decisions.py tests/platform/tui/test_command_registry.py -q`

Expected: FAIL because command routing is absent.

- [ ] **Step 3: Implement enabled operator actions**

- `approval.approve`: call existing `LocalPlatformService.approve_run`; keep the
  returned `resume_required` visible and do not resume automatically.
- `approval.reject`: call existing `reject_run` with operator and reason.
- `approval.hold`: retain the pending controller approval and append a TUI
  operator-decision record with reason.
- `approval.rework`: retain the pending approval, append the decision, and
  enqueue one bounded agent work item linked to run/checkpoint/evidence.
- `agent.enqueue`: call the current bounded queue through a typed port using a
  deterministic work ID derived from `command_id`; replay returns the existing
  item instead of enqueueing twice.
- `alert.dismiss`, `note.add`, and `layout.reset`: call only their TUI-owned
  stores/services.

`alert.dismiss` carries the alert ID and reviewed `created_at_utc`. Admission
must compare both fields with the current controller alert before writing a
command or binding. A resolved/reopened alert with the same ID is a new
occurrence and requires a new review. Binding, dismissal, recovery, and receipt
must keep the original pair exact. Use a completion time no earlier than the
worker claim or bound alert timestamp so a clock rollback cannot create an
invalid durable ledger. Admission and capability state allow dismissal only
for a resolved alert. Projection suppression also applies only to that exact
resolved occurrence; urgent alerts always remain visible.

Every enabled port receives `command_id` as its downstream idempotency key.
Approve/reject recovery reads the checkpoint decision; enqueue recovery reads
the deterministic work ID; TUI-store handlers commit effect and terminal receipt
in one SQLite transaction. If a future external adapter returns `unknown`, mark
the receipt `failed` with `manual-intervention-required` and never reissue it.
At console startup, expired TUI-owned commands recover even when platform
runtime truth is unavailable. External commands remain untouched until runtime
truth is fresh.

Add `MessageRoutingPort.route(text, screen, selected_entity) -> AgentRouteView`.
Routes use only exact existing `AgentRole` values: Portfolio to
`v20-portfolio-researcher`, Models to `v20-model-researcher`, Risk to
`v20-risk-review`, Data to `v20-quant-research-lead`, System/code to
`v20-development`, and Impact/Agents/Timeline/Memory to `v20-product`. Return
agent, reason, confidence, and `send_capability`. `agent.send-message` requires
the routed agent ID or an operator override and displays that choice before
sending. A route may be valid while sending is disabled; never substitute a
different role.

```python
def populate_command_specs(snapshot: ConsoleSnapshot) -> ConsoleSnapshot:
    return snapshot.model_copy(update={"command_specs": COMMAND_SPECS})
```

The controls gateway calls `populate_command_specs` on every full snapshot;
observability alone continues to publish the neutral empty tuple.

```python
def execute(self, context: CommandContext, request: CommandRequest) -> CommandReceipt:
    spec = self._specs[request.command_type]
    decision = self._policy.authorize(context, request, spec)
    if not decision.allowed:
        return self._store.reject(hash_request(request), safe_metadata(request), decision, utc_now())
    accepted = self._store.accept(request, context, self._handlers[request.command_type].key, utc_now())
    return self._run_claimed_once(accepted, request)
```

Do not enable `cancel_run` as an agent Stop substitute unless the selected card
is an actual workflow run and the gateway has its exact run ID.

Default agent-action reasons are exact: `No controller-owned agent message port
is configured.`, `No controller-owned pause port is configured.`, `No
controller-owned retry port is configured.`, and `No controller-owned priority
port is configured.` Stop is enabled only for an exact workflow run ID through
`cancel_run`; otherwise it returns `The selected work item has no reviewed stop
adapter.`

- [ ] **Step 4: Register unavailable controls with exact reasons**

Register these exact phase-3 disabled reasons:

```text
risk.propose-limit -> No controller-owned risk settings port is configured.
trading.pause -> No controller-owned trading control port is configured.
trading.emergency-stop -> No controller-owned trading control port is configured.
service.pause -> No reviewed service supervisor is configured.
service.restart -> No reviewed service supervisor is configured.
runtime.start -> No reviewed runtime manager is configured.
runtime.stop-safe -> No reviewed runtime manager is configured.
runtime.stop-force -> No reviewed runtime manager is configured.
runtime.prepare-shutdown -> No reviewed runtime manager is configured.
mode.switch -> No reviewed runtime mode manager is configured.
mode.leave-live -> No reviewed runtime mode manager is configured.
mode.enable-live -> Live broker activation is not configured or authorized.
model.request-promotion -> No reviewed model promotion port is configured.
model.request-rollback -> No reviewed model rollback port is configured.
memory.compress-now -> No controller-owned context compression port is configured.
backup.create -> Backup service is not installed.
backup.restore -> Backup service is not installed.
source-control.push -> Source-control command port is not installed.
agent.send-message -> No controller-owned agent message port is configured.
agent.pause -> No controller-owned pause port is configured.
agent.retry -> No controller-owned retry port is configured.
agent.set-priority -> No controller-owned priority port is configured.
agent.stop -> The selected work item has no reviewed stop adapter.
```

- [ ] **Step 5: Run tests and verify GREEN**

Run: `$env:TEMP='C:\tmp\v20-tui-controls-temp'; $env:TMP='C:\tmp\v20-tui-controls-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-controls-pytest' -o cache_dir='C:\tmp\v20-tui-controls-cache' tests/platform/tui/test_operator_decisions.py tests/platform/tui/test_command_registry.py -q`

Expected: PASS with zero broker, scheduler, trainer, and protected-path calls.

- [ ] **Step 6: Commit**

```powershell
git add -- 'vesper/platform/tui/command_ports.py' 'vesper/platform/tui/operator_decisions.py' 'vesper/platform/tui/command_registry.py' 'vesper/platform/tui/gateway.py' 'tests/platform/tui/test_operator_decisions.py' 'tests/platform/tui/test_command_registry.py'
git commit -m "feat(tui): route bounded operator actions"
```

### Task 5: Model Live readiness without enabling Live

**Files:**
- Modify: `vesper/platform/tui/views.py`
- Modify: `vesper/platform/tui/command_ports.py`
- Create: `tests/platform/tui/test_live_readiness.py`

**Interfaces:**
- Produces `LiveReadinessView` with broker, account, data, model, strategy, risk, reconciliation, incident, and authority gates.
- Produces `TransitionPlanView` from actual broker holdings to desired holdings when a future approved port supplies both.

```python
class ReadinessGate(StrictModel):
    state: Literal["ready", "blocked", "unavailable", "stale"]
    reason: NonEmptyStr

class LiveReadinessView(StrictModel):
    broker: ReadinessGate
    account: ReadinessGate
    data: ReadinessGate
    model: ReadinessGate
    strategy: ReadinessGate
    risk: ReadinessGate
    reconciliation: ReadinessGate
    incident: ReadinessGate
    authority: ReadinessGate
    enabled: bool

class TransitionOrderView(StrictModel):
    symbol: SafeId
    side: Literal["buy", "sell"]
    quantity: DecimalString
    approval_required: Literal[True]

class TransitionPlanView(StrictModel):
    broker_positions_as_of_utc: datetime
    desired_portfolio_id: SafeId
    orders: tuple[TransitionOrderView, ...]
```

- [ ] **Step 1: Write all-gates and no-paper-copy tests**

Assert Live is disabled if any gate is false, stale, or unavailable. Assert the
transition plan consumes broker positions and desired targets, never Paper
positions. Assert every generated buy/sell remains approval-required.
Assert one active portfolio is shown: Shadow or Paper before activation, and
the reconciled broker-backed portfolio after Live activation.

```python
def test_live_readiness_fails_if_one_gate_is_not_ready() -> None:
    view = build_live_readiness(all_ready_except("reconciliation", "stale"))
    assert view.enabled is False
    assert build_transition_plan(PAPER_POSITIONS, DESIRED) is None
```

- [ ] **Step 2: Run tests and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-controls-temp'; $env:TMP='C:\tmp\v20-tui-controls-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-controls-pytest' -o cache_dir='C:\tmp\v20-tui-controls-cache' tests/platform/tui/test_live_readiness.py -q`

Expected: FAIL because readiness is absent.

- [ ] **Step 3: Implement readiness as a pure view calculation**

The default real view sets broker/account/reconciliation/authority unavailable
and produces no transition plan. Account fields support a remembered privacy
mask but credentials have no model field at all.

```python
def build_live_readiness(gates: tuple[ReadinessGate, ...]) -> LiveReadinessView:
    return LiveReadinessView(**index_gates(gates), enabled=all(g.state == "ready" for g in gates))
```

- [ ] **Step 4: Run tests and verify GREEN**

Run: `$env:TEMP='C:\tmp\v20-tui-controls-temp'; $env:TMP='C:\tmp\v20-tui-controls-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-controls-pytest' -o cache_dir='C:\tmp\v20-tui-controls-cache' tests/platform/tui/test_live_readiness.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add -- 'vesper/platform/tui/views.py' 'vesper/platform/tui/command_ports.py' 'tests/platform/tui/test_live_readiness.py'
git commit -m "feat(tui): show fail-closed Live readiness"
```

### Task 6: Render controls and risk-based confirmations

**Files:**
- Create: `TUI testing/ratatui-console/src/command.rs`
- Create: `TUI testing/ratatui-console/src/controls.rs`
- Create: `TUI testing/ratatui-console/src/confirm.rs`
- Modify: `TUI testing/ratatui-console/src/app.rs`
- Modify: `TUI testing/ratatui-console/src/input.rs`
- Modify: `TUI testing/ratatui-console/src/screens/agents.rs`
- Modify: `TUI testing/ratatui-console/src/screens/risk.rs`
- Modify: `TUI testing/ratatui-console/src/screens/models.rs`
- Modify: `TUI testing/ratatui-console/src/screens/system.rs`
- Create: `TUI testing/ratatui-console/tests/controls.rs`
- Create: `TUI testing/ratatui-console/tests/confirm.rs`

**Interfaces:**
- Produces one button state from server command specs: enabled, disabled with reason, or hidden only when irrelevant to the selected entity.
- Produces confirmation modals for all four levels.

```rust
pub enum ButtonState { Enabled, Disabled { reason: String }, Hidden }
pub enum ConfirmationLevel { None, Confirm, DoubleConfirm, TypedLive }

pub fn button_state(spec: &CommandSpecView, capability: &CapabilityView, relevant: bool) -> ButtonState;
pub fn begin_confirmation(spec: &CommandSpecView, request: PendingCommand) -> ConfirmationState;
pub fn submit_confirmation(state: &ConfirmationState) -> Result<CommandRequest, ConfirmationError>;
```

- [ ] **Step 1: Write keyboard, mouse, disabled, and modal tests**

Assert safe actions send immediately, confirm actions require one approval,
Emergency Stop and Force Stop require two, Live requires exact typed text,
Cancel is initial selection, Esc cancels, a viewer sees Take Control, disabled
buttons open their reason but send no command, and rapid double activation sends
one command ID. Assert the routed agent is visible and can be changed before
sending. Assert the account privacy toggle masks name, number, balance, and
capital, persists locally, and does not alter the server snapshot. Generate one
case from every server command spec and assert the rendered confirmation level
matches it. `backup.restore` additionally requires a validated preview hash,
successful automatic safety-backup receipt, stopped runtime, and confirmation
bound to that preview hash. Viewer Take Control uses `lease-request`; Lock TUI
uses `lock-request` and locally hides all state immediately while awaiting the
server result.

```rust
#[test]
fn restore_requires_preview_safety_backup_and_double_confirmation() {
    let state = begin_confirmation(&restore_spec(), restore_request());
    assert!(submit_confirmation(&state).is_err());
    assert_eq!(state.initial_selection(), Selection::Cancel);
}
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test controls --test confirm --locked`

Expected: FAIL because controls are absent.

- [ ] **Step 3: Render every approved control now**

Agents: Pause, Stop, Retry, priority, Send.

Risk: edit Proposed limits, Pause Trading, Emergency Stop, Approve, Hold, Reject,
Rework. Hold, Reject, and Rework show quick reasons plus an optional note.

Models: candidate detail, approval request, rollback request.

System: service Pause/Restart, Start V20 with Shadow selected, Stop Safely, Force
Stop, Prepare for PC Shutdown, Backup Now, Restore, Push, Lock TUI.

Unavailable controls remain visible with the server reason. Completed receipts
update in place and link into Timeline.

```rust
pub fn begin_confirmation(spec: &CommandSpecView, request: PendingCommand) -> ConfirmationState {
    ConfirmationState::new(spec.confirmation_level, request).with_initial_selection(Selection::Cancel)
}
```

- [ ] **Step 4: Inspect modal snapshots**

Snapshot every confirmation level, disabled reason, rejected stale command,
running receipt, completed receipt, failed receipt, and viewer state in both
themes and Large Text.

- [ ] **Step 5: Run Rust tests and verify GREEN**

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test controls --test confirm --locked`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add -- 'TUI testing/ratatui-console/src/command.rs' 'TUI testing/ratatui-console/src/controls.rs' 'TUI testing/ratatui-console/src/confirm.rs' 'TUI testing/ratatui-console/src/app.rs' 'TUI testing/ratatui-console/src/input.rs' 'TUI testing/ratatui-console/src/screens/agents.rs' 'TUI testing/ratatui-console/src/screens/risk.rs' 'TUI testing/ratatui-console/src/screens/models.rs' 'TUI testing/ratatui-console/src/screens/system.rs' 'TUI testing/ratatui-console/tests/controls.rs' 'TUI testing/ratatui-console/tests/confirm.rs'
git commit -m "feat(tui): add governed console controls"
```

### Task 7: Prove command boundaries end to end

**Files:**
- Create: `tests/platform/tui/test_command_boundaries.py`
- Modify: `tests/platform/tui/test_gateway.py`
- Create: `TUI testing/ratatui-console/tests/command_e2e.rs`
- Modify: `TUI testing/ratatui-console/README.md`

**Interfaces:**
- Produces one fake-gateway end-to-end test suite and one current-platform local integration suite.

```python
@dataclass(frozen=True, slots=True)
class BoundaryScenario:
    context: CommandContext
    request: CommandRequest
    expected_code: SafeId
    expected_handler_calls: int
```

- [ ] **Step 1: Add end-to-end boundary cases**

Cover locked, viewer, stale, disabled, confirmed, double-confirmed, typed Live,
duplicate, disconnect-after-accept, reconnect-to-original-receipt, handler
failure, durable rejected receipt, secret-shaped result, changed prerequisite,
crash before handler, crash after handler/before receipt finish, deterministic
recovery, same-pipe lock/re-unlock, and presentation-only changes that leave the
control pair valid. Use fakes for all financial/runtime commands.

```python
def test_boundary_scenarios_have_exact_receipts(boundary_gateway, scenarios) -> None:
    for scenario in scenarios:
        receipt = boundary_gateway.send(scenario.context, scenario.request)
        assert receipt.code == scenario.expected_code
        assert boundary_gateway.handler_calls == scenario.expected_handler_calls
```

- [ ] **Step 2: Run new boundary tests and verify RED**

Run: `$env:TEMP='C:\tmp\v20-tui-controls-temp'; $env:TMP='C:\tmp\v20-tui-controls-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-controls-pytest' -o cache_dir='C:\tmp\v20-tui-controls-cache' tests/platform/tui/test_command_boundaries.py -q`

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test command_e2e --locked`

Expected: FAIL because the fake gateway harness and capability matrix are absent.

- [ ] **Step 3: Implement the deterministic boundary harness**

Build a fake gateway from the real `CommandPolicy`, `CommandStore`, and
`CommandRegistry` with spy ports. Each `BoundaryScenario` sends one serialized
request through framing, auth, lease, policy, store, handler, and receipt
reduction. The README capability matrix lists all 31 commands and current
enabled/disabled reason without claiming a real financial/runtime adapter.

```python
def build_boundary_gateway(tmp_path, spy_ports) -> Gateway:
    store = CommandStore(tmp_path / "commands.db")
    registry = CommandRegistry(CommandPolicy(), store, spy_ports, COMMAND_SPECS)
    return Gateway(command_registry=registry, command_specs=COMMAND_SPECS)
```

- [ ] **Step 4: Run focused boundary tests and verify GREEN**

Run: `$env:TEMP='C:\tmp\v20-tui-controls-temp'; $env:TMP='C:\tmp\v20-tui-controls-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-controls-pytest' -o cache_dir='C:\tmp\v20-tui-controls-cache' tests/platform/tui/test_command_boundaries.py -q`

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --test command_e2e --locked`

Expected: PASS.

- [ ] **Step 5: Run the complete Python TUI and platform safety suites**

Run: `$env:TEMP='C:\tmp\v20-tui-controls-temp'; $env:TMP='C:\tmp\v20-tui-controls-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-controls-pytest' -o cache_dir='C:\tmp\v20-tui-controls-cache' tests/platform/tui -q`

Run: `$env:TEMP='C:\tmp\v20-tui-controls-temp'; $env:TMP='C:\tmp\v20-tui-controls-temp'; uv run --locked python -m pytest --basetemp 'C:\tmp\v20-tui-controls-pytest' -o cache_dir='C:\tmp\v20-tui-controls-cache' tests/platform/test_authority_boundaries.py tests/platform/test_service.py tests/platform/test_control.py -q`

Expected: PASS.

- [ ] **Step 6: Run complete Rust checks**

Run: `cargo fmt --manifest-path "TUI testing/ratatui-console/Cargo.toml" -- --check`

Run: `cargo clippy --manifest-path "TUI testing/ratatui-console/Cargo.toml" --all-targets --locked -- -D warnings`

Run: `cargo test --manifest-path "TUI testing/ratatui-console/Cargo.toml" --locked`

- [ ] **Step 7: Manually inspect current capability truth**

Open the TUI locally. Confirm current platform approvals/actions reflect their
real state. Confirm broker, risk, Live, training, scheduler, service, backup,
restore, and push controls are disabled and explain why. Send no real command.

- [ ] **Step 8: Commit**

```powershell
git add -- 'tests/platform/tui/test_command_boundaries.py' 'tests/platform/tui/test_gateway.py' 'TUI testing/ratatui-console/tests/command_e2e.rs' 'TUI testing/ratatui-console/README.md'
git commit -m "test(tui): prove governed command boundaries"
```

## Phase acceptance

- Every approved button exists.
- Only controller-backed current actions are enabled.
- Disabled actions explain the missing adapter or authority.
- Stale state, viewer state, and missing confirmation call no handler.
- Every request has one idempotent durable receipt.
- Expired running receipts recover to one terminal result without repeating a
  completed effect.
- Existing workflow approval/rejection and bounded queue actions retain their current authority checks.
- Live remains disabled without every readiness gate.
- No real broker, risk setting, order, scheduler, trainer, or runtime was touched.
