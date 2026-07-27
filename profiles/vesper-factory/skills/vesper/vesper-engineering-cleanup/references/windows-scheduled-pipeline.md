# Windows Scheduled Pipeline: Fail-Closed Verification

Use this reference when Vesper needs a Windows Task Scheduler fallback for a
multi-step artifact or paper-execution workflow.

## Architecture

Keep sequencing in one tested Python module. The batch file should only establish
the runtime, encoding, log destination, and return code.

```python
@dataclass(frozen=True)
class Step:
    name: str
    script: Path


def run_pipeline(steps, *, root, executable):
    for step in steps:
        result = subprocess.run(
            [executable, str(root / step.script)],
            cwd=root,
            check=False,
        )
        if result.returncode != 0:
            raise StepError(step.name, result.returncode)
```

Required tests:

1. Steps are in dependency order.
2. A failing middle step prevents downstream execution.
3. The CLI returns the child failure code.
4. `--dry-run` checks script existence without executing.
5. Domain admission rejects missing/empty required artifacts or inputs.

## Thin Batch Wrapper

```bat
@echo off
setlocal
set "PY=C:\path\to\venv\Scripts\python.exe"
set "LOG=C:\path\to\pipeline.log"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "D:\vesper" || exit /b 1

echo [%date% %time%] Starting pipeline >> "%LOG%"
"%PY%" scheduler\backup_pipeline.py >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo [%date% %time%] FAILED rc=%RC% >> "%LOG%"
  exit /b %RC%
)
echo [%date% %time%] Completed pipeline >> "%LOG%"
exit /b 0
```

Why both UTF-8 variables: Task Scheduler often redirects Python output under a
legacy Windows code page. A Unicode arrow/checkmark in otherwise valid status
output can raise `UnicodeEncodeError` after useful work has already completed.
The wrapper must still report failure rather than silently returning 0.

## Real Task Verification

A direct command or dry run is not enough. Capture all of:

- exact `Task To Run` action;
- trigger type, start time, and weekday list;
- `Run As User` and `Logon Mode`;
- enabled/disabled and current status;
- last run time and last result;
- next run time;
- wrapper log tail and expected output artifacts.

Run the real **artifact-only** task once, wait until it leaves `Running`, and
require `Last Result: 0`. Do not run a broker task to test wiring if doing so can
duplicate orders; verify its action/configuration and exercise broker-free guard
unit tests instead.

`Interactive only` means the task will not run after logout. Record this as an
operational limitation; do not describe it as persistent unattended service.

## Broker-Facing Guard Order

Before account reads or order submission:

1. hardcode/verify paper endpoint;
2. reject weekends;
3. load latest expected-date artifact;
4. enforce maximum age and reject future timestamps;
5. validate exact target count, uniqueness, and symbol shape;
6. create broker client and require broker clock `is_open` (covers holidays);
7. reconcile/cancel conflicting orders, failing on cancellation errors;
8. propagate every submission rejection to process exit;
9. write a receipt only after all intended submissions were accepted.

A nonzero exit after partial accepted submissions is still not atomic. Record the
partial-order/reconciliation limitation and design a serialized broker-confirmed
controller before production protective-order integration.

## Documentation Contract

Update the three durable surfaces together:

- `docs/STATUS.md`: live state, verified/unverified, blockers, next order.
- `README.md`: concise current operating snapshot and source-of-truth pointers.
- `CHANGELOG.md`: dated evidence, failures encountered, safety boundary, remaining work.

Never infer economic correctness from process success. Keep stale data, symbol
quality, survivor bias, and point-in-time provenance as separate admission gates.
