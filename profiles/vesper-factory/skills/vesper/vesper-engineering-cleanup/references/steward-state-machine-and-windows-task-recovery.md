# Deterministic Steward and Windows Task Recovery

## Steward state-machine contract

A scheduler heartbeat is not work. Use these invariants for lane-based autonomous stewards:

1. **Count only material work.** Do not increment cycle/work counters for waiting, already-produced, disabled, completed, or no-packet states.
2. **Concrete packets only.** Delegation lanes require a stable `work_packet.id`; generic `delegate_to_*` lanes must be ineligible without one.
3. **Exactly-once claim.** Persist the packet claim atomically *before* emitting a delegation signal. A crash then leaves a reviewable claim instead of permitting duplicate dispatch.
4. **Completion evidence excludes work.** Existing verified artifact/receipt evidence makes a completed lane ineligible.
5. **Unchanged waits are silent.** Persist/log a wait transition once; repeated identical checks must leave both state and logs unchanged.
6. **Do not reset stuck state on a signal.** A delegation signal without accepted output is not progress. Escalation counters should reflect failed material work, not passive market-data waits.
7. **Cron compares pre/post state.** Dispatch only if the current run increased the material-work counter and created a new packet claim. Never dispatch from an old log line or unchanged `last_action`.

Minimum regression set:

- completed lane is ineligible;
- packet claims exactly once;
- delegate lane without packet is blocked;
- disabled lane is blocked;
- two identical waiting runs do not increment counters, append logs, or rewrite state.

## Windows Task Scheduler recovery contract

1. Keep the `.bat` wrapper tracked and thin: set `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8`, quote the repo interpreter, preserve the canonical log filename, capture `%ERRORLEVEL%`, and `exit /b` with it.
2. Keep a tracked task definition or installer beside the wrapper. `Status: Ready` is not execution evidence.
3. A successful interactive/manual trigger proves the action chain, not logout-safe scheduling. Query and record `Logon Mode`, battery policy, `Last Run Time`, and `Last Result` separately.
4. Converting an existing task from `InteractiveToken` to `S4U` or `SYSTEM` generally requires administrator elevation. If registration is denied, preserve the tested definition and report the live task as interactive-only; do not claim durability.
5. For `schtasks /Create /XML`, an XML declaration that advertises UTF-8 can produce `unable to switch the encoding` on some Windows paths. Use an encoding that matches the actual bytes or omit the encoding declaration for an ASCII/UTF-8 task file.
6. `SYSTEM` requires elevation. S4U avoids storing a password but has restricted network-authentication semantics; verify the actual pipeline under the chosen principal instead of assuming parity.
7. Trigger the real bounded task and require `Last Result: 0`, current logs, and validated downstream receipts. A nonzero result caused by a genuine fail-closed data/factor gate is correct scheduler behavior—repair the underlying transient path rather than weakening the orchestrator.
8. For transient public-data fetches in required weighted factors, prefer bounded retry with regression coverage. Preserve final failure metadata and let the ordered pipeline stop if all attempts fail.

## Verification evidence to retain

- exact task query output (`Logon Mode`, `Last Result`, action path);
- wrapper/task-definition tracked status;
- focused RED→GREEN tests;
- two-run steward silence probe;
- final pipeline log ending in the real completion marker;
- downstream candidate/activation/read-only observation validators.
