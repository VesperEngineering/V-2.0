# Proposed V20 Evidence and History Migration Plan

- Status: Proposed; not executed
- Date: 2026-07-27
- Scope: Future organization of canonical evidence currently stored under `reports/`
- Authority: Planning only; this document authorizes no move, deletion, content rewrite, or consumer change

## Purpose

V20 currently mixes machine-readable receipts, state, model-iteration outputs, logs, research decisions, audit records, and historical architecture documents under `reports/`. Those artifacts have different retention, mutability, authority, and lookup requirements. A future `evidence/` root should make those distinctions explicit without breaking provenance or silently changing canonical paths.

No historical report is migrated by this plan. The current `reports/` paths remain authoritative until a separately approved migration is implemented and verified.

## Proposed directory structure

```text
evidence/
  README.md
  catalog.json
  schemas/
    catalog.schema.json
    migration-manifest.schema.json
  admissions/
    data/
    split-adjustments/
  backtests/
    <program-or-run-id>/
      manifest.json
      audit.json
      logs/
  experiments/
    model-iteration/
      <campaign-id>/
        campaign.json
        log.md
        baseline/
        runs/
          <run-id>/
            ranking.json
            ranking.log
            train.log
    ranking-diagnostics/
    portfolio-ablation/
    spy-momentum-cpu/
    xgb-shadow-forecast/
  validations/
    repository-maintenance/
  history/
    architecture/
    repository-baselines/
  migrations/
    <migration-id>/
      manifest.json
      verification.json
```

The catalog is a locator and integrity index, not a copy of artifact content. Each entry should include at least `artifact_id`, `artifact_type`, `original_path`, `current_path`, SHA-256, Git revision, source run, creation time when known, verification state, supersession links, and retention policy.

## Proposed mapping

| Current source | Count after the confirmed duplicate removal | Proposed destination | Reason | Known dependencies |
|---|---:|---|---|---|
| `reports/gate_a_split_adjustment_admission_v*.json` | 2 | `evidence/admissions/split-adjustments/` | Admission receipts with an explicit supersession chain | `tests/test_split_adjustments.py` hard-codes v2 and verifies v1's recorded path |
| `reports/backtest_accounting_audit.json` and `reports/backtest_after_accounting_fix.log` | 2 | `evidence/backtests/<accounting-fix-run>/` | Keep one audit and its execution log together | `vesper/dashboard/app.py` hard-codes the audit path; dashboard evidence tests exercise its loader |
| `reports/model_iteration_baseline/*` | 3 | `evidence/experiments/model-iteration/<campaign>/baseline/` | Baseline model, metadata, and exact training source form one provenance unit | Historical metadata and model references; migration must verify hashes and avoid executing the script |
| `reports/model_iteration_state.json` and `reports/model_iteration_log.md` | 2 | `evidence/experiments/model-iteration/<campaign>/` | Campaign state and narrative log belong at campaign scope | `vesper/dashboard/app.py` hard-codes the state path; model-run dashboard tests cover parsing behavior |
| `reports/model_iteration_run_01_*` through `run_30_*` | 90 | `evidence/experiments/model-iteration/<campaign>/runs/<run-id>/` | Co-locate ranking receipt, ranking log, and training log for each run | Internal path strings and campaign state references must be catalogued without rewriting historical bodies |
| `reports/ranking_diagnostic.json` | 1 | `evidence/experiments/ranking-diagnostics/<run-id>/result.json` | Machine-readable diagnostic output | `scripts/ranking_diagnostic.py` currently defaults to the old path |
| `reports/portfolio_ablation_2026-07-22.md` and three associated logs | 4 | `evidence/experiments/portfolio-ablation/<run-id>/` | Keep the conclusion and parameter-specific logs together | Documentation links and any operator procedures referencing the filenames must be found before migration |
| `reports/research/*` tracked artifacts | 20 | Program-specific directories under `evidence/admissions/data/` or `evidence/experiments/spy-momentum-cpu/` and `xgb-shadow-forecast/` | Separate contracts, selections, provenance, review decisions, and comparison receipts by program | Cross-version and provenance links must remain resolvable; several records encode canonical source paths |
| Four superseded platform Markdown records plus `platform_gap_lifecycle_contract_v1.json` | 5 | `evidence/history/architecture/hermes-era/` | Preserve design and audit history separately from current ADRs | ADR-0001 links to current paths; link updates and immutable hashes are required before any move |
| `reports/repository_baseline_vs_003.md` | 1 | `evidence/history/repository-baselines/` | Historical repository-state evidence | `tests/test_repository_baseline.py` currently requires the old path |
| Untracked admission/review and maintenance-audit files currently under `reports/` | 4 | Review individually; likely `evidence/admissions/data/`, `evidence/experiments/spy-momentum-cpu/`, or `evidence/validations/repository-maintenance/<run-id>/` | They appear to be later receipts or audit outputs but do not yet have confirmed tracking or ownership status | Must not move until their owner, canonical status, and intended version chain are explicitly confirmed |

`reports/model_iteration_run_29_train.stdout.log` is excluded from the mapping because it was an exact duplicate of `reports/model_iteration_run_29_train.log` and is the only file authorized for removal.

## Migration invariants

1. Use Git-aware moves in a dedicated, clean worktree after explicit approval; do not copy-and-delete canonical files ad hoc.
2. Hash every source before moving and every destination after moving. A migration manifest must prove byte identity and record the original path.
3. Do not rewrite historical artifact bodies merely to update embedded paths. Resolve legacy paths through the catalog or a narrow compatibility resolver.
4. Preserve supersession, receipt, run, and source-artifact relationships. A missing predecessor is a migration failure.
5. Do not migrate unknown or untracked files until ownership and canonical status are resolved.
6. Do not use Windows directory junctions or symlinks as the compatibility contract. Consumers should use an explicit resolver with fail-closed behavior.
7. Treat datasets, models, receipts, manifests, admissions, and risk decisions as immutable evidence unless a format-specific migration is separately approved.
8. Keep filesystem evidence distinct from LangGraph checkpoints and LangGraph Store memory. Moving evidence must not change workflow or memory authority.

## Dependencies and prerequisites

- Approve an evidence catalog schema and stable artifact identifiers.
- Inventory all path references using Git search and the dependency graph immediately before migration.
- Decide whether current untracked receipts are canonical, generated, or operator-owned work.
- Define retention and redaction rules for logs before adding new historical logs.
- Provide a compatibility resolver and update consumers before the first path move.
- Define backup and rollback receipts for a partially completed migration.
- Start from a reproducible V20 test and import baseline.

## Required code and test changes

The future implementation should make the smallest consumer changes necessary:

- Replace `vesper/dashboard/app.py` constants for model-iteration state and backtest audit with a fail-closed evidence resolver.
- Change `scripts/ranking_diagnostic.py` so its default output is resolved through the evidence layout while preserving an explicit `--report-path` override.
- Update `tests/test_split_adjustments.py` to validate artifact IDs, hashes, and supersession through the catalog instead of relying only on hard-coded `reports/` paths.
- Update `tests/test_repository_baseline.py` for the repository-baseline destination.
- Retain and extend dashboard backtest/model-run tests to cover the new resolver, missing evidence, malformed catalog entries, and legacy-path compatibility.
- Add migration-manifest tests for source/destination coverage, byte hashes, duplicate destinations, path traversal, case collisions, missing predecessors, and rollback completeness.
- Add a test proving all 30 model-iteration run triplets resolve to the same bytes after migration.
- Rerun the full scoped V20 suite, tracked-Python compilation, and isolated import verification before and after each migration slice.

No test should access Massive, a broker, an external service, or a live Codex session as part of this migration.

## Required documentation changes

At migration time, update:

- `evidence/README.md` with authority, naming, retention, immutability, and resolver rules;
- the root `README.md` with the evidence lookup and verification commands;
- `architecture.txt` with the filesystem evidence boundary;
- `AGENTS.md` with protected evidence paths and migration safety rules;
- ADR-0001 references after the historical architecture files move;
- dashboard/operator documentation that names `reports/backtest_accounting_audit.json` or `reports/model_iteration_state.json`;
- a new `reports/README.md` deprecation notice that points to the catalog after migration is complete.

Historical records should not be edited solely to replace embedded old paths. Their original path references are part of their provenance.

## Risks and mitigations

| Risk | Effect | Mitigation / stop condition |
|---|---|---|
| Broken hard-coded paths | Dashboard or tests report missing evidence | Land and test the resolver before moving the first family |
| Hash or provenance loss | Evidence can no longer support a decision | Require manifest byte hashes and reject any mismatch |
| Case-insensitive Windows collisions | One artifact overwrites or aliases another | Preflight normalized destination paths and stop on collision |
| Partial migration | Old and new locations become competing authorities | Use migration states, a complete manifest, and a tested rollback procedure |
| Rewriting historical content | Original receipts cease to be immutable evidence | Preserve bodies byte-for-byte and store path mappings externally |
| Oversized or sensitive logs | Credentials or unbounded output enter the new evidence root | Run bounded secret scans and retention review without printing credential values |
| Unclear ownership of untracked files | Operator work is overwritten or reclassified | Stop until ownership and canonical status are confirmed |
| Consumer behavior changes during a path-only task | Unrelated V20 functionality regresses | Separate resolver work from move batches and retain existing behavioral tests |

## Proposed execution sequence

1. Establish a clean, reproducible baseline and freeze the source inventory for one migration ID.
2. Add only the catalog schemas, evidence resolver, and tests; do not move artifacts yet.
3. Generate and review a proposed source-to-destination manifest with hashes and collision checks.
4. Migrate one low-coupling family, preferably repository-maintenance history, using Git-aware moves.
5. Verify hashes, links, consumers, tests, import checks, and rollback for that slice.
6. Migrate admissions, then backtest evidence, then research programs, then model-iteration artifacts in separate reviewed slices.
7. Move superseded architecture history last, after ADR links and documentation have been prepared.
8. Add the `reports/README.md` deprecation notice only when no active consumer depends on an old path.

Each slice stops on a hash mismatch, unclear ownership, unresolved reference, test regression, or incomplete rollback receipt. No migration begins under the current authorization.
