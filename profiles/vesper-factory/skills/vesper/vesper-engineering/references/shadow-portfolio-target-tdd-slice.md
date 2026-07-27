# Inert shadow portfolio-target TDD slice

Use this pattern for Step 3 of the forecast → portfolio → risk → execution migration: construct portfolio targets in memory while preserving the existing signal/order path unchanged.

## Authority boundary

- The target is research-only and shadow-only.
- Deny execution, risk, broker, and persistence authority explicitly in the closed schema.
- Do not import or call engine, signal, order, risk, broker, scheduler, persistence, or configuration code.
- Do not wire the target into runtime paths, submit deltas, or change active thresholds, sizing, risk limits, data, models, or manifests.
- Keep the current signal/order path behaviorally unchanged.

## Raw-score prerequisite

The legacy top-N entry rule compares the model's direct prediction with `entry_threshold`. A cross-sectional z-score is not a truthful substitute.

Before building targets:

1. Add `raw_model_score` to the frozen forecast record.
2. Give it fixed truthful semantics such as `raw_score_units="standardized_forward_return_label_score"` when the training label is the cross-sectional standardized forward-return label.
3. Preserve the existing cross-sectional `standardized_score` as a separate field.
4. Reject nonfinite raw and standardized scores.
5. Propagate the direct model output into every generated forecast without altering legacy signals.

Prove this prerequisite in its own RED → GREEN cycle before adding target code.

## Minimal target behavior

- Rank forecasts by `raw_model_score` descending, then symbol ascending for deterministic ties.
- Eligibility is strict: `raw_model_score > entry_threshold`.
- Select the first `top_n` eligible forecasts.
- Assign equal weight `1 / selected_count`; if none qualify, all target weights are zero.
- Emit zero-weight lines for remaining approved forecasts with explicit reasons such as `outside_top_n` or `below_or_equal_entry_threshold`.
- Carry raw and standardized forecast contributions separately.
- Keep confidence unavailable unless supported by evidence.
- Keep estimated cost unavailable unless an explicit numeric cost rate plus current weights and portfolio value make it derivable.

## Closed provenance schema

Bind at minimum:

- common forecast as-of and valid-until timestamps;
- canonical eligible-forecast-set SHA-256;
- holdings and cash snapshot SHA-256 identities;
- portfolio value and current holdings weights;
- transaction-cost assumption identity and optional explicit rate;
- universe, classification, and constraint identities;
- target-generation version;
- `top_n` and `entry_threshold`;
- per-symbol weight, notional, reason, contributions, confidence, and cost;
- turnover, gross/net exposure, concentration, selected count, and blocked/infeasible diagnostics;
- explicit research/shadow/no-authority fields.

Use frozen, slotted records and revalidate forecast records at the consumer boundary because ordinary frozen dataclasses can be bypassed with `object.__setattr__`.

## Validation and deterministic diagnostics

Reject:

- empty forecast sets, duplicate symbols, mixed common provenance, or mismatched as-of/valid-until values;
- unknown symbols or universe identity mismatches;
- malformed SHA-256 identities;
- nonfinite or nonpositive portfolio values;
- nonfinite thresholds or cost rates, negative cost rates, and invalid `top_n` values (including booleans);
- holdings outside the universe, nonfinite/negative/>1 weights, or holdings weights summing above 1.

For long-only targets, compute:

- `gross_exposure = Σ |target_weight|`;
- `net_exposure = Σ target_weight`;
- `concentration = max |target_weight|`;
- cash-aware one-way turnover: `0.5 × (Σ |target_asset-current_asset| + |target_cash-current_cash|)`.

The cash term prevents underreporting turnover when moving between cash and invested assets.

## Strict TDD sequence

1. Forecast raw-score RED → GREEN.
2. Target module import/behavior RED → GREEN.
3. Add vertical tests for strict threshold, deterministic ties, equal weights, zero-weight reasons, turnover, and optional costs.
4. Add rejection tests for malformed, mixed, stale/mismatched, nonfinite, out-of-universe, and holdings-bound inputs.
5. Add executable inertness/non-mutation checks.
6. Rerun forecast, target, and legacy signal tests together, then the practical non-GUI suite.

If a test expectation is mathematically wrong (for example, cash-aware turnover), correct the test openly and rerun; do not distort production logic to satisfy it.

## Independent adversarial acceptance probes

A green builder suite is not sufficient for accepting the exact staged candidate. Run a fresh external probe against the reviewed index and fail closed on any of these conditions:

1. **Input/output binding:** build two targets with different current holdings but the same holdings-snapshot identity. The contract must not permit different turnover or target economics under an indistinguishable snapshot identity. Bind normalized holdings/cash content into the immutable target or verify supplied identities against canonical content.
2. **Complete liquidation accounting:** include a current holding that has no eligible forecast. If its target is implicitly zero, require an explicit zero-weight target line (or an equivalently complete closed aggregate) and include its liquidation in estimated transaction costs. Turnover may not include a trade that cost evidence silently omits.
3. **Cost-assumption binding:** changing the numeric cost rate while reusing the same assumption identity must reject unless the identity is externally rooted and demonstrably covers that rate.
4. **No caller self-authorization:** a caller-generated universe plus a matching caller-generated hash is self-consistency, not approval. Bind the consumer to the reviewed compatibility manifest or another frozen approval root.
5. **Public-schema invariants:** instantiate or `dataclasses.replace` exported target/line records directly. Reject negative portfolio value, rate, turnover, exposure, concentration, target weights/notionals, or selected count; invalid `top_n`; impossible selected-count/line relationships; and contradictory blocked/infeasible/diagnostic states. Builder-only validation does not make a public dataclass truthful.
6. **Rank coherence:** reject forecast ranks that disagree with deterministic raw-score ordering, including duplicate or skipped ranks when rank is part of the provenance-complete record.
7. **Canonical numeric hashing:** semantically equivalent values such as `1` and `1.0` (and signed zero where applicable) must not create different canonical forecast-set identities. Normalize typed numeric fields before hashing and domain-separate the hash payload/schema version.
8. **Mutation bypass:** continue reconstructing frozen forecast records at the consumer boundary and probe `object.__setattr__` tampering.

Report these separately from authority closure: a target can be perfectly inert yet still be rejected for untruthful portfolio or provenance semantics.

## Freeze and fresh ad-hoc evidence

- Stage only the authorized source/test paths; do not commit unless requested.
- Require no unstaged changes, `git diff --cached --check`, syntax checks, focused tests, practical full tests, and added-line security scans.
- Record staged tree ID and staged binary-diff SHA-256.
- After final staging, generate a fresh external `hermes-verify-*.py` with `tempfile.mkstemp`, execute direct changed behavior, verify exact staged paths plus no unstaged changes, unlink it in `finally`, and assert cleanup.
- Label this output as ad-hoc evidence, not canonical suite evidence.
- Any later source/test/staging change invalidates the prior ad-hoc receipt; rerun it. If nothing changed but a reviewer requests a fresh receipt, rerun the disposable verifier against the same staged tree/diff and report both identities.
