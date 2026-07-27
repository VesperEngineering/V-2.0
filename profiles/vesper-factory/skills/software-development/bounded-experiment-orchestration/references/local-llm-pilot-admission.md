# Local LLM pilot: admission and frozen evaluation

## When to use this pattern

You are building a small specialist LLM on a local GPU (e.g., 16 GB consumer card) for an auditable, non-execution task such as research specification, leakage audit, protocol design, or result interpretation. The goal is to separate **pipeline mechanics** from **quality evidence** before spending larger GPU budgets.

## Hybrid Windows/WSL layout

Keep source code on the Windows side (e.g., `C:\Users\<user>\Desktop\Vesper-Model-Lab`) and large mutable artifacts in native WSL storage (e.g., `~/vesper-model-storage`) to avoid `\\wsl.localhost\` path fragility and cross-filesystem performance issues.

```text
project/                          # Windows Desktop or repo
├── configs/
│   └── train-qlora-1_5b.json     # bounded run config
├── scripts/
│   ├── train.py                  # bounded QLoRA pipeline
│   ├── evaluate_adapter.py       # base-vs-adapter runner
│   ├── build_seed_dataset.py     # seed + holdout + benchmark
│   ├── build_candidate_corpus.py # templated variants
│   ├── promote_candidates.py     # merge approved candidates
│   └── windows/research_console.py # native Tkinter bridge
└── src/<package>/
    ├── dataset_admission.py      # validate records, split manifests
    ├── seed_corpus.py            # authored seed examples
    ├── benchmark_corpus.py       # independent untouched benchmark
    ├── candidate_corpus.py       # templated variants
    ├── candidate_review.py       # structural review gate
    ├── promotion.py              # derived_from holdout guard
    └── frozen_evaluation.py      # deterministic response scoring

storage/                          # WSL native: ~/vesper-model-storage
├── datasets/
│   ├── raw/                      # immutable source dump
│   ├── candidates/               # PENDING_HUMAN_REVIEW variants
│   ├── review/                   # queue + promotion receipts
│   └── splits/
│       ├── quant_research_sft_manifest.jsonl
│       ├── quant_research_holdout.jsonl       # regression holdout
│       └── quant_research_benchmark.jsonl     # untouched benchmark
├── models/adapters/<run-id>/
├── runs/reports/<run-id>.json
├── runs/evaluations/<run-id>-<name>.json
└── runs/state/current.json       # console-visible state
```

## Record contract

Every admitted record must carry these fields:

```json
{
  "id": "factor-spec-001",
  "task_type": "factor_spec",          // factor_spec | leakage_audit | research_protocol | result_interpretation
  "messages": [
    {"role": "system", "content": "You are a quant-research specification and audit assistant. Research only."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "<JSON payload>"}
  ],
  "provenance": {"kind": "authored_seed", "license": "internal", "source_id": "vml-001"},
  "review_status": "APPROVED",         // admission validator rejects anything else
  "evaluation": {                      // task-specific rubric
    "required_keys": ["factor", "data_requirement", "rebalance", "falsifier"],
    "required_terms": ["timestamp"]
  }
}
```

For generated or templated candidates, use `review_status: PENDING_HUMAN_REVIEW` and add `derived_from: <seed-id>` so promotion can enforce holdout independence.

## Three-way split

1. **Training manifest** — reviewed, approved records used for SFT.
2. **Regression holdout** — small seed-derived set for quick regression checks between runs. Do not tune against it.
3. **Independent benchmark** — ≥30 fully separate, never-seen examples authored from scratch. This is the primary quality evidence.

Use `dataset_admission.admit_dataset()` to create deterministic train/holdout splits from the seed corpus, then write the benchmark corpus separately so it cannot be reshuffled into training.

## Promotion with frozen-holdout guard

Never promote all approved candidates blindly. Filter out any candidate whose `derived_from` ID appears in the frozen holdout, even if the human approved the whole queue:

```python
promoted, rejected = promote_candidates(candidates, {record["id"] for record in holdout})
```

Write a versioned merged manifest (`quant_research_sft_manifest_v3.jsonl`) and a promotion receipt that records original train count, promoted count, excluded count, and the SHA-256 of both manifests.

## Training bounds

Fix before the run:

- seed, max_steps, learning_rate, sequence_length
- micro_batch_size, gradient_accumulation_steps
- base model, method (e.g., QLoRA 4-bit), adapter config
- dataset_manifest and holdout_manifest paths

Label the first successful run as **mechanics-only**. Training loss going down is not quality evidence.

## Frozen evaluation

Evaluate the untouched base model and the trained adapter on the **independent benchmark** (not the regression holdout) with deterministic gates:

1. **Schema/JSON validity** — assistant output parses and contains the required keys for that task type.
2. **Required terms** — point-in-time / holdout / timestamp / execution-safety language appears as required by the rubric.
3. **Execution-safety gate** — response contains no broker/execution language such as "buy shares", "sell shares", "place a market order", "execute trade".

Report each gate separately; do not reduce to a single opaque score.

Run with:

```bash
python scripts/evaluate_adapter.py \
  --storage-root ~/vesper-model-storage \
  --run-id <run-id> \
  --manifest datasets/splits/quant_research_benchmark.jsonl \
  --name benchmark
```

## Console bridge

Use a native Windows Tkinter window rather than curses over raw `wsl.exe`, because raw WSL launches may lack `TERM` and a TTY. The GUI retrieves state through bounded WSL JSON commands:

```bash
wsl.exe bash -lc 'source ~/vesper-model-storage/venv/bin/activate && python scripts/wsl/export_dashboard_state.py --storage-root ~/vesper-model-storage'
```

Surface honest status: COMPLETE/BLOCKED/EVALUATING, current run ID, phase, and the latest base/adapter gate counts. Never fake green states.

## Common pitfall: schema collapse

A small corpus dominated by one task type can cause the model to emit the same schema for every prompt. If factor-spec, protocol, or result-interpretation cases fail by producing a leakage-audit JSON, the fix is more **task-diverse examples with distinct required keys**, not more training steps on the same data.

## Verification checklist

- [ ] `pytest -q` passes.
- [ ] `ruff check src tests` and `mypy src` pass.
- [ ] All modified scripts `py_compile`.
- [ ] Train/holdout/benchmark IDs are disjoint.
- [ ] No `PENDING_HUMAN_REVIEW` record in a training manifest.
- [ ] Promotion receipt records excluded count and frozen-holdout hash.
- [ ] Training receipt includes config/manifest hashes, peak VRAM, and explicit scope.
- [ ] Evaluation receipt includes manifest hash, base summary, adapter summary, and per-item gate results.
- [ ] Adapter path exists and loads.
- [ ] Console smoke test shows the latest run and comparison result.
