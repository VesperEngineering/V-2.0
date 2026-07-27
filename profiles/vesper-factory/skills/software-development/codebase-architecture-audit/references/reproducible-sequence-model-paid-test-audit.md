# Reproducible Sequence-Model Paid-Test Audit

Use this reference for a read-only decision on whether local transformer/sequence-model artifacts justify spending on external compute.

## Candidate boundary

Exclude `.tmp`, pytest basetemps, fixture repositories, test-named checkpoints, virtual environments, and scratch worktrees. Inventory only durable checkpoints plus their non-test dataset manifests, training receipts/logs, evaluation outputs, and governance decisions.

Classify each evidence item separately: **checkpoint present**, **runnable now**, **historically reproducible**, and **eligible for paid rerun**. A checkpoint can be runnable while failing the latter two.

## Required evidence matrix

| Gate | Require for GO |
| --- | --- |
| Artifact identity | Exact checkpoint hashes, architecture/config, seed IDs, and actual runtime loading evidence. |
| Executed source | Commit/tree or canonical dirty-worktree manifest covering all imported implementation/config bytes and dependencies. |
| Data availability | Immutable raw panel/source manifest with raw hashes, source/vendor, adjustments, PIT universe/membership, macro inputs, and exact cutoff. Do not accept only size/mtime. |
| Training | Frozen command/config, seed, feature schema, label horizon, train/validation dates, and checkpoint-bound training receipt. |
| Chronology | Chronological train/validation/test dates; explicit purge/embargo for overlapping label horizons. |
| Holdout | A final, untouched period never used for architecture, seed, selector, weighting, group-cap, or cost tuning. Walk-forward portfolio slices alone are not a model-unseen holdout unless model refits are bound to each slice. |
| Economics | Costs, turnover, drawdown, benchmark, capacity/constraint assumptions, and comparable equal-weight plus simple-model controls. |
| Negative controls | Shuffled-label/model controls must not retain comparable economics; otherwise treat the claimed model-specific edge as unproven. |
| Governance | Current registry/board/admission gate must permit an experiment; report-only or `HOLD` receipts do not authorize paid compute. |

## Evidence pitfalls

- A sidecar marked `RUNTIME_BOUND` validates the current checkpoint/file relationship; it does not recover the historical dataset if it records only a mutable database path, size, or mtime.
- An ignored `artifacts/` directory can hold real evidence, but without a content-addressed bundle or tracked producer/source binding it is not reproducible acceptance evidence.
- Validation accuracy from a chronological tail is not an untouched holdout and is inadequate when dates and input hashes are absent.
- Strong results under fixed-model rolling windows can be contaminated when the checkpoint was trained using the same calendar interval. Require refit-per-window proof or a later untouched holdout.
- A separate checkpoint with a weak benchmark-relative result is useful adverse evidence; do not let a stronger but unbound sibling result override it.
- `PASS` often means a receipt or report-only gate completed. Read authority and decision fields; it does not imply admission, promotion, or paid-test readiness.

## Reporting format

Open with **GO/NO-GO**, then provide an evidence table by gate. Cite exact paths, hashes, dates, and metric windows. Separate (1) evidence that supports a future frozen rerun from (2) evidence sufficient to approve it. End with the smallest immutable bundle and rerun protocol required for re-review.
