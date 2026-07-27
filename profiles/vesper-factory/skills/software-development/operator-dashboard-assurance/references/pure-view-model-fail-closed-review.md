# Pure Operator View-Model Fail-Closed Review

Use this reference when an operator dashboard derives work state, objectives, completion, pending decisions, or authority posture from external evidence. The model should be pure and I/O-free; adapters own reads, and separate action handlers own writes.

## Boundary rule

Treat Python type annotations as documentation, not runtime validation. Every externally derived field can be malformed, type-confused, duplicated, padded, contradictory, stale, or adversarial.

A pure resolver must be **total** over malformed evidence: return a fail-closed state (`UNKNOWN`, `BLOCKED`, `UNVERIFIED`, or unavailable) rather than raising or manufacturing green.

## Completion and receipt admission

`COMPLETE` and verified action receipts require all of:

- recognized closed status;
- explicit verified-completion evidence;
- no schema or parse contradiction;
- no `needs_review` or equivalent unresolved review state;
- no duplicate/conflicting record for the same task identity.

Do not maintain separate predicates that disagree about whether work is complete. If separate display and receipt predicates are necessary, test their consistency explicitly.

## Duplicate identity handling

Never resolve records into `dict[id] = state` before checking uniqueness. That creates last-write-wins trust and can hide contradictory evidence.

1. Group records by identity first.
2. Mark every duplicate identity unsafe regardless of order.
3. Keep unsafe roots visible in inventory.
4. Do not select duplicated identities as the current objective.
5. Probe both record orders and combinations of complete, malformed, review, and unverified states.

## Exact pending-decision binding

A `HUMAN GATE` is an operator-facing claim. Require one exact, fresh request bound to the task's expected contract:

- every identifier/text field is the exact built-in `str` type;
- IDs are nonempty and have no leading/trailing whitespace;
- status is exactly the allowed request state;
- task ID, action, and scope equal the task's expected values exactly;
- requester and required decider are canonical, nonempty, and distinct;
- source posture is exact, recognized, and fresh;
- expiry parses safely and is strictly in the future;
- approval/execution fields are exact built-in `bool` values and both are literally `False` when identity is unauthenticated.

Do not case-fold, trim, collapse whitespace, or otherwise normalize malformed authority evidence into validity. Normalize at a trusted producer boundary, then validate exact values at the view-model boundary.

Malformed evidence—including `None`, lists, mappings, padded values, hostile subclasses, and falsey non-booleans—must return `BLOCKED` without an exception.

## Recursive immutability and hashability

A frozen dataclass is not deeply immutable. For signatures/cache keys:

- admit only exact built-in canonical scalar types plus recursively exact tuples;
- reject mutable containers, non-finite floats, and scalar/tuple subclasses;
- validate every field that contributes to whole-object hashing, not only the signature;
- hash the complete intended object tuple during construction and convert hash failures into a clear validation error;
- adversarially test unhashable subclasses in IDs and nested source metadata.

## Total timestamp parsing

Use exact-type branches for accepted `datetime`, `int`, `float`, and `str` values. Reject subclasses unless they are intentionally supported.

- Reject booleans, naive datetimes, non-finite numbers, empty strings, and unknown objects.
- Catch `OverflowError`, `TypeError`, `ValueError`, and platform timestamp errors where conversions can raise.
- Require timezone-aware UTC-normalizable values.
- Probe huge integers, NaN, infinities, hostile numeric subclasses, hostile datetime/tzinfo inputs, and future-skew boundaries.

## RED fixture matrix

Before repair, reproduce each issue with focused tests:

- unverified closed task;
- closed task with schema contradiction;
- closed task requiring review;
- duplicate same-ID roots in both orders;
- blank/padded/case-changed decision fields;
- mismatched expected action/scope;
- same or whitespace-equivalent principals;
- stale/expired/malformed source and expiry;
- `0`, `None`, and other falsey non-boolean authority flags;
- hostile scalar/container subclasses;
- huge and non-finite timestamps.

Then run focused tests, adjacent dashboard/System Spine tests, compilation, lint, secret/forbidden-I/O scans, and diff checks.

## Immutable independent review loop

Freeze an exact candidate SHA and keep canonical integration blocked during review. A review failure is not an appendix: add regressions, repair, rerun focused and adjacent gates, update the engineering ledger with the rejection and remediation, freeze a new SHA, and re-review the full base-to-candidate diff. Never reinterpret a partial pass as permission to integrate.

## Documentation truth

Keep engineering documents descriptive. Distinguish current production behavior from target contracts, record missing callers/wiring explicitly, and never let a new document promote itself above repository governance or create authority by assertion.
