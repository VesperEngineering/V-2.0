# Windows scheduler recovery and safe preview pattern

Use this reference when a scheduled Vesper pipeline appears not to have run, timed out, or reports a stale result.

## Investigation order

1. Read the Windows task directly:
   ```text
   schtasks /query /tn "\\Vesper Task Name" /fo LIST /v
   ```
   Capture `Task To Run`, `Last Run Time`, `Last Result`, `Next Run Time`, and `Status`.
2. Verify every referenced batch/script path exists. A task can be `Ready` while pointing at a deleted wrapper.
3. Read the wrapper and its log. Do not infer success from the task state alone.
4. Run the wrapper's exact interpreter with a no-side-effect readiness command. For Vesper, use the project venv, not ambient `python`.
5. Reproduce the failed child step directly with the same interpreter and working directory.

## Timeout interpretation

A log such as `exit=124` / `timed out after 300s` is evidence about the timeout value used by that invocation, not necessarily the current source. Compare the historical log with the current `backup_pipeline.py` and its `--dry-run` output. Keep the timeout explicit in `PipelineStep` and assert it in tests.

For factor scoring, prefer a measured bounded budget large enough for the real universe (currently 900s after a 300s run was insufficient). Verify with a direct scheduled-venv run before claiming recovery.

## Safe scheduled preview

A scheduled rebalance preview must call the bounded no-submit lane, never a retired/mutating rebalance script:

```text
scripts/run_daily_paper_evidence_loop.py \
  --date YYYYMMDD --symbol AAPL --side buy --notional 5.00 --no-submit
```

The wrapper should log the receipt path, never submit an order, and preserve a fail-closed decision in the receipt. For a no-submit preview, a blocked evidence decision can be operationally successful (`Last Result: 0`) if and only if the expected receipt was generated; never convert the decision to PASS or submit as part of this normalization.

## Verification

Use three layers:

- Focused scheduler tests for step order, timeout, lock, dry-run, and wrapper contract.
- Direct wrapper execution using a Windows-compatible invocation; beware MSYS path/quote conversion when calling `cmd.exe` from Bash.
- Actual `schtasks /run` followed by a fresh query and log readback. A successful trigger only proves task acceptance; verify the child receipt and `Last Result`.

The 09:40 preview may remain fail-closed when same-date data/candidate receipts are absent. That is a data-evidence producer gap, not a scheduler success to hide or a reason to weaken the gate.

## Logout-safe authenticated Windows tasks

Use a password-backed principal for pipelines that must make authenticated network calls after logout. `InteractiveToken` is login-session dependent, while S4U commonly lacks network credential access; neither proves the required unattended network behavior. Keep `RunLevel=LeastPrivilege`, permit battery operation when continuity requires it, and use `StartWhenAvailable` for recovery.

A Windows Hello PIN is not an account password and cannot satisfy Task Scheduler's password logon. Never accept or relay the password through chat, command arguments, source, XML, logs, shell history, or receipts. Invoke `schtasks /Create ... /RP "*"` from an elevated interactive console so Windows owns the secure prompt. If the user does not know the actual password, stop rather than retrying repeatedly; leave redundant coverage active until the password is reset through an official Windows recovery path.

## Immutable runtime deployment and ACL gate

Do not schedule broadly writable repository code, credentials, or an interpreter under a privileged or unattended task. Deploy a version-pinned runtime snapshot to a separate root and secure that root **before** copying `.env` or code into it.

The deployment receipt should bind the source commit SHA, runtime root, exact wrapper/interpreter paths, required-file presence, and ACL verification. Check the root, `.env`, interpreter, and wrapper; only the task user, SYSTEM, and Administrators may hold write-capable ACEs. Copy tracked source from the reviewed commit rather than the mixed worktree. Preserve a local `DEPLOYED_HEAD` marker as evidence, not authority, and reverify ACLs after every runtime update.

## PowerShell and registration diagnostics

Mixed PowerShell 7/Windows PowerShell module paths can make Windows PowerShell 5.1 discover but fail to autoload `Microsoft.PowerShell.Security`. Import the inbox manifest explicitly:

```powershell
Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1"
```

Parse every installer/wrapper before elevation. Elevated executable code must live inside the ACL-restricted runtime; an unelevated launcher may request UAC, but it must point elevation at immutable code.

When `schtasks.exe` fails, preserve only a non-secret diagnostic receipt: status, exception type, sanitized error text, and timestamp. Stream native output to the visible elevated console while teeing it to a temporary file, then delete the temporary file in `finally`; never capture stdin or credentials. Distinguish UAC cancellation, credential rejection, and registration failure rather than treating every exit 1 alike.

## Cutover proof before removing redundancy

After registration, query the exact task and prove:

1. password-backed/non-interactive logon rather than `Interactive only`;
2. action and working directory inside the immutable runtime;
3. approved principal and least-privilege run level;
4. intended battery and `StartWhenAvailable` settings;
5. a real trigger with `Last Result: 0`;
6. canonical wrapper log and expected receipts from the same run window;
7. completed authenticated network reads.

Only then disable redundant coverage. A historical `Last Result: 0` from the old task, or registration/query success alone, is not cutover evidence.
