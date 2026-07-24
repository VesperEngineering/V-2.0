# Vesper Quant Factory Desktop Design

**Status:** Approved for implementation planning
**Decision owner:** Brennan  
**Date:** 2026-07-24  
**Repository:** `VesperEngineering/V-2.0`

## 1. Purpose

Vesper will become a local-first quant software factory that can admit research
objectives, create bounded work, dispatch Codex and Hermes workers, evaluate
their output independently, advance model candidates through research and
Alpaca paper stages, and retain evidence-backed lessons over time.

The product is one Windows desktop application. Its default screen is Mission
Control, with Research and Factory Overview as first-class views backed by the
same durable state. The application owns its orchestration engine; external
agent CLIs are execution adapters, not the source of task state, policy,
evaluation, or memory.

## 2. Approved product decisions

| Area | Decision |
|---|---|
| Product shape | One all-in-one Vesper desktop application |
| Primary purpose | Quant-first agent factory |
| Desktop shell | Native Tauri 2 window; no external browser or hosted UI |
| UI composition | Mission Control home, Research workspace, Factory Overview |
| Agent runtimes | Codex CLI and Hermes CLI in the first release |
| Worker identity | Disposable workers created from generic capability templates |
| Long-term knowledge | Belongs to Vesper, not named personas or private agent memory |
| Initiative | Bounded F2-F3 initiative inside an admitted campaign |
| Improvement | L2-L3 evidence-gated learning with canaries and rollback |
| Model lifecycle | P2: automatic research, shadow, and Alpaca paper progression after gates; live remains human-approved |
| Asset scope | US equities and ETFs; no cryptocurrency workflow |
| Data | Massive local data remains the source of truth |
| Broker | Alpaca paper only until a separate live-trading approval |
| Operator model | Background tray operation with one actionable inbox and a factory-wide stop |
| Resource policy | Frozen per-campaign budgets bounded by stricter factory-wide ceilings |
| Existing engine | Preserve the Python trading engine and current Tkinter dashboard until replacement parity is verified |
| Release gate | Stability and recoverability are required, not optional cleanup |

## 3. Goals and measurable success

The first complete release must:

1. Launch as a packaged Windows desktop application without opening a browser.
2. Keep campaigns, cards, attempts, receipts, evidence, lessons, and candidate
   gates in a Vesper-owned local SQLite database.
3. Start Codex or Hermes automatically from a card with the complete task
   contract already supplied. The user must not have to retype each card into a
   terminal.
4. Display the same CLI availability result that the launcher actually uses.
   A running CLI session and a simultaneous false “CLI not found” status is a
   release-blocking defect.
5. Recover after forced application termination without losing admitted work.
   Previously active attempts become `INTERRUPTED` and require reconciliation;
   they are never silently marked complete or blindly duplicated.
6. Keep Massive data read-only and keep credentials out of prompts, receipts,
   logs, and the UI event store.
7. Require authoritative evidence and an independent verdict before a task or
   model candidate advances through a gated transition.
8. Allow a worker to make fast bounded corrections within one task while a
   fresh evaluator session retains final acceptance authority.
9. Improve routing, context packets, retry policy, and capability templates
   only through versioned evidence, canary evaluation, and rollback.
10. Pass Python, Rust, frontend, packaging, recovery, and Windows smoke suites,
    plus an eight-hour idle/running soak without state corruption or an
    unrecoverable sidecar failure.
11. Continue admitted work in an explicit background/tray mode while surfacing
    only actionable exceptions through an Operator Inbox.
12. Turn a rough objective into a frozen campaign contract and dependency graph
    through a short planning wizard before dispatch.
13. Preserve one progressive dossier per card and reproducible lineage for
    every experiment, including fork, compare, and replay from an immutable run
    manifest.
14. Give workers structured Vesper tools for coordination instead of requiring
    board mutation through shell commands.
15. Detect file, artifact, dataset, compute, and paper-account collisions before
    parallel dispatch.
16. Provide factory analytics and an integrated diff/review surface without
    expanding into a general-purpose IDE.

## 4. Non-goals for the first release

- Live trading, live model deployment, or automatic capital allocation.
- Cryptocurrency data, research, or execution.
- Cloud-hosted task state, remote collaboration, accounts, billing, or a web
  deployment.
- Replacing Massive with another market-data provider.
- Replacing the current active model artifact without the required human gate.
- A general-purpose workflow builder unrelated to Vesper’s quant and software
  development work.
- Named long-lived agent personalities.
- A vector database, distributed queue, Kubernetes, or a third-party
  orchestration engine.
- Multi-node execution, remote/mobile control, or synchronized cloud state.
- A full code editor, local web-preview environment, generic plugin
  marketplace, or imported “agent company.”
- Removing the current Tkinter dashboard before the desktop replacement has
  verified parity.

## 5. System architecture

```text
┌──────────────────────── Tauri desktop process ────────────────────────┐
│ React/TypeScript UI                                                   │
│   Mission Control · Research · Factory Overview · Evidence · Memory   │
│                         │ typed Tauri commands/events                  │
│ Rust host               │                                             │
│   window/tray lifecycle · notifications · CLI discovery · PTYs        │
│   process supervision · diff/commit inspection                        │
│                         │ authenticated loopback requests              │
└─────────────────────────┼─────────────────────────────────────────────┘
                          ▼
┌──────────────────── bundled Python factory sidecar ───────────────────┐
│ admission · task state machine · dispatcher · policy · evaluator      │
│ candidate gates · lesson promotion · receipts · reconciliation        │
│                         │ transactional writes                         │
└─────────────────────────┼─────────────────────────────────────────────┘
                          ▼
┌──────────────────────── local durable state ──────────────────────────┐
│ factory.db (SQLite WAL) · evidence files · worktrees · terminal logs  │
└───────────────────────────────────────────────────────────────────────┘
          │ read-only inputs                         │ paper-only effects
          ▼                                          ▼
 Massive local SQLite                         Alpaca paper endpoint
```

### 5.1 Desktop frontend

The frontend is React with TypeScript inside Tauri’s Windows WebView2 window.
WebView2 is an internal renderer only: Vesper does not start a user-facing web
server, open a browser tab, or depend on internet hosting.

The frontend does not own workflow truth. It renders typed snapshots and
ordered events supplied by the Rust host. Optimistic drag-and-drop may show a
pending state, but the card moves only after the Python controller accepts and
receipts the transition.

### 5.2 Rust host

The Rust layer owns native concerns:

- Window, system-tray, notification, and explicit-quit lifecycle.
- Bundled sidecar startup, health checks, shutdown, and bounded restart.
- Windows Job Object resource enforcement and process-tree termination.
- Codex and Hermes binary discovery and version probes.
- PTY creation through `portable-pty`.
- Terminal streaming to `xterm.js`.
- Read-only Git diff, changed-file, and commit inspection for the review panel.
- A typed proxy between Tauri commands and the Python sidecar.
- Redaction before terminal output is persisted or emitted to the UI.

The Rust host must not implement a second workflow state machine.

### 5.3 Python factory sidecar

The existing Python repository remains the domain center. A new
`vesper.factory` package owns:

- Campaign admission and frozen contracts.
- Objective-wizard drafts and bounded task decomposition.
- Task creation, dependencies, leases, attempts, and transitions.
- Capability-based worker selection.
- Prompt/context packet construction.
- Structured task tools exposed to active Codex and Hermes workers.
- Receipt and evidence validation.
- Independent evaluation.
- Candidate lifecycle gates.
- Experiment lineage, reproducible replay, comparison, and collision checks.
- Operator attention classification, resource budgets, and factory analytics.
- Lesson candidates, canaries, promotion, and rollback.
- Crash reconciliation.

The sidecar binds to `127.0.0.1` on an operating-system-assigned port. Tauri
creates a random session token, passes it through the child process
environment, and proxies every request. The React layer never receives the
token or calls the sidecar directly. The port is not exposed on other network
interfaces.

### 5.4 Durable state

Factory state lives outside the Git repository under:

```text
%LOCALAPPDATA%\Vesper\Factory\
├── factory.db
├── evidence\
├── logs\
├── manifests\
└── worktrees\
```

SQLite runs in WAL mode with foreign keys enabled. Schema migrations are
transactional and create a timestamped database backup before a destructive
migration. Market data stays in its current Massive locations and is opened
read-only by research jobs.

Cleanup may remove expired disposable worktrees, bounded terminal-log tails,
and temporary files that have no receipt reference. It must never delete a run
manifest, candidate artifact, evidence object, or other file referenced by an
authoritative receipt. Storage pressure creates an Operator Inbox item and
blocks new artifact-producing work before the disk reaches the configured
reserve.

## 6. Three related state machines

The UI must not collapse campaign progress, card execution, and the existing
research workflow contract into one ambiguous status.

### 6.1 Campaign and candidate lifecycle

Factory Overview displays:

```text
ADMISSION → RESEARCH → EVALUATION → SHADOW → PAPER → LIVE_APPROVAL_REQUIRED
                    ↘             LEARNING             ↗
```

- `ADMISSION` freezes objective, scope, allowed actions, data, compute bounds,
  metrics, stop conditions, and authority.
- `RESEARCH` may contain multiple bounded experiments and corrections.
- `EVALUATION` requires deterministic checks and a fresh independent reviewer.
- `SHADOW` observes without placing orders.
- `PAPER` may use Alpaca paper only after its gate passes.
- `LIVE_APPROVAL_REQUIRED` is a hard stop. It cannot place live orders or
  change live configuration.
- `LEARNING` receives verified episodes from any stage; it is not a shortcut
  around a candidate gate.

Paper candidates run from immutable candidate-registry artifacts; they do not
overwrite `models/xgb_ranker.json`, its metadata, or the active strategy path in
`config/settings.yaml`.

P2 automation is enabled only by an explicit, human-reviewed factory policy
that grants bounded Alpaca paper execution for an admitted campaign. The
envelope names the paper account by non-secret identifier, permitted universe,
maximum gross notional, maximum positions, maximum orders per session, market
window, expiration time, and paper kill conditions. Workers cannot widen,
renew, or reinterpret the envelope. Creating or adopting the policy is a
separate authority action. The current protected `config/settings.yaml` remains
unchanged by agents. Until the policy is active, the controller stops before
any broker call and presents the exact required human action.

### 6.2 Card execution lifecycle

Mission Control uses:

```text
BACKLOG → READY → RUNNING → EVALUATING → COMPLETED
                   │             │
                   ├→ BLOCKED ←──┤
                   ├→ INTERRUPTED
                   └→ CANCELED
```

- A card becomes `READY` only when dependencies and admission guards pass.
- `RUNNING` requires an exclusive durable lease and an immutable attempt.
- The worker may iterate inside the attempt up to the campaign’s declared
  bounds.
- `EVALUATING` uses a fresh session with frozen evidence. The evaluator cannot
  modify the submitted work.
- `COMPLETED` requires an authoritative receipt.
- `BLOCKED`, `INTERRUPTED`, and `CANCELED` never imply success.

### 6.3 Workflow template lifecycle

The existing platform contract remains the default research/software template:

```text
ADMISSION → CONTRACT → IMPLEMENT → TRAIN → BACKTEST → REVIEW → NEXT
```

Not every card executes every template stage. The campaign planner creates
cards for the stages required by the frozen contract. It may not skip a
required predecessor or reinterpret a failed receipt as completion.

## 7. Core records

The first release uses explicit relational records plus JSON metadata where the
payload varies:

| Record | Responsibility |
|---|---|
| `campaigns` | Frozen standing objective, bounds, authority, budget, and stop conditions |
| `candidates` | Strategy/model candidate identity and current promotion stage |
| `tasks` | User-visible cards and accepted state |
| `task_dependencies` | Required predecessor relationships |
| `attempts` | Immutable execution attempts, runtime, model, and retry lineage |
| `leases` | Exclusive worker claims and heartbeat expiry |
| `receipts` | Append-only outcomes, hashes, authority, and evidence references |
| `events` | Ordered UI/activity stream with a monotonic sequence |
| `workers` | Ephemeral worker instances and capability template versions |
| `sessions` | CLI/PTY process identity, state, exit result, and bounded log path |
| `evidence` | Immutable artifact references, SHA-256 hashes, and purpose |
| `lessons` | Candidate, canary, active, rejected, or reverted project knowledge |
| `routing_stats` | Verified outcomes by runtime, capability template, and work kind |
| `attention_items` | Actionable approval, blocker, stall, budget, data, and safety exceptions |
| `resource_reservations` | Exclusive or bounded file, artifact, dataset, compute, and paper resources |

No table stores broker secrets, provider secrets, CLI authentication tokens, or
raw unrestricted terminal history.

## 8. Agent runtime and task dispatch

### 8.1 Capability templates

Initial templates are functional and versioned:

- Quant Research
- Data Engineering
- ML Systems
- Portfolio Evaluation
- Risk Review
- Development
- Independent Evaluator

A worker instance combines one template version, one runtime adapter, one model
selection, one task, one worktree, and one lease. Finishing the attempt ends the
worker identity. Useful knowledge is extracted into Vesper records rather than
preserved as a persona.

### 8.2 Codex and Hermes adapters

Each adapter implements the same operations:

```text
probe → start → send_task → send_instruction → interrupt → terminate → collect_exit
```

Binary resolution follows one source of truth:

1. Use the explicit absolute path saved in Vesper settings when present.
2. Otherwise search Windows application aliases and `PATH`.
3. Probe the exact resolved binary with its supported version command.
4. Save the resolved path, version, probe time, and failure reason.
5. Launch sessions with that exact path.

Shell selection is separate from agent executable selection. Choosing
PowerShell, Command Prompt, Git Bash, or WSL does not overwrite the Codex or
Hermes path.

The adapter negotiates CLI capabilities by detected version. Unsupported
versions become `BLOCKED` with a concrete remediation; Vesper does not guess
flags or display a contradictory global status.

### 8.3 Automatic card instructions

Starting a card constructs and sends a task packet containing:

- Title and complete description.
- Frozen acceptance criteria and stop conditions.
- Allowed and denied authority.
- Permitted files and worktree path.
- Required skills and repository rules.
- Dependency and predecessor receipt IDs.
- Relevant evidence and a bounded Vesper context packet.
- Expected output and receipt schema.
- A run-manifest schema requiring the dataset snapshot/hash, universe, date
  range, corporate-action adjustment version, feature version, source commit,
  dependency-lock hash, random seeds, transaction-cost and slippage settings,
  evaluation split, runtime version, and local-compute envelope.

The task packet is sent automatically when the session starts. The integrated
terminal is for observation and intervention, not mandatory manual task entry.

### 8.4 Isolation and evaluation

Code-changing attempts run in isolated Git worktrees. A worker may make bounded
corrections in the same attempt when fast tuning is part of the campaign
contract. Final evaluation always uses a fresh worker session that receives the
frozen contract, diff/artifacts, tests, and evidence, but not the authoring
conversation.

### 8.5 Structured Vesper worker tools

Every dispatched worker receives a task-scoped structured tool surface:

| Tool | Permitted effect |
|---|---|
| `vesper_task_show` | Read the frozen task, dependencies, bounds, and current receipt chain |
| `vesper_heartbeat` | Renew only the caller’s current lease |
| `vesper_submit_evidence` | Register an artifact path, hash, purpose, and manifest reference |
| `vesper_create_followup` | Propose a child card inside the admitted campaign bounds |
| `vesper_block` | Record a concrete blocker and required resolution |
| `vesper_comment` | Append a bounded task-local coordination note |
| `vesper_request_evaluation` | Seal the attempt evidence and request a fresh evaluator |

The tool server derives worker, task, campaign, and lease identity from the
session; callers cannot supply another worker’s authority. Tools return typed
results and policy errors. Workers do not shell out to mutate `factory.db`, and
database files are not exposed in their writable worktrees.

## 9. Bounded initiative and authority

### 9.1 Automatically permitted inside an admitted campaign

- Create experiments and follow-up cards inside the frozen objective.
- Retry known-safe failures up to the campaign limit.
- Adjust runtime routing, context selection, and retry order through a canary.
- Tune research candidates within declared parameter bounds.
- Run deterministic tests, training, backtests, and shadow evaluation within
  local-compute bounds.
- Promote candidates to Alpaca paper after all configured gates pass and the
  P2 policy is active.
- Commit and review non-critical code changes in isolated worktrees.

### 9.2 Automatic non-critical code acceptance

A code change may merge only when all of the following are true:

1. The campaign explicitly permits code mutation and names the merge target.
2. `AGENTS.md`, `SKILLS/CODE.md`, and `SKILLS/EXAMPLES.md` preflight passes.
3. The repository CodeGraph index exists and was queried for every changed
   symbol. A missing or stale required index blocks the attempt.
4. The diff contains no protected or denied path.
5. The smallest relevant tests, Python compilation checks, and full practical
   suite pass.
6. A fresh independent reviewer accepts the exact diff and evidence.
7. A canary run succeeds.
8. A rollback commit and immutable receipt exist before merge.

The default automatic target is the local `factory/accepted` integration
branch. A standing campaign may name local `main` only through an explicit
Brennan-approved policy. Remote push, release publication, and live deployment
remain separate human gates.

### 9.3 Always gated

- Credentials and secret handling changes.
- `config/`, `risk/`, `execution/`, or `scheduler/` changes.
- Writes under `vesper/data/massive/` or `vesper/data/model_research/`.
- Active-model replacement under the repository’s current authority policy.
- Live broker endpoints, live orders, positions, capital, or risk limits.
- Paid compute or provider use outside an approved campaign budget.
- Remote pushes, releases, or deployments.
- Expanding a campaign’s objective, path scope, compute bound, or authority.

The controller fails closed when authority is missing or ambiguous.

### 9.4 Factory-wide stop

The window header, tray menu, and Operator Inbox expose one non-delegable
**Stop Factory** control. Activating it:

1. Atomically disables new dispatch and paper-order submission.
2. Revokes pending paper authority for the current process.
3. Requests a bounded graceful stop from every active worker.
4. Terminates any worker that does not stop within 15 seconds.
5. Records interrupted attempts and one authoritative stop receipt.

Resume requires an explicit action in the local operator UI. Workers,
evaluators, routines, and restored sessions cannot invoke it. After an abnormal
application or machine shutdown, Vesper starts paused and requires an explicit
resume after reconciliation.

### 9.5 Hard local-resource budgets

Every campaign freezes limits for concurrent workers, total attempts,
per-attempt wall time, aggregate wall time, CPU share, GPU eligibility and
concurrency, memory ceiling, artifact growth, retained terminal output, and
minimum free-disk reserve. The factory also has global ceilings that a campaign
cannot exceed.

Crossing a warning threshold creates an Operator Inbox item. Crossing a hard
limit blocks new dispatch, stops the affected attempt safely, and records the
measured limit and outcome. A worker cannot modify, renew, or spend beyond its
budget, and no local budget grants paid-compute authority.

### 9.6 Reproducibility and retention

An evaluation receipt is authoritative only when its run manifest is complete,
hash-valid, and sufficient to reconstruct the run from preserved inputs. A
replay creates a new attempt linked to the original; it never edits the
original manifest or receipt. Repeated runs with the same deterministic inputs
must either match the contracted outputs or produce a failed reproducibility
gate with a field-level difference report.

Receipt-referenced evidence and candidate artifacts are pinned. Cleanup is
limited to unreferenced temporary files, expired disposable worktrees, and
bounded log data. Vesper reports reclaimable and pinned storage separately.

### 9.7 Paper authority enforcement

Before each Alpaca paper effect, the controller revalidates the active P2
envelope, paper endpoint, non-secret account identity, clock window, universe,
notional, position, order-count, and kill conditions. Validation is performed
again at effect time rather than trusted from card admission.

An envelope expiry, mismatch, global stop, configured loss condition, stale
market data, reconciliation failure, or provider ambiguity disables subsequent
paper effects and creates a high-priority Operator Inbox item. No automatic
retry occurs while effect status is ambiguous.

## 10. Evidence-backed learning

Vesper records an episode after every attempt:

- Frozen task and context hashes.
- Template, runtime, model, and software versions.
- Input and artifact hashes.
- Timing, local resource use, retries, and exit state.
- Deterministic checks.
- Independent verdict.
- Candidate lesson references.

Learning has four bounded mechanisms:

1. **Context selection:** rank existing evidence and active lessons for a work
   kind.
2. **Routing:** compare verified success, latency, and retry rates for Codex,
   Hermes, and template versions.
3. **Policy candidates:** propose bounded retry or decomposition changes.
4. **Template candidates:** version prompt/task-packet changes.

A general lesson becomes active only after three independent verified episodes
support it with no unresolved contradiction. A deterministic defect lesson may
become active from one independently reproduced failure-and-fix pair. Routing,
policy, and template changes must beat the active version in a canary and retain
the prior version for immediate rollback.

SQLite FTS5 searches evidence summaries, contracts, and lessons. Raw reports
remain canonical; Vesper stores references and hashes rather than copying
unbounded context. A vector database is deferred until measured retrieval
failures justify it.

## 11. User experience

### 11.1 Mission Control — default home

Mission Control contains:

- Left navigation for Factory, Research, Models, Evidence, Memory, and Settings.
- Top status for operating mode, market status, active agents, and next gate.
- Board columns for Backlog, Ready, Running, and Evaluation.
- A right task inspector with contract, acceptance, evidence, files, bounds,
  pause, and stop controls.
- A bottom activity/terminal area tied to the selected card.
- A single **New objective** action that opens campaign admission.

Cards display truthful state, runtime, attempt, progress, elapsed time, and gate
status. Dragging a card cannot bypass controller guards.

### 11.2 Research

Research contains:

- One selected campaign objective and bounds.
- Candidate metrics and comparison history.
- Evidence ladder for data, chronology, leakage, OOS, shadow, and paper gates.
- Experiment queue and current workers.
- Campaign conversation backed by shared Vesper context.
- Integrated terminal for the selected attempt.

The agent may create bounded corrective experiments without asking the user to
re-enter the task.

### 11.3 Factory Overview

Factory Overview presents candidate flow through Admission, Research,
Evaluation, Shadow, Paper, and Learning. It also shows:

- Live immutable activity receipts.
- Factory health and verified-task rate.
- Active workers and evaluator independence.
- Blocked gates and the exact missing evidence or approval.

### 11.4 Evidence, Memory, Models, and Settings

- **Evidence:** receipts, artifacts, hashes, tests, and evaluator verdicts.
- **Memory:** active/candidate/reverted lessons and supporting episodes.
- **Models:** candidate registry and gate history; active replacement remains
  separately governed.
- **Settings:** local paths, CLI adapters, shell, log retention, and health.
  Every adapter has a test button that exercises the same launch path used by
  cards.

## 12. Selected factory feature set

These are the nine adopted features from the compared agent workspaces. They
close first-release feature selection; adjacent features from those products
are not implicitly included.

### 12.1 Operator Inbox

The Operator Inbox contains only actionable exceptions:

- Human approval required.
- Worker blocked or waiting for bounded input.
- Heartbeat stale or progress stalled.
- Resource budget warning or hard-limit stop.
- Data stale, missing, or integrity-gate failure.
- Evaluator rejection or unresolved contradiction.
- Paper envelope stop, expiry, or provider ambiguity.
- Sidecar, database, adapter, or recovery degradation.

Each item contains severity, campaign/task/attempt identity, factual reason,
supporting receipts, the allowed actions, and whether factory progress can
continue elsewhere. Repeated events deduplicate into one item with a count.
Acknowledging an item does not alter the underlying task or safety state.
Desktop notifications are emitted only for new high-priority items or a
configured escalation, not routine progress.

### 12.2 Background factory mode

Closing the main window hides Vesper to the Windows system tray rather than
ending the process. The tray shows `Running`, `Paused`, `Attention`, or
`Degraded`, plus actions to open Mission Control, pause dispatch, stop the
factory, or quit.

**Quit Factory** stops new dispatch, settles or interrupts active attempts,
shuts down the sidecar, and exits. The interface never implies work continues
after an actual quit. Automatic startup at Windows login is not included in the
first release.

### 12.3 Objective planning wizard

**New objective** opens a short admission wizard. It asks only for missing
decisions needed to freeze:

- Research hypothesis or software outcome.
- Universe, data source, and evaluation interval.
- Acceptance metrics and rejection/stop conditions.
- Allowed code/data/model effects.
- Resource and attempt budgets.
- Candidate lifecycle ceiling.
- Required evaluator and human gates.

Vesper then proposes a campaign contract, work-template stages, dependency
graph, and resource reservations. Nothing dispatches until Brennan approves
the rendered contract. Once admitted, workers may create bounded child cards
without repeating the wizard.

### 12.4 Progressive card dossier

Every card has one dossier assembled from authoritative records:

```text
Objective → Frozen Contract → Execution Brief → Attempts/Timeline
          → Run Manifests → Artifacts/Diff → Evaluation Verdict
          → Completion or Blocker Summary → Lessons
```

The dossier is a view, not a second mutable source of truth. Each section links
to the exact receipt, hash, worker, and time that produced it. Missing sections
are shown as unsatisfied gates rather than generated narrative.

### 12.5 Experiment lineage and comparison

A candidate may be forked from any authoritative research receipt. The child
records its parent, inherited manifest, exact changed fields, and reason for the
fork. The default fork permits one declared experimental variable; broader
changes require a new contract or explicit multi-variable experiment.

Research provides side-by-side comparison of metrics, confidence/dispersion,
turnover and cost assumptions, data/evaluation hashes, gate outcomes, resource
use, and evaluator findings. **Reproduce** creates a new attempt from the
original immutable manifest and reports field-level input and output
differences; it never rewrites the original run.

### 12.6 Structured Vesper agent tools

Codex and Hermes coordinate through the task-scoped tools in Section 8.5.
Worker tools are the only supported agent path for heartbeats, evidence
submission, follow-up creation, blockers, comments, and evaluation requests.
The terminal remains available for the assigned work but is not a backdoor to
workflow-state mutation.

### 12.7 Dependency and collision graph

Every campaign can switch from board view to a directed dependency graph.
Edges identify receipt prerequisites; node badges identify current state,
worker, and reserved resources.

Before dispatch, the controller checks overlapping writable files, model or
candidate artifact targets, mutable derived datasets, GPU slots, campaign
compute ceilings, and Alpaca paper-account authority. Safe shared read-only
Massive inputs do not conflict. A resolvable collision serializes dependent
work; an undeclared or unsafe collision blocks dispatch with an Operator Inbox
item. No automatic rebase or conflict rewrite is included in the first release.

### 12.8 Factory analytics

Factory Overview reports metrics derived from receipts and measured runtime
events, never worker self-report:

- Verified completion and rejection rates.
- Autonomy ratio and human interventions.
- Time in queue, execution, evaluation, and blocked states.
- Attempts, retries, interruption, ambiguity, and rollback rates.
- Codex/Hermes and capability-template performance.
- Token/context use when the runtime exposes it.
- CPU, GPU, memory, disk, and wall-time consumption.
- Candidate survival through evaluation, shadow, and paper gates.
- Data-integrity and reproducibility failure rates.

Anomalies create attention items and may pause affected dispatch according to
the frozen policy. Analytics can be exported as local CSV; telemetry export or
cloud reporting is not included.

### 12.9 Integrated review panel

Evaluation and code cards expose a read-only changed-file tree, side-by-side
diff, commit list, test/compile results, run manifests, evidence, and independent
review findings. The operator can accept the verdict, reject it, return the
card with a bounded instruction, or stop the campaign.

The first release does not edit source, stage hunks, resolve conflicts, push,
or publish releases from this panel. Those remain agent work under policy or
explicit external Git actions.

## 13. Error handling and recovery

- Closing the window in background mode does not stop the sidecar or workers;
  explicit quit follows the shutdown receipt sequence in Section 12.2.
- A factory-wide stop takes priority over dispatch, worker, evaluator,
  background, and paper actions.
- A sidecar health failure freezes mutations, marks the UI degraded, and allows
  at most three supervised restart attempts in five minutes. Continued failure
  opens read-only recovery mode.
- A PTY or CLI crash records the exit code and creates an `INTERRUPTED` receipt.
- Lease expiry never proves the worker did nothing. Reconciliation checks
  immutable artifacts and receipts before retry.
- An unknown external effect is `AMBIGUOUS`; no automatic retry or successor is
  allowed.
- Every state transition and receipt append is one SQLite transaction.
- UI event polling uses the monotonic event sequence, so reconnect resumes from
  the last acknowledged event without losing or duplicating displayed state.
- Terminal output is bounded, redacted, and persisted by session. A crashed PTY
  is not pretended to be resumable; a new attempt starts from the last
  authoritative receipt.
- Missing Massive data, stale data, failed chronology checks, or leakage checks
  block the candidate rather than falling back to another provider.
- Resource exhaustion and storage-reserve violations block new work before
  durable evidence is endangered.
- Alpaca errors cannot trigger live endpoints, bypass risk controls, or advance
  a paper gate without required evidence.

## 14. Security and local ownership

- The application binds no service to a non-loopback interface.
- Sidecar authentication is per launch and never stored in the database.
- Existing environment/secret handling remains the credential source until a
  separately approved Windows Credential Manager migration.
- Prompts, receipts, events, and terminal logs pass through shared redaction.
- Worker-tool requests are bound to the session’s task, attempt, worker, and
  lease; the UI and workers do not receive direct database credentials.
- Worktrees and subprocess working directories are resolved to explicit,
  validated paths.
- Diff and commit inspection resolves every requested path inside the recorded
  worktree and is read-only.
- Process termination targets the recorded process tree, never an unresolved
  wildcard.
- The factory database, evidence, prompts, templates, policies, and source code
  remain locally inspectable and exportable.
- No external board, orchestration SaaS, or Vesper telemetry is required.

## 15. Selective component reuse

The product owns its engine and may reuse narrow, well-licensed components:

| Component | Intended use |
|---|---|
| Tauri 2 | Native Windows application shell and IPC |
| React + TypeScript | Desktop view layer |
| `xterm.js` | Terminal rendering |
| `portable-pty` | Windows PTY/process handling |
| `dnd-kit` | Accessible Kanban drag-and-drop |
| SQLite | Local durable state, WAL, and FTS5 |
| Terax patterns | Reference only for Tauri/PTy integration after license and code review |

Vesper will not fork another product wholesale. Reused source must have a
recorded upstream URL, commit, license, retained notice, local tests, and a
small enough boundary that Vesper can maintain it.

Kangentic, Routa, Fusion, Conductor OSS, agtx, Hermes Kanban, and
NautilusTrader are conceptual product/architecture references only. Their
presence in this specification does not approve copying source. In particular,
AGPL source is not incorporated into Vesper unless Brennan separately chooses
that licensing consequence.

## 16. Packaging and release

The Windows package contains:

- The Tauri executable and frontend assets.
- The tray icon, native notification integration, and explicit background/quit
  lifecycle.
- A PyInstaller `onedir` build of the Python factory sidecar.
- Database migrations.
- Default capability templates and policy schema.
- Required third-party notices.

The application verifies sidecar and migration versions at startup. Development
may use the repository Python environment, but a release must not require the
user to install Python, Node, Rust, Codex, or Hermes merely to open the UI.
Codex and Hermes remain separately authenticated local runtimes; unavailable
adapters are shown as blocked while the rest of Vesper remains usable.

## 17. Verification strategy

### Python

- Unit tests for transitions, leases, receipts, objective admission, campaign
  and resource bounds, attention classification, structured worker tools,
  collision detection, evaluators, candidate lineage, replay manifests, paper
  envelopes, lesson promotion, and reconciliation.
- Contract tests proving the existing lifecycle and knowledge schemas remain
  enforceable.
- Integration tests using temporary SQLite databases and fake runtimes.

### Rust

- Unit tests for binary precedence, version probe results, redaction, bounded
  restart, tray/quit lifecycle, notification deduplication, read-only diff
  inspection, path validation, and process-tree bookkeeping.
- Integration tests with fake Codex/Hermes executables and a fake sidecar.

### Frontend

- Component tests for board snapshots, rejected transitions, task inspector,
  Operator Inbox, objective wizard, dossier, experiment comparison, dependency
  graph, analytics, integrated review, adapter health, terminal selection,
  evidence ladders, and recovery mode.
- Accessibility tests for keyboard board movement and terminal focus.

### End to end and release

- Windows smoke tests for install, launch, CLI probing, automatic card prompt,
  background/tray continuation, explicit quit, global stop, automatic card
  prompt, task completion, fork/compare/reproduce, forced kill, paused restart,
  reconciliation, and uninstall.
- Migration tests from every released schema version.
- A simulated 100-task run with duplicate commands and process failures.
- Eight-hour soak with active event polling, terminal output, and sidecar
  restart injection.
- Existing Vesper Python suite remains green.
- No release while the UI can disagree with the actual CLI launch result.

## 18. Incremental delivery boundaries

This design is implemented as independently reviewable sub-projects:

1. **Factory kernel:** SQLite schema, campaigns, cards, attempts, leases,
   receipts, attention items, resource reservations, structured worker tools,
   event stream, and recovery through a Python CLI.
2. **Native shell:** Tauri application, sidecar supervision, Mission Control,
   typed IPC, tray/background lifecycle, Operator Inbox, objective wizard,
   card dossier, dependency graph, and read-only board interaction.
3. **Agent execution:** Codex/Hermes discovery, PTYs, automatic task packets,
   worktree isolation, controls, and terminal logs.
4. **Research pipeline:** Research view, deterministic evaluation, candidate
   registry and lineage, fork/compare/reproduce, shadow and paper gates,
   factory analytics, integrated review, and Factory Overview.
5. **Learning and code autonomy:** episodes, FTS context, routing/template
   canaries, bounded code acceptance, rollback, and Memory view.
6. **Release hardening:** migration backup, recovery mode, Windows packaging,
   failure injection, soak tests, and replacement-parity review.

Each sub-project must deliver working, testable software. Later sub-projects
may consume earlier interfaces but cannot weaken their receipts, authority, or
recovery guarantees.

## 19. Repository impact

The implementation will add focused factory and desktop packages without
reorganizing unrelated trading code. Expected top-level additions are:

```text
apps/desktop/                 # Tauri, React, Rust host, and frontend tests
vesper/factory/               # Python controller and domain records
tests/factory/                # Python factory tests
docs/superpowers/plans/       # Staged implementation plans
```

Existing `vesper.engine`, trading, risk, execution, scheduler, data, model
artifacts, and `config/settings.yaml` remain unchanged unless a later
exact-scope task receives the required human approval.

## 20. Acceptance boundary

Approving this specification authorizes implementation planning. It does not
authorize live trading, protected-path edits, credential handling changes,
active-model replacement, paid compute, remote push, or deployment. Those
actions retain their existing explicit gates.
