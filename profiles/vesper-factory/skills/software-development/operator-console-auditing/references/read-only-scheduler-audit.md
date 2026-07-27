# Read-Only Scheduler Audit

Use this reference when stale data, missed runs, or conflicting scheduler claims must be investigated without triggering jobs or changing configuration.

## Evidence matrix

For every plausible scheduler authority, record:

| Field | Evidence |
|---|---|
| Authority | OS scheduler, app daemon/job store, agent cron, service, startup launcher |
| Task/job | Exact registered name and identity |
| State | Enabled/disabled, ready/running/paused, daemon/process present |
| Schedule | Trigger, timezone, calendar, interval, grace/SLA |
| Last execution | Start, finish, result/exit code, duration |
| Next execution | Exact timestamp or why unavailable |
| Runtime context | User, interactive/service token, working directory, environment |
| Restrictions | Battery, idle, login, instance, timeout, catch-up behavior |
| Command | Exact action, wrapper, interpreter, arguments |
| Data authority | Inputs read and outputs written |
| Receipt/log | Exact path and matching timestamps |

## Investigation sequence

1. Enumerate registered OS tasks broadly by both name and action path; do not assume naming is consistent.
2. Query verbose task state and XML/definition for exact triggers, principal/logon mode, actions, power constraints, and instance policy.
3. Check scheduler history-channel status before querying events. Empty output from a disabled history channel is not evidence that nothing ran.
4. **Verify the "Task To Run" action path exists on disk.** A task can be `Status: Ready` with a valid `Next Run Time` and still silently fail if the wrapper/executable it references does not exist. `Last Result: 1` (exit code 1) on a task whose action points to a missing file is the signature of this failure mode — the task is enabled by the scheduler but cannot launch.
   - If missing, check whether the file was ever committed to version control. A file that was never in VCS (vs. accidentally deleted) has a different root cause and recovery path.
   - Also check whether the task should reference a different launcher — e.g. a Python `.py` script via `python scheduler/backup_pipeline.py` versus a `.bat` wrapper that no longer exists.
5. Enumerate relevant process command lines and working directories. A config file is inactive if its daemon is absent and no startup authority launches it.
6. Read wrapper scripts and trace each command to ingest, scoring/derivation, artifact publication, dashboard refresh, preview, and execution boundaries.
7. **Separate "wrapper/launcher exists" from "all individual pipeline scripts exist."** The scheduled task may reference a batch file or wrapper while each stage script (ingest, scoring, dashboard) is present and individually runnable. Verify all stages independently — a missing wrapper does not imply broken pipeline code.
8. Resolve junctions/symlinks and compare file identity before treating two output paths as distinct stores.
9. Correlate scheduler times with append-only logs, per-run logs, artifact mtimes, receipts, and read-only datastore facts such as maximum source date and row counts.
10. **Cross-reference the last successful log entry with the scheduled task's last successful exit code.** If the log shows a clean run on date D but the task shows exit code 1 for every run after D, the gap reveals when the wrapper went missing or the configuration diverged. Pipeline logs often capture the last clean run timestamp and per-stage output.
11. Compare the last run time with the configured trigger. An immediate post-registration run or an off-schedule success is usually manual/repair validation, not proof of an unattended cycle.
12. **Rule out credential/config issues before concluding the wrapper is the sole problem.** Check environment variables, secrets, API keys, and cloud credentials independently — a missing wrapper and expired credentials are separate failure modes that can compound. Verify credentials are present and syntactically valid (file exists, not commented out, correct format) even if they aren't the root cause.
13. Report unknown history explicitly when `Last Run` has been overwritten and event history is unavailable.

## Windows-oriented probes

Keep probes read-only. Typical sources include:

- `schtasks /query /fo CSV /v` for broad enumeration and filtering by task name/action.
- `schtasks /query /tn <name> /fo LIST /v` for current last/next/result state.
- `schtasks /query /tn <name> /xml` for principal, trigger, action, battery, idle, and instance settings.
- `wevtutil gl Microsoft-Windows-TaskScheduler/Operational` before event queries to establish whether history is enabled.
- Process enumeration with full command line, parent PID, creation time, and working directory.
- SQLite opened with URI `mode=ro` plus `PRAGMA query_only=ON` for datastore verification.

On shells with path rewriting, invoke Windows executables through an argument-safe subprocess API or disable path conversion. Avoid temporary files when direct capture is available.

## Reporting rules

- Lead with the current authoritative state.
- Separate current health from historical root cause.
- Distinguish “configured,” “enabled,” “daemon running,” “command path verified,” and “unattended cycle observed.”
- List tasks that actually update the target data root separately from tasks that only derive artifacts, refresh presentation, preview orders, or execute actions.
- Include concrete task fields, commands, logs, datastore facts, and evidence limitations.
- Never claim read-only if a task, ingestion path, refresh endpoint, or side-effecting control was invoked.
