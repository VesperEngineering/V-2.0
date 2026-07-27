# Incremental Display Iteration Reference

Use this reference for one-pass worker-display improvements.

## Pass contract

- One pass = one new display idea, not a mixed redesign.
- Keep the newest accepted version as the baseline.
- A candidate replaces the baseline only when it improves code quality,
  accuracy/data lineage, and actual execution/readability.
- Record the pass as `WD-###` with its implementation commit, contract,
  verification evidence, and baseline decision.

## Recommended verification sequence

1. Inspect `HEAD`, branch, porcelain status, launcher interpreter, renderer,
   snapshot model, focused tests, and the visual reference if supplied.
2. Add one focused RED test for the desired display behavior.
3. Run the literal `pytest` command with the project virtualenv's `Scripts`
   directory first in `PATH`, `-p no:cacheprovider`, and an external
   `--basetemp`.
4. Implement the smallest truthful pure-render change. Preserve state
   vocabulary: `delegated` is not `running`, owner assignment is not activity,
   and missing values are not zero.
5. Probe the pure renderer at each supported grid. Assert row count, maximum
   line width, footer placement, and breakpoint visibility. Treat this as
   geometry/readability evidence, not visual acceptance.
6. Run the focused layout/controller/provider suite, then the broader suite,
   then rerun the focused suite after the broad run. Classify unrelated dirty-
   worktree failures by exact path instead of silently repairing them.
7. Run added-lines Ruff for legacy files, strict `E9,F`, compilation, and
   `git diff --check`. Full-file Ruff may expose pre-existing debt; do not call
   that new debt or perform drive-by cleanup.
8. Commit only owned paths, verify the commit in a clean temporary worktree,
   push, and confirm the live remote ref with `git ls-remote`.

## Useful target grids

For Vesper's current mission-control layout, probe at least `312x63`, `180x50`,
and `120x35`. Require compact layouts to preserve governance-critical state
and footer shortcuts even when the new card is intentionally hidden.

## Provenance-strip pattern

For provider/token accounting, use bounded scope rows when one legend would clip
at medium widths:

```text
SCOPE  OpenAI=workspace/session  OpenRouter=account
SOURCE OpenRouter=key/credits  Receipts=Vesper-local
```

Keep this adjacent to the numeric lines. Probe `120x35` as well as wide grids;
full-width text that only survives `312x63` is not an effective operator
format. Scope labels must describe actual authorities, not implementation
names, and must never imply that local receipt totals are provider-account
totals.

## Kanban/state-board pattern

A lane board should display counts and bounded rows, with the state label on
every row. Keep delegated work in a truthful pending/review state, preserve
blocker reasons, and never infer worker execution from lane ownership. A board
is a view of current evidence, not an action or authority surface.
