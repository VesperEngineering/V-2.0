# Windows Task Scheduler: logout-capable Vesper jobs

Use this reference when a Vesper Windows task must run after sign-out, retain authenticated network access, execute from a protected runtime, and produce auditable receipts.

## Credential and principal truth

- Identify the exact task principal before registration. A local Windows account, Microsoft-backed Windows account, work/school account, Outlook app credential, and Windows Hello PIN are different credential classes.
- `Password` logon requires the actual Windows logon password for that principal. A Windows Hello PIN is device-bound and is not accepted by `schtasks` password logon.
- If Windows exposes the principal as `MACHINE\user`, treat it as a local account unless authoritative Windows account settings show otherwise. A password reset in Windows sign-in/Settings targets the Windows account; a reset on a Microsoft/Outlook website may not.
- Never request, print, log, pass on a command line, or store the password in source. Use an elevated interactive prompt such as `schtasks ... /RP "*"`.
- After one rejected credential, diagnose account type before retrying. Avoid repeated blind attempts and account lockout.

## Choose the correct logon model

- Use `Password` logon when the job must retain authenticated network access after sign-out.
- Do not use S4U for this class: it can run without storing a password but normally lacks access to network resources requiring the user's credentials.
- Run with least privilege. Broker/order, scheduler, promotion, risk, and provider authorities remain separate.
- Task Scheduler may omit `RunLevel=LeastPrivilege` when exporting the registered task because least privilege is the default. Verify the reviewed template and effective task behavior; do not reinterpret canonical XML omission as elevation.

## Deploy a complete protected runtime

Do not point an unattended task at a mutable working checkout. Deploy and ACL-restrict:

1. Reviewed source snapshot and deployed-commit marker.
2. Interpreter/environment.
3. Launcher, installer, and task template.
4. Secret-bearing environment file, copied without displaying it.
5. Static inputs intentionally ignored by Git.
6. Historical databases/caches required by rolling windows.
7. Writable output, log, and receipt directories.

A Git archive alone is insufficient when the pipeline depends on ignored data or generated state. Inventory every pipeline step's reads before registration. Verify restricted write ACLs on the runtime root, secret file, interpreter, and launcher; only the task principal, SYSTEM, and Administrators should retain write authority.

For SQLite state, prefer the SQLite backup API over raw copying. Explicitly close source, destination, and validation connections before `os.replace()` on Windows; a connection context manager commits or rolls back but does not necessarily close the handle.

## Diagnostic and verification ladder

Treat source, registration, execution, and evidence as distinct layers:

1. **Source:** contract tests and syntax/parse checks pass.
2. **Registration:** installer receipt passes; inspect the installed task, not only its template.
3. **Identity:** exported task XML shows `LogonType=Password`, exact principal, command, arguments, and working directory.
4. **Invocation:** `schtasks /Run` enters `Running`. Decimal `267009` (`0x41301`) means currently running, not success.
5. **Execution:** canonical task log proves interpreter, working directory, imports, and authenticated network reads.
6. **State:** static inputs, historical lookback databases, and every configured weighted-factor dependency are present.
7. **Completion:** task returns `Last Result: 0`; log ends with an explicit success marker.
8. **Receipts:** downstream validators independently show PASS and confirm forbidden side effects were unused.
9. **Cutover:** pause redundant scheduling only after steps 1-8 pass against the installed runtime.

Starting successfully is not completion evidence. Repository pytest is not deployment evidence. A `DEPLOYED_HEAD` marker is metadata, not proof that deployed files and state correspond to it.

## Safe diagnostics

- Preserve `schtasks.exe` error text without recording credentials. Stream output to the elevated console and a restricted temporary log with `Tee-Object`; delete that log in `finally`.
- Wrap elevated installers with a restricted receipt containing only status, exception type/message, and timestamp.
- When ACL cmdlet autoload is shadowed by another PowerShell installation, explicitly import the system Windows PowerShell security module:

```powershell
$module = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1"
Import-Module $module -Force -ErrorAction Stop
```

Record the corrective import, not a durable claim that PowerShell or the cmdlet is broken.

## Root-cause signal

If the task advances farther after each missing-file repair, stop patching inputs one by one. That sequence proves the runtime dependency manifest is incomplete. Trace all downstream reads, deploy the complete minimal state set, and rerun the installed task. Keep each attempt fail-closed and leave redundant coverage enabled until the end-to-end receipt is green.
