# Bounded Agent Autonomy and Daily Journals

- Status: Approved design
- Date: 2026-08-02
- Owner: V20 operator
- Scope: Agent initiative, proposal routing, per-agent journals, and post-market review

## Goal

Let every V20 agent identify opportunities and propose work without giving any
agent unrestricted authority. Preserve a complete, human-readable journal for
each agent and require a hybrid operator review after every trading session.

The review is an accountability and next-session control. It is not a delayed
substitute for approvals that must happen before protected work begins.

## Current and target agents

The current platform has three native specialist agents:

1. `v20-product` turns admitted work into a bounded implementation brief.
2. `v20-development` is the only agent that may edit its controller-granted
   workspace.
3. `v20-risk-review` independently reviews evidence and protected boundaries.

The target core quant team adds five proposed agents:

4. `v20-quant-research-lead` frames hypotheses and routes research work.
5. `v20-model-research` evaluates model and feature ideas in research-only scope.
6. `v20-independent-quant-validation` independently challenges research claims.
7. `v20-portfolio-research` studies construction, exposures, and allocation ideas
   without changing live limits or capital.
8. `v20-execution-performance` analyzes fills, costs, slippage, and operational
   performance without order authority.

The five proposed roles are target architecture, not current implementation.
The controller, validation services, trading engine, and daily review compiler
remain deterministic services rather than additional agents.

The controller maintains the fixed eight-role roster with an explicit status for
each role: `active`, `disabled`, or `not_implemented`. A role that does not yet run
still appears truthfully in the daily digest with its status and no activity.

## Architecture

```mermaid
flowchart TD
    A["Eight agent roles"] --> P["Typed proposals and journal events"]
    P --> G{"Controller authority gate"}
    G -->|"Safe local work"| W["Product to Development to Validation"]
    G -->|"Protected work"| H["Immediate operator decision"]
    G -->|"Disallowed"| X["Reject and record"]
    W --> Q["Quant validation and Risk Review"]
    Q --> F["Final operator acceptance"]
    P --> J["Eight append-only journals"]
    G --> J
    W --> J
    Q --> J
    H --> J
    F --> J
    X --> J
    J --> C["Post-market review compiler"]
    C --> D["Daily digest with eight agent sections"]
    D --> R{"Operator review"}
    R -->|"Review receipt"| J
    R -->|"Approved distilled lesson"| K["Knowledge inbox"]
    K -.->|"Approved context only"| A
```

Every proposal enters through the controller. An agent cannot act directly on
its own proposal, change its authority, validate itself, or approve its outcome.

## Bounded initiative

Every agent may autonomously:

- record an evidence-backed observation;
- suggest a code, test, documentation, research, or process change;
- identify a contradiction, defect, data-quality issue, or missed opportunity;
- request routing to another agent or deterministic service; and
- recommend that an item be rejected, deferred, or escalated.

The controller assigns one of three authority classes:

### Safe local

Read-only analysis or a narrow reversible proposal involving local code,
documentation, or tests may enter the Product and Development workflow without
advance operator approval. Development alone receives a bounded write workspace.
Deterministic validation, independent review, and final operator acceptance still
apply.

### Protected

Broker, order, position, account, credential, provider, risk-limit, trading
parameter, capital-allocation, live-deployment, scheduler, paid-compute,
model-training, model-promotion, active-artifact, protected-data-write, or
destructive proposals stop for immediate operator approval. The daily review
cannot retroactively authorize them.

### Disallowed

Proposals outside policy, lacking required evidence, containing prohibited data,
or attempting to bypass a gate are rejected and journaled. No fallback route may
weaken the boundary.

## Proposal contract

An agent submits a typed `AgentProposal` containing:

- stable proposal, run, task, and agent identifiers;
- trading-session date and UTC creation time;
- concise title and rationale summary;
- proposal category and requested route;
- evidence references and immutable hashes;
- affected files or systems;
- expected benefit and bounded downside;
- requested authority class;
- validation required for acceptance; and
- dependencies, conflicts, and expiration time when applicable.

The rationale is a concise decision explanation, not private chain-of-thought.
Raw prompts, hidden reasoning, credentials, secrets, and raw protected market
data are prohibited.

## Per-agent journal

Each of the eight roles has a separate controller-owned `AgentJournal`. An agent
may propose events, but it cannot create, replace, or delete persisted records
directly.

Meaningful events use these types:

- `observation`
- `proposal_submitted`
- `route_decided`
- `work_started`
- `action_completed`
- `validation_result`
- `blocked`
- `deferred`
- `rejected`
- `operator_decision`
- `correction`

Every `JournalEvent` records:

- event ID, event type, agent, session date, and UTC time;
- related proposal, run, task, and prior-event IDs;
- concise summary and rationale summary;
- evidence references and hashes;
- requested and granted authority;
- route, status, outcome, and next action;
- affected files or systems; and
- previous-event hash and current-event hash.

The controller writes events to a role-scoped LangGraph Store namespace using
unique IDs and no update operation. Hash chaining makes later alteration
detectable. A correction is a new event pointing to the incorrect event.

The existing specialist-turn journal and immutable evidence mechanisms should be
extended rather than replaced. The daily human-readable report is a derived view;
it is not a second canonical ledger.

Journal events capture decisions and outcomes, not token traces or every tool
call. Prohibited content is rejected before persistence. A safe metadata-only
failure event records that rejection without retaining the prohibited value.

## Post-market review bundle

After the official exchange close plus a configured delay, a deterministic
compiler seals one review bundle for the trading-session date. It must use the
exchange calendar, including early-close sessions, rather than assume a fixed
clock time.

The bundle contains:

- one firm-level summary;
- one section for every agent, including explicit `no activity` sections;
- proposals opened, routed, accepted, rejected, blocked, or deferred;
- code and files changed, with diff and test evidence references;
- research claims and independent challenges;
- protected requests awaiting decisions;
- failures, contradictions, corrections, and unresolved items;
- carryover work eligible to continue next session;
- new proposals held by the hybrid review gate; and
- ordered journal hashes and a bundle hash.

The canonical records remain structured. The compiler exports a readable Markdown
digest and machine-readable JSON receipt. Re-running it over unchanged events is
idempotent and produces the same content hash.

## Hybrid review gate

The gate uses these exact rules:

1. Previously admitted work may continue next session only within its unchanged
   proposal scope and granted authority.
2. Deterministic validation and review may continue for that admitted work.
3. Agents may keep observing and journaling while review is pending.
4. A new autonomous proposal is recorded but cannot be admitted to Product,
   Development, or research execution until the prior session has an operator
   review receipt.
5. One operator acknowledgment of the complete digest opens the next-session
   safe-proposal gate. It does not approve any individual unresolved or protected
   item.
6. Rejection, evidence requests, and deferrals remain attached to their individual
   proposals until explicitly resolved.
7. Protected work always requires its own immediate approval before work begins.
8. The gate checks every completed exchange session since the last review, not
   weekends or market holidays. All sealed digests in that backlog must be
   acknowledged before new autonomous proposals are admitted.
9. Initial enablement requires a one-time operator bootstrap receipt. The system
   cannot invent a prior review or silently begin with an open gate.

If the digest is missing, corrupt, incomplete, or unsealed, the new-proposal gate
fails closed. This pauses new autonomous agent work only. It must not stop or alter
the trading engine, order controls, risk enforcement, or operator-initiated work.

## Operator review actions

The operator may:

- acknowledge the complete digest;
- approve, reject, defer, or request evidence for an individual proposal;
- allow or cancel eligible carryover work;
- add a correction or note without rewriting history; and
- approve a distilled lesson for the governed knowledge inbox.

Each action creates an append-only `OperatorReviewReceipt` with the digest hash,
decision, timestamp, affected proposal IDs, and resulting gate state.

Operational journals never become durable knowledge automatically. Only a stable,
distilled lesson explicitly approved by the operator may enter `knowledge/inbox/`.
It still follows normal knowledge review and cannot become runtime authority.

## Failure and recovery

- Duplicate event IDs or a broken hash chain fail before a write is accepted.
- Replayed events are idempotent when their complete canonical payload matches.
- A replay with different content is rejected as an integrity failure.
- Journal persistence failure prevents the related proposal transition.
- Digest compilation failure leaves the prior sealed digest unchanged and closes
  the next-session new-proposal gate.
- Missing agent activity produces a `no activity` section, not a missing section.
- Resume reuses persisted proposal authority and cannot silently widen scope.
- An unavailable agent cannot be replaced by another role with broader authority.
- Logs and diagnostics redact prohibited values before persistence or display.
- Trading execution remains operationally separate from journal review failures.

## Operator surface

The first operator surface should be CLI-first and read-only by default:

- list agent activity for a session;
- render or verify a sealed daily digest;
- inspect one agent, proposal, or hash chain;
- record a digest acknowledgment;
- record an item decision or evidence request; and
- show whether the next-session safe-proposal gate is open.

A dashboard may later render the same contracts. It must not introduce a second
decision store or bypass controller validation.

No scheduled job is activated by this design. Scheduling the post-market compiler
is a separate operator approval because scheduler changes are protected.

## Testing

Focused offline tests must prove:

1. strict proposal, journal-event, digest, and review-receipt schemas;
2. role isolation and controller-only writes;
3. append-only behavior, correction linkage, hash-chain verification, and replay
   idempotency;
4. safe, protected, and disallowed routing without authority escalation;
5. Development-only workspace writes and independent validation;
6. deterministic digest ordering, all eight sections, `no activity`, and stable
   hashes;
7. exchange-calendar handling for ordinary and early-close sessions;
8. hybrid gating for carryover, new proposals, acknowledgment, and unresolved
   protected items;
9. fail-closed behavior for missing or corrupt journals and digests;
10. secret and prohibited-content rejection without value retention;
11. separation between journals, runtime memory, durable knowledge, and trading
    authority; and
12. no effect on trading-engine availability or controls when review is pending.

## Initial implementation boundary

The first implementation should add the shared contracts, controller-owned
journal service, proposal router, deterministic digest compiler, hybrid review
gate, CLI review surface, and focused tests. It should connect the three existing
native specialists and expose the same registration boundary for the five future
roles.

Building the five proposed agents, activating a post-market schedule, adding a
dashboard, changing trading or risk behavior, training or promoting models, and
granting broker or provider access are outside this implementation.

## Acceptance criteria

- Every registered agent has an isolated, append-only, tamper-evident journal.
- Every proposal is evidence-backed, classified, routed, and journaled by the
  controller before work begins.
- Only Development may write, and only inside an exact granted workspace.
- Protected work cannot start through the safe route or daily review.
- Every trading session produces a sealed digest with a section for all eight
  target roles and a truthful active, disabled, or not-implemented status.
- Previously admitted work may continue while new autonomous proposals wait for
  the prior digest review.
- Digest acknowledgment opens only the safe-proposal gate and grants no protected
  authority.
- Corrections and operator decisions add records without rewriting history.
- Only explicitly approved distilled lessons may enter the governed knowledge
  inbox.
- Journal or review failure cannot alter trading, risk, broker, or order behavior.

## Source alignment

- `vesper/platform/composition.py` for existing specialist-turn journaling and
  controller-mediated specialist execution.
- `vesper/platform/contracts.py` for strict typed boundary contracts.
- `vesper/platform/evidence.py` and `vesper/platform/persistence.py` for immutable
  evidence and Store-backed state.
- `vesper/platform/workflow.py` for correction loops and human acceptance.
- `knowledge/skills/knowledge-governance.md` for durable knowledge admission.
- `vesper/data/calendar.py` for exchange-session semantics.
- `vesper/audit/logger.py` remains the trading audit facility and is not replaced
  by agent journals.
