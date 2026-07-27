---
name: windows-native-api-engineering
description: Build and verify Rust/C/C++/Python FFI probes and production components around Windows native handle, filesystem, and kernel-facing APIs. Use for Win32/NT handle-relative operations, Windows ABI debugging, reparse-resistant filesystem work, and disposable native feasibility spikes.
version: 1.1.0
metadata:
  hermes:
    tags: [windows, rust, win32, nt-api, ffi, filesystem, handles, verification]
    related_skills: [surgical-engineering, systematic-debugging, windows-security-audit]
---

# Windows Native API Engineering

## Purpose

Use this skill when correctness depends on Windows handle semantics, Win32/NT information classes, native ABI layout, or reparse-safe filesystem behavior. It governs both disposable feasibility probes and narrowly scoped production changes.

The goal is executable evidence. A successful compile proves only that Rust types and link symbols are accepted; it does not prove an information buffer, access mask, share mode, or security property works on the live filesystem.

## 1. Establish the native contract

Before writing code, list the exact properties to prove and map each to a native operation and observable assertion.

For handle-bound filesystem work, distinguish:

- path-based bootstrap used only to obtain the initial directory handle;
- operations relative to that pinned handle;
- validation performed on opened handles rather than pre-open paths;
- publication semantics, especially replacement versus collision failure;
- verification by relative reopen and bounded read;
- enumeration through the pinned directory handle.

Keep disposable spikes outside production repositories unless the user explicitly requests integration. Give the spike its own manifest, lockfile, source, and captured output.

## 2. Prefer generated bindings, minimize ABI shims

1. Pin a maintained binding (`windows` or `windows-sys`) and enable only the needed Win32/WDK features.
2. Inspect the generated crate source or authoritative SDK declaration for every structure, union, information-class constant, and function signature used.
3. Prefer binding-provided Win32 and WDK types. Do not hand-recreate an ABI type merely because its declaration is familiar.
4. When a binding omits a native export or flexible-array type, define the smallest `#[repr(C)]` shim and add assertions for size, alignment, and critical offsets.
5. Keep unsafe code in small wrappers whose preconditions are documented and checked by safe callers.

Typed Rust removes many ctypes hazards, but a manually transcribed `#[repr(C)]` structure can still have the wrong BOOLEAN width, union interpretation, member offset, or total buffer length.

## 3. Handle acquisition and validation

For a pinned local directory root:

- open with directory and open-reparse-point semantics;
- omit delete sharing when replacement of the pinned directory must be prevented;
- verify disk type, directory status, non-delete-pending state, and no reparse attribute/tag;
- record final path, volume serial, and stable file ID for diagnostics.

For direct children:

- validate a strict leaf before entering the native boundary;
- reject empty, dot, dot-dot, separators, colon/ADS syntax, and embedded NUL;
- use root-relative open/create with no reparse traversal where the native API supports it;
- validate regular file, non-reparse, non-delete-pending, link count one, and same volume as root.

Avoid claiming absolute symlink safety from lexical validation. The security claim comes from root-relative resolution plus post-open handle checks.

## 4. Publication proof

Choose and state one publication contract; do not blur the two:

1. **Staged rename:** create a unique temporary direct child, validate it, write and flush all bytes, then rename to a final leaf relative to the root with replacement disabled. Verify collision preservation against a sentinel destination.
2. **Direct-final:** create the final digest-named leaf relative to the root with collision failure, validate/write/flush/reopen it, and treat interruption residue as a suspicious final entry that blocks recovery. Do not claim atomic visibility, and do not repair or overwrite residue automatically.

For either contract:

- relative-reopen, bounded-read, and compare exact bytes;
- pre-create a final target with sentinel bytes, require collision failure, and prove the sentinel remains unchanged;
- use only information classes and flags verified for the target Windows version;
- never infer that base and `Ex` rename classes share union or flag behavior.

## 5. Directory enumeration

Enumerate through the pinned root handle, not by reconstructing a pathname. Parse variable-length directory records defensively:

- validate fixed header availability;
- validate UTF-16 byte length and bounds;
- validate each next-entry offset and overflow;
- stop only at the documented terminal condition;
- include an unexpected-child fixture so the proof shows enumeration is not merely checking known names.

When generated record types are unavailable, assertions for header offsets are mandatory.

## 6. Debugging sequence

On native failure:

1. Capture the exact API, information class, return value, `GetLastError`, or `NTSTATUS`.
2. Classify the likely boundary: access/share mask, handle type, information-class support, structure layout, buffer sizing, flag semantics, or filesystem capability.
3. Inspect the exact generated/SDK declaration before editing.
4. Add a focused diagnostic or layout assertion that distinguishes hypotheses.
5. Change strategy based on evidence, then re-run.

`ERROR_INVALID_PARAMETER` at a file-information call is usually a contract/ABI signal. Do not guess repeatedly among padding, flags, and rights without a discriminating check.

## 7. Python `ctypes` handle-bound implementations

When the production boundary is Python rather than Rust/C++, keep the same native-contract standard:

1. Declare `argtypes` and `restype` for every Win32/NT function used; never rely on ctypes defaults for handles, pointers, sizes, or NTSTATUS.
2. Keep buffers alive for the whole call. For `UNICODE_STRING`, explicitly cast a `create_unicode_buffer` to `LPWSTR`; passing the array object directly may fail before the API is reached.
3. Use the pinned directory handle as `OBJECT_ATTRIBUTES.RootDirectory`, a strict single leaf as `ObjectName`, and no-reparse/open-reparse-point semantics. Never introduce a pathname fallback after bootstrap.
4. Serialize writers with a root-relative lock leaf opened through the same capability. For direct-final publication, create the digest-named leaf with collision failure and preserve interrupted final residue as suspicious evidence.
5. Validate opened children before and after bounded I/O: ordinary file, non-reparse, non-delete-pending, one link, expected stream set, same volume, exact final parent/name, stable identity, and stable size.
6. During recovery, reconstruct bounded semantic content before choosing the most informative binding error:
   - malformed bytes should report malformed content, not merely filename hash mismatch;
   - valid noncanonical bytes should report canonicalization failure before hash mismatch;
   - duplicate semantic entries should take precedence over per-file canonicalization errors, so alternate encodings cannot be silently deduplicated.
7. Bound the complete recovery workload, not only each file and native query buffer. Cap total admitted directory entries, aggregate name bytes, aggregate payload bytes, and semantic nodes before accumulating them. A fixed `NtQueryDirectoryFile` buffer does not bound a loop that appends names indefinitely.
8. Treat public receipt/recovery dataclasses as authority-signaling models. Their constructors must enforce the same fixed posture as journal-produced values; `frozen=True` prevents mutation but does not prevent direct construction with `FINALIZED`, independently anchored, append-only, or immutable claims.
9. Challenge directory-state TOCTOU separately from file-handle stability. A cooperative lock leaf does not prevent an uncooperative process from adding a direct child after enumeration. Define the snapshot/attacker contract explicitly and, if success claims current directory admission, recheck or otherwise bind membership before return.
10. Prove ancestor mount-point handling, not just root and symlink handling. A final-path lexical comparison may reject ordinary symlink aliases but is not evidence for mounted-folder/volume-mount ancestors until that exact case is exercised or the ancestor chain is inspected by handle.
11. Keep posture explicit. Local direct-final persistence is not independently anchored, append-only, immutable, automatically repaired, or guaranteed atomically visible unless separate evidence proves each property.

See `references/python-ctypes-direct-final-journal.md` for the concrete ABI, validation-order, and verification lessons.

## 8. Build and execution discipline

Run gates separately during exploration:

```text
cargo fmt --check
cargo clippy --release -- -D warnings
cargo build --release
<release executable>
```

A chained command can let an early formatting failure hide compile or runtime evidence. Once all gates pass individually, a final chained verification is appropriate.

Do not repeat an identical execution after only speculative changes. Tool runtimes may classify repeated failing commands as a loop and halt further execution. Use a changed diagnostic command, inspect binding source, or add assertions first.

## 9. Completion standard

Report `VALIDATED` only when the release executable completes every required assertion. The final report must include:

- workspace and files created;
- binding and pinned version;
- native APIs/information classes exercised;
- exact build, lint, and execution commands;
- captured root diagnostics and adversarial rejection output;
- happy-path, collision-preservation, relative-reopen, and enumeration results;
- any open gate if execution did not complete.

If a runtime boundary remains unresolved, preserve the exact error and call it a blocker—not a successful proof.

## References

- `references/typed-rust-handle-journal-spike.md` — detailed checklist and ABI pitfalls learned from a disposable handle-bound journal probe.