# Local PENDING_ANCHOR Content Store

## Use when

Use after a pure semantic replay envelope is accepted but before an independently administered anchor exists. The goal is durable local recovery without claiming immutable, tamper-proof, or independently append-only history.

## Minimal shape

Persist one canonical UTF-8 JSON entry per replay envelope directly under an explicit trusted root:

```text
<root>/
  <entry_sha256>.json
  <entry_sha256>.<random>.tmp   # unpublished transient only
```

The filename is SHA-256 of the exact canonical entry bytes. Do not add a mutable index, sequence counter, predecessor chain, SQLite database, or colocated “anchor” merely to simulate stronger history.

Each entry should contain exact keys equivalent to:

- schema version;
- `anchor_state: PENDING_ANCHOR`;
- `durability_scope: local-persistence-only`;
- the complete strict wire representation of the replay envelope.

Every public receipt and recovery result remains `PENDING_ANCHOR`. No Phase 3 API may return `ANCHORED`, `SEALED`, `IMMUTABLE`, or `APPEND_ONLY`.

## Public API boundary

A small API is sufficient:

- `open(root)` — pin and validate one local root;
- `persist(envelope)` — replay, serialize, stage, flush, publish no-replace, re-open, decode, and replay again;
- `recover()` — validate every direct child and return all entries, or fail closed with no trusted partial subset.

Do not expose anchor, promotion, scheduler, export, execution, broker, risk, model, or configuration operations.

## Semantic closure

Before publication:

1. Require the exact envelope type and rerun its constructor/invariants.
2. Run the production semantic replay and require committed plan/evidence identities.
3. Serialize strict canonical bytes with finite-number enforcement.
4. Decode those exact staged bytes into fresh typed objects.
5. Replay the decoded envelope again before publication.

On recovery and idempotent collision, verify filename hash, exact bytes, strict schema/key/type closure, canonical-byte equality, authority denials, and semantic replay. A digest-valid but semantically detached entry is invalid.

## Windows containment

Path checks are not an authorization boundary. For a Windows implementation:

- reject relative, UNC/SMB, ADS, reparse-point, non-disk, wrong-type, and unexpected-child inputs;
- pin the root with `CreateFileW` and `FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS`, sharing read/write but not delete;
- derive canonical identity/path from the open handle and keep it live for the operation;
- create a random temporary leaf with `CREATE_NEW`, write/hash/decode from that same handle, and call `FlushFileBuffers`;
- publish no-replace relative to the pinned root handle where supported; any fallback destination must derive from the pinned handle, not the caller path;
- re-open the committed winner by handle and fully verify it before returning success;
- treat reparse substitution, hard-link ambiguity, unverified cleanup, or an unexpected leaf as recovery-blocking.

A transitive environment package is not automatically a declared product dependency. If using `pywin32`, declare and lock it explicitly; otherwise isolate the required Win32 calls behind a small `ctypes` adapter.

## Crash and concurrency matrix

Test cuts before create, during partial write, after flush/before rename, and after rename/before response. Only an owned, recognized unpublished temp may be safely discarded. Malformed/unremovable temps and unknown leaves block recovery.

Concurrent same-digest publishers may both report success only after validating the single winning file. Existing wrong bytes must never be replaced. A valid existing file is idempotent success.

## False-green rejection gate

Run this gate immediately after the first happy-path/idempotency GREEN and before broad tests or independent review:

1. Place an unexplained regular file and a malformed owned-looking `.tmp` leaf in the root. `recover()` must block the entire store and return no trusted subset. A healthy `PENDING_ANCHOR` result is an immediate `HOLD`.
2. Inspect the actual security boundary. If root/leaf admission or publication relies on `Path.exists()`, `is_dir()`, `read_bytes()`, `glob()`, or `os.replace()` after a separate check—rather than verified live handles—the Windows containment gate is not implemented. A docstring that disclaims concurrent-replacement guarantees confirms the candidate is intentionally below contract.
3. Prove bounded reads before JSON decode/hash; reading a whole hostile leaf and rejecting it afterward is not bounded failure closure.
4. Require explicit RED coverage for unknown leaves, malformed/unremovable temps, reparse/ADS/root-swap attempts, wrong-byte destination collision, same-digest concurrency, and every durable crash cut. Two green happy-path tests are implementation progress, not acceptance evidence.
5. Do not merge a portable path-based fallback under the label “Windows-safe.” Either make the handle adapter part of the accepted slice or narrow the product claim and keep the containment gate open.

This fast gate catches the common failure mode where canonical serialization and semantic replay work correctly but the filesystem boundary remains check-then-open and fail-open.

## Non-claims

This store detects many local corruption and ambiguity cases, but a same-account administrator can delete, replace, or roll back the whole root. Independent append-only or timestamp claims require a separately administered anchor medium and governance model.