# Dirty Worktree Recovery Before Dashboard Repair

Use when a dashboard audit lands in a repository with hundreds of mixed modifications, deletions, staged additions, and generated payload changes.

## Recovery sequence

1. Inventory staged, unstaged, deleted, and untracked paths separately.
2. Preserve staged and unstaged binary-capable patches before restoration. Record the exact pre-recovery status and deleted-path list.
3. Restore only tracked paths whose worktree status is deleted; do not overwrite modified or untracked files.
4. Verify required CI paths exist. A green run of a sharply reduced surviving suite is not baseline evidence.
5. Run collection, workflow-required focused tests, then the restored full suite with a unique `--basetemp`. Do not run concurrent pytest processes against the same basetemp.
6. Classify failures by cluster: incomplete migration, governance drift, operational data assumptions, environment/toolchain, and genuine product regressions.
7. Do not commit or publish while declared CI paths are missing or the relevant restored baseline is red.

## Important distinctions

- Restoring an unstaged deletion to `HEAD` removes a dangerous worktree deletion but creates no new Git diff and therefore no standalone commit.
- Preserve the rough-patch archive outside the curated source commit.
- A generated payload can dominate diff size; review source and generated data separately.
- If a rename is incomplete, retain the old authority as a compatibility path until active scripts, docs, guards, workflows, and tests migrate together.

## Productive continuation

Recovery is a gate, not the research objective. Time-box it. Once the trustworthy baseline is restored, continue with bounded research or product work—risk controls, portfolio construction, cost diagnostics, or signal-combination evidence—without adding random factors or widening broker/order authority.