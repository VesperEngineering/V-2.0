# Exactly-Once Reviewer Admission

Use when an immutable pending receipt names a reviewer task that is allowed to run only once.

## Generate, then validate

Build the reviewer task body from one structured packet. Do not copy and edit the previous canary's prose. Parse the generated body before task creation and require exact agreement for:

- source SHA;
- worker task, run, session, branch, and clean worktree;
- worker candidate path and raw SHA;
- lifecycle directory, pending receipt, and review packet;
- pending receipt hash and reviewer task binding;
- expected focused-test count and exact command;
- current critical-Ruff file list;
- denied authority and permitted scratch root.

Prefer forward-slash Windows paths in generated task bodies. This avoids accidental `\r` interpretation or CRLF damage when path fragments such as `\real-...` pass through patch/JSON layers.

## Receipt-bound claim circularity

When the receipt binds `reviewer_task_id`, the final receipt hash cannot exist until after the reviewer task has been created. Do not solve this by leaving a placeholder in runnable instructions and relying on manual transcription later.

Use this order:

1. Back up the reviewer profile and make its worker tool surface unavailable or least-privilege before creating the task.
2. Precreate the reviewer branch at the exact source SHA.
3. Create the reviewer task in a non-runnable state and verify zero runs.
4. Finalize the pending receipt using that task ID.
5. Machine-generate the complete structured verdict block from the receipt object. Include the exact 64-character receipt hash, source SHA, and raw candidate SHA.
6. Attach that block as immutable task evidence before dispatch. Instruct the reviewer to generate the same block directly from the receipt with a deterministic command and pass it unchanged to completion—never manually retype the hash.
7. Materialize and verify the exact reviewer worktree, re-read task evidence, and assert zero runs immediately before dispatch.
8. Enable the bounded reviewer profile and dispatch once; restore the original profile bytes immediately after termination.

A board `blocked` label is advisory when automation can promote tasks. The unavailable/least-privilege profile and exact precreated branch are the hard admission controls.

## Parser-first mismatch triage

When finalization reports that claim identity changed, stop before any retry or evidence edit. Read the durable task/run summary and pending receipt, invoke the **same production claim parser** used by the finalizer, and compare each binding separately:

```python
for name, claimed, expected in fields:
    print(name, repr(claimed), len(claimed), repr(expected), len(expected), claimed == expected)
    if claimed != expected:
        first = next((i for i, (a, b) in enumerate(zip(claimed, expected)) if a != b), min(len(claimed), len(expected)))
        print("first_difference", first, repr(claimed[first:first+8]), repr(expected[first:first+8]))
```

Check source revision, logical receipt self-hash, candidate raw-byte SHA, and reviewer task ID independently. Do not compare the receipt file's physical SHA-256 to a field that intentionally carries the receipt's logical self-hash. This parser-first probe turns a vague finalizer error into a precise evidence classification without consuming another exactly-once run. A receipt validator can pass while a separately typed completion block is wrong; validate both surfaces.

## Failure rule

If the reviewer runs once and returns `HOLD`, or returns `APPROVE` with even one mistyped identity byte, do not retry it, edit/backfill its result, or silently repair the claim. Metadata saying the receipt validated does not override a malformed completion claim. Preserve the task as held and start a fresh lifecycle with a newly bound reviewer. A second task cannot review an immutable pending receipt that names the first reviewer.

## Verification

- Exactly one admissible worker run.
- Exactly one admissible reviewer run.
- Reviewer source/worktree and receipt binding match.
- Reviewer verdict parser accepts only the exact structured verdict.
- Profile backup and restored live config hashes match.
- Held preparation/reviewer attempts are explicitly excluded from final evidence rather than hidden.
