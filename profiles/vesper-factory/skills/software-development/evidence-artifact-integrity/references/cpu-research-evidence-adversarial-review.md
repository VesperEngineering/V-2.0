# Adversarial Review of CPU Research Evidence Pipelines

Use this checklist when a local CPU-only research candidate combines frozen data, walk-forward evaluation, immutable receipts, an append-only ledger, restart recovery, a one-time holdout, Kanban updates, and unattended execution.

## 1. Freeze the exact candidate before review

- Count staged paths with NUL framing (`git diff --cached --name-only -z`), not line counting.
- Record the complete binary staged-diff SHA-256 and `git diff --cached --raw` blob IDs.
- Read every staged file from that identity. A claimed 11-file scope that currently contains 12 files is scope drift, not a harmless display discrepancy.
- Recompute the digest before and after tests and again immediately before the verdict. If it changes, identify changed blob IDs, inspect every successor delta, rerun affected gates, and bind the verdict only to the final stable digest. Never silently reuse findings from a superseded candidate.

## 2. Make CPU and queue restrictions executable

A protocol field such as `cpu_only: true` is not enforcement.

- Validate exact nested keys and exact scalar types, not just top-level shape.
- Require the exact experiment queue and an exact ID-to-model mapping; reject extra IDs, repeated models, reordered runs, and arbitrary explicit trials.
- Reject model options that can select GPU/device acceleration or exceed thread limits. Set the CPU device explicitly at construction time.
- Apply thread limits to BLAS, NumExpr, sklearn, and XGBoost on every entry point, not only a scheduler wrapper.
- Enforce the wall-clock budget and terminate the process tree, not only the direct child.
- Bind the dependency lock/version set into the protocol and require all baseline/champion/candidate comparisons to use the same runtime identity.

Minimal negative probe: clone the protocol in memory, set an accelerator option and an excessive worker count, and require validation to reject it before model construction.

## 3. Admit source before any evidence write

- Run the clean-source gate before dataset or feature materialization.
- Resolve every imported evidence-critical module through `module.__file__`; require it to be inside the intended worktree, tracked, and byte-identical to the claimed revision.
- Hash the complete implementation slice, including helpers; hashing only one public function misses behavior changes in called helpers.
- Bind the protocol, dependency lock, data materializer, feature builder, evaluator, lifecycle controller, runner, verifier, and scheduler wrapper.
- Snapshot or lock mutable sources before reading. Hashing an adjusted file or SQLite database after consuming it creates a read/hash race. Use a proven frozen/checkpointed SQLite copy when `immutable=1` is claimed.
- Keep source/output paths disjoint and confined beneath approved canonical roots. Reject traversal components, symlinks, junctions/reparse points, and hostile ticker-to-filename mappings.

### Re-key immutable generations after source-only changes

A raw source digest changes after formatting or line-ending normalization even when computed feature bytes remain identical. Treat that as provenance change, not permission to relax replay validation.

- Let replay fail on the old manifest when the executed feature-builder/evaluator digest changes.
- Preserve the old immutable data/feature generation and manifest.
- Materialize a new versioned generation path bound to the new source digest; never overwrite the old path or edit its manifest.
- Recompute and read back both the new source digest and physical artifact digest. It is valid for the physical feature SHA-256 to remain identical while the source-bound generation identity changes.
- Reset all downstream supervised, reviewer, unattended, and scheduler proofs after the re-key. A semantic-no-op source change still invalidates source-bound acceptance.

## 4. Cross-bind receipts and replay context

A self-hash proves only that fields agree with themselves.

- Derive candidate, evaluation, and decision from frozen inputs and require exact canonical equality.
- Cross-check top-level experiment/model IDs against every embedded payload and ledger row.
- A completed-run replay must match the requested model plus current protocol, dataset, features, source, evaluator, runtime, research date, and prior-evidence bindings before returning success.
- Baseline and champion receipts must have the same complete context as the candidate. Never compare metrics across different source/data/runtime identities.

Negative probes:

1. Request a different model under an already completed experiment ID; require `HELD`, not the old receipt.
2. Recompute a receipt self-hash after changing only a top-level identity; validation must reject the cross-binding.
3. Present a candidate with different dataset/source/runtime hashes to an old baseline; admission must fail before evaluation.

## 5. Recover every durable cut point

- Put data/feature materialization under the same bounded singleton or a dedicated generation lock.
- Publish related artifacts as one generation. A data file without its manifest must be recoverable without overwrite or manual deletion.
- Fault-inject after data, manifest, candidate, evaluation, decision, final run-directory publication, ledger publication, champion publication, summary publication, active-marker cleanup, Kanban comment, and companion publication.
- A receipt-present replay must continue all missing downstream transitions. It must not return merely because the final run directory exists.
- Timeout recovery must account for orphaned descendants and stale locks.

A useful probe raises immediately after the final run directory is published, then retries. The retry must repair the ledger, champion, summary, and active marker before returning.

## 6. Prove append-only history against rollback

Hash-chained generations do not help if a mutable pointer can select an old valid generation.

- Validate row uniqueness, exact sequence, canonical framing, and row-to-receipt model/decision identity.
- Require the current pointer to name the unique maximal valid generation, or bind the accepted head to an independent append-only anchor.
- Treat unexplained later generation directories as evidence of rollback or interrupted publication.
- Probe by creating two generations, restoring the first pointer while retaining the second generation, and requiring rejection with all bytes preserved.

## 7. Keep the holdout genuinely untouched

- Pre-holdout source selection, split inference, quarantine, date masks, and universe filtering must not inspect holdout-period outcomes. A holdout jump must not remove a ticker's earlier training history.
- Compute exact target dates from a frozen exchange-session calendar before filtering incomplete observation dates. Shifting five retained rows can become six real sessions after one excluded date.
- Drain the exact frozen queue and select the exact current pre-holdout champion before opening the holdout.
- Atomically persist a candidate/context-bound consumption latch before evaluation begins. A crash must reconcile the same opening, never evaluate again as a fresh opening.
- Holdout replay must revalidate the candidate receipt, baseline receipt, source/data/features/evaluator/runtime context, decision derivation, and immutable consumption record.

## 8. Verify Kanban and scheduler evidence byte-for-byte

- A marker substring is not comment provenance. Bind the exact live comment ID and exact body hash; require exactly one matching comment.
- Keep comment publication and companion reconciliation inside an exactly-once transition. Two replaying processes must not both observe absence and post duplicates.
- Bind scheduler evidence to the live scheduler record, exact absolute executable paths, argv, wrapper bytes/hash, source revision, cadence, timeout, environment policy, and one-experiment limit.
- Do not describe an environment as credential-denying merely because common secret variables are omitted while `HOME`, application-data directories, or an inherited executable `PATH` remain available.
- Enforce output bounds while streaming; checking size only after `capture_output=True` has already buffered the child output is not a memory bound.

## Acceptance rule

Green happy-path tests do not override a reproduced adversarial failure. Any accepted accelerator option, cross-bound replay, incomplete recovery, early/reopened holdout, pointer rollback, wrong-body Kanban acceptance, or session-horizon drift is a release `HOLD` until repaired and re-reviewed against a newly frozen candidate digest.
