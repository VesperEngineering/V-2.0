# Read-only review of interactive operator-dashboard diffs

Use this checklist when independently reviewing uncommitted dashboard/TUI changes and the user forbids edits.

## Freeze the exact patch

Capture tracked staged and unstaged scope separately, then together:

```bash
git status --short
git diff --stat
git diff --name-status
git diff --check
git diff
git diff --cached --check
git diff --cached --name-status
git diff HEAD | sha256sum
```

Plain `git diff` excludes staged and untracked content. Use `git diff HEAD` for all tracked uncommitted changes; inspect untracked files only when explicitly in scope. Recompute the changed-file list and patch hash before reporting. If either moves during review, invalidate earlier conclusions and re-inspect the final patch.

### Concurrent-staging sentinel

Use the exact same staged-patch command at every checkpoint, for example:

```bash
git diff --cached --binary --no-ext-diff | sha256sum
```

- Check it after initial freeze, immediately before tests, immediately after tests, and before reporting. Hashes made with different diff options are not comparable.
- If the review contract says to fail closed on movement, **one observed hash change is terminal for that review**. Do not silently adopt the later patch and upgrade the verdict; earlier inspection and test evidence belongs to a different candidate.
- Interpret porcelain XY status before testing. `MM path` means the index and worktree both contain changes. Python imports, pytest, builds, and most linters exercise the worktree—not the staged blob—so their results cannot certify that index candidate.
- A transition from `MM path` to staged-only `M  path`, accompanied by a new cached-patch hash, is evidence that concurrent staging occurred even if the worktree is clean afterward.
- If staged and unstaged changes overlap, test an isolated index materialization outside the repository only when temporary files are allowed; otherwise stop and report the mixed-worktree blocker without staging, stashing, or editing.
- Any passing test run bracketed by patch movement must be labeled **transient/stale evidence**, never release evidence.

## Preserve a no-write worktree

- Never stage, stash, format, auto-fix, commit, or run mutating hooks.
- Use `PYTHONDONTWRITEBYTECODE=1` for Python probes.
- Use pytest `-p no:cacheprovider` and temporary directories outside the repository.
- Compare final status and patch hash with the pre-review snapshot.
- Report whether the reviewer modified any worktree file.

## Adversarial probes that passing tests often miss

### Focus, visibility, and key dispatch

Render a width/height matrix that includes default dimensions, each layout breakpoint, and just-below/just-above values. For every focusable/actionable panel, prove that:

1. its selected target is visible, not merely its title;
2. action/scope text is not silently clipped;
3. the key handler acts on the visibly focused target; and
4. a hidden or vertically truncated panel cannot retain active mutation/approval shortcuts.

Include long unbroken action names, identifiers, and scopes. `textwrap(..., break_long_words=False)` followed by slicing still loses data.

### Approval versus execution

Trace decision recording, approval state, execution authorization, and the execution consumer separately. A recorded approval is not execution authority. UI audit text must never claim an exact-scope review unless dispatch required the operator to open and inspect an untruncated detail view.

### State-transition integrity

Probe new, repeated, already-active, expired, stale, and malformed states. A transition may record only facts it actually establishes—for example, ownership and a start timestamp—not guessed progress, completion, verification, cost, or receipt evidence. Starting or repeating an item whose progress is absent must preserve `None`/unknown and render `not reported`, never insert `0%`. Add a fixture-level regression that asserts both the returned projection and the persisted document omit the missing evidence field.

### Provider accounting

Send successful, unavailable, and schema-invalid-but-valid-JSON fixtures, including missing `data`, mapping-valued `data`, list top levels, and `null`. Invalid schema must preserve the last-good snapshot as stale and must never overwrite it with a fresh zero. Any reconciliation derived from stale account usage must visibly inherit the same stale state.

### Launch-relative session counters

Test duplicate session IDs, newest-complete versus newest-incomplete precedence, initial existing sessions, genuinely new post-launch sessions, counter resets, and sessions that reappear after transient nondiscovery. Do not count a session's lifetime total as launch delta unless evidence shows it began after launch.

## Verdict

Lead with **PASS** or **FAIL**. Separate blocking logic/security defects from suggestions, name positive closed-authority findings, list exact verification run, and fail closed if the final diff remains unstable or cannot be fully inspected. A passing test suite does not override a minimal reproduced defect.