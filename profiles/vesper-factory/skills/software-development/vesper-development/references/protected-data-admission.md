# Protected V20 data admission pattern

Use this when a V20 task must admit a verified external/canonical artifact into a protected local data path. The normal rule remains read-only; this procedure applies only after the user explicitly approves the exact protected write and narrow code/test scope.

## Authority packet

Before any protected write, record:

- exact source and destination paths;
- expected byte count and SHA-256;
- allowed code and test files;
- required receipt/review evidence;
- explicit exclusions: training, active-model replacement, configuration, risk, execution, scheduler, broker effects, paid compute, and Factory implementation unless separately approved.

Planning approval is not implementation authority. Stop at the gate and ask one concise approval question.

## Isolation

If the main checkout has unrelated dirty state or another Factory/Codex worktree is active:

1. Preserve the dirty state exactly; do not stage, restore, or repair it.
2. Create a dedicated branch/worktree from the recorded clean commit for code and tests.
3. Do not inspect or operate inside the active Factory worktree.
4. Remember that protected data may be git-ignored: a file created only in a disposable worktree will not reach the main runtime through a merge. Plan the separately approved destination copy explicitly and verify it after integration.

## TDD sequence

Use vertical RED → GREEN slices:

1. Missing artifact fails before feature/label computation.
2. Hash mismatch fails closed.
3. Malformed schema, empty per-ticker factor maps, and invalid/non-finite/non-positive factors fail closed.
4. Reject duplicate JSON object keys explicitly (for example with `object_pairs_hook`); ordinary `json.loads()` silently keeps the last duplicate and can make a closed-schema validator falsely pass.
5. Reject ambiguous ticker normalization (leading/trailing whitespace or unexpected case) before coverage checks.
6. Required-universe coverage failure blocks use.
7. Known factor behavior is deterministic and explicit. Test a no-adjustment series, pre-first-factor dates, event dates, post-last-factor dates, OHLC treatment, volume treatment, and source-frame non-mutation. A repeat pipeline run must begin from the unchanged raw boundary so factors cannot compound silently.
8. For every consumer, test both boundaries separately:
   - negative integration: missing/unverified adjustments stop before data, feature, label, or evaluation work;
   - positive integration: adjusted prices—not raw bars—reach the feature/evaluation function.
9. Training and diagnostics use the same loader/adjuster and have no legacy-path or raw-price fallback.

Do not write all tests at once. Execute each new test and observe the expected RED before adding the minimum production behavior. A green unit test for the adjuster does not prove that a training or diagnostic entry point actually uses it.

## Interruption-safe continuation

Tool-call or context limits are not a reason to compress TDD, skip review, or claim a partial slice as finished.

- Keep all implementation on the dedicated worktree so an interruption leaves a recoverable checkpoint.
- In the handoff, distinguish the **last observed GREEN** from later production edits that have not yet been executed.
- If a gateway restart/session reset is needed, store resumable state with the task-progress facility—not ordinary durable preference memory—including branch, worktree, exact scope/approval, last observed GREEN, pending unexecuted test, untouched concurrent worktrees, and the next command/step.
- On resume, reload the governing skills, inspect the worktree identity/status, and run the narrow pending test before making another edit. Do not assume code added immediately before an interruption is correct.
- Continue the same RED → GREEN slice; do not restart, duplicate files, merge, or broaden scope merely because the session boundary changed.
- Only update durable project records after real verification; transient TDD details belong in task progress/session handoff rather than ordinary long-term memory.

## Admission and verification

- Copy source bytes without normalization or reserialization.
- Verify source hash = destination hash = declared receipt hash.
- Reject a pre-existing different destination; never overwrite silently.
- When the protected runtime path is git-ignored and implementation is isolated in a worktree, verify two deliberate copies: the approved main-runtime destination and a temporary worktree-local test copy. Never mistake the temporary copy for integration; remove it when the worktree is retired.
- Put the immutable machine-readable receipt in a tracked, non-ignored evidence path. Bind the protected artifact, OHLCV snapshot, universe, policy/feature/consumer file hashes, runtime versions, validation counts, label horizon, source/base commit, and all authorization booleans. Use file hashes plus the pre-change source commit to avoid the circular requirement of embedding a commit hash inside the receipt committed by that same commit.
- Run focused tests, `py_compile` for modified Python files, receipt-to-files hash verification, and the scoped project suite.
- Stage only the approved paths, then inspect the exact staged diff and git status for unrelated churn. The review target is the frozen staged candidate, including its final receipt.
- Obtain independent review before commit/merge. Any code, test, receipt, or staging change after that review invalidates the verdict and requires review of the new exact candidate.
- Record exactly what remains blocked (for example, backtests not yet wired) rather than broadening the approved slice.

## Session example (2026-07-25)

A verified read-only split-adjustment candidate at `D:\vesper\vesper_data\split_adjustments.json` had SHA-256 `f4f20d413783b0dd0d32b8bbf8e018d96b8098dba2351a2495737a8ec9dd763a`, 502 tickers, 2,479,293 entries, zero structural field errors, and complete coverage of the configured 100-symbol universe. The intended V20 destination was `vesper/data/massive/split_adjustments.json`. Treat these values as historical evidence only; re-hash and revalidate the current source before any future admission.
