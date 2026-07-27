# Python ctypes direct-final journal lessons

Session class: Windows handle-bound, fail-closed local evidence persistence in Python.

## Native boundary

- Bootstrap with one absolute local path only to open the directory using directory plus open-reparse-point flags.
- Pin `(volume serial, file ID)` and the final path. Revalidate them while holding the operation lock and again before returning.
- Root-relative child opens use `NtCreateFile`, `OBJECT_ATTRIBUTES.RootDirectory`, strict one-component UTF-16 names, `OBJ_DONT_REPARSE`, and open-reparse-point semantics.
- In ctypes, `UNICODE_STRING.Buffer` needs an explicit `ctypes.cast(buffer, LPWSTR)` while retaining the backing buffer. Passing the wchar array directly raised a Python `TypeError`, which correctly identified an FFI marshalling defect before native execution.
- Define and check all function signatures. Treat signed `NTSTATUS` deliberately and retain the hexadecimal status in failure messages.

## Direct-final protocol

- A fixed root-relative lock leaf serializes recovery and persistence.
- Compute canonical bytes and their SHA-256 before opening the final `<digest>.json` leaf with create-only semantics.
- On collision, reopen relative to the root, validate physical identity, bounded-read, strictly decode, replay semantics, and require exact bytes/receipt before returning idempotent success.
- On new creation, validate before write, write all bytes, flush, validate again, close, relative-reopen, bounded-read, and compare exact bytes plus semantic receipt.
- Never rename, replace, delete, truncate, or repair a committed-looking child. A crash can leave an incomplete final file; recovery must preserve it and block.

## Physical validation

For every committed child, check on the opened handle:

- regular file, non-delete-pending;
- no reparse attribute/tag;
- one hardlink;
- same volume as the root;
- only the unnamed `::$DATA` stream;
- final parent equals the pinned root and final basename equals the requested leaf;
- file identity and size are stable across bounded read.

Enumerate via the pinned root handle. When parsing `FileIdBothDirectoryInformation`, validate returned byte count, fixed header availability, UTF-16 byte length, next-offset alignment/bounds, and terminal status.

## Strict codec and failure precedence

- Canonical UTF-8 JSON: sorted keys, compact separators, finite numbers, exact schema keys, duplicate-key rejection, depth/count/string/integer bounds, and canonical datetime round-trip.
- Reconstruct domain dataclasses and call the pure semantic replay function; do not trust stored hashes as self-verification.
- Failure precedence matters for useful fail-closed evidence:
  1. malformed content;
  2. semantic replay failure;
  3. duplicate semantic record across leaves;
  4. noncanonical bytes;
  5. filename/content hash mismatch.

This ordering lets a malformed fixed-name fixture report `malformed`, a reformatted valid record report `canonical`, and an alternate-encoding duplicate report `duplicate` rather than being silently deduplicated.

## Exact-candidate adversarial review additions

A green native suite does not close several class-level review gaps by itself:

- **Constructor closure:** Public receipt and recovery dataclasses must reject caller-supplied posture escalation. Probe direct construction with `status="FINALIZED"`, `local_integrity_only=False`, and anchored/append-only/immutable flags set true. Frozen dataclasses remain forgeable without `__post_init__` invariants.
- **Cumulative recovery bounds:** Bound total directory entries and aggregate name bytes before appending to an in-memory list. Also cap aggregate decoded nodes/work where the single-file byte ceiling does not already establish a sufficiently tight bound. A 64 KiB enumeration buffer is only a per-call bound.
- **Membership races:** Inject an unexpected direct child immediately after the initial enumeration and before semantic validation returns. If recovery still reports pending success with `reason=None`, the implementation has only a cooperative snapshot contract. Either document that exact contract or add a defensible membership-binding/recheck mechanism; the lock leaf alone does not stop non-cooperating writers.
- **Ancestor mounts:** Test a mounted-folder/volume-mount ancestor separately from ordinary directory symlinks. Root reparse checks plus final-path string equality are not automatically proof for every ancestor reparse class.
- **Freeze discipline:** Bind the staged tree, complete binary-diff SHA-256, staged-blob hashes, and no-unstaged-diff state before and after tests. Run ad-hoc probes and pytest basetemps only in authorized external scratch, remove them, and verify absence before the final verdict.

These defects or unresolved boundaries require `HOLD` even when happy path, collision, ADS, hardlink, concurrency, adjacent suites, and the full suite are green.

## Verification pattern

- Preserve frozen RED tests and add only the production module when scope requires it.
- Run focused native adversarial tests first, then upstream forecast/target/delta/evidence suites, `py_compile`, forbidden-authority/path-I/O source scans, and final scope checks.
- If asked for fresh ad-hoc evidence, generate a verifier with `tempfile.mkstemp(prefix="hermes-verify-", suffix=".py")`, run it with the required interpreter, and remove both script and external pytest basetemp. Report it as focused ad-hoc evidence, not as a canonical full-suite run.
- Do not count a tool-generated lint or compile check as runtime proof of handle semantics.

## Posture language

Return and report the exact local-only posture: pending external anchor, local integrity only, not independently anchored, not append-only, and not immutable. Direct-final collision safety does not justify stronger claims.
