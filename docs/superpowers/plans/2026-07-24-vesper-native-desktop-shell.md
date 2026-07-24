# Vesper Native Desktop Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Tauri 2/React 19 native Vesper shell that supervises the
protocol-1 factory sidecar across planned database schemas `1..3` and presents
a truthful, accessible Mission Control experience without moving workflow
authority out of Python.

**Architecture:** Rust owns the native window, sidecar process, authenticated loopback proxy, bounded restart policy, tray, notifications, and shutdown sequencing. React owns only ephemeral presentation state: it renders authoritative snapshots, consumes ordered event envelopes, submits typed commands, and resynchronizes instead of inventing workflow transitions. Plan 03 plugs agent runtime and terminal implementations into the typed no-op boundaries created here.

**Tech Stack:** Tauri 2, Rust stable, Tokio, Reqwest, Serde, React 19.2.8, TypeScript 7.0.2, Vite 8.1.5, Vitest 4.1.10, React Testing Library 16.3.2, `@dnd-kit/core` 6.3.1, `@dnd-kit/sortable` 10.0.0, pnpm 11.17.0.

## Global Constraints

- Before any code edit, follow `AGENTS.md`: load matching skills, query the repository `.codegraph` index for every symbol/file to be changed, and read `SKILLS/CODE.md` plus `SKILLS/EXAMPLES.md`.
- The current local clone does not contain `.codegraph`. Implementation must run from the canonical Windows checkout where the index exists, or stop and refresh/create the required index before editing code.
- Do not edit `config/`, `vesper/risk.py`, `vesper/execution.py`, scheduler code, `vesper/data/massive/`, `vesper/data/model_research/`, or active model artifacts without a new exact-scope approval.
- Keep the Tkinter dashboard and current engine operational until the final parity gate.
- Use test-first changes, surgical diffs, deterministic assertions, and one focused commit per task.
- The sidecar API protocol is `1`; the planned first-release database schemas
  are `1`, `2`, and `3`. Extensions are additive; no task may rename frozen
  fields, reinterpret states, or bypass controller guards.
- Tauri creates a fresh 32-byte random token for every sidecar launch. The token is passed only as `VESPER_FACTORY_SESSION_TOKEN`, is never logged or serialized, and never reaches React.
- The sidecar binds only to `127.0.0.1` on an OS-assigned port. Rust rejects non-loopback readiness addresses and proxies every `/v1/*` request with `Authorization: Bearer <session token>`.
- Rust and React do not own campaign, candidate, task, attempt, lease, receipt, evidence, attention, reservation, or factory-mode truth. All mutations go through `POST /v1/commands`.
- Event sequence gaps, protocol mismatches, unsupported database schemas, or a
  changed sidecar generation cause a full snapshot resynchronization. The UI
  does not repair or infer missing domain events.
- A sidecar health failure freezes mutations. Rust permits at most three supervised restart attempts in a rolling five-minute window, then enters read-only recovery.
- Closing the window hides it to the Windows tray. Only explicit **Quit Factory** stops the sidecar and exits. Automatic startup at Windows login is excluded.
- **Stop Factory** has priority over dispatch, worker, evaluator, background, and paper actions. Resume is an explicit local-operator action.
- Plan 02 owns only `apps/desktop/`. It must not create or edit `apps/desktop/src-tauri/src/agents/` or terminal implementation modules, which belong to Plan 03.
- Plan 02 defines only typed runtime health, runtime-surface, and stop-participant interfaces with deterministic no-op fakes. It does not discover Codex/Hermes, launch either CLI, create a PTY, stream terminal bytes, or inspect Git.
- Research metrics, experiment comparison, factory analytics, candidate gate calculations, integrated review, learning, FTS, routing, canaries, and lesson internals are excluded.
- Massive remains read-only, Alpaca remains paper-only behind an existing P2 envelope, and no protected path, credential, live-trading, paid-compute, remote-push, or deployment authority is added.
- Use generated UUID4 idempotency keys for mutating UI commands. Store/display UTC values as RFC 3339 strings ending in `Z`; never put secrets or unbounded terminal text in frontend state.

---

## Dependencies and Hard Acceptance Gates

This plan depends on the roadmap and on the completed output of Plan 01,
`docs/superpowers/plans/2026-07-24-vesper-factory-kernel.md`. Plan 02 may be
reviewed before Plan 01 exists, but no implementation task may start until all
of the following checks pass.

### Gate D0 — canonical checkout preflight

Run from the repository root in Git Bash on Windows:

```bash
test -d .codegraph
test -f AGENTS.md
test -f SKILLS/CODE.md
test -f SKILLS/EXAMPLES.md
test -f docs/superpowers/plans/2026-07-24-vesper-factory-kernel.md
```

Expected: exit `0` for every command. If `.codegraph` is absent or stale, stop
before editing. Query every `apps/desktop/` file/symbol named by the current
task with `codegraph_explore` and record the result in the task handoff.

### Gate D1 — Plan 01/M1 contract

Plan 01 must have passed M1 and must expose the frozen process and HTTP surface:

```text
GET  /v1/health
GET  /v1/snapshot
GET  /v1/events?after=<sequence>&limit=<1..500>
POST /v1/commands
```

It must publish a process-level fake sidecar at
`tests/factory/sidecar_fixture.py`. That fixture must accept the same two
environment variables as production, bind loopback on an OS-assigned port,
emit the exact readiness line, enforce bearer authentication, return schema-1
snapshot/event envelopes, support deterministic health failure/recovery modes,
and never print the token.

Run:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest -q tests/factory
test -f tests/factory/sidecar_fixture.py
```

Expected: all Plan 01 tests pass and the fixture check exits `0`.

### Gate D2 — additive desktop projection

Plan 01 remains the owner of Python serialization. Before Plan 02 starts, its
schema-1 snapshot and command contract must supply the exact additive fields
defined under **Desktop Contract V1** below. Verify them through the Plan 01
fixture; do not change Python from this plan. If any field or command kind is
absent, stop and resolve the Plan 01 acceptance gate under Plan 01 ownership.
The native lifecycle additionally requires exact command kinds
`factory.pause`, `factory.resume`, and `factory.stop`, each using the frozen
command envelope and `snapshot.factory.version` as `expected_version`.

### Gate D3 — Plan 02/M2 completion

Plan 02 is complete only when:

- a Tauri development executable starts the exact configured sidecar command,
  validates readiness, and never exposes the token to React;
- Mission Control renders from a snapshot plus ordered events and resyncs on a
  gap, protocol mismatch, unsupported database schema, or sidecar restart;
- board transition requests stay pending until accepted and visibly revert on
  controller rejection;
- the inspector, activity shell, objective wizard, Operator Inbox, dossier,
  dependency graph, settings health, and read-only recovery states pass
  component tests;
- mouse and keyboard drag behavior use the same controller command and provide
  focus, instructions, live announcements, cancellation, and rejection copy;
- window close, tray open, pause, resume, stop, quit, notification
  deduplication, bounded restart, and read-only mutation denial pass Rust tests;
- frontend lint/test/build and Rust format/clippy/test commands all pass; and
- M2 from the roadmap is satisfied without creating Plan 03, Plan 04, or
  Plan 05 behavior.

### Gate D4 — interfaces published to Plan 03

Plan 03 depends on these exact Plan 02 outputs:

```rust
#[async_trait::async_trait]
pub trait RuntimeStopParticipant: Send + Sync {
    async fn request_stop_all(&self, deadline: Duration) -> RuntimeStopReportV1;
    async fn terminate_remaining(&self) -> RuntimeStopReportV1;
}
```

```ts
export interface RuntimeSurfaceProps {
  selectedTaskId: TaskId | null;
  session: SessionV1 | null;
  readOnly: boolean;
}

export type RuntimeSurface = ComponentType<RuntimeSurfaceProps>;
```

Plan 03 implements these interfaces inside its owned runtime/terminal modules.
It must not replace the sidecar proxy, event cursor, lifecycle authority, or
Mission Control state source.

---

## Desktop Contract V1

These types are the only domain projection React may render. Rust mirrors them
with Serde using `#[serde(rename_all = "SCREAMING_SNAKE_CASE")]` for enums and
`#[serde(deny_unknown_fields)]` only on the readiness object and UI command
payloads. Snapshot records remain additive across database schemas `1..3`.

```ts
export type CampaignStatus =
  | "DRAFT" | "ADMITTED" | "PAUSED" | "STOPPED" | "CLOSED";
export type CandidateStage =
  | "ADMISSION" | "RESEARCH" | "EVALUATION" | "SHADOW"
  | "PAPER" | "LIVE_APPROVAL_REQUIRED" | "ARCHIVED";
export type TaskState =
  | "BACKLOG" | "READY" | "RUNNING" | "EVALUATING" | "COMPLETED"
  | "BLOCKED" | "INTERRUPTED" | "CANCELED";
export type AttemptOutcome =
  | "VERIFIED" | "REJECTED" | "FAILED" | "BLOCKED"
  | "INCONCLUSIVE" | "INTERRUPTED" | "AMBIGUOUS";
export type AttentionSeverity = "INFO" | "WARNING" | "HIGH" | "CRITICAL";
export type FactoryMode = "RUNNING" | "PAUSED" | "STOPPED";
export type FactoryHealth =
  | "HEALTHY"
  | "DEGRADED"
  | "RECOVERING"
  | "READ_ONLY_RECOVERY";
export type AgentRuntime = "CODEX" | "HERMES";
export type TaskId = `tsk_${string}`;
export type CampaignId = `cmp_${string}`;
export type CandidateId = `cnd_${string}`;
export type AttemptId = `atm_${string}`;
export type WorkerId = `wrk_${string}`;
export type SessionId = `ses_${string}`;
export type EventId = `evt_${string}`;
export type EvidenceId = `evd_${string}`;
export type ReceiptId = `rcp_${string}`;
export type AttentionId = `att_${string}`;
export type ReservationId = `rsv_${string}`;

export interface FactorySnapshotV1 {
  protocol: 1;
  generated_at: string;
  last_event_sequence: number;
  factory: {
    version: number;
    mode: FactoryMode;
    health: FactoryHealth;
    market_status: "OPEN" | "CLOSED" | "UNKNOWN";
    next_gate: { label: string; candidate_id: CandidateId | null } | null;
  };
  campaigns: CampaignV1[];
  candidates: CandidateV1[];
  tasks: TaskV1[];
  attempts: AttemptV1[];
  workers: WorkerV1[];
  sessions: SessionV1[];
  attention_items: AttentionItemV1[];
  resource_reservations: ResourceReservationV1[];
}

export interface CampaignV1 {
  campaign_id: CampaignId;
  title: string;
  objective: string;
  status: CampaignStatus;
  version: number;
}

export interface CandidateV1 {
  candidate_id: CandidateId;
  campaign_id: CampaignId;
  name: string;
  stage: CandidateStage;
  next_gate: string | null;
}

export interface TaskV1 {
  task_id: TaskId;
  campaign_id: CampaignId;
  title: string;
  description: string;
  state: TaskState;
  version: number;
  runtime: AgentRuntime | null;
  attempt_id: AttemptId | null;
  progress: { completed: number; total: number; label: string };
  elapsed_seconds: number;
  gate: {
    status: "SATISFIED" | "UNSATISFIED" | "PENDING";
    label: string;
    missing: string[];
  };
  dependency_ids: TaskId[];
  reserved_resource_ids: ReservationId[];
  acceptance_criteria: string[];
  permitted_paths: string[];
  bounds: Array<{ label: string; value: string }>;
  dossier: TaskDossierV1;
}

export interface AttemptV1 {
  attempt_id: AttemptId;
  task_id: TaskId;
  runtime: AgentRuntime;
  outcome: AttemptOutcome | null;
  started_at: string;
  ended_at: string | null;
}

export interface WorkerV1 {
  worker_id: WorkerId;
  task_id: TaskId;
  attempt_id: AttemptId;
  runtime: AgentRuntime;
  state: "STARTING" | "ACTIVE" | "STOPPING" | "EXITED";
}

export interface SessionV1 {
  session_id: SessionId;
  task_id: TaskId;
  attempt_id: AttemptId;
  state: "STARTING" | "RUNNING" | "EXITED" | "INTERRUPTED";
  started_at: string;
  ended_at: string | null;
}

export type AttentionAction =
  | "ACKNOWLEDGE" | "OPEN_TASK" | "OPEN_CAMPAIGN"
  | "PAUSE_FACTORY" | "STOP_FACTORY";

export interface AttentionItemV1 {
  attention_id: AttentionId;
  version: number;
  severity: AttentionSeverity;
  kind:
    | "APPROVAL_REQUIRED" | "WORKER_BLOCKED" | "HEARTBEAT_STALE"
    | "RESOURCE_LIMIT" | "DATA_INTEGRITY" | "EVALUATOR_REJECTED"
    | "PAPER_STOP" | "SIDECAR_DEGRADED" | "DATABASE_DEGRADED"
    | "ADAPTER_DEGRADED" | "RECOVERY_REQUIRED";
  campaign_id: CampaignId | null;
  task_id: TaskId | null;
  attempt_id: AttemptId | null;
  reason: string;
  receipt_ids: ReceiptId[];
  allowed_actions: AttentionAction[];
  progress_can_continue: boolean;
  occurrence_count: number;
  acknowledged_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ResourceReservationV1 {
  reservation_id: ReservationId;
  campaign_id: CampaignId;
  task_id: TaskId | null;
  kind: "FILE" | "ARTIFACT" | "DATASET" | "COMPUTE" | "PAPER_ACCOUNT";
  target: string;
  mode: "READ" | "WRITE" | "EXCLUSIVE" | "BOUNDED";
  state: "PLANNED" | "ACTIVE" | "RELEASED" | "BLOCKED";
}

export type DossierSectionId =
  | "OBJECTIVE" | "FROZEN_CONTRACT" | "EXECUTION_BRIEF"
  | "ATTEMPTS_TIMELINE" | "RUN_MANIFESTS" | "ARTIFACTS_DIFF"
  | "EVALUATION_VERDICT" | "COMPLETION_BLOCKER" | "LESSONS";

export interface TaskDossierV1 {
  sections: Array<{
    section_id: DossierSectionId;
    title: string;
    status: "AVAILABLE" | "UNSATISFIED";
    missing_gate: string | null;
    entries: Array<{
      label: string;
      value: string;
      receipt_id: ReceiptId | null;
      evidence_id: EvidenceId | null;
      hash: `sha256:${string}` | null;
      worker_id: WorkerId | null;
      occurred_at: string | null;
    }>;
  }>;
}

export interface FactoryEventV1 {
  sequence: number;
  event_id: EventId;
  kind: string;
  aggregate_type: string;
  aggregate_id: string;
  occurred_at: string;
  payload: Record<string, unknown>;
}

export interface EventPageV1 {
  protocol: 1;
  events: FactoryEventV1[];
  last_event_sequence: number;
}
```

The objective wizard submits exactly this draft and receives exactly this
proposal:

```ts
export interface ObjectiveDraftV1 {
  kind: "RESEARCH_HYPOTHESIS" | "SOFTWARE_OUTCOME";
  objective: string;
  universe: string;
  data_source: "MASSIVE_LOCAL_READ_ONLY";
  evaluation_start: string;
  evaluation_end: string;
  acceptance_criteria: string[];
  stop_conditions: string[];
  allowed_effects: {
    code: "READ_ONLY" | "PERMITTED_PATHS_ONLY";
    data: "READ_ONLY";
    model: "NONE" | "CANDIDATE_ARTIFACT_ONLY";
    paper: "DENIED" | "EXISTING_P2_ENVELOPE_REQUIRED";
  };
  budgets: {
    max_concurrent_workers: number;
    max_attempts: number;
    per_attempt_wall_minutes: number;
    aggregate_wall_minutes: number;
    cpu_percent_ceiling: number;
    gpu_eligible: boolean;
    gpu_concurrency: number;
    memory_mb_ceiling: number;
    artifact_bytes_ceiling: number;
    terminal_bytes_ceiling: number;
    min_free_disk_bytes: number;
  };
  lifecycle_ceiling:
    | "RESEARCH" | "EVALUATION" | "SHADOW"
    | "PAPER" | "LIVE_APPROVAL_REQUIRED";
  evaluator: "INDEPENDENT_EVALUATOR";
  human_gates: Array<
    "CONTRACT_APPROVAL" | "PAPER_ENVELOPE" | "LIVE_APPROVAL"
  >;
}

export interface CampaignPlanV1 {
  draft_id: string;
  version: number;
  contract_hash: `sha256:${string}`;
  rendered_contract: string;
  stages: Array<{ stage_id: string; title: string; order: number }>;
  dependencies: Array<{ predecessor_stage_id: string; successor_stage_id: string }>;
  reservations: Array<{
    kind: ResourceReservationV1["kind"];
    target: string;
    mode: ResourceReservationV1["mode"];
  }>;
}
```

The generic sidecar command remains the frozen roadmap envelope. The desktop
allowlist and payloads are:

```ts
export interface UiCommandPayloads {
  "task.transition": { task_id: TaskId; target_state: TaskState };
  "task.pause": { task_id: TaskId };
  "task.stop": { task_id: TaskId };
  "campaign.plan": { draft: ObjectiveDraftV1 };
  "campaign.admit": {
    draft_id: string;
    contract_hash: `sha256:${string}`;
  };
  "attention.acknowledge": { attention_id: AttentionId };
}

export type UiCommandKind = keyof UiCommandPayloads;

export interface FactoryCommandV1<K extends UiCommandKind = UiCommandKind> {
  protocol: 1;
  idempotency_key: string;
  kind: K;
  payload: UiCommandPayloads[K];
  expected_version: number;
}

export interface CommandResponseV1 {
  ok: true;
  command_id: `cmd_${string}`;
  result: Record<string, unknown>;
  last_event_sequence: number;
}
```

Rust exposes only these Tauri commands to React:

```rust
async fn desktop_status(state: State<'_, DesktopState>) -> Result<DesktopStatusV1, DesktopErrorV1>;
async fn factory_snapshot(state: State<'_, DesktopState>) -> Result<ProxyEnvelopeV1<FactorySnapshotV1>, DesktopErrorV1>;
async fn factory_events(after: u64, limit: u16, state: State<'_, DesktopState>) -> Result<ProxyEnvelopeV1<EventPageV1>, DesktopErrorV1>;
async fn factory_command(command: FactoryCommandV1, state: State<'_, DesktopState>) -> Result<ProxyEnvelopeV1<CommandResponseV1>, DesktopErrorV1>;
async fn desktop_probe_health(state: State<'_, DesktopState>) -> Result<DesktopStatusV1, DesktopErrorV1>;
async fn desktop_notify_attention(request: AttentionNotificationV1, state: State<'_, DesktopState>) -> Result<NotificationOutcomeV1, DesktopErrorV1>;
async fn desktop_lifecycle(action: LifecycleActionV1, state: State<'_, DesktopState>) -> Result<LifecycleOutcomeV1, DesktopErrorV1>;
```

The native host envelopes are:

```ts
export type HostState =
  | "STARTING" | "HEALTHY" | "RESTARTING"
  | "READ_ONLY_RECOVERY" | "STOPPED";

export interface ProxyEnvelopeV1<T> {
  generation: number;
  read_only: boolean;
  data: T;
}

export interface RuntimeAdapterHealthV1 {
  runtime: AgentRuntime;
  state: "NOT_CONFIGURED" | "AVAILABLE" | "BLOCKED";
  resolved_path: string | null;
  version: string | null;
  checked_at: string | null;
  reason: string | null;
}

export interface DesktopStatusV1 {
  host_state: HostState;
  generation: number;
  read_only: boolean;
  factory_home: string;
  sidecar_path: string;
  sidecar_pid: number | null;
  protocol: 1 | null;
  schema: 1 | 2 | 3 | null;
  restart_attempts_in_window: number;
  last_health_at: string | null;
  last_error: string | null;
  runtime_adapters: RuntimeAdapterHealthV1[];
}

export type LifecycleActionV1 = "PAUSE" | "RESUME" | "STOP" | "QUIT";
```

---

## File Map

All paths below are relative to the repository root.

| Path | Responsibility |
|---|---|
| `apps/desktop/package.json` | Pinned frontend/Tauri scripts and dependencies |
| `apps/desktop/pnpm-lock.yaml` | Reproducible JavaScript dependency lock |
| `apps/desktop/index.html` | Tauri WebView entry document |
| `apps/desktop/tsconfig.json` | Strict TypeScript project |
| `apps/desktop/vite.config.ts` | Vite and Vitest configuration |
| `apps/desktop/eslint.config.js` | Zero-warning TypeScript/React lint policy |
| `apps/desktop/src/main.tsx` | React 19 `createRoot` entry |
| `apps/desktop/src/App.tsx` | Route shell and recovery boundary |
| `apps/desktop/src/styles.css` | Desktop layout, focus, contrast, and responsive rules |
| `apps/desktop/src/test/setup.ts` | Testing Library matchers and deterministic browser shims |
| `apps/desktop/src/contracts/factory.ts` | Exact Desktop Contract V1 TypeScript types |
| `apps/desktop/src/contracts/fixture.ts` | Deterministic schema-1 test factory |
| `apps/desktop/src/lib/desktop-api.ts` | Typed Tauri invoke wrapper; sole frontend IPC entry |
| `apps/desktop/src/state/factory-sync.ts` | Snapshot/event cursor state machine |
| `apps/desktop/src/state/use-factory-sync.ts` | Non-overlapping polling and resync hook |
| `apps/desktop/src/features/mission-control/` | Header, board, cards, inspector, and activity shell |
| `apps/desktop/src/features/objective/` | Objective draft, validation, proposal, and admission UI |
| `apps/desktop/src/features/inbox/` | Actionable attention list and actions |
| `apps/desktop/src/features/dossier/` | Fixed-order authoritative dossier view |
| `apps/desktop/src/features/dependencies/` | Deterministic dependency layout and accessible list |
| `apps/desktop/src/features/settings/` | Sidecar/runtime health and local path view |
| `apps/desktop/src/features/runtime/runtime-surface.tsx` | Plan 03 React interface and no-op surface |
| `apps/desktop/src-tauri/Cargo.toml` | Native crate and pinned Rust dependency ranges |
| `apps/desktop/src-tauri/Cargo.lock` | Reproducible Rust dependency lock |
| `apps/desktop/src-tauri/build.rs` | Tauri build entry |
| `apps/desktop/src-tauri/tauri.conf.json` | Native window, CSP, bundle identity, and icon |
| `apps/desktop/src-tauri/capabilities/default.json` | Minimal main-window capability |
| `apps/desktop/src-tauri/icons/icon.ico` | Existing Vesper icon copied into the desktop package |
| `apps/desktop/src-tauri/src/main.rs` | Native executable entry |
| `apps/desktop/src-tauri/src/lib.rs` | Tauri builder, managed state, commands, tray, notifications |
| `apps/desktop/src-tauri/src/contracts.rs` | Serde mirror of Desktop Contract V1 |
| `apps/desktop/src-tauri/src/error.rs` | Stable serializable desktop error |
| `apps/desktop/src-tauri/src/ipc.rs` | Typed Tauri command handlers and UI command allowlist |
| `apps/desktop/src-tauri/src/sidecar/readiness.rs` | Strict readiness-line parser |
| `apps/desktop/src-tauri/src/sidecar/launch.rs` | Token, home/path resolution, and child environment |
| `apps/desktop/src-tauri/src/sidecar/client.rs` | Authenticated loopback HTTP client |
| `apps/desktop/src-tauri/src/sidecar/supervisor.rs` | Health, restart budget, generation, cache, recovery |
| `apps/desktop/src-tauri/src/runtime_boundary.rs` | Plan 03 stop-participant interface and no-op fake |
| `apps/desktop/src-tauri/src/notifications.rs` | High-priority notification policy and deduplication |
| `apps/desktop/src-tauri/src/lifecycle.rs` | Pause/resume/stop/quit sequencing |
| `apps/desktop/src-tauri/src/tray.rs` | Tray state/menu and close-to-background behavior |
| `apps/desktop/src-tauri/tests/sidecar_process.rs` | Process/auth/restart integration with Plan 01 fake |

Do not create `apps/desktop/src-tauri/src/agents/`,
`apps/desktop/src/features/terminal/`, Git review modules, Research analytics,
Factory analytics, or Memory modules in this plan.

---

### Task 1: Scaffold the React 19 and Tauri 2 Workspace

**Files:**
- Create: `apps/desktop/package.json`
- Create: `apps/desktop/pnpm-lock.yaml`
- Create: `apps/desktop/index.html`
- Create: `apps/desktop/tsconfig.json`
- Create: `apps/desktop/vite.config.ts`
- Create: `apps/desktop/eslint.config.js`
- Create: `apps/desktop/src/test/setup.ts`
- Create: `apps/desktop/src/App.test.tsx`
- Create: `apps/desktop/src/main.tsx`
- Create: `apps/desktop/src/App.tsx`
- Create: `apps/desktop/src/styles.css`
- Create: `apps/desktop/src-tauri/Cargo.toml`
- Create: `apps/desktop/src-tauri/Cargo.lock`
- Create: `apps/desktop/src-tauri/build.rs`
- Create: `apps/desktop/src-tauri/tauri.conf.json`
- Create: `apps/desktop/src-tauri/capabilities/default.json`
- Create: `apps/desktop/src-tauri/icons/icon.ico`
- Create: `apps/desktop/src-tauri/src/main.rs`
- Create: `apps/desktop/src-tauri/src/lib.rs`

**Interfaces:**
- Consumes: no desktop code; Gate D0 and the repository icon at `assets/dashboard.ico`.
- Produces: React entry `createRoot(document.getElementById("root")!)`,
  `App(): JSX.Element`, and Rust entry `vesper_desktop_lib::run()`.

- [ ] **Step 1: Create the deterministic toolchain files and failing smoke tests**

Use the exact dependency versions from the Tech Stack. `package.json` must
contain:

```json
{
  "name": "vesper-desktop",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "packageManager": "pnpm@11.17.0",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "lint": "eslint . --max-warnings=0",
    "test": "vitest",
    "tauri": "tauri"
  },
  "dependencies": {
    "@dnd-kit/core": "6.3.1",
    "@dnd-kit/sortable": "10.0.0",
    "@dnd-kit/utilities": "3.2.2",
    "@tauri-apps/api": "2.11.1",
    "react": "19.2.8",
    "react-dom": "19.2.8"
  },
  "devDependencies": {
    "@eslint/js": "10.0.1",
    "@tauri-apps/cli": "2.11.4",
    "@testing-library/jest-dom": "7.0.0",
    "@testing-library/react": "16.3.2",
    "@testing-library/user-event": "14.6.1",
    "@types/react": "19.2.17",
    "@types/react-dom": "19.2.3",
    "@vitejs/plugin-react": "6.0.4",
    "eslint": "10.7.0",
    "jsdom": "29.1.1",
    "typescript": "7.0.2",
    "typescript-eslint": "8.65.0",
    "vite": "8.1.5",
    "vitest": "4.1.10"
  }
}
```

Configure strict TypeScript (`strict`, `noUncheckedIndexedAccess`,
`exactOptionalPropertyTypes`, `noFallthroughCasesInSwitch`,
`useUnknownInCatchVariables`), Vitest `jsdom`, and
`setupFiles: ["./src/test/setup.ts"]`. The first frontend test is:

```tsx
import { render, screen } from "@testing-library/react";
import { App } from "./App";

it("renders the native shell identity", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "Vesper Mission Control" }))
    .toBeInTheDocument();
});
```

Create `Cargo.toml` with:

```toml
[package]
name = "vesper-desktop"
version = "0.1.0"
edition = "2024"
rust-version = "1.85"

[lib]
name = "vesper_desktop_lib"
crate-type = ["staticlib", "cdylib", "rlib"]

[build-dependencies]
tauri-build = "2"

[dependencies]
async-trait = "0.1"
base64 = "0.22"
rand = "0.9"
reqwest = { version = "0.13.4", default-features = false, features = ["json"] }
secrecy = "0.10"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tauri = { version = "2", features = ["tray-icon"] }
tauri-plugin-notification = "2"
thiserror = "2"
tokio = { version = "1", features = ["io-util", "macros", "process", "rt-multi-thread", "sync", "time"] }
url = "2"
uuid = { version = "1", features = ["serde", "v4"] }

[dev-dependencies]
tempfile = "3"
wiremock = "0.6"
```

Add a Rust unit test in `src-tauri/src/lib.rs` that imports the not-yet-created
constant:

```rust
#[cfg(test)]
mod tests {
    #[test]
    fn shell_name_is_stable() {
        assert_eq!(super::APP_NAME, "Vesper");
    }
}
```

- [ ] **Step 2: Run the smoke tests to verify they fail**

Run:

```bash
cd apps/desktop
corepack prepare pnpm@11.17.0 --activate
pnpm install
pnpm test --run src/App.test.tsx
cd src-tauri
cargo test shell_name_is_stable
```

Expected: Vitest fails because `src/App.tsx` does not exist; Cargo fails because
`APP_NAME` is not defined.

- [ ] **Step 3: Add the minimal native and React shell**

`src/App.tsx`:

```tsx
export function App() {
  return (
    <main className="app-shell">
      <h1>Vesper Mission Control</h1>
    </main>
  );
}
```

`src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

`src-tauri/src/lib.rs`:

```rust
pub const APP_NAME: &str = "Vesper";

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("failed to run Vesper desktop");
}

#[cfg(test)]
mod tests {
    #[test]
    fn shell_name_is_stable() {
        assert_eq!(super::APP_NAME, "Vesper");
    }
}
```

`src-tauri/src/main.rs`:

```rust
fn main() {
    vesper_desktop_lib::run();
}
```

Set Tauri identifier `com.vesper.factory`, one `main` window titled `Vesper`,
minimum size `1120x720`, initial size `1440x900`, and CSP:

```text
default-src 'self'; connect-src ipc: http://ipc.localhost; img-src 'self' asset: http://asset.localhost; style-src 'self' 'unsafe-inline'
```

The capability contains only `core:default` for window `main`; do not grant
shell execution to JavaScript. Copy `assets/dashboard.ico` to the exact icon
path in this task.

- [ ] **Step 4: Run scaffold verification**

Run:

```bash
cd apps/desktop
pnpm lint
pnpm test --run src/App.test.tsx
pnpm build
cd src-tauri
cargo fmt --check
cargo test shell_name_is_stable
```

Expected: every command exits `0`; Vitest reports one passing test and Cargo
reports one passing test.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop
git diff --check --cached
git commit -m "build: scaffold native desktop shell"
```

### Task 2: Freeze Shared Schema-1 Desktop Contracts

**Files:**
- Create: `apps/desktop/src/contracts/factory.ts`
- Create: `apps/desktop/src/contracts/fixture.ts`
- Create: `apps/desktop/src/contracts/factory.test.ts`
- Create: `apps/desktop/src-tauri/src/contracts.rs`
- Modify: `apps/desktop/src-tauri/src/lib.rs`

**Interfaces:**
- Consumes: the exact Desktop Contract V1 types in this plan and Plan 01 Gate D2.
- Produces: `FactorySnapshotV1`, `FactoryEventV1`, `EventPageV1`,
  `FactoryCommandV1`, `CommandResponseV1`, `ProxyEnvelopeV1<T>`,
  `DesktopStatusV1`, `ObjectiveDraftV1`, `CampaignPlanV1`, and
  `makeFactorySnapshot(overrides)`.

- [ ] **Step 1: Write failing TypeScript and Rust contract tests**

The TypeScript test must assert exact frozen values and prefix-safe IDs:

```ts
import { makeFactorySnapshot } from "./fixture";

it("builds a protocol-1 snapshot with the frozen task lifecycle", () => {
  const snapshot = makeFactorySnapshot();
  expect(snapshot.protocol).toBe(1);
  expect(snapshot.factory.mode).toBe("PAUSED");
  expect(snapshot.tasks[0]).toMatchObject({
    task_id: "tsk_alpha",
    state: "READY",
    version: 4,
  });
  expect(snapshot.last_event_sequence).toBe(42);
});
```

The Rust test deserializes a complete inline JSON snapshot containing one
campaign, one task, one attention item, and empty remaining arrays, then
asserts protocol `1`, schema-compatible enum values, task version `4`, and
sequence `42`.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd apps/desktop
pnpm test --run src/contracts/factory.test.ts
cd src-tauri
cargo test contracts::tests
```

Expected: TypeScript fails because `contracts/fixture` is unresolved; Cargo
fails because module `contracts` is unresolved.

- [ ] **Step 3: Add exact TypeScript types, fixture factory, and Serde mirrors**

Copy the complete **Desktop Contract V1** TypeScript declarations into
`src/contracts/factory.ts` without widening enums to `string`. Add:

```ts
export function makeFactorySnapshot(
  overrides: Partial<FactorySnapshotV1> = {},
): FactorySnapshotV1 {
  const base: FactorySnapshotV1 = {
    protocol: 1,
    generated_at: "2026-07-24T12:00:00Z",
    last_event_sequence: 42,
    factory: {
      version: 7,
      mode: "PAUSED",
      health: "HEALTHY",
      market_status: "CLOSED",
      next_gate: null,
    },
    campaigns: [{
      campaign_id: "cmp_alpha",
      title: "Alpha campaign",
      objective: "Verify the desktop contract.",
      status: "ADMITTED",
      version: 2,
    }],
    candidates: [],
    tasks: [{
      task_id: "tsk_alpha",
      campaign_id: "cmp_alpha",
      title: "Contract task",
      description: "Render one authoritative card.",
      state: "READY",
      version: 4,
      runtime: null,
      attempt_id: null,
      progress: { completed: 0, total: 1, label: "Ready" },
      elapsed_seconds: 0,
      gate: { status: "SATISFIED", label: "Admission", missing: [] },
      dependency_ids: [],
      reserved_resource_ids: [],
      acceptance_criteria: ["Schema one parses."],
      permitted_paths: ["apps/desktop/"],
      bounds: [{ label: "Attempts", value: "1" }],
      dossier: { sections: [] },
    }],
    attempts: [],
    workers: [],
    sessions: [],
    attention_items: [{
      attention_id: "att_alpha",
      version: 1,
      severity: "WARNING",
      kind: "APPROVAL_REQUIRED",
      campaign_id: "cmp_alpha",
      task_id: "tsk_alpha",
      attempt_id: null,
      reason: "Contract approval is required.",
      receipt_ids: [],
      allowed_actions: ["ACKNOWLEDGE", "OPEN_TASK"],
      progress_can_continue: true,
      occurrence_count: 1,
      acknowledged_at: null,
      created_at: "2026-07-24T12:00:00Z",
      updated_at: "2026-07-24T12:00:00Z",
    }],
    resource_reservations: [],
  };
  return { ...base, ...overrides };
}
```

In Rust, use `u64` for versions/sequences, `u16` for protocol/schema, `u32`
for PIDs/counts, `Option<T>` for JSON null, and `serde_json::Value` only for
event payloads and command results. Add the exact host envelope:

```rust
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ProxyEnvelopeV1<T> {
    pub generation: u64,
    pub read_only: bool,
    pub data: T,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct DesktopStatusV1 {
    pub host_state: HostState,
    pub generation: u64,
    pub read_only: bool,
    pub factory_home: String,
    pub sidecar_path: String,
    pub sidecar_pid: Option<u32>,
    pub protocol: Option<u16>,
    pub schema: Option<u16>,
    pub restart_attempts_in_window: u32,
    pub last_health_at: Option<String>,
    pub last_error: Option<String>,
    pub runtime_adapters: Vec<RuntimeAdapterHealthV1>,
}
```

Do not derive `Default` for domain enums; tests must provide an explicit state.

- [ ] **Step 4: Run contract tests**

Run:

```bash
cd apps/desktop
pnpm test --run src/contracts/factory.test.ts
cd src-tauri
cargo fmt --check
cargo test contracts::tests
```

Expected: both focused suites pass.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/contracts apps/desktop/src-tauri/src/contracts.rs apps/desktop/src-tauri/src/lib.rs
git diff --check --cached
git commit -m "feat: define desktop factory contracts"
```

### Task 3: Generate Secrets and Parse the Startup Handshake

**Files:**
- Create: `apps/desktop/src-tauri/src/error.rs`
- Create: `apps/desktop/src-tauri/src/sidecar/mod.rs`
- Create: `apps/desktop/src-tauri/src/sidecar/readiness.rs`
- Create: `apps/desktop/src-tauri/src/sidecar/launch.rs`
- Modify: `apps/desktop/src-tauri/src/lib.rs`

**Interfaces:**
- Consumes: readiness prefix
  `VESPER_FACTORY_READY `, protocol `1`, database schema `1..3`, child PID,
  `%LOCALAPPDATA%`, resource directory, and optional development environment.
- Produces: `SessionToken::generate()`, `parse_readiness(line, child_pid)`,
  `resolve_launch(LaunchInputs)`, and `LaunchSpec`.

- [ ] **Step 1: Write failing startup-contract tests**

```rust
#[test]
fn parses_exact_readiness_and_checks_child_pid() {
    let ready = parse_readiness(
        r#"VESPER_FACTORY_READY {"protocol":1,"port":54321,"pid":1234,"schema":1}"#,
        1234,
    ).unwrap();
    assert_eq!(ready.port, 54321);
    assert_eq!(ready.schema, 1);
}

#[test]
fn rejects_wrong_protocol_unsupported_schema_pid_and_trailing_text() {
    for line in [
        r#"VESPER_FACTORY_READY {"protocol":2,"port":54321,"pid":1234,"schema":1}"#,
        r#"VESPER_FACTORY_READY {"protocol":1,"port":54321,"pid":9999,"schema":1}"#,
        r#"VESPER_FACTORY_READY {"protocol":1,"port":54321,"pid":1234,"schema":0}"#,
        r#"VESPER_FACTORY_READY {"protocol":1,"port":54321,"pid":1234,"schema":4}"#,
        r#"VESPER_FACTORY_READY {"protocol":1,"port":54321,"pid":1234,"schema":1} extra"#,
    ] {
        assert!(parse_readiness(line, 1234).is_err(), "{line}");
    }
}

#[test]
fn token_is_32_urlsafe_bytes_and_debug_is_redacted() {
    let token = SessionToken::generate();
    let decoded = base64::engine::general_purpose::URL_SAFE_NO_PAD
        .decode(token.expose_for_header()).unwrap();
    assert_eq!(decoded.len(), 32);
    assert_eq!(format!("{token:?}"), "SessionToken([REDACTED])");
}
```

Add path tests proving:

- factory home is exactly `<LOCALAPPDATA>/Vesper/Factory`;
- `VESPER_FACTORY_DEV_SIDECAR` must be an existing absolute file;
- `VESPER_FACTORY_DEV_SIDECAR_ARGS_JSON` must be a JSON string array;
- production resolves exactly
  `<resource_dir>/sidecar/vesper-factory.exe`; and
- no launch error includes token bytes.

- [ ] **Step 2: Run startup tests to verify they fail**

Run:

```bash
cd apps/desktop/src-tauri
cargo test sidecar::readiness::tests sidecar::launch::tests
```

Expected: Cargo fails because the `sidecar` modules and `SessionToken` do not
exist.

- [ ] **Step 3: Add strict readiness, token, and launch resolution**

Use:

```rust
const READY_PREFIX: &str = "VESPER_FACTORY_READY ";

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ReadyLineV1 {
    pub protocol: u16,
    pub port: u16,
    pub pid: u32,
    pub schema: u16,
}

pub fn parse_readiness(line: &str, child_pid: u32) -> Result<ReadyLineV1, DesktopError> {
    let json = line.strip_prefix(READY_PREFIX)
        .ok_or(DesktopError::InvalidReadiness("missing prefix".into()))?;
    let ready: ReadyLineV1 = serde_json::from_str(json)
        .map_err(|error| DesktopError::InvalidReadiness(error.to_string()))?;
    if ready.protocol != 1
        || !(1..=3).contains(&ready.schema)
        || ready.pid != child_pid
        || ready.port == 0
    {
        return Err(DesktopError::InvalidReadiness(
            "protocol, schema, pid, or port mismatch".into(),
        ));
    }
    Ok(ready)
}
```

`SessionToken` wraps `secrecy::SecretString`, implements a manual redacted
`Debug`, and exposes bytes only through a crate-private
`expose_for_header(&self) -> &str`. `LaunchSpec` is exact:

```rust
pub struct LaunchSpec {
    pub program: PathBuf,
    pub args: Vec<String>,
    pub factory_home: PathBuf,
    pub display_path: PathBuf,
}

pub struct LaunchInputs {
    pub local_app_data: PathBuf,
    pub resource_dir: PathBuf,
    pub environment: BTreeMap<OsString, OsString>,
}
```

The spawn environment adds only:

```text
VESPER_FACTORY_SESSION_TOKEN=<base64url token>
VESPER_FACTORY_HOME=<absolute LOCALAPPDATA/Vesper/Factory>
```

Do not put the token in an argument, status DTO, error, event, tracing field,
or test snapshot.

- [ ] **Step 4: Run startup-contract tests**

Run:

```bash
cd apps/desktop/src-tauri
cargo fmt --check
cargo test sidecar::readiness::tests sidecar::launch::tests
```

Expected: all readiness, token, and path tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src-tauri/src/error.rs apps/desktop/src-tauri/src/sidecar apps/desktop/src-tauri/src/lib.rs
git diff --check --cached
git commit -m "feat: validate sidecar startup handshake"
```

### Task 4: Build the Authenticated Loopback Sidecar Client

**Files:**
- Create: `apps/desktop/src-tauri/src/sidecar/client.rs`
- Modify: `apps/desktop/src-tauri/src/sidecar/mod.rs`
- Modify: `apps/desktop/src-tauri/src/contracts.rs`

**Interfaces:**
- Consumes: `ReadyLineV1`, `SessionToken`, frozen `/v1/*` paths, and stable
  sidecar error JSON.
- Produces: `SidecarClient::health`, `snapshot`, `events`, and `command`.

- [ ] **Step 1: Write failing authenticated-client tests**

Use `wiremock` to assert all of the following:

```rust
#[tokio::test]
async fn sends_bearer_auth_and_exact_event_query() {
    let server = MockServer::start().await;
    Mock::given(method("GET"))
        .and(path("/v1/events"))
        .and(query_param("after", "41"))
        .and(query_param("limit", "200"))
        .and(header("authorization", "Bearer test-token"))
        .respond_with(ResponseTemplate::new(200).set_body_json(event_page()))
        .mount(&server).await;

    let page = client_for(&server, "test-token").events(41, 200).await.unwrap();
    assert_eq!(page.last_event_sequence, 42);
}
```

Also test:

- constructor rejection for any host other than `127.0.0.1`;
- `limit=0` and `limit=501` rejection before a request;
- a two-second total request timeout;
- protocol mismatch rejection;
- `409 IDEMPOTENCY_CONFLICT` preservation as
  `DesktopErrorV1.code == "IDEMPOTENCY_CONFLICT"`; and
- command serialization with the exact roadmap envelope and no token field.

- [ ] **Step 2: Run client tests to verify they fail**

Run:

```bash
cd apps/desktop/src-tauri
cargo test sidecar::client::tests
```

Expected: Cargo fails because `sidecar::client` does not exist.

- [ ] **Step 3: Add the minimal authenticated client**

The client owns one reused Reqwest client and one loopback base URL:

```rust
pub struct SidecarClient {
    http: reqwest::Client,
    base_url: url::Url,
    token: SessionToken,
}

impl SidecarClient {
    pub fn new(port: u16, token: SessionToken) -> Result<Self, DesktopError> {
        let base_url = url::Url::parse(&format!("http://127.0.0.1:{port}/"))
            .map_err(DesktopError::InvalidLoopbackUrl)?;
        let http = reqwest::Client::builder()
            .timeout(Duration::from_secs(2))
            .redirect(reqwest::redirect::Policy::none())
            .build()
            .map_err(DesktopError::HttpClient)?;
        Ok(Self { http, base_url, token })
    }
}
```

Every request builder calls a single private method that adds
`bearer_auth(self.token.expose_for_header())`. Deserialize non-success bodies
as:

```rust
#[derive(Debug, Deserialize)]
pub struct FactoryErrorEnvelopeV1 {
    pub ok: bool,
    pub error: FactoryErrorV1,
}

#[derive(Debug, Deserialize)]
pub struct FactoryErrorV1 {
    pub code: String,
    pub message: String,
    pub details: serde_json::Value,
}
```

Expose exact methods:

```rust
pub async fn health(&self) -> Result<SidecarHealthV1, DesktopError>;
pub async fn snapshot(&self) -> Result<FactorySnapshotV1, DesktopError>;
pub async fn events(&self, after: u64, limit: u16) -> Result<EventPageV1, DesktopError>;
pub async fn command(&self, command: &FactoryCommandV1) -> Result<CommandResponseV1, DesktopError>;
```

`SidecarHealthV1` is
`{ protocol: 1, schema: 1 | 2 | 3, status: "ok", pid: u32, last_event_sequence: u64 }`.
Reject a health PID or schema that differs from readiness in the supervisor
task.

- [ ] **Step 4: Run authenticated-client tests**

Run:

```bash
cd apps/desktop/src-tauri
cargo fmt --check
cargo test sidecar::client::tests
```

Expected: all loopback, bearer, query, timeout, protocol, and API-error tests
pass.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src-tauri/src/sidecar apps/desktop/src-tauri/src/contracts.rs
git diff --check --cached
git commit -m "feat: proxy authenticated sidecar requests"
```

### Task 5: Supervise Health, Bounded Restarts, and Read-Only Recovery

**Files:**
- Create: `apps/desktop/src-tauri/src/sidecar/supervisor.rs`
- Modify: `apps/desktop/src-tauri/src/sidecar/mod.rs`
- Modify: `apps/desktop/src-tauri/src/contracts.rs`
- Modify: `apps/desktop/src-tauri/src/lib.rs`

**Interfaces:**
- Consumes: `LaunchSpec`, `SessionToken`, `parse_readiness`,
  `SidecarClient`, and `DesktopStatusV1`.
- Produces: `SidecarSupervisor::{start,status,snapshot,events,command,probe,shutdown}`,
  generation numbers, a one-snapshot memory cache, and
  `HostState::ReadOnlyRecovery`.

- [ ] **Step 1: Write failing supervisor policy tests**

Use a fake clock, fake spawner, fake process, and fake client. Test the exact
policy:

```rust
#[test]
fn allows_only_three_restarts_in_rolling_five_minutes() {
    let start = Instant::now();
    let mut budget = RestartBudget::new(Duration::from_secs(300), 3);
    assert!(budget.record_if_allowed(start));
    assert!(budget.record_if_allowed(start + Duration::from_secs(30)));
    assert!(budget.record_if_allowed(start + Duration::from_secs(60)));
    assert!(!budget.record_if_allowed(start + Duration::from_secs(90)));
    assert!(budget.record_if_allowed(start + Duration::from_secs(301)));
}

#[test]
fn three_consecutive_health_failures_request_restart() {
    let mut policy = HealthPolicy::new(3);
    assert_eq!(policy.record(false), HealthDecision::Wait);
    assert_eq!(policy.record(false), HealthDecision::Wait);
    assert_eq!(policy.record(false), HealthDecision::Restart);
}
```

Add async tests proving:

- startup times out after 10 seconds without a readiness line;
- a readiness PID mismatch kills that exact child and records no client;
- health runs every two seconds with a one-second request timeout;
- a successful health resets the consecutive-failure counter;
- each successful relaunch uses a new token and increments `generation`;
- restart delays are exactly zero, one, and two seconds;
- a fourth restart request in five minutes enters
  `READ_ONLY_RECOVERY`;
- `snapshot()` caches the last successful snapshot;
- recovery returns the cached snapshot with `read_only: true`;
- recovery without a cache returns `NO_CACHED_SNAPSHOT`;
- `events()` and `command()` in recovery return
  `READ_ONLY_RECOVERY`; and
- `shutdown()` terminates only the recorded child PID and reaches `STOPPED`.

- [ ] **Step 2: Run supervisor tests to verify they fail**

Run:

```bash
cd apps/desktop/src-tauri
cargo test sidecar::supervisor::tests
```

Expected: Cargo fails because `sidecar::supervisor` does not exist.

- [ ] **Step 3: Add process and policy boundaries**

Define the testable process boundary:

```rust
#[async_trait::async_trait]
pub trait SidecarProcess: Send {
    fn pid(&self) -> u32;
    async fn next_stdout_line(&mut self) -> Result<Option<String>, DesktopError>;
    async fn terminate(&mut self) -> Result<(), DesktopError>;
    async fn wait(&mut self) -> Result<ProcessExitV1, DesktopError>;
}

#[async_trait::async_trait]
pub trait SidecarSpawner: Send + Sync {
    async fn spawn(
        &self,
        spec: &LaunchSpec,
        token: &SessionToken,
    ) -> Result<Box<dyn SidecarProcess>, DesktopError>;
}
```

The production spawner uses `tokio::process::Command` with:

```rust
Command::new(&spec.program)
    .args(&spec.args)
    .env("VESPER_FACTORY_SESSION_TOKEN", token.expose_for_header())
    .env("VESPER_FACTORY_HOME", &spec.factory_home)
    .stdin(Stdio::null())
    .stdout(Stdio::piped())
    .stderr(Stdio::null())
    .kill_on_drop(true);
```

Create `factory_home` before spawn. Never use a shell, unresolved wildcard, or
command string. Buffer stdout by line only until the single readiness line is
accepted; do not forward stdout to React.

- [ ] **Step 4: Add the supervisor state machine**

Use these constants without configuration knobs:

```rust
const STARTUP_TIMEOUT: Duration = Duration::from_secs(10);
const HEALTH_INTERVAL: Duration = Duration::from_secs(2);
const HEALTH_TIMEOUT: Duration = Duration::from_secs(1);
const HEALTH_FAILURES_BEFORE_RESTART: u8 = 3;
const RESTART_WINDOW: Duration = Duration::from_secs(5 * 60);
const MAX_RESTARTS_IN_WINDOW: usize = 3;
const RESTART_DELAYS: [Duration; 3] = [
    Duration::from_secs(0),
    Duration::from_secs(1),
    Duration::from_secs(2),
];
```

Supervisor mutable state is held behind one Tokio mutex:

```rust
struct SupervisorState {
    host_state: HostState,
    generation: u64,
    process: Option<Box<dyn SidecarProcess>>,
    client: Option<SidecarClient>,
    readiness: Option<ReadyLineV1>,
    restart_budget: RestartBudget,
    consecutive_health_failures: u8,
    last_snapshot: Option<FactorySnapshotV1>,
    last_health_at: Option<String>,
    last_error: Option<String>,
}
```

Do not hold the mutex across an HTTP call or process wait. Clone the client
handle, perform I/O, reacquire the mutex, and discard the result if its
captured generation no longer matches. On a successful launch, make one
authenticated health request and require protocol `1`, a schema in `1..3`
equal to the readiness schema, status `"ok"`, and the readiness PID before
publishing `HEALTHY`.

`snapshot()` may return cached data only in recovery. It never writes the
cache to disk or treats it as authoritative. `command()` checks `HEALTHY`
immediately before the HTTP request and checks the generation again before
returning.

- [ ] **Step 5: Run supervisor tests**

Run:

```bash
cd apps/desktop/src-tauri
cargo fmt --check
cargo test sidecar::supervisor::tests
```

Expected: all startup, health, restart-budget, generation, cache, recovery,
mutation-denial, and shutdown tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps/desktop/src-tauri/src/sidecar apps/desktop/src-tauri/src/contracts.rs apps/desktop/src-tauri/src/lib.rs
git diff --check --cached
git commit -m "feat: supervise factory sidecar health"
```

### Task 6: Expose a Typed Tauri Proxy Without Secrets

**Files:**
- Create: `apps/desktop/src-tauri/src/ipc.rs`
- Modify: `apps/desktop/src-tauri/src/error.rs`
- Modify: `apps/desktop/src-tauri/src/lib.rs`
- Create: `apps/desktop/src/lib/desktop-api.ts`
- Create: `apps/desktop/src/lib/desktop-api.test.ts`

**Interfaces:**
- Consumes: `SidecarSupervisor`, `FactoryCommandV1`, `DesktopErrorV1`, and the
  exact Tauri command signatures under Desktop Contract V1.
- Produces: `desktopApi.status`, `snapshot`, `events`, `command`,
  `probeHealth`, `notifyAttention`, and `lifecycle`.

- [ ] **Step 1: Write failing frontend IPC tests**

Mock only `@tauri-apps/api/core` and assert exact command names/argument keys:

```ts
import { beforeEach, expect, it, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { desktopApi } from "./desktop-api";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

beforeEach(() => vi.mocked(invoke).mockReset());

it("requests ordered events through Rust", async () => {
  vi.mocked(invoke).mockResolvedValue({
    generation: 2,
    read_only: false,
    data: { protocol: 1, events: [], last_event_sequence: 42 },
  });
  await desktopApi.events(41, 200);
  expect(invoke).toHaveBeenCalledWith("factory_events", { after: 41, limit: 200 });
});

it("never accepts a token argument", () => {
  expect(Object.keys(desktopApi).sort()).toEqual([
    "command", "events", "lifecycle", "notifyAttention",
    "probeHealth", "snapshot", "status",
  ]);
});
```

Add a command test that supplies
`{ protocol: 1, idempotency_key, kind, payload, expected_version }` and asserts
the invocation payload is `{ command }`, not flattened.

- [ ] **Step 2: Write failing Rust allowlist/error tests**

Test that `validate_ui_command` accepts every exact payload in
`UiCommandPayloads`, rejects an unknown kind with `COMMAND_NOT_ALLOWED`,
rejects missing/unknown payload fields with `INVALID_COMMAND`, rejects a
non-v4 idempotency key, and preserves stable sidecar error code/message/details.
Test `DesktopErrorV1` serialization contains only:

```json
{
  "code": "READ_ONLY_RECOVERY",
  "message": "Factory mutations are disabled in read-only recovery.",
  "details": {},
  "recoverable": true
}
```

- [ ] **Step 3: Run focused tests to verify they fail**

Run:

```bash
cd apps/desktop
pnpm test --run src/lib/desktop-api.test.ts
cd src-tauri
cargo test ipc::tests error::tests
```

Expected: frontend import and Rust modules are unresolved.

- [ ] **Step 4: Add the sole frontend invoke wrapper**

`desktop-api.ts` imports `invoke` directly and exports one frozen object:

```ts
export const desktopApi = Object.freeze({
  status: () => invoke<DesktopStatusV1>("desktop_status"),
  snapshot: () =>
    invoke<ProxyEnvelopeV1<FactorySnapshotV1>>("factory_snapshot"),
  events: (after: number, limit: number) =>
    invoke<ProxyEnvelopeV1<EventPageV1>>("factory_events", { after, limit }),
  command: (command: FactoryCommandV1) =>
    invoke<ProxyEnvelopeV1<CommandResponseV1>>("factory_command", { command }),
  probeHealth: () => invoke<DesktopStatusV1>("desktop_probe_health"),
  notifyAttention: (request: AttentionNotificationV1) =>
    invoke<NotificationOutcomeV1>("desktop_notify_attention", { request }),
  lifecycle: (action: LifecycleActionV1) =>
    invoke<LifecycleOutcomeV1>("desktop_lifecycle", { action }),
});
```

No feature component may import `invoke`, `listen`, a shell plugin, or an HTTP
client. ESLint adds a `no-restricted-imports` rule that permits
`@tauri-apps/api/core` only in this file.

- [ ] **Step 5: Add typed Rust commands and registration**

Define:

```rust
pub struct DesktopState {
    pub supervisor: Arc<SidecarSupervisor>,
}
```

`validate_ui_command` uses a `match` on these six exact kinds and deserializes
each payload into a dedicated `#[serde(deny_unknown_fields)]` struct:

```text
task.transition
task.pause
task.stop
campaign.plan
campaign.admit
attention.acknowledge
```

Require protocol `1`, a UUID4 idempotency key, and `expected_version`. Do not
permit lifecycle commands through the generic endpoint. Register all seven
Desktop Contract V1 Tauri commands in one `tauri::generate_handler!` call.
Task 12 adds the notification and lifecycle implementations behind the
already-registered functions.

- [ ] **Step 6: Run typed proxy tests**

Run:

```bash
cd apps/desktop
pnpm lint
pnpm test --run src/lib/desktop-api.test.ts
cd src-tauri
cargo fmt --check
cargo test ipc::tests error::tests
```

Expected: all focused tests pass; lint confirms no feature can bypass
`desktop-api.ts`.

- [ ] **Step 7: Commit**

```bash
git add apps/desktop/src/lib apps/desktop/eslint.config.js apps/desktop/src-tauri/src/ipc.rs apps/desktop/src-tauri/src/error.rs apps/desktop/src-tauri/src/lib.rs
git diff --check --cached
git commit -m "feat: expose typed desktop IPC"
```

### Task 7: Synchronize Snapshots and Ordered Events

**Files:**
- Create: `apps/desktop/src/state/factory-sync.ts`
- Create: `apps/desktop/src/state/factory-sync.test.ts`
- Create: `apps/desktop/src/state/use-factory-sync.ts`
- Create: `apps/desktop/src/state/use-factory-sync.test.tsx`

**Interfaces:**
- Consumes: `desktopApi.snapshot()`, `desktopApi.events(after, 200)`,
  `ProxyEnvelopeV1`, protocol `1`, monotonic event sequence, and generation.
- Produces: `FactorySyncState`, `reduceSyncState`, and `useFactorySync()`.

- [ ] **Step 1: Write failing cursor and polling tests**

Test the pure reducer:

```ts
it("accepts only a consecutive batch in the same generation", () => {
  const state = readyState({ cursor: 41, generation: 3 });
  const next = reduceSyncState(state, {
    type: "EVENT_PAGE",
    envelope: eventEnvelope(3, [event(42), event(43)]),
  });
  expect(next.cursor).toBe(43);
  expect(next.resyncReason).toBeNull();
});

it.each([
  ["SEQUENCE_GAP", eventEnvelope(3, [event(43)])],
  ["GENERATION_CHANGED", eventEnvelope(4, [event(42)])],
  ["PROTOCOL_MISMATCH", {
    generation: 3,
    read_only: false,
    data: { protocol: 2, events: [], last_event_sequence: 41 },
  }],
])("requests %s resync", (reason, envelope) => {
  const next = reduceSyncState(
    readyState({ cursor: 41, generation: 3 }),
    { type: "EVENT_PAGE", envelope: envelope as never },
  );
  expect(next.resyncReason).toBe(reason);
});
```

With fake timers and a fake API, test that the hook:

- loads one snapshot before polling events;
- polls `events(cursor, 200)` every 1,000 ms;
- never overlaps event requests;
- replaces the snapshot after a non-empty valid batch instead of reducing
  domain event payloads in React;
- loops through full 200-event pages until a short page, capped at three pages
  per tick;
- retains only the newest 500 activity events;
- fetches a new snapshot on gap, protocol mismatch, or generation change;
- stops polling while unmounted; and
- preserves the visible snapshot, marks it read-only, and disables refresh
  mutations when the host enters recovery.

- [ ] **Step 2: Run sync tests to verify they fail**

Run:

```bash
cd apps/desktop
pnpm test --run src/state/factory-sync.test.ts src/state/use-factory-sync.test.tsx
```

Expected: Vitest fails because both state modules are unresolved.

- [ ] **Step 3: Add the pure synchronization state machine**

Use this exact state:

```ts
export interface FactorySyncState {
  phase: "BOOTING" | "READY" | "RESYNCING" | "RECOVERY" | "ERROR";
  snapshot: FactorySnapshotV1 | null;
  events: FactoryEventV1[];
  cursor: number;
  generation: number | null;
  readOnly: boolean;
  resyncReason:
    | "SEQUENCE_GAP" | "GENERATION_CHANGED" | "PROTOCOL_MISMATCH"
    | "SERVER_BEHIND" | null;
  error: DesktopErrorV1 | null;
}
```

For each `EVENT_PAGE`, require:

```ts
page.protocol === 1
envelope.generation === state.generation
page.events.every((event, index) =>
  event.sequence === state.cursor + index + 1
)
page.last_event_sequence >= page.events.at(-1)?.sequence ?? state.cursor
```

If any condition fails, set `phase: "RESYNCING"` and a reason; do not append
events. A replacement snapshot sets the cursor to its
`last_event_sequence`. Event payloads are activity data only; they never
transition cards locally.

- [ ] **Step 4: Add the non-overlapping polling hook**

Expose:

```ts
export interface FactorySyncController extends FactorySyncState {
  refresh(): Promise<void>;
  send<K extends UiCommandKind>(
    kind: K,
    payload: UiCommandPayloads[K],
    expectedVersion: number,
  ): Promise<CommandResponseV1>;
}

export function useFactorySync(
  api: typeof desktopApi = desktopApi,
): FactorySyncController;
```

`send` creates `crypto.randomUUID()` immediately before invoking the command,
does not modify `snapshot`, throws if `readOnly`, and calls `refresh()` after
success. An `inFlight` ref prevents overlapping polls. Use one 1,000 ms
interval and clear it on unmount.

- [ ] **Step 5: Run synchronization tests**

Run:

```bash
cd apps/desktop
pnpm lint
pnpm test --run src/state/factory-sync.test.ts src/state/use-factory-sync.test.tsx
```

Expected: all ordering, bounded catch-up, resync, recovery, command, and cleanup
tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps/desktop/src/state
git diff --check --cached
git commit -m "feat: synchronize factory snapshots and events"
```

### Task 8: Render the Mission Control Board, Inspector, and Activity Shell

**Files:**
- Create: `apps/desktop/src/features/runtime/runtime-surface.tsx`
- Create: `apps/desktop/src/features/mission-control/MissionControl.tsx`
- Create: `apps/desktop/src/features/mission-control/MissionControl.test.tsx`
- Create: `apps/desktop/src/features/mission-control/StatusHeader.tsx`
- Create: `apps/desktop/src/features/mission-control/Board.tsx`
- Create: `apps/desktop/src/features/mission-control/TaskCard.tsx`
- Create: `apps/desktop/src/features/mission-control/TaskInspector.tsx`
- Create: `apps/desktop/src/features/mission-control/ActivityDock.tsx`
- Modify: `apps/desktop/src/App.tsx`
- Modify: `apps/desktop/src/styles.css`

**Interfaces:**
- Consumes: `FactorySyncController`, `FactorySnapshotV1`, ordered
  `FactoryEventV1[]`, and no workflow mutation logic.
- Produces: `MissionControlProps`, `TaskInspectorProps`, `ActivityDockProps`,
  `RuntimeSurfaceProps`, and `NoRuntimeSurface`.

- [ ] **Step 1: Write failing Mission Control component tests**

Render `makeFactorySnapshot()` extended with one task in each visible state and
assert:

- heading and one **New objective** button;
- Backlog, Ready, Running, and Evaluation columns;
- factory mode, market status, active worker count, and next gate;
- card state, runtime, progress, elapsed time, and gate label;
- clicking a card selects it and renders contract, acceptance, files, bounds,
  pause, and stop controls;
- activity shows only events whose `aggregate_id` is the selected task;
- the runtime area says `No active runtime session.` when the no-op surface is
  used; and
- no completed, blocked, interrupted, or canceled task is mislabeled into a
  visible board column.

Use an explicit prop factory:

```tsx
render(
  <MissionControl
    sync={makeSyncController(snapshot)}
    runtimeSurface={NoRuntimeSurface}
    onOpenObjective={vi.fn()}
    onOpenInbox={vi.fn()}
    onOpenSettings={vi.fn()}
    onLifecycle={vi.fn()}
  />,
);
```

- [ ] **Step 2: Run Mission Control tests to verify they fail**

Run:

```bash
cd apps/desktop
pnpm test --run src/features/mission-control/MissionControl.test.tsx
```

Expected: Vitest fails because `MissionControl` is unresolved.

- [ ] **Step 3: Add exact component boundaries**

```ts
export interface MissionControlProps {
  sync: FactorySyncController;
  runtimeSurface: RuntimeSurface;
  onOpenObjective(): void;
  onOpenInbox(): void;
  onOpenSettings(): void;
  onLifecycle(action: LifecycleActionV1): Promise<void>;
}

export interface TaskInspectorProps {
  task: TaskV1 | null;
  readOnly: boolean;
  pendingAction: "PAUSE" | "STOP" | null;
  onPause(task: TaskV1): Promise<void>;
  onStop(task: TaskV1): Promise<void>;
}

export interface ActivityDockProps {
  task: TaskV1 | null;
  events: readonly FactoryEventV1[];
  session: SessionV1 | null;
  readOnly: boolean;
  runtimeSurface: RuntimeSurface;
}

export interface RuntimeSurfaceProps {
  selectedTaskId: TaskId | null;
  session: SessionV1 | null;
  readOnly: boolean;
}

export type RuntimeSurface = ComponentType<RuntimeSurfaceProps>;
```

`NoRuntimeSurface` renders `No active runtime session.` and no controls. This is
the entire Plan 02 terminal boundary; do not add xterm, PTY events, CLI buttons,
or process controls.

- [ ] **Step 4: Render authoritative view models**

Board columns map exactly:

```ts
export const BOARD_COLUMNS = [
  { id: "BACKLOG", label: "Backlog" },
  { id: "READY", label: "Ready" },
  { id: "RUNNING", label: "Running" },
  { id: "EVALUATING", label: "Evaluation" },
] as const;
```

The active-worker count is
`snapshot.workers.filter(worker => worker.state === "ACTIVE").length`.
Elapsed time is formatted from the provided `elapsed_seconds`; React does not
start an authoritative timer. The selected session is the snapshot session
whose `task_id` matches the selected task, or null. Inspector pause/stop call
`sync.send("task.pause" | "task.stop", ...)` and stay disabled while pending
or read-only. Controller errors render verbatim safe `message` text in an
`aria-live="assertive"` region.

The top header includes **Pause dispatch** or **Resume dispatch** according to
`snapshot.factory.mode`, plus the non-delegable **Stop Factory** action. It
calls `onLifecycle`; it does not send domain commands directly.

- [ ] **Step 5: Run Mission Control tests**

Run:

```bash
cd apps/desktop
pnpm lint
pnpm test --run src/features/mission-control/MissionControl.test.tsx
```

Expected: all board, selection, inspector, activity, runtime-boundary, status,
and action-state tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps/desktop/src/App.tsx apps/desktop/src/styles.css apps/desktop/src/features/mission-control apps/desktop/src/features/runtime
git diff --check --cached
git commit -m "feat: render mission control shell"
```

### Task 9: Add Accessible Authoritative Board Transitions

**Files:**
- Create: `apps/desktop/src/features/mission-control/BoardDnd.tsx`
- Create: `apps/desktop/src/features/mission-control/BoardDnd.test.tsx`
- Modify: `apps/desktop/src/features/mission-control/Board.tsx`
- Modify: `apps/desktop/src/features/mission-control/TaskCard.tsx`
- Modify: `apps/desktop/src/features/mission-control/MissionControl.tsx`
- Modify: `apps/desktop/src/styles.css`

**Interfaces:**
- Consumes: `TaskV1`, the four `BOARD_COLUMNS`, and
  `sync.send("task.transition", { task_id, target_state }, task.version)`.
- Produces:

```ts
export interface MissionBoardProps {
  tasks: readonly TaskV1[];
  pendingTaskId: TaskId | null;
  onSelect(taskId: TaskId): void;
  onRequestTransition(request: {
    taskId: TaskId;
    targetState: "BACKLOG" | "READY" | "RUNNING" | "EVALUATING";
    expectedVersion: number;
  }): Promise<void>;
}
```

- [ ] **Step 1: Write failing pointer, keyboard, and rejection tests**

Test that a Ready-to-Running drop submits exactly one request with version `4`,
leaves the card in Ready while the promise is pending, and moves only after an
authoritative refreshed snapshot. Test a rejected promise leaves the card in
Ready and announces `Task dependencies are not complete.` Test that the drag
handle is a focusable button; Space/Enter pick up, arrow keys choose a column,
Space/Enter submit, and Escape cancels without a request.

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```bash
cd apps/desktop
pnpm test --run src/features/mission-control/BoardDnd.test.tsx
```

Expected: FAIL because `BoardDnd` is unresolved.

- [ ] **Step 3: Add dnd-kit without optimistic workflow state**

Use `PointerSensor` with `{ activationConstraint: { distance: 8 } }` and
`KeyboardSensor` with `sortableKeyboardCoordinates`. Each column has droppable
ID `column:<TaskState>` and each card has sortable ID equal to `task_id`.
Resolve a card drop target through the target card's current state; resolve a
column drop through its ID. Ignore same-column drops.

Configure `DndContext` with exact screen-reader instructions:

```ts
const screenReaderInstructions = {
  draggable:
    "Press Space or Enter to pick up a task. Use arrow keys to choose a column. Press Space or Enter to request the move, or Escape to cancel.",
};
```

Use an `aria-live="assertive"` region for accepted/rejected/canceled
announcements. Keep `tasks` prop immutable; `pendingTaskId` only adds
`aria-busy="true"` and disables its drag handle. On success call
`sync.refresh()`; on failure render the safe controller message.

- [ ] **Step 4: Run red/green verification**

Run:

```bash
cd apps/desktop
pnpm lint
pnpm test --run src/features/mission-control/BoardDnd.test.tsx src/features/mission-control/MissionControl.test.tsx
```

Expected: PASS for pointer mapping, keyboard parity, cancellation, pending
state, controller rejection, and Mission Control regression tests.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/features/mission-control apps/desktop/src/styles.css
git diff --check --cached
git commit -m "feat: add accessible board transitions"
```

### Task 10: Add Objective Admission and the Operator Inbox

**Files:**
- Create: `apps/desktop/src/features/objective/ObjectiveWizard.tsx`
- Create: `apps/desktop/src/features/objective/ObjectiveWizard.test.tsx`
- Create: `apps/desktop/src/features/objective/validation.ts`
- Create: `apps/desktop/src/features/inbox/OperatorInbox.tsx`
- Create: `apps/desktop/src/features/inbox/OperatorInbox.test.tsx`
- Modify: `apps/desktop/src/App.tsx`
- Modify: `apps/desktop/src/features/mission-control/MissionControl.tsx`
- Modify: `apps/desktop/src/styles.css`

**Interfaces:**
- Consumes: exact `ObjectiveDraftV1`, `CampaignPlanV1`,
  `AttentionItemV1`, `FactorySyncController.send`, and lifecycle callbacks.
- Produces:

```ts
export interface ObjectiveWizardProps {
  open: boolean;
  readOnly: boolean;
  onPlan(draft: ObjectiveDraftV1): Promise<CampaignPlanV1>;
  onAdmit(plan: CampaignPlanV1): Promise<void>;
  onClose(): void;
}

export interface OperatorInboxProps {
  items: readonly AttentionItemV1[];
  readOnly: boolean;
  onAcknowledge(item: AttentionItemV1): Promise<void>;
  onOpenTask(taskId: TaskId): void;
  onOpenCampaign(campaignId: CampaignId): void;
  onLifecycle(action: "PAUSE" | "STOP"): Promise<void>;
}
```

- [ ] **Step 1: Write failing admission and inbox tests**

Wizard tests must prove:

- five steps render in order: Objective, Data & interval, Authority, Budgets,
  Review;
- Massive is fixed to `MASSIVE_LOCAL_READ_ONLY`;
- blank objective, invalid date order, empty acceptance criteria, empty stop
  conditions, non-positive budgets, GPU concurrency without GPU eligibility,
  PAPER without `PAPER_ENVELOPE`, and LIVE_APPROVAL_REQUIRED without
  `LIVE_APPROVAL` block proposal;
- Plan submits `campaign.plan` with version `0`;
- the proposal renders exact contract hash, stages, dependencies, and
  reservations; and
- Admit submits `campaign.admit` with the proposal version/hash and nothing
  dispatches from the wizard.

Inbox tests must prove only supplied attention records render, repeated items
show `occurrence_count`, acknowledgement uses the item's version, opening
task/campaign is local navigation, lifecycle actions call the native callback,
acknowledgement does not change task state, and every mutation is disabled in
read-only recovery.

- [ ] **Step 2: Run the focused tests to verify they fail**

Run:

```bash
cd apps/desktop
pnpm test --run src/features/objective/ObjectiveWizard.test.tsx src/features/inbox/OperatorInbox.test.tsx
```

Expected: FAIL because both components are unresolved.

- [ ] **Step 3: Add deterministic validation and command mapping**

`validateObjectiveDraft(draft)` returns field-keyed strings and performs only
the checks listed in Step 1; the sidecar remains authoritative for campaign
policy. Parse `CommandResponseV1.result` into `CampaignPlanV1` by requiring all
named fields and rejecting a malformed result with
`INVALID_CAMPAIGN_PLAN_RESPONSE`.

Map commands exactly:

```ts
sync.send("campaign.plan", { draft }, 0);
sync.send(
  "campaign.admit",
  { draft_id: plan.draft_id, contract_hash: plan.contract_hash },
  plan.version,
);
sync.send(
  "attention.acknowledge",
  { attention_id: item.attention_id },
  item.version,
);
```

Use a modal dialog with labelled controls, a visible step list, Previous/Next,
**Propose contract**, and **Admit campaign**. Closing discards only the local
draft. Render inbox severity, factual reason, linked identities, receipt IDs,
allowed actions, whether progress can continue, and count. Do not turn routine
events into inbox rows.

- [ ] **Step 4: Run red/green verification**

Run:

```bash
cd apps/desktop
pnpm lint
pnpm test --run src/features/objective/ObjectiveWizard.test.tsx src/features/inbox/OperatorInbox.test.tsx src/App.test.tsx
```

Expected: PASS for validation, proposal/admission gating, attention actions,
read-only denial, and application wiring.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/App.tsx apps/desktop/src/styles.css apps/desktop/src/features/objective apps/desktop/src/features/inbox apps/desktop/src/features/mission-control/MissionControl.tsx
git diff --check --cached
git commit -m "feat: add objective admission and inbox"
```

### Task 11: Add Dossier, Dependency Graph, Settings Health, and Recovery Views

**Files:**
- Create: `apps/desktop/src/features/dossier/TaskDossier.tsx`
- Create: `apps/desktop/src/features/dossier/TaskDossier.test.tsx`
- Create: `apps/desktop/src/features/dependencies/DependencyGraph.tsx`
- Create: `apps/desktop/src/features/dependencies/layout.ts`
- Create: `apps/desktop/src/features/dependencies/DependencyGraph.test.tsx`
- Create: `apps/desktop/src/features/settings/SettingsHealth.tsx`
- Create: `apps/desktop/src/features/settings/SettingsHealth.test.tsx`
- Modify: `apps/desktop/src/features/mission-control/TaskInspector.tsx`
- Modify: `apps/desktop/src/features/mission-control/MissionControl.tsx`
- Modify: `apps/desktop/src/App.tsx`
- Modify: `apps/desktop/src/styles.css`

**Interfaces:**
- Consumes: `TaskDossierV1`, task dependency IDs, reservations,
  `DesktopStatusV1`, `desktopApi.probeHealth`, and `sync.readOnly`.
- Produces:

```ts
export interface TaskDossierProps {
  dossier: TaskDossierV1;
  onOpenReceipt(receiptId: ReceiptId): void;
}

export interface DependencyGraphProps {
  tasks: readonly TaskV1[];
  reservations: readonly ResourceReservationV1[];
  selectedTaskId: TaskId | null;
  onSelectTask(taskId: TaskId): void;
}

export interface SettingsHealthProps {
  status: DesktopStatusV1;
  checking: boolean;
  onProbe(): Promise<void>;
}
```

- [ ] **Step 1: Write failing read-only view tests**

Test dossier sections always render in the fixed Desktop Contract V1 order,
available entries expose exact receipt/hash/worker/time, and absent content
renders the supplied `missing_gate` without generated narrative. Test the
graph's board/graph switch, deterministic nodes/edges, dependency receipt
labels, worker/state/resource badges, keyboard-selectable node buttons, and a
semantic dependency-list alternative. A cycle must display
`Invalid dependency graph received from controller.` without repairing edges.

Test settings displays host state, factory home, exact sidecar path/PID,
protocol/schema, restart attempts, last health/error, and runtime health
records; its health button calls `desktop_probe_health`. Test recovery keeps
the last snapshot visible, labels it read-only, disables every mutation, and
shows a no-snapshot recovery panel when `NO_CACHED_SNAPSHOT` is returned.

- [ ] **Step 2: Run the focused tests to verify they fail**

Run:

```bash
cd apps/desktop
pnpm test --run src/features/dossier/TaskDossier.test.tsx src/features/dependencies/DependencyGraph.test.tsx src/features/settings/SettingsHealth.test.tsx
```

Expected: FAIL because the three view modules are unresolved.

- [ ] **Step 3: Add deterministic read-only projections**

For the graph, run Kahn topological sorting with task IDs as the stable
tie-breaker. Place level `L`, row `R` at
`x = 40 + L * 280`, `y = 40 + R * 128`; draw SVG edges from predecessor to
successor and render the same relations as an ordered textual list. If the
sorted count differs from task count, set `invalid: true`, preserve all
received nodes/edges, and show the error.

The dossier is a pure rendering of `task.dossier`; clicking a receipt only
filters/highlights activity. `ARTIFACTS_DIFF` may display supplied artifact
labels and hashes, but no Git read/edit implementation is added. `LESSONS`
displays supplied entries without learning calculations.

Settings is read-only in Plan 02. Runtime adapter rows consume
`RuntimeAdapterHealthV1`; the no-op boundary supplies an empty array. The
health button exercises the supervisor's authenticated `/v1/health` path, not
a separate probe.

- [ ] **Step 4: Run red/green verification**

Run:

```bash
cd apps/desktop
pnpm lint
pnpm test --run src/features/dossier/TaskDossier.test.tsx src/features/dependencies/DependencyGraph.test.tsx src/features/settings/SettingsHealth.test.tsx src/features/mission-control/MissionControl.test.tsx src/App.test.tsx
```

Expected: PASS for dossier truthfulness, graph/accessibility/cycle handling,
settings probe, and recovery mutation denial.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/App.tsx apps/desktop/src/styles.css apps/desktop/src/features/dossier apps/desktop/src/features/dependencies apps/desktop/src/features/settings apps/desktop/src/features/mission-control
git diff --check --cached
git commit -m "feat: add desktop detail and recovery views"
```

### Task 12: Add Notifications, Native Lifecycle, Tray Behavior, and the M2 Gate

**Files:**
- Create: `apps/desktop/src/hooks/use-attention-notifications.ts`
- Create: `apps/desktop/src/hooks/use-attention-notifications.test.tsx`
- Create: `apps/desktop/src-tauri/src/runtime_boundary.rs`
- Create: `apps/desktop/src-tauri/src/notifications.rs`
- Create: `apps/desktop/src-tauri/src/lifecycle.rs`
- Create: `apps/desktop/src-tauri/src/tray.rs`
- Create: `apps/desktop/src-tauri/tests/sidecar_process.rs`
- Modify: `apps/desktop/src-tauri/src/contracts.rs`
- Modify: `apps/desktop/src-tauri/src/ipc.rs`
- Modify: `apps/desktop/src-tauri/src/lib.rs`
- Modify: `apps/desktop/src/App.tsx`

**Interfaces:**
- Consumes: Plan 01 fake sidecar, `factory.pause`, `factory.resume`,
  `factory.stop`, `snapshot.factory.version`, `SidecarSupervisor`, Tauri tray
  and notification APIs, and Gate D4.
- Produces:

```rust
#[async_trait::async_trait]
pub trait RuntimeStopParticipant: Send + Sync {
    async fn request_stop_all(&self, deadline: Duration) -> RuntimeStopReportV1;
    async fn terminate_remaining(&self) -> RuntimeStopReportV1;
}

pub struct RuntimeStopReportV1 {
    pub requested: u32,
    pub stopped: u32,
    pub remaining: u32,
}
```

```ts
export interface AttentionNotificationV1 {
  attention_id: AttentionId;
  severity: "HIGH" | "CRITICAL";
  kind: AttentionItemV1["kind"];
  occurrence_count: number;
}

export type NotificationOutcomeV1 =
  | "SENT" | "DEDUPLICATED" | "SKIPPED_ROUTINE" | "PERMISSION_DENIED";

export interface LifecycleOutcomeV1 {
  action: LifecycleActionV1;
  factory_command_recorded: boolean;
  runtime_stop: { requested: number; stopped: number; remaining: number };
}
```

- [ ] **Step 1: Write failing notification, lifecycle, tray, and process tests**

Rust tests must prove:

- INFO/WARNING never notify; HIGH/CRITICAL notify once per
  `(attention_id, occurrence_count)` and notify again only for a higher count
  or severity escalation;
- notification body is exactly
  `"<KIND> requires attention in Vesper."` and contains no reason, receipt,
  path, token, or payload;
- `NoopRuntimeStopParticipant` returns all zeroes and is the default Plan 02
  implementation;
- PAUSE/RESUME/STOP use fresh UUID4 keys, exact command kinds, and current
  factory version;
- STOP sends `factory.stop`, requests graceful runtime stop with a 15-second
  deadline, then terminates only reported remaining processes;
- QUIT performs STOP, shuts down the recorded sidecar, marks explicit quit,
  and exits; a degraded quit reports `factory_command_recorded: false` rather
  than claiming a receipt;
- close-request hides the main window and prevents exit unless explicit quit;
- tray priority is Degraded, Attention, Paused, Running;
- tray actions are Open Mission Control, Pause/Resume Dispatch, Stop Factory,
  and Quit Factory; and
- the Plan 01 fake proves exact readiness, bearer auth, snapshot/event polling,
  three bounded restarts, recovery mutation denial, and token absence from
  captured stdout/status/errors.

Frontend tests prove only new HIGH/CRITICAL attention items invoke
`desktop_notify_attention`.

- [ ] **Step 2: Run focused tests to verify they fail**

Run:

```bash
cd apps/desktop
pnpm test --run src/hooks/use-attention-notifications.test.tsx
cd src-tauri
cargo test notifications::tests lifecycle::tests tray::tests
cargo test --test sidecar_process
```

Expected: FAIL because notification, runtime, lifecycle, tray, and integration
modules are unresolved.

- [ ] **Step 3: Add notification and runtime-stop boundaries**

`AttentionNotifier<S: NotificationSink>` keeps an in-memory
`HashMap<AttentionId, (AttentionSeverity, u32)>`; Rust enforces policy even if
React calls it incorrectly. The Tauri sink uses
`tauri_plugin_notification::NotificationExt`. Initialize the plugin in
`lib.rs`; React receives no notification capability.

Add `RuntimeStopParticipant` exactly as published in Gate D4 and
`NoopRuntimeStopParticipant`. Do not create agent, PTY, terminal, or process
adapter modules.

- [ ] **Step 4: Add lifecycle and tray sequencing**

`desktop_lifecycle` is the only native lifecycle entry:

```rust
match action {
    LifecycleActionV1::Pause => issue_factory("factory.pause").await,
    LifecycleActionV1::Resume => issue_factory("factory.resume").await,
    LifecycleActionV1::Stop => controller.stop(Duration::from_secs(15)).await,
    LifecycleActionV1::Quit => controller.quit(Duration::from_secs(15)).await,
}
```

Pause stops new dispatch only; it does not terminate active work. Stop has
priority and disables concurrent lifecycle actions until complete. Resume is
accepted only after an authoritative PAUSED snapshot and explicit local UI
action. Quit never implies background continuation.

Build one Rust tray with stable IDs `open`, `pause_resume`, `stop`, `quit`.
Double-click and `open` show/focus `main`. Window close calls
`api.prevent_close()` then hides. `RunEvent::ExitRequested` calls
`api.prevent_exit()` unless the lifecycle controller's atomic
`explicit_quit` flag is true.

- [ ] **Step 5: Add the process integration and run all red/green checks**

`sidecar_process.rs` locates the repository root from
`CARGO_MANIFEST_DIR/../../..`, launches
`.venv/Scripts/python.exe` with
`tests/factory/sidecar_fixture.py`, and injects temporary
`LOCALAPPDATA`. It must not edit or import Plan 01 code.

Run:

```bash
cd apps/desktop
pnpm lint
pnpm test --run
pnpm build
cd src-tauri
cargo fmt --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test
```

Expected: all frontend and Rust checks pass, including `sidecar_process`.

- [ ] **Step 6: Run the Windows M2 smoke gate**

From Git Bash in `apps/desktop`:

```bash
pnpm tauri build --debug --no-bundle
VESPER_FACTORY_DEV_SIDECAR="$(cygpath -w "$OLDPWD/.venv/Scripts/python.exe")" \
VESPER_FACTORY_DEV_SIDECAR_ARGS_JSON="[\"$(cygpath -w "$OLDPWD/tests/factory/sidecar_fixture.py" | sed 's/\\/\\\\/g')\"]" \
./src-tauri/target/debug/vesper-desktop.exe
```

Expected: the native window starts without a browser, renders Mission Control,
continues in the tray after close, reopens from the tray, pauses/resumes,
surfaces fake high-priority attention once, stops, and quits explicitly.
Inject the fixture's documented health-failure mode and verify three restart
attempts followed by read-only recovery. Record this manual result in the
commit message body; do not add a separate report file.

- [ ] **Step 7: Inspect scope and commit**

Run:

```bash
git diff --check
git diff --stat
git status --short
```

Expected: Plan 02 implementation changes are confined to `apps/desktop/`; the
protected paths and `apps/desktop/src-tauri/src/agents/` are absent.

```bash
git add apps/desktop
git diff --check --cached
git commit -m "feat: complete native desktop lifecycle"
```

---

## Final Plan 02 Acceptance Checklist

- [ ] Gate D0 canonical checkout and CodeGraph preflight passed.
- [ ] Plan 01/M1 and its process fixture passed Gate D1.
- [ ] Desktop Contract V1 matched Plan 01 additively without Python edits.
- [ ] React never received a session or worker token.
- [ ] Rust/React submitted commands but owned no workflow state machine.
- [ ] Sidecar readiness, auth, health, three-restart budget, and recovery passed.
- [ ] Snapshot/event ordering and all resynchronization triggers passed.
- [ ] Mission Control, accessible DnD, wizard, inbox, dossier, graph, settings,
      activity, and recovery component tests passed.
- [ ] Tray/background, pause/resume/stop/quit, and notifications passed.
- [ ] Plan 03 runtime interfaces exist with no Codex/Hermes or PTY implementation.
- [ ] Research metrics, analytics, review, and learning internals are absent.
- [ ] `pnpm lint`, `pnpm test --run`, `pnpm build`, `cargo fmt --check`,
      strict Clippy, `cargo test`, and the Windows M2 smoke gate passed.
- [ ] Every task was committed independently and the final write set is only
      `apps/desktop/`.
