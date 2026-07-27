# Windows Scheduled Paper-Mutation Verification

Use this reference for any Windows Task Scheduler lane that can mutate a paper broker account.

## Required sequence

1. Run the guarded producer in dry-run mode with the same interpreter and repository root used by the scheduled task.
2. Run focused tests for the low-level guard, submitter, reconciliation, readiness, and downstream evidence readers.
3. Compile changed modules and run `git diff --check`.
4. Create/query the real task and inspect `Task To Run`, `Next Run Time`, `Last Run Time`, `Last Result`, and `Status`.
5. Trigger the real task once under explicit operator authorization. Do not treat `Status: Ready` or `schtasks /run` success as proof that the action completed.
6. Read the task log and receipt. Confirm the action reached the intended endpoint, HTTP status, exact symbol/side/notional, and redacted response.
7. Immediately run read-only broker reconciliation for order status and position/fill state. A successful POST receipt is not lifecycle completion.
8. Re-run the focused suite after any production fix exposed by the smoke test.

## Common production-only defects

- An absolute script path can execute while a package import such as `from scripts...` fails because the repository root is absent from `sys.path`; insert the resolved repo root or use a verified package invocation.
- Central execution guards and downstream evidence readers often retain retired hard-coded symbols. Candidate selection, pretrade, low-level guard, fill evidence, and portfolio evidence must all derive from the same admitted candidate receipt.
- A scheduler task can report `Ready` with a nonzero `Last Result`; correlate that result with the exact wrapper log and filesystem action path.
- A same-day order can be accepted and filled while a post-order evidence script still reports no order because it looks for a legacy symbol or receipt filename.

## Scheduler-authority inventory

Before adding recovery windows or declaring redundancy healthy, inventory every scheduler that can touch the same evidence or mutation path: Windows Task Scheduler, Hermes cron, gateway dispatchers, repository daemons, and manual recovery jobs. Same-time jobs are not automatically redundancy; they may be competing authorities that rewrite prerequisites during execution.

Use this separation:

- one primary producer/mutation authority;
- one conditional, idempotent recovery path;
- repeated exact-key reconciliation windows;
- read-only monitoring and strategy briefings.

A briefing/review job must not implicitly mutate evidence or wake workers unless its prompt, work packet, authority, and dispatch receipt explicitly prove that behavior. Pause or reschedule duplicate production jobs before an observed smoke window so the result has one attributable cause.

## Retry and intraday redundancy rule

Use a deterministic client order ID. Recovery windows may reconcile the same ID, but must not blindly POST after timeout, malformed response, or reconciliation failure. Unknown remains visible and blocks duplicate mutation.

For repeated same-day windows, add an immutable one-effect-per-day envelope latch before network activity:

- Hold a process-level OS/file lock across the complete critical section: read prior receipt → validate immutable envelope → reconcile → optional POST → validate response → durably write receipt. A sequential receipt check is not atomic; two tasks with different deterministic IDs can otherwise both submit.
- Bind the requested date to the current trading-calendar date in the market timezone before choosing receipt paths or client IDs. Caller-controlled historical/future dates must not create a second daily namespace.
- Same date and same symbol/side/notional: reconcile the exact deterministic ID.
- Same date but changed symbol, side, or notional: block before POST and write a separate block receipt; preserve the authoritative accepted-order receipt.
- Prior `ORDER_STATUS_UNKNOWN`: perform exact-key GET reconciliation only. If the result is absent, malformed, mismatched, or still ambiguous, return unknown without POST.
- Treat lock contention as a visible fail-closed result, not a retryable POST failure.

An HTTP success is transport evidence, not semantic acceptance. Before recording `PASS_ORDER_SUBMITTED`, require valid JSON and exact remote identity: client/idempotency key, symbol, side, and all immutable quantity/notional fields exposed by the provider. Missing or mismatched identity is `ORDER_STATUS_UNKNOWN`. A reconciled accepted order should return a successful process exit code so external schedulers do not retry it as a failure.

Schedule read-only reconciliation shortly after every mutation/recovery window. It should regenerate fill/position evidence, run its validator, compare submission and pretrade envelopes using the real receipt field names, record the first failure, and return nonzero for drift or broker/code/receipt errors. Do not accept bare `STATUS: PASS`: bind fill evidence to the submitted date, symbol, and remote/deterministic order identity. After a scheduled mutation window, a missing/truncated expected submission receipt is an integrity failure—not a successful no-op.

## Adversarial tests required for repeated windows

- Two concurrent submitters contend for the daily lock; at most one reaches POST.
- A different-symbol same-day retry is blocked while preserving the accepted receipt.
- A historical/future `--date` is rejected before network activity.
- A prior unknown state may GET-reconcile but cannot POST while unresolved.
- HTTP 200 with invalid JSON, missing ID, or mismatched envelope becomes unknown.
- A fill receipt for another symbol/date/order cannot satisfy the monitor.
- Missing submission/fill receipts produce a nonzero scheduler result.

## Unattended network identity and immutable deployment

Treat Task Scheduler logon mode and filesystem ownership as part of mutation authority, not installation trivia.

- Do not use `TASK_LOGON_S4U` / XML `<LogonType>S4U</LogonType>` for a pipeline that needs authenticated HTTPS, network shares, or encrypted user secrets. S4U is logout-capable but does not provide network access.
- For network-capable unattended work, use either a purpose-built service identity or password logon at `LeastPrivilege`. Prompt interactively (for example, `schtasks /RP "*"`); never place a password in XML, Git, logs, or a command-line argument.
- A Windows Hello PIN is not the account password Task Scheduler requires for password logon.
- Do not point a stored-credential task at a mutable development checkout or writable virtual-environment interpreter. An unprivileged local writer could alter code that later executes as the task principal.
- Prefer an immutable reviewed runtime snapshot. Code, interpreter, launcher, and secret files should be writable only by the task identity, SYSTEM, and Administrators; separate writable data/log/artifact directories explicitly.
- Make the installer audit effective ACLs on the runtime root, secret files, interpreter, and launcher. Reject any unexpected principal with write/modify/delete/ownership rights instead of silently weakening ACLs or installing anyway.
- Source validation is not operational readiness. Keep redundant coverage active until a real logged-out run proves network access, produces the expected log/artifacts, and returns `Last Result: 0`.

## Windows batch exit-code pitfall

Inside parenthesized batch blocks, `%VAR%` is expanded when the block is parsed. Use `setlocal EnableDelayedExpansion`, capture `%ERRORLEVEL%` immediately after the command, and reference `!EXIT_CODE!` inside the block. Otherwise the wrapper can log `FAILED exit=` or a stale value even though Task Scheduler correctly records a nonzero result.

## Evidence minimum

The final smoke-test record should contain: task timestamp, task result, wrapper exit code, exact order envelope, endpoint class (paper only), redacted broker response, order status, filled quantity/price, position quantity/value, and focused test count. Never store credentials or unredacted account/order identifiers.