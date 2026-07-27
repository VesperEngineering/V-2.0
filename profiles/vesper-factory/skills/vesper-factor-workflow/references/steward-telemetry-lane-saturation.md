# Steward Telemetry Lane Saturation

Pattern where a permissive telemetry lane check causes the steward to run the same no-op every cycle, starving portfolio/governance/research delegations.

## Symptoms

- Pipeline blocked on stale data (log shows `resolve_signal_date: ValueError`)
- Telemetry runs every cycle, always producing `STATUS: ACCUMULATING` / same artifact list
- `lane_cycles` in steward_state.json shows only `telemetry: N` growing
- Portfolio, Governance, Research lanes are never logged (no "delegating to X" lines)
- `stuck_cycles` stays 0 because *some* work is done every cycle

## Root Cause

The telemetry check asserts file existence (e.g. `assert scores, 'no scores yet'` on `factor_scores_*.json`). Once a batch of stale score files exists, this check passes indefinitely — even when the scores are a week old and telemetry produces the same accumulating baseline each run.

The steward picks **one lane per cycle** (the highest-priority unblocked lane). A telemetry lane that is never blocked will consume the single action slot forever, blocking delegation lanes (portfolio, governance, research) that would produce real value.

## Detection

Check `steward_state.json`:
```bash
# If lane_cycles has only telemetry after many cycles, saturation is active
python -c "import json; s=json.load(open('.hermes/steward_state.json')); print(s.get('lane_cycles',{}))"
```

Check recency of the file the telemetry check gates on:
```bash
python -c "
from pathlib import Path; 
from datetime import datetime, timezone
scores = sorted(Path('vesper_data').glob('factor_scores_*.json'))
if scores:
    newest = max(s.stem for s in scores)
    print(f'Newest score: {newest}')
    # Check if it's stale (>3 days old)
    from datetime import date
    date_part = newest.replace('factor_scores_', '')
    from datetime import datetime
    d = datetime.strptime(date_part, '%Y%m%d').date()
    delta = date.today() - d
    print(f'Age: {delta.days} days')
"
```

## Fix

Tighten the telemetry lane check in `lanes.json` to gate on recency, not just existence. **Parse the date from the JSON content** (not the filename) — the artifact's own `date` field is the source of truth:

```python
python -c "from pathlib import Path; import json; scores=sorted(Path('vesper_data').glob('factor_scores_*.json')); assert scores, 'no scores yet'; latest=scores[-1]; d=json.loads(latest.read_text()); date_str=d.get('date',''); assert date_str, 'no date in score'; from datetime import date; scored=date(int(date_str[:4]),int(date_str[4:6]),int(date_str[6:8])); gap=(date.today()-scored).days; assert gap <= 3, f'scores stale: latest={date_str} ({gap}d ago)'; print(f'fresh: {date_str}')"
```

**Key details of this pattern:**
- Reads the `date` field from the latest score JSON, not the filename — survives renaming or non-standard naming
- `gap <= 3` calendar days (≈3 XNYS sessions including weekends). Adjust if the pipeline gap is shorter/longer
- Exit code 0 = unblocked (scores fresh), non-zero = blocked (no scores, stale, or unparseable)
- **Shell-escape the nested quotes** correctly when embedding in `lanes.json`: single quotes for inner strings (`'vesper_data'`, `'date'`), double quotes for the outer Python command string

Or introduce a self-block mechanism: have telemetry track whether its last run produced the same artifact state as the run before, and if so, mark itself blocked.

### Verified outcome (2026-07-14)

Before fix: cycle 1–7 showed `telemetry: N` growing in `lane_cycles`; portfolio/governance/research never delegated.

After fix: cycle 8 showed:
- Pipeline: blocked (OHLCV stale)
- Telemetry: **blocked** (scores 4d old, `gap=4 > 3`)
- Portfolio: **delegated to morgan** ← first delegation across all 8 cycles

Lane order verification (run after fix):
```
P1  pipeline        BLOCKED  (OHLCV stale)
P2  telemetry       BLOCKED  (scores stale, recency gate)
P3  portfolio       READY    ok
P4  governance      READY    ok
P5  research        READY    ok
P6  code_health     READY    ok
P10 strategic       READY    ok
```

## See Also

- `references/autonomous-steward.md` — steward architecture and lanes
- `vesper-factor-workflow` SKILL.md — "Lane checks must gate on recency, not existence" pitfall