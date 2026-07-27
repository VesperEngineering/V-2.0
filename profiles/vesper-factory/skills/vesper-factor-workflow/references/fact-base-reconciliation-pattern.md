# VESPER_FACT_BASE.json Reconciliation Pattern

When a governance audit (by Riley or Clarke) finds documentation drift in `docs/VESPER_FACT_BASE.json`, the fix is a direct JSON patch followed by validation.

## Typical findings

1. **Stale status** — an issue's status in `VESPER_FACT_BASE.json` differs from `docs/ISSUES.md`. The ISSUES.md is authoritative for individual issue status.
2. **Missing issues** — issues recorded in `docs/ISSUES.md` but absent from the `open_issues` block in `VESPER_FACT_BASE.json`.
3. **Stale `local_ohlcv_date`** — the `board.local_ohlcv_date` field disagrees with the actual SQLite database `MAX(date)`.

## Fix procedure

### 1. Read the authoritative sources

```bash
# Current ISSUES.md statuses
grep -A5 "^## VQ-YYYYMMDD-NNN " docs/ISSUES.md | grep "Status:"

# Current DB max date
python -c "
import sqlite3
conn = sqlite3.connect('vesper_data/massive/sp500/sp500_ohlcv.sqlite')
print(conn.execute('SELECT MAX(date) FROM sp500_ohlcv').fetchone()[0])
conn.close()
"
```

### 2. Patch VESPER_FACT_BASE.json

Use the `patch` tool on the `open_issues` block. Add missing issues in order and update stale statuses. The `board.local_ohlcv_date` field can also be patched similarly.

### 3. Verify JSON validity

```bash
python -c "import json; json.load(open('docs/VESPER_FACT_BASE.json')); print('JSON valid')"
```

### 4. Run documentation freshness validator

```bash
python scripts/validate_documentation_freshness.py --root .
```

Expected: `DOCUMENTATION FRESHNESS PASS as_of=YYYY-MM-DD findings=0`

### 5. Re-run relevant tests

```bash
python -m pytest tests/test_documentation_freshness.py -q --tb=short --basetemp=/tmp/vesper_pytest_docfix
```

Note: the default pytest basetemp may fail with `PermissionError` (VQ-20260714-012). Use `--basetemp` pointing to a writable location.

## Other sources of truth to check

When fixing `local_ohlcv_date`, update ALL three:
- `docs/PROJECT_ADVANCEMENT.md`
- `docs/VESPER_FACT_BASE.json` (`board.local_ohlcv_date`)
- `docs/STATUS.md`

The validator checks `VESPER_FACT_BASE.json` against the other two. The three must agree.

## Reference

- Session 2026-07-14 cycle 29: fixed VQ-20260714-003 status + added 6 missing issues (VQ-20260714-007 through -014)
- `docs/ISSUES.md` is authoritative for issue status; `VESPER_FACT_BASE.json` is the shared fact base for audience-facing documents