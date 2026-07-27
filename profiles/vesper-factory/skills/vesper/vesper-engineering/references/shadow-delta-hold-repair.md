# Step 4 shadow-delta HOLD repair pattern

Use this after an independent review rejects an inert proposed-delta candidate for detached-schema contradictions, weak Boolean typing, incomplete pending-order evidence, or narrow signal-parity claims.

## Repair contract

Keep the repair inside the inert planner and its tests. Do not add engine, broker, risk, execution, persistence, scheduling, or order-submission wiring. Preserve the existing base commit and freeze a new staged identity only after all repairs and verification pass.

## RED → GREEN slices

### 1. Detached line truthfulness

Write direct `dataclasses.replace()` regressions against an exported line before changing production code. A detached line must reject:

- `delta_notional` different from `target_notional - current_notional`;
- `delta_weight` different from `target_weight - current_weight`;
- tolerant near-misses hidden by `math.isclose` when the contract requires exact arithmetic;
- integer values in fields declared as strict floats;
- non-finite or negative target/current values;
- zero actionable quantity;
- quantity direction opposite to `delta_notional`;
- urgency inconsistent with positive, reducing, closing, or zero quantity;
- blocked/suppressed reasons paired with a nonzero quantity or wrong outcome.

For exact detached arithmetic, compare canonical float representations (for example `float.hex`) after recomputing the expression. Do not use an approximate helper intended for portfolio reconciliation.

**Do not stop at sign-only quantity validation.** A line that merely checks `quantity * delta_notional > 0` can still accept an impossible rounded quantity (for example, changing 5 shares to 1,004 while preserving a $500 delta). Likewise, generic reason-class validation can accept a nonzero delta relabelled as `no_delta`, and a nonnegative cost check can accept an arbitrary estimated cost. A public detached line that claims rounded quantity, suppression reason, or estimated cost must embed enough immutable evidence to recompute those claims, including the applicable price and cost/rounding assumptions. At minimum verify:

- `no_delta` implies an exact zero delta under the declared canonical arithmetic;
- actionable quantity equals the declared lot-rounded `delta_notional / price`, not merely the same sign;
- `zero_after_rounding` and minimum-trade reasons follow from embedded price, lot size, and threshold evidence;
- `estimated_cost == abs(quantity) * price * transaction_cost_rate`, or is `None` when the rate is unavailable;
- `dataclasses.replace()` cannot alter quantity, cost, or a reason while leaving their evidence unchanged.

If adding that evidence would make the detached record redundant or misleading, make the line non-public and expose only the enclosing plan that fully rederives it. Aggregate revalidation does not make a separately exported contradictory dataclass truthful.

The minimum coherent state table is:

| Reason class | Outcome | Quantity | Urgency |
|---|---|---:|---|
| actionable | actionable | nonzero | increase/reduce/close by sign and target |
| stale/pending/unusable snapshot | blocked | 0 | none |
| below minimum/zero after rounding/no delta | suppressed | 0 | none |

### 2. Strict authority/status scalars

Python collapses `1 == True` and `0 == False`. Validate public authority and status fields before content comparison:

```python
if type(blocked) is not bool:
    raise ValueError("blocked must be a bool")
```

Audit every public Boolean/integer scalar on the changed schema, including quantities and lot size. Prefer `type(value) is int` where subclasses and Booleans are invalid. Add parametrized `replace()` tests for every authority Boolean.

### 3. Pending-order completeness and provenance

An empty tuple is not proof of a complete broker observation. Make the builder require explicit order-state evidence rather than defaulting missing input to known-empty:

- closed completeness state: `complete | partial | ambiguous`;
- order snapshot `observed_at`;
- externally carried account identity SHA-256 claim;
- externally carried source snapshot identity SHA-256 claim;
- immutable pending-order observations.

Bind all five components plus `as_of_timestamp` into the internally computed snapshot digest. Label account/source values as external claims; their syntax and inclusion are validated, but the planner does not grant them authority.

Only fresh `complete` evidence may permit actionable proposals. `partial`, `ambiguous`, and stale snapshots must block every line with zero quantity and a truthful plan diagnostic. A fresh `complete` snapshot with an empty observation tuple represents authoritative known-empty state and may proceed. Missing completeness or identity arguments should fail construction rather than silently becoming complete.

Validate exact types and hashes on direct construction and `dataclasses.replace()`. Include digest-sensitivity tests for account identity, source snapshot identity, completeness, and observation time.

### 4. Real-strategy comparison scope

Invoke the real `MLModelStrategy.generate_signals` and replace only scoring. Cover at one timestamp with one universe and price set:

1. empty holdings and positive top-N entries;
2. a selected holding that target construction resizes while the signal path does not re-buy it;
3. a held symbol inside `exit_rank` but outside target top-N;
4. a held symbol outside `exit_rank` that produces a CLOSE signal and a negative closing delta.

Do not call all four cases “parity.” Record intentional abstraction differences explicitly:

- the signal path selects top-N **unheld candidates**, so a held selected name can cause another entry candidate to appear;
- the portfolio target may resize an existing selected holding;
- `exit_rank` can retain a holding that strict target top-N closes.

The comparison proves shared ranking behavior and documents divergence; it does not make the target layer identical to the legacy signal abstraction.

## Verification and freeze

1. Run the focused test file and retain RED and GREEN outputs separately.
2. Run the practical project suite with the project interpreter, bytecode disabled, and an external native Windows `--basetemp`; apply the declared worker-monitor exclusion exactly.
3. Compile changed Python source in memory and run `git diff --check`.
4. Scan added lines for credentials, shell execution, deserialization, SQL, filesystem writes, and forbidden authority imports.
5. Run a fresh ad-hoc verifier from an OS-safe `tempfile.mkstemp(prefix="hermes-verify-", suffix=".py")` path. It should exercise detached replacements, completeness states, stale state, provenance digest sensitivity, and held-position comparison.
6. Remove the verifier, assert its path is absent, and keep verifier exit and cleanup status separate.
7. Stage exactly the declared paths. Require no unstaged or untracked files.
8. Record branch, HEAD/base, staged tree, binary-diff SHA-256, staged file hashes, and staged path set. Do not commit unless separately authorized.
9. Recompute tree/diff identity after the ad-hoc verifier; any change invalidates prior evidence.

### Disposable verifier execution and derivation-closed dataclasses

Create the verifier itself with `tempfile.mkstemp(prefix="hermes-verify-", suffix=".py", dir=<OS temp>)`, execute that concrete file directly with the project interpreter and `PYTHONDONTWRITEBYTECODE=1`, then unlink it and assert absence. Do not substitute an inline orchestrator whose nested subprocess output is the only evidence: verification tooling may not recognize that as a canonical ad-hoc test. If a status gate explicitly reports that no canonical verification command was detected, rerun a fresh concrete verifier rather than merely restating earlier test output. Confirm any earlier scratch paths are absent before freezing the candidate identity.

For a public derivation-closed dataclass, make every claimed output `field(init=False)` and tag it explicitly (for example, `metadata={"derived_claim": True}`), while leaving it included in enclosing content hashes. Keep only immutable evidence as constructor inputs and recompute all quantities, reasons, costs, urgency, and outcomes in `__post_init__`. Python 3.11 `dataclasses.replace()` raises `ValueError` when asked to override an `init=False` field; direct construction with that derived keyword raises `TypeError`. Test both boundaries, plus evidence replacement that must recompute truthful outputs. If a detached line carries a declared blocker that cannot validate external freshness or order state independently, require the enclosing aggregate to rederive and reject arbitrary blocker evidence.

### Windows quoting pitfall for disposable verifiers

A generated Python source string containing `C:\Users\...` can fail before the verifier runs because `\U` begins a Unicode escape. Inside generated source, use a forward-slash path such as `C:/Users/...` or correctly double-escape backslashes. Treat this as a quoting retry pattern, not evidence that temporary verification is unavailable.
