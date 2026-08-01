# V20 TUI Framework Bakeoff Design

Status: approved design sections, pending written-spec review
Date: 2026-08-01
Scope: `C:\Users\bgonn\Desktop\v20\TUI testing`

## Goal

Build production-like, feature-matched operator consoles in Python/Textual and
Rust/Ratatui. Both consoles read the same live V20 state through the existing
machine-readable CLI. The bakeoff will select a framework using reproducible
functional, performance, customization, testing, and packaging evidence.

## Constraints

- Read-only. Neither console may create, resume, approve, reject, cancel, or
  otherwise mutate a V20 run.
- V20 core code and configuration remain unchanged.
- All bakeoff source, fixtures, environments, build outputs, scripts, and
  results remain below `TUI testing`.
- No broker, provider, account, credential, order, position, risk, scheduler,
  training, promotion, protected-data write, or external-service access.
- Missing or malformed state must fail visibly; it must never be presented as
  healthy.
- Both implementations use identical labels, keys, colors, layouts, commands,
  normalized models, fixtures, benchmark loads, and acceptance checks.

## Verified Environment

- Windows, PowerShell
- Python 3.11.15
- uv 0.11.32
- rustc 1.97.0
- cargo 1.97.0
- Live `active` response: `{ "active": [] }`
- Live `approvals` response: `{ "pending": [] }`
- Live `knowledge-status` response: four skill documents and zero memory
  documents

These live values are observations, not fixtures or expected future values.

## Directory Layout

```text
TUI testing/
|-- DESIGN.md
|-- README.md
|-- .gitignore
|-- shared/
|   |-- contract.md
|   |-- benchmark-spec.json
|   `-- fixtures/
|-- python-textual/
|   |-- pyproject.toml
|   |-- src/v20_tui_textual/
|   `-- tests/
|-- rust-ratatui/
|   |-- Cargo.toml
|   |-- src/
|   `-- tests/
|-- scripts/
`-- results/
```

The implementation plan will name exact files. Generated environments,
caches, Rust targets, and transient results will be ignored locally.

## Architecture

```text
Python/Textual --+
                 +--> identical read-only CLI adapter
Rust/Ratatui ----+              |
                                +--> active
                                +--> approvals
                                +--> knowledge-status
                                +--> status <run-id>
                                +--> receipts <run-id>
                                `--> evidence <run-id>
                                           |
                           uv run --locked vesper-agent --json
                                           |
                                LocalPlatformService
```

Both adapters execute argument arrays with the V20 repository as the working
directory. They do not invoke a shell. The adapter command is selected only
from a fixed enum/allowlist; free text may fill only the validated `run-id`
argument.

### Allowed commands

- `active`
- `approvals`
- `knowledge-status`
- `status <run-id>`
- `receipts <run-id>`
- `evidence <run-id>`

No other command is representable by the adapter API.

## Shared Data Contract

Each implementation converts CLI JSON into equivalent typed view models:

- `OverviewSnapshot`: active count, pending count, knowledge counts, command
  health, fetch time, refresh timestamp, and freshness state.
- `ActiveRunSummary`: run identifier, status, runtime metadata, and available
  recovery metadata.
- `ApprovalSummary`: run, task, request, checkpoint, repository revision,
  workspace hash, evidence references, and creation time when supplied.
- `RunDetail`: normalized status payload plus receipt and evidence collections.
- `CommandResult`: success payload or typed timeout, exit, decoding, schema, or
  unavailable failure.

The shared contract documents optional fields explicitly. Unknown fields are
preserved for the raw JSON detail view but do not silently become typed state.

## Refresh and Failure Semantics

- Automatic refresh interval: five seconds.
- Manual refresh: `r`.
- Pause/resume automatic refresh: `space`.
- One refresh may run at a time; a second request is coalesced.
- Per-command timeout: five seconds.
- First-load failure displays `UNAVAILABLE`.
- A later failure retains the last valid snapshot and marks it `STALE` with its
  age and failure category.
- A successful refresh replaces the snapshot atomically.
- The UI shows bounded, sanitized error summaries. It does not display raw
  environment data or credential-shaped values.
- Shutdown cancels refresh work and terminates any owned CLI child process.

`STALE` means the screen is showing the last known valid result, not current
state. This matters because an operator must not mistake old approval or run
information for live truth.

## Matched User Interface

```text
+ V20 Operator Console -- LIVE / READ-ONLY -- Last refresh --------+
| Active Runs | Pending Approvals | Knowledge | CLI Health         |
+ Navigation ------------------------------------------------------+
| [1 Overview] [2 Runs] [3 Approvals]                              |
+ Main table -----------------------+ Detail panel ----------------+
| sortable and filterable rows      | state / receipts / evidence |
|                                   | raw JSON / errors            |
+-----------------------------------+------------------------------+
| r refresh | space pause | / filter | t theme | ? help | q quit  |
+------------------------------------------------------------------+
```

### Screens

1. **Overview**
   - Active, pending, knowledge, and CLI-health summary cards.
   - Command duration and refresh-latency sparklines.
   - Compact active-run and pending-approval previews.
2. **Runs**
   - Sortable and filterable active-run table.
   - Run-ID input for direct lookup.
   - State, receipts, evidence, and raw JSON detail tabs.
3. **Approvals**
   - Sortable and filterable pending-approval table.
   - Read-only authority, checkpoint, revision, workspace-hash, and evidence
     details.

### Shared interaction contract

- `1`, `2`, `3`: switch screen
- `r`: refresh
- `space`: pause/resume automatic refresh
- `/`: focus filter
- `t`: switch dark/light theme
- `?`: help
- `q`: quit
- Keyboard and mouse navigation
- Responsive narrow and wide layouts
- Explicit loading, empty, fresh, stale, and unavailable presentations

No write button, key binding, command-palette entry, or hidden action exists.

## Implementation Boundaries

Each version has the same conceptual modules:

- typed domain/view models;
- read-only CLI adapter;
- refresh coordinator;
- screens and reusable widgets;
- dark/light theme definitions;
- deterministic benchmark entrypoint;
- contract, interaction, snapshot, lifecycle, and live smoke tests.

Framework-specific code stays behind these boundaries. No general plugin system
will be built. New screens and widgets will use a small internal registry only
where the matched implementation requires it.

## Testing

Both implementations must provide equivalent evidence for:

- valid shared fixtures;
- empty live results;
- timeout, nonzero exit, invalid JSON, missing-field, and unknown-field cases;
- first-load unavailable and later stale behavior;
- refresh coalescing;
- run-ID validation;
- screen navigation, filtering, tabs, help, and theme switching;
- narrow and wide layouts;
- mutation-command exclusion;
- clean shutdown with no surviving owned child process;
- live read-only smoke calls to `active`, `approvals`, and `knowledge-status`.

Textual tests use headless `Pilot` and snapshot support. Ratatui tests use its
test backend and buffer snapshots. Tests must assert behavior, not only captured
appearance.

## Benchmark Method

Deterministic shared fixtures provide 100, 1,000, and 10,000 rows. Both
implementations run the same warmup count, iteration count, terminal sizes, and
refresh schedules. Results are emitted as JSON under `results/`.

Measurements:

- cold process startup and first completed frame;
- CLI-fetch latency, reported separately from framework performance;
- JSON decode and view-model construction latency;
- model-update and render median/p95 latency;
- filter and navigation median/p95 latency;
- production load at two updates per second;
- stress load at five updates per second;
- peak working-set memory and CPU usage;
- build/install time and test time;
- isolated Python environment size and Rust release executable size;
- source lines, direct dependency count, and evidence-backed customization
  effort.

The PowerShell runner records environment versions, command lines, iterations,
and timestamps. It does not compare Rust build-directory size with Python
runtime size; only deployable artifacts are compared.

## Mandatory Gate

A candidate is ineligible if any of these fail:

- matched functional scope;
- safe unavailable/stale behavior;
- Windows execution;
- automated contract and UI tests;
- live read-only smoke test;
- no V20 writes or mutation commands;
- clean child-process shutdown;
- responsive input at the two-updates-per-second production load.

## Decision Rubric

Candidates passing the mandatory gate receive a documented 1-5 score in each
category:

| Category | Weight | Required evidence |
| --- | ---: | --- |
| Integration and maintainability | 25% | boundaries, duplication, dependencies, change surface |
| Customization and growth | 25% | matched theme/layout/widget extension tasks |
| Responsiveness and resources | 25% | startup, p95 latency, CPU, memory, artifact size |
| Testability | 15% | interaction, snapshot, failure, and lifecycle coverage |
| Packaging and deployment | 10% | reproducible build, install time, deployable output |

Every score must cite raw measurements or inspectable implementation evidence.
The weighted score cannot override a mandatory-gate failure or conceal a
material weakness. The final report may recommend one framework, recommend a
conditional fallback, or conclude that more experimentation is required.

## Acceptance Criteria

- The two applications implement the matched scope and shared contract.
- Both run against live V20 read-only CLI output from the repository root.
- Shared fixtures and benchmark settings are byte-identical inputs.
- Focused tests and live smoke checks pass with fresh output.
- Benchmark JSON is reproducible and records provenance.
- A comparison report presents raw data, gate results, rubric scores,
  limitations, and the recommended framework.
- No file outside `TUI testing` changes during implementation.

## Explicit Non-Goals

- Trading, broker, provider, account, order, position, or risk controls
- Model training or promotion
- Run creation, approval, rejection, cancellation, or resume
- Scheduler or deployment controls
- Replacing the V20 CLI or `LocalPlatformService`
- A network API, remote dashboard, Jira integration, or third-party plugins
- Selecting a framework before measured results exist
