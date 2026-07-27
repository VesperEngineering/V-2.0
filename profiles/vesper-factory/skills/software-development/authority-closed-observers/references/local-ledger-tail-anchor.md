# Local JSONL tail-anchor checkpoint

Use for a bounded local append-only evidence ledger when replay must reject isolated suffix deletion.

## Protocol

- Store a second bounded JSON artifact beside the JSONL, containing exactly `schema_version`, `entry_count`, and `final_hash`.
- Under the existing interprocess writer lock, reload and validate both ledger and anchor before creating a new entry.
- Atomically replace the JSONL, then atomically replace the anchor, using unique temp files and fsync. A failure between replacements must return unavailable and intentionally leave the pair mismatched; never repair or compact it in the resident path.
- Replay requires a strict anchor whenever the ledger exists. Reject missing, malformed, oversized, type-invalid, tampered, count-mismatched, or final-hash-mismatched anchors. Reject an anchor when no ledger exists.

## Required regressions

1. Delete the final valid JSONL line while retaining the anchor → unavailable.
2. Truncate the entire JSONL while retaining the anchor → unavailable.
3. Missing, malformed, and structurally valid but mismatched anchors → unavailable.
4. Interrupt the second publication in an append → append unavailable and later replay unavailable.

## Security boundary

This detects isolated ledger suffix deletion or truncation. It cannot prevent an actor with local write authority from coherently deleting or rolling back both ledger and anchor files. Claim no stronger anti-rollback property without an independent immutable/external store.
