# Adaptive Knowledge Core Verification Receipt

- Recorded: 2026-07-29
- Environment: Windows, Python 3.11, `uv run --locked`
- Baseline: `62df959795691b894e3b3ed8d5dc5403bb2c50b0`
- Verified implementation head: `188d361fce6b250830368292d571e1e3049e401e`
- Result: all focused, static, full-suite, import, lock, CLI, and diff gates passed

## Implementation commits

- Task 1: `296a708b6e9236af25c694933624fbe8a4aaa900`,
  `e327886c92cd3112d7a9c02d39eb4046578232a1`
- Task 2: `fd99254a9bbcb3f88b57ff9cf6c6ebf0b68f0a5b`
- Task 3: `4932e162b3e9b7bb336cd0d3afaf0973135fdbbc`
- Task 4: `235888d6ae66b54688bee832881b9b818f0562bb`,
  `6f6982f3d42b3e35385294964e86572ee0361a38`,
  `2ff436eb16d346f401e5b9824d44ade46b2805fc`
- Task 5: `befea20e540e74b666731e94d74f50c27944a73f`,
  `5c8471da2a26f57bdcf0c98b9d0b5f2cdd8fd64d`
- Task 6: `5831e801898b14e5b4252bb0cb838bde390ca67b`,
  `365933e4a4deec23da8dcfa1c38a87e8d47fd289`
- Task 7: `7cc80e40b7a9655973abf92e7caf78e7df828f51`
- Task 8: `9ab7b68b894b5d546669ab36a63ff1322b174b53`,
  `10782ad0fe24b0c110ebd5c757cf10d3f23f1ef7`,
  `48947d9ddc74bc4bf2eb19ca36fa0a0b1f0a8191`
- Task 9 required formatting: `188d361fce6b250830368292d571e1e3049e401e`

## Fresh verification

### Focused adaptive suite

```powershell
$adaptiveTestRoot = Join-Path $env:LOCALAPPDATA "Temp\v20-adaptive-knowledge-$PID"
New-Item -ItemType Directory -Force -Path $adaptiveTestRoot | Out-Null
uv run --locked python -m pytest `
  tests/platform/test_contracts.py `
  tests/platform/test_knowledge.py `
  tests/platform/test_knowledge_lifecycle.py `
  tests/platform/test_composition.py `
  tests/platform/test_workflow.py `
  tests/platform/test_service.py `
  tests/platform/test_cli.py `
  -q --basetemp (Join-Path $adaptiveTestRoot "focused")
```

Result: exit 0; `238 passed, 1 skipped in 30.44s`.

After the required locked formatter changed two files mechanically, the directly
affected contract suite was rerun:

```powershell
$adaptiveStyleTestRoot = Join-Path $env:LOCALAPPDATA "Temp\v20-adaptive-style-$PID"
New-Item -ItemType Directory -Force -Path $adaptiveStyleTestRoot | Out-Null
uv run --locked python -m pytest tests/platform/test_contracts.py -q `
  --basetemp (Join-Path $adaptiveStyleTestRoot "pytest")
```

Result: exit 0; `31 passed in 0.13s`.

### Formatting, lint, and compilation

The required formatter command exited 0:

```powershell
uv run --locked ruff format `
  vesper/platform/contracts.py `
  vesper/platform/knowledge.py `
  vesper/platform/knowledge_lifecycle.py `
  vesper/platform/composition.py `
  vesper/platform/workflow.py `
  vesper/platform/service.py `
  vesper/platform/cli.py `
  tests/platform/test_contracts.py `
  tests/platform/test_knowledge.py `
  tests/platform/test_knowledge_lifecycle.py `
  tests/platform/test_composition.py `
  tests/platform/test_workflow.py `
  tests/platform/test_service.py `
  tests/platform/test_cli.py
```

Its output was:

```text
2 files reformatted, 12 files left unchanged
```

The resulting commit changes only line wrapping in
`vesper/platform/contracts.py` and `tests/platform/test_contracts.py`.

```powershell
uv run --locked ruff format --check `
  vesper/platform/contracts.py `
  vesper/platform/knowledge.py `
  vesper/platform/knowledge_lifecycle.py `
  vesper/platform/composition.py `
  vesper/platform/workflow.py `
  vesper/platform/service.py `
  vesper/platform/cli.py `
  tests/platform/test_contracts.py `
  tests/platform/test_knowledge.py `
  tests/platform/test_knowledge_lifecycle.py `
  tests/platform/test_composition.py `
  tests/platform/test_workflow.py `
  tests/platform/test_service.py `
  tests/platform/test_cli.py
uv run --locked ruff check vesper scripts tests
$adaptiveCompileRoot = Join-Path $env:LOCALAPPDATA "Temp\v20-adaptive-compile-$PID"
$env:PYTHONPYCACHEPREFIX = Join-Path $adaptiveCompileRoot "pycache"
uv run --locked python -m compileall -q vesper scripts tests
```

Results:

```text
14 files already formatted
All checks passed!
compileall: exit 0; no output
```

### Full project and import suites

```powershell
$adaptiveFullRoot = Join-Path $env:LOCALAPPDATA "Temp\v20-adaptive-full-$PID"
New-Item -ItemType Directory -Force -Path $adaptiveFullRoot | Out-Null
uv run --locked python -m pytest tests -q `
  --basetemp (Join-Path $adaptiveFullRoot "pytest")
```

Result: exit 0; `734 passed, 5 skipped in 84.64s`.

```powershell
$adaptiveImportRoot = Join-Path $env:LOCALAPPDATA "Temp\v20-adaptive-imports-$PID"
New-Item -ItemType Directory -Force -Path $adaptiveImportRoot | Out-Null
uv run --locked python -m pytest tests/test_imports.py -q `
  --basetemp (Join-Path $adaptiveImportRoot "pytest")
```

Result: exit 0; `66 passed in 27.12s`.

This isolated worktree intentionally has neither `vesper/data/massive/` nor
`vesper/data/model_research/`. The SDD ledger records the earlier baseline as
`659 passed, 5 skipped` in the data-bearing checkout and `654 passed, 5 skipped`
plus five research-readiness failures in the isolated worktree. No exception is
needed for this final run because the current full suite completed with zero
failures.

### Lock, CLI, smoke, and diff gates

```powershell
uv lock --check
uv run --locked vesper-agent --help
uv run --locked vesper-agent knowledge-status
git diff --check
git status --short
```

Results:

```text
uv lock --check: exit 0; Resolved 79 packages in 0.95ms
vesper-agent --help: exit 0; all three governed lifecycle commands listed
git diff --check: exit 0; no output
git status --short: exit 0; no output before receipt creation
```

The help smoke listed `knowledge-observe`, `knowledge-compaction-plan`, and
`knowledge-reactivation-plan`. The status smoke exited 0 with:

```text
documents: 0
active: 0
archived: 0
memory: 0
skill: 0
active_lines: 0
active_line_limit: 3000
```

## Scope and authority boundary

The baseline-to-verified-head range contains 28 tracked files with `3,024`
insertions and `88` deletions. It is limited to the adaptive knowledge contracts,
corpus and retrieval, lifecycle service, composition/workflow/service wiring,
governed CLI, focused tests, vault templates and guidance, ADR/runbook, and the
required mechanical formatting.

No protected data, `config/settings.yaml` risk or trading setting, model
artifact, script or scheduler configuration, credential, dependency, external
service, order path, capital allocation, or live deployment changed. No file
under `vesper/data/massive/` or `vesper/data/model_research/` was created,
copied, linked, read for ingestion, or modified during Task 9.

## Non-goals and deferred items

- Embeddings and vector retrieval remain deferred; retrieval is local lexical
  FTS5.
- Automatic archival, reactivation, deletion, approval, and note movement remain
  deferred and operator-controlled.
- Scheduling and scheduler changes remain deferred.
- External or hosted memory services remain deferred.
- Model training or promotion, paid data or compute, broker access, order
  execution, risk changes, and trading-parameter changes remain outside scope.
