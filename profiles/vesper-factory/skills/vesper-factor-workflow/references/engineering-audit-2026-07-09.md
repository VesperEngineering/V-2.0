# Vesper Engineering Audit — July 2026

Comprehensive codebase audit findings. Run this audit pattern when reviewing Vesper's engineering health.

## Audit Methodology

1. **Project overview** — README, ARCHITECTURE.md, AGENTS.md
2. **Structure** — File counts per directory, LOC totals per module
3. **Test suite** — `pytest tests/ -q --tb=no` for pass/fail/skip count
4. **Cross-reference skills/docs vs code** — Check for discrepancies between stated best practices and actual code (e.g. "kill dilutive factors" in STATUS.md but orphan factor files still on disk)
5. **Dead code scan** — Scripts not referenced in jobs.json, orphan .py files not in registry, v1/v2/v3 iterations of same tool
6. **Hardcoded path scan** — `grep -rn "D:/vesper\|C:/Users" app/ scheduler/ scripts/` in .py files
7. **Config & dependency audit** — pyproject.toml, requirements*.txt, .env.example, .pre-commit-config.yaml
8. **Scheduler design** — jobs.json entries, timeout settings, market-hours guard, log retention
9. **Security check** — SQL injection patterns (`.format()` on SQL), credential exposure in processes, dashboard auth

## Current Findings (July 2026)

### Path Portability (Fix: parameterize via VESPER_ROOT)
- `scheduler/__init__.py:206` — `PYTHONPATH: "D:/vesper;D:/vesper/deploy"`
- `vesper-dashboard/server.py:18-23` — `VESPER_ROOT = Path("D:/vesper")` + 5 hardcoded script paths
- `vesper-dashboard/aggregator.py:21-23` — `sys.path.insert(0, "D:/vesper")`

### Dead Factor Files (6 orphans, not in registry)
`amihud.py`, `beta_factor.py`, `size_factor.py`, `massive_fund.py`, `trends.py`, `whale.py` — 1,080+ lines of code that will never run. Delete them.

### Zero-Weight Factors Still Computed (4 in registry at 0.0)
`sp500_technical`, `massive`, `insider`, `sentiment` — registered in `registry.py` and computed daily by `run_all_factors.py` but weighted 0.0 in the blend. They pollute compute time for zero effect. Remove from registry.py.

### Dead Scripts Bloat (29 scripts, ~10K lines)
- 17 `no_order_checkpoint_*` / `post_rebuild_*` scripts from a completed rebuild event
- 12 `generate_no_order_*` / `generate_post_rebuild_*` scripts
None referenced in `scheduler/jobs.json`. Archive or delete.

### Evolutionary Artifacts (7 scripts, 1,641 lines)
- `signal_mine.py` v1-v4 (983 lines) — only v4 is current
- `vesper_backtest.py` v1-v3 (658 lines) — only v3 is current
Keep only latest, archive the rest.

### SQL Injection Risk
`app/factors/intraday_range.py:48` and `app/factors/mean_reversion.py:51` use `.format()` to inject date lists into SQL. While current data (trusted date strings) makes exploitation unlikely, this pattern is a landmine. `market_micro.py` shows the correct pattern with `?` placeholders.

### Services Bloat (359 files, 178K lines)
254 of 359 service files are massive_*, qlib_*, or tree_ranker_* research-evidence modules — most are historical one-shots. Consider a `services/_archive/` directory for non-live services.

### Scheduler Log Retention
`scheduler/logs/scheduler.log` grows unboundedly. No max-size or retention policy. Add rotation or periodic cleanup.

### Dashboard Security
`vesper-dashboard/server.py` listens on `0.0.0.0:8080` with `SimpleHTTPRequestHandler`. No authentication. `/api/run-pipeline` and `/api/rebalance` are exposed. Alpaca credentials cached in process memory for the server's lifetime.

### Test Coverage Gap
252 tests pass of 255 total. Covers contract/gate/logic services well but most factor implementations have zero direct tests. A factor regression test would catch data-source schema changes.

### Config Fragmentation
Dependencies split across `deploy/requirements.txt`, `deploy/requirements_full.txt`, `deploy/requirements_qlib.txt`. `pyproject.toml` has no `[project]` section — no name, version, or metadata. Consolidate into pyproject.toml.

## Recommended Fixes (Priority Order)

| Priority | Fix | Effort |
|----------|-----|--------|
| P0 | Delete 6 orphan factor files | 5 min |
| P0 | Remove 4 zero-weight factors from registry.py | 10 min |
| P1 | Parameterize D:/vesper via VESPER_ROOT env var | 30 min |
| P1 | Archive 29 dead rebuild scripts | 15 min |
| P1 | Archive 7 evolutionary artifacts (keep latest) | 5 min |
| P2 | Convert SQL `.format()` to parameterized queries in intraday_range & mean_reversion | 10 min |
| P2 | Add scheduler log rotation | 15 min |
| P3 | Consolidate dependencies into pyproject.toml | 30 min |
| P3 | Move historical research services to `_archive/` | 20 min |
| P4 | Add auth to dashboard server or bind to 127.0.0.1 | 15 min |
