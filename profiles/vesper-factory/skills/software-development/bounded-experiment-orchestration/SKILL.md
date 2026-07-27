---
name: bounded-experiment-orchestration
description: Run continuous, reproducible CPU or GPU research batches with fail-closed gates, durable receipts, and a truthful terminal HUD.
version: 1.3.1
---

# Bounded Experiment Orchestration

Use for exploratory ML/data research that should run autonomously for hours while preserving scientific discipline, reproducibility, and user visibility.

## Core separation

Separate two loops:

1. **Continuous compute:** fixed seeds, fixed parameter matrices, and fixed baselines may run back-to-back on the declared CPU or GPU resource.
2. **Research decisions:** deciding a new hypothesis is gated by prior evidence; never let a runner invent hypotheses, retune after results, or re-open an examined holdout.

## Required artifacts for every experiment

- Standalone numbered script.
- Frozen protocol/manifest entry before execution.
- Unbuffered phase logs: data admission, training, embedding extraction, evaluation, statistics, result write, done.
- Machine-readable JSON result artifact.
- Markdown research-log verdict: `VALIDATED`, `PARTIAL`, `INVALIDATED`, or `BLOCKED`.
- Explicit scope and non-production boundary.

## Small-model pilot admission and frozen comparison

For a local LLM pilot, separate **pipeline proof** from **quality evidence**:

1. Admit only records with provenance and an explicit `review_status=APPROVED`. Keep generated, templated, or agent-authored candidates as `PENDING_HUMAN_REVIEW`; enforce this in the admission validator, not merely in documentation.
2. Create deterministic, disjoint train and holdout manifests before training. Record their SHA-256 hashes in each training and evaluation receipt. When promoting variants derived from seed records, persist a `derived_from` lineage field and exclude every candidate derived from a frozen-holdout ID—even under a blanket approval—so paraphrases cannot leak holdout semantics into training. Write a versioned merged training manifest; do not reshuffle the original split.
3. Maintain an **independent benchmark** of at least 30 cases that is authored separately from the training seed and never mixed into training. Use this as the primary quality evidence; reserve a small regression holdout for quick consistency checks only.
4. Start with a deliberately bounded mechanics baseline (fixed seed, small step count, fixed model/configuration). Label it mechanics-only; falling training loss does not establish capability.
5. Evaluate the untouched base and adapter on the independent benchmark with deterministic gates that reflect the product contract—such as structured-output parseability, required audit terms, and refusal of execution language—not loss alone.
6. A tied or zero-pass base/adapter result is valid negative evidence. Preserve it, surface it in the operator UI, and improve reviewed data or task design before spending additional GPU time. Do not tune repeatedly against the same small holdout or benchmark.
7. Watch for **schema collapse**: if the model emits one task's schema for every prompt, the corpus is too narrow. Add task-diverse examples with distinct required keys before adding training steps.
8. If a holdout manifest changes for any reason, its hash changed: rerun the comparison and retain a new receipt. Never apply an earlier comparison to altered data.

See `references/local-llm-pilot-admission.md` for a compact artifact layout and verification checklist. See `references/structured-output-local-llm-pilot.md` for manifest-lineage auditing, assistant-only label masking, truncation fail-closure, development-holdout gates, and untouched-benchmark hygiene. See `references/local-llm-windows-console.md` for a native Windows Tkinter console bridged to a WSL-based bounded training/evaluation pipeline, including dataset admission, frozen-holdout promotion guard, independent benchmark, and honest evidence display.

## One-time sealed-benchmark promotion runs

Treat the benchmark opening as an irreversible transaction, not the evaluator command. First independently verify training completion and full manifest coverage; then write a create-once opening receipt that binds the exact adapter, evaluator, guard, and sealed benchmark before inference starts. Any failure after that receipt consumes the benchmark and forbids silent retry.

Independently rescore every captured response and require exactly one durable evaluation reference to the benchmark path/hash. Keep `NOT_PROMOTED` distinct from mechanical success, and preserve explicit false authority for retuning, candidate selection, replacement-benchmark creation, deployment, and execution when gates fail. On Windows-hosted WSL runs, monitor host RAM outside WSL and total device VRAM through `nvidia-smi`; do not mistake WSL VM memory or PyTorch-only counters for whole-machine bounds.

See `references/one-time-sealed-benchmark-promotion.md` for the evidence-state machine, full-manifest step arithmetic, Windows/WSL guard pattern, irreversible opening transaction, independent rescoring, receipt layout, and cleanup caveats.

## Development after benchmark consumption

After a sealed benchmark is consumed, quarantine its cases, responses, detailed scores, and failure traces from all later development decisions. Build and freeze an explicitly `DEVELOPMENT_ONLY` challenge set, run a bounded sequential capacity-versus-schedule tournament, and stop at the predeclared training-job ceiling. Count a trainer child launch conservatively even when a resource guard stops it before optimizer steps; only a preflight failure before child launch is free of the training-job budget.

If first-time model download or loading breaches host RAM before GPU placement, preserve the failed launch, complete and hash the model snapshot in a separate guarded non-training prefetch, then bind an offline recovery run under an immutable protocol revision. Never weaken resource limits to make the retry pass. On Windows/WSL, fall back to native WSL SHA-256 when a Windows guard cannot traverse a `/home` project symlink; do not confuse traversal failure with byte or CRLF drift.

If a verified model trains within bounds but a combined base-versus-adapter evaluation does not, preserve training and split inference into separately guarded base and adapter processes using the exact production loading/generation/scoring contract. Allow proactive WSL page-cache reclaim only below the hard ceiling, check a hard-limit breach before reclaim, rate-limit and receipt every reclaim event, then merge immutable partials deterministically and independently rescore the canonical result. Tooling failures before model load require a new protocol revision but do not consume a training job.

At campaign closure, reconcile late background notifications against their exact phase/protocol receipts rather than treating an old wrapper exit as current state. If the bounded matrix is exhausted without a gate-passing candidate, freeze `NO_WINNER`, keep the research leader distinct from a selected winner, preserve configured verification-scope output, and issue a cleanup receipt before deleting temporary operational copies. A diagnosis that human-approved data composition is the next lever grants no data-admission or training authority.

When the next mission is data-composition preparation, freeze an immutable protocol before touching candidate artifacts, derive only abstract failure classes from authorized development evidence, author candidate and `DEVELOPMENT_ONLY` concept banks separately, and stop at an exact path-and-SHA human decision. Explicitly require rubric terms in both the prompt and complete assistant target, verify full-target preservation with the production tokenizer, and perform overlap checks only after generation so quarantined holdouts or benchmarks cannot influence authoring. Budget the interaction loop to produce one end-to-end artifact slice before broad refinements; if the ceiling interrupts a final provenance enhancement, return `NOT_READY` rather than treating earlier dry-run evidence as a completed packet. See `references/human-gated-data-composition.md`.

See `references/post-consumption-local-llm-development.md` for quarantine-safe development evidence, offline prefetch receipts, conservative run accounting, immutable recovery revisions, WSL source-binding fallback, memory-safe split evaluation, late-notification reconciliation, no-winner closure, and mid-campaign resume packets.

## Queue design

Use a manifest as the sole source of truth. Each item must have: ID, question, dependency IDs, script, artifact path, primary metric, stop rule, and status (`PENDING`, `RUNNING`, `COMPLETE`, `BLOCKED`).

A queue worker may lease one dependency-ready item at a time. It must stop on nonzero exit, missing artifact, failed guard, or ambiguity; write a receipt; and never mutate parameters or create work items. Use cron only as a watchdog, never as a second worker — with one proven exception: a periodic cron tick MAY act as the leasing worker when (a) a run lock prevents overlap, (b) each tick runs at most one item, and (c) a window gate makes off-window ticks cheap, honest no-op receipts. For operator-owned compute boxes, gate resource-heavy research to off-hours (e.g. weeknights 18:00–07:00 local, weekends continuous) rather than running continuously — the operator's daytime workstation and market-hours pipeline take precedence. See `references/research-island-window-gated.md` for the proven window-gated island skeleton (producer/lease/runner, schema-validated artifacts, kanban bridge) and its build pitfalls.

**Prefer a generic spec-driven probe over per-experiment scripts.** When research directions arrive as natural-language hypotheses (scan agent, kanban card), a single parameterized runner — spec JSON `{features, horizon, train_end, alpha}` embedded in the queue item, a registered feature vocabulary, one fixed walk-forward protocol, one artifact schema — turns approved directions into runnable queue entries as pure data, no bespoke code per hypothesis. Reserve numbered standalone scripts for hypotheses the registry genuinely cannot express. Gate the vocabulary: only registered feature names and bounded horizons/budgets pass validation, so a malformed direction fails closed instead of running arbitrary work.

## Milestone build order and resumable checkpoints

For a multi-stage research milestone, prove the thinnest complete experiment before building the full scheduler, ledger UI, or broad candidate family. The order is: bind control-plane identities; freeze a minimal complete protocol; test protocol/data/feature/evaluator boundaries; execute and read back one supervised baseline; then add trained candidates, durable orchestration, and recurrence. This prevents a finite interaction budget from expiring with infrastructure but no real experiment.

Treat the agent/tool interaction ceiling as part of the bounded-run budget. Around the halfway point, stop broad discovery and drive one end-to-end slice to real artifact readback. Before any long background process, persist its session/process ID, exact command, expected outputs, timeout, and verification command. A launched process without exit/artifact readback remains `HOLD_AUDIT_INCOMPLETE`.

For the CPU cross-sectional ranking variant—including point-in-time data coverage, adjusted/raw fallback safeguards, buffered weekly portfolios, per-experiment evidence, and one-time holdout opening—see `references/cpu-ranking-milestone-lifecycle.md`.

## Scientific guardrails

- Compare neural representation against simple baselines before adding architecture complexity (e.g., PCA and linear autoencoder).
- Treat a single neural coordinate as non-identifiable: sign flips and rotations across random seeds are expected. Test full-subspace probes or alignment, not `dimension N means X` claims.
- Report every predeclared parameter-matrix row; do not select/tune from an already viewed evaluation period.
- Distinguish ordering/correlation from calibrated-level forecasting. A strong correlation plus strongly negative R² is descriptive state structure, not a usable forecast.

### Bounded tuning receipts and exhaustion stops

For periodic model tuning, persist one manifest before the first run: frozen baseline artifact hash and metrics, a finite candidate matrix, per-trial status, acceptance gate, and result-artifact paths. Each tick leases one candidate, snapshots active source/artifacts before training, and restores them on every rejection or error. A saved model is not evidence of improvement; promotion requires every declared gate to pass.

Treat an unchanged candidate artifact hash or identical metrics as a no-op, not a fresh promising result. If a bounded capacity/regularization matrix yields only marginal gains or repeated no-ops, stop rather than spend the remaining budget on adjacent micro-variations. Preserve the baseline, mark the matrix exhausted, and move to a new hypothesis family or protocol. Repeated evaluation of the same split cannot create an untouched holdout; label it retrospective and reserve independently locked folds or newly arriving data for promotion evidence.

When external market data must be refreshed during research, separate that mutation from the fixed candidate matrix: finish or pause the current lease, refresh the approved canonical source, verify the source and local mirror independently, then begin a new protocol. Do not silently mix refreshed data with earlier candidate results.

## Terminal HUD

Keep it compact and boring: top-line current script/phase/compute resource, a small network diagram, evidence bars with actual values, current/queued matrix rows, and recent activity. Do not invent progress, fake green states, or bury the model diagram below the fold.

Use a terminal live renderer/alternate screen rather than manual clear-screen redraw loops. Keep the last artifacts visible after completion.

## Interactive operator workflow

When the experiment runs in a user-owned terminal that the agent cannot directly access:

1. State the boundary plainly; do not imply that the agent can inspect or edit that terminal.
2. When directory movement is required, put the navigation command first. Then give one exact command block at a time and wait for the user’s output before issuing dependent commands.
3. Never make the user paste Python source, shell prompts, PowerShell prompts, or transcript text into a shell. Clearly distinguish source edits from commands that apply edits.
4. Keep Windows/PowerShell and WSL/Linux instructions separate. If a prompt shows `>>`, first recover with `Ctrl+C`; from PowerShell, enter only `wsl`; then `cd` into the WSL-native project path.
5. After every patch, verify the exact lines before running a long experiment. Run a syntax/compile check before a five-minute GPU run.
6. Preserve the user’s current working configuration; do not silently switch from a chosen patching method to an editor or rewrite the approach mid-step.
7. For long Markdown/config contracts with nested fences, hashes, or literal tabs, create an actual host-visible file instead of relying on rendered chat. Read it back completely, hash it, and provide one copy command into the target workspace; preserve the upstream file and review the domain copy separately.

## Adapting reference research repositories

Before setup, inspect whether the upstream project is a reusable framework or a self-contained experiment driven by an external agent. State explicitly whether the plan will run upstream as written, use it as a template, or recreate its pattern in the target project. Never describe a custom domain adaptation as the upstream repository’s documented workflow.

For template ports, preserve the upstream control surface and distinguish two phases explicitly: (1) a one-time reviewed domain bootstrap that replaces domain-specific data/evaluation, baseline trainer, and dependencies; (2) the steady-state autonomous loop, where the human-authored instruction file is fixed and the external coding agent edits only the declared experiment file. Do not silently replace an external-agent loop with a Python grid or hardcoded mutation list; inspect loop ownership in generated files before claiming the adaptation is source-faithful.

When the user wants to inspect and edit an instruction file collaboratively, read the exact upstream revision yourself instead of asking them to paste a long terminal/editor transcript. Preserve the original, edit a review copy, and compare a diff before replacement. On WSL, a GUI editor may open the review copy with `notepad.exe "$(wslpath -w <file>)"`; make clear that the editor is optional and that Markdown belongs in the editor, not at the Bash prompt.

Verify the installed coding-agent CLI with `--help` before giving launch flags. Launch the agent first, wait until its interface is visibly open, and only then provide the natural-language prompt; otherwise users may paste Markdown into Bash. If this boundary is uncertain, stop before any autonomous writes.

See `references/autonomous-research-repo-adaptation.md` for the repository-classification checklist, Karpathy autoresearch structural audit, and version-specific Codex launch notes.

## GPU-port and kernel compatibility

For Blackwell-class GPUs (sm_120), first check the wheel before blaming hardware or toolkit: a CPU-only build (`torch.__version__` ending in `+cpu`) masquerades as a CUDA/toolkit problem. The Windows-native fix is a matching wheel, not a toolkit upgrade — with a recent NVIDIA driver, `uv pip install torch --index-url https://download.pytorch.org/whl/cu128` into a dedicated venv yields working CUDA (`get_device_capability(0) == (12, 0)`). Verify with a real on-device matmul, not just `torch.cuda.is_available()`.

Treat upstream hardware assumptions as part of the protocol. A precompiled attention kernel can fail on a newer GPU with `no kernel image is available for execution on the device`; this is a compatibility failure, not a model-quality result. Establish a tight smoke-test reproduction, then use a supported PyTorch native `scaled_dot_product_attention` fallback when the configured kernel lacks the GPU architecture. Verify tensor layout (`[B,T,H,D]` to `[B,H,T,D]` and back) and run `py_compile` before training.

For a smaller GPU, start with a conservative model/batch configuration, then change one hardware variable at a time. Keep the fixed wall-clock budget and record `val_bpb`, peak VRAM, tokens processed, and parameter count. Native SDPA may reduce throughput; the script’s H100-referenced MFU is not a trustworthy utilization measure for another GPU.

Keep gradient accumulation valid:

```text
TOTAL_BATCH_SIZE % (DEVICE_BATCH_SIZE * MAX_SEQ_LEN) == 0
```

If adapting upstream `prepare.py` (for example, shorter context or smaller evaluation), document that protocol deviation because comparisons are no longer identical to upstream. No model-provider API key is required when the training corpus is downloaded from the repository’s configured public dataset source.

## Fixed-budget interpretation

Under a fixed time budget, model capacity and throughput trade off directly. A deeper model can produce a worse validation metric if it processes substantially fewer tokens, even when it uses more VRAM. Select or retain configurations by the declared metric and protocol, not by memory utilization alone. When a trial is worse or OOMs, restore the last confirmed-good configuration and record the trial as discarded/crashed; do not continue tuning from an inferior state.

## Scheduled-tick delivery contracts

A bounded cron tick can have a deliberately minimal delivery contract (for example, an exact `[SILENT]` response before a terminal run) while still requiring complete durable evidence. Treat the manifest, logs, receipts, artifact hashes, and restoration verification as the source of operational truth; do not omit those steps merely because the outward response is silent. Conversely, when the contract says exact silence, return exactly that token after finalization—do not append a success summary, metrics, or verification narration. Deliver the consolidated experiment report only at the explicitly declared terminal milestone.

### Temporary-verifier cleanup overrides silent delivery

For an external temporary verifier, cleanup is part of finalization. Remove it from outside its leaf, then assert the leaf is absent. On Windows, a completed Python process can leave a directory briefly busy even after the verifier printed a passing result; wait once and retry from the verifier's parent. If Git Bash removal still reports `Device or resource busy`, inspect the leaf from outside it and retry with the platform removal path (for example `cmd.exe /c rmdir /s /q <native-path>`), then assert absence. Do not create another verifier or rerun the experiment merely to clear a locked leaf.

If removal remains unverified, do **not** return `[SILENT]` or imply a clean terminal result: preserve the durable receipt, leave the experiment fail-closed, and return a concise cleanup blocker that distinguishes the passed verifier from the failed cleanup gate. A successful verifier assertion does not compensate for an unverified cleanup gate.

## Verification

Before reporting completion: compile scripts, verify the result artifact exists and parses, confirm the research log reflects the actual verdict, and check that no protected production path was modified.

See `references/jepa-research-lessons.md` for concrete lessons from a raw-OHLCV JEPA program. See `references/karpathy-autoresearch-blackwell.md` for the Blackwell/WSL2 compatibility and fixed-budget experiment notes.
