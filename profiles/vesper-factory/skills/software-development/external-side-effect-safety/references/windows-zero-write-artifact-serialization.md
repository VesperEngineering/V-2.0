# Windows Artifact Publication: Fail Closed to Zero-Write

## Trigger

A local evidence/receipt feature wants to persist a dated JSON artifact and checksum, but the threat model includes a hostile or concurrently modified filesystem path on Windows.

## Rule

Do not claim that `Path.resolve()`, `lstat()`, symlink/reparse checks, an allowed root string, staging directories, or `os.replace()` closes the check-to-use race. A validated root or ancestor can be replaced by a junction/reparse point before later pathname-based creation or replacement.

If the application cannot use a trusted handle-based no-follow primitive for every root-relative operation, remove persistence from the component.

## Safe reduced design

1. Keep the evidence builder pure: explicit frozen inputs -> validated receipt.
2. Rebuild the receipt from its complete frozen input contract before accepting it for serialization; compare canonical bytes to reject incomplete or tampered receipts.
3. Return a deterministic serialization envelope only:
   - date-derived filename;
   - canonical JSON text/bytes;
   - SHA-256 digest;
   - checksum text.
4. Treat persistence as a separate, explicitly trusted boundary owned by an approved backend or runtime with stronger filesystem guarantees.
5. Test determinism and tamper/incomplete-receipt rejection. Assert the serializer itself performs zero filesystem writes.

## Why

A serialized in-memory evidence artifact preserves provenance and reviewability without making unsupported claims about path containment or atomic multi-file publication. It is safer than a superficially hardened local writer that can be redirected through a junction/symlink race.
