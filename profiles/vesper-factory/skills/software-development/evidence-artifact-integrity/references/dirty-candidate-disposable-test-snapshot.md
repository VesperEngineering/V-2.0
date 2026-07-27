# Dirty-Candidate Disposable Test Snapshot

Use this recipe when a broad test suite must validate an uncommitted candidate but some tests or subprocesses write repository-relative paths that `pytest --basetemp` cannot contain.

## Why `--basetemp` is insufficient

`TMPDIR`, `TEMP`, `TMP`, `--basetemp`, and `-p no:cacheprovider` isolate pytest-owned temporary directories and cache. They do **not** redirect application constants such as `ROOT / "artifacts"`, generated assets, local databases, or subprocess outputs. A broad run can therefore leave ignored files in the source worktree even when every pytest fixture uses external temp.

Treat source/evidence isolation as a separate acceptance gate.

## Build an exact disposable candidate

1. Create an external clone or detached worktree-equivalent at exact `HEAD`; retain `.git` metadata for tests that call Git.
2. Export and apply the full tracked working-tree diff relative to `HEAD`, including staged and unstaged tracked bytes and deletions.
3. Copy every untracked candidate file into the same relative location.
4. **Raw-copy every candidate path from the source worktree after patch application.** On Windows, `core.autocrlf`, checkout filters, or patch application can turn LF into CRLF (or the reverse). A successful `git apply` proves semantic patch application, not raw-byte equality.
5. For a source path that is deleted, assert the snapshot path is absent. For every existing candidate path, compare existence, size, and raw SHA-256 between source and snapshot. Persist this manifest before tests.
6. Add only bounded copied test prerequisites to scratch. Avoid junctioning mutable canonical artifact/data roots into the snapshot; a test could then mutate the supposed read-only source.

The snapshot may remain dirty. Its contract is exact candidate bytes plus Git metadata, not a clean status.

## Run and close the gate

Use a second external root for pytest-owned temp:

```bash
mkdir -p D:/pytest_tmp_candidate/run
export TMPDIR='D:\\pytest_tmp_candidate'
export TEMP='D:\\pytest_tmp_candidate'
export TMP='D:\\pytest_tmp_candidate'
export PYTHONPATH='D:/candidate-snapshot'
python -m pytest -q -p no:cacheprovider \
  --basetemp='D:\\pytest_tmp_candidate\\run'
```

Afterward:

- Rehash all candidate paths in the disposable snapshot and require zero source-path drift unless a test explicitly owns a generated candidate file.
- Compare the source worktree's opening/closing `HEAD`, staged binary diff hash, unstaged binary diff hash, status/untracked list, and all canonical evidence hashes/sizes/mtimes.
- For frozen SQLite evidence, compare size/mtime and WAL/SHM presence; do not open the original just to hash-check metadata.
- Preserve the full pytest log and a node-ID comparison against the historical baseline.
- Classify failures into historical baseline, missing disposable-snapshot prerequisites, and genuinely new/relevant failures. A larger raw failure count is not automatically a regression; zero new relevant failures must be demonstrated, not asserted.

## Handling a non-isolated first attempt

If an initial in-worktree run reveals fixed-root writers:

1. Mark it diagnostic/non-admissible for the isolation claim.
2. Do not delete unknown ignored outputs: they may predate the run.
3. Build a fresh exact disposable snapshot and rerun the complete broad command there.
4. Keep both logs when they help prove the candidate repair did not change the failure set.

## Cross-binding warning

Hard-coded absolute worktree constants can make a module imported from the disposable snapshot verify files in the original worktree. Prefer an injectable root or test-process redirection. If redesign is outside scope, prove every referenced source byte is identical in both locations and disclose the cross-binding; never silently treat it as independent evidence.
