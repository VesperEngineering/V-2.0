# Lane Idempotency Gates

The Vesper steward selects one lane per 15-min cycle — the highest-priority unblocked lane. The steward has no output-change tracking: it does not know whether a lane's work has already been done for the current data state. This means individual lane checks must implement idempotency gates to prevent re-running the same work and monopolizing the single action slot.

## Architecture

```
steward cycle → check all lanes by priority → pick first unblocked → execute action
```

A lane is "unblocked" when its `check` command exits with code 0. The steward only checks **blocked/unblocked** — it does not track "already done for this data."

## Gate Types

### 1. ALREADY_SCORED Gate (Pipeline Lane)

**Problem:** The pipeline lane check only tested OHLCV freshness (`resolve_signal_date()`). Once fresh data arrived, the pipeline ran every 15 minutes on the same data, consuming the single action slot and starving all other lanes.

**Fix:** Added a check for whether the score artifact already exists for the current OHLCV max date:

```python
# Single-line version (required on Windows — see pitfall below)
python -c "from scripts.run_all_factors import resolve_signal_date, OHLCV_DB, xnys_today; from pathlib import Path; import sqlite3, sys; resolve_signal_date(OHLCV_DB, xnys_today()); max_date = sqlite3.connect(str(OHLCV_DB)).execute('SELECT MAX(date) FROM sp500_ohlcv').fetchone()[0].replace('-', ''); score_path = Path('data') / f'factor_scores_{max_date}.json'; sys.stderr.write(f'ALREADY_SCORED: {max_date}\\n'); sys.exit(1) if score_path.exists() else print('FRESH')"
```

**Logic:**
1. Verify OHLCV freshness (existing `resolve_signal_date()` call — fails if data is stale)
2. Query the OHLCV DB max date
3. Check if `data/factor_scores_{OHLCVmax}.json` exists
4. If it exists → print "ALREADY_SCORED" to stderr, exit 1 (blocked)
5. If it doesn't exist → print "FRESH" to stdout, exit 0 (unblocked → run pipeline)

### 2. ALREADY_RECORDED Gate (Telemetry Lane)

**Problem:** The telemetry lane check already had a recency gate (scores must be <=3 days old). But once fresh scores existed, the telemetry check passed every cycle, and telemetry re-ran every 15 minutes writing the same report.

**Fix:** Added a check for whether today's telemetry receipt already exists:

```python
# Added to the existing telemetry check:
today = date.today().strftime('%Y%m%d')
tel_path = Path('artifacts/evals') / f'paper_telemetry_baseline_{today}.md'
assert not tel_path.exists(), f'telemetry already recorded for {today}'
```

**Logic:**
1. Check score recency (existing gate — fails if scores are stale)
2. Check if `artifacts/evals/paper_telemetry_baseline_{today}.md` exists
3. If it exists → assert fails (blocked)
4. If it doesn't exist → run telemetry

## Critical Windows Pitfall: `\n` in Python `-c` Strings

**Do not use `\n` (newline escape) inside Python `-c` strings passed through `subprocess.run(shell=True)` on Windows.** cmd.exe does not interpret `\n` inside double-quoted strings. The escape sequence is passed literally as backslash + 'n', causing Python syntax errors.

### Wrong (multi-line in -c string):
```json
"check": "python -c \"from foo import bar\\nfrom pathlib import Path\\nbar()\""
```
Result: `SyntaxError: invalid syntax` — `\n` is literal, not a newline.

### Correct (single line with semicolons):
```json
"check": "python -c \"from foo import bar; from pathlib import Path; bar()\""
```

### Why this matters for JSON:
In JSON, `\\n` decodes to `\n` (backslash + n). When this is passed to the shell, the `-c` argument contains literal `\n` characters, not newlines. On Linux/macOS, the shell interprets `\n` as a newline. On Windows cmd.exe, it does not. The original single-line pipeline check worked because it used semicolons:

```python
# Works on Windows:
from scripts.run_all_factors import resolve_signal_date, OHLCV_DB, xnys_today; resolve_signal_date(OHLCV_DB, xnys_today()); print('FRESH')
```

### Verification:
Test the lane check command directly in a terminal before writing it to lanes.json:
```bash
cd D:/vesper
python -c "from scripts.run_all_factors import resolve_signal_date, OHLCV_DB, xnys_today; from pathlib import Path; import sqlite3, sys; resolve_signal_date(OHLCV_DB, xnys_today()); max_date = sqlite3.connect(str(OHLCV_DB)).execute('SELECT MAX(date) FROM sp500_ohlcv').fetchone()[0].replace('-', ''); score_path = Path('data') / f'factor_scores_{max_date}.json'; sys.exit(1) if score_path.exists() else print('FRESH')"
echo "exit=$?"
```

Verify the steward picks it up correctly:
```bash
python .hermes/steward.py
tail -3 .hermes/steward_log.jsonl
```

## Related Patterns

### Output-change tracking (future steward improvement)
The current steward (`.hermes/steward.py`) has no mechanism to track whether a lane's output has changed since last run. To implement this:
- Add a `last_output_hash` or `last_data_state` field to `steward_state.json`
- Compare against the current state in `pick_lane()`
- Skip lanes whose output hasn't changed

### Manual rotation (current workaround)
Until the steward has output-change tracking, the agent must:
1. Detect repetitive delegations from the same stale state
2. Manually rotate through governance, research, and code_health lanes
3. Log the rotation decision in team_memory.json and learnings.jsonl