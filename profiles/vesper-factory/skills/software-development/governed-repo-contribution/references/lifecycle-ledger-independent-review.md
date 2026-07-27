# Lifecycle-ledger independent review

Use this recipe when reviewing an append-only JSONL ledger whose rows represent a monotonic lifecycle such as `PENDING -> CLOSED`.

## Full-ledger validation must precede replay suppression

Inside the same writer lock:

1. Bound the ledger size and row count before parsing. Treat physical framing as part of validity: an empty file is allowed, but a nonempty JSONL file must end with a newline; reject blank/whitespace-only records and parse objects with duplicate-key detection. Never silently skip a physical row.
2. Validate required row types/states and reject duplicate `(receipt_id, state)` identities.
3. Group all rows by receipt while preserving ledger order.
4. For every receipt history, compare all non-state fields using canonical JSON bytes, not Python object equality. Python considers `False == 0` and `1 == 1.0`; that can silently accept a JSON scalar-type mutation.
5. Require an exact allowlist of state histories, for example only `[PENDING]` or `[PENDING, CLOSED]`.
6. Only after every history is valid may code inspect the caller's matching receipt, suppress an exact replay, enforce CLOSED-first rejection, and append.

The key invariant is global: a matching replay or an unrelated new receipt must never return before corruption elsewhere in the ledger has been rejected.

## Required adversarial matrix

Use external scratch and assert rejection preserves ledger bytes/hash:

- valid `PENDING -> CLOSED`;
- exact PENDING and CLOSED replay (both no-op, bytes unchanged);
- matching replay when a later CLOSED row changed a non-state field;
- unrelated append over that corrupted history;
- pre-existing reverse `CLOSED -> PENDING`;
- missing terminal newline followed by a distinct append attempt (must raise and preserve bytes; never produce `}{`);
- embedded blank or whitespace-only physical records;
- duplicate JSON object keys as well as duplicate lifecycle rows;
- CLOSED-first on an empty ledger;
- JSON scalar-type mutation such as `false -> 0`;
- concurrent exact append from both threads and spawned processes.

For exact concurrency, expect exactly one writer result of `True`, all others `False`, one final row, and no worker error. A repeated stress round is valuable because a single barrier run can miss lock contention defects.

## Windows thread plus process locking

A Windows `msvcrt.locking` byte-range lock is an interprocess primitive, but many same-process threads can intermittently raise `OSError: [Errno 36] Resource deadlock avoided` under contention. Layer locks in this order:

1. obtain/create a process-local `threading.Lock` keyed by the canonical resolved lock-file path under a small registry guard;
2. acquire that thread lock;
3. open and acquire the `msvcrt` byte-range lock;
4. validate the full ledger and append while both are held;
5. release in reverse order.

Keep the path key canonical so aliases do not obtain distinct thread locks for the same byte-range lock. Stress with at least 12-16 threads and separately with spawned processes. Treat a one-off passing thread test as insufficient after an observed contention failure.

## Triangulate real worker, reviewer, and scheduler identities

Do not certify identity from fields inside a receipt or review result alone. Corroborate independent evidence planes read-only:

1. Read the live board task and complete run history. Match task ID, creator, role/profile, workspace, requested branch, status/outcome, and exact run ID. A completed task may clear its `current_run_id`; use the immutable run-history row rather than treating a null current pointer as missing evidence.
2. Resolve the run's session ID from run metadata, then read the named profile's session store. Require a real session row, model/provider telemetry, nonzero model/API turns, and the expected tool-call history. Worker and reviewer must be distinct task/run/session identities.
3. Verify the materialized worker and reviewer worktrees directly: exact `HEAD`, tracked-clean status, and frozen input hashes. Board branch labels and receipt assertions are not substitutes.
4. Bind the reviewer run's exact terminal claim and summary bytes to the review-result hash, then bind that result to the closure receipt and final lifecycle event.
5. For a natural one-shot scheduler proof, corroborate the scheduler execution record, captured stdout/result, wrapper bytes/hash, exact source arguments, and post-run absence from the active/disabled job registry. A self-authored `scheduler_evidence.json` is supporting evidence, not sole proof.

Prefer official read-only CLI surfaces when they expose complete records; otherwise inspect a consistent external snapshot of the board, session, or scheduler database. A nominal SQLite `mode=ro` connection can still create WAL/SHM sidecars on some platforms; do not open source evidence directly when the audit promises zero mutation. Never infer missing current state from conversation history when the live source is accessible.

## Make exact-once reviewer dispatch receipt-first

A reviewer is admissible only when its first runnable state already binds the exact candidate and pending receipt. Treat task preparation, dispatch, and review as separate phases:

1. Create the reviewer behind a **durable dependency/hold**, not merely an initial status label. Some board maintenance loops automatically promote `blocked`/`todo` cards that have no persisted blocker.
2. While the card is non-runnable, attach the pending receipt hash, exact source SHA, candidate hash, worker task/run/session, review instructions, and denied-authority fields. Materialize and verify the reviewer worktree at that exact source.
3. Re-read the live task and run history. Require zero runs, the expected assignee, exact branch/workspace, and an active blocker before lifting the hold.
4. Remove the blocker once, dispatch at most one reviewer, and require exactly one terminal run. Never retry an admissible reviewer task: a second run makes its verdict ambiguous.
5. If preparation fails and the card acquires any run row—even a `blocked` or setup-only run—archive it as **inadmissible preparation evidence** and create a fresh reviewer task ID. Do not erase or reinterpret the run, and do not let its status or log contaminate the final reviewer receipt.

A setup failure is `NO_VERDICT`, not a rejection of the candidate. The final receipt must name only the fresh exactly-once reviewer while preserving the archived setup card as historical evidence.

## Rebinding a candidate that is committed mid-review

An independent review starts by recording HEAD, status, exact changed-file allowlist, and the SHA-256 of the complete binary working diff. If another actor commits the candidate during review:

- do not report the now-empty working-tree diff as the reviewed candidate;
- record the new commit and parent;
- require the parent to equal the original baseline;
- require the commit's changed-file list to equal the reviewed allowlist;
- hash `git diff --binary --no-ext-diff <baseline>..<new-head> -- <allowlist>` and require it to equal the last reviewed working-diff digest;
- rerun the behavioral matrix and acceptance gates after the commit, because tests may inspect HEAD;
- report both the candidate patch digest and the current uncommitted-diff digest, explicitly explaining why the latter is empty.

If the patch digest differs, the old verdict is stale: inspect the successor diff and rerun the review. If the digest is identical and post-commit gates pass, the verdict may bind the exact commit while disclosing the candidate-state transition.