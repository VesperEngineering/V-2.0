# Worktree Reconciliation Sweep — 2026-07-19 session detail

Session-specific evidence for the sweep procedure in SKILL.md §15. Repo: `D:/vesper`, branch `vesper`.

## Outcome

37 worktrees → 13 (root + 12 owner-decision). 24 pruned, zero unvetted removals.
Uncommitted residue archived to `.hermes/audits/worktree-sweep-20260719/` before any `--force` (per-worktree `.patch` of `git diff`, plus `-untracked/` copies of untracked files excluding `.venv`/`.tmp*`, plus `<branch>-vs-main.patch` for the cherry tranche).

## Tranche A — ancestor-merged (17 pruned)

Test: `git merge-base --is-ancestor <branch> vesper`. All commits already in main.
Pruned: `wt/board-date-parser-reconciliation`, `wt/daily-no-order-candidate-evidence`, `wt/daily-preview-active-evidence-final-revision`, `wt/daily-preview-active-evidence-routing`, `wt/daily-preview-active-evidence-validator-revision`, `wt/factor-basket-receipt-semantics`, `wt/freshness-board-pointer-repair`, `wt/local-factor-input-diagnosis`, `wt/local-only-shadow-candidate-pipeline`, `wt/local-only-shadow-candidate-pipeline-r2`, `wt/massive-approved-refresh-report-only`, `wt/operator-next-action-validation-repair`, `codex/dashboard-trust-hardening`, `codex/retirement-wave1`, `wt/t_09c8073f-impl`, `feat/structured-handoff-protocol-v1`, `feature/vot-command-deck`.

Note: 7 of these had dirty working trees (uncommitted edits, untracked files). Merged tip ≠ clean state — archive first, always.

## Tranche B — patch-equivalent via git cherry (7 pruned)

Test: `git cherry vesper <branch>` — `+` = unique commit, `-` = equivalent in main. `unique=0` justified `git branch -D`.
Pruned: `fix/vot-left-rail-flicker`, `feat/operator-tui-v1`, `feat/operator-tui-shortcut`, `wt/board-date-parser-reconciliation-r2`, `wt/daily-preview-authoritative-validator-r3`, `wt/daily-preview-authoritative-validator-r4`, `fix/cockpit-queue-overflow`.

This catches the "same fix landed via a different branch" case that ancestor checks miss — common when parallel agents retry the same task.

## Kept for owner decision (12, with unique-commit counts)

| Worktree | Unique | Note |
|---|---|---|
| `codex/vesper/paper-capacity-kernel` | 9 | Likely real work (fail-closed paper kernel) |
| `codex/vesper/winui-command-center` | 80 | Large unmerged investment — direction decision |
| `wt/stage2-local-delivery-shadow` | 3 | Governance stage lanes — live or abandoned? |
| `wt/stage3-kanban-shadow-transition` | 7 | same family |
| `wt/stage3-kanban-atomic-transition` | 8 | same family |
| `fix/vot-telemetry-panels` | 3 | 15 dirty files — possibly a live concurrent session |
| `fix/vot-telemetry-integration` | 1 | Lean prune (likely superseded by VOT rebuild) |
| `codex/loop-retirement` | 1 | Lean prune |
| `wt/t_84afd6e5` / `t_c7b1cf3c` / `t_e4e2603b` | 2 ea | Lean prune (abandoned retries; sibling merged) |
| `codex/nastocs/react-electron-cockpit` | 23 | Month-stale spike, 935 behind — lean prune |

## Pitfalls hit (encoded in SKILL.md §15)

- Windows CRLF in bash loops over `git worktree list --porcelain` — branch names carried `\r`, every `merge-base` check failed silently, the loop printed nothing and looked done. Python parsing fixed it.
- Untracked files invisible to `git diff` — must enumerate with `git -C <wt> ls-files --others --exclude-standard` and archive separately.
- Dirty-file count as a liveness signal: `fix/vot-telemetry-panels` had 15 dirty files → possibly an active session; excluded from pruning.
