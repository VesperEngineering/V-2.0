# Exact-source final gate and natural scheduler provenance

Use this recipe when an implementation is already frozen and the only remaining acceptance gates are fresh focused tests/lint, delayed-expiry adversarial behavior, one natural unattended scheduler run, and opening/closing drift proof. It is designed for a strict **read-only outside unique external scratch** audit.

## 1. Freeze exact source without mutating the source repository

1. Create one unique scratch root outside the repository and evidence roots.
2. Make an independent clone in scratch at the exact source SHA. Do **not** use `git worktree add`: that writes worktree metadata into the source repository.
3. Set `GIT_OPTIONAL_LOCKS=0` for reads against the governed checkout.
4. Record source `HEAD`, `HEAD^{tree}`, branch, porcelain-v2 status, working/cached diff hashes, and the exact commit path list.
5. Require the governed checkout and scratch clone to have the same exact SHA/tree and clean tracked state. Independently compare physical bytes for the touched and gate-critical files; this catches checkout/canonicalization surprises that a tree ID alone does not explain.

## 2. Phase the scratch evidence

Use restartable outputs such as:

- `logs/` — exact pytest, Ruff, probe, and provenance output;
- `scheduler/` — copied SQLite stores, jobs snapshot, schema fingerprint, provenance report;
- `probes/` — fresh mutation/concurrency trees and a machine-readable report;
- `manifests/` — opening/closing source, evidence, profile, wrapper, and OS-task manifests;
- `FINAL_AUDIT.json` — one fail-closed rollup that revalidates every preceding result.

Never place pytest cache, bytecode, copied databases, or mutation probes in the governed checkout. On Windows set `TMPDIR`, `TEMP`, `TMP`, `PYTHONPYCACHEPREFIX`, and `PYTHONDONTWRITEBYTECODE`; use `-p no:cacheprovider`.

## 3. Run fresh gates exactly

- Run the user-specified focused pytest command from the exact scratch clone with the project interpreter and external temp roots. Preserve full output and exit status. If using `tee`, explicitly test the producer's `PIPESTATUS[0]`; otherwise redirect output and inspect it afterward.
- Run critical Ruff selectors on the exact touched/gate files. Derive touched paths from the exact commit and expand only existing gate-file globs. Do not guess filenames. A Ruff `E902` for an absent guessed path is an audit-harness selection error, not a source defect; correct the file list, rerun, and retain the setup attempt separately from the final gate.
- A final report must state the exact command, selectors, count, exit status, and log hash—not merely “tests passed.”

## 4. Fresh 13-probe delayed-expiry matrix

A compact matrix can cover the required boundary without duplicating the full unit suite:

1. brand-new expired contract is rejected for admission;
2. exact completed receipt replays after expiry with unchanged receipt and companion bytes;
3. crash after deterministic evaluation resumes after expiry using one frozen contract, with unchanged candidate/evaluation bytes and no duplicate lifecycle events;
4. future-issued contract is rejected even when a durable lifecycle row exists;
5. missing, hash-chain-corrupt, and wrong-contract-hash lifecycle variants all fail reconciliation (three subcases in one probe);
6. raw candidate-byte mutation after expiry returns `HELD` and is not repaired;
7. persisted semantic evaluation mutation after expiry returns `HELD` and is not repaired;
8. receipt mutation fails closed;
9. lifecycle-event mutation fails closed;
10. full-ledger identity mutation fails closed and remains unmodified by the attempted replay;
11. barrier-synchronized thread duplicates yield exactly one initial producer and one durable artifact/event set;
12. spawn-process duplicates yield exactly one initial producer and one durable artifact/event set;
13. authority-denial/tool widening is rejected, while a valid run retains every literal false authority field.

For concurrency, allow contenders either to observe the single-instance lock (`HELD`) or to replay after the winner releases it; require exactly one `PASS` with `replayed=false`, one candidate, one evaluation, one receipt, one ledger row, and the exact expected event count. Persist each probe's outcome and failure traceback in one JSON report and fail the phase unless all 13 pass.

## 5. Prove natural scheduler provenance, not just a manual run

1. Inventory the scheduler directory before touching SQLite.
2. Copy the execution database to scratch before opening it. If WAL is zero and the database is checkpointed, copy the main file. If WAL is active, copy the main database, `-wal`, `-shm`, and jobs file as one stable set:
   - hash/stat the source set before copy;
   - copy all members to matching scratch basenames (`copy.db`, `copy.db-wal`, `copy.db-shm`);
   - hash/stat the source set again;
   - accept only when before/after states and copied hashes agree; retry boundedly otherwise.
3. Open only the scratch copy, run `PRAGMA quick_check`, discover `sqlite_master`, `table_xinfo`, and indexes, and persist a schema fingerprint before writing the target query.
4. Require exactly one target execution row with terminal-success status, no error, and bounded claimed/started/finished timestamps.
5. Bind that row to the scheduler's persisted stdout/result artifact (commonly `cron/output/<job_id>/<timestamp>.md`). Verify exact job ID/name, `no_agent` mode, the one JSON result, natural run path, `status=PASS`, `replayed=false`, and literal false execution/promotion fields.
6. Hash and AST-inspect the wrapper: exact source SHA, runner path, output root, schedule identity, timeout, captured output, and project interpreter.
7. Validate the natural receipt with exact source code. Keep logical receipt hash distinct from physical file SHA. Bind the result artifact to both, and also validate the supervised receipt named by the acceptance contract.
8. Enclose receipt lifecycle timestamps within the scheduler execution interval when both use parseable timezone-aware timestamps.
9. Re-read current `jobs.json`: the one-shot job must be auto-removed, with no active or disabled duplicate by ID, exact name, or wrapper. A separate supervisor may remain only when explicitly paused/disabled.

Do not demand whole-file equality for a live cron database or `jobs.json`: unrelated recurring jobs may advance during the audit. Compare the exact target row and semantic “no proof schedule” state instead.

## 6. Opening/closing no-drift proof

Capture and then recompute at the end:

- governed source SHA/tree/status and critical physical file hashes;
- complete per-file manifests (relative path, size, mtime, SHA-256, symlink flag) for each critical evidence directory;
- scheduler wrapper and persisted stdout artifact hashes;
- current worker/reviewer profile hashes versus the canary's exact backup files;
- semantic no-proof-schedule state and the exact target execution row;
- required Windows scheduled-task records, comparing the bounded task subset rather than the entire volatile task listing.

Compare opening and closing manifests structurally. Any source/evidence/profile/wrapper drift is a `HOLD`. Dynamic unrelated scheduler counters are not material when the exact target row and no-proof-schedule predicates remain unchanged.

## 7. Finalization

Build a machine-readable rollup in scratch that re-opens every gate artifact, asserts the expected counts/hashes/false authority fields, and records explicit non-authority (no push, broker/order, paper/live, promotion/deployment, or scheduler mutation). If the user required the response to be exactly `PASS` or `HOLD`, keep all detail in scratch and return one token only.
