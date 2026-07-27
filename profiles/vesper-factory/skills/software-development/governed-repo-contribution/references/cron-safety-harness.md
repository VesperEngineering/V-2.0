# Cron Safety Harness for Governed Unattended Execution

Pattern from Vesper Layer 0 preflight (2026-07-17). Applies when moving any
governed, fail-closed, manually-operated system to cron-scheduled operation.

## Why a preflight layer

Cron is the largest leverage point but also the largest risk: an unattended
job that silently widens execution authority, overlaps with a manual run, or
fails without anyone noticing is worse than no cron at all. Layer 0 proves
the safety harness works end-to-end *before* any real cron job is wired.

## The five components

### 1. CronTaskEnvelope (frozen dataclass)

Every cron job must construct this before doing any work:

```python
@dataclass(frozen=True)
class CronTaskEnvelope:
    job_id: str               # "vesper-daily-eod"
    scheduled_time: datetime
    authority_class: str      # "no_submit_evidence" | "research_batch" | "watchdog"
    allowed_tools: tuple[str, ...]
    required_evidence: str    # path or schema reference
    stop_condition: str
    run_lock_path: str
    receipt_path: str
```

- Validates `authority_class` against a frozen set
- Serializes to/from JSON (datetime as ISO, tuple as list)
- Writes to `artifacts/cron/envelopes/<job_id>.json`

### 2. RunLock (file-based, cross-process)

Uses `os.O_CREAT | os.O_EXCL` for atomic creation. Works on Windows + POSIX.

- `acquire()` returns `True`/`False` (non-blocking when timeout_s=0)
- Lock file contains JSON: `{"pid": ..., "acquired_at": "<iso>"}`
- Stale lock detection: if age > `stale_after_s`, forcibly break and retry
- Context manager releases on exception
- Second acquire on same path returns False, not hang

### 3. NoSubmitGuard

Reads board state from two sources and merges:

- `PROJECT_ADVANCEMENT.md` — regex extraction of `Execution allowed`, `Execution authority interpretation`, `Paper execution scope`, `Paper execution window`
- `docs/VESPER_FACT_BASE.json` — structured `board` object (overrides markdown)

Validation rules (all must pass):
- `execution_interpretation` must be `bounded_paper_order_evidence_only`
- `paper_execution_scope` must be `paper_only`
- Missing/malformed files → fail-closed (raise SafetyViolation)

Writes assertion file: `artifacts/cron/assertions/<job_id>_no_submit.json`

### 4. CronReceipt (frozen dataclass)

```python
@dataclass(frozen=True)
class CronReceipt:
    job_id: str
    started_at: datetime
    finished_at: datetime
    status: str               # "PASS" | "FAIL" | "HELD" | "BLOCKED"
    evidence_path: str | None
    error: str | None
    metrics: dict
```

Invariant rules:
- PASS requires `evidence_path` and rejects `error`
- FAIL requires `error`
- `started_at` must precede `finished_at`
- `status` must be in the frozen set

### 5. Dry-run harness (`scripts/cron_dry_run.py`)

Chains: envelope → lock → guard → (simulate work) → receipt → release lock.

Tests three paths:
- **Happy path**: all steps pass, PASS receipt, lock released
- **Lock conflict**: stale/fresh lock present → HELD receipt, exit 1
- **Safety violation**: guard raises → BLOCKED receipt, exit 1

## Layer progression

| Layer | Deliverable | Exit condition |
|-------|------------|----------------|
| 0 | Envelope, lock, guard, receipt, dry-run harness | Manual dry run produces receipt, proves locks, proves safety mode, shows failure path |
| 1 | Cron wiring: EOD loop, research batch, watchdogs | Jobs execute on schedule, never overlap, create owned incidents |
| 2 | Unified operator surface (read-only cross-system status) | One glance shows freshness, work, health, "Needs Brennan" |
| 3 | Cross-system triggers + gateway alerts | Candidate has reproducible handoff, urgent failures reach channel |
| 4 | Guarded continuity: safe retries, longitudinal evidence, monthly review | Retries safe, promotion stays explicitly approved, no autonomous live leap |

## Key design decisions

- **No-submit guard only runs for `no_submit_evidence` jobs** — watchdog and research_batch jobs skip it (they have different authority boundaries)
- **Receipts are the source of truth for "did it run"** — not logs, not exit codes alone
- **Run locks prevent overlap** — a second cron tick while the first is still running gets HELD, not queued
- **Stale locks are broken automatically** — configurable max age (default 1h) prevents a crashed job from blocking forever
- **All artifacts go under `artifacts/cron/`** with subdirs: `envelopes/`, `locks/`, `receipts/`, `assertions/`, `status/`, `alerts/`

## Proving a natural one-shot execution

A manual invocation proves the wrapper but not scheduler ownership. A one-shot job disappearing from the active list is also insufficient: it may have been removed after success, failure, or administrative cleanup.

For a scheduler-owned proof, bind and retain all of:

1. the exact one-shot job ID, schedule, script hash, and source revision before the due time;
2. the scheduler execution-registry row (job ID, process/PID identity, claimed/started/finished timestamps, terminal status, and error);
3. the scheduler-owned output file/log for that execution;
4. the generated run directory and validated receipt with the exact source, schedule identity, bounded runtime/cost/retries, and denied authority;
5. post-run evidence that the one-shot job is absent or disabled and that no second proof schedule remains enabled.

Use the scheduler's execution registry and output directory as control-plane provenance, and the receipt as domain-result provenance. Require both. Do not substitute `cronjob run` or direct script execution for the natural due-time tick.

## Layer 1 — Cron wiring (verified implementation)

After Layer 0 dry-run passes, wire actual cron jobs. Each job script wraps the
existing repo entry point inside the Layer 0 safety harness.

### Job scripts

Each `scripts/cron_<job>.py` follows the same structure:
1. Build envelope (authority_class from JOB_CONFIGS)
2. Acquire RunLock (non-blocking, stale_after_s varies by job)
3. For `no_submit_evidence` jobs: run NoSubmitGuard.assert_safe()
4. Execute real work via `subprocess.run()` with timeout
5. Write CronReceipt (PASS/FAIL/HELD based on subprocess exit code)
6. Release lock
7. Print summary

### Hermes cronjob wiring

The `cronjob` tool requires scripts under `~/.hermes/scripts/`. Create thin
`.sh` wrappers that `cd` to the repo and `exec` the Python script:

```bash
#!/bin/bash
cd /d/vesper
exec /d/vesper/.venv/Scripts/python.exe /d/vesper/scripts/cron_vesper_eod.py
```

Then create jobs with `no_agent=True` (pure script execution, no LLM needed):

```
cronjob(action='create', name='Vesper Daily EOD Loop',
        schedule='0 17 * * 1-5', script='vesper_daily_eod.sh',
        no_agent=True, deliver='local')
```

### Schedule reference

| Job | Schedule | Authority | Script |
|-----|----------|-----------|--------|
| Vesper Daily EOD | `0 17 * * 1-5` | no_submit_evidence | cron_vesper_eod.py |
| Research Batch | `*/30 * * * *` | research_batch | cron_research_batch.py |
| Health Watchdog | `*/30 * * * *` | watchdog | cron_health_watchdog.py |
| Disk/VRAM Watchdog | `0 * * * *` | watchdog | cron_disk_vram_watchdog.py |

### Research batch WSL2 bridging

The research batch script runs on Windows but shells into WSL2 to read the
experiment queue and execute batches:
- `_wsl(cmd)` helper: `subprocess.run(["wsl", "bash", "-lc", cmd])`
- Queue manifest at `~/vesper-ranker/experiment_queue.json`
- No manifest → PASS receipt with `action: "no_queue"`, exit 0
- Pending item found → lease one, run `.venv/bin/python <script>`, write receipt

## Layer 2 — Unified operator surface

### CrossSystemStatus aggregator

`app/services/cross_system_status.py` reads Layer 1 artifacts and produces a
read-only status object with Pipeline + Research health:

- `load_cross_system_status(repo_root)` returns a `CrossSystemStatus` with:
  - `pipeline_health`: healthy/stale/held/blocked/down/unknown
  - `research_health`: healthy/idle/degraded/down/unknown
  - `alerts_count`: count of files in `artifacts/cron/alerts/`
  - `needs_brennan`: list of actionable items
  - `overall`: healthy/attention/degraded/unknown

Stale detection: receipt age > 48h → "stale". Missing receipt → "down".

### Operator terminal integration

Add a `cross-system` command to the existing Prompt Toolkit terminal:
1. Add `render_cross_system(console, status)` to the render module
2. Add `"cross-system"` to HELP_TEXT
3. Wire command handler: `load_cross_system_status(self.root)` → render

The panel shows a Rich Table with System/Health/Freshness/Current Work/State
rows, plus overall status and "Needs Brennan" items. Read-only — no execution
controls.

### Test pattern

```python
def _write_receipt(repo, name, status, finished_at, metrics=None):
    # Write a JSON receipt to artifacts/cron/receipts/<name>.json
    ...

def test_healthy_pipeline_and_research(tmp_path):
    now = datetime.now(UTC).isoformat()
    _write_receipt(tmp_path, "vesper-daily-eod", "PASS", now, {"date": "20260717"})
    _write_receipt(tmp_path, "research-batch", "PASS", now, {"action": "no_pending"})
    s = load_cross_system_status(tmp_path)
    assert s.pipeline_health == "healthy"
    assert s.research_health == "idle"
    assert s.overall == "healthy"
```

## Test commands

```bash
# Run all Layer 0 + Layer 2 tests
.venv/Scripts/python.exe -m pytest tests/test_cron_task_envelope.py tests/test_run_lock.py tests/test_no_submit_guard.py tests/test_cron_receipt.py tests/test_cross_system_status.py -v --basetemp=.pytest_tmp

# Run dry-run harness
.venv/Scripts/python.exe scripts/cron_dry_run.py --job vesper-daily-eod

# Test cross-system command in operator terminal
.venv/Scripts/python.exe -m app.operator_terminal --command "cross-system"

# Lint (repo baseline: F + E9 only)
.venv/Scripts/python.exe -m ruff check --select F,E9 app/services/cron_*.py app/services/run_lock.py app/services/no_submit_guard.py app/services/cross_system_status.py scripts/cron_*.py
```
