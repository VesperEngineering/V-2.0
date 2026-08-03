# V20 Ratatui Governed Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add every approved button and command path while enabling only actions backed by a current controller-owned capability and returning a durable accepted or rejected receipt for every request.

**Architecture:** A Python command registry binds typed commands to capability checks, stale-state checks, authority validation, handlers, and an idempotent receipt store. Rust renders enabled and disabled controls from server capabilities, gathers risk-based confirmation, and never decides permission locally. Existing governed-platform actions are the first real handlers; trading, broker, risk, training, and runtime lifecycle use explicit unavailable ports until separately authorized adapters pass their contracts.

**Tech Stack:** Phase 1 and 2 stack plus Python command policies, SQLite receipts, Pydantic discriminated payloads, and Ratatui modal controls.

## Global Constraints

- Complete the foundation and observability plans first.
- A visible button is not evidence that its backend is enabled.
- Python is the final authority for every state-changing request.
- Rust sends the state version, command ID, operator identity, reason, and typed payload.
- Reject stale commands before any handler runs.
- Safe reversible actions need no confirmation; state-changing actions need one confirmation; destructive/emergency actions need two; Live requires typed `ENABLE LIVE`.
- Cancel is selected by default in every confirmation.
- No second password is requested after the TUI is unlocked.
- A viewer cannot send a command and cannot silently acquire control.
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
        reviewed_state_version=19,
        operator_id="windows-user",
        reason="Evidence is stale",
        payload={"run_id": "run-1", "checkpoint_id": "cp-1"},
    )
    assert request.reviewed_state_version == 19
```

Reject blank reasons where required, unknown command types, unknown payload
fields, account secrets, credential-like fields, negative state versions, and
payloads above 64 KiB. Rust must accept and reject the same fixtures.

- [ ] **Step 2: Run Python and Rust contract tests and verify RED**

Expected: FAIL because command contracts are absent.

- [ ] **Step 3: Define the exact command catalog**

```text
note.add
alert.dismiss
layout.reset
lease.take-control
tui.lock
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

Each command type maps to one payload model, confirmation level, required
capability ID, and reason rule. Keep the catalog in Python and transmit it in
the snapshot; Rust does not hard-code permission.

- [ ] **Step 4: Run contract tests and verify GREEN**

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat(tui): define governed command contracts`

### Task 2: Enforce capability, lease, and stale-state policy

**Files:**
- Create: `vesper/platform/tui/command_policy.py`
- Create: `tests/platform/tui/test_command_policy.py`

**Interfaces:**
- Produces: `CommandPolicy.authorize(context, request, spec) -> AuthorizationDecision`.
- Produces stable rejection codes: `locked`, `viewer`, `unknown-command`, `capability-disabled`, `stale-state`, `reason-required`, `confirmation-missing`, `typed-confirmation-mismatch`, `prerequisite-failed`.

- [ ] **Step 1: Write a policy decision table test**

Create one parameter row for every rejection code and one allow row per
confirmation level. Assert policy checks occur in this order: authenticated,
control lease, command known, capability enabled, reviewed state current,
reason present, confirmation valid, prerequisites current.

- [ ] **Step 2: Run policy tests and verify RED**

Run: `uv run --locked python -m pytest tests/platform/tui/test_command_policy.py -q`

Expected: FAIL because policy is absent.

- [ ] **Step 3: Implement a pure policy object**

The policy receives immutable context and performs no handler calls, file
writes, or logging of payload values. `mode.enable-live` accepts only exact
case-sensitive `ENABLE LIVE`. A changed data, model, portfolio, code, evidence,
or approval version makes the reviewed state stale.

- [ ] **Step 4: Run tests and verify GREEN**

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat(tui): enforce command authority policy`

### Task 3: Store idempotent command receipts

**Files:**
- Create: `vesper/platform/tui/command_store.py`
- Create: `tests/platform/tui/test_command_store.py`

**Interfaces:**
- Produces: `CommandStore.begin(request, accepted_at) -> CommandReceipt`.
- Produces: `CommandStore.finish(command_id, status, result, finished_at) -> CommandReceipt`.
- Produces: `CommandStore.get(command_id) -> CommandReceipt | None`.
- Produces: `CommandStore.list(limit, cursor) -> tuple[CommandReceipt, ...]`.

- [ ] **Step 1: Write replay, conflict, crash, and redaction tests**

Assert exact replay returns the original receipt, conflicting use of one command
ID is rejected, accepted-without-finish reopens as `running`, terminal states
cannot change, receipts survive reopen, and safe results exclude keys matching
`secret`, `token`, `password`, `credential`, and `api_key`.

- [ ] **Step 2: Run tests and verify RED**

Expected: FAIL because the store is absent.

- [ ] **Step 3: Implement the receipt ledger**

Use SQLite WAL and one transaction for request hash plus accepted receipt. Hash
canonical request JSON with SHA-256. Store status transitions in an append-only
receipt-events table and the latest status in a materialized command row.

- [ ] **Step 4: Run tests and verify GREEN**

Expected: PASS including process-reopen tests.

- [ ] **Step 5: Commit**

Commit: `feat(tui): persist command receipts`

### Task 4: Route current safe platform actions

**Files:**
- Create: `vesper/platform/tui/command_ports.py`
- Create: `vesper/platform/tui/operator_decisions.py`
- Create: `vesper/platform/tui/command_registry.py`
- Modify: `vesper/platform/tui/gateway.py`
- Create: `tests/platform/tui/test_operator_decisions.py`
- Create: `tests/platform/tui/test_command_registry.py`

**Interfaces:**
- Produces protocol `PlatformCommandPort` for approve, reject, cancel, enqueue, and read-current-state.
- Produces protocols whose default implementations return explicit disabled capability for risk, trading, runtime, service, model, backup, memory, and source control.
- Produces: `CommandRegistry.execute(context, request) -> CommandReceipt`.

- [ ] **Step 1: Write handler-spy and disabled-port tests**

Test `approval.approve` calls exactly one `approve_run`, `approval.reject` calls
exactly one `reject_run`, and agent enqueue calls exactly one bounded queue
method. Test a stale request calls no handler. Test all disabled ports return the
configured reason and call no legacy object.

Contract fakes must also prove the future enabled semantics: a tighter approved
risk limit becomes effective immediately, blocks new risk when violated, and
creates a corrective plan whose broker orders still need approval; a higher
limit changes permission without forcing a trade. Pause Trading leaves existing
orders alone. Emergency Stop requests cancellation of every open order. Safe
Stop drains/checkpoints, Force Stop uses the second warning, and service recovery
tries one safe restart before raising an alert.

- [ ] **Step 2: Run tests and verify RED**

Expected: FAIL because command routing is absent.

- [ ] **Step 3: Implement enabled operator actions**

- `approval.approve`: call existing `LocalPlatformService.approve_run`; keep the
  returned `resume_required` visible and do not resume automatically.
- `approval.reject`: call existing `reject_run` with operator and reason.
- `approval.hold`: retain the pending controller approval and append a TUI
  operator-decision record with reason.
- `approval.rework`: retain the pending approval, append the decision, and
  enqueue one bounded agent work item linked to run/checkpoint/evidence.
- `agent.enqueue`: call the current bounded queue through a typed port.
- `alert.dismiss`, `note.add`, `layout.reset`, and `lease.take-control`: call only
  their TUI-owned stores/services.
- `tui.lock`: release the control lease, clear authenticated Rust state, and
  return to the password screen without stopping V20.

Add `MessageRoutingPort.route(text, screen, selected_entity) -> AgentRouteView`.
The default deterministic route is Portfolio to Portfolio Researcher, Models to
Model Researcher, Risk to Risk Review, Data to Data Researcher, System/code to
Development, and Impact/Agents/Timeline/Memory to Product. Return agent, reason,
and confidence. `agent.send-message` requires the routed agent ID or an operator
override and displays that choice before sending.

Do not enable `cancel_run` as an agent Stop substitute unless the selected card
is an actual workflow run and the gateway has its exact run ID.

- [ ] **Step 4: Register unavailable controls with exact reasons**

Examples:

```text
risk.propose-limit -> No controller-owned risk settings port is configured.
runtime.start -> No reviewed runtime manager is configured.
mode.enable-live -> Live broker activation is not configured or authorized.
service.restart -> No reviewed service supervisor is configured.
backup.restore -> Backup service is not installed.
source-control.push -> Source-control command port is not installed.
```

- [ ] **Step 5: Run tests and verify GREEN**

Expected: PASS with zero broker, scheduler, trainer, and protected-path calls.

- [ ] **Step 6: Commit**

Commit: `feat(tui): route bounded operator actions`

### Task 5: Model Live readiness without enabling Live

**Files:**
- Modify: `vesper/platform/tui/views.py`
- Modify: `vesper/platform/tui/command_ports.py`
- Create: `tests/platform/tui/test_live_readiness.py`

**Interfaces:**
- Produces `LiveReadinessView` with broker, account, data, model, strategy, risk, reconciliation, incident, and authority gates.
- Produces `TransitionPlanView` from actual broker holdings to desired holdings when a future approved port supplies both.

- [ ] **Step 1: Write all-gates and no-paper-copy tests**

Assert Live is disabled if any gate is false, stale, or unavailable. Assert the
transition plan consumes broker positions and desired targets, never Paper
positions. Assert every generated buy/sell remains approval-required.
Assert one active portfolio is shown: Shadow or Paper before activation, and
the reconciled broker-backed portfolio after Live activation.

- [ ] **Step 2: Run tests and verify RED**

Expected: FAIL because readiness is absent.

- [ ] **Step 3: Implement readiness as a pure view calculation**

The default real view sets broker/account/reconciliation/authority unavailable
and produces no transition plan. Account fields support a remembered privacy
mask but credentials have no model field at all.

- [ ] **Step 4: Run tests and verify GREEN**

Expected: PASS.

- [ ] **Step 5: Commit**

Commit: `feat(tui): show fail-closed Live readiness`

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

- [ ] **Step 1: Write keyboard, mouse, disabled, and modal tests**

Assert safe actions send immediately, confirm actions require one approval,
Emergency Stop and Force Stop require two, Live requires exact typed text,
Cancel is initial selection, Esc cancels, a viewer sees Take Control, disabled
buttons open their reason but send no command, and rapid double activation sends
one command ID. Assert the routed agent is visible and can be changed before
sending. Assert the account privacy toggle masks name, number, balance, and
capital, persists locally, and does not alter the server snapshot.

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

- [ ] **Step 4: Inspect modal snapshots**

Snapshot every confirmation level, disabled reason, rejected stale command,
running receipt, completed receipt, failed receipt, and viewer state in both
themes and Large Text.

- [ ] **Step 5: Run Rust tests and verify GREEN**

Expected: PASS.

- [ ] **Step 6: Commit**

Commit: `feat(tui): add governed console controls`

### Task 7: Prove command boundaries end to end

**Files:**
- Create: `tests/platform/tui/test_command_boundaries.py`
- Modify: `tests/platform/tui/test_gateway.py`
- Create: `TUI testing/ratatui-console/tests/command_e2e.rs`
- Modify: `TUI testing/ratatui-console/README.md`

**Interfaces:**
- Produces one fake-gateway end-to-end test suite and one current-platform local integration suite.

- [ ] **Step 1: Add end-to-end boundary cases**

Cover locked, viewer, stale, disabled, confirmed, double-confirmed, typed Live,
duplicate, disconnect-after-accept, reconnect-to-original-receipt, handler
failure, secret-shaped result, and changed prerequisite. Use fakes for all
financial/runtime commands.

- [ ] **Step 2: Run the complete Python TUI suite**

Run: `uv run --locked python -m pytest tests/platform/tui -q`

Expected: PASS.

- [ ] **Step 3: Run focused existing platform safety tests**

Run: `uv run --locked python -m pytest tests/platform/test_authority_boundaries.py tests/platform/test_service.py tests/platform/test_control.py -q`

Expected: PASS.

- [ ] **Step 4: Run complete Rust checks**

Run fmt, Clippy with `-D warnings`, and all locked tests.

- [ ] **Step 5: Manually inspect current capability truth**

Open the TUI locally. Confirm current platform approvals/actions reflect their
real state. Confirm broker, risk, Live, training, scheduler, service, backup,
restore, and push controls are disabled and explain why. Send no real command.

- [ ] **Step 6: Commit**

Commit: `test(tui): prove governed command boundaries`

## Phase acceptance

- Every approved button exists.
- Only controller-backed current actions are enabled.
- Disabled actions explain the missing adapter or authority.
- Stale state, viewer state, and missing confirmation call no handler.
- Every request has one idempotent durable receipt.
- Existing workflow approval/rejection and bounded queue actions retain their current authority checks.
- Live remains disabled without every readiness gate.
- No real broker, risk setting, order, scheduler, trainer, or runtime was touched.
