# V20 Ratatui Console Build Roadmap

Status: implementation complete; focused/full gates pass; integration pending
Date: 2026-08-03
Design: `TUI testing/RATATUI_DESIGN.md`

The design's section 0 errata and section 4.4 command table are authoritative
for every phase. If older wording conflicts, those two sections win.

## Outcome

Build the approved Ratatui console as four testable phases. Each phase leaves a
working product and does not claim abilities the connected V20 runtime lacks.

## Originally verified starting point

These bullets record the pre-implementation state; the current closeout is
summarized below.

- V20 is Python 3.11 and exposes `vesper-agent` through Typer.
- The governed agent platform lives under `vesper/platform/`.
- The older trading runtime lives in `vesper/engine.py` and is not controlled by
  the governed platform service.
- V20 has read models for agent runs, approvals, journals, evidence, memory, and
  agent queues.
- V20 does not have one controller-owned portfolio, order, broker, risk,
  training, notification, or service-management API suitable for the TUI.
- No Rust crate currently exists under `TUI testing`.
- The current main worktree contains unrelated user changes. Implementation must
  use an isolated worktree created from commit `9b958a5` or its reviewed
  descendant.

The separation between the agent platform and trading engine matters: the TUI
must not turn legacy Python objects into an unreviewed broker control path.

## Current closeout

- The Ratatui crate, Python controller gateway, ten-screen shell, strict
  contracts, chats, memory, notifications, operations policies, package script,
  and exact `dist/tui` package are implemented.
- Fresh focused verification passes: Python `1,314 passed`; Rust format,
  Clippy, and all-target tests pass.
- Fresh full-repository verification passes: `2,087 passed, 5 skipped`.
- Broker, order, risk, Live, scheduler, training, source-control, and
  production backup/restore adapters remain disabled or unavailable.
- Backup/restore remains an explicit activation gate because restore writes
  state; temporary-state service tests pass without enabling the production
  adapter.

## Plan set

1. `2026-08-03-v20-ratatui-foundation.md`
   - Versioned protocol, secure Windows named pipe, password, control lease,
     Rust client, fixed ten-screen shell, themes, and layout tests.
   - 9 executable tasks.

2. `2026-08-03-v20-ratatui-observability.md`
   - Truthful projections, snapshots and events, all ten read views, search,
     drill-down, freshness, portfolio ordering, broker mismatch display, and
     presentation performance. Cached-first-screen verification belongs to
     phase 4 after the encrypted snapshot cache exists.
   - 11 executable tasks. Task 9b closes full-ledger and stored-note search.

3. `2026-08-03-v20-ratatui-controls.md`
   - Controller command registry, receipts, confirmations, existing agent and
     approval actions, and visible disabled controls for unavailable authority.
   - 7 executable tasks.

4. `2026-08-03-v20-ratatui-operations.md`
   - Continuous-agent policy, per-agent chats, bounded Qwen context, working
     memory, notifications, backup/recovery, code-maintenance policy,
     capability-gated phase-4 adapters, cached-first-screen performance,
     packaging, and final verification.
   - 13 executable tasks; backup/restore, encrypted cache, recovery, and history
     retention each own an independent RED/GREEN/commit cycle.

Execute the plans in this order. A phase consumes only committed interfaces from
the preceding phase.

## Authority gates

Writing and testing code behind a disabled capability does not activate it.

| Capability | Code may be built | Real adapter or activation |
| --- | --- | --- |
| Agent-platform reads | Yes | Allowed |
| Existing run approval/rejection/cancel | Yes | Operator confirmation required |
| Portfolio/order/broker reads | Yes, through a port | Broker/account approval required |
| Risk-limit changes | Yes, through a port | Risk approval required |
| Shadow/Paper/Live start or stop | Yes, through a port | Runtime and broker approval required |
| Candidate training/evaluation | Yes, through a port | Training approval and resource gate required |
| Operations daemon adapter | Yes, disabled by default | Runtime activation approval required |
| Scheduler/continuous work/daily curation | Yes, disabled by default | Separate scheduler activation approval required; adapter availability is insufficient |
| Automatic local merge | Yes, policy and fake tests | Clean main plus low-risk scope required |
| GitHub push | Confirmed button only | Operator confirmation required |
| Candidate artifact deletion | Yes, policy and temporary-root tests | Separate destructive-retention approval required before a real-root adapter can enable `apply` |
| Protected data writes | No | Not authorized |

## Coverage map

| Approved design area | Owning phase |
| --- | --- |
| Python source of truth and typed gateway | 1 |
| Windows named pipe and no TCP port | 1 |
| Password lock and one control lease | 1 |
| Fixed shell, keys, themes, text sizes | 1 |
| Hybrid snapshot/event refresh | 2 |
| Impact | 2 |
| Portfolio and return views | 2 |
| Orders and reconciliation | 2 |
| Agents and Jira-style cards | 2 |
| Models and regime | 2 |
| Timeline | 2 |
| Risk and approvals read view | 2 |
| Data and evidence | 2 |
| Memory and system read views | 2 |
| Search, filters, notes, drill-down, full persisted history | 2 |
| Risk-based button behavior | 3 |
| Agent and approval commands | 3 |
| Runtime/mode/risk command gates | 3 |
| Live typed confirmation | 3 |
| Continuous work and Quiet Mode | 4 |
| Qwen compression and chats | 4 |
| 2,000-word working memory and vault | 4 |
| Windows notifications | 4 |
| DPAPI backup, restore, and recovery | 4 |
| Automated local code maintenance | 4 |
| Encrypted snapshot cache and cached-first-screen measurement | 4 |
| Performance, package, and end-to-end gates | 4 |

## Cross-phase rules

- Rust renders and requests. Python validates and owns authoritative state.
- Preserve `ml_model` as the default strategy; `momentum` remains supported and
  no strategy or model family is added by the TUI work.
- Wire and stored timestamps are canonical UTC. Rust renders them in
  `America/New_York`, including EST/EDT transitions.
- `WireEnvelope.sequence` is a per-client presentation/event delivery sequence.
  It is assigned only after coalescing and never grants command authority.
- Snapshots carry `control_version` and `control_hash` separately from
  presentation state. Every command carries the exact control pair the operator
  reviewed. Metrics, clocks, layout, chat, and other presentation-only changes
  do not change that pair.
- Snapshots also carry strict `command_specs`: phase 2 publishes an empty tuple;
  phase 3 publishes exactly the 31 design-table rows. Rust consumes these rows
  and does not hard-code capability or confirmation decisions.
- Strict typed models reject unknown fields. The decoder may retain bounded raw
  unknown fields only in an ephemeral untrusted diagnostic record that is never
  rendered, logged, persisted, or passed to policy or handlers.
- The gateway derives operator identity from the authenticated Windows pipe
  session. Rust never asserts an audit identity.
- An authenticated viewer may send only the lease-transfer request. Every
  governed command requires the current control lease.
- Every accepted or rejected command returns a durable receipt.
- Missing capability means `DISABLED` plus a plain reason.
- Before a reviewed runtime-status adapter succeeds, mode is `UNKNOWN`, mode
  freshness is `UNAVAILABLE`, and the gateway must not infer `STOPPED`.
- First-load failure means `UNAVAILABLE`; loss after a good value means `STALE`.
- Existing V20 state outranks TUI cache, history, or memory.
- Tests use fakes unless an explicit opt-in read-only integration test is named.
- No test connects to a live broker or uses real money.
- No task writes under `vesper/data/massive/` or
  `vesper/data/model_research/`.
- A real phase-4 service is usable only through its typed command port and only
  when the controller advertises the matching capability. Constructing an
  adapter does not enable runtime, scheduler, training, retention deletion,
  automatic merge, broker, risk, or Live authority.
- Each phase-4 activation is an `ActivationGrant`; enabled is valid only with
  its matching controller receipt. Candidate deletion additionally validates
  that receipt against the resolved candidate root and exact plan hash.

## Completion rule

The full console is complete only after all four plans pass their focused and
combined checks, the design coverage map has no gap, and real capabilities are
reported separately from disabled ones. Deployment, runtime activation, Live
activation, training, scheduler/continuous-work/daily-curation activation,
candidate deletion, or automatic merge activation are separate authority events
even when their code and tests exist.
