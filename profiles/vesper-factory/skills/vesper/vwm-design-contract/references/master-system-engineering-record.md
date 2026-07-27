# Master System-Engineering Record Pattern

Use this pattern when a VOT/system build needs one durable engineering index across UI, control plane, evidence, authority, and verification.

## Required stance

- Descriptive engineering index, never a new authority source.
- Current live receipts/ledgers and the project board outrank the document.
- The stricter authority boundary wins on disagreement.
- Record implemented state separately from intended/future state.
- Update in the same code/test commit; rerun verification after the final doc edit.

## Recommended sections

1. Purpose and same-slice maintenance rule.
2. Authority/source hierarchy.
3. Whole-system topology.
4. Component registry: implementation, contract owner, actual state.
5. Source-state semantics: fresh, stale, missing, malformed, error.
6. Domain-state semantics: working, planning, review, waiting, blocked, human gate, complete, no-op, unknown, unavailable.
7. Operator/VOT page and software boundaries.
8. Autonomous work-management permissions and strict human gates.
9. Reliability invariants and hidden-write prohibitions.
10. Engineering change protocol.
11. Verification matrix by surface.
12. Implementation ledger.
13. Current gaps and next safe sequence.
14. Links to canonical governance/architecture documents.
15. Maintenance checklist.

## Implementation-ledger row

```markdown
| Date | Slice | Component/source contract | Verification | Authority effect | State |
|---|---|---|---|---|---|
| YYYY-MM-DD | concise slice | exact files/readers/writers and behavior | exact focused/adjacent commands and results | normally `none`; name any changed gate | planned / implemented candidate / verified candidate / integrated |
```

Never write `verified` if the recorded command ran before a later source or documentation edit. Rerun the relevant test target and `git diff --check` against the final candidate.

## Anti-drift checks

- Every named source feeds the matching domain; no generic status reused under a specific label.
- Missing/malformed source is unavailable, not a healthy empty state.
- Retained last-good values carry a stale overlay after refresh failure.
- UI command labels match exact mutations (`COMPLETE TASK` is not formal approval).
- Approval, execution, integration, push, deployment, release, and Ship remain separate.
- Provider/status reads do not hide persistent cache writes.
- Raw runtime journals and model text are not accepted shared knowledge without source-linked validation.
- Parallel worktrees and canonical integration state are stated accurately.
