# V20 TUI Bakeoff Design

Status: approved
Date: 2026-08-01
Folder: `C:\Users\bgonn\Desktop\v20\TUI testing`

## Goal

Build two matching terminal dashboards:

- Python with Textual
- Rust with Ratatui

Both apps will show the same live, read-only V20 data. They will also use the
same fake data for repeatable speed tests. We will compare the results and pick
the better framework.

## Safety Rules

- Put all new files inside `TUI testing`.
- Do not change V20 code or settings.
- Read V20 data only through the existing JSON command line.
- Do not add any action that changes a run.
- Do not access brokers, accounts, credentials, orders, positions, risk
  settings, schedulers, training, model promotion, or paid services.
- Never write to protected V20 data folders.
- Show missing, old, or broken data clearly. Never make it look healthy.
- Give both apps the same features, labels, keys, colors, data, and tests.

## Verified Tools

- Windows and PowerShell
- Python 3.11.15
- uv 0.11.32
- rustc 1.97.0
- cargo 1.97.0

The live checks returned:

- no active runs;
- no pending approvals;
- four skill documents and no memory documents.

These values can change. They are not test fixtures.

## Planned Files

```text
TUI testing/
|-- DESIGN.md
|-- IMPLEMENTATION_PLAN.md
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

Generated files, caches, Python environments, Rust build files, and temporary
results will be ignored.

## Data Flow

```text
Textual app ----+
                +--> fixed read-only adapter --> V20 JSON command line
Ratatui app ----+
```

Both adapters will run the same command from the V20 root:

```text
uv run --locked vesper-agent --json <allowed-command>
```

They will pass arguments directly. They will not use a shell.

Only these commands are allowed:

- `active`
- `approvals`
- `knowledge-status`
- `status <run-id>`
- `receipts <run-id>`
- `evidence <run-id>`

The adapter will use a fixed command list. Free text is allowed only for a
checked run ID. No other V20 command can be called.

## Shared Data Shape

Each app will turn the JSON into the same typed records:

- `OverviewSnapshot`: counts, command health, timing, and data age.
- `ActiveRunSummary`: run ID, state, and available recovery details.
- `ApprovalSummary`: run, task, request, checkpoint, revision, workspace hash,
  evidence, and creation time when available.
- `RunDetail`: state, receipts, evidence, and raw JSON.
- `CommandResult`: valid data or a clear timeout, exit, JSON, schema, or
  unavailable error.

Optional fields will be listed in the shared contract. Unknown fields will
remain visible in raw JSON, but they will not silently become trusted fields.

## Refresh and Error Rules

- Refresh live data every five seconds.
- Let the user refresh with `r`.
- Let the user pause or restart automatic refresh with `space`.
- Never run two refreshes at once. If more requests arrive, keep only one
  request to run next.
- Stop each command after five seconds.
- On the first failed load, show `UNAVAILABLE`.
- After a later failure, keep the last good data and show `STALE`, its age, and
  the error type.
- Build each new view fully before replacing the old view.
- Show short, safe error messages. Do not show environment values or anything
  that looks like a credential.
- On exit, stop refresh work and every command process started by the app.

`STALE` means the screen shows old data, not the current V20 state. This stops
an operator from treating an old run or approval as current.

## Matching Screens

```text
+ V20 Console -- LIVE / READ-ONLY -- Last refresh -----------------+
| Active Runs | Pending Approvals | Knowledge | Command Health     |
+------------------------------------------------------------------+
| [1 Overview] [2 Runs] [3 Approvals]                              |
+ Main table -----------------------+ Details ----------------------+
| rows, sort, and filter            | state, receipts, evidence    |
|                                   | raw JSON or errors           |
+------------------------------------------------------------------+
| r refresh | space pause | / filter | t theme | ? help | q quit  |
+------------------------------------------------------------------+
```

### Overview

- Summary cards for active runs, approvals, knowledge, and command health.
- Small charts for command time and refresh delay.
- Short lists of active runs and pending approvals.

### Runs

- A sortable and filterable active-run table.
- A run-ID box for direct lookup.
- Detail tabs for state, receipts, evidence, and raw JSON.

### Approvals

- A sortable and filterable pending-approval table.
- Read-only details for authority, checkpoint, revision, workspace hash, and
  evidence.

### Shared keys and behavior

- `1`, `2`, `3`: change screen
- `r`: refresh
- `space`: pause or restart automatic refresh
- `/`: focus the filter
- `t`: switch dark and light themes
- `?`: open help
- `q`: quit
- keyboard and mouse support
- layouts for narrow and wide terminals
- clear loading, empty, fresh, stale, and unavailable states

There will be no write button, write key, write menu item, or hidden write
action.

## Code Parts

Each app will have the same main parts:

- typed data records;
- read-only V20 command adapter;
- refresh controller;
- screens and reusable widgets;
- dark and light themes;
- repeatable benchmark command;
- contract, screen, snapshot, shutdown, and live smoke tests.

Framework-specific code will stay inside these parts. We will not build a
general plugin system. A small internal list of screens or widgets is enough.

## Tests

Both apps must test the same behavior:

- valid shared fixtures;
- empty live results;
- timeouts, failed commands, bad JSON, missing fields, and unknown fields;
- first-load unavailable and later stale states;
- refresh requests do not overlap;
- run-ID checks;
- navigation, filters, tabs, help, and theme changes;
- narrow and wide layouts;
- no write commands;
- clean exit with no command process left running;
- live read-only checks for `active`, `approvals`, and `knowledge-status`.

Textual will use its headless Pilot test tools and snapshots. Ratatui will use
its test screen and buffer snapshots. Tests will check behavior as well as
appearance.

## Speed Tests

Shared fixtures will contain 100, 1,000, and 10,000 rows. Both apps will use the
same warmups, test runs, terminal sizes, and update schedules. The runner will
save JSON results under `results`.

We will measure:

- process start and first complete screen;
- V20 command time, kept separate from framework speed;
- JSON reading and typed-record creation;
- screen update and draw time, including median and 95th percentile;
- filter and navigation time;
- two screen updates per second as the normal benchmark;
- five screen updates per second as the stress benchmark;
- peak memory and CPU use;
- build, install, and test time;
- installed Python app size and Rust release app size;
- source line count, direct dependency count, and effort for the same UI change.

The live refresh still runs every five seconds. The faster update rates apply
only to repeatable screen-load tests.

The PowerShell runner will record tool versions, commands, run counts, and
times. It will compare deployable app sizes, not Rust build files against a
Python runtime.

## Required Passes

A framework cannot win unless it passes all of these checks:

- all matching features work;
- old or missing data is shown safely;
- it runs on Windows;
- contract and screen tests pass;
- live read-only smoke tests pass;
- it has no write command or write action;
- it exits without leaving a command process;
- input stays responsive during the normal benchmark.

## Score

Frameworks that pass every required check get a score from 1 to 5 in each area:

| Area | Weight | Evidence |
| --- | ---: | --- |
| Easy V20 integration and upkeep | 25% | code boundaries, repeated code, dependencies, change size |
| UI changes and future growth | 25% | same theme, layout, and widget changes |
| Speed and computer use | 25% | start time, delay, CPU, memory, app size |
| Easy testing | 15% | screen, snapshot, error, and shutdown tests |
| Easy install and release | 10% | repeatable build, install time, released files |

Every score must point to raw results or code that can be checked. A high score
cannot hide a failed required check. The final report can choose one framework,
name a backup choice, or say that more testing is needed.

## Done When

- Both apps have the same agreed features and data rules.
- Both apps can read live V20 data from the repository root.
- Both apps use the exact same fixtures and benchmark settings.
- Focused tests and live read-only checks pass with fresh output.
- Benchmark JSON includes enough details to repeat each test.
- The final report shows raw results, pass/fail results, scores, limits, and a
  framework recommendation.
- No file outside `TUI testing` changes because of this work.

## Not Included

- Any trading, broker, account, order, position, or risk control
- Model training or promotion
- Creating, approving, rejecting, cancelling, or restarting runs
- Scheduler or deployment controls
- Replacing the V20 command line or platform service
- A network service, remote dashboard, Jira link, or outside plugin
- Picking a winner before the measured results are ready
