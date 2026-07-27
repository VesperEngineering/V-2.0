# Morning Briefing: Artifact State vs Governance Admission

Use this checklist when reviewing a daily Vesper factor pipeline without changing runtime authority.

## Evidence order

1. Read `PROJECT_ADVANCEMENT.md` and keep its current producer/provider/order boundary.
2. Inspect the newest score artifact and factor-run receipt by timestamp, not by assumed directory. `data/` may be a junction/mirror of `vesper_data/`; factor-run receipts can live there even when an older instruction names `artifacts/evals/`.
3. Inspect the matching basket and telemetry receipt for the same source session.
4. Read the last five steward-log entries, `steward_state.json`, the newest activity rows, team memory, and the last five learnings.
5. Review every worker file's `## Proposed knowledge`; explicitly record zero proposals when none exist. Preserve unresolved `needs_review` work.

## Two-layer classification

Never turn `status=SUCCESS` or `evidence_state=READY` into an unconditional pipeline PASS.

- **Technical artifact state:** score count, admitted universe, top names, factor outcomes, degradation reasons, basket, and telemetry.
- **Governance/control-plane state:** board authority, successful producer-run binding, source fingerprint/sentinel, call/write inventory, steward/activity reconciliation, and independent-review disposition.

Report:

- `PASS` only when both layers agree and the run is governance-admitted.
- `DEGRADED` when artifacts are structurally READY but control-plane telemetry is stale, contradictory, or provenance admission is unresolved.
- `BLOCKED` when the board denies the producer/action, a required receipt is missing, or independent review rejects admission.

A later artifact timestamp does not erase an earlier steward failure. If the steward/activity ledger ends on failure while later artifacts or team notes claim success, say so directly and keep the artifacts observation-only until reconciled. Do not rerun providers, mutate history, or open an order path merely to manufacture proof.

## Briefing output

Keep the report direct:

1. Pipeline status with the layer-specific reason.
2. Score count, top three, exclusions, and degradation.
3. Basket tickers, sectors, and weights.
4. Paper-evidence days and telemetry state.
5. Worker-proposal dispositions and unresolved `needs_review` events.
6. Team-memory/steward highlights.
7. One recommendation.

## Persistence and verification

- Append a significant briefing to `.hermes/team_memory.json`; keep every-cycle detail in append-only `.hermes/learnings.jsonl`.
- Validate `team_memory.json` as JSON after editing.
- Validate the newly appended JSONL row independently before considering any pre-existing malformed historical row. Never rewrite the append-only journal merely to make a whole-file parser green.
- When repository verification is requested for a memory/knowledge change, run the focused knowledge-reader tests with a unique disposable Windows `--basetemp` outside the repository, then remove it.

Session basis: 2026-07-20 morning review, where score/status artifacts were structurally READY while steward/activity still ended on an earlier failure and provenance admission was unresolved.