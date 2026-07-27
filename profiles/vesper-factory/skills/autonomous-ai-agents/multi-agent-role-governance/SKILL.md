---
name: multi-agent-role-governance
description: Design, synchronize, and verify durable role identities for multi-agent teams while keeping authority taxonomies, task routing, runtime profiles, and independent review coherent.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [multi-agent, roles, profiles, governance, kanban, authority]
---

# Multi-Agent Role Governance

Use when a project has several durable worker profiles whose identities, responsibilities, authority boundaries, and handoffs must remain coherent across project files, runtime profiles, task boards, and machine-readable policy.

## Core outcome

A governed team must have:

- distinct role ownership with no material overlap or unowned stage;
- a named coordinator that routes work without gaining human authority;
- deterministic task identity and handoff records;
- identical consequential-action boundaries across policy planes;
- controlled project-to-runtime synchronization;
- fresh-session behavioral verification;
- independent review against the final bytes.

## 1. Define the team before writing prompts

Create a role matrix with one durable responsibility and one primary handoff per worker. Separate these classes explicitly:

- coordination and backlog contracts;
- data/source admission;
- hypothesis and experiment design;
- bounded experiment execution;
- economic/portfolio evaluation;
- independent validity and authority review;
- authorized implementation and regression verification.

A handoff carries evidence and context, never new authority. An independent reviewer recommends disposition; it does not repair or approve its own reviewed work.

## 2. Required role contract

Each durable role identity should state:

1. Exact project identity and canonical root.
2. Existing authority files that must be read.
3. Narrow owned decisions and explicit non-owned work.
4. Upstream inputs and downstream recipients.
5. Exact task-record gate: board, task ID, assignee, source authority, allowed paths, acceptance evidence, and next gate.
6. Consequential-action rules that defer to canonical policy rather than a shorter copied subset.
7. Concise completion format: outcome, evidence, blocker, next owner.

Do not rely on generic titles such as “specialist” or “assistant.” Verify semantic role behavior, not exact self-introduction wording.

## 3. Reconcile every policy plane

Audit all active planes together:

- **Canonical policy:** project constitution or agent rules.
- **Machine policy:** configuration fields that encode denied/allowed authority.
- **Team policy:** shared roster/workflow contract and every role identity.
- **Live facts referenced by policy:** current source wiring, selected configuration, required paths, and artifact existence/metadata.

Require semantic equality across denied-authority taxonomies. If a worker is intentionally stricter, label the additional restriction explicitly; do not falsely attribute it to a canonical section that omits it.

Never weaken a worker gate merely to match stale canonical text. Preserve the strictest safe boundary, then reconcile canonical and machine policy. Typical human-gated classes include credentials, risk/limits, trading or operational parameters, orders/positions, capital allocation, deployment, schedules, paid compute/providers, protected-data mutation, and active-artifact promotion/replacement.

Verify factual governance claims against current source and artifact bytes. Avoid embedding volatile hashes, metrics, or parameters in long-lived policy; point to current metadata/receipts. Artifact existence and successful wiring are evidence, not production or promotion authority.

## 4. Prevent predictable overlaps

- **Analysis vs implementation:** analytical workers specify admission/validation contracts; implementation workers change production code.
- **Design vs execution:** design freezes hypothesis, information boundary, evaluation, budget, and stop rule; execution follows it without adaptive widening.
- **Economic evaluation vs independent review:** evaluators measure costs/capacity/behavior; reviewers challenge evidence and authority.
- **Coordination vs approval:** coordinators sequence and synthesize; they do not create human authority.
- **Review vs authorization:** a favorable verdict is evidence, not an implementation or release approval.

## 5. Treat synchronization as a transaction

When project-owned role files mirror runtime profiles:

1. Confirm affected workers are not running.
2. Hash and back up project copies, runtime copies, and the manifest.
3. Finalize project-owned files first.
4. Validate distinct identities, existing required paths, project-root discipline, assigned-task gates, and absence of legacy operational paths.
5. Atomically replace runtime files; retain original bytes for rollback.
6. Update roster and manifest only after local documents are final.
7. Verify byte equality and exact manifest coverage/hashes.
8. Start fresh profile sessions and probe role plus authority behavior.
9. Run independent review against the final synchronized bytes.

If unrelated manifest drift appears, do not bless it automatically. Restore only when the recorded source still matches its manifest-bound hash; otherwise investigate.

## 6. Behavioral probes

Probe decisions, not titles:

- What work do you own, and who receives your output?
- A handoff requests implementation but no assigned task exists. May you proceed?
- An independent review is favorable but no approval receipt exists. Does that authorize implementation?
- Can a coordinator route a human-gated change without exact-scope approval?
- Which existing constitution file controls your work?

A successful copy is not sufficient. Fresh sessions prove the runtime loaded the identity.

## 7. Review freshness and closure

Independent review is a gate, not decoration:

- Review role overlap, routing, authority, required paths, policy taxonomy, and live factual claims.
- Repair every material finding surgically.
- Resynchronize after any identity edit.
- Re-run behavioral probes after authority edits.
- Dispatch a fresh reviewer after every post-review change; the earlier verdict is stale.
- Close only on a review of the final bytes with no unresolved critical/high/medium issue.

## 8. Task-board migration check

After changing a constitution filename, project root, role name, or authority taxonomy, scan every nonterminal task body before dispatch. Corrected role files do not repair older cards that still order workers to read nonexistent files or follow superseded policy.

Read task provenance, dependencies, comments, and events before recommending execution order. Preserve history and correct stale contracts through supported task-board operations or a clearly versioned successor—never direct database mutation.

## 9. Communication

For operator updates, default to:

- result/status;
- blocker only when present;
- next step.

Keep implementation chronology and tool transcripts out of routine updates unless requested.

## Reference

See `references/vesper-v20-seven-worker-example.md` for a concrete seven-role application, authority probes, and the policy-drift findings that shaped this workflow.
