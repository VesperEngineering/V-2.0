# Champion/Challenger Governance Audit Reference

Use for read-only audits of model identity, admission, promotion, registry, and comparison logic.

## Evidence chain

Trace these independently, then compare them:

1. Board/current-state aliases and execution/promotion gates.
2. Registry-declared active artifact/path and lifecycle status.
3. Inferred/runtime scoring ensemble and expected seed set.
4. Path-keyed checkpoint hashes and feature-schema hashes.
5. Source/data snapshot, cutoff dates, universe, costs, and label horizon.
6. Champion/challenger comparison receipts and baseline/equal-weight controls.
7. Admission/promotion decision surface and any mutation/apply surface.
8. Tests that assert status, authority flags, and receipts.

## High-value probes

### Path/hash binding

A registry match must compare `declared_sha == inferred_hashes[declared_path]`. A path membership check plus independent hash-set membership is unsafe: it can accept path A paired with path B's hash.

### Ensemble completeness

If configured seeds are `(7, 21, 42, 84)`, missing checkpoints must be a blocking state. `checkpoint_count == len(existing_paths)` is not a completeness check. Require the expected seed set/count and expose missing seeds.

### Status semantics

Distinguish evidence validation from decision eligibility. A receipt can be technically valid while the decision is `HOLD` or `REJECT`. Flag a top-level `PASS` that hides all decisions being held/rejected, especially when the module is named a promotion gate. Prefer explicit statuses such as `PASS_NO_PROMOTION`, `HOLD`, and `FAIL`.

### Comparison controls

A champion/challenger admission surface should bind model identities and require comparable evidence: same universe, same dates/OOS windows, same costs/turnover assumptions, equal-weight or declared baseline, walk-forward/confirmation windows, feature-schema/data-snapshot hashes, and no-lookahead checks (`feature_cutoff_date <= as_of_date`, `label_start_date > as_of_date`). Scalar confidence/stability metrics alone are not comparison evidence.

### Apply-vs-promotion contradictions

A documentation-only registry apply may be safe, but a generic `apply_ready` field beside `promotion NOT_READY` is operationally ambiguous. Require the field to say documentation-only/non-authorizing and preserve the separate promotion blockers.

### Alias/date drift

Compare board aliases, accepted-paper aliases, registry model IDs, scoring variants, source sessions, and checkpoint sets. A stale source session can make a registry snapshot look current. Require explicit `as_of`/freshness semantics or a stale-historical classification.

## Test discipline

- Read the focused tests before judging the implementation; tests may encode false confidence.
- Run a narrow behavioral subset first.
- If pytest's configured basetemp is under a protected/generated root and cleanup fails, rerun using a unique external temp root where supported; if the config still overrides it, report the exact collection/setup failure and do not call the suite green.
- Record behavioral passes separately from setup/collection errors.
- Verify `git status --short` and preserve pre-existing dirty files.

## Required finding format

For each finding record:

- Severity
- Exact path and line range
- Concrete evidence and operational consequence
- Reproduction or test command and observed result
- Minimal safe fix candidate
- Whether the issue is unsafe behavior, contradictory state, stale provenance, missing control, or false-confidence test coverage

Keep the audit read-only: no edits, training, model artifact writes, registry mutation, or promotion.