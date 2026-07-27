# Goal-loop review recipe

Use this recipe after a Vesper goal worker reports `blocked`/`needs_input` for implementation review.

## 1. Confirm provenance and state

```bash
hermes kanban --board vesper show <TASK_ID>
hermes kanban --board vesper stats
```

Read the card comments before acting. The useful review inputs are the worker worktree, the claimed changed files, the focused test command, the fixture/real-provider distinction, and the exact blocker.

## 2. Inspect the isolated worktree

```bash
git -C <WORKTREE> status --short
git -C <WORKTREE> branch --show-current
git -C <WORKTREE> diff --stat
```

Untracked implementation files do not appear in `git diff`; read them directly and stage only the intended source/tests/docs. Leave runtime ledgers, basetemp directories, fixture output, and unrelated files unstaged.

## 3. Verify twice

First run the focused tests in the worker worktree, then rerun them after promotion in the canonical checkout:

```bash
<PROJECT_PYTHON> -m py_compile <CHANGED_PY>...
<PROJECT_PYTHON> -m pytest <FOCUSED_TESTS> -q --tb=short --basetemp=<TEMP_DIR>
```

Exercise a hermetic fixture path if available. Separately invoke the no-transport path and record its fail-closed blocker; never call fixture evidence a real provider canary.

## 4. Promote exactly one reviewed change

```bash
git -C <WORKTREE> add -- <INTENDED_FILES>
git -C <WORKTREE> diff --cached --check
git -C <WORKTREE> commit -m "<scoped message>"
git -C <CANONICAL> cherry-pick <COMMIT>
```

Check the canonical diff and rerun the focused tests from `<CANONICAL>` after the cherry-pick. Push only the canonical branch if repository policy requires it; do not push from the worker worktree.

## 5. Record and close

```bash
hermes kanban --board vesper comment <TASK_ID> \
  "Independent review PASS: <commit>; <tests>; fixture/real distinction; denied authority." \
  --author hermes-review
hermes kanban --board vesper complete <TASK_ID> \
  --result "<short result>" \
  --summary "<handoff>" \
  --metadata '{"verification":"PASS","real_provider_canary":"BLOCKED_SEPARATELY"}'
```

A following roadmap card may be created only after `show <TASK_ID>` reports `done`. Keep provider, broker/order, risk, promotion, scheduler, and secret actions separately authorized.
