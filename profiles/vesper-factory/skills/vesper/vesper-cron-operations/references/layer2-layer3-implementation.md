# Layer 2 + Layer 3 Implementation — July 17 2026

## Layer 2: Operator surface

### CrossSystemStatus service

`app/services/cross_system_status.py` — aggregates Layer 1 cron artifacts into one read-only status object.

**Design decisions:**

1. **Fact-base JSON overrides markdown** — same pattern as NoSubmitGuard. If the health watchdog wrote a degraded status, that overrides the EOD receipt's healthy status.
2. **Stale threshold = 48h** — a PASS receipt older than 48 hours is "stale", not "healthy". This catches a system that stopped running.
3. **Missing artifacts = "down"** — no receipt file at all means the system hasn't run. Fail-closed.
4. **Alerts counted by file** — each alert JSON in `artifacts/cron/alerts/` (not in `dispatched/` subdir) increments the count.
5. **needs_brennan is a list, not a bool** — each item is a specific actionable string ("Pipeline BLOCKED — check safety guard", "2 alert(s) in queue", etc.).

### Operator terminal integration

The `cross-system` command was added with minimal changes to existing files:

- `app/operator_terminal_render.py`: new `render_cross_system()` function + import of `CrossSystemStatus` + HELP_TEXT entry
- `app/operator_terminal.py`: new `if command == "cross-system":` block with lazy imports (avoids circular import risk)

**Color coding:**
- green: healthy
- dim green: idle
- yellow: stale, degraded, held
- red: blocked, down
- dim: unknown

### Tests

13 tests in `tests/test_cross_system_status.py`:
- Uses `tmp_path` to create isolated artifact directories
- Helper functions `_write_receipt()` and `_write_health()` create test fixtures
- Covers: no artifacts, healthy, stale, blocked, failed research, alerts, health override, active batch, held, evidence links

Total test count after Layer 2: 80 (67 from Layer 0 + 13 new).

## Layer 3: Triggers and alerts

### Research→Kanban bridge

`scripts/research_to_kanban_bridge.py`

**Key design decisions:**

1. **Processed tracking via text file** — `artifacts/cron/processed/research_artifacts.txt` is a simple append-only list of WSL2 paths. No database needed. Each run loads the set, filters out processed, processes new ones, appends.
2. **Invalid artifacts are marked processed** — prevents infinite retry of a malformed artifact. The validation failure is in the receipt.
3. **Idempotency key** — `research-bridge-{commit}-{name}` prevents duplicate Kanban cards if the same artifact is somehow processed twice.
4. **Kanban card assigned to vesper-thomas** — Thomas does strategy review first, then Clarke plans, then Riley independently reviews.
5. **WSL2 file listing** — `wsl bash -lc 'ls ~/vesper-ranker/artifacts/evals/candidate_factor_*.json 2>/dev/null'` — the `2>/dev/null` suppresses errors when no files match the glob.

**Required artifact fields (13):**
hypothesis, economic_rationale, source_commit, dataset_version, backtest_results, walk_forward_results, transaction_cost_assumptions, stability_analysis, drawdown_analysis, correlation_analysis, known_failure_modes, compute_cost, reproducibility_instructions

### Alert dispatcher

`scripts/cron_alert_dispatcher.py`

**Key design decisions:**

1. **Only immediate severity dispatched** — `DISPATCH_SEVERITIES = frozenset({"immediate"})`. Routine success chatter is suppressed.
2. **Alerts moved to dispatched/ after processing** — `shutil.move()` to `artifacts/cron/alerts/dispatched/`. Prevents re-delivery on next run.
3. **Failed dispatches also moved** — prevents infinite retry. The failure is recorded in the receipt. A failed Telegram send doesn't loop forever.
4. **hermes send -t telegram** — uses the gateway's home channel. No LLM, no agent loop. Just `subprocess.run(["hermes", "send", message, "-t", "telegram"])`.
5. **Message format** — `🚨 VESPER ALERT\n{name}\nSeverity: {severity}\nDetail: {detail}\nTime: {ts}`. Detail truncated at 500 chars.

### Live verification

```
research_to_kanban_bridge.py → PASS ("No new candidate artifacts")
cron_alert_dispatcher.py → PASS ("No alerts directory — nothing to do")
```

### Final test count

80 tests (67 Layer 0 + 13 Layer 2). Layer 3 scripts are cron wrappers with no new testable services — they compose existing Layer 0 services.

```
pytest: 80 passed in 2.12s
ruff (F,E9): All checks passed
py_compile: OK
```
