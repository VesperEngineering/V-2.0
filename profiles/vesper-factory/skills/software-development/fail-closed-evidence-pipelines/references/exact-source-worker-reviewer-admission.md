# Exact-Source Worker and Reviewer Admission

Use when a governed proof requires a real Hermes worker plus a distinct exactly-once reviewer bound to one immutable source SHA.

## Discover the live control contract

Before scripting a Kanban mutation, inspect the exact installed subcommand help. Do not infer or transplant flags such as title/worktree/runtime options from another Hermes version. If a create command fails, query the board before retrying so a partial success cannot become a duplicate task.

Treat a coordinator script as a multi-write transaction even when it only prints one final JSON object. A task create, lifecycle finalization, and receipt comment may all have committed before a later formatting or result-key exception. After any nonzero exit, reconcile task identity, run count, receipt, review packet, and comment by immutable IDs before deciding whether any part may be retried. Never rerun the whole script merely because its final `print()` failed.

Prefer an existing audited bridge API when it already encodes project, branch, retry, and workspace invariants.

## Establish source before dispatch

1. Commit and test the candidate.
2. Pre-create the worker/reviewer branch at the exact SHA.
3. If automatic dispatch is possible, establish a reversible admission barrier before task creation. Temporarily withholding an assignee profile is acceptable only after proving no task for that profile is running and backing up its configuration byte-for-byte.
4. Create the task record.
5. Before dispatch, require:
   - zero runs and no current run/PID;
   - expected project, assignee, creator, retry/runtime bounds, and workspace path;
   - materialized worktree `HEAD` equals the immutable SHA;
   - tracked status is clean;
   - frozen inputs/config exist and match their hashes.
6. If Hermes created only a task record, materialize its workspace manually from the pre-created branch. If it materialized from canonical or another SHA, preserve the task as `HELD`; do not retry it into admissibility.

A requested branch name or task body is intent, not source proof.

## Worker execution

- Narrow tools and paths to the immutable contract.
- Release admission only after exact-source verification.
- Accept exactly one run. A second run makes an exactly-once proof inadmissible even when successful.
- Immediately restore temporary profile configuration byte-for-byte after termination and verify its digest.
- Audit persisted session telemetry—not only rendered logs—for provider/model, every tool call and path, run/session identity, and tracked cleanliness.

## Atomic reviewer admission

Status labels alone may not prevent gateway auto-promotion. Keep the reviewer non-runnable until all dependencies exist. Restoring an assignable profile can immediately promote a `blocked` card to `ready`; therefore treat profile restoration as the admission release and perform every branch/worktree/receipt/run-count check before that restore.

1. pre-create the reviewer branch at the exact source SHA;
2. create a distinct reviewer task with zero runs behind a real admission barrier;
3. bind worker task/run/session/candidate identities into the lifecycle;
4. generate the exact pending receipt and review packet;
5. attach/comment the exact receipt hash and paths;
6. verify reviewer branch/worktree SHA, tracked cleanliness, zero runs, and distinct identity;
7. release admission for exactly one reviewer run;
8. restore reviewer configuration byte-for-byte immediately afterward;
9. accept only a machine-parseable verdict bound to source SHA, receipt hash, and candidate hash;
10. inspect persisted reviewer telemetry, not only its summary: require the final exact focused test and lint invocations to exit zero, account for every failed intermediate command, and reject any un-superseded failed adversarial probe or forbidden persistent write. A retry caused only by external scratch/setup is admissible only when the equivalent exact gate later passes without weakening scope.

Avoid uncertain goal/dependency auto-promotion paths. Use supported unlink/admission controls discovered from live help or an audited bridge; do not patch board SQL ad hoc.

## Supersession rule

Preserve wrong-source, multi-run, premature-dispatch, ambiguous-verdict, or missing-dependency attempts as explicit held provenance. Never recycle their identities.

Any source-changing remediation invalidates prior exact-source worker/reviewer evidence, unattended schedule proof, and positive operator projection. Mark those artifacts superseded, remove stale positive projections, and repeat the complete proof from the new SHA.

## Checklist

- [ ] Live CLI syntax was discovered before mutation.
- [ ] Worker and reviewer branch/worktree HEADs equal the exact SHA.
- [ ] Both tasks had zero runs before admission and exactly one afterward.
- [ ] Pending receipt hash was attached before reviewer execution.
- [ ] Persisted telemetry stayed within allowlisted tools and paths.
- [ ] Temporary profile changes were restored byte-for-byte.
- [ ] Held/superseded attempts have explicit dispositions.
- [ ] A source change triggered a fresh end-to-end proof rather than evidence reuse.
