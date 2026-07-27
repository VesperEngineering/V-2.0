# Asynchronous Audit Drain and Acceptance Supersession

Use this procedure when independent reviewers or adversarial audits run asynchronously while a source-bound acceptance or integration decision is being prepared.

## Core distinction

- A `PASS` is an authorization scoped to the exact source/evidence identity it reviewed. It never transfers to a newer SHA.
- A `HOLD` is a concrete defect claim. An older reviewed SHA does **not** make the defect irrelevant: the same behavior may survive through later commits. Before dismissing a delayed `HOLD`, either identify the exact remediation in the ancestry or rerun its reproducer against the current candidate.

## Pre-acceptance drain

Maintain a small gate ledger containing every acceptance-critical delegation:

- delegation ID and role;
- source SHA/evidence root/merge SHA under review;
- state: running, completed-unread, PASS, HOLD, superseded-by-replacement;
- durable summary path and exact verdict;
- any reproducer that must be rerun on current source.

Before canonical integration, board closure, or a final receipt:

1. Enumerate every dispatched acceptance-critical audit from the session and handoff context.
2. Resolve every `running`, `completed-unread`, unidentified, or focus-metadata-only entry.
3. Read the durable final summary. Do not infer PASS from a live transcript, a completed notification, or partial green probes.
4. For every older-source HOLD, inspect whether the implicated behavior changed between that SHA and the current SHA. If not proven repaired, rerun the reproducer on current source.
5. Require current-source PASS for the final evidence bundle and current integration PASS for the exact merge candidate.
6. Record the fully drained ledger in the acceptance receipt.

A known unresolved audit is a release barrier even when all tests are green.

## Replacement audits

If an auditor harness fails rather than the target:

1. classify the result as `HOLD_AUDIT_INCOMPLETE`, not target PASS or target defect;
2. preserve its summary;
3. dispatch a replacement with the corrected schema/checker;
4. require the replacement's durable final PASS before acceptance.

Do not let a replacement for one audit silently supersede a different outstanding audit.

## Verdict emitted at the execution ceiling

An orchestration wrapper may report `max_iterations` after the auditor has already emitted its verdict but before it writes the usual consolidated summary file. Treat this as a distinct evidence condition, not automatically as either PASS or target HOLD.

Default to `HOLD_AUDIT_INCOMPLETE` unless **all** of the following are durable and exact:

1. the append-only transcript contains an explicit terminal auditor message whose entire verdict is unambiguous (`PASS` or `HOLD`), emitted before the wrapper-exhaustion record;
2. the auditor persisted a machine-readable final report in its unique external scratch with the same verdict, the expected exact source/receipt identities, the complete required check inventory, and `failed=[]` (or an equivalent zero-failure field);
3. opening/closing drift checks and every acceptance-critical gate named in the audit brief are present, not merely a subset of green probes;
4. the transcript, report, and any subordinate static/evidence reports are hashed and recorded in the parent receipt or board attachment; and
5. no later transcript row retracts or contradicts the verdict.

When those conditions hold, the durable transcript plus machine-readable report is the final-summary equivalent; do not discard a completed proof merely because the delivery wrapper appended an iteration-budget warning. If any condition is missing—or the auditor only thought `PASS`, printed partial green output, or never persisted a complete report—dispatch a narrow replacement audit and require its durable PASS. Never infer authorization from `status=completed` alone.

## Late HOLD after acceptance

When a delayed result exposes a real defect after a receipt or local merge:

1. Reproduce it on the currently accepted source before making any status claim.
2. If reproduced, immediately withdraw the completion claim.
3. Preserve the old receipt and write an append-only supersession record that binds its hash, accepted source, merge, finding, and denied authority. Never rewrite the old receipt.
4. Annotate the authoritative board. If a completed card cannot be reopened, create a correction card linked to the original and keep it non-runnable until ownership is isolated.
5. Add a RED regression, repair, and obtain an independent exact-diff review.
6. Commit a new SHA and invalidate every source-bound worker, reviewer, unattended, scheduler, VOT, integration, and final-audit proof from the old SHA.
7. Rerun the complete proof chain before issuing a replacement acceptance receipt.

## Common failure pattern

Do not say “historical and superseded” merely because an audit reviewed an older commit. That reasoning is valid for transferring PASS authority, but invalid for dismissing an unverified defect report. PASS scope and defect persistence are different questions.
