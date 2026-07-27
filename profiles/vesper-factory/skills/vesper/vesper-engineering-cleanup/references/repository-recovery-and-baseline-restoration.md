# Repository Recovery and Baseline Restoration

Use this when a Vesper worktree contains a large, ambiguous deletion set or when a small surviving test suite is green only because established tests disappeared.

## Recovery sequence

1. Read `git status --short`, staged/unstaged stats, CI workflow commands, and the current governance files before editing.
2. Preserve both tracked diff layers separately with binary-safe Git patches:
   - `git diff --binary --output=<archive>/unstaged.patch`
   - `git diff --cached --binary --output=<archive>/staged.patch`
   - Save `git status --short` and the deleted-path inventory beside them.
3. Count deleted tracked files by class. Pay particular attention to tests, execution guards, launchers, governance validators, and workflow-referenced paths.
4. Restore only paths whose current status is deleted. Do not overwrite modified or untracked work. Batch explicit paths through `git restore --worktree -- <paths>`.
5. Verify that the remaining deleted count is zero and that workflow-required files exist.
6. Run validation in layers:
   - workflow-required compile/test slice;
   - failure-cluster tests;
   - broad non-optional suite;
   - full suite in a fresh process.
7. Treat a formerly green reduced suite as non-evidence. Report both the surviving-suite result and the restored-baseline result.
8. Do not commit merely because deletions were restored: restoring unstaged deletions to `HEAD` may produce no commit diff. Commit only intentional repairs that have focused passing evidence and an understood broad-suite state.

## Failure-cluster triage

Group failures by shared cause before editing. Common classes:

- incomplete CLI/product rename;
- mixed SQLite storage representation;
- current-workspace tests depending on ignored historical artifacts;
- governance tracker drift;
- optional ML runtime corruption contaminating an in-process broad run;
- stale tests asserting retired GUI selectors or old documentation structure.

Use RED-GREEN for actual code defects. For stale tests, update them only when repository history/current source proves the contract changed intentionally.

## Rename rule

A CLI/product rename is atomic across launchers, production command constructors, tests, fixtures, docs, workflow commands, safety markers, and historical evidence contracts. Never change scattered call sites while deleting the compatibility entry point. If the migration cannot be completed and verified as one slice, keep the canonical compatibility path and defer the rename.

## SQLite timestamp boundary

Legacy Vesper SQLite tables can contain integer epochs and ISO-like text timestamps in the same column. Boundary readers must:

- accept integer/float epochs;
- accept numeric epoch strings;
- accept ISO-like text, including `Z`;
- classify malformed values as unknown/missing and fail closed;
- never let `int(MAX(timestamp))` crash operator or launcher output.

Add mixed-storage regression coverage at every freshness/health reader, not just the first crash site.

## Historical ignored evidence

Never fabricate PASS receipts to satisfy tests. If a restored integration test requires ignored historical evidence that is unavailable:

1. Prefer making the test hermetic with explicit temporary fixture paths.
2. If the production command deliberately consumes a historical chain and cannot be made hermetic in the current slice, conditionally skip with the exact missing prerequisite and retain unit-level fail-closed coverage.
3. Record that skipped integration coverage must be restored later; do not report it as passing.

## Pytest isolation

Keep CI `--basetemp` outside repository-owned artifact trees when concurrent or nested runs can delete each other’s temporary directories. Validate the workflow and receipt contract against the same external path.

If an optional runtime such as PyTorch/Triton enters a corrupt re-registration state or segfaults after a broad run, rerun its tests in a fresh process. Preserve the distinction between deterministic repository failures and process/runtime contamination.

## Completion bar

- Original staged and unstaged state is recoverable.
- No unexplained tracked deletions remain.
- Workflow-required paths exist.
- Focused repair clusters pass.
- Broad-suite remaining failures are classified with exact evidence.
- No fake receipts, broad resets, unrelated reverts, or safety-boundary widening occurred.
- Commit/push happens only for a curated, verified slice.
