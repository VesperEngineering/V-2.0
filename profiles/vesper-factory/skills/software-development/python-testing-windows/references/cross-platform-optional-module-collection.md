# Cross-platform optional-module collection failures

Use this recipe when native Windows pytest fails during collection because a Unix-only optional stdlib module such as `_curses` is imported by an unrelated TUI test/module.

## Classify before editing code

1. Read the import traceback and identify the first project module that imports the unavailable optional module.
2. Check the project's declared canonical runtime. If the full application/test contract is WSL/Linux and the changed slice is platform-neutral, a native Windows `_curses` collection error is an interpreter-selection failure, not evidence that the changed code is broken.
3. Do not add fake modules, broad skips, or conditional production imports merely to make the wrong interpreter collect. If native Windows support for that TUI is itself required, treat it as a separate product portability task.
4. Preserve the failed setup attempt in reporting; do not present it as a behavioral test failure.

## Two-layer verification

### Native Windows changed scope

Run the changed platform-neutral test modules under Windows with:

- an external native `TEMP`/`TMP`/`TMPDIR` on the repository drive and outside the repository;
- `-p no:cacheprovider`;
- an explicit `--basetemp`;
- the project's installed package or, for a `src/` layout without a Windows installation, `PYTHONPATH=src`.

A missing `PYTHONPATH=src` that produces `ModuleNotFoundError: <project_package>` is a setup-only failure. Correct the import root and rerun from a fresh temp root; do not patch project imports.

### Complete canonical suite

Run the full suite in the declared project environment (for example its WSL virtualenv), again with an external basetemp. A complete WSL/Linux pass is admissible for a project whose documented full-suite runtime is WSL/Linux. It does not prove native Windows support for the Unix-only TUI.

Report both layers separately:

- native changed scope: exact targets and count;
- canonical full suite: exact count and platform-specific skips;
- native full-suite setup error: `_curses` unavailable, if it occurred;
- whether native full-suite support was or was not part of the acceptance contract.

## Cleanup timing

Windows pytest temp roots can remain undeletable for a short interval even after the pytest summary is printed. Preserve the pytest exit status, then retry cleanup in a fresh post-pytest process after the command has fully returned. Verify `not path.exists()` before closing the gate. A delayed successful cleanup is the reusable lesson; do not encode the transient lock as a permanent tool limitation.

## Fail-closed boundary

If the review contract explicitly requires a green native Windows full suite, a WSL pass cannot replace it. Keep the gate on HOLD until native collection is made valid through an approved portability change or the contract is revised by the user. If the canonical full-suite environment is WSL and native testing is supplemental, report the native limitation and use the green WSL suite as the complete behavioral verdict.
