# Frozen Candidate and Independent Review

Use for governed Vesper implementation slices that must be reviewed before submission.

1. **Preflight and isolate.** Confirm canonical repo is untouched; use a dedicated worktree and record base SHA.
2. **TDD and verify.** Add failure contracts first. Run focused tests, relevant integration/VOT suites, lint, compile, and `git diff --check` with external temporary directories.
3. **Freeze exactly.** Stage the scoped candidate (not commit), record base SHA, staged tree ID, and staged binary-diff SHA-256. Treat this triple as the review binding.
4. **Independent review.** Give the reviewer the exact binding and explicit fail-closed checks: authority denial fields, strict digest validation, malformed/blank input, bounded reads, atomic durability, interprocess race behavior, and no strict-authority paths.
5. **Do not edit beneath a live review.** If a defect is already known, either wait for its receipt or explicitly invalidate that frozen candidate before editing. A changed tree makes its previous review receipt historical evidence only.
6. **Repair from reproduced findings.** Add a RED regression for every reviewer finding; then repair and run the focused suite plus broader relevant suite. Include real multiprocessing tests for interprocess writer claims—atomic replace alone does not prevent lost updates.
7. **Refreeze and rereview.** A failed review never authorizes a successor. Stage the repaired candidate, derive new bindings, and obtain a new independent receipt before submission.

Pitfalls:
- Validate SHA-256 as exactly 64 lowercase hex characters, not merely a 64-character string.
- JSONL must reject blank/extra lines rather than silently skipping them.
- Use bounded handle reads (`limit + 1`), never `Path.read_bytes()` for untrusted artifacts.
- The write lock must cover replay, idempotency/conflict checks, construction, and replacement.
- Preserve denied authority boundaries: no provider, broker/order, scheduler, risk, promotion, deployment, secret, dispatcher, or generic executor path.
