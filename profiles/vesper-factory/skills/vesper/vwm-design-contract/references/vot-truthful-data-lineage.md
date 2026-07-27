# Truthful VOT Data-Lineage Gate

Use this gate after visual mockups are approved and before production Tkinter implementation begins. The objective is not to prove that a value can be rendered; it is to prove that the value means what its label claims.

## Required sequence

1. Freeze the canonical revision and unrelated dirty state.
2. Trace each visible field from authoritative source → parser/service → dataclass/view model → final Tk writer.
3. Classify each value:
   - **Authoritative** — canonical durable source or validated receipt.
   - **Derived** — deterministic projection whose inputs are named.
   - **Advisory** — activity, declarations, labels, or unvalidated observations.
   - **Unavailable** — no trustworthy final-writer plumbing yet.
4. Record source scope, observed time, source-session time, age, state, and failure behavior.
5. Run live read-only probes where possible. Do not launch a normal UI path if its “read” refresh writes caches or other persistent state.
6. Write pure view-model/state-resolution tests before page construction.
7. Build one end-to-end tracer (`source → view model → Workflow card`) before drawing all pages.
8. Report progress in three separate percentages/states: visual design, data/architecture contract, and production implementation. A complete plan is not production-code progress.

## Work-state rules

- Assignment, ownership, `todo`, `ready`, or a historical run never proves `WORKING`.
- `WORKING` requires fresh task-bound run/heartbeat evidence.
- Planning requires a fresh active planning/decomposition/staff step.
- A stale, malformed, future-dated, contradictory, or unbound running state is `UNKNOWN`.
- `HUMAN GATE` requires an exact current pending decision binding; historical approval/rejection is decision history.
- Completion without required result/receipt/verification is `UNVERIFIED`, not a trusted action receipt.
- When multiple roots exist without uniquely current evidence, show all and state that no unique objective is evidenced; never pick one arbitrarily.

## Source-label integrity

A panel name is a source contract:

- **Worker Runtime** reads Worker Runtime events/receipts—not engineering telemetry or task assignment.
- **Operator Activity** reads the bounded activity ledger—not engineering telemetry.
- **Provider Ledger** is distinct from account capacity/remaining budget.
- **VOT/Kanban** is an out-of-band board read model, not agentd evidence or execution authority.
- **Research** combines queue manifest, batch receipt, artifact, validator/admission binding, and GPU observation. `PASS no_queue` is `IDLE / NO-OP`, not productive health.
- **Issues** missing/unreadable is `ISSUES UNAVAILABLE`; unknown non-closed statuses stay visible.
- **Agentd** missing/malformed/stale is unavailable and unsafe for planning; no unrelated healthy domain may make it green.

## Provider-display boundary

A dashboard refresh should not perform hidden persistent writes.

- Keep provider collection/cache persistence outside the Tk aggregation path.
- Let VOT consume a bounded sanitized cache snapshot read-only.
- Preserve provider scope: OpenAI workspace/session, OpenRouter account, and Vesper-attributed local spend are different facts.
- If the cache is stale, either suppress the numeric capacity or render `STALE` inseparably with it. Never truncate away the stale marker.
- A refresh failure may retain last-good data, but every retained appbar/page value must inherit a visible stale/error overlay until fresh evidence arrives.

## Exact action semantics

Never use one label for several authority classes.

- `kanban_complete()` is **COMPLETE TASK**, not formal approval.
- Formal approval is an attestation unless authenticated identity and downstream authority exist; show literal `approval_granted` and `execution_authorized` fields.
- Comment, complete, reject/block, unblock, approve attestation, deploy, schedule, promote, and submit order are distinct actions.
- Ordinary validated report/artifact delivery may proceed autonomously inside scope.
- Capital/orders, risk, paid-provider spend, scheduler mutation, production/model promotion, secrets/permissions, and unclassified external effects require exact-scope human decisions.
- Validation and authority classification are separate. A revision returns to the relevant work packet/implementation stage, not merely a cosmetic re-validation loop.

## Knowledge and history

- Separate **LearnedFact** from **ActionReceipt**.
- Only typed, source-linked, validated facts enter accepted shared knowledge.
- Raw model text, runtime journals, stale observations, and task completion without evidence remain advisory/history.
- History should retain source pointers and continuity metadata (source state/reason, previous hash, entry hash, receipt binding) rather than flattening everything into timestamps or prose.

## Minimum adversarial tests

- assigned task does not become `WORKING`
- stale/future/malformed heartbeat becomes `UNKNOWN`
- old approved attestation is not pending and never authorizes execution
- missing issue registry is unavailable
- unknown issue status remains visible
- missing/malformed research input is unavailable, not zero/idle
- no-op research receipt is not productive success
- artifact mtime/raw `VALIDATED` does not imply admission
- named System Spine domains consume their named readers
- provider UI reader performs zero network collection and zero filesystem writes
- failed refresh marks every retained appbar/page field stale
- `kanban_complete()` has no ambiguous `APPROVE` UI label
- unchanged signatures do not rebuild card widgets or reset selection/scroll
