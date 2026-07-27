# Data-directory freshness and weekend scheduler audit

Use this when an operator judges pipeline freshness from Windows Explorer folder timestamps or expects every `vesper_data` subdirectory to refresh daily.

## Filesystem interpretation

- `D:/vesper/data` may be a Windows junction to `D:/vesper/vesper_data`; prove identity (`cmd /c dir D:\vesper /AL`, `Path.resolve()`, or `os.path.samefile`) before treating them as separate stores.
- A directory's Explorer **Date modified** does not reliably change when an existing child file is overwritten or an SQLite database is updated. Audit newest files recursively and query source provenance/MAX(session date) inside canonical databases.
- Distinguish file mtime from admitted data freshness. For canonical OHLCV, verify the database path, `MAX(date)`, latest-session row count, total coverage, and `PRAGMA quick_check`, then reconcile with wrapper logs and downstream artifact provenance.

## Classify before declaring staleness

A top-level data directory can be:

1. active production input/cache;
2. periodic collector;
3. historical snapshot/archive;
4. one-time pilot or admission fixture;
5. research artifact;
6. retired/abandoned factor output.

Trace each directory to a current writer, registry entry, and authoritative scheduler action. Dashboard display or cleanup references alone do not prove an active feed. Empty dated payloads from removed factors are placeholders, not evidence of a healthy collector.

## Scheduler authority and weekend behavior

- Reconcile live Windows tasks, `scheduler/jobs.json`, Hermes cron, processes, and logs. Configuration files can describe a scheduler that is no longer running.
- Inspect schedule type, next/last run, result, action command, logon mode, battery conditions, and event-history availability.
- A Windows task scheduled **Daily** launches on weekends unless its action or wrapper explicitly suppresses weekends. A market-aware pipeline may still run and resolve the prior XNYS session (Saturday/Sunday normally resolve to Friday).
- Weekend runs can prove task launch, interpreter/cwd, ingestion mechanics, and fail-closed source-date logic, but they do not by themselves prove normal weekday timing.
- `InteractiveToken` / “Interactive only” proves neither logout-safe nor set-and-forget operation. Require a natural run under the intended logon state. Battery conditions can independently suppress a task.
- Do not overwrite natural-run evidence with a manual trigger before determining whether the scheduled run occurred. If Task Scheduler Operational history is disabled, preserve wrapper logs and task receipts because reconstruction may otherwise be impossible.

## Reporting order

Report plainly:

1. canonical production source freshness;
2. whether the latest success was scheduled or manually/out-of-window triggered;
3. unattended-execution caveats;
4. active-but-unscheduled collectors;
5. archives, research snapshots, and retired folders.

Avoid saying “none of the folders updated” or “the pipeline is stale” from Explorer alone. Name the exact stale layer.