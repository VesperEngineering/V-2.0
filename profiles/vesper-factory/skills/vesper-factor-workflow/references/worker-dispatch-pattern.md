# Worker Dispatch Pattern (via delegate_task)

The steward logs `delegate_to_<name>` but does not dispatch subagents. The agent must read the steward log/state and dispatch the worker manually.

## Workflow

1. Read `steward_state.json` (`last_action.lane` + `last_action.status`)
2. Read the last 5 lines of `steward_log.jsonl` to find delegation signals
3. Check if worker was already dispatched this session (avoid duplicate work)
4. Call `delegate_task` with the worker's tier-appropriate model and full context

## Context Templates

### Morgan — Portfolio Construction

Include: current equal-weight basket code path, covariance/constructor file paths, strategic finding about ~120 lines of glue code, test status, and the specific integration question.

```python
context = f"""
You are MORGAN, portfolio construction researcher.

## Current State
- Equal-weight basket: scripts/sector_neutral_basket.py (top ticker from 4 strongest sectors, 25% each)
- Covariance: app/services/portfolio_covariance.py (Ledoit-Wolf, existing but unwired)
- Optimizer: app/services/portfolio_constructor.py (MCP, existing but unwired)
- ~120 lines of glue code needed to replace equal-weight with correlation-aware sizing

## Task
Design and implement the integration. Write tests. Produce a memo at artifacts/evals/portfolio_construction_memo_{date}.md

## Constraints
- Fail closed
- Preserve existing sector_neutral_basket.py CLI interface
- All weights sum to 1.0, no position > 0.25
- Use existing dependencies (numpy, scipy, sqlite3)
"""
```

### Riley — Governance Cleanup

Include: current false-green receipts, stale status fields, contradictory documentation, and the specific cleanup target.

```python
context = f"""
You are RILEY, governance reviewer.

## Current State
- STATUS.md may claim dates that differ from actual DB state
- Receipts may have stale or contradictory fields
- Dead code or archived scripts may have orphaned references

## Task
Audit the specified surface. Report exact file paths, line ranges, and the fix. Do not apply changes without explicit approval.
"""
```

### Rez — Deep Research

Include: current research question, available data sources, existing factor findings, and the specific gap to investigate.

```python
context = f"""
You are REZ, research analyst.

## Current State
- [specific research question]
- Available data: [Massive OHLCV, SEC EDGAR, FRED, Wikipedia, etc.]
- Existing findings: [FM evidence, IC tracker, etc.]

## Task
[Research question]. Stay bounded — report findings, do not implement changes.
"""
```

### Thomas — Strategic Review (escalation only)

Include: stuck cycles count, lane states, current blockers, and the request for re-prioritization.

```python
context = f"""
You are THOMAS, COO.

## Escalation
All lanes have been stuck for {stuck_cycles} consecutive cycles.

## Current State
- Pipeline: [blocked reason]
- Telemetry: [blocked reason]  
- Portfolio: [status]
- Governance: [status]
- Research: [status]
- Code Health: [status]

## Request
Review and re-prioritize lanes. What should change?
"""
```

## Avoiding Duplicate Dispatches

When the steward cycles 3 times and delegates to Morgan each time (e.g., cycles 8, 9, 10), only dispatch Morgan once. Track dispatch state in the session. The steward logs the same delegation because the underlying data hasn't changed — dispatching again would produce the same work.

- Before dispatching, check if this worker was already dispatched in this session
- If yes, write a note to the learnings journal and skip
- The next fresh cycle (new data, new blocker resolution) may warrant a new dispatch

## Quota-Aware Model Selection

Read the current quota before dispatching:

```python
from app.services.quota_router import read_quota, get_tier, allocate_models
quota = read_quota()
tier = get_tier(quota)
models = allocate_models(quota)
worker_model = models.get("morgan")  # or riley/rez/thomas
```

Tier FULL: Morgan/Riley get Sol (openai-codex), Rez gets DeepSeek V4 Pro
Tier CONSERVE: Only Thomas gets Sol, others on DeepSeek
Tier CRITICAL: All on DeepSeek V4 Flash