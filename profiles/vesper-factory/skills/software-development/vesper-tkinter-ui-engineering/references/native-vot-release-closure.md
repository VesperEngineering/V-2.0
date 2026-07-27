# Native VOT production-readiness and release closure

Use this checklist when the operator asks whether a redesigned VOT is **up and running**, or asks to finish and launch it. It prevents mockups, architecture foundations, passing unit tests, and isolated worktree code from being mistaken for a deployed desktop program.

## Readiness levels

Report the highest level actually proved:

1. **Visual direction approved** — mockups only.
2. **Data/view-model foundation implemented** — pure models or adapters exist, but the production Tk pages may not consume them.
3. **Production UI implemented in an isolated branch** — pages exist and tests pass, but canonical and the Desktop launcher do not use them.
4. **Canonical integration verified** — exact candidate is in the canonical root and focused/adjacent tests plus smoke mode pass there.
5. **Running desktop verified** — the real shortcut launched the canonical build; exact process, HWND/title/version, screenshots, page navigation, and idle behavior were checked.

Only level 5 supports “up and running.” State lower levels explicitly instead of compressing them into “almost done.”

## Inspect before editing or launching

1. Read the actual Desktop shortcut target, arguments, working directory, and icon.
2. Identify the canonical entry point and semantic version.
3. Inspect exact process identity. Exclude the process-inspection command itself and shell wrappers; require the expected `pythonw.exe -m app.vot_tk`, canonical working directory, and visible HWND/title.
4. Compare the design branch to canonical with merge-base, branch-only commits, and changed files.
5. Determine whether the branch contains actual page modules and entry-point wiring or only plans, docs, tests, and view-model foundations.
6. Do not launch the old shortcut merely to prove it exists when the user asked for the new design; first establish what it will run.

## Build in bounded vertical slices

A full Layout I–N rebuild is too large for one opaque “implement everything” coding-agent pass. Use serial, independently green slices:

1. workflow graph/source adapter;
2. knowledge and action normalization;
3. decision normalization;
4. provider/System Spine/research/issue source corrections;
5. shared shell and appbar;
6. one complete Workflow tracer;
7. remaining pages;
8. refresh coordinator and smoke mode;
9. dead-topology retirement;
10. release verification and visual closure.

For every slice:

- begin from a clean, isolated worktree;
- add focused RED tests;
- implement the smallest vertical path;
- run the exact focused tests with a native external Windows pytest temp directory;
- inspect the diff and update the master engineering record in the same slice;
- commit only after GREEN;
- rerun the focused gate independently before treating the commit as accepted input to the next slice.

Do not count an agent’s prose, uncommitted diff, or reported test number as completion. Read back Git state and rerun the exact gate.

## Recover a stalled coding-agent coordinator

A long autonomous coding session may finish a child slice but leave its parent coordinator waiting indefinitely (for example, an internal collaboration wait) even though the worktree has a clean new commit.

Recovery procedure:

1. Inspect `git status`, recent commits, and the exact focused test gate.
2. If the tree is dirty, independently run the focused tests and preserve the diff; do not claim completion.
3. If the slice is clean, committed, and independently GREEN, record that immutable boundary.
4. Terminate only the stalled coordinator process; do not reset or rewrite the clean commits.
5. Resume the same coding session or start a new direct worker from the verified HEAD with one explicit next slice.
6. Tell the resumed worker to work serially and not wait on already-completed collaborators.

Avoid repeated blind waits. Silence is neither failure nor progress; Git state and real test output decide.

## Canonical integration gate

Before merging:

- candidate worktree clean;
- branch diff fully inventoried;
- focused and adjacent VOT suites green;
- Ruff, compile, smoke mode, and diff checks green;
- final frozen candidate independently reviewed;
- unrelated canonical dirt inventoried and left untouched;
- merge/reconciliation method proven not to absorb unrelated files.

After integration, rerun all release evidence from canonical. Worktree test output does not prove the Desktop shortcut’s target.

## Real Windows launch gate

After the final canonical source change:

1. Read back the `.lnk` contract.
2. Launch the `.lnk`, not merely `python -m` from a shell.
3. Verify one intended `pythonw` runtime, canonical CWD, visible window, and semantic version in title/appbar.
4. Capture every production page at the target size and inspect against approved mockups.
5. Programmatically switch pages and exercise selection, wheel scrolling, follow state, and close while capturing callback exceptions.
6. Confirm zero visible `Scrollbar` widgets and no popup/Toplevel during normal operation.
7. Force one loader failure and verify last-good data becomes visibly stale/error and later recovers.
8. Run a bounded idle soak; unchanged polls must not rebuild continuously, leak workers, flash consoles, or grow memory materially.
9. Any source edit after launch invalidates the runtime evidence; restart and repeat.

## Required final verdict

Lead with one of:

- **RUNNING / TRUSTWORTHY** — canonical, shortcut, window, pages, data lineage, and soak all verified.
- **RUNNING / DEGRADED** — executable is live but named source or visual/interaction defects remain; enumerate them.
- **NOT YET RUNNING** — design/foundation/branch work exists, but canonical launcher proof is absent.

Then report `Did`, `Passed`, `Next`, and `Remaining`. Never say the redesigned VOT is operational while only the old shortcut or old v0.1.0 process is available.
