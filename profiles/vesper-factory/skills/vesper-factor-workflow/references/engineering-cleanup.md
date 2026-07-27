# Vesper Engineering Cleanup Checklist

Routine maintenance patterns for keeping the Vesper codebase lean.

## Dead Factor Identification

1. **Check registry.py** for all registered factors vs `app/factors/*.py` on disk
2. **Files on disk but NOT in registry** → delete immediately (orphans)
3. **Factors in registry with weight 0.0 in `run_all_factors.py`** → remove from registry AND delete source file
4. **FM-validated dead factors** (|t| < 1.5) → remove from registry per STATUS.md kill rule

## Dead Script Identification

1. **`scripts/generate_*` and `scripts/validate_*` not referenced from `scheduler/jobs.json`** → archive/delete
2. **Evolutionary dead-ends** (e.g., `signal_mine_v1.py` through `signal_mine_v3.py` when v4 exists) → delete all but current
3. **Rebuild artifacts** (no_order_checkpoint, post_rebuild patterns) → delete once rebuild is complete

## Nova→Vesper Rename Checklist

When renaming `deploy/nova.py` → `deploy/vesper.py`:

1. `git mv deploy/nova.py deploy/vesper.py`
2. `git mv nova.cmd vesper.cmd` / `nova.ps1 vesper.ps1`
3. Update launcher scripts internally (env vars, paths, error messages)
4. Grep-and-replace `deploy/nova.py` → `deploy/vesper.py` across all files:
   - `app/services/*.py` (15+ files typically)
   - `scripts/*.py`
   - `deploy/cli/data.py`
   - `tests/*.py` (any test that subprocess-calls the CLI)
5. Verify: `grep -rn "deploy/nova\.py" app/ scripts/ tests/` returns zero hits
6. Run full pytest suite

## Hardcoded Path Parameterization

Replace hardcoded `D:/vesper` with `VESPER_ROOT` env var + fallback:

```python
VESPER_ROOT = Path(os.environ.get("VESPER_ROOT", Path(__file__).resolve().parent.parent))
```

Locations to check:
- `scheduler/__init__.py` — PYTHONPATH in Job.run()
- `vesper-dashboard/server.py` — VESPER_ROOT + script paths
- `vesper-dashboard/aggregator.py` — VESPER_ROOT + sys.path

## Shared DB Helper Pattern

When 2+ factors share identical SQLite connection/query patterns, extract to `app/factors/db.py`:

```python
# app/factors/db.py
def open_ohlcv_db(db_path): ...     # uri=True, row_factory
def fetch_recent_dates(conn, ...):  # parameterized
def fetch_ohlcv_rows(conn, ...):    # parameterized, no .format()
def build_ohlcv_panel(rows, ...):   # {ticker: [prices]}
```

## Scheduler Log Hygiene

- Scheduler log: use `RotatingFileHandler` (5MB, 3 backups)
- Per-job logs: cap at 100 latest per job, clean on startup
- Cleanup function should be best-effort (never crash the scheduler)
