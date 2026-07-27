# Response Schema After Commit

Use when a transactional backend may commit before the local caller validates the response.

## Pre-live contract probe

Run once against an isolated backend/database using the actual console/module entrypoint:

1. Create a source record.
2. Invoke the exact fixed command with an immutable handoff key.
3. Decode structured stdout with strict JSON (reject nonfinite constants).
4. Inspect both returned values and durable rows. Assert the response agrees with the stored binding.
5. Replay the exact command and assert the identical destination/receipt binding and cardinality of one.
6. Send a changed immutable input under the same key; assert nonzero exit and no new rows.

Do not infer response types from test mocks. Match authoritative storage/API schema exactly. For SQLite timestamps stored as `INTEGER`, accept only positive non-boolean integers no greater than `2**63 - 1`; reject strings, floats, zero/negative values, `NaN`, and infinity.

## Post-commit local-validation failure

A local parse/binding failure after command exit uncertainty must be treated as **remote effect unknown**:

1. Stop retries immediately.
2. Read the backend by immutable handoff key and source ID.
3. If a downstream task/receipt pair exists, record the exact IDs and quarantine or archive the downstream task before it can be reviewed/dispatched.
4. Preserve the original source receipt and a recovery record; do not delete evidence or pretend the transition never happened.
5. Repair the caller with a regression reproducing the real response.
6. Obtain independent review of the repaired client.
7. Use a new candidate/workflow/source/key for a fresh bounded shadow. Never reuse the committed key or source binding for the repaired attempt.

Only report end-to-end success after both the durable backend binding and the caller’s strict validation/replay check succeed.
