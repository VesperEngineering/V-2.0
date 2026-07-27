# Windows native handle containment

Use this only when a persisted local artifact must resist junction/symlink/reparse and pathname TOCTOU substitution on Windows. `Path.resolve()`, `exists()`, `is_dir()`, `GetFileAttributesW()`, `os.replace()`, and reopen-by-path checks are not an authorization boundary.

## Verified minimum pattern

1. Open and retain the existing root directory handle with `CreateFileW`, `FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT`; inspect the opened handle and reject a reparse-point root.
2. Accept only syntactically direct child names (no separators, colon, NUL, `.` or `..`).
3. Use `ctypes` bindings to `ntdll.NtCreateFile` with `OBJECT_ATTRIBUTES.RootDirectory=root_handle` and `OBJ_DONT_REPARSE` (`0x1000`) for `FILE_CREATE` / CREATE_NEW temp leaves. Keep the UTF-16 buffer alive through the call.
4. Write, flush, rewind, hash, strict-decode, and semantically replay through the same temporary file handle.
5. Publish with `NtSetInformationFile(FileRenameInformation=10)` relative to the same root handle with `ReplaceIfExists=False`. Treat target collision as idempotency only after opening and validating the winner by handle; never overwrite. **Do not treat a plausible `ctypes` structure size as proof:** packing, pointer alignment, information-class choice, and relative-name semantics must be exercised in a disposable native probe on the target Windows architecture. The probe must show both absent-target success and existing-target collision with source and destination bytes preserved before this binding is admitted.
6. Recovery must enumerate with the pinned root handle (for example, `NtQueryDirectoryFile`) and open/read each direct leaf relative to it. Do not claim handle-bound safety if it falls back to `Path.glob`, `read_bytes`, or pathname unlink/replace.
7. On every opened child handle, verify regular-file type, non-reparse status, stable same-volume/file identity, delete-pending false, and link count exactly one. Query stream information through the handle and reject any non-default alternate data stream. A colon-free pathname does not prove that an existing file has no ADS.

## Native-binding admission and fallback rules

A native design is not admitted merely because root opening, child creation, or structure-size probes succeed individually. Treat publication as a separate kill gate:

1. Prove absent-target success and existing-target no-replace collision end to end on the target architecture.
2. If repeated `ctypes` attempts fail at the same rename/information-class boundary, stop retrying. Classify the binding as `HOLD_FFI_UNPROVEN` and change strategy—prefer maintained typed bindings or a small audited native component. Do not move partially proven layout constants into production.
3. A disposable Rust/typed-binding spike proves API feasibility only. Before choosing it for production, separately prove reproducible build inputs, binary/source identity, packaging, Python invocation/FFI behavior, failure propagation, and exact-candidate review. A locally working prebuilt helper is not self-authenticating evidence.
4. Direct root-relative final `FILE_CREATE` is a narrower fallback, not an atomic-rename substitute. Consider it only when the public crash contract explicitly says an interrupted or truncated final leaf blocks the entire store as `RECOVERY_BLOCKED`, preserves the leaf for forensics, and requires deterministic operator recovery. Add crash cuts during write and after flush. Do not call this atomic publication or transparent crash recovery.
5. Keep the repository RED-test-only until the native kill gate is resolved. This prevents canonical codec or happy-path work from normalizing an unsafe filesystem boundary.

## Validated direct-final target-host probe

A Windows 10 x86_64 probe built with Rust 1.97 and `windows-sys` 0.61.2 validated the constrained no-rename fallback twice with **37 PASS / 0 FAIL**. Treat these as admission criteria to reproduce on the actual target, not as a portable guarantee:

- `CreateFileW` pinned an absolute local root with backup-semantics/open-reparse flags and no delete sharing; handle queries proved disk, directory, non-reparse, non-delete-pending, volume serial, and 128-bit file identity.
- Root-relative `NtCreateFile(FILE_CREATE, OBJ_DONT_REPARSE, FILE_NON_DIRECTORY_FILE | FILE_SYNCHRONOUS_IO_NONALERT)` created the final leaf, and a second create returned `STATUS_OBJECT_NAME_COLLISION` while original bytes remained unchanged.
- The create handle needed read as well as write/synchronize access; otherwise `FileAttributeTagInfo` could fail with `ERROR_ACCESS_DENIED` during post-create validation.
- After `WriteFile` and `FlushFileBuffers`, a root-relative `FILE_OPEN` returned the same identity and exact bounded bytes. Handle-based enumeration exposed both canonical and unexpected direct children.
- A deliberately truncated final leaf was preserved byte-for-byte and classified `RECOVERY_BLOCKED`; it was never accepted, deleted, or repaired.

This proves local fail-closed feasibility, not atomic publication. The final name can be visible before the write completes, and an interrupted final blocks the store until separately governed operator reconciliation. Keep `PENDING_ANCHOR` and all non-claims explicit. Identity behavior was proven only on an NTFS-class local volume; fail closed when required identity/stream queries are unsupported.

## x64 ctypes facts

- `UNICODE_STRING`: 16 bytes; `Length` and `MaximumLength` are UTF-16LE byte counts excluding NUL.
- `OBJECT_ATTRIBUTES`: 48 bytes; includes `RootDirectory` and `Attributes`.
- `IO_STATUS_BLOCK`: 16 bytes.
- Required native exports: `NtCreateFile`, `NtSetInformationFile`, `RtlNtStatusToDosError`.
- Useful constants: `OBJ_CASE_INSENSITIVE=0x40`, `OBJ_DONT_REPARSE=0x1000`, `FILE_CREATE=2`, `FILE_SYNCHRONOUS_IO_NONALERT=0x20`, `FILE_NON_DIRECTORY_FILE=0x40`, `FileRenameInformation=10`.

## Practical Python integration notes

- The root probe must reject both a reparse-point **and** a non-directory handle. `CreateFileW(... FILE_FLAG_BACKUP_SEMANTICS ...)` can otherwise return a valid handle for an ordinary file.
- Checking only the final root handle's reparse tag does not detect a symlink/junction in an ancestor component. Normalize the caller's absolute local path, strip the `\\?\` prefix from `GetFinalPathNameByHandleW`, and require the normalized paths to match. Add a regression where `linked-parent\journal` traverses a directory symlink to `real-parent\journal`; the final journal directory itself is ordinary, but admission must still reject the ancestor traversal.
- Bound handle-based enumeration by both child count and cumulative decoded name bytes. A fixed per-call `NtQueryDirectoryFile` buffer does not bound the total allocation if results are appended indefinitely. Exceeding either limit must block the complete recovery result, not return a valid prefix.
- With `UNICODE_STRING.Buffer` declared as `wintypes.LPWSTR`, a `ctypes.create_unicode_buffer()` array may need `ctypes.cast(buffer, wintypes.LPWSTR)` when constructing the structure. Keep the original array referenced until `NtCreateFile` returns; the cast does not own the storage.
- For an existing content-addressed target, do not pre-check existence. Attempt the no-replace rename first; only on `STATUS_OBJECT_NAME_COLLISION` open the winner through `NtCreateFile` relative to the pinned root, read it through that handle, then compare exact canonical bytes and strict-decode it.
- If handle-bound directory enumeration is not yet implemented, `recover()` must explicitly raise an unsupported/fail-closed error. Do not retain a happy-path path-based recovery method merely to preserve an API shape.
- `NtSetInformationFile(FileDispositionInformation)` may be used only for an owned temporary handle and must be exercised by a collision/error cleanup test. Do not identify or delete temporary names by path.
- The `ntdll` calls remain an internal-API supportability risk even after a target-host probe passes. Keep ABI/probe tests close to the implementation and fail closed on unexpected symbols, layouts, or NTSTATUS values.

## Post-GREEN adversarial review gates

A focused/full GREEN suite is not sufficient until these public and concurrency surfaces are probed:

1. **Close public posture constructors.** Frozen dataclasses do not stop callers from directly constructing `FINALIZED`, independently anchored, append-only, immutable, or non-local receipts. Every public receipt/recovery/status object needs constructor-time invariant validation. Parameterize one mutation per posture field; blocked recovery must contain no entries plus one nonblank reason, while healthy local recovery must remain exactly `PENDING_ANCHOR` with no blocked reason.
2. **Bound total enumeration twice.** Enforce child-count and aggregate UTF-16 name-byte limits while consuming native directory records, then enforce them again at admission so mocked or alternate enumeration paths cannot bypass the bound. A fixed 64 KiB query buffer is only a per-call limit.
3. **Re-observe membership before success.** A cooperative writer lock does not stop a non-cooperating same-account process from creating a late child. After reading/validating candidates, enumerate and admit the directory again immediately before returning success; require the final membership to equal the initial set plus only the one expected newly-created digest leaf. Inject an unexpected child between the two calls and require `RECOVERY_BLOCKED` or a failed persist, never healthy output. Document that a same-account process can still race after the final observation; this is why the result remains local-integrity-only.
4. **Walk and retain every ancestor handle.** Final-path equality catches ordinary ancestor symlinks, but an independently reviewed fail-closed implementation should open every lexical path component with `OPEN_REPARSE_POINT`, reject disk/type/delete-pending/reparse/final-path ambiguity at each step, and retain those no-delete-share handles for the journal lifetime. This explicitly rejects junction and volume-mount ancestors and prevents component replacement after admission. Test a symlinked parent; exercise a mounted-folder fixture when the environment safely supports creating one.

These are release `HOLD`s, not hardening suggestions: posture forgery creates false authority, unbounded accumulation creates denial-of-service, late-child acceptance creates false healthy recovery, and ancestor ambiguity breaks containment.

## Test requirements
In temporary roots:

- prove a reparse traversal succeeds without `OBJ_DONT_REPARSE` but fails with `STATUS_REPARSE_POINT_ENCOUNTERED`;
- prove relative no-replace rename collides without changing source or destination, and succeeds for an absent target;
- hard-link a valid committed entry and require recovery to block on link count greater than one;
- attach an unexpected ADS to a valid committed entry and require recovery to block;
- leave an unexplained regular child and malformed owned-looking temp and require all-or-nothing blocked recovery;
- force semantic replay to fail and prove no committed destination exists afterward;
- run concurrent same-digest writers and require one valid leaf plus identical verified receipts.

Test recovery independently; publication safety alone is insufficient. Preserve every adversarial leaf unless an explicitly owned, recognized cleanup protocol is itself tested; silent deletion can destroy forensic evidence.
