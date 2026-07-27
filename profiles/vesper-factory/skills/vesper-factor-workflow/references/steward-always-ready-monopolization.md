# Always-Ready Lane Monopolization

A structural steward problem where a lane with `blocked_if: "never"` at a non-last priority monopolizes every cycle when higher-priority lanes are blocked, starving lower-priority but equally-available lanes.

## Symptoms

- Pipeline blocked (OHLCV stale)
- Telemetry blocked (recency gate)
- Portfolio-delegated-to-Morgan repeats every cycle (observed: 6+ consecutive cycles)
- `lane_cycles` in steward_state.json shows only `portfolio: N` growing alongside the initial `telemetry: M`
- `stuck_cycles` stays 0 — portfolio runs fine, it's just the same no-progress delegation
- Governance, research, code_health lanes never get a turn
- The "only dispatch once" rule prevents duplicate work, but the steward keeps re-signaling the same delegation

## Root Cause

The steward picks **one lane per cycle** (the highest-priority unblocked lane). When P1 (pipeline) and P2 (telemetry) are blocked, the steward falls through to P3 (portfolio). Portfolio's check always returns 0 (`"check": "python -c \"print('ready')\""`), so it's always ready.

The steward has no mechanism to:
- Track whether a lane's output has changed since its last run
- Skip a lane after N consecutive cycles with no new data
- Rotate among equally-ready lanes at different priorities
- Self-block after producing the same artifact state twice

## Detection

```bash
# Check lane_cycles — if portfolio keeps growing while governance/research stay 0
python -c "import json; s=json.load(open('.hermes/steward_state.json')); print('lane_cycles:', s.get('lane_cycles',{}))"

# Check if the portfolio delegation is repetitive from the same stale state
tail -20 .hermes/steward_log.jsonl | grep -c "delegating to morgan"
```

## Contrast with Telemetry Saturation

| Aspect | Telemetry Saturation | Always-Ready Monopolization |
|--------|---------------------|---------------------------|
| Check type | Permissive (existence) | Trivially always-ready |
| Fix target | Tighten the check (recency gate) | Structural: steward needs output-change tracking |
| Cycle behavior | Same lane runs every cycle | Same lane signaled every cycle |
| Dispatch | Agent CAN dispatch (new work each time) | Agent should NOT dispatch (duplicate work) |
| Symptoms | Only telemetry lane_cycles grows | Telemetry + portfolio both grow, portfolio repeats |

## Fix Options

### Option A: Add output-change tracking to the steward

The steward should track whether a lane's last action produced output different from the run before. If the same lane is selected and its prior output artifact has the same hash/date/content, skip it and fall through to the next ready lane.

Implementation sketch:
```python
# In steward.py, after lane action completes:
# 1. Compute a fingerprint of the lane's output (e.g. hash of the primary artifact)
# 2. Store it in steward_state.json as lane_output_fingerprints: {lane_id: hash}
# 3. Before selecting a lane, check if its fingerprint is unchanged since last run
# 4. If unchanged, skip to next ready lane
```

### Option B: Add max-consecutive-cycles to lanes.json

Allow each lane to declare a `max_consecutive_cycles` field. When a lane has been selected that many times in a row, force-skip to the next ready lane. `blocked_if: "never"` lanes would get `max_consecutive_cycles: 1` to prevent monopolization.

```json
{
  "id": "portfolio",
  "priority": 3,
  "blocked_if": "never",
  "max_consecutive_cycles": 1,
  "action": "delegate_to_morgan"
}
```

### Option C: Rotate among always-ready lanes

When the highest-priority unblocked lane is an always-ready lane (`blocked_if: "never"`), rotate through all always-ready lanes at that priority tier and below. Only run the same one again after all others have had a turn.

## Current Workaround (Manual)

The agent handling the steward cron applies the "only dispatch once" rule: skip the actual `delegate_task` call when the same lane signals the same delegation with no state change. Instead, pick a different always-ready lane (governance, research, code_health) and dispatch that worker.

This is fragile — it relies on the agent's judgment to detect duplicate state. The structural fix should live in the steward itself.

## See Also

- `references/steward-telemetry-lane-saturation.md` — the earlier telemetry existence-check pattern
- `vesper-factor-workflow` SKILL.md — "Steward delegation signals require agent dispatch" pitfall
- `D:/vesper/.hermes/steward.py` — the steward implementation
- `D:/vesper/.hermes/lanes.json` — lane definitions