# ADR-0001: Native LangGraph Agent Platform

- Status: Accepted
- Date: 2026-07-27
- Owner: V20 operator
- Decision scope: Target architecture only; implementation and dependency changes require a later authorized phase

## Context

V20 previously relied on a Hermes-oriented architecture for specialist identities, orchestration, memory, task state, and operator visibility. That strategy provided useful historical analysis, but it left authority and lifecycle behavior divided between V20 and a general-purpose external orchestrator.

V20 now needs one native control plane that owns specialist definitions, routing, deterministic validation, correction limits, receipts, long-term memory policy, persistence, and human approval boundaries. A successful specialist process or model response must never by itself constitute acceptance. Current repository evidence, tests, receipts, and source artifacts remain more authoritative than generated summaries or memories.

The initial architecture must remain local, resumable, and narrow. It must not require a separately billed OpenAI API key, a hosted tracing service, a cloud vector database, trading access, schedules, model promotion, or changes to portfolio and risk limits.

## Decision

V20 will replace the target Hermes-oriented runtime with a native platform built around LangGraph, the LangGraph Store abstraction, LangMem-compatible memory consolidation, the local OpenAI Codex SDK authenticated through the operator's ChatGPT account, and SQLite for initial local persistence. No Hermes runtime adapter will be built.

### Control graph

The first vertical workflow is:

```text
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

The Product supervisor is the graph owner. Development and Risk Review are independent specialist subgraphs. Deterministic validation is controller code, not a model judgment.

- A validation failure routes back to Development.
- A Risk Review rejection routes back to Development.
- The combined correction budget is at most three failed attempts for a workflow.
- A third failed attempt stops automatic correction and requires operator intervention.
- Risk approval does not finalize the task; it produces a real human-approval interrupt.
- Final acceptance occurs only after explicit operator approval.
- The controller, not a specialist or Codex thread, owns routing, validation, approval state, and acceptance.

### Persistence and evidence

SQLite is the initial local persistence boundary:

- A SQLite LangGraph checkpointer persists graph state, interrupts, correction counters, specialist thread references, and resumable execution state.
- Long-term records are accessed through the LangGraph Store abstraction. The implementation phase must select or implement a compatible local SQLite-backed store without introducing hosted infrastructure.
- LangMem-compatible consolidation operates only on validated memory candidates and writes through the Store boundary.
- Large or immutable evidence remains in a filesystem evidence store. SQLite stores identifiers, hashes, paths, verification state, and relationships rather than duplicating artifact bodies.

Checkpoint state, long-term memory, and authoritative filesystem evidence are separate concerns. A process interruption must be resumable from the checkpoint without treating an interrupted specialist call as successful.

### Specialist execution

V20 will expose a narrow adapter around the Python `openai-codex` SDK. The adapter will start and resume specialist threads, select an approved model, bind an explicit repository or worktree directory, enforce read-only or workspace-write sandbox modes, capture available streamed events and the final response, and emit typed receipts for timeout, cancellation, usage limits, permissions, and completion.

The adapter will use the operator's local ChatGPT-authenticated Codex session. It must not read, print, copy, persist, or place authentication material into prompts, receipts, memory, or source control. SDK authentication availability and exact API compatibility are implementation gates, not assumptions made by this ADR.

### Contracts and authority

The platform will define typed contracts for tasks, graph state, specialist receipts, deterministic validation, risk review, memory candidates, and operator approval. Filesystem and tool permissions are explicit inputs to specialist execution.

Initial specialist profiles are `v20-product`, `v20-development`, and `v20-risk-review`. Each owns a distinct memory namespace and permission set. Development cannot write Risk Review decision memory. Dynamic repository state is injected by the controller rather than embedded in profile prompts.

Memory consolidation is selective:

- only validated candidates may be stored;
- contradictory or superseded records remain traceable;
- receipts, repository state, tests, and source artifacts outrank generated memories;
- profile identity, `SOUL.md`, security policy, permissions, approval rules, and risk limits cannot be edited automatically.

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
- LangGraph, LangMem, and Codex SDK APIs and compatible versions must be resolved before implementation.
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
3. Verify local Codex SDK authentication without exposing credential material.
4. Resolve the existing import failure in `scripts.run_paper` and make the Tk dashboard test baseline reproducible.
5. Approve typed contracts, SQLite schemas and migration policy, filesystem evidence layout, and exact tool permissions.
6. Implement against fake Codex adapters first and keep real SDK coverage separately marked as a local integration test.

## References

- [Proposed evidence/history migration plan](../plans/evidence-history-migration-plan.md)
- [Repository architecture overview](../../architecture.txt)
- [Repository operating guidance](../../AGENTS.md)
