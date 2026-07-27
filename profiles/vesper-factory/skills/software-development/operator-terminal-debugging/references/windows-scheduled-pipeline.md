# Windows Scheduled Pipeline Reliability

Use this when a Windows Task Scheduler job appears configured but the pipeline is stale or the task reports only exit code `1`.

## Investigation order

1. Query the task directly, not only by broad task listing:
   ```bat
   schtasks.exe /Query /TN "\\Vesper Factor Scores Backup" /FO LIST /V
   ```
2. Check `Last Run Time`, `Last Result`, `Task To Run`, `Run As User`, `Logon Mode`, and `Next Run Time`.
3. Confirm the wrapper exists and inspect its log. No log usually means the wrapper never started or could not create its log directory.
4. Reproduce through native `cmd.exe`, not a Bash path-converted invocation:
   ```bash
   MSYS_NO_PATHCONV=1 cmd.exe /d /c "call D:\\vesper\\scheduler\\windows_factor_pipeline.bat"
   ```
5. Read the wrapper log after each run; identify the first failing pipeline stage.

## Robust wrapper pattern

The batch wrapper should:

- set an absolute project root;
- set an absolute project interpreter (`D:\\vesper\\.venv\\Scripts\\python.exe`);
- create the log directory before the first redirect;
- log user, host, interpreter, Python version, stage output, and final exit code;
- fail explicitly if the interpreter is missing;
- invoke the Python pipeline through `cmd.exe /d /c` in the scheduled task action.

Do not rely on bare `python`: Task Scheduler's PATH differs from an interactive shell and can select Hermes' interpreter, a global interpreter, or a Windows Store alias.

## Dependency diagnosis

If ingest succeeds but factor execution fails with `ModuleNotFoundError`, treat it as runtime provisioning, not an approval gate. Install the missing package into the exact interpreter used by the wrapper and record the runtime set in a repository dependency manifest. For the Vesper quant pipeline, the core set is:

```text
numpy
pandas
python-dotenv
requests
scikit-learn
scipy
statsmodels
```

Then rerun the same native wrapper. Do not bypass factor, paper-readiness, or live-execution gates to make the schedule appear green.

## Verification

A real repair requires all of:

- the direct task query shows the explicit `cmd.exe` action and future run time;
- the wrapper regression test checks absolute interpreter and guaranteed logging;
- the native wrapper is exercised end-to-end;
- the log contains `COMPLETED OK`;
- expected fresh artifacts and receipts exist;
- scheduler-focused pytest passes.

An enabled task is not proof of execution. A green dry-run is not proof of execution. The log and fresh artifact are the proof.