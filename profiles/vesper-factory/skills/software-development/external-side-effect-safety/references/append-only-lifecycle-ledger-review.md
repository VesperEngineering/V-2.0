# Append-Only Lifecycle Ledger Review

Use this probe matrix for JSONL/event ledgers with transitions such as `PENDING -> CLOSED`, especially when exact replay is suppressed and concurrent writers are supported.

## Required invariants

1. Hold one OS process-safe lock across the complete `read -> parse -> validate history -> decide -> append -> flush/fsync` critical section. A process-local mutex or thread-only test does not prove this boundary. On Windows, also serialize same-process contenders through a per-resolved-ledger-path thread mutex **before** taking `msvcrt.locking`; concurrent byte-range locks from many threads in one process can raise `EDEADLK`/`Resource deadlock avoided`. The thread mutex prevents that local failure, while the OS lock remains necessary for independent processes.
2. Validate the **entire pre-existing ledger before returning an exact-replay result**:
   - every nonblank row parses and has the exact allowed schema/state domain;
   - duplicate `(immutable identity, lifecycle state)` pairs are rejected globally;
   - all rows sharing an immutable identity agree on every field except the lifecycle state;
   - historical state order is monotonic and complete (for example, `CLOSED` cannot precede or exist without `PENDING`).
3. Only after full-history validation may the incoming operation be classified as exact replay, legal forward transition, or rejection.
4. A malformed historical row must block even an unrelated append. Otherwise a writer can extend a ledger whose integrity is already unknown.
5. Authority-bearing fields are immutable identity fields. A lifecycle transition must not change approval, execution, promotion, account, scope, actor, or decision fields. Compare canonical JSON bytes (sorted keys, fixed separators, NaN forbidden) or perform recursive exact-type comparison; ordinary Python equality is unsafe because `False == 0` and `True == 1`.
6. Validate **physical JSONL framing** inside the writer lock. A valid final row may omit its terminal newline. Before appending, inspect the last byte: either reject noncanonical framing without changing bytes or write a separator before the new canonical row. Never concatenate `{row1}{row2}\n` and return success. After every successful append, reparse every physical line and assert the expected row count.

## Adversarial probes

Run all probes in a fresh, uniquely named external temporary directory for that review attempt and assert exact row counts plus byte preservation on rejection. Never share or reuse probe paths across concurrent reviewers: stale rows can turn the expected first `True` into `False` and produce misleading race results.

| Probe | Required result |
|---|---|
| Fresh PENDING, then exact PENDING | first append `True`, replay `False`, one row |
| Fresh PENDING, then exact CLOSED | two rows in `PENDING, CLOSED` order |
| CLOSED on an empty ledger | rejection; no ledger row created |
| PENDING, then CLOSED with one payload/authority field changed | rejection; bytes unchanged |
| Two pre-existing identical `(identity, state)` rows | rejection for both same-identity and unrelated incoming appends |
| Pre-existing PENDING plus payload-mutated CLOSED, then replay PENDING | rejection, not `False`; an early replay return must not mask the later corrupt row |
| Pre-existing CLOSED followed by incoming PENDING | rejection; never append a backward “repair” transition |
| Non-state identity field changes JSON type, e.g. `false` to `0` or `true` to `1` | rejection; bytes unchanged |
| Valid existing final row has no terminal newline, then an unrelated valid append occurs | two separately parseable physical rows, or fail-closed with bytes unchanged; never concatenated JSON |
| Twelve same-process threads racing one exact append on Windows | exactly one `True`, all others `False`, no `EDEADLK`, one physical row |
| Eight spawned processes racing one exact append | exactly one `True`, all others `False`, zero errors, one physical row |

Use **both** threads and spawned processes on Windows. The thread race catches `msvcrt` same-process `EDEADLK`; the spawned-process race proves independent writers serialize through the OS lock. A thread-only pass can still hide a broken process boundary.

## Exact-candidate pinning during review

Capture `HEAD`, tree identity, status, and a hash of the exact reviewed delta before probes, then capture them again afterward. Define the reviewed artifact as a declared **baseline-to-current, path-limited binary diff**, not merely `git diff HEAD`: if an uncommitted patch is committed during review, `git diff HEAD` becomes empty even though the candidate bytes are unchanged.

A reproducible recipe is:

```bash
git diff --binary --no-ext-diff "$BASE" -- path/one.py path/two.py > "$SCRATCH/exact.diff"
sha256sum "$SCRATCH/exact.diff"
wc -c < "$SCRATCH/exact.diff"
git diff --name-only "$BASE" --
```

Repeat the command after probes and gates, compare the patch files byte-for-byte, and verify the path set. If an uncommitted delta is edited, staged, committed, rebased, or otherwise moves while review is running, do not silently carry the old verdict forward. Re-identify the final commit/range, re-read the resulting safety diff, and rerun the focused suite and adversarial probes against the final `HEAD`. An unchanged baseline-to-current patch hash can prove that an uncommitted delta became an identical commit, but report the final state accurately rather than claiming the diff is still uncommitted.

## No-authority-widening check

For a narrow ledger-lock/history repair, supplement line-by-line diff review with an AST boundary comparison:

1. Parse the baseline and candidate modules without line-number attributes.
2. Compare the top-level function inventory.
3. Require the changed-function set to equal the intended lock/history helpers.
4. Require authority-bearing entrypoints (finalizers, submitters, approval handlers, cleanup paths) to be AST-identical.
5. Strip only the expected new lock import/globals and changed helpers, then require the remaining module AST to match.
6. Mutate each durable authority field (`approval_granted`, execution/operational authority, promotion, denied scope) across a lifecycle transition and require rejection with byte preservation.

AST comparison is supplemental, not a substitute for reading the exact unified diff: it is useful for proving that a concurrency repair did not quietly alter authority-bearing code elsewhere in the same file.
