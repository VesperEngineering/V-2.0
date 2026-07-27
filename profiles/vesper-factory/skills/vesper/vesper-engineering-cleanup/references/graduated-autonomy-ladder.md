# Graduated Autonomy Ladder

Framework for introducing automation into a fail-closed paper-only quant system. Every step toward hands-off operation is paired with a mandatory health check that defaults to STOP.

## Core principle

Never jump from manual to autonomous. Each level proves itself before the next is considered. Every automation step requires a corresponding health gate. Gates default to HALT — the system must prove health before proceeding, not prove failure before stopping.

## Levels

### Level 0 — Manual (current baseline)
- User triggers everything: data ingestion, scoring, basket construction, paper execution
- No automation surface to fail
- Highest operator burden, lowest automation risk

### Level 1 — Scheduled data + scoring
- Pipeline runs on cron: ingest → score factors → produce report
- No action taken from scores
- Health gate: data freshness check, score bounds sanity
- User reviews report before market open; manual decision to trade
- Failure mode: stale data → report flags red → user sees it and doesn't trade

### Level 2 — Scheduled scoring + paper basket
- Pipeline runs, basket auto-generated from scores
- Basket logged but NOT submitted to broker
- Health gates: same as L1 plus position count sanity, sector exposure within limits
- User reviews basket, manually submits if approved
- Failure mode: nonsensical basket → logged but not submitted → user sees anomaly

### Level 3 — Auto paper execution with health gates
- Basket auto-submitted to Alpaca paper
- ONLY if all health gates pass: data freshness, score bounds, position count, sector exposure, notional limits
- Any gate fails → no submission, user alerted
- This is the "open claw" boundary — the gate is the protection
- Failure mode: gate failure → halt → user alerted; gate false-pass → paper-only, no real capital at risk

### Level 4 — Live shadow (weeks, not days)
- Paper execution runs silently
- Separate shadow process tracks "what would have happened live"
- Builds evidence without risk
- No live capital deployed
- Promotion gate requires: 20+ trading days of reconciled paper evidence, model beats equal-weight benchmark, zero unexplained PnL breaks

### Level 5 — Minimal live (months, evidence-gated)
- Small capital only (e.g. $3K)
- Hard-coded position and notional limits
- Human approval required to raise limits
- Daily automated reconciliation against paper shadow
- Promotion from paper to live is a separate governance gate — never automatic

## Health Gate Design Rules

1. Every gate defaults to HALT — the system proves health, not failure
2. Gates must be independent of the process they guard (separate code path, separate data check)
3. Gate failure must produce a human-readable alert with the specific reason
4. Gates must not be configurable at runtime (hard-coded thresholds)
5. Adding a new automation step requires adding a new gate before enabling it
6. Removing or weakening a gate requires explicit operator approval with a dated receipt

## Anti-patterns

- "It ran successfully once" → not evidence of readiness for the next level
- "The dry run passed" → dry runs prove mechanics, not safety
- "We'll add gates later" → gates must be designed and tested BEFORE the automation they protect
- "It's only paper" → paper can still produce false confidence; treat paper automation with the same gate discipline as live