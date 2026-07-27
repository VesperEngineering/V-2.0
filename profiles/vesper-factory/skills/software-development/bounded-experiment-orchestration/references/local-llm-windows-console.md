# Local LLM pilot with native Windows console

A compact pattern for a bounded local GPU specialist-model pilot that exposes state, controls, and honest evidence through a clickable Windows Desktop console.

## Architecture

```
Windows Desktop (.lnk)
   ├── launches pythonw.exe + scripts/windows/research_console.py
   │
   └── native Tkinter/ttk app polls WSL state asynchronously

WSL2 (Ubuntu)
   ├── dataset admission, training, evaluation scripts
   ├── durable JSON state in ~/vesper-model-storage/runs/state/current.json
   └── bounded JSON exporter scripts/wsl/export_dashboard_state.py
```

Keep large mutable artifacts (datasets, adapters, receipts) in native WSL storage. Keep source on the Windows/Desktop bridge. Retrieve state through fixed WSL commands, not through `\\wsl$` paths.

## Components

### 1. Dataset admission gate (`dataset_admission.py`)

- Validate every SFT record for required fields, provenance, and `review_status=APPROVED`.
- Reject `PENDING_HUMAN_REVIEW` records at admission time.
- Produce disjoint train/holdout manifests and record SHA-256 hashes.

### 2. Seed corpus + candidate generation

- Author a diverse seed corpus with task-specific schemas and rubrics.
- Generate candidates by varying seed records (contexts, wording).
- Attach `derived_from` lineage to every candidate.

### 3. Frozen-holdout promotion guard (`promotion.py`)

Even under a blanket user approval, exclude every candidate whose `derived_from` ID is in the frozen holdout set. This prevents paraphrased holdout semantics from leaking into training. Write a versioned merged manifest and a promotion receipt.

### 4. Independent benchmark

Create at least 30 cases authored separately from the training seed. Never mix it into training. Use it as the primary quality evidence; keep a small regression holdout only for quick consistency checks.

### 5. Bounded training (`scripts/train.py`)

- Load typed `TrainingConfig` with upper bounds on steps/sequence length.
- Block on missing manifest.
- Prevent overlapping runs via durable state.
- Save adapter, report, and receipt with hashes.

### 6. Frozen evaluation (`frozen_evaluation.py`, `scripts/evaluate_adapter.py`)

- Generate responses from untouched base model and from adapter.
- Score deterministic gates: JSON/schema validity, required rubric terms, execution safety.
- Report each gate separately; do not reduce to a single opaque score.
- Accept `--manifest` and `--name` so the same runner can evaluate regression holdout or independent benchmark.

### 7. Native Windows console (`scripts/windows/research_console.py`)

- Tkinter/ttk dark dashboard: status, run ID, phase, recent activity.
- Two Canvas illustrations:
  - training progression node diagram (Data → Train → Eval → Report);
  - research-only inference path (Thesis → Specialist model → Schemas/tools → Research package).
- Asynchronous WSL state refresh and a bounded "Run training" button.
- Desktop shortcut via `pythonw.exe` to avoid console flash.

## Verification checklist

- `pytest -q` passes.
- `ruff check src tests scripts/windows` passes.
- `mypy src` passes.
- `python -m py_compile` on all scripts.
- `--smoke-test` prints real state without opening a window.
- Actual Desktop `.lnk` launches a titled, responsive native window.

## Honest evidence posture

- Label the first mechanics baseline as pipeline-proof only, not quality evidence.
- Surface negative/tied results in the UI instead of hiding them.
- Do not claim model quality, trading value, or readiness from training loss alone.
- Execution-safety gate must refuse phrases like "buy shares", "place a market order", "execute trade".
