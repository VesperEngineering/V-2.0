# ADR-0004: Autonomous Financial Research Phase 1

- Status: Accepted
- Date: 2026-07-29
- Owner: V20 operator
- Decision scope: Shadow-only Phase 1 financial coverage research

## Context

V20 needs a thin, end-to-end financial-research slice before adding parallel
analysis, external retrieval, model experiments, or event scheduling. The slice
must reuse controller-owned persistence and evidence, remain independent of the
seven-node software-change workflow, and preserve the read-only Massive and
human-authority boundaries.

## Decision

Add a sibling Phase 1 workflow with two admitted event types:
`direct-request` and `weak-model-result`. A direct request always triggers. A
weak result triggers only when its observed metric is below its threshold;
otherwise it terminates as `ignored`. Weak-result metrics must be finite at the
CLI, service, and typed-contract boundaries.

Triggered events follow one static, typed, acyclic two-node plan: read local
Massive coverage and summarize it. The executor opens
`sp500_ohlcv.sqlite` read-only and immutable, validates its identity and schema,
queries only the requested symbols and inclusive date bounds, and writes
canonical JSON only below the controller's separate derived and evidence roots.
Malformed source dates outside that candidate window are irrelevant. Dataset
receipts bind source, plan, transform, cache, authority, lineage, and
validation-evidence hashes. Generated evidence, dataset, assessment, and
recommendation timestamps come from the injected execution clock.

Accepted terminal records hash-bind the initiating event and exact typed output
chain. Status replays those integrity checks before exposing a record. Generic
workflow-failure records remain minimal and inspectable. A same-event retry
cleans only `financial-research:<run_id>` checkpoints and re-executes; a
mismatched event or corrupt terminal record fails closed.

Expose only `financial-research-start` and `financial-research-status`. Every
CLI start creates a new run. Status opens only the existing terminal Store with
SQLite `mode=ro`; it performs no directory, file, schema, index, evidence,
checkpointer, or executor initialization. Missing or corrupt state and terminal
Store failures expose generic operator-safe messages rather than raw internals.

Phase 1 is shadow research and non-authoritative. It provides no orders, model
promotion, model training, web retrieval, scheduler activation, automatic
two-week schedule, deployment, broker, risk, capital, or credential behavior.
August 12, 2026 is a human review gate, not an automatic action.

## Consequences

- Operators can compare direct-request and weak-result coverage runs with
  persisted state, immutable derived JSON, and hash-bound validation evidence.
- Raw Massive data remains unchanged and outside output roots.
- Coverage conclusions do not establish price quality, returns, model fitness,
  trading value, or promotion readiness.
- Separate CLI starts intentionally create separate run/event identities; any
  future cross-run cache reuse requires another phase and review.
- Parallel execution, repair loops, selected-web retrieval, experiments,
  inactive candidate registration, scheduling, and promotion remain deferred.

## Alternatives considered

- Route research through the software-change workflow: rejected because
  financial analysis has different contracts, state, and authority boundaries.
- Implement later-phase autonomy now: rejected because the thin local slice must
  first produce reproducible evidence without expanding authority.
- Write outputs beside Massive data: rejected because raw provider data is a
  protected read-only dependency.

## References

- [Phase 1 operator runbook](../runbooks/autonomous-financial-research.md)
- [Phase 1 implementation plan](../superpowers/plans/2026-07-29-autonomous-financial-research-phase-1.md)
- [Accepted engine design](../superpowers/specs/2026-07-29-autonomous-financial-research-engine-design.md)
- [Phase 1 verification receipt](../receipts/autonomous-financial-research-phase-1-receipt.md)
