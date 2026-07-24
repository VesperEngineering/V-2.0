# Vesper Quant Factory Delivery Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the approved local-first Vesper quant factory as six independently reviewable increments without weakening the existing engine, data, model, or execution boundaries.

**Architecture:** A Tauri 2 desktop host supervises one bundled Python sidecar. React renders snapshots and ordered events; Rust owns native process, PTY, tray, notification, and read-only Git concerns; `vesper.factory` owns all workflow truth, authority, evaluation, learning, and durable state in SQLite WAL. Codex and Hermes are replaceable execution adapters, never orchestration authorities.

**Tech Stack:** Python 3.11, stdlib SQLite, `mcp[cli]==1.28.1`, pytest, Tauri 2, Rust stable, React 19, TypeScript, Vite, Vitest, React Testing Library, `@xterm/xterm`, `portable-pty`, `@dnd-kit/core`.

## Global Constraints

- Before any code edit, follow `AGENTS.md`: load matching skills, query the repository `.codegraph` index for every symbol/file to be changed, and read `SKILLS/CODE.md` plus `SKILLS/EXAMPLES.md`.
- The current local clone does not contain `.codegraph`. Implementation must run from the canonical Windows checkout where the index exists, or stop and refresh/create the required index before editing code.
- Do not edit `config/`, `vesper/risk.py`, `vesper/execution.py`, scheduler code, `vesper/data/massive/`, `vesper/data/model_research/`, or active model artifacts without a new exact-scope approval.
- Massive data is opened read-only. Alpaca is paper-only and remains disabled until a human-reviewed P2 envelope is active.
- Keep the Tkinter dashboard and current engine operational until the final parity gate.
- Use test-first changes, surgical diffs, deterministic assertions, and one focused commit per task.
- Use generated UUID4 identifiers with stable prefixes (`cmp_`, `cnd_`, `tsk_`, `atm_`, `rcp_`, `evt_`, `wrk_`, `ses_`, `evd_`, `lsn_`, `att_`, `rsv_`). Store UTC timestamps as RFC 3339 strings ending in `Z`.
- Store flexible payloads as canonical JSON: UTF-8, sorted keys, compact separators. Hash canonical bytes with SHA-256.
- Never store raw session tokens, worker tokens, broker credentials, provider credentials, or unbounded terminal output in SQLite.

---

## 1. Frozen Cross-Subsystem Contracts

These contracts are version `1`. Subsequent plans may extend them additively,
but may not silently rename fields, reinterpret states, or bypass their guards.

### 1.1 State values

```python
CampaignStatus = Literal["DRAFT", "ADMITTED", "PAUSED", "STOPPED", "CLOSED"]
CandidateStage = Literal[
    "ADMISSION", "RESEARCH", "EVALUATION", "SHADOW",
    "PAPER", "LIVE_APPROVAL_REQUIRED", "ARCHIVED",
]
TaskState = Literal[
    "BACKLOG", "READY", "RUNNING", "EVALUATING", "COMPLETED",
    "BLOCKED", "INTERRUPTED", "CANCELED",
]
AttemptOutcome = Literal[
    "VERIFIED", "REJECTED", "FAILED", "BLOCKED",
    "INCONCLUSIVE", "INTERRUPTED", "AMBIGUOUS",
]
AttentionSeverity = Literal["INFO", "WARNING", "HIGH", "CRITICAL"]
```

The candidate lifecycle, task lifecycle, and
`ADMISSION → CONTRACT → IMPLEMENT → TRAIN → BACKTEST → REVIEW → NEXT`
workflow template remain distinct.

### 1.2 Sidecar startup and authentication

Tauri creates a 32-byte random session token and starts the exact bundled or
development sidecar path with:

```text
VESPER_FACTORY_SESSION_TOKEN=<base64url token>
VESPER_FACTORY_HOME=<absolute %LOCALAPPDATA%\Vesper\Factory path>
```

The sidecar binds only to `127.0.0.1` on an OS-assigned port and writes exactly
one machine-readable readiness line to stdout:

```text
VESPER_FACTORY_READY {"protocol":1,"port":54321,"pid":1234,"schema":1}
```

`protocol` versions the sidecar API. `schema` is the current SQLite
`PRAGMA user_version`: Plan 01 reports `1`, Plan 04 reports `2`, and Plan 05
reports the first-release target `3`. The desktop accepts only the planned
range `1..3`; it never treats a database schema change as an API protocol
change. The token and any secret values are never printed. `/v1/*` requests require
`Authorization: Bearer <session token>`. `/mcp` requires a short-lived worker
token. React never receives either token; all frontend calls use typed Tauri
commands.

### 1.3 Sidecar HTTP API

```text
GET  /v1/health
GET  /v1/snapshot
GET  /v1/events?after=<sequence>&limit=<1..500>
POST /v1/commands
POST /v1/runtime-grants
POST /v1/runtime-grants/<session_id>/revoke
```

`POST /v1/commands` accepts:

```json
{
  "protocol": 1,
  "idempotency_key": "uuid",
  "kind": "task.transition",
  "payload": {},
  "expected_version": 4
}
```

It returns:

```json
{
  "ok": true,
  "command_id": "cmd_...",
  "result": {},
  "last_event_sequence": 42
}
```

Validation and policy failures use an HTTP status matching the failure and a
stable body:

```json
{
  "ok": false,
  "error": {
    "code": "TRANSITION_DENIED",
    "message": "Task dependencies are not complete.",
    "details": {}
  }
}
```

Mutating commands require an idempotency key. Repeating a key with identical
canonical input returns the original result. Repeating it with different input
returns `409 IDEMPOTENCY_CONFLICT`.

### 1.4 Snapshot and event ordering

`GET /v1/snapshot` returns `FactorySnapshotV1`:

```json
{
  "protocol": 1,
  "generated_at": "2026-07-24T12:00:00Z",
  "last_event_sequence": 42,
  "factory": {
    "version": 0,
    "mode": "PAUSED",
    "health": "HEALTHY",
    "market_status": "UNKNOWN",
    "next_gate": null
  },
  "campaigns": [],
  "candidates": [],
  "tasks": [],
  "attempts": [],
  "workers": [],
  "sessions": [],
  "attention_items": [],
  "resource_reservations": []
}
```

Events have a strictly increasing SQLite integer `sequence` and this envelope:

```json
{
  "sequence": 42,
  "event_id": "evt_...",
  "kind": "task.transitioned",
  "aggregate_type": "task",
  "aggregate_id": "tsk_...",
  "occurred_at": "2026-07-24T12:00:00Z",
  "payload": {}
}
```

The frontend applies events only in sequence order. Any gap, protocol mismatch,
or server restart triggers a new snapshot instead of speculative repair.

### 1.5 Runtime adapter contract

Rust implements:

```rust
pub trait AgentAdapter: Send + Sync {
    fn runtime(&self) -> AgentRuntime;
    fn probe(&self, configured_path: Option<&Path>) -> Result<RuntimeProbe, AdapterError>;
    fn build_launch(&self, request: &LaunchRequest) -> Result<LaunchSpec, AdapterError>;
}
```

`RuntimeProbe.resolved_path` is the exact binary used by `build_launch`.
Supported launch lifecycle operations are:

```text
probe → start → send_task → send_instruction → interrupt → terminate → collect_exit
```

The Rust session manager owns process identity, PTY I/O, Job Object membership,
redaction, and exit collection. Python owns task/attempt/lease state.

### 1.6 Autonomous dispatch handshake

The background factory does not depend on React, a visible window, or terminal
typing. While the factory is `RUNNING`, one Rust `DispatchSupervisor` polls the
authenticated sidecar with a bounded idle backoff and asks for the next grant.
Python remains the dispatcher: it selects only an eligible `READY` author task
or `EVALUATING` reviewer task after dependency, collision, budget, stop, and
runtime-capability checks. Rust reports which probed runtimes are currently
available and whether each has a capability-proven read-only reviewer mode,
but it cannot choose a different task or bypass Python policy. A reviewer is
never dispatched through a runtime lacking that mode.

`POST /v1/runtime-grants` accepts one of two strict version-1 request shapes:

```json
{
  "protocol": 1,
  "idempotency_key": "uuid4",
  "selection": "TASK",
  "task_id": "tsk_...",
  "expected_version": 4,
  "runtime_capabilities": [
    {"runtime": "codex", "author": true, "read_only_reviewer": true},
    {"runtime": "hermes", "author": true, "read_only_reviewer": false}
  ]
}
```

```json
{
  "protocol": 1,
  "idempotency_key": "uuid4",
  "selection": "NEXT",
  "expected_factory_version": 7,
  "runtime_capabilities": [
    {"runtime": "codex", "author": true, "read_only_reviewer": true},
    {"runtime": "hermes", "author": true, "read_only_reviewer": false}
  ]
}
```

`TASK` is the explicit operator start path. `NEXT` is the background path.
When no work is eligible, `NEXT` returns `204` and changes nothing. A successful
claim atomically creates the worker, session, attempt, lease, reservations,
one-time grant, and canonical task packet. Author claims move `READY → RUNNING`.
Reviewer claims keep the task `EVALUATING`, create a fresh
`attempt_kind="EVALUATOR"` session with no author conversation, and expose only
the sealed contract, diff/artifacts, tests, evidence, and receipt chain.
`NEXT` may report an empty capability list when both optional CLIs are
unavailable; that is an idle `204`, not a fabricated runtime or global health
failure.

The host starts only the exact runtime named by the returned grant. Any probe,
worktree, profile, packet, spawn, or reporting failure revokes the grant and
returns the attempt to reconciliation; the host never silently asks for
another card. Factory stop cancels the dispatch loop before stopping active
workers. Closing the window to the tray does not cancel it.

### 1.7 Worker grants and MCP tools

Python creates a 32-byte worker token, returns it once to Rust, and stores only
its SHA-256 digest, worker/task/attempt/session/lease IDs, expiry, and revoked
time. Rust injects:

```text
VESPER_FACTORY_MCP_URL=http://127.0.0.1:<port>/mcp
VESPER_WORKER_TOKEN=<raw one-time-returned token>
```

Codex receives one-launch config overrides using
`mcp_servers.vesper_factory.url` and
`mcp_servers.vesper_factory.bearer_token_env_var="VESPER_WORKER_TOKEN"`.

Hermes uses a dedicated locally cloned profile named `vesper-factory`. Its MCP
entry uses:

```yaml
mcp_servers:
  vesper_factory:
    url: "${VESPER_FACTORY_MCP_URL}"
    headers:
      Authorization: "Bearer ${VESPER_WORKER_TOKEN}"
    tools:
      include:
        - vesper_task_show
        - vesper_heartbeat
        - vesper_submit_evidence
        - vesper_create_followup
        - vesper_block
        - vesper_comment
        - vesper_request_evaluation
      resources: false
      prompts: false
```

Vesper provisions that profile through Hermes’ profile command after explicit
local setup confirmation. It does not edit the user’s normal Hermes profile.
Every tool derives authority from the bearer grant; no tool accepts task,
worker, attempt, session, or lease identity from model-controlled arguments.

### 1.8 Evidence and receipt authority

Evidence files are immutable and addressed by SHA-256. Paths must resolve under
the attempt worktree or the factory evidence directory before registration.
An authoritative receipt contains:

```json
{
  "receipt_id": "rcp_...",
  "kind": "evaluation.verdict",
  "aggregate_type": "attempt",
  "aggregate_id": "atm_...",
  "authority": "independent-evaluator-v1",
  "outcome": "VERIFIED",
  "contract_hash": "sha256:...",
  "input_hash": "sha256:...",
  "evidence_ids": ["evd_..."],
  "manifest_id": "evd_...",
  "created_at": "2026-07-24T12:00:00Z"
}
```

Receipts are append-only. Corrections append superseding receipts; they never
update prior receipt bytes.

### 1.9 Run manifest

`RunManifestV1` requires:

```text
dataset_snapshot, dataset_hash, universe, start_date, end_date,
corporate_action_version, feature_version, source_commit,
dependency_lock_hash, random_seeds, transaction_costs, slippage,
evaluation_split, runtime_versions, compute_envelope
```

Replay reads the immutable original manifest and creates a linked new attempt.
It never mutates the original evidence or receipt.

### 1.10 Redaction

Python and Rust consume the same checked-in cases from
`tests/fixtures/factory_redaction_cases.json`. Both implementations:

1. Replace every active session/worker token and every configured secret value
   of eight or more characters with `[REDACTED]`.
2. Replace values in common credential assignments and authorization headers.
3. Preserve non-secret task IDs, hashes, symbols, metrics, and ordinary output.
4. Reject a receipt/event payload if canonical serialized bytes still contain
   a known secret after redaction.

Redaction happens before text is logged, persisted, emitted, or inserted into a
prompt/context packet. Tests use synthetic credentials only.

---

## 2. Delivery Dependency Order

```text
Plan 01 Factory Kernel
       ├── Plan 02 Native Desktop Shell
       └── Plan 03 Codex/Hermes Execution
              │              │
              └──────┬───────┘
                     ▼
            Plan 04 Research Pipeline
                    │
                    ▼
          Plan 05 Learning & Autonomy
                    │
                    ▼
           Plan 06 Release Hardening
```

Plans 02 and 03 may begin after Plan 01 publishes schema `1`, the API contract,
the dispatch/grant contract, and a fake-sidecar fixture. Plan 04 requires both
the working desktop host and attempt/evidence/runtime paths. Plan 05 consumes
verified episodes from Plan 04. Plan 06 runs only after all product behavior is
present.

## 3. Plan Files and Owned Write Sets

| Plan | File | Primary write set |
|---|---|---|
| 01 | `2026-07-24-vesper-factory-kernel.md` | `vesper/factory/`, `tests/factory/`, `scripts/factory.py`, `requirements.txt` |
| 02 | `2026-07-24-vesper-native-desktop-shell.md` | `apps/desktop/` except runtime adapter modules |
| 03 | `2026-07-24-vesper-agent-execution.md` | `apps/desktop/src-tauri/src/agents/`, terminal UI modules, runtime contract tests |
| 04 | `2026-07-24-vesper-research-pipeline.md` | research/evaluation Python modules and Research/Overview/Review frontend modules |
| 05 | `2026-07-24-vesper-learning-autonomy.md` | learning/routing/autonomy Python modules and Memory frontend modules |
| 06 | `2026-07-24-vesper-release-hardening.md` | packaging, migrations, recovery, release tests, notices, parity documents |

Shared-file edits must be serialized and rebased on the prior plan. Agents must
not make concurrent edits to `requirements.txt`, database migrations, root
configuration, or shared frontend API types.

Migration ownership and ordering are fixed:

```text
vesper/factory/migrations.py::SCHEMA_V1          Plan 01
vesper/factory/research/migration.py::SCHEMA_V2  Plan 04
vesper/factory/learning_migration.py::SCHEMA_V3  Plan 05
```

Plans 02 and 03 do not add database migrations. Plan 06 tests upgrade and
backup behavior across versions `1`, `2`, and `3`; it adds no product schema.
Each later migration is registered by a surgical edit to
`vesper/factory/migrations.py`, runs transactionally, records its checksum, and
updates `PRAGMA user_version` only after all statements succeed.

## 4. Milestone Acceptance Gates

- [ ] **M1 Kernel:** a CLI can admit a campaign, transition a card,
      deterministically claim the next author/reviewer grant, acquire and
      reconcile a lease, append evidence/receipts, use every structured worker
      tool, stop/resume the factory, and replay ordered events from temporary
      SQLite state.
- [ ] **M2 Desktop:** the packaged development shell starts the sidecar,
      renders Mission Control from snapshot/events, handles tray/background
      mode, surfaces the Operator Inbox, and fails into read-only recovery.
- [ ] **M3 Execution:** both explicit start and the background dispatcher start
      the exact Python-selected probed CLI, send the full task packet
      automatically, stream a redacted PTY, launch fresh reviewer sessions for
      `EVALUATING` work, and record truthful exit/interruption state without a
      visible React window.
- [ ] **M4 Research:** deterministic evaluation, candidate lineage,
      fork/compare/replay, analytics, integrated review, shadow, and bounded
      paper gates work from authoritative manifests and receipts.
- [ ] **M5 Learning:** verified episodes drive FTS context, routing/template
      canaries, bounded code acceptance, rollback, and inspectable lesson state.
- [ ] **M6 Release:** migrations, forced-kill recovery, failure injection,
      100-task simulation, Windows packaging/smoke, eight-hour soak, notices,
      and Tkinter replacement-parity evidence pass.

## 5. Approved Feature Coverage

| Approved feature | Domain implementation | Operator surface | Release proof |
|---|---|---|---|
| Operator Inbox | Plan 01 | Plan 02 | Plan 06 |
| Background factory mode | Plan 01 dispatch policy + Plan 03 headless supervisor | Plan 02 tray lifecycle | Plan 06 |
| Objective planning wizard | Plan 01 admission/contract commands | Plan 02 wizard | Plan 06 |
| Progressive card dossier | Plans 01 and 04 authoritative records | Plan 02 dossier | Plan 06 |
| Experiment lineage and comparison | Plan 04 | Plan 04 Research view | Plan 06 |
| Structured Vesper agent tools | Plan 01 MCP tools/grants | Plan 03 runtime injection | Plan 06 |
| Dependency and collision graph | Plan 01 guards/reservations | Plan 02 graph | Plan 06 |
| Factory analytics | Plan 04 measured projections | Plan 04 Overview | Plan 06 |
| Integrated review panel | Plan 04 evidence/verdict data | Plans 02 and 04 | Plan 06 |

Factory-wide stop, hard local-resource budgets, reproducibility/retention, and
paper-authority enforcement are cross-cutting acceptance requirements, not
additional optional features. Plans may add only support needed to implement
these approved items; no plugin marketplace, general IDE, multi-node control,
cloud state, crypto workflow, or live-trading path is implied.

## 6. Verification Commands Used by Every Plan

From Git Bash on Windows, create a native temporary directory and run:

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-pytest-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest -q --basetemp="$TMPROOT/pytest"
```

For desktop work:

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

Run `python -m py_compile` on every changed Python module. Inspect
`git diff --check`, `git diff --stat`, and the focused diff before every commit.
