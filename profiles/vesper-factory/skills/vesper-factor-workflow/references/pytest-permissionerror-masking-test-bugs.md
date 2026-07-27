# Pytest PermissionError on Windows Temp Dir — Masking Real Test Bugs

## The Problem

On Windows, pytest creates numbered subdirectories under
```
C:\Users\<user>\AppData\Local\Temp\pytest-of-<user>\
```
for each test session's `tmp_path` fixtures. If a prior pytest process crashes or
leaves a stale lock, succeeding runs hit:

```
PermissionError: [WinError 5] Access is denied:
  'C:\Users\bgonn\AppData\Local\Temp\pytest-of-bgonn'
```

Every test that uses `tmp_path` (or any fixture that depends on it) **ERRORs at
setup** — it never reaches the actual assertion. The output shows:

```
7 errors in 1.77s
```

Every error is the same PermissionError traceback. This **looks like** an
environment issue (and it is), but it also **masks** any genuine test logic
failures that exist in the test suite.

## Diagnostic

Run pytest with a writable `--basetemp` to bypass the locked default directory:

```bash
cd /d/vesper
python -m pytest tests/test_run_all_factors.py -q --tb=short --basetemp d:/tmp/pytest-basetemp
```

Compare with the default run:

| Outcome | Default run | `--basetemp` run |
|---------|-------------|-------------------|
| 14 tests | ERROR at setup | passed |
| 2 tests | ERROR at setup | **FAILED** (real bugs) |
| **Total** | 7 errors, 9 passed | 2 failed, 14 passed |

The 2 FAILUREs were **existing test logic bugs** — they had been hidden behind
the setup-phase PermissionError for weeks. Fix them; do not attribute them to the
`--basetemp` switch.

## Concrete Example (2026-07-15)

Two tests in `tests/test_run_all_factors.py` referenced a bare `results[name]`
where `results` was a class attribute (`Registry.results`), not a local variable:

```python
class Registry:
    names = (...)
    results = {...}

# Bug: lambda references bare `results` instead of `Registry.results`
monkeypatch.setattr(
    factor_runner, "_run_factor",
    lambda name, _date_stamp, _timeout, _failure_codes: results[name],
)
```

Fix: `Registry.results[name]`.

The second test also needed `intraday_range` added to `Registry.names` because
`REQUIRED_CORE_FACTORS` includes it; omitting it from the mock caused a
`REQUIRED_CORE_FACTOR_FAILED` error once the NameError was fixed.

## Cleanup

```bash
rm -rf d:/tmp/pytest-basetemp
```

## Root Cause

The stale-lock PermissionError on `C:\Users\bgonn\AppData\Local\Temp\pytest-of-bgonn`
persisted because Windows does not release the lock when pytest crashes (e.g. from
a Hermes agent timeout mid-test). The `rmdir /s /q` command also fails with
"Access is denied" because the lock is held by the OS. The `--basetemp` switch
instructs pytest to use a different root directory, bypassing the lock entirely.

## Prevention

- Always run `--basetemp` with a repo-local directory when the default Windows
  temp root is inaccessible.
- Document test results as "N passed, M failed (with `--basetemp`)" when the
  PermissionError is present, not as "N passed, M errors" which conflates
  environment failures with test outcomes.
- Consider adding `--basetemp=d:/tmp/pytest-basetemp` as a Makefile/Justfile
  target or pytest.ini override on Windows development machines.