# Autonomous financial research Phase 1 runbook

## Purpose and boundary

Phase 1 runs one bounded coverage analysis against local Massive data and emits
an evidence-bound recommendation. It is shadow research only: no orders,
promotion, training, web retrieval, scheduler activation, risk or capital
changes, or deployment.

There is no automatic two-week schedule and no automatic action on August 12.
August 12, 2026 is a human review gate for deciding whether later work should be
authorized; Phase 1 does not notify, schedule, promote, or act on that date.

## Supported events

- `direct-request` always enters the analysis-only workflow and forbids
  `--observed-metric` and `--threshold`.
- `weak-model-result` requires both metric options. It enters research only when
  `--observed-metric` is lower than `--threshold`; an equal or higher result is
  persisted as `ignored` and creates no derived dataset or validation evidence.
  Both values must be finite; `NaN` and positive or negative infinity are
  rejected before service construction.

Dates must use ISO `YYYY-MM-DD`, the start must not follow the end, and
`--symbol` may be repeated. The only admitted analysis is the fixed two-node
coverage plan: read source coverage, then summarize it. Its single aggregate
binds the requested symbols and inclusive date bounds. Malformed dates are
rejected when they occur in that candidate window; rows outside it are not part
of the request.

## Controller-owned locations

The examples use explicit Windows paths so state and outputs cannot depend on
the current directory.

| Content | Location |
| --- | --- |
| LangGraph checkpoints | `C:\Users\bgonn\AppData\Local\V20\agent-platform\checkpoints.sqlite3` |
| Terminal research-run records | `C:\Users\bgonn\AppData\Local\V20\agent-platform\store.sqlite3` |
| Derived coverage JSON | `C:\Users\bgonn\AppData\Local\V20\agent-platform\derived\<run_id>\coverage-<cache-prefix>.json` |
| Validation evidence | `C:\Users\bgonn\AppData\Local\V20\agent-platform\evidence\runs\<run_id>\coverage-<cache-prefix>-validation.json` |
| Read-only Massive source | `C:\Users\bgonn\Desktop\v20\vesper\data\massive\sp500\sp500_ohlcv.sqlite` |

`--state-db` selects the checkpoint database. Its parent owns
`store.sqlite3`, `knowledge-index.sqlite3`, and `derived\`. `--evidence-root`
selects the separate immutable evidence root. The service rejects state,
derived, or evidence locations that overlap the repository, each other, or the
Massive and model-research protected roots.

The Massive SQLite database is opened read-only and immutable with query-only
mode. Phase 1 hashes it before and after the aggregate and fails closed if it
changes, has unsafe SQLite sidecars, has an invalid schema/date, or cannot be
read safely. It never writes under `vesper\data\massive\` or
`vesper\data\model_research\`.

## Start a direct request

From `C:\Users\bgonn\Desktop\v20` in PowerShell:

```powershell
$direct = uv run --locked vesper-agent `
  --state-db "C:\Users\bgonn\AppData\Local\V20\agent-platform\checkpoints.sqlite3" `
  --evidence-root "C:\Users\bgonn\AppData\Local\V20\agent-platform\evidence" `
  --research-data-root "C:\Users\bgonn\Desktop\v20\vesper\data\massive" `
  --json financial-research-start `
  --event-type direct-request `
  --objective "Compare local SPY and QQQ coverage." `
  --symbol SPY `
  --symbol QQQ `
  --start-date 2024-01-02 `
  --end-date 2024-01-31 | ConvertFrom-Json

$direct.run_id
```

No credential option or environment binding is needed. This path does not
initialize a model specialist or trading/provider runtime.

## Start a weak-model-result run

Use a metric below its threshold to exercise the admitted weak-result path:

```powershell
$weak = uv run --locked vesper-agent `
  --state-db "C:\Users\bgonn\AppData\Local\V20\agent-platform\checkpoints.sqlite3" `
  --evidence-root "C:\Users\bgonn\AppData\Local\V20\agent-platform\evidence" `
  --research-data-root "C:\Users\bgonn\Desktop\v20\vesper\data\massive" `
  --json financial-research-start `
  --event-type weak-model-result `
  --objective "Check coverage after a weak shadow metric." `
  --symbol SPY `
  --symbol QQQ `
  --start-date 2024-01-02 `
  --end-date 2024-01-31 `
  --observed-metric 0.01 `
  --threshold 0.02 | ConvertFrom-Json

$weak.run_id
```

## Inspect and compare runs

`financial-research-status` takes the run ID as a positional argument. It reads
the persisted terminal record; it does not start or resume work. It opens only
the existing Store database with SQLite `mode=ro` and does not create a root,
file, schema, knowledge index, evidence store, checkpointer, or executor.

```powershell
$directStatus = uv run --locked vesper-agent `
  --state-db "C:\Users\bgonn\AppData\Local\V20\agent-platform\checkpoints.sqlite3" `
  --evidence-root "C:\Users\bgonn\AppData\Local\V20\agent-platform\evidence" `
  --research-data-root "C:\Users\bgonn\Desktop\v20\vesper\data\massive" `
  --json financial-research-status $direct.run_id | ConvertFrom-Json

$weakStatus = uv run --locked vesper-agent `
  --state-db "C:\Users\bgonn\AppData\Local\V20\agent-platform\checkpoints.sqlite3" `
  --evidence-root "C:\Users\bgonn\AppData\Local\V20\agent-platform\evidence" `
  --research-data-root "C:\Users\bgonn\Desktop\v20\vesper\data\massive" `
  --json financial-research-status $weak.run_id | ConvertFrom-Json

@($directStatus, $weakStatus) | ForEach-Object {
  [pscustomobject]@{
    run_id = $_.run_id
    event_type = $_.event.event_type
    status = $_.status
    rows = $_.dataset.row_count
    tickers = $_.dataset.ticker_count
    coverage_start = $_.dataset.coverage_start
    coverage_end = $_.dataset.coverage_end
    derived_output = $_.dataset.derived_output_path
    evidence = $_.dataset.validation_evidence.relative_path
  }
} | Format-Table
```

Compare the persisted status, coverage counts/dates, source/transform/cache
hashes, initiating event, relative derived path, evidence path, conclusion, and
uncertainty. The accepted terminal hash covers that event and the complete typed
output chain. Output `created_at` values record their generation times and may
follow the event intake time. A fair comparison uses the same symbols and date
window. Different `run_id` and `event_id` values are expected.

## Status and failure semantics

- `completed`: coverage exists and contains no null close rows. The conclusion
  establishes coverage only, not price quality, returns, or model fitness.
- `stopped`: the run cannot accept a conclusion, including coverage with null
  close rows or a workflow failure that was durably recorded.
- `ignored`: a weak metric met or exceeded its threshold; no analysis executed.
- Invalid CLI option combinations fail before persistence.
- A missing, unavailable, or integrity-invalid status record reports
  `platform unavailable: financial research run is unavailable`.
- Workflow execution and replay-integrity failures expose the generic message
  `platform unavailable: Financial research workflow failed.` and exit code 4;
  raw internal details are not emitted.

Each CLI `financial-research-start` call creates a new controller-owned run; it
is not a cross-invocation deduplication command. Within one run, replay of the
same event fingerprint returns an existing outcome only when its accepted
terminal record is integrity-valid: `completed`, `ignored`, or an accepted
`stopped` recommendation. A generic workflow-failure record remains minimal and
inspectable through status. Retrying its exact event removes only the prefixed
`financial-research:<run_id>` checkpoint history and performs a fresh bounded
execution; unrelated software-workflow history is preserved. Terminal Store
write failures follow the same sanitized cleanup and retry behavior. A different
event under the same run ID fails closed. Derived and evidence files are
immutable: an exact same-byte output write is accepted idempotently, while
conflicting bytes at an existing path are rejected. Status inspection validates
terminal integrity, is read-only, and is repeatable.

## Verification and review gate

Verify the installed interface without opening persistence:

```powershell
uv run --locked vesper-agent --help
uv run --locked vesper-agent financial-research-start --help
uv run --locked vesper-agent financial-research-status --help
```

On August 12, 2026, a human may review accumulated comparison evidence and
decide whether to authorize another phase. Nothing in Phase 1 grants model
training or promotion authority, and the review date itself triggers no action.
