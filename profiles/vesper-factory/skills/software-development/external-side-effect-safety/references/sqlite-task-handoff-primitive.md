# SQLite Atomic Task-Handoff Primitive

Use when one backend owns both an upstream task/receipt stream and the downstream task table, and a caller must not compose two separate CLI writes.

## Contract

A single handoff key binds immutable input:

- source task ID;
- downstream title/body/assignee/workspace;
- receipt body and author.

One backend write transaction must either persist all of:

1. one destination task;
2. one source-task receipt comment;
3. source/destination audit events;
4. one durable `task_handoffs` binding row;

or persist none of them.

Identical replay returns the original destination-task ID and source-comment ID without writes. Any changed field under the same key is an error, not a second handoff.

## SQLite implementation pattern

- Add a dedicated `task_handoffs` table keyed by `handoff_key`, with source/destination/comment identifiers and every immutable input required for replay comparison.
- Make additive schema creation repeat-safe; exercise an existing database upgrade explicitly.
- Acquire `BEGIN IMMEDIATE` before reading the handoff key. Read-before-transaction idempotency is race-prone.
- Validate the source exists and is not archived inside the transaction.
- Insert destination task, receipt comment, ordinary events, and binding row using the same connection.
- Let any failure before commit escape the transaction context so rollback removes every earlier insert.
- Do not claim, dispatch, approve, or change source lifecycle state as part of routing.

## CLI boundary

Expose a narrow structured command with required explicit arguments and JSON-only success output. Require absolute workspace paths. Failures must emit no success JSON and have a nonzero **process** exit status. Test both the installed-console-script contract (`sys.exit(main())`) and `python -m ...`; returning an error from a leaf handler is insufficient if the top-level entrypoint discards it.

## Minimum adversarial proof

- first handoff;
- identical replay;
- same-key mismatch;
- missing and archived sources;
- injected exception after each earlier insert but before commit;
- two or more concurrent connections/callers with one key;
- fresh legacy-database schema upgrade;
- actual temporary-home CLI probe checking exact table counts.

For a verified implementation/review sequence, retain the candidate SHA before and after tests. If broad platform tests have existing failures, reproduce the same command against the exact base and compare failure identities before classifying a result as a candidate regression.

## Adoption boundary

An atomic routing primitive proves durable orchestration only. Keep semantic evidence verification, independent technical review, attestation, and all execution/Ship authority in their separately governed layers. Install or activate the backend candidate only with explicit authorization; do not test the primitive against an active production board while proving it.