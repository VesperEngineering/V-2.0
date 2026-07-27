# Adversarial review of pure VOT view models

Use this checklist when reviewing a frozen VOT state/view-model candidate that claims canonical grammar, immutable models, fail-closed resolution, or non-authorizing approval semantics.

## Frozen committed-candidate gate

For a committed candidate, bind the review to:

- exact base SHA and candidate SHA;
- `merge-base` equal to the stated base;
- candidate tree ID;
- SHA-256 of `git diff --no-ext-diff --binary <base>..<candidate>`;
- clean porcelain status and zero nonignored untracked files.

Take two matching fingerprints before inspection, then repeat after source review, after long tests, and immediately before the verdict. A committed candidate at clean `HEAD` has an empty `git diff HEAD`; the base-to-candidate digest—not the empty worktree diff—is the reviewed patch identity.

## Grammar and exception-totality probes

Do not stop when common malformed values (`None`, list, dict, `0`) fail closed. Include hostile but legal Python objects:

```python
class HostileEq:
    def __eq__(self, other):
        raise RuntimeError("hostile equality")

class FalseyImpostor:
    def __bool__(self):
        return False

class StrSubclass(str):
    pass
```

For every input field, require either a canonical value or a deterministic closed result—never an exception. In particular, avoid this ordering:

```python
value == "" or is_canonical_id(value)
```

because arbitrary `__eq__` executes before the type guard. Prefer an exact-type check first:

```python
type(value) is str and (value == "" or is_canonical_id(value))
```

Exercise the same malformed field through every public consumer, not just the private validator: state resolver, verified-receipt predicate, objective selector, page constructor, and pending-decision binding.

## State-conditioned SourcePosture validation

Field-level type validation is insufficient. Validation must depend on source state. A `FRESH` source must not be canonical when `observed_at`, reason, or provenance is absent. Otherwise the following can become false-green:

- a pending decision is treated as current;
- a blocked task renders as `HUMAN_GATE`;
- a page model accepts a provenance-free fresh source.

Probe each `FRESH` field independently and all-empty together. Keep separate contracts for `STALE`, `MISSING`, `MALFORMED`, and `ERROR`; do not weaken `FRESH` merely because missing/error states legitimately lack an observation time.

If freshness is caller-derived and no universal age window exists, still require a nonempty parseable observation and provenance. Do not invent a global staleness threshold inside the pure model unless the architecture defines one.

## Authority and immutability checks

- Authority flags must be the exact singleton `False`; reject `0`, `None`, empty containers, strings, and falsey impostors.
- Reject scalar subclasses when exact canonical scalar types are required.
- Recursively reject mutable signature members and non-finite floats, then call `hash()` on the complete page model.
- Duplicate root evidence must remain visible in inventory and unselected.
- Assignment alone must never imply work; closure alone must never imply verified completion.
- Hostile `tzinfo`, numeric subclasses, datetime subclasses, huge epochs, and non-finite timestamps must return the closed result without raising.

## Evidence interpretation

Passing focused tests does not override an adversarial reproduction. Report separately:

1. direct changed-contract tests;
2. adjacent VOT/System Spine suites;
3. compile/lint/diff checks;
4. full-suite status and infrastructure/data-dependent failures;
5. adversarial probe counts and exact failures;
6. final frozen-candidate fingerprint.

If engineering documentation claims exception-total or complete source validation and an adversarial probe disproves it, cite the documentation line as a separate accuracy finding. A reproducible contract defect is `FAIL`, not a no-verdict, even when all authored tests pass.
