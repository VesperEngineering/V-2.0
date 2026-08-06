# V20 Ratatui Console Build Roadmap

Status: ready for operator review
Date: 2026-08-03
Design: `TUI testing/RATATUI_DESIGN.md`

Documentation status (2026-08-04): the candidate [CLI and TUI operator guide](../../knowledge/inbox/v20-cli-tui-how-to.md)
is drafted and linked from the root README and Obsidian vault index. The CLI
workflow is current; no TUI implementation or launch command exists yet.

## Outcome

Build the approved Ratatui console as four testable phases. Each phase leaves a
working product and does not claim abilities the connected V20 runtime lacks.

## Verified starting point

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

## Plan set

1. `2026-08-03-v20-ratatui-foundation.md`
   - Versioned protocol, secure Windows named pipe, password, control lease,
     Rust client, fixed ten-screen shell, themes, and layout tests.

2. `2026-08-03-v20-ratatui-observability.md`
   - Truthful projections, snapshots and events, all ten read views, search,
     drill-down, freshness, portfolio ordering, and broker mismatch display.

3. `2026-08-03-v20-ratatui-controls.md`
   - Controller command registry, receipts, confirmations, existing agent and
     approval actions, and visible disabled controls for unavailable authority.

4. `2026-08-03-v20-ratatui-operations.md`
   - Continuous-agent policy, per-agent chats, bounded Qwen context, working
     memory, notifications, backup/recovery, code-maintenance policy,
     performance, packaging, and final verification.

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
| Scheduler/continuous work | Yes, disabled by default | Scheduler activation approval required |
| Automatic local merge | Yes, policy and fake tests | Clean main plus low-risk scope required |
| GitHub push | Confirmed button only | Operator confirmation required |
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
| Search, filters, notes, drill-down | 2 |
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
| Performance, package, and end-to-end gates | 4 |

## Cross-phase rules

- Rust renders and requests. Python validates and owns authoritative state.
- Preserve `ml_model` as the default strategy; `momentum` remains supported and
  no strategy or model family is added by the TUI work.
- Every command carries the state version the operator reviewed.
- Every accepted or rejected command returns a durable receipt.
- Missing capability means `DISABLED` plus a plain reason.
- First-load failure means `UNAVAILABLE`; loss after a good value means `STALE`.
- Existing V20 state outranks TUI cache, history, or memory.
- Tests use fakes unless an explicit opt-in read-only integration test is named.
- No test connects to a live broker or uses real money.
- No task writes under `vesper/data/massive/` or
  `vesper/data/model_research/`.

## Completion rule

The full console is complete only after all four plans pass their focused and
combined checks, the design coverage map has no gap, and real capabilities are
reported separately from disabled ones. Deployment, Live activation, training,
scheduler activation, or automatic merge activation are separate authority
events even when their code and tests exist.
