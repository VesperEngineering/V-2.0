# Concurrent repository reconciliation for operator UI work

Use this pattern when an autonomous steward, another agent, or repository automation is committing or resetting the canonical worktree while an operator-terminal change is in progress.

## Detect ownership drift early

Before editing, record:

- canonical `HEAD` and branch
- porcelain status, including staged versus unstaged columns
- the explicit files owned by the current slice

Recheck `HEAD` and those paths after long tests or any surprising disappearance of edits. Two rapid head changes, rewritten equivalent commits, or production markers vanishing while tests remain are evidence of concurrent ownership—not a reason to keep reapplying patches blindly.

## Immutable staged-candidate review mode

A frozen staged-candidate review is a stop-and-report workflow, not a reconciliation workflow. If the user supplies an expected `git write-tree`, follow `references/read-only-diff-drift-gate.md`: assert it first, bracket substantive batches, recheck after any command/tool failure, and stop on the first drift without rebaselining. Return to the reconciliation steps below only when explicitly asked to implement or reconcile a new candidate.

## Isolate instead of fighting the canonical tree

1. Stop writing the canonical tree as soon as concurrent replacement is confirmed.
2. Create a named temporary worktree and bounded feature branch from the latest canonical commit.
3. If an owned diff still exists, export only the explicit slice and apply it in the worktree. If it was already reset, reconstruct from the verified tests/source rather than restoring an untrusted broad patch.
4. Continue test-first implementation in the isolated worktree. Never disable or mutate the scheduler merely to win a race unless that authority was separately granted.

A worktree isolates tracked source, but it normally lacks ignored local state such as `.env`, `.venv`, databases, generated receipts, and bulk artifacts. Therefore:

- invoke the canonical virtualenv explicitly while setting the worktree as `cwd`
- do not copy credentials into the worktree
- run the focused source-backed suite there
- treat asset-dependent full-suite failures as inconclusive, not regressions or passes
- prove the environment classification by rerunning the implicated nodes or test files in canonical with the ignored assets available; failure names alone are not evidence
- rerun the full suite in canonical after reconciliation

## Reconcile without losing someone else's work

1. Freeze the isolated candidate for an **early assurance review**: stage only explicit owned paths, record the staged tree or diff hash, and make no edits while that review is running. This review can catch logic defects, but it is not the release verdict if later integration can change the tree.
2. Run focused tests, compile/static checks, pure-render geometry, `git diff --check`, changed-line lint, a requirement-to-evidence audit, and a secret/authority scan. Commit the isolated slice only when a commit is useful as a transport for rebase/cherry-pick.
3. Re-read canonical `HEAD`, branch, and status immediately before reconciliation. Rebase, cherry-pick, or three-way apply onto the newest canonical history; do not rewrite concurrent commits.
4. If conflict resolution is required, preserve non-overlapping canonical files and unknown local edits. Select one side for an overlapping file only after proving that the canonical hunk is an earlier version of the same slice (for example, stage comparison plus byte/hash equivalence of the intended superset). Otherwise merge the symbols deliberately and retest.
5. Rerun the focused suite and all checks on the post-integration candidate. Complete the last product-requirement audit and added-line lint **before** commissioning final review; late omissions such as an undisplayed total invalidate an otherwise good review.
6. Stage only the final owned paths, record `git write-tree`, and commission the final independent review against that exact post-integration tree. The reviewer must assert the tree first and last. Any edit, conflict resolution, rebase, formatter, or canonical-head advance invalidates the verdict and requires a fresh review.
7. After the immutable final review passes, commit the exact staged tree, run canonical tests that need ignored local assets, and push according to repository policy. If canonical advances again, integrate and repeat steps 5–7 rather than treating the old review as transferable.
8. Only then restart the real terminal and perform live keyboard/screenshot acceptance. Enumerate exact children, close stale copies, and leave one authoritative project-venv process.

## Telemetry and secret boundary during reconciliation

- Use the canonical ignored `.env` for live read-only probes without printing values or copying it into the worktree.
- A user-pasted credential is compromised even if it was already present in `.env`; never repeat it, advise immediate rotation, and never treat a successful probe with that key as removing the rotation requirement.
- Print only sanitized telemetry fields and static error classifications. Provider spend remains account aggregate until receipt lineage attributes it.
- Configure non-secret opt-in and operator-identity names locally only after the code path and tests are verified.

## Stop conditions

Do not claim completion when any of these remain:

- isolated commit not reconciled into canonical root
- independent review still pending
- canonical full-suite boundary unknown
- stale/multiple terminal processes still running
- no fresh live render or screenshot after relaunch

Report these as explicit unverified boundaries rather than converting focused success into a broad green claim.
