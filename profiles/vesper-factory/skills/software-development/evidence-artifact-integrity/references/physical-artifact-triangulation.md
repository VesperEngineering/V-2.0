# Physical Artifact Triangulation

Use this during final acceptance of receipt-backed workflows. It catches cases where every individual validator is green but different physical copies of the “same” artifact carry different bytes.

## Failure class

A producer emits multiline LF bytes and computes their SHA-256. A durable write helper opens the destination without binary mode on Windows, so the on-disk copy receives CRLF bytes. The lifecycle records the pre-write hash, the evaluator parses the text-equivalent JSON successfully, and the finalizer later builds a valid receipt from the original producer file. Schema, deterministic-evaluation, receipt, and focused-test gates can all pass while the durable candidate is not the candidate named by the receipt.

A compact one-line JSON fixture will not expose this failure because it contains no newline to translate.

## Required cross-copy matrix

For every required artifact, independently read and hash each applicable surface:

| Surface | Required check |
|---|---|
| Producer/worker output | Raw bytes and SHA-256 |
| Durable lifecycle artifact | Raw bytes equal producer/receipt bytes; SHA-256 equal durable binding |
| Receipt payload | Embedded bytes rehash to claimed artifact hash |
| Lifecycle row | `candidate_sha256` / `evaluation_sha256` equals the actual durable file |
| Lifecycle event | State-specific `external_id` equals the actual durable file hash |
| Review packet | Candidate/evaluator/receipt hashes equal the same physical files |
| Ledger | Receipt/candidate/contract identity matches the accepted receipt exactly |
| VOT/operator projection | Reads the validated artifact set rather than an isolated self-consistent receipt |

Do not stop after proving any one column. A valid worker file does not prove the durable copy, and a valid receipt does not prove its companions.

## Minimal read-only probe

```python
from hashlib import sha256

producer = producer_path.read_bytes()
durable = durable_path.read_bytes()
embedded = receipt["candidate"]["bytes_utf8"].encode("utf-8")

facts = {
    "producer_sha256": sha256(producer).hexdigest(),
    "durable_sha256": sha256(durable).hexdigest(),
    "embedded_sha256": sha256(embedded).hexdigest(),
    "producer_equals_durable": producer == durable,
    "durable_equals_embedded": durable == embedded,
}
assert producer == durable == embedded
assert facts["durable_sha256"] == receipt["candidate"]["sha256"]
assert facts["durable_sha256"] == lifecycle_row["candidate_sha256"]
```

For SQLite evidence, do not assume URI `mode=ro` is physically side-effect free: on Windows, a WAL-mode database can still create `-shm`/`-wal` sidecars beside the source. Under a strict no-source-mutation boundary, inventory the source directory, copy a proven closed/checkpointed database to approved external scratch, and inspect the copy. For active databases, use the official read-only surface or an approved consistent snapshot including WAL state. `immutable=1` is safe only for a proven frozen/checkpointed database with no unapplied WAL; otherwise it can omit current rows. Never instantiate a store class whose constructor issues `PRAGMA journal_mode`, DDL, migrations, or directory creation during a read-only audit.

## Writer fix

Use binary mode for every content-addressed write:

```python
flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
fd = os.open(path, flags, 0o600)
try:
    os.write(fd, encoded)
    os.fsync(fd)
finally:
    os.close(fd)
if path.read_bytes() != encoded:
    raise IntegrityError("persisted bytes differ from hashed bytes")
```

The read-back is part of the write contract, not merely a test convenience.

## Regression requirements

1. Use deterministic **multiline** bytes containing several `\n` characters.
2. Write through the exact production helper on Windows.
3. Assert raw read-back equality and SHA-256 equality.
4. Restart from the durable artifact and require exact replay, not semantic JSON equivalence.
5. Exercise the **public/top-level run entrypoint** after a receipt exists. Mutate only candidate raw bytes while preserving valid JSON semantics (append a newline or change LF to CRLF), then invoke the exact same run identity and require `HELD`. A controller-only replay test does not cover a receipt-present fast path that returns before the controller runs.
6. Repeat the public replay probe for the evaluation artifact and every other contract-required companion.
7. Run the same cross-copy probe against one real evidence bundle; unit fixtures alone are insufficient.

## Canonicalization boundary

Tracked source/input text may deliberately use an explicitly contracted `crlf_to_lf` profile. Generated candidates, evaluations, receipts, review packets, and ledgers are still raw-byte-bound unless their own schema explicitly includes them in that canonicalization scope. Never extend a tracked-text profile to generated evidence by implication.

## Disposition

Any mismatch between producer, durable artifact, receipt, event/state, review packet, or ledger is a concrete release `HOLD`. Do not waive it because the logical JSON objects compare equal or because a focused suite is green. Repair the writer/validator, preserve the contradictory bundle as historical evidence, and rerun the complete proof chain on the repaired exact source SHA.
