# Frozen Candidate Repair and Re-Freeze

Use when an independent review rejects an already staged, uncommitted candidate and authorizes a bounded repair in its isolated worktree.

## Preserve identity before edits

1. Record worktree root, branch, `HEAD`, `git status --short`, staged name-status, unstaged name-status, `git diff --cached --check`, and the staged binary diff SHA-256.
2. Require tracked index/worktree equality before the repair. If the candidate has unexpected unstaged tracked changes or an out-of-scope staged path, stop rather than folding it into the repair.
3. Keep canonical checkout, commit/push, scheduling, provider, dispatch, and authority changes outside scope unless separately authorized.

## Repair loop

- Use one RED → GREEN slice per review finding. Run each new adversarial regression with a fresh external same-drive `--basetemp` before production edits; retain the expected failure output.
- For hostile filesystem artifacts, never call a broad `read_bytes()` before enforcing size. Read at most `MAX_BYTES + 1` through a binary handle, reject oversize before JSON decode or hashing, and preserve distinct absent/read-error versus oversize fail-closed outcomes. Cover every reader of the artifact, including replay, pre-append state, sidecar/checkpoint, and recovery/suppression paths.
- Where a snapshot accepts an injected clock, thread that exact normalized timestamp through all embedded freshness readers. Test stale and future evidence relative to the injected timestamp and make wall-clock access fail in the deterministic test.
- For a report-only CLI, define exit semantics explicitly: report-only healthy/completed states may exit zero; `UNAVAILABLE` and unexpected states must be nonzero so automation observes failure. Do not add retry, scheduling, or remediation as part of an exit-code repair.

## Re-freeze

1. Run the complete required adjacent suites with fresh external temp roots after the final semantic edit. Run lint, compile validation, and `git diff --check` with bytecode output redirected outside the repository.
2. Remove only clearly identified candidate-local test scratch directories; never broad-clean an isolated worktree with unknown untracked files.
3. Stage the exact approved candidate allowlist explicitly, never with a broad add.
4. Verify `git diff --cached --check`, `git diff --quiet`, and that no untracked/staged test artifacts remain. Bind the refreshed candidate with `git diff --cached --binary | sha256sum`.
5. If a later explicit unverified-status signal appears, treat it as a fresh gate: rerun the relevant pytest selection immediately, read its real result, and report only that evidence. Do not edit solely to satisfy the signal.

The resulting staged candidate is for a new independent review only; do not self-approve or integrate it.
