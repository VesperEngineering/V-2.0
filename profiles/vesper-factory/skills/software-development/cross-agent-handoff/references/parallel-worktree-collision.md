# Parallel Hermes Sessions Sharing a Git Worktree

Use this when two Hermes windows may be modifying the same task.

## Detection sequence

1. Inspect the live worktree first; session history is secondary evidence:
   ```bash
   git status --short --branch
   git worktree list --porcelain
   git reflog -8 --date=iso
   git diff --cached --stat
   git diff --cached --binary | sha256sum
   ```
2. Search Hermes session history for the exact worktree path or branch name. Match reports to actual file edits and timestamps.
3. Check running Hermes processes only as supporting evidence. Multiple processes prove multiple sessions exist, not that they are editing the same path.
4. Compare the current staged diff with each session's last reported state. A historical summary is stale whenever it conflicts with the live worktree.

## Resolution

- Assign exactly one session as owner of a worktree/branch/task.
- Stop only the conflicting session; unrelated Hermes windows may remain open in separate worktrees.
- Never let two sessions intentionally compare implementations inside one worktree. Give each implementation its own branch and worktree.
- Do not reset until ownership is explicit and the user approves discarding uncommitted work.
- Reset only the affected worktree; verify adjacent layout/feature worktrees remain clean and separate.

## Communication rule

State plainly which session changed which candidate. If review forces a scope downgrade (for example, full workflow to read-only shadow mode), announce that the approved workflow is no longer being delivered before continuing. Do not let repeated verification activity obscure the feature being tested or imply that a narrowed candidate satisfies the original request.
