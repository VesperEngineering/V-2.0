# Accepted Lifecycle Extension Audit

Use this checklist when a later milestone must reuse an independently accepted Vesper agentic lifecycle without silently generalizing the earlier proof.

## Freeze and reconcile

1. Record canonical root, branch, full `HEAD`, `HEAD^{tree}`, recent parents, and worktree inventory with `GIT_OPTIONAL_LOCKS=0`.
2. For a very dirty root, hash the NUL-delimited porcelain status and report tracked/untracked counts plus only relevant owned diffs. Recompute the digest before the verdict.
3. Hash external acceptance receipts and record byte sizes. Keep current working-tree observations separate from source-bound acceptance evidence.
4. Read authority in order: `PROJECT_ADVANCEMENT.md` → `AGENTS.md` → coding standards → lane/autonomy manifests → milestone receipt. If the board names an older milestone than the receipt, call it governance drift and make reconciliation a prerequisite while retaining the stricter closed boundary.

## Classify what is actually reusable

For each module, capture exact public signatures and production callers, then classify it as:

- **lifecycle core:** state/event store, receipt validation, review closure, ledger append, read-only projection;
- **profile-bound:** frozen task profile, candidate parser, evaluator, fixture/baseline, runner constants, finalizer assumptions;
- **proof orchestration:** externally composed canary/scheduler evidence that is not an ordinary caller.

Tests instantiating a class do not prove production wiring. If filename search contradicts direct reads, use tracked-file inventory plus AST/signature inspection before concluding absence.

## Prefer versioned profiles over mutation

- Preserve the accepted v1 schema, defaults, fixture, baseline, evaluator, and runner behavior byte-compatible.
- Add a v2 frozen profile selected by an internal allowlist over exact schema/evaluator IDs.
- Never accept task-supplied callable paths, code, dynamic imports, or arbitrary commands.
- Rerun the complete accepted focused gate plus the new profile's adversarial tests.
- A new profile inherits lifecycle machinery, not the prior milestone's acceptance verdict.

## Separate worker and evaluator evidence

A useful research profile must prevent holdout-label access:

- mark inputs `worker`, `evaluator`, or `both` in a versioned contract;
- expose only DSL config, baseline specification, and unlabeled summaries to the worker;
- keep labels/holdout partitions evaluator-only;
- audit every worker file action against the worker-visible subset;
- bind all inputs in the final receipt.

## Freeze ranking semantics before thresholds

For cross-sectional ranking, define before seeing candidate outcomes:

- PIT universe date and post-latest fallback policy;
- effective-dated ticker aliases;
- price/total-return adjustment basis and source lineage;
- exchange-session calendar and exact forward horizon;
- listing, delisting, halted, and missing-row treatment;
- average-rank tie handling plus stable symbol ordering;
- coverage denominator/minimum cross-section;
- proposal and holdout partitions;
- baseline, metric, guardrails, and threshold.

Measure actual PIT-member coverage against the chosen source. Long history for today's constituent list is not a historical PIT panel. If full adjusted coverage is absent, hold the milestone or label the narrower probe honestly.

## Preserve state meaning

- Worker card `done`: bounded output exists.
- `ACCEPTED`: frozen research evaluator passed.
- `REJECTED`: valid evidence did not pass.
- `HELD`: identity, authority, coverage, evidence, or runtime is invalid/unknown.
- Riley `APPROVE`: evidence integrity approved.
- `CLOSED`: lifecycle complete.
- None of these grants model admission, promotion, portfolio targeting, paper/live orders, or execution authority.

The append-only ledger is a projection, not sole truth. Permit exactly the pending row followed by an identity-equal independently-approved closure row.

## Schedule separately

A prior one-shot proof is not standing recurrence authority. A later schedule must be separately approved and bind exact source revision, profile, fixture hash, run ID, limits, and output root. Run from a clean exact-source worktree, use a single-instance lock and zero blind retries, perform no data acquisition/training/promotion/orders/successor dispatch, require receipt readback, auto-remove a one-shot proof, and leave output pending independent review.

## Completion checklist

- [ ] Initial and final Git/status/evidence identities match.
- [ ] Governance drift is reconciled or explicitly blocking.
- [ ] Production callers are distinguished from tests and proof scripts.
- [ ] Accepted v1 behavior is unchanged.
- [ ] New profile is versioned and internally allowlisted.
- [ ] Worker cannot read holdout labels.
- [ ] PIT, adjustment, session, alias, and coverage semantics are frozen.
- [ ] Evaluation acceptance, independent review, closure, and promotion remain distinct.
- [ ] Prior focused gate and new adversarial tests pass.
- [ ] Any later schedule is separately approved, one-shot, source-bound, receipted, and auto-removed.
