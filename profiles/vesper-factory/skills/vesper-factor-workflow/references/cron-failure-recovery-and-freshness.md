# Cron failure recovery and freshness verification

Session-derived procedure for Vesper scheduled operations.

## Model/provider drift failures

Hermes cron jobs can fail closed before making an inference call when a job was created with an unpinned model/provider snapshot and global inference configuration later changes. Inspect the active cron store (`%LOCALAPPDATA%/hermes/cron/jobs.json` on Windows) and read the job's `last_error`; do not infer the cause from `last_status` alone.

Typical message:

```text
Skipped to prevent unintended spend: global inference config drifted since this job was created ... this job is unpinned
```

Repair by explicitly pinning the job to an available provider/model with `cronjob update --model` (or the equivalent CLI), preserving the job's safety prompt and tool restrictions. For the Vesper pattern, use the included provider/model that is actually available for the role; do not bypass the drift guard or silently switch to a paid provider with no credits.

A provider-credit failure is a separate cause: the job may be pinned to a provider whose account has no available credits. Read the exact `last_error`, then move the research job to an available provider/model and run it once to verify.

## Verification order

For dependent jobs, repair and run in dependency order:

1. Research job (independent) and nightly read-only audit (independent) may run in parallel.
2. Run the bounded overnight repair only after the fresh nightly-audit output exists, because it consumes that audit context.
3. Read back the cron registry and confirm each job has `last_status: ok`, a current `last_run_at`, and no new `last_error`.
4. Verify concrete artifacts: research memo path, issue registry/health briefing read-back, and any repair test result. A successful cron run means the job executed; it does not mean Vesper is healthy.

## Freshness recovery

When OHLCV is stale, do not wait for the next scheduler tick if a safe no-order chain is available. Confirm the wrapper is the no-order path, then run:

```text
ingest -> factor scores -> sector basket -> dashboard refresh
```

Verify source-session date, admitted universe size, score provenance, excluded non-universe count, basket artifact, and dashboard artifact. Preserve fail-closed execution boundaries: freshness recovery must not invoke broker orders.

## Windows test-environment note

A stale inaccessible `%TEMP%\\pytest-of-<user>` directory can create `PermissionError` during pytest fixture setup before tests execute. This is an environment condition, not evidence of a code regression. Use a writable explicit basetemp for verification, for example:

```text
python -m pytest <focused-tests> --basetemp D:/vesper/.tmp/<run-tag>
```

Report the workaround and do not call a suite run canonical if it only passed after changing test-environment setup.
