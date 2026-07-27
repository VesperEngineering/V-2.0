# Canonical code identity for receipts on Windows Git checkouts

Use this when a tracked receipt must authenticate source files from a staged candidate and `core.autocrlf` or mixed line endings may be active.

## Failure mode

Hashing `Path.read_bytes()` from the working tree can bind CRLF checkout bytes while Git stages canonical LF blobs. A receipt may self-verify before commit yet fail after checkout, or mix CRLF- and LF-based identities across files.

## Required pattern

1. Freeze the candidate first: exact staged allowlist, no tracked unstaged changes, `git diff --cached --check`, staged tree ID, and SHA-256 of `git diff --cached --binary`.
2. Define the receipt hash basis explicitly. Preferred basis: SHA-256 of exact staged Git blob bytes.
3. Derive each tracked identity from the index, not the checkout:
   ```bash
   git show :path/to/file | sha256sum
   ```
   For deterministic Python verification, hash `subprocess.check_output(["git", "show", ":" + path])`.
4. If a checkout-level regression test must work on Windows and Unix, normalize only CRLF to LF before hashing and state that exact normalization in the receipt. Confirm the result equals the staged-blob hash.
5. Add a regression that iterates **every tracked-text identity in the receipt**, not only files changed by the candidate. Include unchanged feature/config/universe/manifest inputs and any earlier receipt being superseded. Do not test only one newly created LF file; older files may still check out as CRLF.
6. A receipt included in the same commit cannot non-circularly bind the complete final tree that contains itself. Bind the code/input blobs individually plus the source/base commit. Use the staged tree/diff digest as external freeze/review evidence.
7. If review finds a hash-basis mismatch before commit, treat the candidate receipt as not yet admitted: record the HOLD, correct the receipt with a new revision/correction reference, rerun RED→GREEN and all adjacent gates, re-freeze, and obtain a fresh independent review.
8. After integration, rerun the receipt verifier from the canonical checkout **before push/publication**. Compare tracked identities to `git show HEAD:path`. Resolve ignored artifacts/databases from canonical paths—their absence in an isolated worktree is not proof of absence. This catches candidate-worktree coupling that a clean staged review can miss.
9. If an incorrect immutable receipt was already committed or admitted, preserve it. Issue a superseding receipt that SHA-256-binds the exact committed old-receipt blob, states the defect and canonical basis, carries corrected tracked-input identities, preserves all denied authority flags, and receives its own regression plus fresh independent review. Never silently rewrite committed evidence.

## Acceptance evidence

- Receipt declares its hash basis.
- Receipt identities equal exact staged Git blob SHA-256 values.
- Cross-platform regression passes from a CRLF checkout.
- Frozen staged digest/tree remain unchanged during final review.
- Any prior HOLD is cited in the corrected receipt; it is never silently erased.
