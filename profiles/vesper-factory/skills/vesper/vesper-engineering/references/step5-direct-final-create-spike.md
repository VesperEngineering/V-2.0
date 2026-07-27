# Step 5 Direct-Final Root-Relative FILE_CREATE Spike (VALIDATED, 2026-07-25)

Session detail for the disposable Rust spike that proved the narrow Step-5
direct-final no-rename create protocol. Verdict: **VALIDATED** — 37 PASS / 0 FAIL,
two deterministic runs (identical modulo volatile file IDs), exit 0, spike dir
deleted afterward per contract.

## What was proven (real execution, Windows 10, Rust 1.97, windows-sys 0.61.2)

1. Leaf validator rejects colon/slash/backslash/`.`/`..`/trailing-dot; accepts plain leaf.
2. Absolute existing dir pinned via `CreateFileW(FILE_GENERIC_READ,
   share=READ|WRITE (NO delete), OPEN_EXISTING,
   FILE_FLAG_BACKUP_SEMANTICS|FILE_FLAG_OPEN_REPARSE_POINT)`; verified
   `FILE_TYPE_DISK`, directory, non-reparse, non-delete-pending; 128-bit
   `FILE_ID_INFO` identity captured.
3. `NtCreateFile(RootDirectory=root, OBJ_DONT_REPARSE, FILE_CREATE,
   FILE_NON_DIRECTORY_FILE|FILE_SYNCHRONOUS_IO_NONALERT)` creates the final child
   directly (no temp+rename); exact bytes written via `WriteFile` + `FlushFileBuffers`.
4. Post-create handle verifies same-volume (`FileIdInfo` vol serial == root's),
   regular, non-reparse (`FileAttributeTagInfo`), `NumberOfLinks==1`, not
   delete-pending, exact size.
5. Close + relative `FILE_OPEN` (add `FILE_OPEN_REPARSE_POINT`) → same file
   identity, bounded read returns exact bytes, semantic frame validator accepts.
6. Second `FILE_CREATE` on same leaf → `STATUS_OBJECT_NAME_COLLISION` (0xC0000035);
   original bytes verified unchanged.
7. Semantic replay before create: missing → create; valid-identical → idempotent
   skip (no create attempted).
8. `NtQueryDirectoryFile` through the root handle (class
   `FileIdBothDirectoryInformation` = 37) sees both an unexpected pre-existing
   child and the final child.
9. Crash-residue (truncated 31/62-byte final): validator returns
   `RECOVERY_BLOCKED` (frame length mismatch); residue stays byte-identical —
   never auto-deleted or repaired.

## Pitfalls discovered (durable)

- **`FileAttributeTagInfo` needs read access.** `GetFileInformationByHandleEx`
  with `FileAttributeTagInfo` fails `ERROR_ACCESS_DENIED` (5) on a
  `GENERIC_WRITE|SYNCHRONOUS`-only handle while FileBasic/Standard/IdInfo succeed
  on the same handle. Fix: request `GENERIC_READ|GENERIC_WRITE` at create time (or
  query reparse on a reopened read handle).
- **windows-sys 0.61.2 feature gates.** `CreateFileW` requires `Win32_Security`
  (not just `Win32_Storage_FileSystem`); `ReadFile`/`WriteFile` require
  `Win32_System_IO`. `SYNCHRONOUS` (0x00100000) is not exported — define locally.
  `GENERIC_READ`/`GENERIC_WRITE` live in `Win32::Foundation`.
- **Hand-declared NT FFI shapes.** `OBJECT_ATTRIBUTES`/`UNICODE_STRING`/
  `IO_STATUS_BLOCK` as `#[repr(C)]`; `IO_STATUS_BLOCK = { Status: i32,
  Information: usize }` (union layout identical). DesiredAccess
  `GENERIC_*|SYNCHRONOUS` is fine — the I/O manager maps generic bits.
- **File-search tool on cargo registry.** The file-search tool errored
  "path not found" on `~/.cargo/registry/src/...` while the tree existed;
  `read_file` with offsets and terminal `grep -n` worked. Fall back instead of
  retrying the same failing path.

## Protocol adopted for Step 5

Strict leaf validation → pin+validate root → semantic replay before create →
root-relative `FILE_CREATE` (no replacement, no delete share) → write+flush →
verify (disk/regular/non-reparse/link-count-1/same-volume/identity) → close +
relative reopen + bounded read → fail-closed `RECOVERY_BLOCKED` on any invalid
existing final.

## Fatal limitations (contractually out of scope — do not claim these)

- **No atomic visibility**: final name is enumerable with partial bytes between
  create and write completion; readers must run the semantic validator.
- **No automatic repair**: crash residue permanently blocks the leaf until
  out-of-band operator action.
- **No append-only/immutability/anchoring**: any process with write access can
  mutate the final post-create; protection rests on no-delete share mode only.
- Identity checks assume an NTFS-class local volume; other filesystems untested.
