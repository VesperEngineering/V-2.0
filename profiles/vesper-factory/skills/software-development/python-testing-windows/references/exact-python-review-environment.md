# Exact Python review environment on Windows

Before dispatching an independent reviewer, bind the verification environment and commands into the task:

- exact repository/worktree and candidate or diff identity;
- exact project interpreter/virtualenv path;
- exact test targets;
- native external `TEMP`, `TMP`, `TMPDIR`, and `--basetemp` paths;
- exact lint/static commands, including selectors;
- read-only worktree rule and external scratch/log directory.

## Interpreter identity

Invoke the project interpreter directly, for example:

```bash
D:/repo/.venv/Scripts/python.exe -m pytest ...
```

A missing module under system Python does not prove the candidate failed. Re-run with the bound project interpreter before issuing a product verdict. If that exact interpreter is unavailable or fails, HOLD with the actual blocker; do not install dependencies during read-only review.

## Scratch source identity

When the user requires execution in unique external scratch, determine whether the tests themselves call Git. A `git archive` gives exact tracked bytes but no repository metadata; `git rev-parse HEAD` and related setup will fail with exit 128 even when the source is correct.

Use one of these source-preserving scratch forms:

1. an external detached clone at the exact commit; or
2. an external initialized repository whose object alternates point read-only at the source object store, followed by checkout of the exact SHA.

Before the gate, require external `HEAD == requested SHA`, external tree ID equals the requested tree, and clean external status. Keep `TEMP`/`TMP`/`TMPDIR`, basetemp, logs, caches, and bytecode external too. If an archive-only first attempt fails solely for missing Git metadata, record it as setup-only, create a new basetemp, and rerun from the exact detached scratch repository.

## Gate identity

Run the configured gate exactly. If acceptance requires critical Ruff only:

```bash
python -m ruff check --select E9,F63,F7,F82 <scoped paths>
```

Do not substitute unrestricted project-wide Ruff and then block on historical formatting/docstring debt. A broader scan can be reported separately as baseline information, but only the specified gate determines acceptance. Conversely, do not shrink a required full suite to focused tests.

For a known non-green broad baseline, report both:

1. focused acceptance result;
2. broad failure-count comparison.

Only new failures block unless the governing task explicitly requires a globally green suite.

## Review cleanliness

- Keep pytest scratch and logs outside the reviewed worktree.
- Use `-p no:cacheprovider` when cache files would dirty the tree.
- Do not write learnings, caches, or diagnostics into the reviewed worktree.
- Recheck candidate/diff identity immediately before the verdict; a changed diff makes the review stale.
- Preserve real process exit codes; avoid pipelines that can mask or alter them.
