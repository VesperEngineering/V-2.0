# VESPER 2.0

Market-hours trading system for US equities with a local Tkinter dashboard.

## Development setup

V20 is a Python 3.11 project managed by `uv`. `pyproject.toml` declares the
runtime dependencies, the `dev` dependency group contains development tools,
and `uv.lock` is the reproducible resolution. `requirements.txt` is only a
compatibility shim for pip-based runtime installs.

From PowerShell at the repository root:

```powershell
uv sync --locked --all-groups
```

The command creates or updates the repository-local `.venv`; it does not
install packages globally. Application credentials remain local in `.env` and
are not needed for setup or verification.

## Entry points

| Purpose | Command | Operational boundary |
| --- | --- | --- |
| Native platform CLI help | `uv run --locked vesper-agent --help` | Side-effect-free help; it does not open persistence, initialize a specialist, load credentials, or import trading/provider/UI runtime modules. |
| Paper launcher help | `uv run --locked python scripts/run_paper.py --help` | Safe inspection only; does not initialize Tk, load credentials, connect to a broker or data provider, or execute trading logic. |
| Paper trading | `uv run --locked python scripts/run_paper.py` | Operational command: loads credentials and starts the configured paper-trading engine. Do not use as a health check. |
| Dashboard | `uv run --locked python scripts/dashboard.py` | Opens the local Tk dashboard. It has no command-line help mode. |
| Backtest | `uv run --locked python scripts/run_backtest.py --help` | Shows the no-submit backtest interface. |
| Model training | `uv run --locked python scripts/train_model.py --help` | Shows the model-training interface; running it can write model artifacts. |
| Ranking diagnostic | `uv run --locked python scripts/ranking_diagnostic.py --help` | Shows the no-submit diagnostic interface. |
| Research evaluators | `uv run --locked python scripts/intermediate_momentum_research.py --help`, `uv run --locked python scripts/low_vol_research.py --help`, and `uv run --locked python scripts/spy_momentum_cpu_experiment.py --help` | Help is safe; substantive runs can read protected data and write evidence. |
| Universe builder | `uv run --locked python scripts/build_universe.py` | Operational command with network and configuration-write side effects; it has no help mode. |

The native platform command tree currently exposes `create`, `status`,
`resume`, `receipts`, `evidence`, `approvals`, `active`, `approve`, `reject`,
`cancel`, `knowledge-sync`, `knowledge-search`, and `knowledge-status`.
Approval, rejection, and cancellation require explicit arguments.
Only `create` and a resumed specialist turn may invoke an explicitly selected
model runtime; no command connects to a trading runtime. See
`docs/receipts/M1-M7-offline-slice-receipt.md` for the graph-backed command
boundary. Status, receipts, evidence, pending approvals, approval, rejection,
resume, and cancellation use local SQLite checkpoints and Store records.
Every run begins with controller-owned read-only Data Research and Model Evaluation
nodes. Data Research reports only bounded SP500 coverage aggregates, null counts,
date bounds, and split-adjustment identity from a read-only SQLite connection. Model
Evaluation reads only the configured model path, streams its hash, and validates the
companion metadata metrics without loading or executing the model. Both evidence
summaries are visible in `create` and `status`, are supplied to Product and Risk Review,
and are bound into the approval evidence set. Raw bars, model bytes, model parameters,
broker/risk settings, credentials, trading access, and model-promotion authority are
never exposed to specialists. Missing data, malformed coverage dates, a missing model,
invalid metadata, or an artifact hash mismatch stops before Product with
`operator-intervention`; it cannot reach acceptance.
The controller data root defaults to `vesper/data/massive` relative to the installed
Vesper package, not the operator's working directory or disposable specialist clone. Override it with global
`--research-data-root <path>` when using the canonical protected store; the resolved
read-only root persists with the run and must match on resume.
Runs checkpointed before these required stages must be recreated rather than resumed
through an approval that never reviewed research/model evidence.
`create` fails closed until an operator-approved specialist composition is
configured. `DockerCodexAdapter` is the first isolated runtime implementation. It
runs Codex in an already-provisioned Docker sandbox bound to an exact disposable
standalone clone and verifies OpenAI OAuth, disabled MCP, exact host mounts, no
published ports, and the effective network allowlist before every turn. Read-only
turns retain Codex's inner sandbox; workspace-write turns rely on the Docker
microVM because the nested Linux sandbox is incompatible with the Windows mount.
The adapter force-removes the one-shot sandbox after every outcome and fails
closed on Git control-plane mutation. Secure `--no-share-skills` provisioning and
Docker-managed OAuth have passed a real adapter canary. Every specialist turn
requires a fresh uniquely named sandbox; stopped VMs are never reused. The adapter
is not wired into `create` until one-shot provisioning exists and the specialist
composition is adapted and reviewed. OpenCode is an opt-in host subprocess route,
not an OS sandbox. Select it with global `--runtime opencode --model provider/model`
options before `create`; the selected runtime and model persist with the run. The
gateway scrubs the child environment, isolates global and project configuration, and
can pass only the selected provider's explicitly bound
`--credential-environment-key`. Product and Risk Review receive no tools. Development
receives only repository-relative, workspace-scoped read/edit/write;
shell, search, subagents, skills, web, and external paths remain denied. Providers
available in pure mode may use OpenCode's local authentication without an environment
binding. The plugin-backed OpenAI OAuth route remains excluded while default plugins
are disabled. Opt-in `local_opencode` coverage includes a complete controlled workflow
with `opencode/mimo-v2.5-free` that stopped at persisted human approval. Host turns
publish active child-process metadata outside the clone and cooperatively terminate on
an operator cancellation request.

## Agent knowledge

The repository-local [`knowledge/`](knowledge/README.md) directory is the
canonical Obsidian-compatible source for approved agent memories and procedures.
Obsidian is optional: the runtime reads ordinary Markdown directly. Approved
notes synchronize into LangGraph Store and a rebuildable local SQLite FTS5
index; every production run receives an immutable, bounded, role-scoped snapshot
before Product executes. Specialists cannot access the vault directly, and
retrieved knowledge is context rather than evidence or authority.

From the repository root:

```powershell
uv run --locked vesper-agent knowledge-sync
uv run --locked vesper-agent knowledge-status
uv run --locked vesper-agent knowledge-search --query "split adjustment" --role v20-development
```

See the [knowledge operator runbook](docs/runbooks/obsidian-knowledge.md) for
frontmatter, review, promotion, retrieval, and recovery rules. The default vault
is `knowledge/`; use global `--knowledge-root <path>` only for another approved
repository-local vault.

For a normal code task across an entire clone, the additional
`--allow-repository-root-workspace` flag is required. It is accepted only for OpenCode
in a clean standalone clone retaining origin provenance on an `m2/` branch. `.git`,
profiles, agent instructions, settings, model artifacts, environment files, controller
state, and protected data remain unreadable and unwritable to the specialist. Clones
containing submodules are rejected, OpenCode's patch tool is disabled, and cancelled,
timed-out, invalid, or crash-interrupted turns roll back partial workspace edits from a
controller-owned durable snapshot. Nested `.git`, `.state`, and environment files are
also denied. On Windows the child tree is assigned to a kill-on-close Job Object.

Example from the root of an approved disposable clone:

```powershell
$revision = git rev-parse HEAD
uv run --locked vesper-agent --runtime opencode --model opencode/mimo-v2.5-free `
  --allow-repository-root-workspace create `
  --objective "Implement the bounded code change." `
  --workspace . `
  --repository-revision $revision `
  --acceptance-check git-diff-check
```

## Verification

Use a native Windows temporary directory for pytest because repository-local
temporary directories have previously encountered ACL and cleanup races:

```powershell
$testRoot = Join-Path $env:LOCALAPPDATA "Temp\v20-pytest-$PID"
New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
uv run --locked python -m pytest tests -q --basetemp (Join-Path $testRoot "pytest")
```

The test scope is intentionally `tests`; running bare `pytest` can collect
historical or vendored test trees that are not part of V20's suite.

Run the repository-wide fatal-error lint gate:

```powershell
uv run --locked ruff check vesper scripts tests
```

Format only files in the change being prepared, then check the same paths. The
historical tree is not yet globally Ruff-formatted, so a repository-wide format
rewrite is intentionally outside M0.

```powershell
uv run --locked ruff format <changed-python-paths>
uv run --locked ruff format --check <changed-python-paths>
```

Compile first-party Python without writing bytecode into the repository:

```powershell
$compileRoot = Join-Path $env:LOCALAPPDATA "Temp\v20-compile-$PID"
$env:PYTHONPYCACHEPREFIX = Join-Path $compileRoot "pycache"
uv run --locked python -m compileall -q vesper scripts tests
```

Verify every first-party package and script import in an isolated subprocess:

```powershell
$importRoot = Join-Path $env:LOCALAPPDATA "Temp\v20-imports-$PID"
New-Item -ItemType Directory -Force -Path $importRoot | Out-Null
uv run --locked python -m pytest tests/test_imports.py -q --basetemp (Join-Path $importRoot "pytest")
```

Before handing off a change, also run:

```powershell
uv lock --check
git diff --check
```
