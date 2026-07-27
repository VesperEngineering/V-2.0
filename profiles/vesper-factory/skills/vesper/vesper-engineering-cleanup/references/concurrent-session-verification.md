# Verifying a Concurrent/Finished Agent's Changes

How to independently verify a code slice that another Hermes/Codex session left in
the working tree (uncommitted), then hand back a trustworthy verdict. Burned in by
the VOT verification session (2026-07-18): Sol left a repaired-but-uncommitted VOT
slice; the job was to verify it without owning it.

## 1. Establish the working-tree state first

```bash
git status --short          # what's modified / deleted / untracked
git log --oneline -5        # last committed baseline
```

Note deletions explicitly (e.g. `app/vot_kanban.py` deleted) and confirm nothing
still imports a deleted module:
`grep -rln "import vot_kanban\b" app/ tests/ | grep -v vot_kanban_data`
(beware false positives from similarly-named modules — check the actual import).

## 2. Independent verification battery (read-only)

Run in order; each is cheap and objective:

1. **Compile:** `python -m py_compile <files>`
2. **Import:** import each module, catch exceptions
3. **Lint:** `ruff check <files> --output-format=concise` (report exact codes)
4. **Focused tests:** run the slice's own tests
5. **Live-data smoke:** for a data/UI app, drive one real fetch/refresh cycle and
   confirm real values (not fabricated placeholders). For Tkinter, instantiate the
   app headless (`tk.Tk(); root.withdraw()`), call its refresh, drain its queue,
   confirm the expected payload arrives.

On Windows, if pytest dies with `PermissionError ...\Temp\pytest-of-<user>`, that's
environmental, not a red suite — set `TMPDIR/TEMP/TMP` to a writable dir and add
`-p no:cacheprovider`. See `vesper-windows-integration` pitfalls.

## 3. Classify failures: introduced vs pre-existing

When the tree is dirty and tests are red, decide whether the tree caused them by
running the SAME failing tests against the committed baseline:

```bash
git stash push -u -m "classify-baseline"   # tracked + untracked
python -m pytest <failing-tests> -q        # at committed HEAD
git stash pop                              # restore
```

- Identical failures at HEAD → **pre-existing**, NOT introduced by the tree.
- Pass at HEAD, fail in tree → **introduced** by the tree.

After `stash pop`, confirm full restore: no `--diff-filter=U` conflicts, dirty-file
count back, a known edit present (e.g. its lint signature or a new file). Drop the
stash only after `git diff stash@{0} --stat` is empty.

## 4. Further classify by root cause, not just "pre-existing"

"Pre-existing" is not one bucket. Split so the fix path is obvious:

- **Strict-string drift** — test asserts a literal string the docs/comments no
  longer contain verbatim. Fix = update test or restore the contract token.
- **Behavioral in a retired/legacy path** — test exercises code under `deploy/` or
  an old module that is clean and unsupported. Usually touch nothing.
- **Replaced literal contract sentence** — the other agent rewrote a sentence the
  test asserts verbatim; semantics improved. Fix = update the test to the new
  contract, don't revert the improvement.
- **Structural / fail-closed-by-design** — the gate is correctly refusing; the test
  asserts the old permissive expectation. This needs a *governance decision*, not a
  code fix: either emit the missing governance key (make the capability enable-able)
  or update the test to inject the expected manifest explicitly (keep fail-closed).
  Verify mutations are hard-closed before concluding there's no security exposure.

## 5. Scope the verdict to the evidence

Say exactly what the checks proved, no more. "Builds, imports, passes focused
tests, pulls live data" is a **smoke signal**, not "release-verified" or
"up-to-date". If you ran a narrower battery than the artifact's own release gate
(full repo pytest, real `.lnk` launch, visual no-scrollbar/no-console check,
staging/commit), enumerate the gate items you did NOT run. **Read the other
session's own findings/repair report before issuing a verdict on the same
artifact** — don't conclude readiness from your subset while ignoring a broader
pending gate. The user's correction in the source session: a green build check was
mistaken for release readiness and had to be walked back.

## 6. Independent confirmation via subagents

For a second opinion, dispatch read-only `delegate_task` subagents with: the exact
files, the constraint "do NOT edit/commit/stash", the pytest-temp workaround, and a
numbered checklist. Have one verify code/runtime and another verify integration
(e.g. read-only DB reads, CLI-only writes, redaction, gated mutations). Require
line-level citations for authority/redaction claims.
