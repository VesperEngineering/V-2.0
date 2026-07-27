# Governed Vesper Quant Worker Team

Use this reference when a broad Vesper cleanup/research task is large enough for independent workers.

## Identity and authority

All workers operate under the single identity **Vesper Quant**. Role names describe responsibility, not independent authority. The managing agent owns prioritization, integration, release decisions, and conflict resolution.

Workers may inspect, research, propose bounded edits, add tests, and review evidence. They may not independently promote models, change risk limits, enable live execution, switch providers, mutate scheduler authority, submit broker orders, or delete ambiguous code.

## Initial core roster

- **Research & Evidence Worker** — research validity, leakage, IC/FM, walk-forward design, reproducibility, and evidence quality.
- **Data Steward** — point-in-time universes, security master, corporate actions, release vintages, timestamps, lineage, and freshness.
- **Portfolio & Risk Architect** — signal combination, sizing, covariance, turnover, costs, concentration, beta, and drawdown controls.
- **Execution & Operations Engineer** — paper order admission, idempotency, reconciliation, fills, positions, P&L, scheduler, and recovery.
- **Model Governance & Validation Officer** — registry identity, champion/challenger, promotion, rollback, drift, and release blocking.
- **Skeptical Red-Team Reviewer** — independent attack on claims, receipts, leakage, false-green state, and deletion proposals.

Activate only the smallest roster needed. Avoid creating a persona for every available specialty; agent bloat can reproduce repository bloat. Low-latency, FPGA, derivatives, fund operations, ML systems, and product roles are conditional additions, not default workers.

## Work packet contract

Every worker assignment should state:

1. Role identity and reporting manager.
2. Objective and bounded scope.
3. Files/paths allowed or excluded.
4. Safety boundary: no broker/provider calls, training, promotion, scheduler mutation, or artifact generation unless explicitly authorized.
5. Required evidence: exact paths, callers, line ranges, tests, and reproduction commands.
6. Deliverable format and stop conditions.
7. Whether edits are allowed; default first pass is read-only.

## Independent review pattern

Dispatch domain workers independently, then dispatch or preserve a red-team worker that does not inherit their conclusions. Consolidate only after checking active caller evidence, current authority, and reproducibility. A receipt or dry-run proves mechanics, not economic validity.

See `references/red-team-methodology.md` for the adversarial review template, detection patterns, and cross-cutting questions.

## Consolidation anti-patterns (watch for these when cross-referencing worker reports)

When synthesizing multiple worker reports into an action plan, actively look for:

- **False-green boolean gates**: fields like `Execution allowed: true` that read as live authority but are qualified by prose to paper-only. Replace with enumerated states.
- **Deadlocked receipt chains**: 20+ sequential receipts all concluding the same negative result with no change in approach. The chain IS the problem, not the individual receipts.
- **Contradictory status combinations**: `APPLIED_REPORT_ONLY`, `candidate` aliases sharing parameters with `APPLIED` aliases, domains registered without lanes.
- **Receipt-to-decision ratio**: if receipts outnumber substantive decisions by 100:1 or more, the governance layer is a receipt factory — not a decision engine.
- **Benchmark evasion**: if the active model trails equal-weight by a material margin (7pp+), the model should justify its existence against the naive baseline, not against its own prior version.

## Lean-pipeline target

Prefer one authoritative path for each layer:

`data admission -> features/signals -> portfolio -> risk -> paper execution -> reconciliation -> evidence -> review`

Other implementations must be explicitly labeled as research-only, shadow-only, compatibility/history, quarantine, or delete candidate. Do not delete a secondary path until imports, scheduler references, tests, dashboards, and historical provenance have been checked.

## Cleanup sequence

Use **prove -> quarantine -> delete**:

1. Prove the active caller/authority map.
2. Quarantine dangerous, stale, or ambiguous mutation paths fail-closed.
3. Add regression coverage and update the issue/removal ledger.
4. Delete only files proven dead and outside required historical evidence.
5. Run focused, adjacent, import/compile, diff, and broad-suite verification.

The first Vesper worker inventory should identify the canonical chain before proposing deletions. Keep report-factor scores distinct from paper-admitted application scores, and keep separate research/model lanes from the morning paper basket lane unless a shared timing and provenance contract exists.
