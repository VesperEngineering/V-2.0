# Factor Maintenance Hygiene

## Registry is truth, not the filesystem.

Files in `app/factors/` that aren't registered in `registry.py` are dead code — delete them. Factors registered but weight 0.0 are dead weight — remove from registry and delete the source. Fama-MacBeth is the gold standard: |t| < 1.5 = kill immediately. Don't leave at weight 0.0 "for research."

## Removing a dead factor (full checklist)

1. Confirm weight is 0.0 in `scripts/run_all_factors.py` `FACTOR_WEIGHTS` dict.
2. Check for external imports: `grep -rn "from app.factors.<name>" app/ scripts/ vesper-dashboard/`
3. Remove from `registry.py`: delete the import line and the `register_all()` entry.
4. Remove from `run_all_factors.py`: delete FACTOR_TIMEOUTS and FACTOR_WEIGHTS entries.
5. Delete source: `git rm app/factors/<name>.py`
6. Delete any dependent scripts that import it, if unused by scheduler (`scheduler/jobs.json`).
7. Run `pytest -q` — expect same pass count, zero regressions.
8. Update `docs/STATUS.md`.

## Shared DB helper (`app/factors/db.py`)

All OHLCV-sourced factors should use `db.py` instead of duplicating SQLite patterns.
Provided functions:
- `open_ohlcv_db(path)` — Row factory, read-only URI mode
- `fetch_recent_dates(conn, table, limit)` — parameterized date fetch
- `fetch_ohlcv_rows(conn, date_list, table, columns, extras)` — parameterized OHLCV fetch
- `build_ohlcv_panel(rows, universe, close_col)` — per-ticker close-price panel

All queries use `?` placeholders. Never `.format()` on SQL strings. If a factor opens SQLite directly with manual `conn.row_factory` setup, refactor it.

## Engineering audit patterns

When auditing Vesper for dead code/quality:
1. Find orphan files: `ls app/factors/*.py | while read f; do name=$(basename $f .py); grep -q "$name" app/factors/registry.py || echo "NOT IN registry: $name"; done`
2. Find 0.0-weight factors: grep `"<name>": 0.0` in `scripts/run_all_factors.py`
3. Find hardcoded paths: `grep -rn "D:/vesper" app/ scheduler/ vesper-dashboard/`
4. Find unreferenced scripts: cross-reference `scheduler/jobs.json` script names against `scripts/` directory
5. Find duplicate imports: `grep -rn "from app.factors.<old_name> import"` before deleting a factor

## July 2026 cleanup record

Removed (48 files): 6 orphan factors, 4 dead factors (sp500_technical, massive, insider, sentiment), 29 rebuild scripts, 7 evolutionary dead-ends (signal_mine v1-4, backtest v1-3), 2 dead scripts. Registry: 13→9 factors. Extracted shared `db.py`. Parameterized 3 hardcoded D:/vesper paths. Added scheduler log rotation.
