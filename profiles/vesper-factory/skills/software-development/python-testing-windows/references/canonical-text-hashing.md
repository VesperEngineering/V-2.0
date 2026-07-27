# Canonical tracked-text hashing across Windows worktrees

Use this pattern when a contract or receipt must identify **tracked source/input text** across Git worktrees whose checkout filters may produce LF in one worktree and CRLF in another.

## Keep two evidence classes separate

1. **Persisted evidence artifacts** — receipts, ledgers, candidate JSON bytes, signatures, and content-addressed outputs must bind the exact bytes written. Use binary-safe writes (`O_BINARY` on Windows), hash raw bytes, and never normalize during validation.
2. **Tracked textual source/input content** — when identity must survive Git EOL checkout conversion, declare and apply a canonical text profile. Do not silently normalize while claiming a raw-byte hash.

A narrow profile used successfully is:

```json
{
  "algorithm": "sha256",
  "text_canonicalization": "crlf_to_lf",
  "scope": "tracked_text_content"
}
```

Bind this profile into both the immutable task contract and the durable receipt so the hash semantics are reviewable and tamper-evident.

## Minimal helper

```python
import hashlib
from pathlib import Path


def tracked_text_sha256(path: Path) -> str:
    canonical = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(canonical).hexdigest()
```

Use the same helper/semantics in preparation, finalization, unattended execution, and independent verification. The actual consumer must also consume the equivalent canonical text (for example, Python text-mode reads with universal-newline handling) rather than hashing one representation and evaluating another.

## Required regressions

- LF and CRLF forms of the same UTF-8 text produce the same canonical SHA-256.
- Their raw-byte SHA-256 values may differ; do not label the canonical digest a raw-byte hash.
- Missing, extra, or changed hashing-profile fields fail contract and receipt validation.
- Every producer path emits the same exact profile.
- A real CRLF checkout in a second worktree normalizes to the contract hash.
- Candidate and receipt artifacts remain raw-byte-bound and are not line-ending normalized.

## Independent-review recipe

For each bound tracked text path:

1. Read raw bytes from the exact worker/reviewer worktree.
2. replace `CRLF` with `LF` exactly as declared;
3. compute SHA-256 over the canonical bytes;
4. compare with the contract/receipt digest;
5. separately verify exact source revision, clean tracked tree, and path identity.

Do not confuse a Git object ID with SHA-256 over `git show <rev>:<path>` content. Record which digest and byte representation are being compared.
