# Native Windows handle-bound journal feasibility probes

Use this note when independently proving a Windows journal/artifact design whose security boundary must be a pinned directory handle rather than a pathname. Run the probe entirely in user-authorized external scratch and remove it afterward; capture repository status before and after.

## Proven primitive combination

- Pin the trusted root with `CreateFileW(..., FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, ...)` and omit `FILE_SHARE_DELETE` so replacing/deleting that opened root is blocked while the handle lives.
- Validate the root and every opened child with handle queries: `GetFileType`, `GetFileInformationByHandleEx(FileStandardInfo)`, `FileAttributeTagInfo`, `FileIdInfo`, and `GetFinalPathNameByHandleW`.
- Open/create direct children with `NtCreateFile`, `OBJECT_ATTRIBUTES.RootDirectory = pinned_root`, a single validated leaf name, and `OBJ_DONT_REPARSE | OBJ_CASE_INSENSITIVE`. Include `FILE_OPEN_REPARSE_POINT`; reject reparse-point handles after opening rather than following them.
- Reject empty names, `.`/`..`, NUL, `:`, `/`, and `\\` before creating a `UNICODE_STRING`. This closes ADS and path-separator forms at the leaf grammar boundary.
- Use a direct-child lock file opened with share mode zero as the exclusive writer lock. Verify a second open fails with sharing violation.
- Write through the child handle, require an exact byte count, and call `FlushFileBuffers` before publish.
- Publish with native `NtSetInformationFile(FileRenameInformation = 10)` using `FILE_RENAME_INFORMATION.RootDirectory = pinned_root`, `ReplaceIfExists = FALSE`, and a validated leaf target. On the tested Windows host this handle-relative native call succeeded, while `SetFileInformationByHandle(FileRenameInfo = 3)` with the same `RootDirectory` form returned `ERROR_INVALID_PARAMETER (87)`. Do not silently fall back to a pathname rename.
- Enumerate from the pinned directory handle with `NtQueryDirectoryFile` until `STATUS_NO_MORE_FILES`; parse every returned variable-length record and reject malformed offsets/extents. Do not treat one buffer as a complete enumeration.
- Perform bounded reads through child handles and distinguish limit exhaustion from EOF.

## ctypes ABI details that matter on 64-bit Windows

- `UNICODE_STRING`: 16 bytes.
- `OBJECT_ATTRIBUTES`: 48 bytes.
- `IO_STATUS_BLOCK`: 16 bytes.
- `FILE_ID_INFO`: 24 bytes.
- `FILE_STANDARD_INFO`: 24 bytes. Its trailing `DeletePending` and `Directory` members are one-byte `BOOLEAN`s (`BYTE` in ctypes), **not** four-byte Win32 `BOOL`s. Using `BOOL` corrupts interpretation and produced a false root-validation failure.
- `FILE_RENAME_INFORMATION`/`FILE_RENAME_INFO` field offsets on x64: replace flag 0, root handle 8, name length 16, UTF-16 name bytes 20. Allocate conservatively as `sizeof(header) + name_bytes`; `FileNameLength` excludes any terminator.
- Declare `NTSTATUS` as signed 32-bit and test `status < 0`; map failures with `RtlNtStatusToDosError` for evidence.

## Adversarial checks

1. Root delete/rename attempt is blocked while the no-delete-share handle is open.
2. Second writer-lock open is blocked.
3. Child is disk-backed, non-directory, not delete-pending, not a reparse point, same volume as root, has exactly one link, and its final handle path has the pinned root as parent.
4. Existing-target publish fails without replacing existing bytes.
5. Hard-link setup raises link count to two and is rejected.
6. Symlink/junction setup, when local privileges permit it, opens the reparse point itself and is rejected by handle metadata.
7. Enumeration reaches `STATUS_NO_MORE_FILES` and identifies every unexpected direct child.

## Probe workflow and evidence hygiene

- Treat each failed attempt as diagnostic and change the probe or invocation before rerunning. Repeating the exact same failing tool call can trigger an execution guardrail and prevent final verification.
- Avoid keeping a just-published source handle open with share mode zero when the next step reopens or collision-tests the target; close it first, or the test will measure `STATUS_SHARING_VIOLATION` rather than no-replace collision behavior.
- The final admissible run must complete all assertions, print a clear verdict, clean scratch in `finally`, and be followed by explicit checks that scratch is gone and repository status/HEAD are unchanged.
- A partially successful run is not a verdict. Report it as incomplete and resume with a materially changed command (for example, an invocation nonce or changed harness) if a repeated-command guard blocks the old call signature.

## Binding limitations

This validates availability and behavior of the native primitives on the tested machine; it does not by itself prove immunity to all filesystem-driver, network-share, filter-driver, or hostile-local-admin behavior. Production design must define supported filesystem types and attacker authority, validate ABI definitions against the target SDK/architecture, and keep all fallback paths fail-closed.
