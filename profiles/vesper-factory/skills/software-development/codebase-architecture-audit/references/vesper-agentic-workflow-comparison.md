# Vesper Agentic Workflow Comparison — Evidence Model

Use this reference when a user asks whether a Vesper version, roadmap milestone, or architecture diagram is "doing this now." It captures the durable audit pattern, not a frozen status claim.

## Core distinction

Vesper can expose two different orchestration systems at once:

1. **Hermes Kanban workforce** — goals, decomposition, linked cards, worker profiles, worktrees, leases, runs, reviews, comments, and handoffs.
2. **Vesper resident runtime (`vesper-agentd`)** — repository-owned report-only runtime, local state, worker-runtime receipt contracts, world-state observation, and VOT display.

Never merge these into one capability claim. The Hermes board can be operational while resident agentd remains fixture-only, unscheduled, non-planning, or disconnected from Kanban.

## Six-stage comparison matrix

For diagrams shaped as:

```text
user goal
→ orchestrator
→ work packets
→ agents execute
→ validate/revise
→ approve
→ deliver/deploy/schedule
→ shared memory for next cycle
```

classify each stage independently:

| Stage | Required evidence |
|---|---|
| User goal/task | live Kanban goal/card or authenticated request intake |
| Orchestrator | reachable coordinator handler that loads current context, constraints, tools, and authority |
| Work packets | durable child tasks/links with bounded scope, owner, dependency, budget, and acceptance evidence |
| Agent execution | task run plus worker identity, provider request or process launch, artifact, and terminal state |
| Validation/revision | exact test/validator result, independent reviewer, blocked/rework edge, and immutable candidate binding |
| Human approval | exact-scope decision with actor and expiry; separately prove whether any execution handler consumes it |
| Delivery/deploy/schedule | concrete side effect and idempotent receipt; a recorded approval or completed review is not delivery |
| Shared memory | a current writer and reader used by the next cycle; a stale file or display-only continuity history is not adaptive planning memory |

Answer with `YES`, `PARTIAL`, `NO`, or `PRESENT BUT NON-AUTHORIZING` for every row. Avoid one blended percentage.

## Version truth

Before accepting a label such as V3.6:

1. Search canonical source, roadmap, board titles/bodies, and user-facing version constants separately.
2. Determine whether the label is a product release, architecture milestone, design-only proposal, compatibility name, or unintegrated worktree scope.
3. Quote the milestone's explicit allowed and prohibited behavior.
4. Check for a live card or canonical commit implementing that exact milestone.
5. Check runtime evidence: process/service, scheduled job, fresh heartbeat/receipt, state database, task ledger, and real transport.

A completed V3.1–V3.5 test suite does not prove V3.6 exists. A VOT semantic version can also differ from an architecture roadmap version.

## Live-runtime proof order

Use this order so repository intent cannot masquerade as operation:

1. Canonical governance and roadmap definition.
2. Canonical implementation and reachable callers.
3. Launcher transport: fixture-only versus real provider/process adapter.
4. Installed scheduler/service/process.
5. Fresh status receipt and durable state.
6. Live Kanban board/task-run evidence.
7. Artifact/provider/review receipts.
8. Actual delivery side effect.

Missing runtime artifacts plus no installed launcher means "implemented/tested but not currently running," not "active."

## Shared-memory classification

Inventory each store independently:

- Kanban tasks, comments, events, runs, links, and handoffs
- worker task ledger
- provider request ledger
- team memory / accepted knowledge
- operator activity
- agentd world-state continuity history
- approval and execution ledgers

For each store record:

```text
writer
reader
freshness
integrity/bounds
whether next-cycle selection consumes it
whether it carries authority
```

A continuity history may be legitimate memory for observation while deliberately `safe_for_planning=false`. Call it observation memory, not a learning/planning loop. Team memory that is no longer fresh or has no active reader is retained history, not current shared intelligence.

## Approval semantics

Distinguish:

```text
request recorded
→ decision recorded
→ approval granted/authenticated
→ execution authorized
→ side effect performed
→ execution receipt validated
```

If the approval service deliberately throws before execution, report `PRESENT BUT NON-AUTHORIZING`. This is a valid fail-closed design, but it does not satisfy a diagram's deploy/deliver box.

## Fast Vesper source map

Check current equivalents rather than assuming paths are unchanged:

- active board/current truth: `PROJECT_ADVANCEMENT.md`
- repo authority: `AGENTS.md`
- lane/process manifests: `app/services/lane_manifest.py`, `app/services/autonomy_manifest.py`
- workforce design/status caveat: `docs/WORKFORCE_OPERATING_MODEL.md`
- resident loop: `app/services/vesper_agentd.py`
- worker runtime: `app/services/worker_runtime.py`
- fixture launchers: `scripts/run_worker_runtime.py`, `scripts/run_vesper_agentd.py`
- world-state safety: `app/services/world_state.py`
- continuity history: `app/services/agentd_continuity_history.py`
- VOT approval semantics: `app/services/vot_approval_workflow.py`
- live external orchestration: Hermes Kanban DB/CLI and scheduler inventory

## Reporting pattern

Lead with the distinction:

> **Partially overall, but not as one integrated resident loop.**

Then provide the stage matrix, name which system supplies each implemented stage, identify the exact missing bridge, and give one recommendation. For Vesper, default to a human-reviewed proposal bridge before granting resident agentd task creation, dispatch, provider, scheduler, or execution authority.
