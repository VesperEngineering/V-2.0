# V20 Ratatui Operations Console Design

Status: approved; foundation implemented; activation and verification status is
recorded in `results/FINAL_VERIFICATION.md`
Date: 2026-08-03
Location: `C:\Users\bgonn\Desktop\v20\TUI testing`

## 0. Approved errata and precedence

This section corrects ambiguous language elsewhere in this design and takes
precedence over every later section and the historical bakeoff documents.

- Wire and stored timestamps are UTC with zero offset. Field names use `_at_utc`
  or `_time_utc`. Only Rust presentation converts them to
  `America/New_York`; EST/EDT never crosses the wire or enters storage.
- Until a reviewed runtime-status adapter returns a value, operating mode is
  `UNKNOWN` with freshness `UNAVAILABLE` and reason `No reviewed runtime-status
  adapter is configured.` The gateway must not infer `STOPPED`.
- `state_version` and event `sequence` describe presentation delivery only.
  `control_version` and `control_hash` are separate controller authority facts.
  Every governed command binds the exact control pair the operator reviewed.
- Every typed Python and Rust contract rejects unknown fields. The decoder may
  pass one frame's unknown-field object and SHA-256 to a synchronous
  `UntrustedProtocolDiagnostic` callback. The diagnostic is capped by the 1 MiB
  frame limit, destroyed when the callback returns, and never rendered, logged,
  persisted, placed in receipts, or passed to policy or handlers.
- Every full snapshot carries `command_specs`. Observability defines the neutral
  strict view and publishes `[]`; controls publishes exactly the 31 authoritative
  rows from section 4.4. Rust replaces its local command-spec map atomically on
  each snapshot and never invents a row.
- Runtime start, continuous work, daily curation, candidate training, candidate
  deletion, and automatic merge each use `ActivationGrant(enabled,
  receipt_id)`. Enabled requires a matching validated controller receipt;
  disabled requires no receipt. Adapter availability cannot activate a grant.

## 1. Purpose

Build a production-quality local Ratatui console that mirrors V20 truthfully and
lets the operator understand and control the system without replacing the work
of its agents.

The console must answer these questions quickly:

- What is V20 doing now?
- Which agent is working, queued, waiting, or finished?
- What did that work affect?
- What does the portfolio actually hold?
- What weights are current, proposed, and approved?
- What regime and models are active, and why?
- When can the portfolio rebalance, and what blocks it?
- What needs approval or intervention?
- Does V20 match the broker?
- Is the local runtime healthy?

The design is dense because the information is useful, not because every space
must be filled.

## 2. Scope and non-goals

### Included

- One local Windows computer.
- Rust and Ratatui for the terminal interface.
- Python V20 as the authoritative controller.
- Stocks, ETFs, and cash.
- One active portfolio at a time.
- Shadow, Paper, and Live operating modes.
- Agent work, chats, memory, models, regime, portfolio, orders, risk, evidence,
  approvals, runtime health, and source-control status.
- Keyboard and mouse controls.
- Continuous governed local-agent work.
- Automatic candidate training and evaluation inside approved boundaries.
- Local encrypted backup and recovery.

### Not included

- A web dashboard.
- Remote access or an open network port.
- A phone application. The runtime will expose a future notification adapter,
  but phone work is a separate project.
- Replay mode.
- Multiple simultaneous portfolios or broker accounts.
- Options or cryptocurrency.
- Automatic GitHub pushes.
- New strategies, new model families, broker setup, credentials, real-money
  activation, or protected-data writes.

The TUI must never imply that an unavailable backend capability exists. A
planned control may be visible but disabled with a plain reason until V20
implements, configures, and authorizes it.

## 3. Source of truth

Python V20 remains the only source of truth. This means the Rust interface may
display state and request actions, but it does not decide authoritative state.

The TUI must not directly write:

- controller databases;
- portfolio or order state;
- model registries or active artifacts;
- risk settings;
- agent queues or journals;
- broker state;
- protected data.

Every state-changing request goes to the Python controller. The controller
checks the request against current state, permissions, data freshness, risk,
approvals, and capability availability. It then returns an accepted or rejected
receipt.

Test fixtures may contain fake data. The running TUI may not replace missing
live data with fixtures, examples, or guesses.

## 4. Process architecture

### 4.1 Components

1. **Ratatui client**
   - Renders screens.
   - Handles keyboard and mouse input.
   - Maintains local selection, filters, column visibility, and panel sizes.
   - Sends typed requests and renders controller receipts.

2. **V20 control gateway**
   - Runs in Python.
   - Maps V20 state into versioned view models.
   - Publishes snapshots and live events.
   - Authenticates the TUI.
   - Owns the single control lease.
   - Routes commands to existing V20 services.
   - Never moves a permission check into Rust.

3. **V20 runtime**
   - Owns agents, Qwen, data, models, portfolio, risk, execution, persistence,
     evidence, memory, and notifications.
   - Continues running when the TUI closes.

### 4.2 Local transport

The Ratatui client and gateway communicate through a duplex Windows named pipe.
The pipe is restricted to the signed-in Windows account and denies network
access. No TCP port is opened.
The signed-in Windows logon is the security boundary; defending against a
hostile process under that same logon requires a separate OS identity or
service and is out of scope.

Opening the TUI may start a control-only gateway process, but it must not start
agents, trading, research, or the V20 runtime. Without a reviewed runtime-status
adapter the gateway reports `UNKNOWN` / `UNAVAILABLE`; it never guesses
`STOPPED`. The runtime starts only after an authenticated and confirmed Start
request through an available controller adapter.

### 4.3 Protocol

Every message uses a versioned typed contract with:

- schema version;
- message or request ID;
- monotonic event sequence;
- current state version;
- canonical UTC timestamp named `timestamp_utc`;
- message type;
- typed payload.

The first successful connection returns a complete snapshot. Later changes use
events. A sequence gap, reconnect, or schema mismatch forces a fresh snapshot.

State-changing commands include the `control_version` and `control_hash` the
operator saw. If either is no longer current, the controller rejects the command
as stale and requires the operator to review the new authority facts.

### 4.4 Authoritative governed-command decision table

This is the complete command catalog. `capability ID` is exact. Payload models
are strict and frozen; every field shown is required unless marked optional.
`EmptyPayload` has no fields. `NonEmptyStr` is trimmed length 1..512,
`SafeId` matches `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`, `Sha256Hex` is 64
lowercase hexadecimal characters, `GitRevision` is 40 or 64 lowercase
hexadecimal characters, `ScreenName` is exactly `impact`, `portfolio`, `orders`,
`agents`, `models-regime`, `timeline`, `risk-approvals`, `data-evidence`,
`memory`, or `system`, and `DecimalString` is a finite base-10 string without
exponent notation. Unknown commands, fields, enum values, and
payloads above 64 KiB are rejected before policy or handler execution.
Python owns an exact immutable `PAYLOAD_MODELS` mapping for all 31 commands.
`CommandRequest` constructs a dictionary payload through the mapped class and
then requires `type(payload) is PAYLOAD_MODELS[command_type]`; a valid payload
model belonging to another command is rejected as `payload-model-mismatch`.

Reason rules are exact: `forbidden` requires JSON `null`; `optional` allows
`null` or trimmed text of 1..2,000 characters; `required` requires trimmed text
of 1..2,000 characters. Confirmation levels are `none`, `confirm`,
`double-confirm`, and `typed-live`; `typed-live` accepts only case-sensitive
`ENABLE LIVE`.

| Command | Exact payload model and fields | Capability ID | Reason | Confirmation |
| --- | --- | --- | --- | --- |
| `note.add` | `NoteAddPayload(target_type: stock\|order\|approval\|agent-event, target_id: SafeId, body: str[1..8000], visibility: private\|shared)` | `note.add` | forbidden | none |
| `alert.dismiss` | `AlertDismissPayload(alert_id: SafeId, created_at_utc: UtcDateTime)` | `alert.dismiss` | forbidden | none |
| `layout.reset` | `LayoutResetPayload(screen: ScreenName optional)` | `layout.reset` | forbidden | none |
| `approval.approve` | `ApprovalPayload(run_id: SafeId, checkpoint_id: SafeId)` | `approval.approve` | optional | confirm |
| `approval.hold` | `ApprovalPayload(run_id: SafeId, checkpoint_id: SafeId)` | `approval.hold` | required | confirm |
| `approval.reject` | `ApprovalPayload(run_id: SafeId, checkpoint_id: SafeId)` | `approval.reject` | required | confirm |
| `approval.rework` | `ApprovalReworkPayload(run_id: SafeId, checkpoint_id: SafeId, evidence_ids: tuple[SafeId, ...])` | `approval.rework` | required | confirm |
| `agent.send-message` | `AgentMessagePayload(agent_id: SafeId, text: str[1..8000], selected_entity_type: str optional, selected_entity_id: SafeId optional)` | `agent.send-message` | forbidden | none |
| `agent.enqueue` | `AgentEnqueuePayload(agent_id: SafeId, title: NonEmptyStr, objective: str[1..8000], priority: int[0..100])` | `agent.enqueue` | required | confirm |
| `agent.pause` | `AgentWorkPayload(work_id: SafeId)` | `agent.pause` | required | confirm |
| `agent.stop` | `AgentStopPayload(work_id: SafeId, workflow_run_id: SafeId optional)` | `agent.stop` | required | confirm |
| `agent.retry` | `AgentWorkPayload(work_id: SafeId)` | `agent.retry` | required | confirm |
| `agent.set-priority` | `AgentPriorityPayload(work_id: SafeId, priority: int[0..100])` | `agent.set-priority` | required | confirm |
| `risk.propose-limit` | `RiskLimitPayload(limit_id: SafeId, proposed_value: DecimalString, evidence_ids: tuple[SafeId, ...])` | `risk.propose-limit` | required | confirm |
| `trading.pause` | `EmptyPayload` | `trading.pause` | required | confirm |
| `trading.emergency-stop` | `EmptyPayload` | `trading.emergency-stop` | required | double-confirm |
| `service.pause` | `ServicePayload(service_id: SafeId)` | `service.pause` | required | confirm |
| `service.restart` | `ServicePayload(service_id: SafeId)` | `service.restart` | required | confirm |
| `runtime.start` | `RuntimeStartPayload(mode: shadow\|paper, activation_receipt_id: SafeId)` | `runtime.start` | required | confirm |
| `runtime.stop-safe` | `EmptyPayload` | `runtime.stop-safe` | required | confirm |
| `runtime.stop-force` | `EmptyPayload` | `runtime.stop-force` | required | double-confirm |
| `runtime.prepare-shutdown` | `EmptyPayload` | `runtime.prepare-shutdown` | required | confirm |
| `mode.switch` | `ModeSwitchPayload(target_mode: shadow\|paper)` | `mode.switch` | required | confirm |
| `mode.leave-live` | `ModeSwitchPayload(target_mode: shadow\|paper)` | `mode.leave-live` | required | confirm |
| `mode.enable-live` | `EnableLivePayload(desired_portfolio_id: SafeId)` | `mode.enable-live` | required | typed-live |
| `model.request-promotion` | `ModelDecisionPayload(candidate_id: SafeId, evidence_ids: tuple[SafeId, ...])` | `model.request-promotion` | required | confirm |
| `model.request-rollback` | `ModelDecisionPayload(candidate_id: SafeId, evidence_ids: tuple[SafeId, ...])` | `model.request-rollback` | required | confirm |
| `memory.compress-now` | `CompressMemoryPayload(agent_id: SafeId)` | `memory.compress-now` | forbidden | none |
| `backup.create` | `BackupCreatePayload(destination: str[1..32767])` | `backup.create` | optional | confirm |
| `backup.restore` | `BackupRestorePayload(archive: str[1..32767], preview_hash: Sha256Hex, safety_backup_receipt_id: SafeId)` | `backup.restore` | required | double-confirm |
| `source-control.push` | `SourceControlPushPayload(expected_revision: GitRevision)` | `source-control.push` | required | confirm |

`alert.dismiss` is occurrence-bound. The Rust client copies both the selected
alert ID and its `created_at_utc` into the reviewed request. At admission, the
controller requires that pair to still match the current alert. If the alert
resolved and reopened under the same ID, the old request is rejected and the
new occurrence stays visible. The durable binding, dismissal effect, recovery,
and terminal receipt all retain that exact pair. Only a green resolved alert
can be dismissed. An urgent alert remains visible even if an old exact
dismissal record exists.

Notification history cleanup uses a durable queue of at most 64 opaque alert
IDs inside the current alert record. Incident switches persist the new urgent
truth and the old cleanup ID together before cleanup is attempted. Successful
idempotent removals are deleted from the queue one at a time. On overflow, the
oldest cleanup ID is dropped, a sticky generic overflow flag is stored, and a
generic notification-health failure is recorded; the new urgent alert remains
primary and no incident detail is stored.

`approval.rework` stays disabled until immutable approval lineage identifies one
responsible approved agent and the decision-plus-enqueue recovery rule is
defined. The controller must not guess. `agent.stop` with no
`workflow_run_id` also stays disabled until queued cancellation has a separate,
explicit meaning; active work requires an exact persisted work-to-run binding.

`backup.restore` is admitted only when all staged preconditions are current in
the same control pair: runtime status is exactly `STOPPED`; archive structure,
allowlist, DPAPI decrypt, entry sizes, and manifest hashes validate; the preview
lists every add/replace/remove target and its SHA-256; `preview_hash` matches the
canonical preview; an automatic safety backup completed successfully and its
receipt ID matches the request; the archive and target state have not changed;
double-confirmation is bound to the same preview hash. Any precondition failure
replaces zero target paths. After replacement starts, verification must pass or
the controller rolls back every target from the safety backup and returns a
failed receipt. If rollback cannot be verified, protected writes stay locked and
the console requires manual recovery.

### 4.4 Refresh model

Use a hybrid update model:

- Stream approvals, agent events, orders, portfolio changes, alerts, and chat.
- Refresh system and market metrics every one to two seconds while visible.
- Refresh slower data every five to ten seconds.
- Combine bursts into one draw.
- Redraw only changed panels.

## 5. Authentication and control ownership

The entire dashboard is hidden until a password unlocks it.

- The gateway verifies the password.
- Store only a salted memory-hard password verifier in local application state.
- Never store, display, log, or back up the password.
- There is no inactivity timeout.
- A manual Lock TUI command remains available.
- Closing and reopening always requires the password again.
- High-risk confirmations do not ask for the password a second time.

One authenticated TUI owns the control lease. Additional TUI windows may open
only as read-only viewers. If the controlling window closes, a viewer stays
read-only until the operator explicitly presses Take Control.

## 6. Visual system and interaction

### 6.1 Shell

Every screen uses the same fixed shell:

1. Runtime and market header.
2. Permanent navigation row.
3. Persistent alert area.
4. Screen content.
5. Small agent input.
6. Key hints and system status.

The header always shows:

- Shadow, Paper, or Live;
- data age;
- market regime and confidence;
- portfolio value;
- next rebalance and blockers;
- active agent and queue length;
- Qwen idle/busy state and context usage;
- active alerts;
- Eastern Time and market session.

The snapshot field is `current_time_utc`; Rust alone renders the Eastern Time
label from it.

Market session labels are Pre-market, Open, After-hours, and Closed. Eastern
Time automatically observes EST and EDT.

### 6.2 Navigation

Permanent screens:

1. Impact
2. Portfolio
3. Orders
4. Agents
5. Models & Regime
6. Timeline
7. Risk & Approvals
8. Data & Evidence
9. Memory
0. System

Global keys:

- `o`: open selected content full-screen;
- `Esc`: return;
- `/`: search all supported V20 records;
- `f`: filter the current screen;
- `:`: command menu;
- `i`: focus agent input;
- `Enter`: send input;
- `?`: help;
- `q`: close the TUI, not V20.

Every visible button supports mouse and keyboard activation. Text input consumes
normal typing keys until `Esc` exits input mode.

Buttons follow the action's risk:

- safe and reversible actions run immediately and return a receipt;
- actions that change runtime, risk, model, portfolio, order, backup, restore,
  source-control, or Live state require a confirmation;
- destructive or emergency actions use a second warning with Cancel selected;
- an unavailable action stays visible but disabled and explains what is missing.

### 6.3 Accessibility and themes

- Warm white and charcoal themes.
- Remember the selected theme.
- Red means urgent, yellow waiting, blue active, and green healthy or resolved.
- Color is never the only status signal; use a word and symbol too.
- No flashing, repeated sound, or decorative motion.
- Resolved alerts turn green but remain until dismissed.
- Compact, Standard, and Large Text display modes.
- Panel positions remain fixed.
- Panels may resize within defined minimums.
- Table columns may be shown or hidden.
- Per-screen layout preferences persist.
- Reset Layout restores the approved layout.

The full multi-panel dashboard targets wide terminals. Narrow terminals keep all
features through one-panel focus views instead of squeezing unreadable columns.

## 7. Screen designs

### 7.1 Impact

Impact is the startup screen. It uses the approved portfolio-dominant layout:

- all holdings in the large left panel;
- impact feed in the upper-right panel;
- compact agent work in the lower-right panel;
- portfolio, regime, rebalance, Qwen, agent, and data summaries above them.

Impact events answer:

`agent work -> finding -> model or regime effect -> affected stocks -> weight or
rebalance effect -> risk or approval`

No-impact work stays in history and does not crowd the default feed.

### 7.2 Portfolio

The portfolio screen shows every holding.

- Row order follows confirmed executed portfolio weight.
- Normal price movement does not reorder rows.
- A proposal or approval does not reorder rows.
- Rows move only after broker execution and position reconciliation complete.
- Unchanged rows remain neutral.
- Current, Proposed, and Approved weights appear beside one another.
- Highlight only changed cells before execution.
- Keep the whole affected rebalance highlighted until every order completes and
  V20 reads back matching broker positions.
- After confirmed execution, update Current and return the row to its normal
  background.

Portfolio performance toggles between:

- Today;
- Since Rebalance;
- Since Start.

Remember the last view. Compare every period with the S&P 500 total return,
including dividends. Break portfolio return into price gains or losses,
dividends, cash interest, and fees.

Show current drawdown, largest holding, portfolio volatility, and cash level
with equal visual weight.

Opening a stock leads with its full history of proposals, approvals, rejections,
expirations, weight changes, orders, fills, and reconciliations. Current position
facts remain pinned at the top. Rejected and cancelled events remain in history.

### 7.3 Orders

Group orders by stock, newest first within each stock.

Show:

- proposed order;
- approval state;
- submitted time;
- broker order ID without credentials;
- partial fills;
- completed fills;
- rejections;
- cancellations;
- expected versus actual execution;
- fees and slippage;
- broker-to-V20 reconciliation.

Partial execution does not clear the rebalance highlight. It clears only when
the full rebalance is broker-complete and reconciled.

A mismatch creates an urgent Reconciliation Agent task. It identifies the
owner, differences, affected holdings, evidence, and repair progress. New broker
orders and rebalances stay blocked while research, data, agents, and simulations
continue.

### 7.4 Agents

Use the approved Jira-style card board:

`Queued | Running | Waiting | Done`

Urgent is a priority label, not a column. Urgent cards remain in their real work
stage and stay at the top of that column. Extra tasks live in Backlog.

Cards show:

- agent and task;
- priority;
- current stage;
- elapsed time;
- model;
- affected V20 area.

Opening a card shows the plan, stages, tool calls, files, evidence, decisions,
errors, results, context meter, and that agent's chat. Show plans and auditable
work, not private token-by-token reasoning.

Each agent has a separate chat. Chats are hidden until opened. Qwen responses
stream as DRAFT and become COMPLETE only after the response and required
validation finish.

Each running task exposes Pause, Stop, Retry, and task-only priority controls.
Done shows today's work; older work remains searchable.

### 7.5 Models & Regime

Show:

- active model and rollback model;
- candidate models;
- approved family and strategy;
- features;
- metrics and comparisons;
- evaluation windows;
- pass/fail gates;
- evidence;
- promotion, rejection, and rollback status.

Show the final market regime plus every participating model's opinion and
confidence. Model disagreement produces UNCERTAIN. UNCERTAIN blocks automatic
portfolio changes until deterministic rules pass.

Agents may automatically train and evaluate candidates when resources allow,
but only inside approved model families, strategies, features, and data. New
families, active-artifact replacement, promotion, and rollback require approval.
No candidate becomes active automatically.

Retention:

- failed or rejected candidate files: 30 days;
- passed but unselected candidate files: 90 days;
- active and rollback model files: permanent;
- metrics, evidence, lineage, and history: permanent.

Low disk space pauses training rather than deleting protected artifacts early.

### 7.6 Timeline

Timeline is a separate permanent screen using the approved impact-first design.

- Show impact events by default.
- `e` reveals all routine events.
- Always show the hidden-event count.
- Show past, current, and scheduled events.
- Link every event to its agent, evidence, holding, model, approval, or order.
- Use `o` for full event detail.

### 7.7 Risk & Approvals

Show risk limits, exposure, drawdown, concentration, blocked actions,
circuit-breaker state, and pending approvals.

Risk limits are editable through Current and Proposed values. A change requires
a reason, risk-agent review, evidence, and confirmation.

- A tighter approved limit activates immediately.
- If the portfolio violates it, block new risk and create a corrective plan.
- Corrective broker orders still require approval.
- A higher limit changes future permission but does not force a trade.

Emergency controls:

- Pause Trading blocks new orders and leaves existing broker orders alone.
- Emergency Stop blocks new orders and requests cancellation of every open
  order.
- Agents and research continue so they can diagnose the problem.

Approval detail includes the reason, affected stocks, weight changes, risks,
evidence, and expected consequences. Choices are Approve, Hold, Reject, and Ask
Agents to Rework. Hold, Reject, and Rework use quick reasons plus optional notes.

If underlying data, model results, portfolio state, code revision, or evidence
changes, the approval becomes stale and cannot be used.

### 7.8 Data & Evidence

Lead with each source's:

- health;
- age;
- coverage;
- errors;
- current consumers and dependencies.

Evidence is searchable by stock, agent, model, order, approval, source, and
time. Raw logs remain available through drill-down.

First-load failure shows UNAVAILABLE. Failure after a valid load keeps the last
valid data, labels it STALE, shows age and error, and disables every unsafe
control that depends on it.

### 7.9 Memory

Qwen has no model-internal durable state. V20 provides controller-owned memory
tools and storage.

Store full per-agent chats on the SSD. They remain searchable and are not loaded
wholesale into every request.

Maintain one shared 2,000-word V20 Core Memory:

- V20-only information;
- automatically curated by Qwen and the agents;
- no manual pins;
- additions and demotions based on evidence, usefulness, successful reuse,
  relevance, and age;
- rare safety facts cannot be displaced merely because they are rarely used;
- lower-value memories move to the archive instead of being destroyed.

Use a dedicated Obsidian-compatible Qwen vault, separate from raw chats. The
default local path is `%USERPROFILE%\Documents\V20 Qwen Vault`. This is managed
working memory, not permission or proof.

`AGENTS.md`, current instructions, live repository state, policy, tests,
evidence, and approvals always outrank managed memory. Core rules do not count
toward the 2,000-word limit and Qwen cannot edit them.

Memory curation timing:

- agents may submit candidates after completed work;
- replace core memory only when the replacement is more valuable;
- review the full core daily for stale or duplicate content;
- log every change with evidence and make it reversible.

The screen shows core memory, archive search, recent additions and removals,
reasons, evidence, which agents used an item, and change history.
Archive search reads the complete bounded archived content through the
controller's read-only ledger path; it is not limited to the 512-character
snapshot summary.

### 7.10 System

Show:

- CPU, GPU, temperature, memory, disk, and process state;
- Qwen load, current agent, queue length, context use, and inference timing;
- service health and errors;
- source-control branch, revision, cleanliness, worktrees, checks, and unpushed
  commits;
- backup, recovery, and notification health.

Controls:

- pause or restart one service;
- try one safe automatic restart after a crash, then alert;
- Start V20 and select Shadow, Paper, or Live, with Shadow selected by default;
- Stop Safely;
- Force Stop with a second warning;
- Prepare for PC Shutdown;
- Backup Now;
- Restore;
- Push confirmed local commits;
- Lock TUI.

Starting or stopping the whole runtime always opens a confirmation with Cancel
selected by default. Prepare for PC Shutdown stops new tasks, safely pauses or
finishes work, checkpoints chats, flushes journals and state, disconnects, and
shows SAFE TO SHUT DOWN. It does not shut down Windows.

## 8. Operating modes and Live transition

Only one portfolio is active at a time. Shadow and Paper remain available as
history and comparison. Live becomes the active broker-backed portfolio only
after activation.

Entering Live requires:

- configured and authorized broker connection;
- current account and capital display;
- fresh data;
- model and strategy approval;
- risk checks;
- clean broker reconciliation;
- no blocking incident;
- typed `ENABLE LIVE` confirmation.

Account name, number, balance, and capital may display normally. A privacy
toggle masks them and remembers its setting. Credentials never appear.

The first Live transition reads actual broker holdings. V20 then prepares a
transition plan from broker reality to the desired portfolio. It never copies
Paper holdings directly into broker orders. Every required buy or sell remains
visible and requires approval.

Leaving Live requires a normal confirmation.

## 9. Agent autonomy and scheduling

Agents may create safe V20 follow-up tasks automatically. Queue limits apply per
agent and globally. Duplicate tasks merge. Work beyond the active queue moves to
Backlog. Every task records why it was created.

V20 remains continuously available:

1. Runtime incidents, approvals, portfolio work, and operator commands have
   highest priority.
2. Normal queued tasks follow.
3. When the queue is empty, agents pull useful work from the V20 research
   backlog.
4. After each background unit, the controller pauses briefly and checks
   priorities again.
5. Temperature, memory, disk, repeated error, and queue limits force rest.

Quiet Mode runs from 7:00 PM through 8:00 AM Eastern Time and all weekend. It
uses lower GPU load and longer pauses. Quiet Mode does not weaken safety checks.

If Qwen cannot safely finish a task, it may create a Request Codex Help
approval. The request shows why Qwen is blocked, what data would be shared, and
the intended scope. Codex never runs automatically.

## 10. Qwen context and conversation storage

Only one agent uses `qwen:64k` inference at a time. Other agents queue. The TUI
shows BUSY or IDLE, active agent, queued count, and context usage.

Use the V20 context budget rather than an artificial small prompt limit. Reserve
enough space for tool results and the model response.

Auto-compression begins near 80 percent of the safe input budget only after a
controller-owned runtime observes the real prompt budget. Manual Compress Now
first shows the exact approved agent and allows an override before sending.
Compression is per agent.

Always preserve in active context:

- current objective and state;
- unresolved decisions and approvals;
- evidence references;
- errors and blockers;
- applicable `AGENTS.md` rules;
- V20 Core Memory;
- pointers to the raw transcript.

Compression never deletes raw chat. Interrupted streams remain in history as
INTERRUPTED and never become validated results.

## 11. Notes and conversations

The operator may add notes or bookmarks to stocks, orders, approvals, and agent
events. Each note is Private or Shared with Agents.

Shared notes are context only. They never become commands. Commands go through
the global input and are automatically routed to the responsible agent. The TUI
shows the selected agent before sending and allows an override.

Conversations exist only between the operator and agents. There are no stock,
order, or approval chat threads.

## 12. Alerts and notifications

- Critical TUI alerts are visual and silent.
- Active urgent alerts use a persistent red banner.
- Fixed alerts change to green RESOLVED but remain until dismissed.
- If the TUI is closed, use a generic Windows notification: `V20 needs
  attention`.
- Clicking the notification opens the TUI at the relevant alert after password
  unlock.
- Notification content does not expose portfolio or account details.

The notification layer must allow a future private phone application without
adding phone or remote access to this scope.

## 13. Backup, retention, and recovery

Backup Now creates one local archive encrypted to the signed-in Windows account.
It includes settings, memory, history, journals, receipts, and eligible state.
It excludes credentials and protected source data.

Restore requires:

1. stopped V20 runtime;
2. archive validation;
3. exact preview of changes;
4. automatic safety backup;
5. explicit confirmation;
6. post-restore verification.

Keep portfolio, order, approval, memory, and agent history permanently. Compress
raw logs after 30 days. Do not automatically delete history.

After power loss or an unclean stop, enter Recovery Mode. Verify journal chains,
state versions, active work, model references, portfolio state, and broker
positions. Do not resume broker actions until reconciliation passes and the
operator confirms resume.

## 14. Automated code maintenance

Development agents never edit main directly. They use isolated branches and
worktrees.

A fix may merge automatically into local main only when all conditions pass:

- main is clean and at the expected revision;
- the change is small and inside a preapproved low-risk scope;
- required focused and broader tests pass;
- formatting and static checks pass;
- an independent review agent approves the exact diff;
- no protected file or authority boundary is touched;
- a rollback commit can be created;
- the merge lock is held.

Automatic merge is forbidden for broker, order, portfolio, risk, models,
training policy, scheduler, credentials, protected data, `AGENTS.md`, or broad
architecture changes.

If post-merge verification fails, revert the merge immediately, keep main clean,
and queue a repair task. Automatic changes remain local. GitHub Push requires a
confirmed operator action.

The current V20 main worktree is dirty. This existing state must be reconciled
separately before automatic merging can be enabled. This design does not
authorize cleanup or alteration of those changes.

## 15. Error handling

- Fail closed when required truth is missing.
- Never silently substitute a model, strategy, artifact, data source, broker
  state, or memory.
- Keep last-known data only with a visible STALE label, age, source, and error.
- Disable commands whose prerequisites are stale or unavailable.
- A broken pipe reconnects with bounded backoff and requires a fresh snapshot.
- Unknown protocol fields reject the typed message. Only the bounded ephemeral
  diagnostic defined in section 0 may retain their raw object.
- Unsupported schema versions stop control actions.
- Duplicate command IDs return the original receipt and do not repeat an
  action.
- A partially completed multi-step action remains visible and recoverable.

## 16. Performance targets

Measure Ratatui separately from Python, broker, data, and model latency.

Targets on the approved local computer:

- cached first screen within one second;
- live event to visible update within 250 milliseconds under normal load;
- keyboard and mouse response within 50 milliseconds;
- no full-screen redraw when one panel changes;
- near-zero idle TUI CPU use;
- responsive filtering and navigation with at least 10,000 history rows;
- bounded memory growth during continuous event and chat streaming;
- clean shutdown with no orphaned TUI or gateway process when runtime is
  stopped.

If a target cannot be met, report the measured result and bottleneck rather than
hiding it.

## 17. Testing

Required test groups:

1. **Protocol contracts**
   - snapshots, events, commands, receipts, schema versions, unknown fields,
     sequence gaps, and duplicate commands.

2. **Screen snapshots**
   - both themes;
   - Compact, Standard, and Large Text;
   - wide and narrow terminals;
   - loading, empty, fresh, stale, unavailable, urgent, resolved, and locked.

3. **Interaction**
   - keyboard and mouse parity;
   - search, filters, command menu, input mode, `o`, `Esc`, confirmations, and
     control lease transfer.

4. **Safety**
   - stale approvals;
   - incorrect password;
   - disabled unsupported controls;
   - missing data;
   - broker mismatch;
   - partial orders;
   - risk-limit tightening;
   - Live activation gates;
   - no secret display or logging.

5. **Agents and memory**
   - queue bounds and duplicate merging;
   - one Qwen inference lease;
   - streaming DRAFT to COMPLETE;
   - interrupted response;
   - automatic context compression with raw-history preservation;
   - 2,000-word core enforcement and reversible archive movement.

6. **Lifecycle**
   - TUI close while runtime continues;
   - safe stop, force stop, shutdown preparation, crash recovery, backup, and
     restore.

7. **Source control**
   - dirty-main block;
   - isolated worktree enforcement;
   - allowed and forbidden auto-merge scopes;
   - failed post-merge verification and automatic revert;
   - manual push gate.

8. **Performance**
   - first paint, event latency, render time, input latency, CPU, memory, long
     streaming sessions, and 10,000-row data sets.

Broker and order tests use deterministic fakes or approved paper environments.
No test uses real money.

## 18. Acceptance criteria

The design is implemented only when:

- all ten screens use the approved shell and truthful live contracts;
- Impact uses layout A and Agents uses the Jira card board;
- every state-changing action is controller-validated and receipt-backed;
- no TUI path writes directly to authoritative V20 state;
- authentication and control ownership work across multiple TUI windows;
- stale and unavailable states disable unsafe actions;
- portfolio rows obey executed-only movement and broker reconciliation;
- agents, Qwen context, continuous work, memory, training, and approvals obey
  their defined limits;
- recovery, backup, notifications, and runtime lifecycle work with the TUI
  closed or reopened;
- required tests pass with fresh output;
- performance results are recorded honestly;
- protected data and credentials remain untouched;
- activation of broker, Live, schedules, automatic training, or automatic
  merging occurs only through separately verified runtime readiness steps.

## 19. Relationship to the original bakeoff

`DESIGN.md` and `IMPLEMENTATION_PLAN.md` describe the earlier matching Textual
versus Ratatui read-only bakeoff. That scope was useful for framework comparison
but cannot support this approved operations console.

This document supersedes the product scope of that bakeoff. It does not delete
the historical documents, implement the TUI, activate runtime behavior, access a
broker, or authorize cleanup of the existing dirty worktree.
