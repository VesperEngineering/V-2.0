# Vesper Codex and Hermes Agent Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver milestone M3 so both explicit operator start and the headless background dispatcher start the exact Python-selected Codex or Hermes CLI in an isolated Windows workspace, inject the complete Python-owned task packet, stream a redacted PTY, enforce process-tree limits, and record truthful exit or interruption state.

**Architecture:** Rust owns one runtime registry, a window-independent dispatch supervisor, Windows executable resolution, version negotiation, workspaces, PTYs, Job Objects, redaction, bounded terminal tails, and session controls. The Plan 01 sidecar remains authoritative for dispatch order, task, attempt, worker, session, lease, grant, and packet data; Plan 03 consumes its version-1 HTTP contracts without creating a second workflow state machine. React implements the Plan 02 `RuntimeSurface` boundary with xterm and receives only redacted text plus non-secret session metadata.

**Tech Stack:** Rust stable, Tauri 2, `portable-pty 0.9.0`, `windows-sys 0.61.2`, `serde_yaml_ng 0.10.0`, React 19, TypeScript, Vitest, React Testing Library, `@xterm/xterm 6.0.0`, `@xterm/addon-fit 0.11.0`, Codex CLI `>=0.139.0,<1.0.0`, Hermes CLI `>=0.18.2,<1.0.0`.

## Global Constraints

- Before any product-code edit, follow `AGENTS.md`: load matching skills, read `SKILLS/CODE.md` and `SKILLS/EXAMPLES.md`, and query `.codegraph` for every symbol or file to be changed. The present clone has no `.codegraph`; implementation must run in the canonical Windows checkout with a current index or stop before editing code.
- Plan 03 may start only after Plan 01 publishes schema `1`, the frozen `/v1` API, runtime-grant and task-packet fixtures, and its fake sidecar, and after Plan 02 publishes the M2 shell, typed sidecar client, `RuntimeStopParticipant`, and `RuntimeSurface`.
- Serialize shared-file edits after Plans 01 and 02. Do not replace their sidecar supervisor, authenticated proxy, event cursor, lifecycle authority, Mission Control state, or domain contracts.
- The Plan 03 write set is `apps/desktop/src-tauri/src/agents/`, the two test-only agent binaries, runtime contract tests, terminal/runtime frontend modules, and the smallest listed integration edits in existing Plan 02 files. Do not edit Python, database migrations, `requirements.txt`, `config/`, `vesper/risk.py`, `vesper/execution.py`, scheduler code, `vesper/data/massive/`, `vesper/data/model_research/`, or active model artifacts.
- Rust owns process identity, PTY I/O, Windows Job Object membership, redaction, and exit collection. Python owns task, attempt, worker, session, lease, grant, packet, and workflow state.
- Keep the frozen adapter trait and lifecycle exactly: `probe → start → send_task → send_instruction → interrupt → terminate → collect_exit`. `RuntimeProbe.resolved_path` is the exact target represented by `LaunchSpec`; no launch-time rediscovery is allowed.
- An explicit configured CLI path wins. If it is invalid, Vesper reports `BLOCKED` and does not fall back to aliases or `PATH`. Shell preference is separate and never changes a Codex or Hermes path.
- Do not infer unsupported CLI flags. Probe the frozen current interfaces and block unsupported versions or missing capabilities with a concrete remediation.
- Never place a sidecar session token or worker token in argv, frontend state, Tauri events, errors, logs, SQLite, task packets, receipts, or debug output. The raw worker token may exist only in the one runtime-grant response, Rust secret memory, and the child environment.
- Persist only a redacted terminal tail bounded by the authoritative grant ceiling. Redact before both UI emission and file persistence.
- Code-changing attempts use a validated Git worktree. Do not merge, rebase, delete, or auto-clean a worktree in this plan.
- Exit code `0` is process evidence, not task completion. Only the Python controller and authoritative receipts may advance workflow state.
- Research scoring/verdict policy, model/candidate progression, learned routing,
  prompt-template learning, analytics, paper effects, and autonomous code
  acceptance belong to Plans 04 and 05 and are excluded. Generic launch of a
  Python-selected `EVALUATOR` grant in a capability-proven read-only mode is
  required here; Rust never decides or interprets the verdict.
- Use test-first changes, deterministic fake executables, one focused commit per task, and the exact red/green commands below.

---

## Dependencies and Acceptance Gates

### Plan 01 contract gate

Before Task 1, verify Plan 01 tests publish these exact schema-1 exchanges. If any field differs, stop and reconcile under Plan 01 ownership; do not create an alternative Rust-only contract.

```json
POST /v1/runtime-grants
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

The window-independent dispatch loop uses the same endpoint with
`selection="NEXT"`, `expected_factory_version`, and the same capability
records. `204` means idle and changes nothing.

```json
{
  "protocol": 1,
  "selection": "TASK",
  "worker_token": "<base64url encoding of exactly 32 bytes>",
  "worker_id": "wrk_...",
  "task_id": "tsk_...",
  "attempt_id": "atm_...",
  "session_id": "ses_...",
  "lease_id": "uuid4",
  "session_version": 0,
  "attempt_kind": "AUTHOR",
  "review_of_attempt_id": null,
  "runtime": "codex",
  "expires_at": "2026-07-24T12:30:00Z",
  "worktree": {
    "repository_root": "C:\\src\\V-2.0",
    "worktree_path": "C:\\Users\\me\\AppData\\Local\\Vesper\\Factory\\worktrees\\atm_...",
    "branch_name": "factory/attempt/atm_...",
    "source_commit": "40-lowercase-hex"
  },
  "limits": {
    "wall_seconds": 1800,
    "cpu_percent": 100,
    "memory_bytes": 4294967296,
    "terminal_bytes": 5000000
  },
  "task_packet": {
    "protocol": 1,
    "canonical_json": "{\"protocol\":1,...}",
    "sha256": "sha256:<64-lowercase-hex>"
  }
}
```

`POST /v1/runtime-grants/<session_id>/revoke` accepts
`{"protocol":1,"reason":"SPAWN_FAILED|EXITED|INTERRUPTED|TERMINATED|HOST_SHUTDOWN"}`.
It is idempotent and returns the same revocation result on a repeat.

Plan 01's generic `POST /v1/commands` accepts the frozen command envelope for
`runtime.session_started` and `runtime.session_exited`:

```json
{
  "protocol": 1,
  "idempotency_key": "uuid4",
  "kind": "runtime.session_started",
  "payload": {
    "session_id": "ses_...",
    "process_id": 1234,
    "resolved_path": "C:\\absolute\\codex.exe",
    "runtime_version": "0.139.0",
    "worktree_path": "C:\\absolute\\worktree"
  },
  "expected_version": 0
}
```

```json
{
  "protocol": 1,
  "idempotency_key": "uuid4",
  "kind": "runtime.session_exited",
  "payload": {
    "session_id": "ses_...",
    "exit_code": 0,
    "reason": "EXITED|INTERRUPTED|TERMINATED|SPAWN_FAILED|HOST_SHUTDOWN",
    "terminal_bytes": 2048,
    "log_path": "C:\\Users\\me\\AppData\\Local\\Vesper\\Factory\\logs\\terminal\\ses_....log"
  },
  "expected_version": 1
}
```

The sidecar must construct the canonical task packet. Rust validates and sends
it without adding policy or learning content.

### Plan 02 contract gate

Plan 02 M2 must be green and must expose these exact boundaries:

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

Plan 03 extends the existing Plan 02 sidecar client and sole frontend IPC
wrapper; it does not bypass either.

### M3 acceptance gate

- One click can start either exact probed CLI for explicit intervention.
- With React unmounted and the window hidden, one background supervisor claims
  `NEXT` work and starts the exact Python-selected eligible CLI; `204` idles
  with bounded backoff and no busy loop.
- The complete packet is injected exactly once without manual task entry.
- `EVALUATING` work starts in a fresh reviewer session only on a runtime whose
  probe proves read-only-reviewer capability; it receives no author
  conversation and cannot write the attempt worktree.
- The same runtime probe drives Settings, launch eligibility, and active-session metadata; contradictory status is regression-tested.
- xterm receives ordered, redacted PTY output and resize events.
- Interrupt is graceful; terminate and factory stop kill the complete Job Object process tree.
- The worker grant is revoked on every terminal path, including worktree, profile, spawn, and reporting failures.
- Bounded redacted terminal persistence and truthful
  `runtime.session_started`/`runtime.session_exited` reporting pass fake-CLI
  integration tests on Windows.

---

## Frozen Plan 03 Interfaces

```rust
pub trait AgentAdapter: Send + Sync {
    fn runtime(&self) -> AgentRuntime;
    fn probe(&self, configured_path: Option<&Path>) -> Result<RuntimeProbe, AdapterError>;
    fn build_launch(&self, request: &LaunchRequest) -> Result<LaunchSpec, AdapterError>;
}
```

```rust
#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum AgentRuntime {
    Codex,
    Hermes,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum RuntimeCapability {
    InteractivePty,
    ExplicitWorkingDirectory,
    OneLaunchHttpMcp,
    BearerTokenEnv,
    ReadOnlyReviewer,
    DedicatedProfile,
    ProfileClone,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct RuntimeProbe {
    pub protocol: u8,
    pub runtime: AgentRuntime,
    pub state: RuntimeProbeState,
    pub resolved_path: Option<PathBuf>,
    pub invocation: Option<InvocationKind>,
    pub version: Option<String>,
    pub capabilities: BTreeSet<RuntimeCapability>,
    pub checked_at: String,
    pub reason: Option<String>,
    pub remediation: Option<String>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum RuntimeProbeState {
    NotConfigured,
    Available,
    Blocked,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
#[serde(tag = "kind", rename_all = "SCREAMING_SNAKE_CASE")]
pub enum InvocationKind {
    Native,
    CmdScript { command_processor: PathBuf },
}
```

`LaunchRequest` contains an `AVAILABLE` `RuntimeProbe`, the Python-owned
attempt kind/access mode, validated worktree, loopback MCP URL, in-memory
`WorkerToken`, and optional Hermes profile home.
`LaunchSpec` is intentionally not serializable and implements a secret-safe
`Debug`:

```rust
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ExecutionAccess {
    Author,
    ReadOnlyReviewer,
}

pub struct LaunchRequest {
    pub probe: RuntimeProbe,
    pub access: ExecutionAccess,
    pub worktree: PathBuf,
    pub mcp_url: String,
    pub worker_token: WorkerToken,
    pub hermes_profile_home: Option<PathBuf>,
}

pub struct LaunchSpec {
    pub target_path: PathBuf,
    pub invocation: InvocationKind,
    pub args: Vec<OsString>,
    pub cwd: PathBuf,
    pub public_env: BTreeMap<OsString, OsString>,
    pub secret_env: BTreeMap<OsString, WorkerToken>,
}
```

`ReadOnlyReviewer` requires `RuntimeCapability::ReadOnlyReviewer`; otherwise
`build_launch` fails before process creation. In the first release Codex earns
that capability only when its capability probe confirms the installed CLI's
read-only sandbox interface and an integration test proves attempted writes
fail. Hermes remains author-capable but reviewer-ineligible unless the probed
installed version can produce an equivalently deny-write dedicated profile
and pass the same fixture; absence blocks reviewer dispatch rather than
weakening isolation.

`WorkerToken` decodes base64url without padding into exactly `[u8; 32]`, has no
`Clone`, `Debug`, `Display`, `Serialize`, or getter returning `String`, and
overwrites its byte array in `Drop`.

The sidecar packet's `canonical_json` must decode to this exact shape:

```json
{
  "protocol": 1,
  "task": {
    "task_id": "tsk_...",
    "task_version": 4,
    "attempt_id": "atm_...",
    "worker_id": "wrk_...",
    "session_id": "ses_...",
    "lease_id": "uuid4",
    "title": "Complete title",
    "description": "Complete description",
    "acceptance_criteria": ["frozen criterion"],
    "stop_conditions": ["frozen stop"]
  },
  "authority": {
    "allowed": ["bounded effect"],
    "denied": ["protected effect"]
  },
  "workspace": {
    "repository_root": "C:\\absolute\\repo",
    "worktree_path": "C:\\absolute\\worktree",
    "permitted_paths": ["relative/path"],
    "denied_paths": ["config", "vesper/risk.py"]
  },
  "instructions": {
    "required_skills": ["skill-name"],
    "repository_rules": [
      {"path": "AGENTS.md", "sha256": "sha256:<64-lowercase-hex>"}
    ]
  },
  "dependencies": {
    "task_ids": ["tsk_..."],
    "receipt_ids": ["rcp_..."]
  },
  "context": {
    "evidence_ids": ["evd_..."],
    "items": [{"kind": "bounded", "text": "redacted context"}]
  },
  "expected_output": {
    "summary": "required",
    "evidence": "structured MCP submissions",
    "receipt_schema": 1
  },
  "run_manifest_schema": {
    "required": [
      "dataset_snapshot",
      "dataset_hash",
      "universe",
      "start_date",
      "end_date",
      "corporate_action_version",
      "feature_version",
      "source_commit",
      "dependency_lock_hash",
      "random_seeds",
      "transaction_costs",
      "slippage",
      "evaluation_split",
      "runtime_versions",
      "compute_envelope"
    ]
  }
}
```

Unknown or missing keys, identity mismatch with the grant, a non-loopback MCP
URL, noncanonical packet bytes, or a SHA-256 mismatch blocks launch and revokes
the grant.

---

### Task 1: Add Runtime Contracts and Pinned Dependencies

**Files:**
- Modify: `apps/desktop/src-tauri/Cargo.toml`
- Modify: `apps/desktop/src-tauri/Cargo.lock`
- Create: `apps/desktop/src-tauri/src/agents/mod.rs`
- Create: `apps/desktop/src-tauri/src/agents/types.rs`
- Create: `apps/desktop/src-tauri/src/agents/error.rs`
- Create: `apps/desktop/src-tauri/tests/agent_contract.rs`

**Interfaces:**
- Produces the frozen trait, enums, `RuntimeProbe`, `ExecutionAccess`, `LaunchRequest`,
  `LaunchSpec`, `WorkerToken`, `RuntimeGrantV1`, `TaskPacketEnvelopeV1`,
  `WorktreeSpecV1`, and `RuntimeLimitsV1`.
- Adds exact direct dependencies `portable-pty = "=0.9.0"`,
  `windows-sys = "=0.61.2"` with Win32 process/threading, Job Object, console,
  foundation, and security features, and `serde_yaml_ng = "=0.10.0"`.
- Reuses Plan 02's existing Serde, async, HTTP, URL, UUID, SHA-256, and base64
  dependencies; do not add duplicate crates.

- [ ] **Step 1: Write contract tests first**

```rust
#[test]
fn worker_token_accepts_exactly_32_bytes_and_never_serializes() {
    let encoded = base64::engine::general_purpose::URL_SAFE_NO_PAD.encode([7_u8; 32]);
    let grant: RuntimeGrantV1 = serde_json::from_value(json!({
        "protocol": 1,
        "selection": "TASK",
        "worker_token": encoded,
        "worker_id": "wrk_00000000000000000000000000000000",
        "task_id": "tsk_00000000000000000000000000000000",
        "attempt_id": "atm_00000000000000000000000000000000",
        "session_id": "ses_00000000000000000000000000000000",
        "lease_id": "00000000-0000-4000-8000-000000000000",
        "session_version": 0,
        "attempt_kind": "AUTHOR",
        "review_of_attempt_id": null,
        "runtime": "codex",
        "expires_at": "2026-07-24T12:30:00Z",
        "worktree": worktree_fixture(),
        "limits": limits_fixture(),
        "task_packet": packet_fixture()
    })).unwrap();
    assert!(!format!("{grant:?}").contains(&encoded));
    assert!(serde_json::to_value(&grant).is_err());
}
```

Also test exact enum spelling, denied unknown grant fields, 32-byte token
length, URL-safe decoding, positive limits, RFC 3339 `Z`, ID prefixes, and
secret-safe error/debug output.

- [ ] **Step 2: Run the focused test and verify red**

```bash
cd apps/desktop/src-tauri
cargo test --test agent_contract
```

Expected: FAIL because `agents` and its contract types do not exist.

- [ ] **Step 3: Implement only the contracts and dependency pins**

Use `#[serde(deny_unknown_fields)]` on all sidecar and Tauri command inputs.
Implement `Drop for WorkerToken` with `self.0.fill(0)`. Its only operation is:

```rust
impl WorkerToken {
    pub(crate) fn with_base64url<R>(&self, use_value: impl FnOnce(&str) -> R) -> R {
        let encoded = URL_SAFE_NO_PAD.encode(self.0);
        let result = use_value(&encoded);
        drop(encoded);
        result
    }
}
```

Do not derive or implement serialization for `RuntimeGrantV1`.

- [ ] **Step 4: Run green verification**

```bash
cd apps/desktop/src-tauri
cargo fmt --check
cargo test --test agent_contract
```

Expected: formatting exits `0`; all contract tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src-tauri/Cargo.toml apps/desktop/src-tauri/Cargo.lock apps/desktop/src-tauri/src/agents/mod.rs apps/desktop/src-tauri/src/agents/types.rs apps/desktop/src-tauri/src/agents/error.rs apps/desktop/src-tauri/tests/agent_contract.rs
git diff --check --cached
git commit -m "feat(desktop): add agent execution contracts"
```

### Task 2: Implement Windows Discovery, Capability Probes, and One Registry

**Files:**
- Create: `apps/desktop/src-tauri/src/agents/resolve.rs`
- Create: `apps/desktop/src-tauri/src/agents/probe.rs`
- Create: `apps/desktop/src-tauri/src/agents/registry.rs`
- Create: `apps/desktop/src-tauri/tests/agent_discovery.rs`

**Interfaces:**

```rust
pub struct RuntimeRegistry {
    adapters: BTreeMap<AgentRuntime, Arc<dyn AgentAdapter>>,
    probes: RwLock<BTreeMap<AgentRuntime, RuntimeProbe>>,
}

impl RuntimeRegistry {
    pub fn refresh(
        &self,
        runtime: AgentRuntime,
        configured_path: Option<&Path>,
    ) -> Result<RuntimeProbe, AdapterError>;
    pub fn current(&self, runtime: AgentRuntime) -> RuntimeProbe;
    pub fn available_for_launch(
        &self,
        runtime: AgentRuntime,
    ) -> Result<RuntimeProbe, AdapterError>;
}
```

Resolution order is exact:

1. A configured absolute file path, with no fallback on failure.
2. `%LOCALAPPDATA%\Microsoft\WindowsApps\codex.exe|codex.cmd` or
   `hermes.exe|hermes.cmd`.
3. Every `PATH` directory in order, using `PATHEXT` in order for a bare name.

Normalize absolute paths, compare case-insensitively for deduplication, reject
directories and non-`.exe`/`.com`/`.cmd`/`.bat` targets, and classify scripts as
`CmdScript` using `%COMSPEC%` only when it is an absolute `cmd.exe`; otherwise
use `%SystemRoot%\System32\cmd.exe`.

Probe the exact resolved target with a five-second timeout and a combined
64-KiB output ceiling:

| Runtime | Version command | Required help checks | Supported range |
|---|---|---|---|
| Codex | `codex --version` | root `--help` contains `--config`, `--no-alt-screen`, and `--cd` | `>=0.139.0,<1.0.0` |
| Hermes | `hermes --version` | root `--help` contains `chat` and `profile`; `profile create --help` contains `--clone-from` and `--no-alias` | `>=0.18.2,<1.0.0` |

Every Settings status, start decision, `LaunchSpec`, and active-session record
must use the same immutable probe returned by `RuntimeRegistry`.

- [ ] **Step 1: Write discovery and contradiction tests**

Cover explicit-path precedence, invalid explicit path with a valid `PATH`
candidate, application-alias precedence, `PATHEXT` order, case-insensitive
deduplication, timeout, oversized output, malformed version, below-floor
version, missing help capability, and shell-preference independence.

```rust
#[test]
fn invalid_explicit_path_never_falls_back_to_path() {
    let result = resolver_fixture()
        .with_path_fake("codex.exe")
        .resolve(AgentRuntime::Codex, Some(Path::new(r"C:\missing\codex.exe")));
    assert_eq!(result.unwrap_err().code(), "CONFIGURED_RUNTIME_NOT_FOUND");
}
```

- [ ] **Step 2: Run red**

```bash
cd apps/desktop/src-tauri
cargo test --test agent_discovery
```

Expected: FAIL because resolver, probe runner, and registry are unresolved.

- [ ] **Step 3: Implement deterministic resolution and negotiation**

Use direct process APIs, never a user-selected shell. Convert a successful
probe into Plan 02's `RuntimeAdapterHealthV1`; `reason` and `remediation` are
stable, non-secret strings. Store the probe in the registry before projecting
it. `available_for_launch` clones that stored probe and never calls the resolver.

- [ ] **Step 4: Run green**

```bash
cd apps/desktop/src-tauri
cargo test --test agent_discovery
cargo test agents::probe agents::registry
```

Expected: all discovery, capability, and one-source-of-truth tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src-tauri/src/agents/resolve.rs apps/desktop/src-tauri/src/agents/probe.rs apps/desktop/src-tauri/src/agents/registry.rs apps/desktop/src-tauri/tests/agent_discovery.rs
git diff --check --cached
git commit -m "feat(desktop): probe agent runtimes once"
```

### Task 3: Build the Codex One-Launch Adapter

**Files:**
- Create: `apps/desktop/src-tauri/src/agents/codex.rs`
- Create: `apps/desktop/src-tauri/tests/codex_adapter.rs`
- Modify: `apps/desktop/src-tauri/src/agents/mod.rs`

**Exact launch interface:**

For an available Codex probe, `build_launch` produces the exact target path,
worktree cwd, token environment, and argv below:

```text
--no-alt-screen
--cd
<absolute worktree>
--config
mcp_servers.vesper_factory.url="<escaped loopback MCP URL>"
--config
mcp_servers.vesper_factory.bearer_token_env_var="VESPER_WORKER_TOKEN"
```

Environment:

```text
VESPER_FACTORY_MCP_URL=http://127.0.0.1:<port>/mcp
VESPER_WORKER_TOKEN=<base64url worker token>
```

For `ExecutionAccess::ReadOnlyReviewer`, append exactly:

```text
--sandbox
read-only
--ask-for-approval
never
```

The Codex probe advertises `ReadOnlyReviewer` only when the exact installed
binary's help/capability fixture accepts both options and the fake/real
integration fixture proves a write attempt is denied. An author launch does
not receive these two overrides.

The URL value is encoded as a TOML basic string. The token and task packet
never enter argv. `build_launch` rejects a runtime mismatch, non-`AVAILABLE`
probe, absent resolved path, non-loopback HTTP URL, relative worktree, or
worktree/profile mismatch, and rejects reviewer access without the proven
capability.

- [ ] **Step 1: Write failing exact-argv tests**

```rust
#[test]
fn codex_launch_uses_the_probed_path_and_bearer_env_indirection() {
    let spec = adapter().build_launch(&codex_request()).unwrap();
    assert_eq!(spec.target_path, PathBuf::from(r"C:\Tools\codex.exe"));
    assert_eq!(spec.args, os_args([
        "--no-alt-screen",
        "--cd",
        r"C:\Factory\worktrees\atm_1",
        "--config",
        "mcp_servers.vesper_factory.url=\"http://127.0.0.1:54321/mcp\"",
        "--config",
        "mcp_servers.vesper_factory.bearer_token_env_var=\"VESPER_WORKER_TOKEN\"",
    ]));
    assert!(!spec.args.iter().any(|arg| arg.to_string_lossy().contains("worker-secret")));
}
```

Also test quote/backslash escaping, `.cmd` classification, exact reviewer
flags, an attempted reviewer write failing, and reviewer denial when the
capability probe does not advertise `ReadOnlyReviewer`.

- [ ] **Step 2: Run red**

```bash
cd apps/desktop/src-tauri
cargo test --test codex_adapter
```

Expected: FAIL because `CodexAdapter` does not exist.

- [ ] **Step 3: Implement `CodexAdapter`**

Implement the frozen trait directly. `probe` delegates to the shared probe
runner; `build_launch` consumes only `request.probe`. For `.cmd`/`.bat`, retain
`target_path` as the exact probe path and defer command-processor wrapping to
Task 8.

- [ ] **Step 4: Run green**

```bash
cd apps/desktop/src-tauri
cargo test --test codex_adapter
cargo test agents::codex
```

Expected: all Codex capability, argv, URL, cwd, and secret-boundary tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src-tauri/src/agents/codex.rs apps/desktop/src-tauri/src/agents/mod.rs apps/desktop/src-tauri/tests/codex_adapter.rs
git diff --check --cached
git commit -m "feat(desktop): add exact Codex launch adapter"
```

### Task 4: Provision and Launch the Dedicated Hermes Profile

**Files:**
- Create: `apps/desktop/src-tauri/src/agents/hermes.rs`
- Create: `apps/desktop/src-tauri/tests/hermes_adapter.rs`
- Modify: `apps/desktop/src-tauri/src/agents/mod.rs`

**Interfaces:**

```rust
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HermesProfileProvisionRequestV1 {
    pub confirmed: bool,
    pub base_home: PathBuf,
    pub source_profile: String,
}

pub struct HermesProfileManager;

impl HermesProfileManager {
    pub fn provision(
        &self,
        probe: &RuntimeProbe,
        request: &HermesProfileProvisionRequestV1,
    ) -> Result<PathBuf, AdapterError>;
}
```

Reject `confirmed=false`, nonabsolute or symlinked `base_home`, path separators
in `source_profile`, `source_profile == "vesper-factory"`, and any probe not
`AVAILABLE`. Run the exact probed Hermes target with:

```text
hermes profile create vesper-factory --clone-from <source_profile> --no-alias
```

For this command only, set `HERMES_HOME=<base_home>`. The resulting dedicated
home is `<base_home>\profiles\vesper-factory`. Modify only its `config.yaml`,
preserve every unrelated key, and set this exact subtree:

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

Write through an exclusive sibling file and atomic replace. Refuse symlinked
profile/config targets. Re-running is idempotent and never edits the source or
normal profile.

Hermes launch uses exact argv `["chat"]`, cwd equal to the worktree, and:

```text
HERMES_HOME=<base_home>\profiles\vesper-factory
VESPER_FACTORY_MCP_URL=http://127.0.0.1:<port>/mcp
VESPER_WORKER_TOKEN=<base64url worker token>
```

This `vesper-factory` profile is author-capable only. In the first-release
contract `HermesAdapter::build_launch` rejects
`ExecutionAccess::ReadOnlyReviewer` and the probe reports
`read_only_reviewer=false`. Do not approximate reviewer isolation with prompt
text or a mutable allowlist. A later Hermes version may become eligible only
after adding a version-probed deny-write profile and the same attempted-write
integration test under a separately reviewed change.

- [ ] **Step 1: Write failing profile and adapter tests**

Hash the source profile before and after provisioning. Assert exact clone argv,
confirmation enforcement, idempotence, YAML merge, literal `${...}` values,
normal-profile immutability, `chat` argv, profile `HERMES_HOME`, and no token in
disk bytes or argv.

- [ ] **Step 2: Run red**

```bash
cd apps/desktop/src-tauri
cargo test --test hermes_adapter
```

Expected: FAIL because `HermesAdapter` and `HermesProfileManager` are unresolved.

- [ ] **Step 3: Implement profile cloning and the adapter**

Use `serde_yaml_ng` mappings, not string concatenation. Treat an already
existing dedicated profile as valid only after its MCP subtree is made exact.
Do not change Hermes' selected/default profile or the process-wide `HOME`.

- [ ] **Step 4: Run green**

```bash
cd apps/desktop/src-tauri
cargo test --test hermes_adapter
cargo test agents::hermes
```

Expected: all cloning, profile isolation, YAML, environment, and launch tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src-tauri/src/agents/hermes.rs apps/desktop/src-tauri/src/agents/mod.rs apps/desktop/src-tauri/tests/hermes_adapter.rs
git diff --check --cached
git commit -m "feat(desktop): isolate Hermes factory profile"
```

### Task 5: Create Validated Attempt Worktrees

**Files:**
- Create: `apps/desktop/src-tauri/src/agents/worktree.rs`
- Create: `apps/desktop/src-tauri/tests/agent_worktree.rs`
- Modify: `apps/desktop/src-tauri/src/agents/mod.rs`

**Interface:**

```rust
pub trait WorktreeManager: Send + Sync {
    fn prepare(&self, spec: &WorktreeSpecV1) -> Result<PreparedWorktree, AdapterError>;
}

pub struct PreparedWorktree {
    pub repository_root: PathBuf,
    pub worktree_path: PathBuf,
    pub branch_name: String,
    pub source_commit: String,
    pub read_only: bool,
}
```

Validation requires absolute canonical paths, a real repository root, a
worktree strictly below `%LOCALAPPDATA%\Vesper\Factory\worktrees`, branch
`factory/attempt/<attempt_id>`, source commit `[0-9a-f]{40}`, and no existing
path except an idempotent worktree whose branch and `HEAD` already match.

Invoke Git directly, never through a shell:

```text
git -C <repository_root> worktree add -b <branch_name> <worktree_path> <source_commit>
```

After success, require `git -C <worktree_path> rev-parse --verify HEAD` to equal
the source commit and `git -C <worktree_path> status --porcelain` to be empty.
Do not run remove, prune, merge, rebase, checkout, reset, or clean.

- [ ] **Step 1: Write failing temporary-repository tests**

Cover valid creation, wrong branch/attempt pairing, path escape, symlink escape,
noncommit source, dirty/idempotent mismatch, argv with spaces, and canonical
repository remaining on its original branch and commit.
Also prove the returned `read_only` bit exactly matches the Python grant and
cannot be downgraded between packet validation and adapter launch.

- [ ] **Step 2: Run red**

```bash
cd apps/desktop/src-tauri
cargo test --test agent_worktree
```

Expected: FAIL because `WorktreeManager` is unresolved.

- [ ] **Step 3: Implement direct-argv worktree creation**

Capture bounded stdout/stderr for safe errors. Do not persist Git environment
variables from the parent except those required by the existing repository.

- [ ] **Step 4: Run green**

```bash
cd apps/desktop/src-tauri
cargo test --test agent_worktree
```

Expected: all isolation, path, idempotence, and canonical-checkout tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src-tauri/src/agents/worktree.rs apps/desktop/src-tauri/src/agents/mod.rs apps/desktop/src-tauri/tests/agent_worktree.rs
git diff --check --cached
git commit -m "feat(desktop): prepare isolated agent worktrees"
```

### Task 6: Consume Worker Grants and Inject the Canonical Task Packet

**Files:**
- Create: `apps/desktop/src-tauri/src/agents/grants.rs`
- Create: `apps/desktop/src-tauri/src/agents/task_packet.rs`
- Create: `apps/desktop/src-tauri/tests/agent_grants.rs`
- Modify: `apps/desktop/src-tauri/src/sidecar/client.rs`
- Modify: `apps/desktop/src-tauri/src/agents/mod.rs`

**Interfaces:**

Extend the Plan 02 authenticated client with only:

```rust
pub async fn create_runtime_grant(
    &self,
    request: &RuntimeGrantRequestV1,
) -> Result<Option<RuntimeGrantV1>, DesktopErrorV1>;

pub async fn revoke_runtime_grant(
    &self,
    session_id: &str,
    request: &RuntimeGrantRevokeV1,
) -> Result<RuntimeGrantRevocationV1, DesktopErrorV1>;

pub async fn report_runtime_session(
    &self,
    command: &FactoryCommandV1,
) -> Result<CommandResponseV1, DesktopErrorV1>;
```

These methods reuse the Plan 02 in-memory session bearer token internally.
They do not accept that token as an argument and do not expose it to React.
`RuntimeGrantRequestV1` is the roadmap's strict tagged `TASK`/`NEXT` enum.
The client maps an empty `NEXT` `204` to `Ok(None)` and rejects `204` for
`TASK`. Capability records come only from stored `RuntimeProbe` values:
`author=true` for an available compatible runtime and
`read_only_reviewer=true` only when that probe contains
`RuntimeCapability::ReadOnlyReviewer`.

`TaskPacket::validate(grant)` computes SHA-256 over the exact UTF-8
`canonical_json` bytes, parses the frozen schema above, verifies all six
identities and both worktree paths against the grant, rejects unknown fields,
and requires the full `RunManifestV1` field list in exact order when the
frozen task says `requires_run_manifest=true`; otherwise the required list
must be empty. It also verifies reviewer packets contain only sealed evidence
and no author conversation/terminal field.

`TaskPacket::framed_bytes()` returns exactly:

```rust
[
    b"\x1b[200~<VESPER_TASK_PACKET_V1>\n".as_slice(),
    canonical_json.as_bytes(),
    b"\n</VESPER_TASK_PACKET_V1>\x1b[201~\r".as_slice(),
].concat()
```

The session manager writes those bytes once, only after the CLI child-start
marker from Task 8. `send_instruction` writes subsequent user text using the
same bracketed-paste framing but without the task-packet tags.

Grant lifecycle is exact:

```text
available probe
→ Hermes profile ready when applicable
→ create `TASK` grant or receive Python-selected `NEXT` grant
→ validate packet
→ prepare worktree
→ spawn and assign Job Object
→ report runtime.session_started
→ inject packet exactly once
→ collect exit
→ report runtime.session_exited
→ confirm grant revocation idempotently
```

The successful exit command atomically records the exit and revokes the grant
in Python; Rust then confirms through the idempotent revoke endpoint. Every
failure after grant creation executes revoke. A reporting failure does not
suppress local process termination or revocation.

- [ ] **Step 1: Write failing fake-sidecar tests**

Assert authenticated endpoint paths and bodies, one-time token handling,
identity/hash/canonical failures, full run-manifest field list, exact framing,
single injection, and revoke on packet/worktree/spawn failures. Search all
captured requests, errors, and debug strings for the synthetic token.

- [ ] **Step 2: Run red**

```bash
cd apps/desktop/src-tauri
cargo test --test agent_grants
```

Expected: FAIL because grant client and task-packet validation are unresolved.

- [ ] **Step 3: Implement grant, validation, framing, and failure guards**

Use an RAII revocation guard armed immediately after decoding a grant. Disarm
only after an idempotent revoke result. Keep `WorkerToken` out of closure error
messages and erase temporary encodings immediately after child-environment
construction.

- [ ] **Step 4: Run green**

```bash
cd apps/desktop/src-tauri
cargo test --test agent_grants
cargo test agents::grants agents::task_packet
```

Expected: all HTTP, packet, secret, framing, and lifecycle tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src-tauri/src/agents/grants.rs apps/desktop/src-tauri/src/agents/task_packet.rs apps/desktop/src-tauri/src/agents/mod.rs apps/desktop/src-tauri/src/sidecar/client.rs apps/desktop/src-tauri/tests/agent_grants.rs
git diff --check --cached
git commit -m "feat(desktop): bind grants to task packets"
```

### Task 7: Redact Streams and Persist a Bounded Terminal Tail

**Files:**
- Create: `apps/desktop/src-tauri/src/agents/redaction.rs`
- Create: `apps/desktop/src-tauri/src/agents/terminal_log.rs`
- Create: `apps/desktop/src-tauri/tests/agent_redaction.rs`
- Modify: `apps/desktop/src-tauri/src/agents/mod.rs`

**Interfaces:**

```rust
pub struct StreamingRedactor {
    carry: Vec<u8>,
    active_secrets: Vec<Vec<u8>>,
}

impl StreamingRedactor {
    pub fn new(active_secrets: impl IntoIterator<Item = Vec<u8>>) -> Self;
    pub fn push(&mut self, bytes: &[u8]) -> Vec<u8>;
    pub fn finish(&mut self) -> Vec<u8>;
}

pub struct BoundedTerminalLog {
    path: Option<PathBuf>,
    ceiling: usize,
    tail: VecDeque<u8>,
    observed_redacted_bytes: u64,
}
```

Consume the shared cases from
`tests/fixtures/factory_redaction_cases.json`. Replace every active token and
configured secret of at least eight characters, credential assignments, and
authorization-header values with `[REDACTED]`. Preserve task IDs, hashes,
symbols, metrics, ANSI control sequences, and ordinary output.

The carry length is
`max(512, longest_active_secret_length + 64)`, so byte-split secrets cannot
escape. Invalid UTF-8 is rendered with replacement characters after redaction.
The exact order is PTY bytes → streaming redactor → both UI event and terminal
tail.

Log path is
`%LOCALAPPDATA%\Vesper\Factory\logs\terminal\<session_id>.log`. Keep only the
last `limits.terminal_bytes` redacted bytes; `0` creates no file. Write a
bounded sibling file and atomically replace the tail. Never put terminal text
in SQLite or a sidecar command.

- [ ] **Step 1: Write failing split-stream and bound tests**

For every shared redaction case, split input at every byte boundary and assert
the secret appears in neither emitted chunks nor disk. Test exact ceiling,
zero ceiling, ANSI preservation, generic bearer/assignment patterns, invalid
UTF-8, and a token longer than 512 bytes.

- [ ] **Step 2: Run red**

```bash
cd apps/desktop/src-tauri
cargo test --test agent_redaction
```

Expected: FAIL because stream redaction and bounded log types are unresolved.

- [ ] **Step 3: Implement one redacted fan-out**

Expose one `RedactedTerminalSink::accept(sequence, bytes)` that obtains the
redacted chunk once and passes the identical bytes to event emission and
`BoundedTerminalLog`. No caller may access unredacted terminal bytes after this
boundary.

- [ ] **Step 4: Run green**

```bash
cd apps/desktop/src-tauri
cargo test --test agent_redaction
```

Expected: all shared-case, split-boundary, and persistence-bound tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src-tauri/src/agents/redaction.rs apps/desktop/src-tauri/src/agents/terminal_log.rs apps/desktop/src-tauri/src/agents/mod.rs apps/desktop/src-tauri/tests/agent_redaction.rs
git diff --check --cached
git commit -m "feat(desktop): bound and redact terminal streams"
```

### Task 8: Supervise PTYs and Windows Job Object Process Trees

**Files:**
- Create: `apps/desktop/src-tauri/src/agents/job.rs`
- Create: `apps/desktop/src-tauri/src/agents/pty.rs`
- Create: `apps/desktop/src-tauri/src/agents/session.rs`
- Create: `apps/desktop/src-tauri/src/bin/vesper-agent-bootstrap.rs`
- Create: `apps/desktop/src-tauri/tests/agent_process_windows.rs`
- Modify: `apps/desktop/src-tauri/Cargo.toml`
- Modify: `apps/desktop/src-tauri/src/agents/mod.rs`

**Interfaces:**

```rust
pub trait AgentSessionControl: Send + Sync {
    async fn start(&self, request: AgentStartRequestV1) -> Result<AgentSessionV1, AdapterError>;
    async fn send_instruction(&self, session_id: &str, text: &str) -> Result<(), AdapterError>;
    async fn interrupt(&self, session_id: &str) -> Result<(), AdapterError>;
    async fn terminate(&self, session_id: &str, reason: ExitReasonV1) -> Result<(), AdapterError>;
    async fn resize(&self, session_id: &str, cols: u16, rows: u16) -> Result<(), AdapterError>;
    async fn collect_exit(&self, session_id: &str) -> Result<AgentExitV1, AdapterError>;
}
```

Use `portable-pty` for a native Windows PTY. Launch the
`vesper-agent-bootstrap` helper inside the PTY. The helper writes
`VESPER_BOOTSTRAP_READY_V1\r\n` and waits. Rust obtains its PID, creates a Job
Object, sets `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, applies the grant's memory
and CPU limits, assigns the helper, then writes
`VESPER_BOOTSTRAP_GO_V1\n`. The helper starts the exact `LaunchSpec`, writes
`VESPER_BOOTSTRAP_CHILD_V1\r\n`, and waits for the CLI with the same exit code.
Filter both markers before redaction, UI, and persistence. Inject the task
packet only after the child marker.

For `Native`, the helper executes `target_path` directly. For `CmdScript`, it
executes the validated `cmd.exe` from `InvocationKind` with:

```text
/D /Q /V:OFF /S /C <one command line produced by cmd_quote>
```

`cmd_quote` rejects NUL/CR/LF, quotes every token, doubles `%`, escapes embedded
quotes and carets, and is covered by a fake `.cmd` test containing spaces and
shell metacharacters in arguments. It never accepts a prejoined command string.

Session state is:

```text
STARTING → RUNNING → STOPPING → EXITED | INTERRUPTED
```

Each output chunk has a monotonic per-session `u64` sequence. `interrupt`
writes Ctrl+C to the PTY and waits for natural exit. `terminate` revokes the
grant, calls `TerminateJobObject`, closes the Job handle, then collects exit.
Closing the application or reaching the stop deadline must kill every
descendant. A crashed PTY becomes `INTERRUPTED`; it is never marked resumable.

Implement Plan 02's `RuntimeStopParticipant`: request Ctrl+C for all sessions,
wait until the supplied deadline, then `terminate_remaining` kills every
remaining Job Object and reports exact session IDs.

- [ ] **Step 1: Write failing Windows process-tree tests**

The fixture must spawn a grandchild that records its PID. Assert PTY streaming,
automatic packet injection once, resize, follow-up instruction, Ctrl+C,
natural exit, nonzero exit, forced termination of both child and grandchild,
Job-close cleanup, grant revocation, and truthful exit reporting. Guard the
integration test with `#[cfg(windows)]`; keep pure quoting/state tests portable.

- [ ] **Step 2: Run red on Windows**

```bash
cd apps/desktop/src-tauri
cargo test --test agent_process_windows
```

Expected: FAIL because Job, PTY, bootstrap, and session manager are unresolved.

- [ ] **Step 3: Implement the race-free bootstrap and session manager**

Never release the bootstrap before successful Job assignment. On each partial
failure, close the Job handle, kill any known process, revoke the grant, flush
the redactor, persist the bounded tail, and report `SPAWN_FAILED` or
`INTERRUPTED` when the sidecar is reachable.

- [ ] **Step 4: Run green on Windows**

```bash
cd apps/desktop/src-tauri
cargo test --test agent_process_windows -- --test-threads=1
cargo test agents::job agents::pty agents::session
```

Expected: all PTY, exact-target, Job Object, descendant, control, and exit tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src-tauri/Cargo.toml apps/desktop/src-tauri/Cargo.lock apps/desktop/src-tauri/src/bin/vesper-agent-bootstrap.rs apps/desktop/src-tauri/src/agents/job.rs apps/desktop/src-tauri/src/agents/pty.rs apps/desktop/src-tauri/src/agents/session.rs apps/desktop/src-tauri/src/agents/mod.rs apps/desktop/src-tauri/tests/agent_process_windows.rs
git diff --check --cached
git commit -m "feat(desktop): supervise agent process trees"
```

### Task 9: Expose Session Commands and Fake-CLI Regression Coverage

**Files:**
- Create: `apps/desktop/src-tauri/src/agents/commands.rs`
- Create: `apps/desktop/src-tauri/src/agents/dispatcher.rs`
- Create: `apps/desktop/src-tauri/src/bin/vesper-fake-agent.rs`
- Create: `apps/desktop/src-tauri/tests/agent_execution_windows.rs`
- Create: `apps/desktop/src-tauri/tests/agent_dispatch_windows.rs`
- Modify: `apps/desktop/src-tauri/Cargo.toml`
- Modify: `apps/desktop/src-tauri/src/contracts.rs`
- Modify: `apps/desktop/src-tauri/src/runtime_boundary.rs`
- Modify: `apps/desktop/src-tauri/src/ipc.rs`
- Modify: `apps/desktop/src-tauri/src/lib.rs`

**Tauri commands:**

```rust
agent_probe(request: AgentProbeRequestV1) -> RuntimeProbe
agent_provision_hermes_profile(request: HermesProfileProvisionRequestV1) -> HermesProfileStatusV1
agent_start(request: AgentStartRequestV1) -> AgentSessionV1
agent_send_instruction(request: AgentInstructionRequestV1) -> AgentSessionV1
agent_interrupt(session_id: String) -> AgentSessionV1
agent_terminate(session_id: String) -> AgentSessionV1
agent_resize(request: AgentResizeRequestV1) -> ()
agent_terminal_tail(session_id: String) -> TerminalTailV1
agent_get_session(session_id: String) -> AgentSessionV1
```

```rust
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AgentStartRequestV1 {
    pub task_id: String,
    pub runtime: AgentRuntime,
    pub idempotency_key: Uuid,
    pub cols: u16,
    pub rows: u16,
}
```

Rust obtains the task's current version from a fresh sidecar snapshot before
creating the grant; React cannot supply an authority version. Validate
`cols in 20..=500`, `rows in 5..=300`, instruction UTF-8 length `1..=16384`,
and exact prefixed IDs.

The same task adds a non-serializable `DispatchSupervisor` owned by Tauri
state:

```rust
pub struct DispatchSupervisor {
    registry: Arc<RuntimeRegistry>,
    sessions: Arc<AgentSessionManager>,
    sidecar: Arc<SidecarClient>,
    cancel: CancellationToken,
}

impl DispatchSupervisor {
    pub async fn run(self: Arc<Self>);
    pub async fn stop(&self);
}
```

After sidecar health is ready, `run` is the sole `NEXT` claimant. It reads the
fresh factory version and available stored probes, builds capability records,
and requests one `NEXT` grant only when local session capacity is available.
`204` backs off monotonically from 250 ms to 5 seconds; an ordered factory
event or session exit resets the delay. `409 VERSION_CONFLICT` refreshes the
snapshot and retries with a new idempotency key; it never reuses stale policy
input. A returned grant is passed to
`AgentSessionManager::start_from_grant` without allowing Rust to replace its
task or runtime. The next claim waits until that grant is either launched or
revoked, preventing token loss.

The loop starts independently of React after the sidecar reaches health,
continues when the window is hidden to the tray, pauses when factory mode is
not `RUNNING`, and stops before the sidecar during explicit quit/global stop.
Only one loop may exist per app process. Sidecar loss, protocol/schema
mismatch, restart-budget exhaustion, no eligible reviewer runtime, or local
capacity exhaustion never spins or launches speculative work.

Emit:

```rust
pub const TERMINAL_OUTPUT_EVENT: &str = "vesper://terminal-output";
pub const AGENT_SESSION_EVENT: &str = "vesper://agent-session";

pub struct TerminalChunkV1 {
    pub session_id: String,
    pub sequence: u64,
    pub text: String,
}
```

`AgentSessionV1` contains IDs, runtime, state, immutable `RuntimeProbe`,
worktree path, process ID, packet hash, started/ended times, exit code/reason,
redacted-byte count, and log path. It contains no token or raw terminal text.

Build `vesper-fake-agent` only with Cargo feature `test-fixtures`. Tests copy it
to `codex.exe`, `codex.cmd`, `hermes.exe`, and `hermes.cmd`. It implements the
exact version/help/profile/chat interfaces, records argv and a
`worker_token_present: bool` without recording the value, echoes synthetic
credentials, records the injected packet count/hash, accepts instructions,
and can spawn a grandchild or choose an exit code.

The contradictory-status regressions are mandatory:

1. Probe a fake on `PATH`, start from that stored probe, clear `PATH`, and
   assert Settings health, `AgentSessionV1.probe`, and the launched target all
   remain the same `AVAILABLE` path.
2. Configure a missing absolute path while a valid fake is on `PATH`; assert
   Settings and start both report the same `BLOCKED` probe and no process starts.
3. Change preferred shell among PowerShell, Command Prompt, Git Bash, and WSL;
   assert neither runtime probe nor launch path changes.
4. Unmount React and hide the window, admit one `READY` author task, resume the
   factory, and assert the background loop claims and launches it exactly once.
5. Seal that attempt into `EVALUATING`; assert a fresh read-only Codex reviewer
   is selected, while Hermes-only availability leaves the task queued with no
   process launch.

- [ ] **Step 1: Write failing fake-CLI end-to-end tests**

Use the Plan 01 fake sidecar, temporary repository/worktree root, and synthetic
tokens. Assert both author runtimes, explicit and `NEXT` paths, headless tray
continuation, fresh read-only reviewer behavior, profile clone, packet
auto-injection, redaction, bounded log, session controls, process-tree kill,
grant revocation, exact status, and no secret in serialized Tauri payloads.

- [ ] **Step 2: Run red on Windows**

```bash
cd apps/desktop/src-tauri
cargo test --features test-fixtures --test agent_execution_windows --test agent_dispatch_windows -- --test-threads=1
```

Expected: FAIL because commands, dispatcher, fixture binary, and Tauri
registration are unresolved.

- [ ] **Step 3: Register commands and replace only the no-op stop participant**

Manage one `Arc<RuntimeRegistry>` and one `Arc<AgentSessionManager>` in Tauri
state plus one `Arc<DispatchSupervisor>`. Project registry probes into Plan 02
`DesktopStatusV1.runtime_adapters`. Wire `AgentSessionManager` as
`RuntimeStopParticipant`; retain Plan 02's no-op implementation for its own
isolated tests. Start the supervisor from the native setup path after sidecar
readiness, never from a React effect.

- [ ] **Step 4: Run green on Windows**

```bash
cd apps/desktop/src-tauri
cargo test --features test-fixtures --test agent_execution_windows --test agent_dispatch_windows -- --test-threads=1
cargo test --all-targets --all-features
```

Expected: all fake Codex/Hermes and contradictory-status regressions pass.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src-tauri/Cargo.toml apps/desktop/src-tauri/Cargo.lock apps/desktop/src-tauri/src/bin/vesper-fake-agent.rs apps/desktop/src-tauri/src/agents/commands.rs apps/desktop/src-tauri/src/agents/dispatcher.rs apps/desktop/src-tauri/src/contracts.rs apps/desktop/src-tauri/src/runtime_boundary.rs apps/desktop/src-tauri/src/ipc.rs apps/desktop/src-tauri/src/lib.rs apps/desktop/src-tauri/tests/agent_execution_windows.rs apps/desktop/src-tauri/tests/agent_dispatch_windows.rs
git diff --check --cached
git commit -m "feat(desktop): expose truthful agent sessions"
```

### Task 10: Render Redacted xterm Streaming and Session Controls

**Files:**
- Modify: `apps/desktop/package.json`
- Modify: `apps/desktop/pnpm-lock.yaml`
- Modify: `apps/desktop/src/lib/desktop-api.ts`
- Create: `apps/desktop/src/features/runtime/agent-types.ts`
- Create: `apps/desktop/src/features/runtime/AgentExecutionPanel.tsx`
- Create: `apps/desktop/src/features/runtime/AgentExecutionPanel.test.tsx`
- Create: `apps/desktop/src/features/terminal/AgentTerminal.tsx`
- Create: `apps/desktop/src/features/terminal/AgentTerminal.test.tsx`
- Modify: `apps/desktop/src/features/runtime/runtime-surface.tsx`
- Create: `apps/desktop/src/features/settings/RuntimeSettingsPanel.tsx`
- Create: `apps/desktop/src/features/settings/RuntimeSettingsPanel.test.tsx`
- Modify: `apps/desktop/src/App.tsx`
- Modify: `apps/desktop/src/styles.css`

**Component props:**

```ts
export type AgentExecutionPanelProps = RuntimeSurfaceProps;

export interface AgentTerminalProps {
  session: AgentSessionV1 | null;
  readOnly: boolean;
  onSendInstruction(sessionId: SessionId, instruction: string): Promise<void>;
  onInterrupt(sessionId: SessionId): Promise<void>;
  onTerminate(sessionId: SessionId): Promise<void>;
  onResize(sessionId: SessionId, cols: number, rows: number): Promise<void>;
}
```

Extend the sole Plan 02 `desktopApi` object with typed wrappers for all Task 9
commands and two subscriptions:

```ts
terminalOutput: (handler: (value: TerminalChunkV1) => void) =>
  listen<TerminalChunkV1>("vesper://terminal-output", event => handler(event.payload)),
agentSession: (handler: (value: AgentSessionV1) => void) =>
  listen<AgentSessionV1>("vesper://agent-session", event => handler(event.payload)),
```

No feature module imports Tauri `invoke` or `listen`.

`AgentExecutionPanel` is the concrete `RuntimeSurface`. For a selected READY
task it offers Codex and Hermes using the registry-derived status and starts
with a UUID4 idempotency key. For an active session it renders
`AgentTerminal`. In read-only mode it disables all mutations but may display
the persisted redacted tail.

`AgentTerminal` creates `Terminal` plus `FitAddon`, writes only matching
monotonic chunks, requests `agent_terminal_tail` on mount and on a sequence
gap, reports fitted rows/columns, and disposes terminal, addon, observers, and
event listeners on unmount. The xterm surface is observation-only. A separate
form sends bounded instructions; explicit buttons perform Interrupt and
Terminate.

`RuntimeSettingsPanel` displays the exact `RuntimeProbe` fields and uses
`agent_probe` for **Test Codex** and **Test Hermes**. Hermes setup requires an
explicit confirmation control and source-profile value before invoking
`agent_provision_hermes_profile`.

- [ ] **Step 1: Write failing component and IPC tests**

Assert exact command names and argument shapes, runtime availability,
one-click start, no manual packet field, ordered chunks, gap-tail recovery,
FitAddon resize, instruction validation, interrupt/terminate confirmation,
read-only behavior, cleanup, Hermes confirmation, and identical path/version
in Settings and active session. Assert rendered output never contains the
synthetic secret.

- [ ] **Step 2: Run red**

```bash
cd apps/desktop
pnpm test --run src/features/runtime/AgentExecutionPanel.test.tsx src/features/terminal/AgentTerminal.test.tsx src/features/settings/RuntimeSettingsPanel.test.tsx
```

Expected: FAIL because agent panel, terminal, settings panel, and API methods are unresolved.

- [ ] **Step 3: Implement the typed runtime surface**

Pin:

```json
{
  "@xterm/xterm": "6.0.0",
  "@xterm/addon-fit": "0.11.0"
}
```

Pass `AgentExecutionPanel` where Plan 02 previously passed `NoRuntimeSurface`.
Do not add task-state logic, packet construction, token handling, or direct
sidecar HTTP to React.

- [ ] **Step 4: Run green**

```bash
cd apps/desktop
pnpm lint
pnpm test --run src/features/runtime/AgentExecutionPanel.test.tsx src/features/terminal/AgentTerminal.test.tsx src/features/settings/RuntimeSettingsPanel.test.tsx
pnpm build
```

Expected: lint and build exit `0`; all runtime, terminal, Settings, cleanup,
accessibility, and status-consistency tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/package.json apps/desktop/pnpm-lock.yaml apps/desktop/src/lib/desktop-api.ts apps/desktop/src/features/runtime apps/desktop/src/features/terminal apps/desktop/src/features/settings/RuntimeSettingsPanel.tsx apps/desktop/src/features/settings/RuntimeSettingsPanel.test.tsx apps/desktop/src/App.tsx apps/desktop/src/styles.css
git diff --check --cached
git commit -m "feat(desktop): stream agent sessions in xterm"
```

### Task 11: Prove the Windows M3 Acceptance Gate

**Files:**
- Create: `apps/desktop/src-tauri/tests/m3_agent_execution_windows.rs`
- Create: `apps/desktop/src/features/runtime/m3-agent-execution.test.tsx`

**Acceptance fixture:**

Run a table with Codex native, Codex `.cmd`, Hermes native, and Hermes `.cmd`.
For each author row: probe, claim explicit or `NEXT` work, prepare worktree,
launch, observe exact target/version, automatically receive one packet, emit
split synthetic credentials, send one instruction, resize, spawn a grandchild,
terminate or exit, report the authoritative session result, and confirm grant
revocation. Add a Codex reviewer row that attempts and fails to write, receives no
author conversation, submits one verdict evidence artifact, and exits. Assert
the canonical checkout is unchanged and the normal Hermes profile hash is
unchanged.

- [ ] **Step 1: Add the failing milestone tests**

The Rust test must fail if any secret appears in argv, debug/error strings,
events, bounded files, or serialized session DTOs; if the runtime status
disagrees with the launch; if packet count differs from one; if a descendant
survives termination; if a headless `READY` card is not claimed exactly once;
if Hermes receives a reviewer grant; if a reviewer write succeeds; or if exit
code `0` changes a task to `COMPLETED`.

The frontend test must render a selected task through Plan 02's real
`RuntimeSurface` boundary and verify start, stream, intervention, tail recovery,
read-only mode, and terminal exit. The Rust headless-dispatch assertions do not
mount the frontend.

- [ ] **Step 2: Run the milestone tests and verify red**

```bash
cd apps/desktop
pnpm test --run src/features/runtime/m3-agent-execution.test.tsx
cd src-tauri
cargo test --features test-fixtures --test m3_agent_execution_windows -- --test-threads=1
```

Expected: FAIL until the complete Plan 03 integration is wired.

- [ ] **Step 3: Make only integration corrections within the listed Plan 03 write set**

Correct contract wiring, teardown ordering, listener cleanup, or deterministic
fixture behavior exposed by the milestone tests. Do not add research,
evaluation, learning, packaging, or protected-path behavior.

- [ ] **Step 4: Run the full Plan 03 gate from Git Bash on Windows**

```bash
TMPROOT="$LOCALAPPDATA/Temp/v20-agent-plan03-$$"
mkdir -p "$TMPROOT"
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='' \
  TMPDIR="$TMPROOT" TEMP="$TMPROOT" TMP="$TMPROOT" \
  .venv/Scripts/python.exe -m pytest -q --basetemp="$TMPROOT/pytest"

cd apps/desktop
pnpm lint
pnpm test --run
pnpm build

cd src-tauri
cargo fmt --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test --all-targets --all-features -- --test-threads=1
```

Expected: the existing Python suite, all frontend checks, and all Rust checks
pass; M3's exact-path explicit/background launch, automatic packet, fresh
read-only reviewer, redacted PTY, process-tree, grant, worktree,
Hermes-profile, bounded-log, and contradictory-status assertions are green.

- [ ] **Step 5: Inspect scope and commit**

```bash
git diff --check
git status --short
git diff --stat
git diff -- apps/desktop
git add apps/desktop/src-tauri/tests/m3_agent_execution_windows.rs apps/desktop/src/features/runtime/m3-agent-execution.test.tsx
git diff --check --cached
git commit -m "test(desktop): prove agent execution milestone"
```

Expected scope: only the files named in this plan. Plan 03 is accepted when the
roadmap's M3 checkbox can be checked without relying on evaluation or learning
behavior.
