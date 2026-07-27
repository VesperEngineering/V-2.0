# Protected Data Admission with Ignored Runtime Artifacts

Use this pattern when a governed repository must admit one exact local data artifact while keeping large/protected runtime data ignored by Git and committing only validator, integration, tests, and a machine-readable receipt.

## Authority boundary

Before writing anything, freeze the exact approval envelope:

- source artifact path and read-only status;
- one canonical destination path;
- allowed code, test, and receipt paths;
- explicit denials for data refresh, model training/replacement, provider calls, broker/execution, risk, scheduler, configuration, paid compute, and unrelated cleanup;
- required test and independent-review gates.

A provenance admission is not authority to train, promote, backtest broadly, or execute.

## Byte-identical transfer

1. Hash and size the source with bounded streaming reads.
2. If the destination already exists, hash it first. Accept only an exact match; never silently overwrite different bytes.
3. Copy bytes without parsing, normalizing, reserializing, or regenerating.
4. Read back destination size and SHA-256 and require `source == destination == declared`.
5. When the artifact is Git-ignored and the candidate uses an isolated worktree, keep the canonical approved copy in the canonical checkout. A temporary worktree-local copy may be used for candidate tests, but it is not the authority recorded by the receipt.
6. Verify `git check-ignore` and prove the large artifact is not staged/tracked.

## Strict loader shape

A fail-closed loader should validate in this order:

1. file exists/readable;
2. raw-byte SHA-256 equals one pinned accepted digest;
3. JSON/object parsing rejects duplicate keys at every nesting level (for Python JSON, an `object_pairs_hook` can reject both duplicate tickers and duplicate dates before dictionary collapse);
4. root is a non-empty object;
5. ticker keys are non-empty and normalized exactly as required by the universe contract;
6. every ticker map is a non-empty object;
7. dates are canonical ISO dates, not merely loosely parseable strings;
8. factors are exact numeric scalars excluding booleans, strings, nulls, zero, negatives, NaN, and infinity;
9. every required universe symbol is present; report valid extras separately.

Missing, malformed, mismatched, empty, or incomplete evidence must abort before feature/label/evaluation work.

## Adjustment behavior contract

Specify and test all boundary semantics rather than inheriting assumptions:

- which price columns are adjusted;
- explicit volume treatment;
- pre-first-factor behavior;
- post-last-factor behavior;
- no-split series unchanged;
- input frames not mutated;
- approved training/evaluation entry points invoke the shared loader and adjustment exactly before features, labels, or diagnostics.

Use RED → GREEN slices for missing evidence, hash mismatch, schema, coverage, factor behavior, and entry-point ordering. Keep integration tests bounded with faked model/feed boundaries; never train merely to test the gate.

## Tracked immutable receipt

The ignored artifact should have a small tracked JSON receipt. Complete the receipt **before dispatching the final reviewer**. At minimum bind:

- receipt schema/version and creation time;
- exact approval reference and false authority flags;
- source path, bytes, hash, and honest provenance statement;
- canonical destination path, bytes, hash, and byte-identical transfer method;
- input database/snapshot identity;
- universe path, count, and hash;
- feature/loader/training/diagnostic code hashes;
- source/base commit and policy version;
- runtime versions;
- exact validation counts, date range, missing/extra coverage, and factor semantics.

Avoid circular identity: bind the base/source commit plus exact code-file hashes (or a staged tree/diff digest), rather than trying to embed the receipt's own future commit hash.

## Verification and review order

1. Verify receipt fields against real canonical files and current candidate code.
2. Run focused tests, adjacent scoped tests, compile/lint where available, `git diff --check`, and an added-line security scan.
3. Stage only the exact allowlist; require no tracked unstaged candidate changes.
4. Bind the frozen candidate with staged paths, staged tree, and SHA-256 of `git diff --cached --binary`.
5. Dispatch independent review against that exact frozen identity.
6. **Any receipt, test, or code change after dispatch invalidates the verdict.** Re-run affected gates, re-freeze, and obtain a fresh review. The common avoidable mistake is reviewing code first and creating the required receipt afterward, which forces a second review.
7. Integrate into a dirty canonical checkout only after proving every target path is clean in both index and worktree. Preserve unrelated dirt; never use stash/reset/broad checkout or broad add commands.
8. Re-verify canonical artifact hashes, receipt parity, tests, model hashes, and exact dirty-state preservation after integration.

## Pitfalls

- A clean worktree lacking ignored databases is not proof the canonical input is missing. Verify canonical existence and identity explicitly.
- Do not let a receipt claim an alternate database merely because it lives near the source artifact; bind the actual database consumed by the admitted V20 pipeline.
- A top-level `PASS` or `accepted` label is not enough. Every decision-critical claim must be recomputable from bound bytes and code identities.
- Keep temporary test roots external and same-drive on Windows; clean only roots created by the task.
- Do not record unknown producer history as fact. State provenance limitations honestly and rely on exact observed path/hash/bytes.
