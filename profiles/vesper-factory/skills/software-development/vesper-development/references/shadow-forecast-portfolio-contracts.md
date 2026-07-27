# Shadow Forecast and Portfolio Contract Verification

Use this reference for additive research-shadow migrations where an existing model must emit forecasts and portfolio targets without gaining operational authority.

## 1. Separate and name the migration gates exactly

Before reporting the active or next stage, reread the authoritative Obsidian migration sequence. Do not infer a label from the implementation idea: for example, Step 4 is **Plan**, not “Shadow” or “Persistence.” Map operator updates to the exact file, section, and numbered step.

Treat each step as a separately frozen and independently reviewed candidate:

1. **Observe** — emit immutable in-memory forecasts; do not write receipts or alter active signals.
2. **Compare** — prove exact ranking/signal parity on a frozen dataset and publish a reproducible evidence receipt.
3. **Construct** — build inert portfolio targets; do not produce deltas, orders, risk decisions, or broker calls.
4. **Plan** — generate inert proposed deltas and compare them with the current signal path; a delta is a plan, not an order.
5. **Risk parity** — prove every current deterministic risk rejection remains rejected and new ambiguity fails closed.
6. **Paper shadow** — compare proposed versus actual paper-path behavior without submitting through the new path.
7. **Cutover review** — require explicit human approval before any paper-only cutover.
8. **Retire later** — remove the direct path only after parity, recovery, rollback, and cutover evidence exist.

Durable append-only persistence is its own artifact-authority boundary; do not smuggle it into Plan merely because deltas would eventually need receipts. Likewise, do not bundle any later gate into an earlier one merely because the code is convenient.

## 2. Forecast compatibility needs an external authority root

A per-call pair such as `actual_feature_hash == expected_feature_hash` is self-authorization when the same caller supplies both values. The same defect applies to caller-supplied approved universes.

Bind stable compatibility in an independently reviewed model-companion manifest containing at least:

- exact model-artifact SHA-256;
- ordered feature schema and canonical identity;
- ordered approved universe and canonical identity;
- horizon;
- target definition.

The forecast method loads the companion internally, verifies it against the model bytes and imported feature schema, and rejects drift. Do not permit per-call or constructor overrides that can replace the accepted companion for the current champion.

Per-run values such as dataset, adjustment, or run-manifest hashes may remain carried provenance claims, but label them honestly; they are not authorization unless rooted elsewhere.

## 3. Forecast records

Use a frozen, slotted, closed schema. Recommended fields:

- schema, expert, and expert-version identity;
- symbol, exact `datetime` as-of, valid-until, freshness state;
- horizon and truthful target definition;
- raw model output plus truthful units;
- cross-sectional standardized score plus units/direction;
- deterministic rank;
- model path/hash;
- dataset, adjustment, feature, universe, and run identities;
- explicit `research_only=True`, `authority_state="shadow"`, and denied execution authority.

Reject blank/malformed hashes, nonfinite scores, invalid timestamps, stale bars, unknown symbols, and rank/order contradictions.

Preserve active signal behavior with a regression comparing the complete signal payload and rebalance state before/after scoring refactors.

## 4. Canonical hashing rules

Hashes are contracts over bytes, not labels. Specify and test the exact byte stream.

- Domain-separate different payload types.
- Sort symbols deterministically.
- Encode exact integers as type-tagged decimal strings; never cast ranks/counts/`top_n` to binary64. Values above `2**53` otherwise collide.
- Normalize semantically floating fields deliberately and encode with `float.hex()` when `1` and `1.0` should be equivalent.
- Include framing/separators or length prefixes explicitly.
- Embed the canonical projection required to recompute each digest.

Add regressions for integer collisions, ordering invariance, numeric equivalence where intended, and payload framing.

## 5. Shadow portfolio targets must be self-validating

A target cannot safely carry only a forecast-set digest. Embed the immutable validated forecast tuple (or an equivalent complete frozen projection) so `__post_init__` can recompute the digest and validate each line.

Bind actual content, not caller-minted hashes:

- normalized current holdings and cash plus internally computed snapshot hash;
- explicit transaction-cost assumptions plus internally computed identity;
- actual constraints (`top_n`, threshold, long-only, equal-weight) plus internally computed identity;
- rooted universe identity from forecasts/compatibility manifest.

Emit lines for the union of forecast symbols and current holdings. A holding absent from forecasts needs a zero target, a liquidation reason, and cost coverage when a rate is supplied. Turnover and costs must use the same union.

Public frozen dataclasses must reject contradictory direct construction and `dataclasses.replace()` states. Recompute and validate:

- digest versus embedded forecasts;
- forecast/no-forecast line classification;
- raw/standardized contributions;
- unique deterministic line order;
- selected count and equal weights;
- target notionals;
- turnover, gross/net exposure, concentration, and cost arithmetic;
- blocked/infeasible diagnostic consistency;
- all denied authority flags.

## 6. Reproducible parity receipts

A parity result is not independently reproducible unless its receipt includes:

- input row window and ordering;
- columns and data types;
- timestamp and float serialization;
- framing/separators and encoding;
- row/symbol counts;
- complete run-manifest content and canonicalization, or an immutable path plus raw hash;
- exact model, compatibility, feature, adjustment, database, and repository bindings.

If review confirms the numbers but cannot reproduce a hash, preserve the result, issue a new receipt revision with the missing serialization contract, refreeze, and re-review. Never silently rewrite historical evidence.

## 7. Independent adversarial review checklist

Before integration, freeze exact staged paths, staged tree, and binary diff hash. The reviewer should probe:

- caller self-authorization of universe/features;
- model/manifest/feature/universe drift;
- nonfinite values and stale timestamps;
- deterministic tie ranking;
- active-signal parity and rebalance nonmutation;
- file writes or imports into engine/risk/execution/broker paths;
- arbitrary digest replacement;
- contribution/reason/embedded-forecast replacement;
- missing liquidation lines/costs;
- public-schema negative/inconsistent metrics;
- integer hash collisions and representation-dependent hashes.

Any HOLD invalidates the exact staged identity. Repair with RED tests, restage only authorized paths, compute new identities, and request a fresh review.

## 8. Derivation-closed Step 4 review protocol

For a repaired **Plan** candidate whose public delta lines contain derived claims, do not accept a green suite alone. Independently prove that the exact staged candidate closes every ordinary construction and replacement path.

### Freeze and preserve the candidate

Capture these values before review and again after all tests and scratch cleanup:

- branch and HEAD/base;
- `git write-tree` staged-tree identity;
- canonical `git diff --cached --binary | sha256sum` digest;
- exact staged path set;
- zero unstaged and untracked paths;
- worktree blob hashes equal the corresponding index blob hashes.

Review the staged candidate only. A changed tree or diff digest requires a fresh review, even when the change appears harmless.

### Public-line closure matrix

For every derived delta-line field (delta weight/notional, raw and proposed quantity, reason, urgency, estimated cost, and constraint outcome):

1. Assert the dataclass field is `init=False` and absent from the constructor signature.
2. Assert direct construction cannot supply it.
3. Assert `dataclasses.replace(line, derived_field=...)` fails.
4. Assert normal attribute assignment raises `FrozenInstanceError`.
5. Replace each accepted evidence input and independently recompute the expected derived values. The object must recompute truth rather than preserve stale claims.

`object.__setattr__` is outside the conventional frozen-dataclass boundary, but enclosing aggregate revalidation must detect mutated nested evidence or contradictory line tuples when the plan is rebuilt or replaced.

### Independent arithmetic and precedence probes

Probe more than the happy path:

- transaction-cost rate `None`, zero, ordinary finite values, and overflow;
- positive and negative truncation, zero-after-rounding, exact representable bounds, and impossible quantity bounds;
- blocker precedence over no-delta and suppression paths;
- no-delta precedence over minimum-trade checks;
- raw below-minimum suppression versus post-rounding below-minimum suppression;
- close versus reduce urgency;
- strict exact types, malformed hashes/timestamps, nonfinite numbers, and boolean-as-integer attacks.

For the enclosing plan, replace blocker evidence, line tuples, snapshots, constraints, authority flags, and provenance bindings. The plan must recompute from embedded inputs and reject contradictions.

### Verification and reporting

Run the focused Step 4 tests, then a disjoint practical project slice (exclude the focused file if reporting a combined total), syntax compilation, staged-diff checks, inertness/security scans, and caller/import searches. Use task-owned external scratch and remove it before the final identity check.

A PASS report should state only the verdict, exact identity, key closure evidence, disjoint test counts, inertness/caller result, and clean final state. Any unresolved contradiction is a HOLD; never average it against passing tests.
