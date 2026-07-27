# Typed-Rust handle-bound journal spike checklist

This reference records the reusable technical detail from a disposable Windows journal-primitive probe. It is not a claim that a particular unpublished spike validated successfully.

## Evidence checklist

The executable should print or assert all of the following:

- root opened without delete sharing;
- root `FILE_TYPE_DISK`;
- root `FILE_STANDARD_INFO`: directory and not delete-pending;
- root `FILE_ATTRIBUTE_TAG_INFO`: neither reparse attribute nor nonzero reparse tag;
- root final path, volume serial, and 128-bit file ID;
- direct-child rejection of `""`, `.`, `..`, forward/back separators, traversal forms, colons, and ADS forms;
- root-relative create/open using no-reparse traversal;
- child regular-file, live, non-reparse, link-count-one, same-volume checks;
- complete write and `FlushFileBuffers`;
- root-relative no-replace rename;
- relative reopen and maximum-length-plus-one bounded read;
- collision failure and byte-for-byte preservation of the existing target;
- handle-based directory enumeration containing expected and deliberately unexpected children.

## ABI details that require explicit verification

### Native BOOLEAN versus BOOL

Several file-information structures use native `BOOLEAN` fields. Those are one byte. Using a four-byte Win32 `BOOL` changes following field offsets and can make valid handles appear to have false directory state or otherwise corrupt interpretation.

### Flexible-array rename buffers

For rename structures, independently verify:

- selected information-class numeric value;
- whether the first union member is a one-byte replacement Boolean or a flags DWORD;
- `RootDirectory` offset for the target architecture;
- `FileNameLength` offset;
- flexible UTF-16 filename offset;
- minimum accepted buffer size and whether the API expects `sizeof(struct) + filename_bytes` or an offset-based size;
- required access rights on source and root handles;
- filesystem/OS support for the chosen base or `Ex` class.

Base rename and rename-Ex classes must not be treated as interchangeable just because their trailing fields look similar.

### Directory records

Variable-length `FILE_ID_BOTH_DIR_INFO`-style records should never be parsed from remembered offsets alone. Prefer generated types; otherwise assert every critical offset against the SDK layout and check each record against the bytes actually returned, not merely the full allocation capacity.

## Diagnostic progression for `ERROR_INVALID_PARAMETER`

1. Print pointer width and layout assertions (`size_of`, `align_of`, offsets).
2. Confirm the information-class constant from the installed generated bindings/SDK.
3. Confirm source/root handle access and share modes.
4. Confirm buffer length and union encoding for that exact class.
5. If supported, run a control call with a fully qualified destination to distinguish root-relative handling from general structure rejection.
6. Only then alter the implementation.

Each retry should discriminate at least one hypothesis. Rebuilding and re-running after an unverified padding guess is not useful evidence.

## Tool-loop avoidance

During bring-up, avoid repeatedly submitting the same long `cargo build && executable` command. Separate formatting, lint, compile, and runtime stages. When runtime behavior fails, inspect source declarations or add a diagnostic before executing again. This both improves debugging quality and avoids automated repeated-failure halts.