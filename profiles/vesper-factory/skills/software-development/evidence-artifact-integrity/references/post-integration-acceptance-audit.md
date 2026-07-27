# Post-Integration Canonical Acceptance Audit

Use after an exact local merge is already canonical and an immutable acceptance receipt claims the integration, preservation, tests, evidence lifecycle, scheduler provenance, and closed authority state.

## Goal

Return a fail-closed `PASS` or `HOLD` for the exact merge and receipt. `PASS` may authorize attachment to a local correction card and local Kanban closure only. It never authorizes push, deployment, scheduler mutation, provider/model changes, broker/order activity, or trading.

## Order of operations

1. **Declare authoritative bindings in memory:** canonical repo/branch, exact merge and ordered parents, source SHA/tree/base, receipt path/hash, protected manifests, evidence roots, worker/reviewer IDs, scheduler job/execution IDs, correction card, and explicit false authority fields.
2. **Hash the acceptance receipt first.** Reject a physical SHA mismatch before spending time on subordinate evidence.
3. **Build a claim-to-proof matrix.** Every material receipt field must map to one physical artifact, Git fact, copied database row, live read-only control observation, or fresh external-scratch gate. A top-level `PASS` is never its own proof.
4. **Run acceptance-critical static checks in one consolidated script:**
   - canonical branch/HEAD/tree and ordered merge parents;
   - tree-neutral sibling or exact-base topology;
   - exact four/path allowlist and byte-identical binary diff;
   - manifest hashes, pre/post entry equality, current porcelain-row equality, full file/symlink streaming hashes, case-folded/prefix/reparse collisions;
   - named source/reviewer/integration worktrees clean at exact SHAs;
   - no local remote-tracking ref contains the merge.
5. **Authenticate lifecycle evidence in one consolidated script:**
   - contract canonical hash and frozen input/evaluator hashes;
   - deterministic evaluation recomputation;
   - receipt logical hash plus physical SHA;
   - candidate/evaluation/receipt/review/closure cross-copy equality;
   - lifecycle event hashes and exact single `CLOSED` transition;
   - worker/reviewer task/run/session identity and exactly-once counts;
   - VOT projection recomputed from a scratch copy;
   - unattended supervised/natural receipts and false authority fields;
   - superseded historical receipt remains bound to an immutable HOLD record.
6. **Copy SQLite sources before opening them.** For Kanban and cron, make a stable external copy of main/WAL/SHM, require before/after source hashes and copied hashes to agree, run `PRAGMA quick_check`, discover schema, then query the copy. Never instantiate production stores against original evidence.
7. **Re-read live controls without mutation:** target proof job auto-removed, no duplicate, historical supervisor paused/disabled, profiles byte-equal to backups, and all named Windows paper-submit tasks disabled with no next run.
8. **Run fresh gates from a detached external clone at exact merge:** focused pytest with external `TEMP`/`TMP`/`TMPDIR` and `--basetemp`, critical Ruff, in-memory or externally routed compile, `git diff --check`, and a bounded added-line authority/security scan. Preserve command, exit code, summary, and log hash.
9. **Authenticate broad evidence:** require complete terminal newline/summary; compare failure node IDs by exact unique count, set, and order against the named baseline. A broad suite may remain non-green only when there are zero added nodes and no changed-test failure.
10. **Reserve budget for closing drift.** Re-run canonical HEAD/branch/tree, status SHA, all protected content hashes, evidence-root manifests, named worktree cleanliness, receipt hash, profiles, scheduler semantics, and correction-card state immediately before verdict.

## Time-dependent probe rule

Do not use the current wall clock to prove expiry behavior: the contract may not yet be expired. Parse `expires_at`, set an injected probe clock to `expires_at + epsilon`, and require:

- strict first-admission validation rejects the contract as expired;
- reconciliation validation accepts the same structurally valid contract only when a matching durable lifecycle already exists;
- a future-issued contract is still rejected.

If an initial audit script used wall time and produced a false HOLD, classify it as an audit-harness error, correct the injected clock, rerun, and preserve both attempts in external scratch. Do not attribute the harness error to the target.

## Iteration-budget discipline

- Prefer two restartable consolidated scripts (`static` and `evidence`) over dozens of one-off commands.
- Execute receipt hash, protected-content verification, lifecycle cross-copy checks, focused tests, scheduler/card state, and closing drift before optional narrative reconstruction.
- Keep at least one final tool-call tranche unused for closing drift and machine-readable rollup.
- If the runtime ceiling arrives before any acceptance-critical gate or closing drift, return `HOLD`; do not infer completion from earlier green evidence.

## Verdict artifact

Write a machine-readable rollup in the authorized external scratch root containing every check, failed invariant, exact hashes/counts, harness-error classification, and retained authority boundaries. If the interaction contract requires a one-token final response, keep concrete evidence in that rollup and return only `PASS` or `HOLD`.