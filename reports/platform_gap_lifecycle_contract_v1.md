# V20 platform-gap lifecycle and receipt contract v1

> **Status: Superseded by ADR-0001.** See [ADR-0001: Native LangGraph Agent Platform](../docs/adr/ADR-0001-native-langgraph-platform.md). This file and its JSON companion are preserved as historical design records; ADR-0001 now governs the target runtime architecture.

**Decision owner:** Brennan  
**Scope:** proposed, platform-neutral contract for G4 deterministic lifecycle control and G8 scheduler/task receipts. This document is a design contract only. It does not alter Hermes, Kanban, schedules, source/configuration, data, models, providers, risk, broker, or execution state.

## 1. Status, evidence, and terms

**Current evidence.** `reports/agent_platform_strategy.md:203-216` records G4 as only partly represented by Kanban dependencies and states that the deterministic controller is not implemented. Lines 245-252 record G8 as partial and recommend immutable task IDs, run locks, one lease per worker, atomic state transitions where available, and explicit interrupted/ambiguous receipts. The live V20 board has immutable-looking task IDs; `tasks`, `task_events`, `task_runs`, and `task_links`; claim locks with expiries; heartbeat events; dependency links; and observed run outcomes `completed` and `blocked`. These are evidence of existing primitives, not proof of exactly-once execution or a deterministic lifecycle.

**Design assumption / new requirement.** This contract defines a small controller above any platform adapter. A platform may supply storage and dispatch, but it may not skip or reinterpret the stage guards below.

Terms:

- **workflow:** one admitted V20 work item, identified permanently by `workflow_id`.
- **stage:** one member of the fixed ordered sequence below.
- **attempt:** one immutable execution claim for one `(workflow_id, stage, role_id)`.
- **receipt:** an append-only, immutable record of an attempt or transition.
- **authoritative receipt:** a receipt whose required hashes, evidence references, and guard result are present; a message alone is never authoritative.
- **ambiguous:** the controller cannot prove whether an external or durable effect occurred. It is not a successful completion.

Every field proposed below is tagged **[E]** when backed by the observed V20 strategy/board/manifests or **[N]** when it is a new requirement. Tags do not claim implementation.

## 2. Fixed lifecycle

```text
ADMISSION -> CONTRACT -> IMPLEMENT -> TRAIN -> BACKTEST -> REVIEW -> NEXT
```

| Stage | Proposed accountable role [N] | Entry guard | Exit guard | Failure/stop result |
|---|---|---|---|---|
| `ADMISSION` | Product | Immutable `workflow_id` exists [N]; originating Brennan instruction or already-admitted V20 task contract is referenced [E/N]; requested authority is classified [N]. | Scope, owner, dependencies, evidence location, acceptance criteria, and stop condition are recorded; any denied-authority item has Brennan’s exact-scope approval reference before it becomes runnable [E/N]. | `BLOCKED` for missing authority/evidence; `REJECTED` for out-of-scope work [N]. |
| `CONTRACT` | Quant Research | Authoritative ADMISSION receipt says `VERIFIED` [N]. | A frozen, testable contract binds hypothesis/scope, inputs, clocks, metrics, acceptance criteria, stop conditions, and required evidence [N]. | `BLOCKED` or `FAILED`; no implementation, training, or backtest may start [N]. |
| `IMPLEMENT` | Development | Authoritative CONTRACT receipt says `VERIFIED` [N]. | Required implementation evidence and verification receipt meet the frozen contract; any required review gate is recorded [N]. | `BLOCKED`, `FAILED`, `INTERRUPTED`, or `AMBIGUOUS`; TRAIN is prohibited [N]. |
| `TRAIN` | ML Systems | Authoritative IMPLEMENT receipt says `VERIFIED`; a contract explicitly authorizes a research-only training action [N]. | Frozen inputs, code/environment identity, execution bounds, and outputs are receipted; no model promotion is implied [E/N]. | `BLOCKED`, `FAILED`, `INTERRUPTED`, or `AMBIGUOUS`; BACKTEST is prohibited [N]. |
| `BACKTEST` | Portfolio Research | Authoritative TRAIN receipt says `VERIFIED`, or the sealed contract explicitly specifies a no-training evaluation [N]. | Contract-bound inputs, costs, outputs, and integrity checks are receipted [N]. | `BLOCKED`, `FAILED`, `INTERRUPTED`, or `AMBIGUOUS`; REVIEW is prohibited [N]. |
| `REVIEW` | Risk Review | Authoritative BACKTEST receipt says `VERIFIED` [N]. | Independent verdict and the exact evidence considered are receipted; the reviewer does not implement or self-authorize its own finding [E/N]. | `BLOCKED`, `FAILED`, `INCONCLUSIVE`, `INTERRUPTED`, or `AMBIGUOUS`; no advance occurs [N]. |
| `NEXT` | Product | Authoritative REVIEW receipt has a recorded verdict [N]. | A decision is one of `STOP`, `CLOSE`, `REQUEST_NEW_ADMISSION`, or `HUMAN_APPROVAL_REQUIRED`; any follow-on work receives a new immutable workflow identity [N]. | No automatic recurrence, scheduling, deployment, promotion, or capital action [E/N]. |

### Exact transition rules [N]

1. The only forward stage transition is from a stage in the table to its immediate successor. No adapter may jump over a stage.
2. A forward transition is one atomic durable operation: append the predecessor’s authoritative exit receipt, persist the successor stage as `READY`, and bind the successor to that receipt ID. If atomic storage is unavailable, record `AMBIGUOUS` and do not dispatch the successor.
3. A stage becomes `ACTIVE` only after its entry guard passes and its exclusive lease is durably granted.
4. A stage becomes `VERIFIED` only through an authoritative receipt with `outcome=VERIFIED`; an agent narrative, log line, or dashboard indicator cannot substitute.
5. `NEXT` never causes execution. It records an explicit human gate or closes/stops the workflow. `REQUEST_NEW_ADMISSION` is a new workflow, never a rewind of the existing identity.
6. The controller must fail closed: a missing receipt, missing evidence reference, missing authority reference, or invalid predecessor outcome prevents the forward transition.

## 3. Identity, leases, and idempotency

### Immutable identity [N]

- `workflow_id` is assigned once at ADMISSION and never reused, renamed, or reassigned.
- `attempt_id` is assigned once per execution claim and never reused; retries receive a new `attempt_id` and retain `retry_of_attempt_id`.
- `receipt_id` is assigned once, is immutable, and identifies exactly one append-only receipt.
- `idempotency_key` is supplied before dispatch. Repeating the same request with the same `(workflow_id, stage, idempotency_key)` must return the existing attempt/receipt rather than create a second runnable attempt.

The observed board already stores immutable-looking task IDs, run rows, events, and an `idempotency_key` column [E]. Their required immutability and cross-platform semantics are new [N].

### One lease per role [N]

Within the V20 board namespace, at most one unexpired `ACTIVE` lease may exist for a `role_id` at a time. A lease is identified by `(lease_id, workflow_id, stage, role_id, attempt_id)`, has an issued time and expiry, and is renewable only by its holder before expiry. The durable lease grant must reject a conflicting active lease.

A lease expiry does not prove the holder did not act. On expiry, the controller creates an `INTERRUPTED` receipt and moves the attempt to reconciliation; it must not automatically treat the work as failed or rerun it.

The current board provides claim locks, expiries, current-run pointers, and heartbeats [E]. Namespace-wide one-active-lease-per-role enforcement and the reconciliation rule are new [N].

## 4. Outcomes, interruption, ambiguity, and dependencies

### Attempt outcomes [N]

- `VERIFIED`: exit guard passed and evidence is bound in an authoritative receipt.
- `REJECTED`: ADMISSION declined before any downstream stage is made runnable.
- `FAILED`: a known guard or verification failure occurred; evidence identifies it.
- `BLOCKED`: a named external dependency or required human decision is absent.
- `INCONCLUSIVE`: REVIEW evidence does not justify a positive or negative research conclusion.
- `INTERRUPTED`: the lease ended, process crashed, or dispatcher recovery occurred before a verified exit receipt.
- `AMBIGUOUS`: durable or external effect status cannot be proven. This blocks automatic retry and requires reconciliation.

Observed board run outcomes include `completed` and `blocked`, and the schema enumerates `crashed`, `timed_out`, and `released` statuses/outcomes [E]. The normalized outcomes and their lifecycle meaning are new [N].

### Reconciliation rule [N]

For `INTERRUPTED` or `AMBIGUOUS`, a distinct reconciler reads immutable inputs, output/effect evidence, and all prior receipts. It must produce exactly one reconciliation receipt:

- `VERIFIED` only if the original exit guard is independently proved;
- `FAILED` only if non-completion is independently proved; or
- `BLOCKED` with `ambiguity_reason` if neither can be proved.

No automatic retry, successor transition, model replacement, schedule action, or authority escalation is permitted before reconciliation.

### Dependency propagation [N]

A successor may enter `READY` only when every required predecessor has an authoritative `VERIFIED` receipt satisfying the predecessor’s exit guard. If any predecessor is `REJECTED`, `FAILED`, `BLOCKED`, `INTERRUPTED`, `AMBIGUOUS`, or `INCONCLUSIVE`, every dependent is recorded `BLOCKED` with `blocked_by_receipt_ids` and the exact propagated outcome. It is not silently promoted, retried, or considered successful.

The observed board has durable parent/child links and promotions after parent completion [E]. The required outcome-aware propagation and receipt binding are new [N].

## 5. Minimum receipt schema

Each receipt is immutable, append-only, JSON-serializable, and free of secrets [N]. The source column marks every field as existing evidence or a new requirement.

| Field | Required | Source | Meaning |
|---|---:|---|---|
| `schema_version` | yes | [N] | Contracted receipt format version. |
| `receipt_id` | yes | [N] | Immutable receipt identity. |
| `workflow_id` | yes | [E/N] | Immutable workflow identity; maps to the existing task-ID concept. |
| `attempt_id` | yes | [E/N] | Immutable execution identity; maps to the existing run-row concept. |
| `stage` | yes | [N] | One fixed lifecycle stage. |
| `role_id` | yes | [E/N] | Accountable role; existing board records assignees. |
| `event_type` | yes | [E/N] | `LEASE_GRANTED`, `HEARTBEAT`, `EXIT`, `RECONCILIATION`, or `TRANSITION`. Existing board records event kinds. |
| `outcome` | yes for `EXIT`/`RECONCILIATION` | [E/N] | One canonical outcome from Section 4. |
| `occurred_at_utc` | yes | [E/N] | Event timestamp; existing events/runs store timestamps. |
| `predecessor_receipt_ids` | yes | [N] | Exact satisfied prerequisite receipts. |
| `blocked_by_receipt_ids` | conditional | [N] | Exact failed, blocked, interrupted, ambiguous, or inconclusive dependencies. |
| `authority_reference` | conditional | [E/N] | Brennan’s originating instruction or exact-scope approval reference where required. |
| `contract_reference` | conditional | [N] | Frozen contract path plus content hash. |
| `evidence` | yes | [E/N] | Array of `{path_or_uri, sha256, purpose}`; existing manifests and research receipts use paths and hashes. |
| `lease` | conditional | [E/N] | `{lease_id, issued_at_utc, expires_at_utc, renewed_at_utc}`; existing board has claim locks/expiry and heartbeats. |
| `idempotency_key` | yes for dispatch/effecting attempts | [E/N] | Duplicate-suppression key. |
| `effect_scope` | yes | [N] | `none`, `read_only`, or explicitly approved bounded effect; no authority is implied. |
| `ambiguity_reason` | conditional | [N] | Why completion/effect status cannot be proven. |
| `retry_of_attempt_id` | conditional | [N] | Immutable link to the prior reconciled attempt. |
| `producer` | yes | [E/N] | Platform adapter, worker role, and declared version; board runs already capture profile. |

## 6. Minimum adapter obligations [N]

A platform adapter must: persist identity, leases, stage state, links, and receipts durably; enforce the transition and lease guards; expose append-only receipt retrieval; preserve raw platform event/run references; and report inability to make a transition atomic as `AMBIGUOUS`. It may not declare research, operational, deployment, promotion, trading, scheduling, paid-compute, risk, or capital authority.

## 7. Current gate

This is a proposed contract, not an implementation approval. The current evidence supports only partial G4/G8 primitives, while V20 research admission remains NO-GO pending its independently documented data/evaluation gates. The next permissible action is Brennan’s review of this contract; implementation requires a separately admitted, exact-scope task and any required authority approval.
