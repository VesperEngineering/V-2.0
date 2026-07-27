# Receipt Path-Binding Review

Use this when a receipt declares both a path and a digest for a superseded or upstream artifact.

## Required invariant

A digest proves content identity, not path identity. A same-byte alias, copied receipt, traversal path, or alternate location can satisfy a hash-only check. When the contract requires one exact predecessor, validate in this order:

1. Parse the receipt.
2. Require the declared path to equal the exact expected repository-relative POSIX path.
3. Reject absolute paths and `..` traversal where paths are configurable rather than fixed.
4. Resolve and read the artifact at the validated declared path.
5. Apply the contract's declared canonicalization exactly once (for example, CRLF to LF for canonical tracked text).
6. Compare SHA-256 against the receipt.

A test that hashes a hardcoded predecessor while ignoring `receipt["supersedes_receipt"]["path"]` leaves a path-binding gap. A test that follows any declared path and checks only its digest still permits same-byte aliases when exact lineage matters.

## Adversarial proof

In a disposable external snapshot of the frozen candidate:

1. Copy the legitimate predecessor to a different repository-relative path without changing bytes.
2. Change only the receipt's declared predecessor path to the alias; retain the original digest.
3. Run the exact binding test.
4. Require failure at the exact-path assertion, before digest verification.

This distinguishes path binding from content binding. A same-byte alias must fail when lineage is exact.

## Snapshot harness discipline

- Overlay the frozen staged files onto the disposable snapshot before mutation.
- Run pytest with the snapshot as the current working directory. Merely creating a snapshot and then launching pytest from the source worktree tests the wrong candidate and can produce a false pass.
- Print or otherwise verify the resolved test-file and receipt paths if the result is surprising.
- Treat a wrong-working-directory run as setup-only evidence; correct the harness and rerun.
- Use an external same-drive basetemp, disable repository pytest cache/bytecode when required, and remove the authorized scratch root afterward.
- Recompute HEAD, staged tree/diff digest, staged path allowlist, unstaged tracked diff, and `git diff --cached --check` after the probe to prove the source candidate did not move.

## Verdict boundary

A focused green binding test plus a same-byte-alias rejection proves the path-binding repair. It does not establish that an unrelated full suite is green. Report focused, adjacent, adversarial, and broad-suite evidence separately.