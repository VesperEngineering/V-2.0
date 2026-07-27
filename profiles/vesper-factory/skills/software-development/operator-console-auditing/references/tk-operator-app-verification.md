# Read-only verification battery — Tk operator dashboard (VOT)

Use when the user asks to verify a Tkinter operator app (e.g. Vesper's VOT) is
"up-to-date, functioning, no code errors, producing correct information, and will
run" — **without editing anything**. Output is a findings list, not fixes.

Run each layer independently and report per-layer pass/fail. A green layer does
not excuse a red one; report all of them.

## 0. Establish tree state first

A concurrent session may have uncommitted changes in flight (deleted files,
modified modules). Record this before trusting any result:

```bash
cd /d/vesper && git status --short && git branch --show-current && git log --oneline -5
```

Flag explicitly if the tree is dirty — verdicts apply to the **working tree as
found**, not the last commit, and should be re-run after the other session commits.

## 1. Lint + syntax + import (static health)

```bash
ruff check app/<modules>.py                 # all VOT modules
for f in app/<modules>.py; do python -m py_compile "$f"; done
python -c "import app.mod1, app.mod2, ..."  # every module imports
```

Check for **dangling references to deleted files** (e.g. a module the other
session removed): grep for `import <deleted>` / `from app.<deleted> import` and
confirm zero hits. Ripgrep does NOT support lookahead — use a plain pattern and
filter, not `foo(?!bar)`.

## 2. Tests — Windows pytest temp-permission workaround

A first run may fail with `PermissionError: [WinError 5] Access is denied:
'C:\Users\<u>\AppData\Local\Temp\pytest-of-<u>'`. This is **environmental**, not
a code failure. Re-run with a redirected temp dir before concluding anything:

```bash
mkdir -p /tmp/votpytest
TMPDIR=/tmp/votpytest TEMP=/tmp/votpytest TMP=/tmp/votpytest \
  python -m pytest tests/ -k "<app>" -q --no-header -p no:cacheprovider
```

Distinguish collection/permission **errors** (environmental) from assertion
**failures** (product defects). Never report a temp-ACL error as a product bug.

**Cross-mount gotcha:** redirecting `TMPDIR` to an MSYS path (`/tmp/...`) lands
pytest's tmp on the `C:` mount while the repo lives on `D:`. Any test that calls
`os.path.relpath(path, "D:/...")` then fails with `ValueError: path is on mount
'C:', start on mount 'D:'` — a false positive, not a defect. Point temp at the
**same drive** as the repo instead:

```bash
mkdir -p /d/vesper/.pytest_tmp
TMPDIR="D:\\vesper\\.pytest_tmp" TEMP="D:\\vesper\\.pytest_tmp" TMP="D:\\vesper\\.pytest_tmp" \
  python -m pytest tests/ -q --no-header -p no:cacheprovider
rm -rf /d/vesper/.pytest_tmp   # clean up scratch afterward
```

## 3. Live data correctness (against real sources, not fixtures)

Instantiate the data layer directly and pull real data:

- **Kanban / SQLite layer:** open the DB read-only
  (`file:<path>?mode=ro`, `uri=True`), confirm schema columns match every query,
  then call each fetch function and check row counts are sane (not just non-zero).
  Verify the roster includes every expected agent and detail returns
  comments+events+latest_summary.
- **Version label:** call the label function; confirm it is a **semantic
  `vX.Y.Z`**, not a git SHA (user preference — VOT shows semver).
- **Provider usage:** run the app's **real refresh cycle** end-to-end (below) and
  confirm it returns actual provider numerics, not the placeholder.

## 4. Runtime smoke — real Tk app + full refresh drain

Tkinter instantiates on Windows without a visible window using `withdraw()`.
Drive the real refresh and drain the app's own `pending` queue like the mainloop
would — this is the strongest evidence the app "will run":

```python
import queue, time, tkinter as tk
from pathlib import Path
root = tk.Tk(); root.withdraw()
from app.vot_tk import VotTkApp
app = VotTkApp(root, Path('D:/vesper'))
root.update_idletasks()
app.refresh()                                # spawns background snapshot thread
deadline = time.time() + 90
got = {}
while time.time() < deadline and 'snapshot_complete' not in got:
    try:
        kind, payload = app.pending.get(timeout=2); got[kind] = payload
    except queue.Empty: pass
snap = got.get('snapshot')
pa = getattr(snap, 'provider_accounting', None)   # real numerics or None
print(getattr(pa,'openai_remaining_percent',None),
      getattr(pa,'openrouter_remaining_budget_usd',None))
root.destroy()
```

Expect queue messages like `kanban_live`, `snapshot`, `snapshot_complete`. Confirm
`provider_accounting` carries **real** values (e.g. `OAI 93% left · OR $29.38
left`), proving the snapshot→provider→appbar path is wired, not stubbed.

## 5. Appbar / label rendering

Test the pure formatter directly for both the typed-numeric path and the
unavailable-fallback path. Confirm usage renders as **percent/budget remaining**,
never raw token counts (user preference). Icon assets should exist on disk and be
referenced behind a `try/except tk.TclError` guard.

## Verdict discipline — do not overstate from a narrow battery

A green battery proves the layers you ran, nothing more. Before writing a
bottom-line verdict, ask whether a broader audit or another agent's report
exists. If your run was narrower (e.g. focused tests only, no live launch, no
full-repo pytest), say exactly which layers you verified and which you did NOT —
never let "passes lint + focused tests + one live refresh" become "up-to-date and
verified." When a concurrent session's audit already reached a different verdict
(e.g. "not yet release-verified"), reconcile scope explicitly: state what your
checks confirm, what theirs cover that yours did not, and which verdict governs.
Overstating assurance is a first-class trust defect — the user will catch it, and
it is worse than reporting a blocker.

## 6. Verify a concurrent session's uncommitted work (stash → baseline → restore)

When another agent/session leaves the tree dirty with repairs and you must judge
whether failures are **pre-existing** or **introduced by their edits**, do not
guess — test the committed baseline directly:

```bash
cd /d/vesper
git stash push -u -m "verify-baseline"      # capture ALL edits + untracked
# ... run the suspect tests against the clean committed baseline ...
git stash pop                                # restore their work EXACTLY
git stash drop stash@{0}                     # only after confirming pop applied
```

Then compare: a test failing **identically** at baseline and in the working tree
is pre-existing (not the other session's fault); failing only in the working tree
is introduced. Confirm the restore is intact afterward (file count matches, the
other session's marker edits/imports are present, focused tests still pass)
before dropping the stash — `git stash pop` sometimes reports "stash entry is
kept"; verify no conflict (`git diff --diff-filter=U` empty) and that the working
tree matches (`git diff stash@{0} --stat` empty) first. Leave pre-existing
"preserve concurrent..." stashes from other sessions untouched.

Failure-classification buckets worth naming in the report: (a) pre-existing
strict-string drift (test asserts literal doc text that changed), (b) a repair
that replaced a literal contract sentence — test needs updating, not the code,
(c) structural design gaps (e.g. a loader requires a manifest key that no source
ever emits) — fail-closed still works, but the capability can never enable;
recommend the conservative test-side fix (inject the dependency explicitly)
unless the user rules the capability should be enable-able.

## Reporting order

Lead with the dirty-tree caveat, then per-layer ✅/❌:
lint / syntax / imports / stale refs / tests / live data / version / provider /
runtime. Close with items to **re-check after the concurrent session commits** —
never claim the verdict survives the other session's pending edits.
