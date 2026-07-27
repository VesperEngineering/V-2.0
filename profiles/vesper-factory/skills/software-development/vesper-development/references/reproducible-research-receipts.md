# Reproducible research receipts

Use this reference when a VESPER research/evaluation result includes hashes of derived rows, manifests, rankings, forecasts, portfolio targets, or other computed evidence.

## Core rule

A digest is not independently verifiable unless the receipt also defines the exact byte stream that was hashed. “Deterministic SHA-256” is insufficient.

For every derived-data hash, record:

- source artifact paths and raw hashes;
- admitted row window and filtering rule;
- symbol/entity order and row order;
- columns and their order;
- type coercions;
- timestamp formatting and timezone treatment;
- float/integer serialization;
- separators, length prefixes, framing, and trailing-newline behavior;
- text encoding;
- hash algorithm;
- expected digest;
- row/entity counts and common as-of boundary.

If the implementation performs incremental `hash.update()` calls, describe each update in order. State explicitly when no separator or length prefix is used; silent concatenation is still a framing decision.

## Run-manifest binding

Do not publish only a run-manifest digest. Either:

1. embed the complete run-manifest object plus its canonicalization rule and canonical JSON/string; or
2. identify an exact immutable path/artifact and bind its raw hash.

A canonical JSON rule should state at least key sorting, separators, Unicode handling, encoding, and trailing-newline behavior. Recompute the digest from the embedded content before freezing the receipt.

## Staged-byte discipline on Windows

Review and hash the exact staged blob, not a CRLF-translated worktree copy. A reviewer should export/read the index or use Git plumbing when receipt raw hashes are part of the candidate identity. Label worktree-byte and staged-blob hashes separately if both are useful.

## One-shot evaluation discipline

When a contract permits one outcome-producing call:

- capture the returned outcomes once;
- perform all post-processing and consistency checks from that capture;
- do not rerun merely because a checker used the wrong bootstrap, serialization, or comparison rule;
- correct the audit harness and reuse the captured values when possible;
- record whether any additional outcome call occurred.

## Receipt revision after a HOLD

If numerical/parity evidence passed but the receipt was under-specified:

- preserve the original result fields and bindings;
- add `receipt_revision` and a precise `revision_reason`;
- add the missing serialization profile/manifest content;
- recompute the raw receipt hash and staged candidate identity;
- obtain a fresh independent review;
- do not describe the repaired receipt as accepted until that review passes.

## Independent verification checklist

- [ ] Exact branch, HEAD, staged tree, staged paths, and staged binary-diff hash match.
- [ ] Raw source/model/config/manifest hashes match.
- [ ] Dataset hash reproduces from the receipt’s byte-level profile.
- [ ] Run-manifest hash reproduces from embedded/frozen content.
- [ ] Entity and row counts, date window, and as-of boundary match.
- [ ] Numerical/ranking/parity results reproduce without hidden inputs.
- [ ] Authority denials remain explicit and accurate.
- [ ] No protected writes, SQLite sidecars, or repository drift occurred.
- [ ] External scratch is removed and candidate identity is unchanged afterward.
