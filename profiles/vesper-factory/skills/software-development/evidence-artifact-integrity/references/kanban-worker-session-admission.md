# Kanban worker session admission and end-to-end telemetry

Use this recipe when a worker or reviewer run is itself acceptance evidence and must execute exactly once on an exact source revision.

## Why task completion is not enough

Kanban task state and worker-process state are distinct. A model may invoke `kanban_complete`, make the task `done`, then continue reasoning and call more tools before the process exits. Changed-file metadata can still list only the intended outputs. Therefore the acceptance boundary is the complete persisted worker session, not the first completion event.

## Admission sequence

1. Freeze the source commit and contract before creating the task.
2. Precreate the intended task branch at the exact source commit. Do this before the task can be claimed; a dispatcher may otherwise materialize the branch from the canonical default head.
3. Back up the assigned profile's configuration byte-for-byte and record its digest.
4. Temporarily pin the profile's CLI toolsets to the least required surface:
   - artifact-only worker: `file`;
   - read-only reviewer that must execute tests: `file` plus `terminal`.
   Task-scoped Kanban lifecycle tools are added by the dispatcher and do not require broad CLI toolsets.
5. Parse the edited configuration and assert the CLI value is a YAML list, not a quoted string. Also verify adjacent platform toolsets were preserved.
6. Create the task with exact source, branch, contract hash, idempotency key, limits, and expected output paths. A `blocked` state is not a hard lock when board automation can promote tasks, so steps 2–5 must already be complete.
7. Materialize the declared worktree immediately when necessary. Before the claim runs, or at minimum before accepting it, assert exact `HEAD`, expected branch, and clean tracked state.
8. Allow one run only. Never retry an identity whose exact-once requirement has already been consumed.
9. Restore the profile from the byte-for-byte backup immediately after the worker process is terminal and compare digests.

## Full-session audit

Read the authoritative session ID from the task-run record, then audit every persisted assistant tool-call row in order through the final session message. Do not stop at `kanban_complete`.

For an artifact-only worker, the complete tool sequence should contain only:

- task-scoped Kanban show/bookkeeping;
- the contract-authorized frozen-input reads;
- the exact bounded output writes;
- task-scoped Kanban completion/bookkeeping.

Reject terminal, search, patch, skill, memory, web, dependency, scheduler, provider, broker/order, or any other non-allowlisted call—even if it occurs after successful completion and leaves no tracked diff.

Cross-check:

- exactly one task-run row;
- exact worker profile, model/provider, session ID, source SHA, worktree, and branch;
- runtime, turns, retries, and cost within contract limits;
- only approved output paths and exact raw-byte hashes;
- clean tracked source before and after;
- complete session tool sequence, not metadata's summarized changed-file list;
- restored profile digest equals its pre-run backup.

## Failure classification

- **Wrong source before useful execution:** preserve as wrong-source HOLD; never review or finalize it.
- **Extra tool after completion:** preserve the entire telemetry as an allowed-tool HOLD. Do not truncate the session at the completion event.
- **Reviewer instructions or pending receipt stale:** preserve the zero/one-run reviewer task as preparatory or held; create a fresh lifecycle identity rather than retrying.
- **Profile restore mismatch:** stop acceptance until the original bytes are restored and verified.

A valid candidate and deterministic evaluation cannot override an inadmissible worker session.
