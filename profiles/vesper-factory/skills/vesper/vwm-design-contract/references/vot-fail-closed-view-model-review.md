# VOT fail-closed view models and synchronized engineering records

Use this reference when implementing or independently reviewing a VOT production slice.

## Master system-engineering record

When the operator requests a master system-engineering document, create or maintain `docs/MASTER_SYSTEM_ENGINEERING.md` in the same isolated VOT worktree and verified change slice.

The record should connect topology, component ownership, source contracts, state semantics, authority effects, verification evidence, failed reviews, current gaps, and the next engineering sequence. Keep it **descriptive, not authoritative**:

- defer current state and authority to receipts, `PROJECT_ADVANCEMENT.md`, `AGENTS.md`, and machine-readable contracts;
- distinguish current, candidate, and target capability explicitly;
- identify current VOT approvals as unauthenticated attestations with execution denied until principal authentication and action-specific handlers exist;
- record failed independent review honestly rather than retaining an earlier green claim;
- name exact direct versus adjacent test counts and pending review gates;
- do not turn an operator-requested documentation practice into a new repository governance gate;
- do not link machine-local/untracked plans as reproducible candidate documentation.

Update the record after implementation and again whenever verification or review changes the candidate state.

## Pure view-model contract

The view model contains no Tkinter, filesystem, database, network, subprocess, provider, broker, scheduler, or secret access. It derives display state only from typed evidence.

Mandatory false-green protections:

1. `done`/`archived` becomes `COMPLETE` only with independently verified completion evidence. Otherwise render `UNVERIFIED` and retain the root in objective inventory. The action-receipt predicate must enforce the same schema/review checks; a separate looser green display or receipt path is forbidden.
2. Resolve schema contradictions and `needs_review` before closed-state handling. Never filter raw closed rows before state resolution.
3. Detect duplicate task/card IDs before any keyed reduction. Group first; a duplicate ID remains visible and unselected until an authoritative adapter resolves the contradiction. Never allow last-write-wins to erase an unsafe row.
4. `WORKING` requires a current matching run plus a fresh task-bound heartbeat. Assignment, `todo`, `ready`, old runs, and future/malformed timestamps are not proof of work.
5. Timestamp normalization guards numeric conversion itself, rejects non-finite values, and returns unavailable/unknown instead of raising on huge integers or numeric strings.
6. `HUMAN GATE` requires a fresh exact pending request: stripped non-empty IDs, canonical request status, exact action and scope match against the task's expected decision contract, unexpired timestamp, canonically distinct requester/required decider, valid source posture, and explicit false approval/execution flags. A set of task IDs, truthy whitespace, or non-empty action/scope alone is insufficient.
7. Under the current unauthenticated identity model, decision models reject `approval_granted=true` and `execution_authorized=true` structurally.
8. Change-only render signatures admit only exact built-in immutable scalar types and exact tuples recursively. Reject mutable values, non-finite floats, and hostile/unhashable scalar subclasses, then explicitly verify `hash(signature)` during construction.
9. Multiple waiting or unevidenced roots yield `No uniquely evidenced current objective`; never select one arbitrarily.

## Independent review sequence

Freeze the candidate SHA and review the exact base-to-candidate diff. Probe semantic contradictions in addition to rerunning tests: unverified closure, verified closure plus `schema_error`/`needs_review`, duplicate same-ID rows in both orders, malformed/huge/non-finite timestamps, whitespace-only IDs, whitespace-equivalent principals, expected action/scope mismatch, expired/stale/closed requests, authority flags, nested mutable signatures, hostile unhashable scalar subclasses, hidden I/O, documentation overclaims, and current/target confusion.

If review returns FAIL:

1. Keep canonical integration blocked.
2. Preserve the failed verdict and findings in the engineering record.
3. Add regressions reproducing every finding before editing production code.
4. Create a new revision commit; do not amend away the rejected candidate.
5. Run direct tests, all adjacent VOT/System tests, compile, Ruff, secret/forbidden-I/O scans, and `git diff --check`.
6. Freeze the new SHA and obtain fresh independent re-review before integration.

Passing tests before review never override a semantic FAIL verdict.
