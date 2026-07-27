# Shadow Evidence: Local Integrity vs. Independent Append-Only History

## Trigger

Use when a research-only system wants to persist deterministic decisions such as forecast → target → proposed delta → attribution, especially on Windows.

## Boundary discovered

A JSONL ledger plus a checkpoint/anchor in the same writable evidence root can detect accidental corruption and divergence from a previously trusted tip. It **cannot** prove immutable or append-only history against an actor able to rewrite both files. Do not describe that design as tamper-proof, immutable, or independently append-only.

Before implementation, identify the independently administered checkpoint medium and ownership model. Viable examples:

- WORM/object-lock storage with separate credentials;
- a signing/HSM-backed append-only service;
- an operator-held signed checkpoint log retained independently.

A same-host sidecar, same-account ACL, or an HMAC key stored beside the ledger is not independent anchoring.

## Required semantic-envelope pattern

Persist canonical replay inputs, not merely a serialized derived plan plus its digest. On append, verification, and recovery:

1. Strictly bounded-parse the envelope, rejecting duplicate keys and noncanonical framing.
2. Reconstruct typed input objects.
3. Re-run the existing deterministic builder.
4. Require the rebuilt plan, signal snapshot, and attribution digests to equal the persisted expectations.
5. Derive signals through an explicit adapter from the production representation (for example an enum-backed `SignalAction`), instead of trusting untyped action strings.

## Choose the smallest truthful pre-anchor store

When no independent anchor has been selected and chronology is not itself required, prefer a flat **content-addressed record store** over a JSONL ledger/checkpoint/state-machine design:

- one canonical, semantically replayable envelope per `<sha256>.json` leaf;
- deterministic hash-sorted recovery with no chronology claim;
- exact retries are idempotent;
- every successful result is explicitly `PENDING_ANCHOR`, `local_integrity_only=True`, `independently_anchored=False`, `append_only_history=False`, and `immutable_history=False`.

Do not add sequence numbers, predecessor links, mutable manifests, colocated anchor files, or transaction databases merely to make the design look ledger-like. Those are justified only when ordered history is an actual requirement and their recovery complexity is fully tested.

For a content-addressed store, the publication boundary must be derivation-closed:

1. Replay the supplied typed envelope before serialization.
2. Serialize canonical bounded bytes.
3. Strict-decode those exact staged bytes into fresh typed objects and replay again **before publication**.
4. Hash and re-read through the same verified handle, flush the file handle, then publish no-replace relative to the pinned root handle.
5. Reopen by verified handle, rehash, strict-decode, and replay before returning success.

A replay error after rename/publication is too late: it can leave an invalid committed-looking leaf behind. Add a failure-injection test proving semantic rejection leaves no published `.json` entry.

Recovery is all-or-nothing. Any unexpected direct child, malformed or unexplained owned-looking temp, oversized entry, hash/name mismatch, reparse/hard-link ambiguity, noncanonical bytes, or semantic replay failure must return `RECOVERY_BLOCKED` with **no partial trusted entries**. Preserve ambiguous bytes for operator inspection; never silently ignore or delete them. Read at most `MAX_BYTES + 1` before parsing.

Happy-path and idempotency tests alone are not an acceptance gate. Include unexpected-leaf, orphan-temp, invalid-preexisting-destination, post-write replay failure, concurrent-publisher, bounded-read, and root/child swap probes before review.

## Ledger commitment (only when ordered history is required)

If the approved requirement genuinely needs ordered local history, hash a single canonical entry containing sequence, predecessor hash, and envelope digest. A predecessor pointer outside the entry commitment permits splice/substitution attacks. Keep the colocated checkpoint labeled as local consistency evidence, never an independent anchor.

## Crash protocol

Use a durable state machine rather than treating an anchor mismatch as permanently corrupt:

```text
PREPARED → LEDGER_DURABLE → ANCHOR_CONFIRMED → FINALIZED
```

After local append but before external anchor confirmation, return `PENDING_ANCHOR`; retry the exact idempotent checkpoint on recovery. Any non-prefix history, semantic replay failure, or conflicting anchor is `HELD`; never repair by rewriting history.

## Windows containment

Path checks alone (`resolve`, `is_symlink`, reopen-by-path) do not close junction/reparse/TOCTOU risks. Keep a verified directory handle, open each ledger/journal/lock/temp child relative to it, reject reparse points and alternate streams, and operate on the verified handles. Treat a broad legacy evidence subsystem as design evidence only; extract the minimal containment adapter rather than importing unrelated database/worker/runtime authority.

## Minimum adversarial tests

- semantic rehash/rewrite of target, price, position, pending-order, constraint, signal, and attribution fields;
- predecessor/sequence/envelope splice, reorder, truncation, and duplicate-entry probes;
- independent-anchor divergence and idempotent same-checkpoint retries;
- failures at every durable transition, including anchor timeout after ledger flush;
- root and child symlink/junction/reparse/ADS plus ancestor/child swap probes;
- concurrent writer and stale-lock process probes;
- strict parser bounds, duplicate keys, invalid UTF-8, NaN, and missing terminal newline.
