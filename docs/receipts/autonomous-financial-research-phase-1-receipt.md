# Autonomous Financial Research Phase 1 Verification Receipt

- Recorded: 2026-07-29
- Environment: Windows, Python 3.11, `uv run --locked`
- Phase 1 implementation head: `d3572370812b9924bcc681f37657cdbd75cb7fe4`
- Final verification pre-receipt tree: `9cf96f8` (`docs(research): clarify
  replay failure semantics`)
- Result: behavioral, lint, compile, lock, CLI, documentation, and diff checks
  passed; the required repository-wide Ruff format check remains open: `40
  files would be reformatted, 67 files already formatted`.

## Implemented boundary

The verified slice admits `direct-request` and `weak-model-result`, validates a
static typed two-node coverage plan, reads Massive SQLite read-only, and writes
immutable controller-owned derived JSON, validation evidence, and terminal
state. The operator surface is limited to `financial-research-start` and
`financial-research-status`.

It provides no orders, promotion, training, web retrieval, scheduler
activation, automatic two-week schedule, or automatic August 12 action. August
12, 2026 remains a human review gate.

## CLI help

```powershell
uv run --locked vesper-agent --help
uv run --locked vesper-agent financial-research-start --help
uv run --locked vesper-agent financial-research-status --help
```

Result: all three exited 0. Top-level help listed both Phase 1 commands. Start
help listed required `--event-type`, `--objective`, `--symbol`, `--start-date`,
and `--end-date`, plus optional `--observed-metric` and `--threshold`. Status
help showed positional `{run_id}`.

## Focused tests

The exact planned command was run first:

```powershell
uv run --locked python -m pytest tests/platform/test_financial_research.py tests/platform/test_financial_workflow.py tests/platform/test_contracts.py tests/platform/test_service.py tests/platform/test_cli.py -q
```

Result: exit 1; `88 passed, 124 errors in 29.99s`. Every error occurred during
pytest `tmp_path` setup while enumerating the host default temporary directory;
no test assertion failed.

The same pytest command was then rerun with `TEMP` and `TMP` set to a fresh,
task-owned directory below `C:\tmp`.

Result: exit 0; `212 passed in 25.61s`.

## Full suite

The planned command was run with `TEMP` and `TMP` set to a fresh, task-owned
directory below `C:\tmp`:

```powershell
uv run --locked python -m pytest tests -q
```

Result: exit 0; `865 passed, 5 skipped in 98.24s`.

## Formatting

```powershell
uv run --locked ruff format --check vesper tests
```

Result: exit 1; `42 files would be reformatted, 65 files already formatted`.
Task 6 changes no Python. The failures are pre-existing and include historical
files outside this phase. They were not bulk-formatted because that would exceed
the Task 6 documentation-only scope.

## Final bounded format repair

The final bounded repair formatted only the two Phase 1 Python files:

```powershell
uv run --locked ruff format vesper/platform/financial_research.py tests/platform/test_financial_research.py
```

Result: exit 0; `2 files reformatted`. Review of Ruff's generated diff
confirmed line-wrapping and whitespace changes only; no production or test
semantics changed.

The focused final verification command used a fresh task-owned `C:\tmp`
directory for `TEMP` and `TMP`, preserving the historical host-default temp ACL
failure above:

```powershell
uv run --locked python -m pytest tests/platform/test_financial_research.py tests/platform/test_financial_workflow.py tests/platform/test_contracts.py -q
```

Result: exit 0; `117 passed in 10.99s`.

```powershell
uv run --locked ruff check vesper/platform/financial_research.py tests/platform/test_financial_research.py
uv run --locked ruff format --check vesper/platform/financial_research.py tests/platform/test_financial_research.py
uv run --locked python -m py_compile vesper/platform/financial_research.py tests/platform/test_financial_research.py
git diff --check
```

Results: Ruff lint exit 0 (`All checks passed!`); the two files are already
formatted; `py_compile` exit 0 with no output; and `git diff --check` exit 0
with no whitespace errors.

The branch-changed Python set was then checked against baseline `6215a50`:

```powershell
$pythonFiles = @(git diff --name-only 6215a50 -- '*.py')
uv run --locked ruff format --check @pythonFiles
```

Result: exit 0; `10 files already formatted`.

The repository-wide check was rerun without formatting any other file:

```powershell
uv run --locked ruff format --check vesper tests
```

Result: exit 1; `40 files would be reformatted, 67 files already formatted`.

## Lint, compilation, and lock

```powershell
uv run --locked ruff check vesper scripts tests
uv run --locked python -m compileall -q vesper scripts tests
uv lock --check
```

Results:

- Ruff lint: exit 0; `All checks passed!`
- Compileall: exit 0; no output. `PYTHONPYCACHEPREFIX` pointed to a fresh
  task-owned directory below `C:\tmp`.
- Lock: exit 0; `Resolved 79 packages in 1ms`.

## Documentation and Git checks

A targeted read-only check confirmed that all referenced local documents exist,
the runbook contains both commands, both event types, and every required
authority exclusion, and the knowledge note still declares
`vesper_status: candidate`.

```powershell
git diff --check
git status --short
```

Result after receipt creation: `git diff --check` exited 0 with no whitespace
errors. Status contained exactly the five expected Task 6 paths: `README.md`,
the candidate knowledge note, ADR-0004, the runbook, and this receipt.

## Remaining concern

The repository-wide formatter gate is not green: `40 files would be
reformatted, 67 files already formatted`. No production assertion, focused
Ruff-lint, focused compilation, lock, CLI-help, documentation-content, link, or
whitespace defect remains. The remaining format baseline should be resolved in
a separate authorized code/test formatting task rather than folded into this
bounded repair.
