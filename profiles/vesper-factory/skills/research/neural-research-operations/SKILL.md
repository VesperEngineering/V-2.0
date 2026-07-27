---
name: neural-research-operations
description: Run bounded neural-network research experiments with continuous compute, fail-closed inference, reproducible artifacts, and a factual terminal HUD.
version: 1.1.0
---

# Neural Research Operations

Use for exploratory neural/representation-learning work where the user wants continuous GPU utilization and visible progress, but hypotheses must remain scientifically bounded and separate from production systems.

## Operating model

Separate **compute cadence** from **research-decision cadence**:

- Run predeclared replications, fixed seed batches, and fixed evaluation suites continuously when the GPU can support them.
- Do not let a scheduler autonomously invent new hypotheses, tune hyperparameters, or reuse examined holdouts.
- Between experiment families, require an explicit research question, frozen protocol, baseline, acceptance criterion, and rejection criterion.
- Keep exploratory code, data copies, environments, and artifacts outside production repositories and deployment paths.

## Required experiment contract

Before execution, record:

1. Question and scope: predictive, descriptive, robustness, or interpretability.
2. Frozen data cut, embargoes, seed list, model configuration, and metrics.
3. Baselines and what result would count as incremental evidence.
4. Explicit statement of what the test cannot establish.
5. Artifact paths: standalone script, JSON result, and research-log entry.

After execution, compile the script, preserve machine-readable results, and write an honest `VALIDATED`, `PARTIAL`, or `INVALIDATED` verdict. Negative results are successful research outputs.

## Representation-learning interpretation

Never assign a permanent semantic identity to an individual latent coordinate from one training run. Unconstrained latent spaces admit sign flips, rotations, and permutations across seeds.

To test whether a learned representation captures an observable:

1. Replicate across fixed independent seeds.
2. Evaluate the **full latent subspace** with an out-of-sample linear probe, alignment method, or other rotation-invariant test.
3. Separate contemporaneous/descriptive association from forward predictive value.
4. Downgrade or correct prior claims immediately when seed replication invalidates coordinate-level interpretation.

A healthy non-collapsed embedding and accurate latent-state prediction do not imply alpha, causal regimes, calibrated risk forecasts, or production suitability.

## Terminal observability

For long runs, emit unbuffered, phase-level output beyond epoch counters:

```text
training epoch N/M
Phase: training complete
Phase: encoding windows
Phase: fitting/evaluating probe
Phase: computing statistics
Phase: writing JSON artifact
Done
```

A run that has printed its final epoch may still be legitimately working through embedding extraction, fitting, statistics, and artifact writing. Verify with process state, GPU utilization, artifact presence, and fresh timestamps before diagnosing a hang.

Prefer a compact, factual terminal HUD over decorative dashboards:

- status, script, phase, elapsed time, and GPU telemetry;
- one compact model diagram (input → encoder → latent → predictor);
- evidence bars tied to actual baseline deltas;
- current scientific boundary and latest artifact status.

Avoid full-screen clearing redraws that flicker. Use a stable live renderer or in-place terminal updates that fit the viewport. Keep the layout boring, compact, and legible; do not invent progress, semantic labels, or green success indicators.

## Autonomous batch protocol

For unattended work:

1. Launch only a predeclared fixed batch (for example fixed seeds or folds).
2. Pause decision-oriented cron jobs that could overlap the batch.
3. Stream every child run through a local runner that updates a state/event file for the HUD.
4. After completion, read results before launching a new family.
5. Correct documentation and HUD claims immediately when a replication changes the conclusion.

## Consumer GPU constraints

When the user's GPU has limited VRAM (<24 GB, e.g. RTX 5070 Ti at 16 GB):

1. **Ask before defaulting.** The default config in most repos targets H100 (80 GB). Always check `nvidia-smi` or `torch.cuda.get_device_properties()` and tune before running.
2. **Key knobs to shrink** (in order of impact): `DEPTH` (layers), `DEVICE_BATCH_SIZE` (per-device batch), `TOTAL_BATCH_SIZE` (tokens/step), `MAX_SEQ_LEN` (context length), `WINDOW_PATTERN` (attention pattern).
3. **Start conservative** — ~3-4 GB peak for a 16 GB card. Bump up after a successful baseline.
4. **Move out of /mnt/c/.** Inside WSL2, keep the repo on the native Linux filesystem (`~/project`), not `/mnt/c/Users/...` — NTFS cross-mounts cause PyTorch memory-mapping I/O issues.

## WSL2 GPU passthrough

When the user is on Windows with an NVIDIA GPU:

1. NVIDIA driver for WSL installs on the **Windows host**, not inside WSL.
2. Verify with `nvidia-smi` inside WSL2.
3. Ubuntu 24.04 enforces PEP 668 (no system pip). Use `uv sync` + `uv run` instead — uv creates its own venv automatically.
4. The Hermes terminal runs on Windows, not WSL2. You cannot reach WSL2's filesystem from here. Give the user exact commands to paste into their WSL2 terminal.

## References

- `references/terminal-hud-and-representation-pitfalls.md` — practical HUD and latent-coordinate interpretation checklist.
- `references/autoresearch-setup-and-tuning.md` — karpathy/autoresearch setup, tuning for consumer GPUs, config values, and WSL2 workflow.
