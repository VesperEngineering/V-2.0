# Windows Pytest and CI-Contract Drift

Use this reference when a governed Windows repository has pytest setup failures or a local CI validator disagrees with the active workflow.

## Reproduction pattern

1. Capture the exact failing command and whether failure occurs during collection, fixture setup, test execution, or teardown.
2. Inspect `pytest.ini`/`pyproject.toml` for a forced `--basetemp` path. A path under `artifacts/` is unsafe because pytest cleanup can collide with generated evidence, stale ACLs, or another process.
3. Rerun only the affected tests with a unique external path, for example:

```text
python -m pytest tests/test_slice.py -q --basetemp="C:/Users/<user>/AppData/Local/Temp/<repo>-pytest-slice"
```

4. If the external run passes, separate the machine/temp-root blocker from code behavior. Do not repair ACLs or delete shared directories automatically.

## Correct repository repair

- Remove a global artifact-owned basetemp override from local pytest configuration.
- Leave CI's explicit external `/tmp/...` basetemp intact.
- Re-run focused tests with an external basetemp and record the default-root permission issue separately if it remains.

## Validator/workflow reconciliation

Read the active workflow before changing `REQUIRED_WORKFLOW_SNIPPETS`. Retired Node/React/cockpit commands must not remain mandatory after a terminal-only migration. Remove only stale requirements. Keep stable command prefixes rather than requiring optional package suffixes, so older valid fixtures remain accepted.

## Evidence standard

Report separately:

- focused repaired slices;
- compilation and diff checks;
- full-suite pass/skip/fail counts;
- nonzero exit or terminal-control failures;
- pre-existing validator/workflow drift;
- environment-only temp/ACL failures.

A focused green slice is not a green full suite.