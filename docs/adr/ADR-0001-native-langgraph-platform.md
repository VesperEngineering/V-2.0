# ADR-0001: Native LangGraph Agent Platform

- Status: Accepted
- Date: 2026-07-27
- Owner: V20 operator
- Decision scope: Target architecture only; implementation and dependency changes require a later authorized phase
- Knowledge amendment: [ADR-0002](ADR-0002-obsidian-langgraph-knowledge.md)

## Context

V20 previously relied on a Hermes-oriented architecture for specialist identities, orchestration, memory, task state, and operator visibility. That strategy provided useful historical analysis, but it left authority and lifecycle behavior divided between V20 and a general-purpose external orchestrator.

V20 now needs one native control plane that owns specialist definitions, routing, deterministic validation, correction limits, receipts, long-term memory policy, persistence, and human approval boundaries. A successful specialist process or model response must never by itself constitute acceptance. Current repository evidence, tests, receipts, and source artifacts remain more authoritative than generated summaries or memories.

The initial architecture must remain local, resumable, and narrow. It must not require a separately billed OpenAI API key, a hosted tracing service, a cloud vector database, trading access, schedules, model promotion, or changes to portfolio and risk limits.

## Decision

V20 will replace the target Hermes-oriented runtime with a native platform built around LangGraph, the LangGraph Store abstraction, provider-neutral model-execution adapters, and SQLite for initial local persistence. Docker-isolated Codex is the first sandboxed runtime; OpenCode is an opt-in host subprocess adapter. Durable operator-authored knowledge is governed by ADR-0002. No Hermes runtime adapter will be built.

### Control graph

The first vertical workflow is:

```text
Controller Data Research
        |
        v
Controller Model Evaluation
        |
        v
Product supervisor
        |
        v
Development specialist
        |
        v
Deterministic validation
        |
        v
Risk Review specialist
        |
        v
Human approval interrupt
        |
        v
Final acceptance
```

LangGraph is the graph owner. Data Research, Model Evaluation, and deterministic validation are controller code, not model judgments. Product, Development, and Risk Review are independent specialist stages.

- Data Research always runs first through a read-only SQLite URI and emits only bounded aggregate coverage, null-count, date-bound, and split-adjustment evidence; raw bars never enter graph state or prompts.
- Its controller-owned Massive root is separate from the disposable specialist clone, opens SQLite with `mode=ro&immutable=1`, persists with the run, and must match on resume.
- Model Evaluation always runs second, hashes but never loads or executes the configured artifact, validates bounded companion metadata, and excludes model parameters and unrelated settings from evidence.
- Missing or malformed data, invalid bounded dates/metrics, unavailable model artifacts, and hash mismatches produce typed summaries and stop at operator intervention before Product.
- A validation failure routes back to Development.
- A Risk Review rejection routes back to Development.
- The combined correction budget is at most three failed attempts for a workflow.
- A third failed attempt stops automatic correction and requires operator intervention.
- Risk approval does not finalize the task; it produces a real human-approval interrupt.
- Final acceptance occurs only after explicit operator approval.
- Acceptance additionally requires available Data Research and a passing Model Evaluation; legacy checkpoints without these stages require a new run.
- The controller, not a specialist or model session, owns routing, validation, approval state, and acceptance.

### Persistence and evidence

SQLite is the initial local persistence boundary:

- A SQLite LangGraph checkpointer persists graph state, interrupts, correction counters, specialist thread references, and resumable execution state.
- Long-term records are accessed through a local SQLite-backed LangGraph Store abstraction without hosted infrastructure.
- Validated receipt-derived memory remains separate from the operator-authored Obsidian knowledge standardized in ADR-0002.
- Large or immutable evidence remains in a filesystem evidence store. SQLite stores identifiers, hashes, paths, verification state, and relationships rather than duplicating artifact bodies.
- Data Research and Model Evaluation evidence is revision-bound, included in Risk Review context, and required in the final human-approval evidence set.

Checkpoint state, long-term memory, and authoritative filesystem evidence are separate concerns. A process interruption must be resumable from the checkpoint without treating an interrupted specialist call as successful.

### Specialist execution

V20 will expose narrow, provider-neutral execution adapters. The first adapter invokes Codex only inside an already-provisioned Docker sandbox bound to the exact disposable standalone repository. It verifies the sandbox identity, OpenAI OAuth mode, disabled MCP gateway, exact model-provider network allowlist, implicit default-deny behavior, and Git control-plane integrity. It captures bounded process metadata and emits typed receipts for timeout, cancellation, usage limits, permissions, and completion. LangGraph remains the only workflow controller; no model runtime owns V20 state, memory, routing, evidence, or approval.

Docker Sandboxes brokers the operator's ChatGPT-authenticated OpenAI access without exposing the underlying token to V20 or the sandbox. Read-only requests retain Codex's inner read-only sandbox. Workspace-write requests use Codex's documented externally-sandboxed mode only after the Docker boundary passes preflight, because nested Bubblewrap cannot remount the Windows-backed workspace reliably. Each sandbox is uniquely provisioned for one specialist turn and force-removed after every outcome; a stopped guest is never reused because its disk state is not authoritative. The adapter must not read, print, copy, persist, or place authentication material into prompts, receipts, memory, or source control.

OpenCode may be used as an explicitly operator-selected host subprocess route when OS sandboxing is not required. `create` activates it only with an exact `provider/model`; the runtime, model, and optional credential environment-variable name persist with the run. Its adapter disables sharing, external plugins, and model-list fetching, isolates global and project configuration, and starts from a scrubbed environment. Product and Risk Review receive no tools. Development receives only repository-relative, workspace-scoped read/edit/write; shell, search, subagents, skills, web, and external paths remain denied. A caller may bind one environment variable name to a provider; only the selected provider's bound value crosses the process boundary, and a missing bound value fails before spawn. Providers available in pure mode may use OpenCode's local authentication without an environment binding; plugin-backed authentication remains unavailable while default plugins are disabled. Credential values must not enter commands, generated configuration, prompts, receipts, evidence, memory, or source control. The controller still owns deterministic validation, Risk Review routing, and persisted human approval.

Repository-root execution is a separate explicit OpenCode grant. It requires a clean standalone clone retaining origin provenance, no Git submodules, an `m2/` branch, and an operator-supplied root-workspace flag that persists with the run. The adapter and controller independently protect top-level and nested Git control data, controller state, environment files, agent and profile policy, configured trading and risk settings, model artifacts, and protected data. OpenCode's patch tool is disabled because its move operation does not authorize the destination independently; exact edit and write tools remain path-scoped. A newly created JSON sidecar is treated as transport residue only when its parsed content exactly equals the model's final response; other JSON remains a task change. Before dispatch, the controller stores a durable rollback image for the writable, non-secret workspace. Cancelled, timed-out, invalid, and crash-interrupted turns restore that image. Host turns record their OS process identity outside the clone, poll the durable cancellation signal, terminate their process tree on request or timeout, and clear active state only after confirmed exit. Windows turns run in a kill-on-close Job Object so controller failure terminates descendants; POSIX turns use a dedicated process group. Crash recovery compares the live identity before terminating an orphan and never trusts or reuses an ambiguous or stale PID.

### Contracts and authority

The platform will define typed contracts for tasks, graph state, specialist receipts, deterministic validation, risk review, memory candidates, and operator approval. Filesystem and tool permissions are explicit inputs to specialist execution.

Initial specialist profiles are `v20-product`, `v20-development`, and `v20-risk-review`. Each owns a distinct memory namespace and permission set. Development cannot write Risk Review decision memory. Dynamic repository state is injected by the controller rather than embedded in profile prompts.

Receipt-derived runtime memory remains selective:

- only validated candidates may be stored;
- contradictory or superseded records remain traceable;
- receipts, repository state, tests, and source artifacts outrank generated memories;
- profile identity, `SOUL.md`, security policy, permissions, approval rules, and risk limits cannot be edited automatically.

Operator-authored memories and procedures use the repository-local Obsidian-compatible Markdown vault, derived Store/FTS indexing, and immutable per-run snapshots defined by ADR-0002. Those notes are context, not validated evidence or new authority.

No graph node is authorized to contact Massive, a broker, or another external service; place paper or live orders; enable schedules; promote models; change portfolio or risk limits; deploy; merge; push; or rewrite Git history. Such actions remain outside this architecture phase and require separate authority where applicable.

### Operator surface

A local CLI will provide task submission, status, validation and review inspection, approval, rejection, cancellation, and resume operations. Human approval must be represented by a persisted interrupt and an explicit resume command, not by a prompt convention or a specialist's self-report.

## Superseded historical records

ADR-0001 supersedes the runtime recommendation or target-platform status in these records:

- [V20 Agent Platform Strategy](../../reports/agent_platform_strategy.md)
- [Platform Gap Authority Audit v1](../../reports/platform_gap_authority_audit_v1.md), for target-architecture conclusions only
- [Platform Gap Knowledge and Portability Contract v1](../../reports/platform_gap_knowledge_contract_v1.md)
- [Platform Gap Lifecycle and Receipt Contract v1](../../reports/platform_gap_lifecycle_contract_v1.md)
- `reports/platform_gap_lifecycle_contract_v1.json`, the unchanged structured companion to the lifecycle record

They remain in the repository as historical design and audit evidence. Their factual observations are not erased. Platform-neutral receipt, provenance, and authority concepts may be reused only when they are compatible with this ADR and revalidated against the native implementation.

## Consequences

Positive consequences:

- V20 has one explicit owner for lifecycle state and acceptance.
- Correction limits and approval boundaries become deterministic and testable.
- SQLite checkpoints allow local interruption and resume without cloud infrastructure.
- Specialist execution, memory, and risk-review isolation can be verified through typed contracts and receipts.
- Historical Hermes analysis remains available without constraining the target runtime.

Costs and risks:

- V20 assumes responsibility for orchestration, persistence migrations, memory hygiene, receipt integrity, and operator tooling that Hermes previously supplied.
- LangGraph, Docker Sandboxes, Codex, and OpenCode executable APIs and compatible versions must be resolved before their respective implementation phases.
- SQLite requires locking, backup, corruption recovery, schema migration, and concurrency tests.
- ChatGPT-account SDK authentication may be unavailable or may not support the required local boundary; implementation must stop rather than fall back to unapproved credentials.
- Deterministic validation can be incomplete if its inputs and evidence schemas are underspecified.

## Alternatives considered

- Retain Hermes as the V20 orchestrator: rejected because V20 would not own the complete authority, lifecycle, memory, and acceptance boundary.
- Build a Hermes adapter: rejected because Hermes is not part of the target runtime and an adapter would preserve the split control plane.
- Use Codex alone as the orchestrator: rejected because a specialist thread is not a durable deterministic graph, approval system, or evidence authority.
- Build a custom workflow engine without LangGraph: rejected because it would recreate checkpoint, interrupt, routing, and state-transition machinery before V20-specific behavior is validated.
- Use hosted tracing, hosted memory, or a cloud vector database: rejected for the initial platform because local persistence and bounded external authority are requirements.

## Implementation gates

This ADR does not authorize dependency installation or runtime integration. Before implementation begins:

1. Establish a reproducible `uv`/`pyproject.toml` dependency baseline without removing or downgrading critical packages.
2. Resolve and record compatible pinned versions, licenses, transitive changes, and security findings.
3. Verify the selected local model runtime's authentication without exposing credential material.
4. Resolve the existing import failure in `scripts.run_paper` and make the Tk dashboard test baseline reproducible.
5. Approve typed contracts, SQLite schemas and migration policy, filesystem evidence layout, and exact tool permissions.
6. Implement process adapters against deterministic fakes first and keep real provider coverage separately marked as a local integration test.

## References

- [Proposed evidence/history migration plan](../plans/evidence-history-migration-plan.md)
- [Obsidian and LangGraph knowledge standard](ADR-0002-obsidian-langgraph-knowledge.md)
- [Repository architecture overview](../../architecture.txt)
- [Repository operating guidance](../../AGENTS.md)
