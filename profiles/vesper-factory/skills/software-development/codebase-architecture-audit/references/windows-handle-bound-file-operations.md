# Windows Handle-Bound File Operations: Native API Feasibility Probe

Use this reference for a **read-only feasibility audit** of a Python Windows implementation that needs direct-child creation and no-replace publication relative to a pinned directory handle.

## Evidence to collect

1. Confirm runtime architecture and bindings:
   - `ctypes.sizeof(c_void_p) == 8` when documenting x64 layouts.
   - `ntdll` exports `NtCreateFile`, `NtSetInformationFile`, and `RtlNtStatusToDosError`.
   - Determine whether pywin32 exposes a native wrapper; it commonly exposes `CreateFile`/`SetFileInformationByHandle` but not `NtCreateFile`.
2. Inspect local Windows SDK declarations, especially `um/winternl.h` and `um/WinBase.h`.
3. Freeze the target worktree baseline and inspect current path-based checks (`exists`, `glob`, `os.replace`, `Path.read_bytes`) before proposing a stronger guarantee.
4. Run disposable `%TEMP%` probes only; clean them up and do not alter the audited repository.

## Native ABI checklist (x64)

- `UNICODE_STRING`: 16 bytes; `Length`, `MaximumLength`, `Buffer`; lengths are UTF-16LE byte counts excluding NUL.
- `OBJECT_ATTRIBUTES`: 48 bytes; root-handle offset 8, object-name offset 16, attributes offset 24.
- `IO_STATUS_BLOCK`: 16 bytes; status offset 0, information offset 8.
- `FILE_RENAME_INFO` dynamic buffer: `ReplaceIfExists`/flags offset 0, root-handle offset 8, name length offset 16, UTF-16 filename offset 20.

Keep Unicode backing buffers alive until each native call returns. Define `argtypes` and `restype` explicitly; use signed `c_long` for `NTSTATUS` and judge success with `status >= 0`.

## Minimal direct-child model

1. Pin a directory handle. Open it as a directory (`FILE_FLAG_BACKUP_SEMANTICS`); use `FILE_FLAG_OPEN_REPARSE_POINT` and inspect the resulting final object/tag to reject a reparse root.
2. Permit **only one leaf component**. Reject path separators, colon, NUL, `.` and `..`; a fixed digest filename grammar is preferable.
3. Call `NtCreateFile` using the root handle in `OBJECT_ATTRIBUTES.RootDirectory`, with `OBJ_CASE_INSENSITIVE | OBJ_DONT_REPARSE`, `FILE_CREATE`, `FILE_SYNCHRONOUS_IO_NONALERT | FILE_NON_DIRECTORY_FILE`, and a non-directory file attribute.
4. Request `FILE_WRITE_DATA | FILE_WRITE_ATTRIBUTES | DELETE | SYNCHRONIZE` for a temporary file that will later be renamed. `DELETE` is required for the source-side rename.
5. Write and flush through the handle, then publish with `NtSetInformationFile(..., FileRenameInformation=10)`. Use a `FILE_RENAME_INFO` buffer with `ReplaceIfExists = FALSE`, the pinned root handle, and a single target leaf. Do not do a prior existence check.
6. Treat `STATUS_OBJECT_NAME_COLLISION` as the no-replace/idempotency outcome; map diagnostics through `RtlNtStatusToDosError`.

## Required probes

- Direct child `FILE_CREATE` succeeds.
- Traversal through a directory symlink succeeds without `OBJ_DONT_REPARSE` and fails with it (`STATUS_REPARSE_POINT_ENCOUNTERED` is expected on current Windows 10).
- Rename to an existing regular target returns `STATUS_OBJECT_NAME_COLLISION`; source remains.
- Rename to an absent direct target succeeds; source disappears and target appears.
- Rename to an existing reparse target with `ReplaceIfExists=FALSE` must collide rather than publish through it.

## Boundaries and uncertainty

- The Windows SDK explicitly labels `winternl.h` APIs as internal and potentially version-changing. The path can be *locally demonstrated*, but is not a stable public Win32 compatibility promise. Feature-gate it with symbol checks and isolated tests; fail closed on unexpected status/layout behavior.
- `NtSetInformationFile(FileRenameInformation)` has a destination root handle but no `OBJ_DONT_REPARSE` field. The security claim relies on a pinned root, strict direct-child names, and no-replace rename; do not claim a broader recursive no-reparse guarantee.
- A pathname-based recovery scan (`Path.glob`, `exists`, `read_bytes`) is outside this guarantee. Strong recovery needs handle-bound enumeration/open/read as well.
- `FILE_INFORMATION_CLASS.FileRenameInformation` for `NtSetInformationFile` is `10`; it is distinct from Win32 `FILE_INFO_BY_HANDLE_CLASS.FileRenameInfo` (`3`).
