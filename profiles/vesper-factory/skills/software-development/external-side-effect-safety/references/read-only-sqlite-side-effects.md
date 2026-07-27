# Verifying Truly Read-Only SQLite Consumers

SQLite URI mode `mode=ro` prevents database-page mutation, but opening a WAL-mode database can still modify or create `-wal` and `-shm` sidecars through locking/shared-memory activity. A command advertised as zero-write must therefore be tested at the filesystem boundary, not inferred from connection flags.

## Verification protocol

1. Resolve the real storage root used by production defaults. Check environment-derived/global paths as well as repository-local paths; evidence limited to the repository can miss writes under a user application-data directory.
2. Snapshot existence, size, modification time, and—when practical—content hash for the database plus `database-wal`, `database-shm`, journal, lock, and temporary files.
3. Run a passive control interval of comparable duration. If files change without the command, identify the concurrent writer before attributing changes.
4. Invoke the smallest isolated read helper once and compare snapshots.
5. Invoke the complete default CLI and compare again. Disable Python bytecode and tool caches or monitor them explicitly so incidental cache writes cannot hide behind a semantic “no persistence” claim.
6. Treat any command-caused sidecar creation or modification as a write. `PRAGMA query_only` and `mode=ro` are not sufficient evidence by themselves.
7. Add an integration regression around the real default path, not only dependency-injected tests that replace the database reader.

## Safer design options

- Avoid opening the live SQLite database when the data is not needed for the read-only result.
- Consume a separately produced immutable snapshot or bounded receipt.
- If direct reads are required, choose and verify a SQLite access mode that neither writes sidecars nor sacrifices WAL visibility or consistency. Do not add `immutable=1`, `nolock=1`, or copy-based snapshots without testing concurrent-writer correctness and freshness.
- Keep temporary snapshots outside authoritative state roots and report them honestly as writes; “no authoritative persistence” is weaker than “zero writes.”

## Proposal-generator review probes

For bounded generators, validate the complete input authority contract before stopping output at the cardinality cap. A limit on emitted objects must not prevent inspection of later authority-bearing records. Also probe duplicate normalized identities: either deduplicate deterministically or reject ambiguity so repeated inputs cannot consume all bounded slots with the same identifier.
