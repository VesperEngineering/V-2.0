# Dirty Canonical Recovery Into an Isolated Candidate

Use this pattern when canonical contains broad tracked and untracked user work, local and cached-remote history diverged, and the reviewed result must be integrated without reset, stash, broad checkout, or accidental overwrite.

## 1. Never build the candidate in the dirty canonical checkout

1. Record canonical `HEAD`, branch, `git status --short`, tracked diff paths, untracked paths, worktrees, and cached remote refs.
2. Create a clean integration worktree from the exact cached/refreshed remote base.
3. Reconcile legitimate work in independently testable slices. For each slice:
   - identify the canonical patch and source owner;
   - run its focused tests before transfer when possible;
   - apply or semantically reconcile it in integration;
   - rerun focused tests, compile/lint/diff checks;
   - commit only that slice.
4. Preserve semantic intent when remote and local changed the same file; do not select wholesale `ours` or `theirs` for governance or authority surfaces.

## 2. Create an exact tracked-dirt safety ref

Before changing canonical paths, create a separate preservation branch/worktree from canonical `HEAD`:

```bash
branch="preserve/canonical-dirt-YYYYMMDD"
snapshot="D:/worktrees/canonical-dirt-snapshot"
git worktree add -b "$branch" "$snapshot" <canonical-branch>
git -C <canonical> diff --binary | git -C "$snapshot" apply --index -
git -C "$snapshot" diff --cached --check
git -C "$snapshot" commit -m "chore: snapshot pre-reconciliation canonical dirt"
```

This captures all tracked modifications and tracked deletions without touching canonical. It does **not** capture untracked files.

Verify every path against the snapshot commit. For a modified file, compare canonical `git hash-object <path>` with `git -C <snapshot> rev-parse HEAD:<path>`. For a tracked deletion, verify the snapshot commit also omits the path. Refuse to proceed on any mismatch.

Do not use this safety commit as the integration candidate; it is a recoverability ref for exact pre-reconciliation state.

## 3. Detect candidate-added/untracked collisions

A merge can fail or overwrite intent when the candidate adds a path that is currently untracked in canonical. Compute:

```text
(candidate paths with status A relative to canonical HEAD)
INTERSECT
(canonical git ls-files --others --exclude-standard)
```

For every collision:

1. read and classify the canonical untracked file;
2. copy it byte-for-byte to an external evidence/preservation directory;
3. compare SHA-256 of original and backup;
4. record both paths and digest;
5. do not remove or replace the canonical copy until candidate review is approved and the exact integration plan names that path.

Do not treat thousands of unrelated untracked/generated files as merge scope merely because they exist. Preserve them in place unless they collide.

## 3a. Freeze a byte-level manifest of all unrelated canonical dirt

A path-only `git status` snapshot proves names and status codes, not that unrelated user bytes survived integration. When canonical contains substantial tracked or untracked work, create an external content manifest immediately before the final integration gate:

- bind the canonical `HEAD` and raw `git status --porcelain=v1 -z --untracked-files=all` records;
- for each record, preserve the two-character status and normalized relative path;
- for a regular file, record byte size and SHA-256;
- for a symlink or junction-like path, record the link target without dereferencing it;
- for a tracked deletion, record an explicit missing/deleted marker;
- hash the completed manifest itself and keep it outside the repository.

Recompute the candidate-path/dirty-path intersection from the same live status snapshot. If the intersection is empty, the entire dirty-content manifest must remain byte-for-byte equivalent after the merge. If an authorized collision exists, compare all entries outside the explicit collision allowlist and verify the collision against its separate backup digest. Stop if canonical dirt changes between review and merge; refresh the manifest and integration review rather than silently accepting drift.

This manifest complements rather than replaces the tracked-dirt safety ref and untracked-collision backups. It is especially useful when thousands of untracked files make a broad preservation commit inappropriate. Never dereference links while hashing or let generated target contents turn a link identity check into an unbounded filesystem walk.

## 4. Freeze and verify the containing candidate

The review target is the **containing** integration SHA, not an earlier coordinator or subagent commit.

- Create a detached worktree at the exact SHA.
- Run focused changed-path suites with the project interpreter, candidate `PYTHONPATH`, and an external same-drive `--basetemp`.
- Run repository validators, JSON/schema checks, `py_compile`, critical Ruff, and `git diff --check`.
- Run the broad suite at the exact SHA and report its exit/status honestly.
- Never fabricate ignored data or copy canonical runtime artifacts merely to make the detached suite green.

Classify broad failures separately:

- candidate-path regression;
- existing checked-in baseline debt;
- machine-local/ignored-artifact coupling;
- missing local data/tooling;
- unrelated flaky or infrastructure failure.

Focused green evidence does not make a nonzero broad suite green, but a noisy broad baseline also does not erase verified changed-path evidence.

## 5. Dispatch an exact-SHA independent review correctly

The reviewer packet must name:

- full candidate SHA and base SHA;
- detached worktree;
- complete commit/diff range;
- preserved authority boundaries;
- exact tests/validators to rerun;
- known broad-suite failures;
- explicit read-only/no-side-effect restrictions.

In dependency-based Kanban systems, linking the review card as a child of a still-running implementation/goal can prevent dispatch. Either complete the implementation parent before linking, or create the review as a standalone card and record its relationship in the goal comments/receipt. Never force-promote a genuinely blocked dependent review.

Any tracked candidate edit after dispatch invalidates the verdict. Evidence files outside the candidate may be updated, but the reviewed tree must remain immutable.

## 6. Simulate the canonical merge before touching canonical

Use a disposable clean worktree at the current canonical `HEAD` and run the exact intended merge with `--no-commit`. This predicts content conflicts without changing the dirty checkout.

1. Require the conflict set to equal the expected set. Stop on any new path.
2. Resolve only from the already reviewed containing candidate or from a documented semantic reconciliation; never improvise a new candidate during integration.
3. After resolution, require the proposed merge tree to equal the approved candidate when that is the intended topology:

```bash
git diff --exit-code <approved-candidate-sha> --
```

4. Abort/remove the simulation worktree after recording the result.

If canonical history and the reviewed candidate intentionally produce the same final tree, prove tree identity both before and after the real merge:

```bash
git rev-parse HEAD^{tree}
git rev-parse <approved-candidate-sha>^{tree}
```

A merge commit may have distinct parents while still preserving the exact independently reviewed tree. Record both parents and both tree hashes.

## 7. Integrate only after approval

Before canonical integration:

1. require reviewer approval bound to the full containing SHA;
2. verify the candidate worktree is clean;
3. verify the safety-ref blob equality still matches current canonical tracked dirt, or create a new safety ref if canonical moved;
4. re-check untracked collisions and external backup digests;
5. prepare an explicit per-path plan: candidate wins, canonical dirt already preserved, untouched/unrelated, or collision handled from backup;
6. move each backed-up untracked collision out of the target path only after digest equality is proved;
7. if classified tracked dirt must be cleared before merge, use one exact path allowlist after the safety-ref equality check—never a broad restore, reset, stash, or clean;
8. avoid broad `git add`, `reset --hard`, `clean`, or unscoped restore operations.

After integration, verify canonical branch/HEAD, exact changed-file range, surviving unrelated dirt, intentional deletions, focused tests, validators, and any installed no-submit canary. For an installed preview canary, read back the exact action path and wrapper first, prove a hard `--no-submit` argument, run only that preview task, then bind Task Scheduler result, wrapper log, and generated receipt. A preview `0` proves preview plumbing only—it must not imply paper readiness or order authority. Synchronize issue/fact/status/health surfaces only after this installed-state evidence exists.

If broad-suite failures are caused by tests that are meant to be hermetic but read ignored canonical artifacts, replace that coupling with explicit temporary fixtures and rerun the tests; do not merely deselect them. Keep genuinely machine-local integration checks separate from unit tests.

Record candidate SHA, canonical integration SHA, safety-ref commit, collision-backup digests, commands/results, residual risks, and rollback instructions in the durable task receipt.

## Common pitfalls

- A tracked-dirt safety commit does not preserve untracked collisions.
- `git status` from an old handoff is not current evidence; re-read immediately before preservation and integration.
- A previously approved narrower coordinator commit does not approve a later containing branch with additional scheduler, VOT, or governance changes.
- Report-only documentation updates after exact-SHA review can invalidate the review target if they are committed into the candidate; either finalize receipts before review or obtain a narrow successor review.
- Markdown tracker labels are interfaces. Keep parser-consumed task fields on separate exact rows; semicolon suffixes or punctuation outside backticks can change extracted values.
