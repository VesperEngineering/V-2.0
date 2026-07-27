# From an Aspirational Brief to a Runtime-Truth Roadmap

Use this reference when a user supplies an architecture or agentic-workflow brief and asks how to make Vesper fully functional.

## Core rule

Treat the brief as desired behavior, not evidence of current operation. Build the roadmap from live runtime truth and canonical repository evidence.

## Baseline proof order

1. Read current authority in `PROJECT_ADVANCEMENT.md`, `AGENTS.md`, coding standards, and lane/autonomy manifests.
2. Record canonical branch, local/remote divergence, dirty paths, ownership, and every active worktree/ref.
3. Inspect the live Hermes board: nonterminal cards, dependencies, comments/provenance, runs, handoffs, and auto-decomposition posture.
4. Inspect running processes and prove whether VOT, resident services, workers, gateway, and observers are actually live. Detect duplicate operator instances.
5. Check runtime artifacts: heartbeats, task/provider ledgers, receipts, state databases, and freshness/integrity.
6. Inspect installed scheduler definitions, exact action-path existence, last results, and matching receipts. A scheduled task or zero exit code alone is not operational proof.
7. Trace the real transport. Fixture launchers and fake providers prove contracts, not a real agent path.
8. Inspect evaluator independence, keep/reject/hold behavior, retries, idempotency, crash recovery, and Kanban read-back.
9. Separate recorded attestations from authenticated approval, execution authorization, side effect, and independent post-check.
10. Reconcile status documents, issue registry, fact base, and current evidence before declaring readiness.

## Stage matrix

Classify each stage independently as `YES`, `PARTIAL`, `NO`, or `PRESENT BUT NON-AUTHORIZING`:

```text
goal intake
→ immutable task contract
→ authority classification
→ real worker dispatch
→ bounded candidate/artifact
→ independent fixed evaluator
→ accept/reject/hold
→ full lifecycle receipt
→ Kanban final-state read-back
→ human review/approval
→ delivery or separately gated execution
→ accepted learning consumed by a later cycle
```

Never blend these into one completion percentage.

## Canonical ownership decision

Default to one orchestration owner. When Hermes/Kanban already provides durable tasks, worktrees, worker dispatch, runs, and comments, prefer it as the real worker control plane. Let Vesper own domain contracts, deterministic evaluation, receipts, state projection, and safety classification. Avoid scheduling a second general-purpose provider/task runtime unless a deliberate architecture decision proves why both are needed.

Keep observation systems separate: a resident observer may summarize completed evidence but must not become a planner or dispatcher because it has a heartbeat or a `PASS` receipt.

## First-loop pattern

Do not start with arbitrary production edits, model training, promotion, or order authority. Prefer a small research schema/DSL candidate:

```text
frozen local objective
→ contract hash
→ real Hermes worker
→ one bounded JSON candidate
→ deterministic evaluator
→ ACCEPTED / REJECTED / HELD
→ receipt + review packet
```

The worker cannot edit the evaluator, baseline, threshold, data manifest, limits, or authority. Rationale is advisory; the evaluator makes the decision. Accepted means retained as research evidence, not promoted.

## Define “fully functional” explicitly

Cover each dimension rather than equating a passing test suite with a working project:

- canonical source and status truth;
- proven unattended agentic loop;
- current data/research/portfolio evidence;
- safe preview and separately gated paper lifecycle;
- scheduler/process ownership and recovery;
- VOT/operator visibility;
- durable alert delivery;
- approval/authentication semantics;
- backup, rollback, and soak acceptance.

Live trading remains a separate future authority decision unless the user explicitly opens it.

## Selective rebuild criteria

Rebuild a component only when evidence shows one of the following:

- two components claim the same state or authority;
- no live caller/runtime exists and compatibility adds ambiguity;
- the boundary is narrative/flag-only rather than structural;
- idempotency, recovery, integrity, or evaluator isolation cannot be added safely with a small repair;
- a small replacement can be proved by compatibility and negative tests.

Preserve healthy data, validation, evidence, UI, and governance pieces. Rebuild the orchestration spine selectively before considering a wholesale rewrite.

## Roadmap order

1. Reconcile Git/worktrees/ownership and current truth.
2. Freeze task, candidate, baseline, evaluator, budgets, and stop conditions.
3. Add deterministic authority classification and an idempotent Kanban bridge.
4. Add a durable lifecycle controller and full receipt.
5. Prove fixtures, isolated integration, one real canary, restart recovery, and an unattended window.
6. Add honest VOT projection and single-instance discipline.
7. Repair scheduler/alerts only after their authority gates are explicitly opened.
8. Complete data/research/portfolio lanes.
9. Repair and separately approve the paper lifecycle.
10. Soak, recover, document, and release.

## Common false positives

- Source code exists → not proof it is running.
- Tests exist/pass → not proof of a live transport.
- Provider event exists → not necessarily task-bound execution.
- Task is assigned/running → not proof of a fresh worker lease.
- Scheduler entry exists → not proof its action path or receipt is valid.
- Approval label exists → not execution authority.
- Receipt says `PASS` → not sufficient unless schema, source binding, freshness, and downstream meaning validate.
- Green no-queue/no-op → classify `IDLE`, not productive success.
