# Post-consumption local-LLM development campaigns

Use this pattern after a sealed promotion benchmark has been opened and consumed, when further development is authorized but benchmark-derived tuning is forbidden.

## Evidence separation

- Treat the consumed benchmark as quarantined metadata. Development code may verify only its immutable identity, consumed status, and authority boundary; it must not read cases, responses, failure details, per-task scores, or evaluator traces.
- Build a new `DEVELOPMENT_ONLY` challenge set from independent, non-benchmark sources. Freeze it before model evaluation and mark it immediately ineligible for promotion claims.
- Validate unique IDs, balanced task families, complete deterministic rubrics, and no normalized-prompt, assistant-target, or case-concept overlap against approved training data and declared development holdouts.
- Development responses may be inspected and used for model selection. Promotion evidence must later be independently constructed only after the chosen recipe and training data are frozen.

## Bounded staged tournament

Predeclare a small sequential matrix instead of a Cartesian sweep:

1. Evaluate the current base and adapter on the new development set.
2. Run one matched capacity challenger.
3. Run one matched schedule challenger using the better completed family.
4. Use a final confirmation only if the training-job budget still permits it.

Keep one principal variable per completed comparison. Declare winner gates and tie-breakers before inference. If no candidate passes, select none and stop at the budget ceiling.

Count trainer launches conservatively. A guard-terminated trainer that reached model download/loading but completed zero optimizer steps is a failed pretraining job, not a free retry. Preserve a failure receipt with the guard reason, output absence, log hash, zero-step proof, and remaining job budget. Any recovery launch gets a new run ID and a revised frozen protocol.

## Model snapshot prefetch under host-RAM pressure

First-time model download can violate host-RAM limits before GPU allocation begins. Distinguish this infrastructure failure from model-quality evidence:

1. Verify no report or adapter exists and no training step was logged.
2. Correct stale dashboard state from `RUNNING` to receipt-backed `FAILED`.
3. Complete the model snapshot in a separate **non-training** phase with a single download worker under the same host-RAM guard.
4. Require no `*.incomplete` files, required shard/index/tokenizer files present, exact sizes and SHA-256 hashes, and a write-once prefetch receipt.
5. Reclaim only disposable filesystem page cache if authorized; do not delete model or project artifacts.
6. Bind every snapshot file or a verified snapshot manifest into the next training protocol.
7. Force the recovery launch offline (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`) so download behavior cannot recur inside the trainer.
8. Keep the original resource ceilings unchanged. If local-only model loading still crosses them, classify the capacity hypothesis as resource-blocked rather than weakening the guard.

Host RAM must be measured from the Windows host when WSL is the worker. Low VRAM during a RAM-triggered failure is evidence that the process failed before model placement, not that the model would fit.

## Memory-safe base-versus-adapter evaluation

A model can train within bounds yet fail a combined base-versus-adapter evaluator because model loading, memory-mapped shards, and WSL page cache have different host-RAM behavior. Preserve the verified adapter: an evaluation guard failure is not a training failure and does not consume another training job.

When a combined evaluator crosses the host-RAM ceiling:

1. Verify that no canonical evaluation was written, no evaluator remains, and the GPU lock was released. Preserve a separate failure receipt.
2. Split base and adapter inference into separate guarded processes so host allocations are released between modes. Keep the development manifest, tokenizer, quantization, deterministic generation, and scoring identical; process lifetime is an infrastructure variable, not a scientific variable.
3. Inspect the live evaluator before wrapping it. Do not assume private helper names or a reusable high-level function exist. Reuse the exact production loading contract—allocator fraction, 4-bit configuration, dtype, device map, tokenizer padding, `no_grad`, generation length, sampling mode—and call the actual scoring loop.
4. Compile and lint campaign tooling, introspect callable signatures, and smoke-test the merger with isolated synthetic partials before GPU launch. A child that exits before model load is a tooling failure and may be retried under a new immutable protocol revision; it does not consume a training job.
5. Write one immutable partial per mode with the complete response/score details, manifest hash, evaluator hash, tool hash, allocator limit, and peak VRAM. Guard each process independently.
6. Predeclare a deterministic CPU-only merge that binds both partial hashes, both phase protocols, both guard receipts, and the exact merger. The canonical evaluation is written once only after both partials are complete.
7. Independently rescore every merged response against the frozen development rubric and bind the rescore receipt to the canonical evaluation hash. Never trust merge success alone.

For WSL page-cache pressure, a revised guard may proactively reclaim disposable WSL filesystem cache at a warning threshold below the hard host-RAM ceiling. The fail-closed ordering is critical:

- sample and record the original host RAM peak;
- if the sample already exceeds the hard ceiling, terminate immediately—never retroactively rescue a breach;
- otherwise, at the warning threshold, perform a rate-limited `sync` plus root `drop_caches` operation;
- record before/after percentages and timestamps in the guard receipt;
- recheck the hard RAM and VRAM limits after reclaim;
- treat reclaim failure as a guard trigger.

Detect the campaign-specific split evaluator as a competing GPU-heavy process in addition to the production trainer/evaluator. Long partial evaluations must be tracked by one process ID and one expected receipt; timeout of a wait operation is not authorization to launch a duplicate.

## Immutable recovery revisions

Never overwrite a frozen campaign or phase protocol after preflight or launch:

- Write a failure receipt for the old revision.
- Create `campaign-protocol-rN.json` and a new phase directory.
- Record `supersedes`, old protocol hash, exact reason, training jobs started/remaining, and unchanged scientific variables.
- Separate an infrastructure change (for example, completed offline cache) from the experiment's principal variable.

A failed preflight before lock acquisition and child launch does not consume a training job, but it still needs a durable receipt. A trainer child launch does consume one.

## Windows/WSL source-binding pitfall

A Windows process may be unable to traverse a WSL `/home` project symlink through `\\wsl.localhost`, even when the native Windows and WSL file bytes have the same SHA-256. Do not misclassify this as CRLF drift.

For each input binding:

1. Try the host-visible path and exact byte hash.
2. If traversal fails, invoke native WSL `sha256sum <wsl-path>` directly without a shell-quoted code string.
3. Accept only the predeclared hash; never skip the binding.
4. Publish a revised guard and protocol rather than mutating a hash-bound guard in place.

Use ordinary multiline process-probe code instead of compressed list-comprehension one-liners; verify the probe independently before freezing it.

## Late background notifications and phase reconciliation

A background-process completion notice can arrive after the campaign has already superseded that phase. Treat the notice as evidence about the exact process named in the notice, not as the current campaign state.

1. Match the notice to its phase ID, protocol path/hash, command hash, and tracked process ID.
2. Read the guard receipt and host log before interpreting wrapper exit codes such as `97`. Distinguish a guard trigger, a child/runtime error, and an orchestration-wrapper status.
3. Establish whether a trainer child launched, whether a model loaded, whether optimizer steps completed, and whether any canonical output was written. These facts determine training-job accounting and scientific authority.
4. Check whether a later immutable protocol revision already preserved and superseded the failure. Never roll a completed campaign backward merely because an old process notification arrived late.
5. State the reconciliation explicitly: for example, `known tooling failure before model load; zero training jobs; superseded by r3 successful evaluation`.

## No-winner closure and cleanup

When the bounded matrix is exhausted and no candidate passes every frozen gate, close with `NO_WINNER`; do not promote the best observed candidate by narrative.

- Freeze a machine-readable comparison for every candidate, gate failures, training-job accounting, adapter tree hashes, source/config/data bindings, quarantine status, and false authority for promotion/deployment/execution.
- Distinguish `best_observed_research_leader` from `selected_development_winner`. The former may be recorded while the latter remains null.
- A development diagnosis may identify the next material lever, but a recommendation for data composition grants no admission or training authority. Require a new explicit human approval of an exact inspectable artifact.
- Write both a JSON verdict and a concise Markdown research verdict, plus a fail-closed promotion-readiness artifact. If no winner exists, do not create or authorize a future promotion benchmark.
- Re-run the project-declared verification gates and preserve their exact commands/output. Respect configured scope: if `pyproject.toml` declares only a package, invoke mypy on its source path when editable-install resolution complains about a missing `py.typed`; do not broaden the terminal gate to operational scripts and then repair unrelated typing debt after the experiment.
- Preserve the finalizer source in the campaign before removing temporary operational copies. For a Windows-host temporary file copied into a WSL-native campaign, prefer a WSL command using `/mnt/c/...` to `/home/...`; UNC backslash escaping is fragile in nested Python/shell/JSON layers.
- Finish with a cleanup receipt proving no GPU-heavy process, no lock, no temporary operational copies, and hashes for the final verdict/verification/finalizer.

## Resume packet when interaction budget ends

If the agent/tool ceiling arrives mid-campaign, report only verified state:

- completed and failed phases;
- exact receipts and hashes;
- training jobs consumed and remaining;
- predeclared but unlaunched phase protocol;
- whether any winner exists;
- the single next executable action.

Do not call a prepared protocol a completed experiment, and do not claim a capacity-versus-strategy conclusion until both completed comparisons exist.
