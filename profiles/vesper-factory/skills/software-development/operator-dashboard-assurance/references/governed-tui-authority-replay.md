# Governed TUI authority replay and immutable review

Use this reference when an operator dashboard or TUI records approvals, exposes issue actions, renders provider accounting, or is reviewed while its canonical branch is advancing.

## Durable authority invariants

### Configured labels are not authenticated principals

An identity loaded from `.env`, process configuration, a CLI flag, or a local preferences file is an attribution label unless a separate authentication mechanism proves possession or identity. It may support an append-only review **attestation**, but it must not set either of these projections true:

- `approval_granted`
- `execution_authorized`

Keep status and authority separate. A record may say `status=approved` to preserve the operator's selected disposition while also saying `approval_granted=false` and `execution_authorized=false`. UI copy should call this an attestation or recorded intent, not an authenticated grant.

### Replay must derive authority, never trust it

Append-only replay code must not deserialize authority booleans as trusted state. If the current system has no authenticated authority mechanism:

1. Require serialized authority flags to be exactly `false`.
2. Reject missing, non-boolean, or `true` values as malformed evidence.
3. Construct the in-memory projection with literal `False` values.
4. Keep execution admission separately locked even after an approve attestation.

Minimal adversarial regression:

1. Create one valid request event.
2. Change only `approval_granted` or `execution_authorized` to `true` without changing request fields or request hash.
3. Replay the ledger.
4. Require replay to fail closed and produce no execution receipt.

Do not assume a request hash protects later decision or authority fields unless those fields are explicitly part of the authenticated/hash-bound envelope.

## Visible review before mutation

A two-stage governed action requires a real render boundary:

1. First key press selects the exact row and sets the review overlay state.
2. Normalize the selected identifier.
3. Explicitly invalidate/redraw the application.
4. Only a later key press while that overlay is active may mutate state.

Changing the controller state without invalidating is not proof the operator could see the review surface. Test with a fake application whose `invalidate()` increments a counter; after the first key, require overlay active, zero mutations, and one invalidation. Then require the second key to mutate only the reviewed identifier.

Probe the controller boundary independently of normal key dispatch. Call every mutation helper directly while the overlay is absent—including internal/private issue-start helpers, not only public approve/reject/execute methods—and require zero ledger or registry mutation. A green two-Enter dispatcher test can otherwise coexist with a helper that explicitly falls back to an embedded selection when `overlay is None`.

Hidden, clipped, or vertically truncated queues must remain non-actionable. Complete action, scope, and reason values must fit, scroll, or otherwise be explicitly exposed before approve/reject/execute keys become active.

## Minimum review geometry is an authority contract

Derive admission from the **actual minimum overlay body**, not the outer terminal size. Count fixed rows (header, IDs, timestamps, warning, status, footer) and reserve only the remaining rows for governed values. If the minimum body is `80×19` with 12-column field labels, value wrapping has 68 terminal columns; simultaneous field limits must fit the remaining row budget, not merely pass separate character caps.

Use one shared wrapper for both request validation and rendering:

1. Reject tabs, newlines, ANSI/control characters, and other non-display input before request hashing or ledger append. Do not let `textwrap` silently expand or normalize them differently later.
2. Measure terminal columns (`wcwidth`, Prompt Toolkit `get_cwidth`, or an equivalent), not Python code-point length. CJK/emoji may consume two columns and combining marks may consume zero.
3. Preserve exact accepted text while wrapping by columns. The validator should count the wrapper's output rows; the renderer should render those exact rows.
4. At the minimum supported geometry, reconstruct every accepted action/scope/reason from rendered rows and require the closed-authority warning, status line, and action footer to remain present and within bounds.
5. For malformed direct snapshot objects, render a non-actionable `REVIEW UNAVAILABLE` surface rather than crashing or showing partial review controls.

Regression fixtures should include simultaneous maximum ASCII fields, medium words/spaces, a tab/control payload that writes no ledger or checkpoint, and wide Unicode whose Python length fits but terminal width does not. If scrolling is chosen instead of a combined row budget, decision keys must remain disabled until the complete entry has been explicitly exposed.

## Complete-event integrity and suffix truncation

A request hash covers only request fields. Hash complete events—including status, event kind, actor, time, decision reason, and authority flags—and link each event to the previous hash. This catches field changes, head deletion, and reordering, but **not tail deletion**: a shortened log is still a valid hash-chain prefix.

To detect suffix truncation, persist a separate chain checkpoint with at least:

- verified event count;
- current head hash;
- a checksum over those checkpoint fields.

Safe append ordering is: validate current log and checkpoint → append event → flush/fsync the event → atomically replace the checkpoint. Replay must reject a log with a missing checkpoint, a checkpoint without a log, count/head mismatch, malformed checkpoint, stale checkpoint after append, or any broken event link. A crash between event append and checkpoint replacement intentionally leaves evidence unavailable rather than silently rolling forward.

Probe request plus decision, then independently modify decision metadata, delete the head, delete only the final event while retaining the checkpoint, reorder events, and remove the checkpoint. Every replay must fail closed. Be precise about the guarantee: a local checkpoint detects ordinary truncation and partial writes; it is not authenticated identity and cannot prove against coordinated deletion or recomputation of both local files.

## Authority language is executable policy

Audit command help, overlay footers, status messages, protocol docstrings, diagrams, and runbooks together. If local labels only record attestations and the execute function always denies, operator-visible text must say `record attestation` and `check closed execution gate`. Phrases such as `grant exact action`, `execute`, or `run approved action` create false authority even when code remains locked. Add a focused help test and a repository-wide stale-wording scan.

## Provider numeric fail-closed boundary

Provider payload validation must reject more than malformed strings:

- booleans;
- negative values;
- fractions in integer fields;
- `NaN` and infinities;
- integers too large for `float()` (`OverflowError`);
- finite rows whose aggregate overflows to infinity.

Validate finiteness after **every arithmetic layer**, not only during field conversion. Exercise at least:

1. one huge JSON integer that overflows `float()`;
2. two individually finite rows such as `1e308 + 1e308` whose sum becomes infinity; and
3. a finite total whose elapsed-time rate calculation overflows.

For each failed observation, assert the returned snapshot is stale, all last-good fields are unchanged, and the cache bytes or parsed object are identical before and after. A conversion-only test does not certify aggregate or derived-rate safety.

Normalize conversion and post-arithmetic failures to the service's malformed-payload error type. The fetch boundary must then return the exact sanitized last-good snapshot as stale and must not overwrite its cache.

## Stale reconciliation is a data-flow assertion

A `STALE` prefix is necessary but not sufficient. Preserve the last-good account total for display, but capture or spy on the value passed into receipt reconciliation and require it to be `None`/unknown. The derived unattributed amount must render `unknown`; subtracting current receipt attribution from an old account total manufactures a persuasive number even when the line is labeled stale.

During commit review, compare the parent and candidate versions of focused tests. If a test changes from asserting `reconciliation(account_total=None)` and `unattributed unknown` to checking only a stale label, treat that weakened assertion as a regression signal even when the claimed suite remains green.

## Immutable review when canonical advances

For a long independent review, freeze and record:

- candidate `HEAD`;
- candidate parent;
- candidate tree hash;
- clean porcelain status;
- stable patch ID.

The reviewer must assert HEAD, parent, tree, and clean status both before and after probes. If the candidate changes, the review fails closed.

If canonical advances during an otherwise valid review:

1. Do not mutate the tree being reviewed.
2. Let the reviewer finish its behavioral assessment against the frozen candidate.
3. Inspect the parent-to-new-canonical changed paths for overlap.
4. Rebase only after review completion.
5. Recompute the stable patch ID; require it to match when only the base changed.
6. Rerun focused and full verification against the rebased candidate.
7. Require a final lightweight attestation against the exact rebased HEAD/parent/tree before merge or push.

A matching patch ID proves the feature diff survived an unrelated base rewrite; it does not prove the final whole tree is deployable. The final tree still needs tests and exact-hash attestation.

## Closure checklist

- [ ] Environment/config identity described as label or attestation, not authentication.
- [ ] Authority flags are false by construction and tampered true values reject.
- [ ] Execution remains separately unavailable and writes no receipt.
- [ ] First governed key opens, normalizes, and redraws review; second key mutates.
- [ ] Direct controller mutation helpers deny calls while the relevant overlay is absent.
- [ ] Admission and rendering use one terminal-column wrapper; control input writes no evidence and wide Unicode fits the minimum viewport.
- [ ] Every accepted minimum-viewport review shows complete governed values, closed-authority warning, status, and footer before controls activate.
- [ ] Complete events are hash-linked and a verified head/count checkpoint rejects field edits, reordering, head deletion, and tail deletion.
- [ ] Huge/non-finite provider fields, aggregate sums, and derived rates preserve the byte-identical last-good stale cache.
- [ ] Stale account totals remain display-only; reconciliation receives unknown and renders unattributed usage unknown.
- [ ] Parent-to-candidate test changes do not weaken fail-closed assertions into label-only checks.
- [ ] Help, docs, protocol copy, and UI use attestation/closed-gate vocabulary consistently.
- [ ] Reviewer asserts immutable state at start and finish.
- [ ] Canonical movement is reconciled by rebase + patch ID + fresh final verification.
