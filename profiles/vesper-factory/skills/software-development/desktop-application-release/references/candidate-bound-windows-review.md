# Candidate-bound review in dirty Windows worktrees

Use this protocol for broad desktop-release candidates when unrelated tracked or untracked state must remain untouched.

## Freeze the staged candidate

1. Capture branch, base `HEAD`, upstream/ahead-behind, staged paths, unstaged paths, and untracked categories.
2. Stage an explicit source/test allowlist. Never use `git add -A` in a dirty or shared worktree.
3. Require no unstaged application-owned path and assert unrelated tracked dirt remains unstaged.
4. Run worktree and cached `git diff --check`, added-lines secret scanning, and relevant static checks.
5. Bind review to the base commit, `git write-tree` staged tree, staged file count/path digest, and a canonical raw-byte staged-diff digest.

## Canonical raw-byte digest on Windows

PowerShell text pipelines can normalize Git diff bytes and produce a different digest for the same index. Hash raw subprocess bytes instead of decoded pipeline text:

```python
import hashlib
import subprocess

data = subprocess.run(
    ["git", "diff", "--cached", "--binary", "--full-index", "--no-ext-diff"],
    check=True,
    stdout=subprocess.PIPE,
).stdout
print(hashlib.sha256(data).hexdigest())
```

Give the reviewer this exact method. The staged tree is the primary Git-native identity; the digest proves the rendered binary patch under a defined byte-preserving method.

## Reviewer contract

A desktop release reviewer needs read-only repository access, not only a pasted diff. Require it to recompute identities, inspect guardrails/contracts/implementation/tests and the whole staged scope, distinguish setup HOLD from candidate HOLD, and return structured fail-closed output.

Require findings to be reconciled with the producer and consumer contracts before repair. A field named `last_event_sequence`, for example, may be a journal-global tail accompanying a limit-bounded page rather than a page-local tail.

## Repair and rereview

Every post-freeze edit invalidates the prior identity and verdict. Reproduce each valid finding with a focused RED test, repair minimally, rerun affected/full gates, restage only the repair allowlist, recompute identities, and obtain a fresh review.

Tests must model production scheduling and identity. For async React effects, clearing an in-flight ref or forcing a test rerender does not prove retry when item/notifier dependencies remain stable; use stable identities and advance a bounded retry timer.

## Commit gate

Immediately before commit, recompute base/tree/digest/file count, verify no application-owned unstaged paths, and prove unrelated dirt is still unstaged. Commit the already-reviewed index without broad restaging. After commit, assert `HEAD^{tree}` equals the reviewed staged tree.
