# Local Non-Runnable Proposal Ledger Pattern

Use this pattern when autonomous agents may detect discrepancies and draft work, but authenticated human approval and atomic downstream task creation are not ready.

## Boundary

- Proposal generation is autonomous and non-authoritative.
- Proposal storage is local operational state, not an approval or execution ledger.
- Do not expose `approve`, `review`, or downstream-task creation commands until actor identity is authenticated and the task handoff is atomic.
- Every authority field remains exact built-in `false`; never reconstruct unsafe durable values as safe defaults.

## Data model

Separate immutable proposal identity from repeat observations:

- `planning_proposals`: immutable canonical proposal payload keyed by deterministic proposal ID.
- `proposal_observations`: append-only sightings with `observed_at` and `recorded_at`.

Exclude changing observation timestamps from identity comparison. A later observation of the same discrepancy appends a sighting instead of causing an identity conflict.

Store and replay the complete canonical schema. Validate exact field sets, types, text bounds, control characters, status/class values, and every authority flag on both append and replay. Reject extra fields rather than silently dropping them.

## SQLite discipline

- Missing database on read means an empty queue and must not create directories or files.
- Existing empty/malformed database means `UNAVAILABLE`; do not initialize or repair it from a read path.
- Use SQLite URI `mode=ro` for list/VOT reads.
- Initialize schema only inside an explicit write transaction.
- Validate the complete allowed `sqlite_master` object set, not just table columns: reject unexpected triggers/views/indexes; verify column names, affinities, nullability, defaults, and primary-key order; require the intended non-partial unique index with exact column order/origin; and verify the complete foreign-key definition.
- Run `PRAGMA foreign_key_check` and reconcile parent/child cardinality during replay. An inner join can silently hide parent proposals with no observations, and declared foreign keys do not prove existing rows are valid when another writer used `foreign_keys=OFF`.
- Bind redundant identities explicitly: the table primary key, observation foreign key, and `proposal_id` embedded in canonical JSON must agree exactly. Validating the embedded ID grammar alone is insufficient.
- Validate every durable proposal and observation, including historical rows that are not selected as the latest state. Reject hidden/orphan rows and databases whose durable count already exceeds the configured bound.
- Check event/observation limits before insert.
- Build the returned record inside the committing transaction; avoid a fallible post-commit reread.
- Explicitly close every connection on Windows.
- If a bounded batch partially commits, report committed IDs and the ID being attempted when failure occurred.

Unexpected triggers are especially important: a trigger can rewrite canonical payload or identity between insertion and the transaction-derived return query while a column-only schema validator still reports success.

An unkeyed hash chain inside the same writable database is not deletion-resistant. Do not claim tamper evidence against final-row deletion, suffix truncation, or database replacement without a separately trusted tail/count checkpoint or authenticated signature.

## Path and source safety

- Production write CLI must bind to the canonical project root.
- Check the original unresolved root and every relevant component for symlink/junction/reparse indirection before calling `resolve`; resolving first erases evidence that the caller supplied a reparse path. Then separately prove that the resolved destination is contained by the canonical root.
- Reject reparse indirection at the root, ledger directory, and database path. Checking only `.hermes` and the final database does not reject a junction used as the supplied or canonical root.
- Treat pathname validation followed by `sqlite3.connect(path)` as a check/open race: another local process can replace the checked directory or file with a junction between those operations. Where containment is a security property, prefer handle-based/no-follow opening or verify the opened handle's canonical target before mutation.
- Keep dry-run/list paths provider-free and mutation-free. If the shared dashboard loader normally fetches provider accounting or writes usage caches, add an explicit local-only switch and test that the provider loader is never called.

## Shadow-only fallback

Use a zero-write shadow phase when authenticated identity, atomic task handoff, or a structurally safe persistence primitive is missing.

- Keep deterministic, bounded proposal generation and hard-false authority fields.
- Expose no `record`, `list`, `review`, `approve`, publish, dispatch, or scheduler mode.
- Disable provider accounting explicitly rather than assuming a dashboard read is local-only.
- Prove the real canonical invocation creates no database/cache files and changes no repository-local operational state.
- If independent reviews repeatedly uncover new ledger-integrity or path-containment defect classes, count that as architecture failure rather than an invitation to add another layer of local checks. Remove the ledger and every surface that implies durable pending work; preserve only the independently useful shadow generator.
- Treat the reduced shadow implementation as a new candidate: restage it, recompute its diff hash, rerun focused and adjacent tests, and obtain a fresh review. Earlier verdicts do not transfer across the scope reduction.

Persistence can return only behind a backend transaction, handle-based/no-follow storage primitive, or other mechanism that closes the stated threat model without caller-side check/open races.

## UI truthfulness

- Pending proposals may be displayed in VOT and listed through a Telegram-compatible read CLI.
- Malformed/unavailable ledger evidence must render `UNAVAILABLE` with review/execution authority closed—not `(none pending)`.
- Do not label an unauthenticated actor string as approval.

## Minimum regression matrix

1. Repeat identical observation is idempotent.
2. Later timestamp for same discrepancy appends cleanly.
3. Changed canonical payload under same ID fails.
4. Any true/non-boolean authority flag fails before file creation.
5. Extra/malformed durable fields fail replay.
6. Leading/trailing/embedded controls fail before normalization.
7. Missing read performs zero writes; empty/malformed DB remains byte-for-byte unchanged.
8. Limit is enforced before commit and ledger remains readable.
9. Connections close immediately on Windows.
10. Concurrent first-use writers retain one valid schema and all rows.
11. Canonical-root and reparse-path bypasses fail before snapshot loading or writes.
12. Partial batch reports committed and attempted IDs.
13. Real canonical dry-run creates no ledger DB, calls no provider, and changes no local state.
14. A valid embedded proposal ID that differs from the table key fails replay and makes the UI unavailable.
15. Parent-without-observation, observation-without-parent, and malformed historical observation rows all fail replay instead of being hidden by the current-state query.
16. Unexpected trigger/view/index objects and a partial unique index are rejected as noncanonical schema.
17. `PRAGMA foreign_key_check` is clean, complete durable counts stay within bounds, and replay validates every durable row rather than only rows selected by an inner join.
18. A junction at the supplied root or canonical root is rejected; where the threat model includes a competing local process, exercise or structurally close the reparse swap between validation and open.

For staged fail-closed reviews, hash the exact staged byte stream (for example, `git diff --cached --binary --no-ext-diff | sha256sum`), inspect staged file contents with `git show :path`, run adversarial probes only against temporary roots outside the repository, and recompute the digest before issuing the verdict. Passing unit tests do not override a demonstrated fail-open probe.
