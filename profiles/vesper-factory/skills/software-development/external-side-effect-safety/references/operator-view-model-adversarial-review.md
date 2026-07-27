# Adversarial review of pure operator view models

Use this when a read-only dashboard derives operator states such as `HUMAN_GATE`, `COMPLETE`, `WORKING`, or `CURRENT` from normalized evidence. A pure model can still fail open even when it has no I/O or execution caller: a false-green display changes operator decisions.

## Decision-gate matrix

For any state that indicates a pending human decision:

1. Define one shared canonical grammar for IDs and bounded text, and use it across gate, receipt, source, and objective logic. IDs should require an exact built-in `str`, a nonempty allow-listed form, and rejection of edge/repeated whitespace, tabs, newlines, NUL, DEL, unhashable values, and subclasses. Do not let two blank IDs match.
2. Treat action and scope as immutable envelope fields. Compare exact canonical values produced by the upstream adapter; do not case-fold, strip, or collapse whitespace inside the resolver, because that widens malformed evidence into a match.
3. Principals need a canonical identity grammar, not merely edge trimming or `casefold()`. Probe whitespace-equivalent spellings such as one space, repeated spaces, tabs, and newlines; none may create apparent principal separation.
4. Require authority fields with identity checks (`approval_granted is False`, `execution_authorized is False`), not generic falseyness. Reject `0`, `None`, empty strings, and containers.
5. Validate the complete source posture before reading its state: exact source and enum types, canonical timestamp/reason/provenance fields, parseability, and freshness. A `FRESH` source must have a nonempty parseable observation time that is neither future nor outside its declared freshness window; `SourcePosture(FRESH, observed_at="", reason="", provenance="")` and `SourcePosture(FRESH, observed_at=[], reason=0, provenance={})` are malformed, not fresh. Probe the complete source object through both the page constructor and every authority-signaling resolver—a validator that permits empty timestamps for `MISSING`/`ERROR` must not accidentally permit them for `FRESH`.
6. Canonical action, scope, reason, and provenance text must reject every Unicode category `C` character, not only ASCII C0/NUL/DEL. Probe invisible format controls such as U+200B ZERO WIDTH SPACE and bidi controls in both expected and observed values; exact equality between two malformed strings must never create `HUMAN_GATE`.
7. Convert malformed input and malformed decision collections to the closed domain state (`BLOCKED`, `UNKNOWN`, or `UNAVAILABLE`) without raising. Exercise `None`, lists, subclasses, surrounding whitespace, control characters, case changes, stale/expired evidence, hostile clocks, and mismatched scope.
8. Keep display attestations separate from execution authority. A truthful `HUMAN_GATE` still grants no mutation permission.

A useful direct probe should show one canonical valid request reaching `HUMAN_GATE`; every malformed, padded, mismatched, stale, expired, self-decided, or authority-bearing request must remain closed with no exception.

## Receipt and task-evidence totality

Treat completion and contradiction fields as security-sensitive evidence:

- Require `completion_verified is True`; `1`, `"true"`, and arbitrary truthy objects are not verification.
- Require exact built-in `False` where authority is hard-closed; falsey impostors are malformed.
- Validate `status`, run status, block kind, step key, schema error, and expected action/scope before any `.strip()`, `.split()`, or `.casefold()` call.
- A malformed or falsey non-string `schema_error` must fail closed rather than disappear.
- Padded `needs_review` is malformed evidence and must not fall through to `COMPLETE`.
- Contradictory completion evidence must fail both the display resolver and the verified-receipt predicate.

## Duplicate and malformed identity inventory

Never resolve task evidence with `{id: resolved_state}` if duplicate IDs are possible; last-write-wins can hide contradictory evidence.

- Group valid records by ID and preserve duplicate identity as an ambiguity.
- A duplicated root remains visible even when every record claims completion.
- A duplicated root is never selected as the unique objective.
- Empty, padded, control-bearing, unhashable, or subclass task IDs must never enter inventory or become current; return a closed malformed-evidence result without indexing a mapping by that value.
- Validate the task collection and parent mapping boundary before grouping so malformed containers cannot raise. Require the declared built-in collection/mapping shapes and recursively validate every parent value before calling `.get()` or testing truthiness. Probe `None`, list-vs-tuple substitution, a mapping whose `.get()` raises, falsey malformed values such as `[]`, truthy strings, malformed keys, and parent-ID subclasses. Every malformed graph must return an explicit closed result—never select a root, hide the inventory, or leak an exception.
- Test both input orders and a bounded Cartesian product of meaningful states. Assert exact inventory and selection cardinality, not one example.

## Immutability and hashability

If any rendered model is promised immutable or hashable:

- Treat `@dataclass(frozen=True)` as shallow only. Validate exact built-in scalar/tuple types recursively for every nested field; reject subclasses, lists, dicts, sets, mutable source metadata, and NaN/infinity.
- Probe every rendered layer, not only the signature carrier: mutate a list retained as a card tuple field, decision action/scope, page source field, and top-level `source_errors`/page collection after construction. Construction must reject the value, defensive-copy it into a canonical tuple, or the object must remain unchanged.
- Prove `hash(card)`, `hash(decision)`, `hash(page)`, and `hash(full_view_model)` where those objects are advertised hashable; `hash(page.signature)` alone is insufficient.
- Include hostile-but-type-compatible values such as a `str` subclass with `__hash__ = None`, and malformed nested source metadata. A validating child object does not make an unchecked parent recursively safe.

## Parser exception matrix

For untrusted timestamp/numeric normalization, probe `TypeError`, `ValueError`, and `OverflowError`, plus booleans, huge integers, NaN/infinity, naive datetimes, hostile numeric subclasses, and exact built-in `datetime` objects carrying hostile `tzinfo` implementations. Guard both expiry parsing and the resolver's `now` conversion. A resolver that advertises fail-closed behavior must return the closed value rather than let conversion or `astimezone()` exceptions escape.

## Frozen-candidate evidence

- Pin base and candidate SHA before inspection and again after the final probe.
- Read the entire base-to-candidate diff, then separately inspect the prior-candidate-to-current delta.
- Run committed tests, but do not infer adversarial closure from green regressions; use independent probes that are not added to the candidate.
- Keep pytest temp/cache/bytecode outside the repository and use a native same-drive Windows basetemp when applicable.
- Report each requested invariant as closed or open, list any newly discovered defect separately, and block integration on any false-green or malformed-input escape.
- A failed frozen SHA stays rejected. Add regressions first, create a successor commit, and re-review the full `base..successor` range; never amend or relabel the rejected SHA as reviewed.
- After repeated failures, simplify or remove the authority-signaling surface instead of adding permissive normalization.
- Review documentation as evidence: distinguish current implementation from target contracts, record failed reviews accurately, and never let a descriptive engineering record promote itself into governance authority. Cross-check enumerated pages, states, and ownership against the governing plan rather than only proofreading prose; duplicated pages or a changed page count are contract drift. Reproduce claimed test counts when practical, but treat green counts as separate from semantic claims such as “complete source validation,” “strict grammar,” or “immutable models”—independent counterexamples make those claims inaccurate even when every committed test passes.
