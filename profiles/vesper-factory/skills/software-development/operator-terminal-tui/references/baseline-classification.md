# Baseline classification — pre-existing vs. newly-introduced test failures

When a failing test sits adjacent to someone else's uncommitted repair slice, the first question is: **did this change introduce the failure, or was it already broken at the last good commit?** Answer with evidence before assigning cause or proposing a fix.

## The technique

```bash
git stash push -u -m "baseline-classify"   # stash tracked + untracked (-u)
# ... run the EXACT failing tests against the clean baseline commit ...
git stash pop                              # restore the repair slice
git stash drop stash@{0}                   # only after confirming pop applied cleanly
```

## Reading the result

- **Fails identically at baseline and in the working tree** → **pre-existing**, not introduced by the slice. Do not attribute it to the repair; do not let it block the slice's release verdict.
- **Passes at baseline, fails in the tree** → introduced by the change; investigate the diff.

## Verify the restore before dropping the stash

- `git status --short` file count matches the pre-stash count; key files are present.
- A focused test re-runs green after the pop.
- A `git stash pop` that prints "The stash entry is kept in case you need it again" usually **still applied cleanly** — confirm with `git diff --name-only --diff-filter=U` (empty = no conflicts) before `git stash drop`. Don't assume the keep message means failure.

## Report per-test verdicts, not a blanket claim

Classify each failing test individually. In one Vesper session, 8 adjacent failures broke down as: 6 pre-existing (doc-string drift + retired-path behavior), 1 a stale board-route assertion, 1 a test-environment false positive. None were introduced by the slice under review.

## Distinguish a broken test from broken behavior

A failing test is not automatically a code bug. Before "fixing" code, determine which moved:

- **Live-state-dependent tests** assert a transient condition (a board route, timestamp, registry state) that legitimately advances. Symptom: the builder/guard still returns the fail-closed value, but the *routing/next-action* expectation is stale. Fix = update the assertion to the current correct value while keeping every fail-closed/redaction/guard assertion intact — do NOT loosen the guard itself. Verify by running the underlying builder directly and inspecting returned values, not just the rendered string.
- **Brittle exact-string contract tests** assert literal doc/markdown text since reworded (often for the better). Fix = update the test to the current authoritative string, or scope the assertion to where the content actually lives — do NOT mangle improved docs to satisfy a stale literal.
- **Real behavioral regressions** = the guard/validation now returns a weaker value. Fix the code, not the test.

## Windows pytest temp pitfalls (companion to windows-tui-debugging.md)

- A stale `%TEMP%\pytest-of-<user>` dir causes `PermissionError` before assertions run — this is infrastructure, not a product failure.
- Redirecting `TMPDIR`/`TEMP`/`TMP` to an **MSYS** path (e.g. `/tmp/...`) can land pytest tmp on a different Windows drive than the repo. Tests that call `os.path.relpath(path, repo_root)` then fail with `ValueError: path is on mount 'C:', start on mount 'D:'` — a **cross-mount false positive**, not a defect. Use a **repo-local** `--basetemp` on the same drive (e.g. `D:/vesper/.pytest_run`) to avoid both the permission and the mount problems.
