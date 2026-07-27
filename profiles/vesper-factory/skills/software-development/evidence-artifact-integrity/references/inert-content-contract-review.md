# Adversarial review of inert, content-addressed contracts

Use for frozen in-memory records such as forecasts, portfolio targets, plans, proposed deltas, and research-only authority envelopes. “No side effects” does not make a schema truthful or tamper-evident.

## Content roots

- Embed the complete immutable source projection needed to recompute every material digest; a digest plus derived lines is insufficient.
- When upstream data has an independently reviewed identity (model manifest, universe, feature schema), carry that rooted identity into every descendant rather than accepting an actual/expected pair from the same caller.
- Distinguish external provenance claims from verified content bindings. A single carried source hash can be honest metadata, but must not be described as self-verification.
- Bind actual holdings, cash, costs, constraints, prices, and order observations whenever their values drive output. Compute their hashes internally.

## Canonicalization

- Type-tag booleans, integers, floats, strings, sequences, and mappings.
- Never canonicalize integers through binary64. Values above `2**53` can collide.
- Keep exact integer fields (ranks, counts, limits) as tagged decimal strings.
- Normalize semantically floating fields first, then encode with `float.hex()` when `1` and `1.0` should be equivalent.
- Domain-separate nested payloads and use unambiguous framing; test reordered inputs and delimiter/collision cases.

## Public child schemas

Every exported frozen dataclass must independently reject contradictory state. Do not rely only on the enclosing aggregate to catch mutation.

For fields that are pure derivations—delta arithmetic, rounded quantity, classification reason, urgency, cost, status—prefer `field(init=False)` and compute them in `__post_init__` from immutable evidence inputs. This removes caller authority over the claims and makes `dataclasses.replace()` recompute truth instead of accepting a detached override. The enclosing aggregate must still recompute external blocker/completeness evidence from its full snapshots and reject a child whose declared evidence differs.

Probe `dataclasses.replace()` against:

- digests and embedded source snapshots;
- raw/standardized contributions;
- current, target, and delta arithmetic;
- reason, status, urgency, and authority combinations;
- costs, turnover, exposure, concentration, and selected counts;
- Boolean fields replaced with `0` or `1`;
- line classification changed from forecast-backed to no-forecast/liquidation.

Require exact scalar types (`type(value) is bool` / `type(value) is int`) before equality or membership checks.

## Completeness and ambiguity

An empty observation collection is not proof of an authoritatively empty external state. Snapshot schemas should include:

- explicit completeness (`complete`, `partial`, `ambiguous`);
- observation time;
- source/account identity claims where applicable;
- a content-derived snapshot digest.

Only a complete snapshot may enable an actionable shadow classification. Partial or ambiguous state blocks action-like proposals even when the record remains research-only.

## Portfolio and delta specifics

- Emit lines for the union of forecast symbols and current holdings so liquidation is visible.
- Cover liquidation in turnover and cost calculations.
- Validate ranks as unique, contiguous, and consistent with the declared deterministic sort.
- Proposed-delta lines must independently prove `target - current = delta`, coherent rounded quantity, minimum-notional classification, and reason/outcome/urgency consistency.
- Keep comparison evidence honest: separate true parity from intentional architectural divergence (for example, a target may resize a held position while a legacy signal path emits no signal).

## Review sequence

1. Write RED tests for direct construction and `dataclasses.replace()` before production fixes.
2. Freeze the exact staged tree and binary diff digest.
3. Run focused and practical suites outside protected repositories when fixed-root writers exist.
4. Dispatch an independent reviewer with every previous HOLD exploit listed explicitly.
5. Integrate only the unchanged reviewed tree; any restaging invalidates the verdict.
