# Native redesign lineage-gap audit

Use when a Tkinter/native operator-console redesign is approved as visual mockups or image layouts and the task is to prove whether the current data model can support every proposed field without inventing truth.

## Evidence boundary

1. Freeze `HEAD`, dirty state, and relevant source mtimes before tracing.
2. Read governance and the current shipped runtime contract before historical design specs. Mark superseded specs as provenance only.
3. Inventory every dynamic field visible in the approved mockups. Separate static headings/navigation from data requirements.
4. Do not launch the application during a strict read-only audit until startup side effects are known. A nominally read-only UI may perform provider calls, update caches, initialize SQLite, or write telemetry during its first refresh.
5. If the full snapshot loader writes a cache or calls a provider, use pure/local sub-loaders and existing sanitized snapshots instead. State that the live UI was not launched and why.

## Trace from final writer backward

For each visible field, record:

`authoritative artifact/API -> parser/query -> service transformation -> dataclass/view field -> final StringVar/widget/text writer`

Start with every `StringVar.set`, widget insertion, and detail-text builder. Then inspect repeated writers and queue ordering. A field present in a dataclass but never read by the native renderer is **unavailable in the final UI**, not implemented.

Classify each field:

- **authoritative** — direct canonical ledger, database, approved artifact, or governance record;
- **derived** — deterministic projection with explicit inputs and rules;
- **advisory** — heuristic, activity hint, local observation, note, or non-admitted research result;
- **unavailable** — required by the redesign but absent from the final writer or current source.

## Cross-model contradiction checks

- Compare the exact governance fields consumed by parsers with later canonical summaries in the same document. A last-match parser can still consume stale truth when the canonical correction uses a different label or prose shape.
- Verify named System Spine domains use their named sources. Engineering activity is not Worker Runtime; provider account usage is not provider-ledger health; task assignment is not worker activity.
- Separate a rich model that is loaded from the model that is rendered. If a nine-stage workflow is loaded but the UI renders an older six-stage projection, report the richer fields as unwired.
- Treat missing registry/manifest/queue files as `UNAVAILABLE`, never as zero tasks, no issues, idle workers, or no pending decisions.
- When compact formatting shortens provider text, prove `STALE`, source scope, and observation time survive truncation. Suppress numeric capacity when the source is stale or unavailable.

## Mutation inventory

Audit persistence even for a display described as read-only:

- explicit task/comment/approval/issue controls;
- local provider-cache writes caused by refresh;
- startup initialization of databases or state files;
- append-only activity/receipt writers;
- upstream producers that are not UI mutations but feed the display.

Separate three scopes in the report:

1. mutations reachable from the current native UI;
2. mutations present only in maintenance/legacy sibling surfaces;
3. upstream service writers observed by the UI.

A control label must name its real mutation. If `APPROVE` calls task completion, classify it as task completion—not formal approval—even when both are governance-related.

## Redesign gap matrix

Group fields by operator domain rather than by source file:

- global posture and authority classes;
- workflow/current objective and dependency context;
- work items versus worker lifecycle;
- formal decisions versus task administration;
- learned facts versus action receipts;
- System Spine/world state/continuity;
- provider usage by scope;
- research queue, productive-run evidence, admission, and GPU freshness;
- issues;
- receipts and history;
- all mutations.

For each group, cite exact parser, dataclass, and final-writer line ranges; identify false-green, false-clear, and false-stale behavior; list the fields needed by the approved layouts.

## Recommended boundaries

Prefer explicit view models:

- `GlobalPostureVM`
- `WorkflowVM`
- `WorkGraphVM` plus a separate `WorkerRuntimeVM`
- `DecisionGateVM`
- `KnowledgeLedgerVM`
- `SystemSpineVM`
- `ProviderUsageVM`
- `ResearchOpsVM`
- `IssueVM`
- `HistoryVM`
- one exact command adapter for bounded mutations

Every major view-model value should carry source, scope, observed time, source-session time, age, state, and reason. Last-good retention must add a stale/error overlay rather than leave prior green values unchanged.

## Live-data reality check before implementation

Do not stop at source inspection. Run a bounded, sanitized, read-only probe over the actual adapters and summarize only counts, states, timestamps, IDs/titles needed for routing, and source posture. Never print secrets, task bodies, private session IDs, workspace paths, or raw provider payloads.

At minimum compare:

- nonterminal task rows versus current task runs, heartbeats, leases, and task-bound runtime events;
- task links versus the proposed objective/dependency graph;
- provider-ledger activity versus task-bound execution evidence;
- approval status versus `approval_granted` and `execution_authorized`;
- declared lanes/assignees versus current lifecycle evidence;
- current receipts/artifacts versus board completion state;
- system/world-state source presence and freshness.

This check often exposes the central trust gap: a board may contain active-looking rows after the underlying work was integrated, while current runtime evidence is empty. Report the contradiction and design for it; do not clean or reinterpret production state during a redesign audit.

## Evidence-backed workflow-card state resolution

Keep task inventory, worker metadata, and current activity separate. Resolve card state in fail-closed order:

1. malformed schema/timestamp or contradictory running evidence → `UNKNOWN`;
2. terminal board state plus required completion evidence → `COMPLETE` (otherwise completion remains unverified);
3. explicit review state/current review run → `REVIEW`;
4. blocked task plus exact, unexpired, current-scope pending human request → `HUMAN GATE`;
5. other blocked task → `BLOCKED`;
6. running task plus fresh task-bound run/heartbeat/lease → `PLANNING` or `WORKING` from the current step;
7. ready/todo/triage/assigned without fresh activity → `WAITING`;
8. anything else → `UNKNOWN`.

Never use assignee presence, lane ownership, historical `started_at`, an old provider event, or a declaration file as proof of current work. Provider events that are only worker/lane-bound may be contextual metadata but cannot prove a Kanban task is active.

If several active roots exist and none has fresh evidence, show all roots and state that there is no uniquely evidenced current objective. Do not pick one by title, creation time, or visual convenience. A deterministic default selection is allowed only after the evidence rule is explicit and tested.

## Decision projection

Project approvals into two surfaces:

- **Pending human decisions:** only unexpired `requested` records with exact action/scope binding.
- **Decision history:** approved, rejected, and expired attestations.

Always render `approval_granted` and `execution_authorized` independently. An `approved` attestation with both flags false is history, not a runnable action and not an awaiting-human item. A task button named `APPROVE` that actually completes/unblocks a board card belongs to task administration, not the formal decision ledger.

## Implementation-ready handoff artifact

Before production edits, write one bounded plan containing:

- mockup/page-to-production mapping;
- authoritative-source → parser/query → view model → final-writer matrix;
- source cadence, freshness rule, stable ID, and malformed/unavailable behavior;
- exact status-resolution order and contradiction tests;
- mutation inventory and retained authority denials;
- vertical tracer order: pure data/view model first, one end-to-end workflow page second, remaining pages afterward;
- a read-only smoke mode that loads every production adapter without creating a GUI or invoking mutations;
- real native-window launch, multi-page visual QA, and idle-soak verification.

The key sequence is **data/view model → one end-to-end tracer → remaining presentation**. Building all pages against placeholder dictionaries recreates the original trust gap and makes visual completion look like integration.
