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
`resume`, `receipts`, `evidence`, `approvals`, `approve`, `reject`, and
`cancel`. Approval, rejection, and cancellation require explicit arguments;
no command connects to a provider or trading runtime. See
`docs/receipts/M1-M7-offline-slice-receipt.md` for the graph-backed command
boundary. Status, receipts, evidence, pending approvals, approval, rejection,
resume, and cancellation use local SQLite checkpoints and Store records.
`create` fails closed until an operator-approved specialist composition is
configured; deterministic specialist fakes are used only by tests.

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
