# Verification & Baseline Classification

Condensed, reusable recipes for (a) giving a second opinion on another agent/session's
verification claims and (b) classifying test failures as pre-existing vs. introduced by
uncommitted working-tree changes. Written for the Vesper repo but the patterns are general.

---

## 1. Second-opinion verification workflow

When the user says "verify what session X did" or "run the tests X ran so I can get a
second opinion":

1. **Read X's actual report first.** Do not run your own battery and declare a verdict.
   X's report contains its real release gate ("still required" list), its claimed test
   counts, and its audit findings. Your job is to *reproduce and check*, not to substitute.
2. **Replicate X's exact runs.** Match the reported counts before widening the net.
   - If X reports "73 passed, 2 failed" and your `-k` boundary gives "150 passed, 0 failed",
     your selection boundary differs. Bisect the `-k` expression or test-path set until you
     reproduce X's number, OR report that X's count is not reproducible and show the
     widest-net result as the honest answer.
3. **Scope the verdict to what you ran.** A headless instantiate + one `refresh()` + a
   focused `-k` pytest is a **build/smoke signal only**. It proves the code builds, imports,
   and pulls live data once. It is NOT a release verification. Never say "up-to-date" or
   "release-ready" on that basis. Correct phrasing: "green on my checks; X's release gate
   still stands."
4. **Do not claim a `.lnk`/desktop-shortcut launch from a headless probe.** A Tk app that
   builds under `tk.Tk()` + `withdraw()` does not prove the shortcut target, `pythonw.exe`
   command line, no-console-flash, or scrollbar rendering. Those need a real launch.

### Windows pytest temp-dir gotcha

Symptom: `PermissionError: [WinError 5] Access is denied: '...\\Temp\\pytest-of-<user>'`.
This is environmental (a stale/locked temp dir), NOT a code failure. Fix:

```bash
mkdir -p /tmp/votpytest
TMPDIR=/tmp/votpytest TEMP=/tmp/votpytest TMP=/tmp/votpytest \
  python -m pytest tests/ -k vot -q --no-header -p no:cacheprovider
```

Use `python` (not `python3`) on this Windows git-bash host.

---

## 2. Baseline-classify failures (pre-existing vs. introduced)

The question: did the dirty working tree cause this failure, or was it already broken at
the last commit?

### The stash-verify-restore procedure

```bash
git stash push -u -m "classify-baseline"   # -u captures untracked files too
git log --oneline -1                        # confirm HEAD == committed baseline
pytest <exact failing tests> -q             # identical command as the tree run
git stash pop                               # restore the work
git diff --name-only --diff-filter=U        # empty => no conflicts
git diff stash@{0} --stat                   # empty => tree matches stash
pytest tests/ -k <fast focused> -q          # confirm tree still works
git stash drop stash@{0}                    # only after the pop is confirmed clean
```

Interpretation:
- **Fails identically at baseline** => PRE-EXISTING. The tree did not cause it. Say so and
  do not let the tree's owner absorb the blame.
- **Passes at baseline, fails in tree** => INTRODUCED by the working tree.

Safety notes:
- `git stash pop` reporting "The stash entry is kept" is usually a harmless untracked-dir
  warning, not a conflict. Confirm with `git diff --name-only --diff-filter=U` (empty) and a
  re-run of a fast test before dropping the stash.
- The `-u` pop may warn "failed to remove <dir>: Permission denied" for an untracked dir it
  couldn't clean — harmless; the stash still applied.
- Pre-existing "preserve concurrent ..." stash entries are normal in this repo. Count stashes
  before and after; only drop the one you created.

### Token-presence attribution (which change caused a doc/string drift)

```bash
git show HEAD:<file> | grep -c "<token>"   # present at committed HEAD?
grep -c "<token>" <file>                   # present in working tree now?
git status --short -- <file>               # clean (committed) or M (tree-edited)?
```

- Token present at HEAD, absent now, file is `M` => the working tree removed/changed it.
- Token absent at HEAD, file clean => pre-existing strict-literal drift; the test needs updating.
- When a tree edit *replaced* a literal contract sentence with a more precise one
  (semantics improved, old literal gone), that is **test-needs-update**, not a code bug.

---

## 3. Failure taxonomy (label before recommending a fix)

| Kind | Signal | Verdict | Action |
|------|--------|---------|--------|
| Strict-literal-string | test asserts exact doc wording; doc file is clean | Pre-existing drift | Update test or doc; no logic risk |
| Retired/legacy-path | test imports a `deploy/` or superseded copy | Pre-existing drift | Leave retired path alone unless re-enabling |
| Tree-replaced literal | HEAD had token, tree removed it, semantics improved | Test needs update | Update test to new contract; confirm semantics |
| Structural governance | fail-closed gate holds; test expects board-only enablement | Design decision | Route authority question to user; NOT a live bug |
| Behavioral routing | status/decision mismatch in live logic | Investigate as real bug | systematic-debugging |

### Provider-policy structural case (Vesper example)

`load_operator_provider_policy` requires unanimous board + lane + autonomy manifest agreement,
but `lane_manifest.build_lane_manifest()` never emits the `operator_provider_telemetry` key, so
`.get(...)` returns `{}` and every capability locks. Mutations are hard-closed
(`mutations_allowed: Literal[False]`), so there is no security exposure — the fail-closed design
is working. The failing tests expect board-only enablement. Fix options (user decides):
(a) emit the key from the lane manifest so the capability *can* be enabled unanimously, or
(b) have the tests inject `lane_policy=` explicitly (as the sibling disagreement test does),
keeping the capability locked by default. This is an authority/design call, not a defect to patch
unilaterally.
