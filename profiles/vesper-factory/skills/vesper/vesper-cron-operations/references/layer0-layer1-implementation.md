# Layer 0 + Layer 1 Implementation — July 17 2026

## What was built

### Layer 0: Safety harness (preflight)

Four services under `app/services/`:

| File | Purpose | Tests |
|------|---------|-------|
| `cron_task_envelope.py` | Frozen dataclass, JSON serialization, authority class validation | 20 |
| `run_lock.py` | Cross-process file lock, stale detection, context manager | 12 |
| `no_submit_guard.py` | Board state reader, execution flag assertion, fail-closed | 11 |
| `cron_receipt.py` | Receipt writer/reader, status validation, evidence/error rules | 24 |

Total: **67 tests**, all passing.

Dry-run harness: `scripts/cron_dry_run.py` — ties all four together, tested live with:
- `vesper-daily-eod` → PASS (envelope, lock, assertion, receipt all written)
- `health-watchdog` → PASS (skips no-submit guard)
- `research-batch` → PASS (skips no-submit guard)
- Lock conflict → HELD receipt, exit 1

### Layer 1: Cron scripts

Four scripts under `scripts/`:

| Script | What it wraps | Live result |
|--------|--------------|-------------|
| `cron_vesper_eod.py` | `run_daily_paper_evidence_loop.py --no-submit` | Compiled, linted |
| `cron_research_batch.py` | WSL2 `~/vesper-ranker` experiment queue | PASS (no queue manifest) |
| `cron_health_watchdog.py` | EOD receipt + research receipt + data freshness | PASS (healthy) |
| `cron_disk_vram_watchdog.py` | `shutil.disk_usage` + `nvidia-smi` | PASS (454 GB disk, 14 GB VRAM) |

Four cron jobs wired via `cronjob` tool (`no_agent=True`, `deliver=local`):
- `77952eba1975` — Vesper Daily EOD Loop (`0 17 * * 1-5`)
- `b4cb6acce346` — Research Batch Advance (`*/30 * * * *`)
- `a1b08e550d56` — Pipeline Health Watchdog (`*/30 * * * *`)
- `d15d952f5b5a` — Disk/VRAM Watchdog (`0 * * * *`)

Shell wrappers at `~/.hermes/scripts/vesper_*.sh`.

## Verification

```
pytest: 67 passed in 1.78s
ruff (F,E9): All checks passed
py_compile: OK (all 9 files)
```

## Key design decisions

1. **Envelope before lock before guard before work** — the order is mandatory. If the envelope can't be built, nothing else runs.
2. **NoSubmitGuard reads both PROJECT_ADVANCEMENT.md and VESPER_FACT_BASE.json** — the fact base JSON overrides the markdown if both are present. This prevents a stale markdown file from masking a board state change.
3. **RunLock uses O_EXCL, not fcntl/msvcrt** — cross-platform without conditional imports. Slightly less robust than fcntl on POSIX but works identically on Windows and WSL2.
4. **CronReceipt validates semantic consistency** — PASS without evidence is rejected, PASS with error is rejected, FAIL without error is rejected. This prevents misleading receipts.
5. **Watchdog jobs skip the no-submit guard** — they don't touch execution paths, so the guard is unnecessary and would block if the board state changed.
6. **Research batch script handles "nothing to do" as PASS** — no queue manifest or no pending items is a successful check, not a failure.
7. **All deliver=local** — in the TUI session, cron output is saved but not delivered live. Gateway delivery is deferred to Layer 3.
