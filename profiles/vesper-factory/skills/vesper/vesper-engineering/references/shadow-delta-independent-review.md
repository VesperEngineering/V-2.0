# Step 4 inert shadow-delta independent review

Use this for an exact staged-candidate acceptance review of the forecast → portfolio → risk → execution migration's inert proposed-delta slice.

## Acceptance posture

Review the exact branch, base/HEAD, staged tree, binary-diff SHA-256, staged path set, and zero unstaged/untracked state. Any candidate or staging change invalidates prior tests and ad-hoc evidence. Review only: do not edit, stage, commit, merge, or mutate runtime/data/model state.

Read the current Obsidian migration contract directly. Contract 4 requires inert proposed deltas, lot/quantity rounding, minimum-trade handling, stale-price closure, pending/open-order closure, estimated costs, and fail-closed ambiguity. Contract 5 account/effect-time authority remains later work; do not accidentally grant it in Step 4.

## Adversarial schema review

Green builder tests are insufficient. Exercise every exported input/output dataclass directly and through `dataclasses.replace`.

### Detached line truthfulness

A public delta-line record must reject contradictions even outside its aggregate plan. At minimum verify:

- `delta_weight == target_weight - current_weight`;
- `delta_notional == target_notional - current_notional`;
- nonnegative target/current weights and notionals where the domain requires them;
- zero quantity cannot be `actionable_shadow` / `actionable`;
- nonzero positive/negative quantity agrees with increase/reduce/close urgency;
- stale-price and pending-order reasons imply blocked outcome and zero proposed quantity;
- suppressed reasons imply suppressed outcome and zero quantity;
- estimated cost is unavailable or internally coherent with the line's embedded price/rate evidence.

If a line lacks enough immutable fields to validate its own public claims, either add the required fields or make the record non-public and ensure the public boundary is the fully revalidated aggregate. `frozen=True` alone is not closure.

### Strict scalar types

Python equality collapses `1 == True`. For authority and status Booleans, use exact identity/type checks rather than ordinary equality. Probe blocked plans with `replace(plan, blocked=1)` and equivalent Boolean-as-integer substitutions. Recomputed content may be Boolean while the stored public field is integer unless strictness is explicit.

### Snapshot completeness

Price coverage can be structurally complete by requiring one validated price for every target symbol. Pending-order state is different: an empty tuple is indistinguishable from omitted or partially observed broker state unless completeness is represented.

Require an explicit closed completeness state and honest external account/source/snapshot identity claims when order-state completeness is asserted. Unknown, partial, stale, malformed, conflicting, or ambiguously observed order state must block proposals. Label externally supplied identities as carried claims, not content-derived authority. Keep the internally computed snapshot digest bound to observations, as-of time, completeness state, and those claims.

Also probe:

- duplicate order identities and multiple orders per symbol;
- unsupported/ambiguous states such as partially represented broker statuses;
- unknown symbols and incomplete price coverage;
- stale and future-dated observations;
- quantity bounds and impossible rounding;
- exact-integer hashing beyond `2**53`, signed zero, Boolean-vs-number separation, and deterministic input reordering;
- mutation bypass of nested frozen observations, target records, lines, constraints, and snapshots.

## Baseline comparison

A parity test that invokes the real `MLModelStrategy.generate_signals` with only `_score_universe` replaced is valid evidence for that narrow path. State its scope precisely. Empty-holdings positive top-N order does not establish same-position parity for existing holdings, reductions, closures, rebalance timing, or `exit_rank` behavior.

Add same-timestamp/universe/prices/positions comparisons for nonempty holdings. Where portfolio-target rebalancing intentionally diverges from the legacy signal abstraction, record the divergence explicitly rather than calling it parity. Do not change active scoring or signal methods for Step 4.

## Verification sequence

1. Read guardrails and the live migration contract.
2. Record exact staged identity and candidate file hashes.
3. Inspect all imports/callers; require no engine/risk/execution/broker/scheduler/persistence wiring and no writes.
4. Run syntax compilation in memory, `git diff --cached --check`, and an added-line security/authority scan.
5. Run focused delta tests and the declared practical suite in the project interpreter with external temp roots and bytecode disabled.
6. Generate a fresh external probe for detached-record contradictions, strict Booleans, order completeness, canonical hashing, mutation bypass, and baseline-comparison scope.
7. Execute the exact probe directly, remove it and every temp root, and verify absence.
8. Recompute staged identity and cleanliness. Report PASS only if every gate closes on one unchanged identity.

A test-selection mistake is reviewer/setup evidence, not a candidate defect. Correct only the external invocation, clean its temp root, and rerun against the unchanged candidate. Preserve the distinction in the final receipt.

## HOLD repair handoff

A useful HOLD must name the exploit, affected invariant, exact evidence, and next safe RED→GREEN action. Do not edit the candidate during independent review. Require a new staged tree/diff and fresh review after repair.