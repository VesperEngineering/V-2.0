# Windows batch session resolver and fail-closed task parking — 2026-07-20

This is dated implementation evidence, not a claim about current installed state.

## Defect pattern

A Task Scheduler wrapper attempted to populate `RUN_DATE` with inline Python inside `for /f`:

```bat
for /f %%D in ('"%PYTHON%" -c "from datetime import datetime; print(datetime.now().strftime('%%Y%%m%%d'))"') do set "RUN_DATE=%%D"
```

Nested command, quote, parenthesis, and percent parsing left `RUN_DATE` unset and the wrapper exited `92` before its no-submit runner.

## Durable repair pattern

Move date/session logic into one tracked Python script whose stdout is exactly one token. Keep the batch wrapper declarative:

```bat
for /f "usebackq delims=" %%D in (`"%PYTHON%" scripts/resolve_completed_xnys_session.py`) do set "RUN_DATE=%%D"
if not defined RUN_DATE exit /b 92
```

The resolver should import the canonical exchange-calendar helpers and select the prior completed session:

```python
def resolve_completed_xnys_session_yyyymmdd(now=None):
    current = datetime.now().astimezone() if now is None else now
    return previous_xnys_session(xnys_today(current)).strftime("%Y%m%d")
```

Do not use wall-clock calendar `today` for a market-session preview.

## RED-to-GREEN validation ladder

1. Add a static wrapper regression requiring the tracked resolver path and rejecting inline ` -c "` Python.
2. Observe the regression fail against the old wrapper.
3. Add the tracked resolver and minimal batch call; make the static test pass.
4. Add a fixed-time Monday regression requiring the previous Friday; then add an exchange-holiday regression where relevant.
5. Run focused pytest, `py_compile`, critical Ruff, and `git diff --check`.
6. Run an external **resolver-only** batch canary using the exact `for /f "usebackq delims="` form. This proves Windows parsing without running the evidence loop or any broker/order path.
7. Integrate the reviewed source into the canonical deployment.
8. Only then run one installed **preview-only/no-submit** task canary and join Task Scheduler result, wrapper log, and generated receipt. Never use this step to trigger an order-capable task.

Observed repair evidence in this session:

- focused wrapper suite: `4 passed`;
- Monday resolver output: `20260717`;
- resolver-only Windows batch canary: `RUN_DATE=20260717`, exit `0`;
- no installed preview task or order-capable task was triggered during source repair.

## Parking missing order-capable tasks

A missing wrapper is accidental inertness. To park matching tasks safely:

1. Query every exact task name and action first.
2. Require the action to equal the expected missing path; abort on any mismatch.
3. Require the action file to remain absent; if it exists unexpectedly, stop and re-audit capability.
4. Disable the exact tasks without invoking them.
5. Read back `State=Disabled`, `Enabled=false`, action, arguments, and retained last result.
6. Record that no task was triggered and no order path was used.

Do not recreate a missing order wrapper merely to make Task Scheduler green. Restoration, an order canary, and broker reconciliation are separate authority decisions.
