# Ignored-data worktree preflight

## Problem shape
A clean Git worktree contains tracked files, but typically omits ignored operational inputs such as multi-GB SQLite stores and generated receipts. A bounded preflight run inside that worktree can therefore fail because paths are absent even though the canonical repository has the exact local inputs.

## Safe recovery pattern
1. Treat the worktree failure as a workspace-scoped result, not evidence that the canonical input is absent.
2. Check only canonical input existence and metadata first (path, size, mtime); do not read large databases until scope is established.
3. If the next action is genuinely read-only, run it against canonical data with a fixed argv and write only a named ignored receipt. Record pre/post metadata for every protected input and active-state sentinel.
4. If an action would make a provider call or write staged artifacts, require the normal plan/preflight and exact authority in canonical context before it can run.
5. Keep code changes in isolated worktrees; never use this exception to casually edit a dirty canonical checkout.

## Reporting
Distinguish `missing in isolated worktree` from `missing in canonical source`. Do not claim a source is unavailable until the canonical source has been checked.