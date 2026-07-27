# One-Time Sealed-Benchmark Promotion Run

Use this recipe when one bounded model-training run is followed by exactly one base-versus-candidate evaluation on a sealed benchmark.

## Evidence-state machine

Use explicit, durable states rather than prose:

```text
SEALED
  -> TRAINING_AUTHORIZED
  -> TRAINING_COMPLETE_UNVERIFIED
  -> TRAINING_VERIFIED
  -> OPENED_FOR_SINGLE_EVALUATION
  -> CONSUMED_AFTER_SINGLE_EVALUATION
  -> PROMOTION_EVIDENCE_PASSED | NOT_PROMOTED
```

Never skip directly from trainer exit code to benchmark opening. `OPENED_FOR_SINGLE_EVALUATION` is irreversible: if launch, model load, generation, scoring, or receipt writing fails after the opening receipt exists, the benchmark is still consumed. Do not silently retry.

## Preflight and protocol freezing

Before any GPU-heavy child:

1. Verify exact manifest, approval, seal, provenance, and source-code hashes.
2. Confirm there is no trainer, evaluator, or GPU lock.
3. Sample host RAM and total device VRAM.
4. Confirm every expected output path is absent.
5. Freeze the exact run ID, command, config, thresholds, resource ceilings, output paths, guard source hash, and benchmark policy in one protocol receipt.
6. Compile and lint operational guards **before** hashing/freezing them. Once a guard is protocol-bound or running, do not edit it.

If the loader is sequential and each optimizer step consumes `gradient_accumulation_steps * micro_batch_size` records, prove manifest coverage explicitly:

```text
examples_seen = max_steps * gradient_accumulation_steps * micro_batch_size
```

For one exact pass, require `examples_seen == admitted_record_count`. A nominally valid old step budget can silently omit the tail of a larger frozen manifest.

## Resource monitoring across Windows and WSL

When the GPU process runs in WSL but the machine is Windows-hosted:

- Monitor **Windows host RAM** from a Windows guard; WSL `psutil.virtual_memory()` may describe only the VM.
- Monitor total GPU allocation with `nvidia-smi --query-gpu=memory.used`, not just PyTorch-reserved memory.
- Preserve a separate PyTorch allocation ceiling inside the child.
- Use a write-once GPU-heavy lock and one child process group.
- Record initial/peak RAM, initial/peak total VRAM, sample count, trigger reason, child return code, command, log hash, and executed-guard hash.

Do not use loose command-substring probes as sole process evidence: the probe shell can match its own command text. Prefer token-aware process inspection (for example, an argument that ends with `scripts/train.py` or `scripts/evaluate_adapter.py`) and exclude the observer itself.

Keep Windows/WSL path identities explicit. For source bindings captured as Windows paths but verified in WSL, map with `PureWindowsPath` relative to the known project root rather than constructing malformed UNC strings ad hoc.

## Training verification gate

Before opening the benchmark, independently verify:

- report status and run ID;
- completed step count and final completion marker;
- exact admitted count and examples seen;
- manifest/config/source hashes;
- assistant-only label strategy and positive supervised-token count;
- adapter directory, required files, nonzero sizes, individual hashes, canonical adapter-tree hash, and readable tensor keys;
- guard status, resource peaks, log hash, and no trigger;
- authoritative run state;
- unchanged benchmark hash and zero prior evaluation references.

Write a `VERIFIED_TRAINING_COMPLETE` receipt with `benchmark_opened=false`. Wrapper exit code `0` is insufficient.

## Irreversible opening transaction

Only after training verification passes:

1. Recheck benchmark hash, seal receipt, unopened status, and absent one-shot outputs.
2. Copy the already linted evaluator guard into durable storage.
3. Write a create-once opening receipt binding:
   - benchmark path/hash and seal-receipt hash;
   - training-verification hash;
   - adapter-tree hash;
   - evaluator source hash;
   - evaluation-guard hash;
   - expected output path;
   - `open_count=1`;
   - the rule that any post-opening failure consumes the benchmark.
4. Launch exactly one guarded base-versus-candidate evaluator.

The opening receipt must exist **before** model inference starts. It is the exposure boundary.

## Independent evaluation verification

Do not trust stored summary counts alone. From captured response details:

1. Require exactly one base and one candidate response for every benchmark ID.
2. Match task types and IDs back to the frozen benchmark.
3. Re-run the frozen scoring function for every response.
4. Require recomputed per-record scores and aggregate summaries to equal the evaluator receipt.
5. Compute predeclared overall, delta, safety, schema, and per-task gates.
6. Scan durable evaluation receipts for the benchmark path/hash and require exactly one occurrence.
7. Write a consumed receipt and final verdict receipt.

If any promotion gate fails, use an explicit `NOT_PROMOTED` verdict while preserving successful mechanical evidence. Set `promotion_claimed=false`, `retuning_authorized=false`, `candidate_selection_authorized=false`, and `replacement_benchmark_authorized=false`.

## Post-run verification and cleanup

- Run the canonical test suite, lint, and type checks after model/evaluator completion.
- Bind protocol, model, guard, opening, evaluation, consumption, and final receipt hashes in a post-run receipt.
- Verify no trainer/evaluator and no GPU lock remain.
- Remove temporary operational scripts and test directories; keep the durable protocol copies.
- Report baseline RAM/VRAM after cleanup.

A WSL distribution can be immediately reawakened by an existing desktop console or file watcher. Do not terminate user-owned UI processes merely to make WSL show `Stopped`. Report separately that (a) no heavy child/lock remains and (b) WSL stays awake because of an identified reader.

## Worked evidence shape

A completed run should leave a directory resembling:

```text
runs/protocols/<run-id>/
  protocol.json
  train-config.json
  train_guard.py
  training-verification.json
  eval_guard.py
  benchmark-opening.json
  benchmark-consumed.json
  finalizer.py
  final-verification.json
  post-run-verification.json
```

The critical lesson is separation of authority: protocol creation authorizes bounded work; training verification authorizes one opening; opening consumes the benchmark; evaluation evidence may support a verdict but never authorizes deployment, broker access, or repeated tuning by itself.
