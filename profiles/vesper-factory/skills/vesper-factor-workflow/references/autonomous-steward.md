# 24/7 Autonomous Work Steward

Built 2026-07-14. Replaces static clock-driven cron with fluid lane-based progression.

## Architecture

```
Steward (every 15 min)
  ├─ check lanes.json for highest-priority unblocked lane
  ├─ execute lane action (shell or delegate)
  ├─ log to steward_log.jsonl + steward_state.json
  └─ after 4 stuck cycles → escalate to Thomas
```

## Lane Definitions

File: `D:/vesper/.hermes/lanes.json`

| Lane | Priority | Blocks when | Action when ready |
|------|----------|-------------|-------------------|
| pipeline | 1 | OHLCV stale | Run ingest → score → basket |
| telemetry | 2 | No scores yet | Run paper evidence baseline |
| portfolio | 3 | never | Delegate to Morgan |
| governance | 4 | never | Delegate to Riley |
| research | 5 | never | Delegate to Rez |
| code_health | 6 | tests broken | Run tests, report status |
| strategic | 10 | never (escalation) | Thomas re-prioritizes |

## Key Design Decisions

1. **Fluid switching** — when pipeline is blocked (data stale, weekend), steward automatically picks next ready lane. No human intervention needed.
2. **Never idle** — portfolio/research/governance/code_health are always ready. The system is always making forward progress on something.
3. **Fail-closed** — `never_actions` list prevents steward from touching live orders, model promotion, risk limits, scheduler authority, or data providers.
4. **Escalation** — after 4 cycles with no forward progress, Thomas (COO) is signaled to review and re-prioritize lanes.
5. **Delegate pattern** — lanes with `action: "delegate_to_<worker>"` signal the steward cron job to spawn a subagent. The subagent's output is captured in the steward log.

## Cron Wiring

```bash
hermes cron create "*/15 * * * *" --prompt "Run steward + dispatch workers"
```

The cron job:
1. Runs `python .hermes/steward.py` to check lanes
2. Reads `steward_state.json` for the last action
3. If a delegation was signaled, dispatches the appropriate worker subagent
4. If escalated, runs Thomas strategic review

## Files

- `.hermes/lanes.json` — lane definitions and rules
- `.hermes/steward.py` — Python engine (self-contained, no deps beyond stdlib)
- `.hermes/steward_log.jsonl` — audit trail
- `.hermes/steward_state.json` — cycle counter, last action, stuck count
