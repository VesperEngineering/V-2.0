# V20 Complete Agent Platform Diagram Design

Date: 2026-07-29
Status: Approved for specification

## Objective

Create a polished, repo-grounded PDF that explains the complete native V20 agent
platform at two levels: one master architecture poster and four readable subsystem
diagrams. The document must distinguish actual LangGraph runtime nodes, native
specialist profiles, deterministic controller services, operator authority, and
persistence systems.

## Scope

The diagram covers the native agent platform implemented under `vesper/platform/`,
the approved profiles under `profiles/native/`, the operator knowledge system, and
the runtime interfaces described by ADR-0001 and ADR-0002.

Quant strategies, model internals, broker integration, trading execution, portfolio
construction, and risk-limit logic are outside the diagram except where they appear
as protected external boundaries.

## Source of Truth

The PDF must be derived from the live checkout, with priority given to:

1. `vesper/platform/workflow.py` for nodes and conditional edges.
2. `vesper/platform/service.py` and `vesper/platform/cli.py` for the operator surface.
3. `vesper/platform/composition.py` and the native profiles for specialist execution.
4. `vesper/platform/persistence.py`, `evidence.py`, `memory.py`, and `knowledge.py`
   for state, evidence, and context boundaries.
5. ADR-0001 and ADR-0002 for accepted architectural intent.
6. Focused platform tests for failure, recovery, authority, and correction behavior.

Generated text must not claim behavior that is only proposed or historical.

## Deliverable

Write one PDF to `output/pdf/v20-complete-agent-platform.pdf` with five pages.
All diagrams use vector lines, shapes, and text so the document remains sharp when
zoomed on a phone or printed.

### Page 1 - Master Architecture Poster

- Size: 17 by 11 inches, landscape.
- Show five horizontal ownership layers:
  - operator and CLI;
  - controller and service composition;
  - LangGraph runtime;
  - specialists, deterministic gates, and execution adapters;
  - persistence, evidence, memory, and knowledge.
- Show the primary request-to-acceptance path.
- Show approval and correction paths without duplicating the detailed lifecycle.
- Mark protected external systems such as Massive data, credentials, brokers,
  schedules, deployment, and trading controls as outside automatic authority.
- Add numbered references to pages 2 through 5.

### Page 2 - Runtime Lifecycle

- Size: 11 by 8.5 inches, landscape.
- Show the exact seven runtime nodes:
  `data_research`, `model_evaluation`, `product`, `development`, `validation`,
  `risk_review`, and `human_approval`.
- Identify Data Research, Model Evaluation, and Validation as controller-owned,
  deterministic services.
- Identify Product, Development, and Risk Review as the three native specialist
  stages.
- Show the validation-to-development and risk-review-to-development correction
  loops.
- Show the shared maximum of three failed correction attempts.
- Show integrity failures, holds, infrastructure failures, rejection, cancellation,
  operator intervention, acceptance, and other terminal outcomes accurately.
- Make clear that Risk Review approval leads to human approval, not acceptance.

### Page 3 - Specialists and Execution Boundaries

- Show `v20-product`, `v20-development`, and `v20-risk-review` as independent
  profiles with distinct inputs, outputs, permissions, and memory namespaces.
- Product and Risk Review are read-only. Development receives only the exact
  controller-granted workspace.
- Show structured contracts and evidence-backed receipts at every specialist
  boundary.
- Show Docker Codex as the sandboxed default adapter and OpenCode as the explicit
  operator-selected host route.
- Show disposable worktree checks, protected paths, default-deny network behavior,
  bounded tools, cancellation, timeout, process cleanup, and rollback ownership.
- State that specialists cannot validate themselves, approve operator authority,
  or declare final acceptance.

### Page 4 - Persistence, Evidence, Memory, and Knowledge

- Separate the following authority domains visually:
  - SQLite LangGraph checkpoints for resumable graph state and interrupts;
  - SQLite LangGraph Store for typed workflow records and role-scoped memory;
  - immutable hash-verified filesystem evidence;
  - canonical operator-authored Markdown under `knowledge/`;
  - derived SQLite FTS5 knowledge index;
  - immutable per-run `KnowledgeContext` snapshots;
  - small controller-owned control records.
- Show receipt-derived memory as validated, typed, append-only, provenance-bound,
  and separate from operator-authored knowledge.
- Show that approved Markdown is canonical while Store and FTS are derived.
- Show that specialist prompts receive bounded context snapshots, not live vault
  access.
- Show evidence and repository state outranking generated memory or summaries.

### Page 5 - Operator Surface and Authority

- Show the CLI command families: create, status, resume, receipts, evidence,
  approvals, active, approve, reject, cancel, knowledge-sync, knowledge-search,
  and knowledge-status.
- Show the controller-owned transitions behind create, resume, approval, rejection,
  cancellation, and recovery.
- Show explicit operator approval boundaries for credentials and accounts, broker
  or provider actions, trading and risk changes, schedules, paid compute, model
  training or promotion, deployment, protected-data writes, and destructive work.
- Show permitted local actions: inspection, tests, documentation, narrow reversible
  fixes, read-only research, and read-only pipeline work.
- End with the final acceptance predicate: passing research integrity, completed
  development receipt, deterministic validation pass, Risk Review approval, stable
  workspace evidence, persisted matching operator decision, and explicit resume.
- Include a compact source-file legend.

## Visual System

- Technical schematic style with high contrast and restrained color.
- Dark blue denotes controller-owned flow.
- Green denotes verified success or accepted state.
- Amber denotes operator decisions, interrupts, or wait states.
- Red denotes rejection, failed integrity, or terminal intervention.
- Purple denotes native specialist execution.
- Gray denotes storage, context, or protected external systems.
- Color is always paired with labels, line patterns, or node shapes.
- Runtime nodes use rounded rectangles; decisions use diamonds; stores use cylinders;
  external boundaries use dashed containers; terminal states use double outlines.
- Use short labels inside shapes and place explanatory text in adjacent notes.
- Use page headers, page numbers, and a consistent legend on all pages.

## Layout and Accessibility

- Minimum body text size is 8 points on the poster and 9 points on detail pages.
- Avoid rotated text, overlapping connectors, crossing labels, and color-only meaning.
- Use orthogonal connectors and arrowheads that remain unambiguous at phone zoom.
- Use ASCII hyphens and standard embedded fonts.
- Include PDF metadata title and subject.

## Failure and Recovery Representation

The diagrams must distinguish corrections from terminal failure. Validation failure
and Risk Review rejection may return to Development within the shared correction
budget. Integrity failure, Risk Review hold, exhausted corrections, invalid authority,
missing persisted approval, cancellation, or unreconciled runtime state stop or
require operator intervention. An interrupted run resumes from persisted checkpoint
state; interruption is never treated as successful specialist completion.

## Verification

Before delivery:

1. Reconfirm runtime node and edge names against `workflow.py`.
2. Reconfirm CLI commands against `cli.py`.
3. Reconfirm profile permissions against all three native `profile.yaml` files.
4. Extract text from the PDF and confirm every page title and required node name.
5. Render every page to PNG with Poppler.
6. Inspect every rendered page for clipping, overlap, unreadable text, broken arrows,
   missing legends, and incorrect color or shape mappings.
7. Confirm the final PDF has five pages and opens without parser errors.
8. Confirm only the intended specification and PDF artifacts were created or changed.

## Acceptance Criteria

- The PDF contains one complete poster and four detailed diagrams.
- All seven runtime nodes and all conditional paths are represented accurately.
- The three specialist profiles are clearly distinguished from deterministic services.
- Persistence, evidence, runtime memory, and operator knowledge remain visibly
  separate authority domains.
- Operator approval cannot be mistaken for Risk Review or model self-approval.
- The document is legible on a phone at zoom and on its intended print sizes.
- Every substantive architecture claim can be traced to a live repository source.
