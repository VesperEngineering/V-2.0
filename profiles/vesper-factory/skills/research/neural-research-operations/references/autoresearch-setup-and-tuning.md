# karpathy/autoresearch — Setup & Tuning for Consumer GPUs

> Agent-driven LLM pretraining research. The agent edits `train.py`, runs 5-min experiments, keeps or discards changes, and loops autonomously.

## Repo structure

| File | Role |
|---|---|
| `prepare.py` | Fixed — data download, BPE tokenizer, dataloader, eval. Do not modify. |
| `train.py` | Agent edits this — model, optimizer, training loop, hyperparameters. |
| `program.md` | Human edits this — agent instructions / "research org code." |
| `analysis.ipynb` | Notebook to analyze results. |

## Workflow

1. Clone → `uv sync` → `uv run prepare.py` (one-time data prep)
2. `uv run train.py` (baseline, ~5 min)
3. Point an AI coding agent at `program.md` with:
   ```
   Read program.md and kick off a new experiment. Do the setup first.
   ```
4. Agent loops: modify `train.py` → commit → `uv run train.py` → check `val_bpb` → keep or `git reset` → repeat

## Tuning for consumer GPUs (16 GB VRAM, e.g. RTX 5070 Ti)

Default config targets H100 (80 GB). Must shrink for <24 GB:

| Parameter | H100 default | 16 GB tune |
|---|---|---|
| `DEPTH` | 8 | 4 |
| `DEVICE_BATCH_SIZE` | 128 | 16 |
| `TOTAL_BATCH_SIZE` | 2**19 (524K) | 2**16 (65K) |
| `WINDOW_PATTERN` | "SSSL" | "L" |
| `MAX_SEQ_LEN` | 2048 | 1024 |
| `EVAL_TOKENS` | 40 * 524288 | 5 * 524288 |

Apply via `sed` in `train.py` and `prepare.py`:

```bash
# train.py
sed -i 's/^DEPTH = 8/DEPTH = 4/' train.py
sed -i 's/^DEVICE_BATCH_SIZE = 128/DEVICE_BATCH_SIZE = 16/' train.py
sed -i 's/^TOTAL_BATCH_SIZE = 2\*\*19/TOTAL_BATCH_SIZE = 2\*\*16/' train.py
sed -i 's/^WINDOW_PATTERN = "SSSL"/WINDOW_PATTERN = "L"/' train.py

# prepare.py
sed -i 's/^MAX_SEQ_LEN = 2048/MAX_SEQ_LEN = 1024/' prepare.py
sed -i 's/^EVAL_TOKENS = 40 \\* 524288/EVAL_TOKENS = 5 * 524288/' prepare.py
```

**VRAM budget:** With these changes, expect ~3-4 GB peak usage, leaving 12+ GB headroom. If it OOMs, reduce `DEVICE_BATCH_SIZE` to 8 and `DEPTH` to 3. If it runs with room to spare, bump `DEVICE_BATCH_SIZE` to 32 or `DEPTH` to 6.

## WSL2 + CUDA setup

Prerequisites: NVIDIA GPU, Windows 10/11 with WSL2 installed.

1. **Install NVIDIA driver for WSL** on the Windows host (not inside WSL) — [developer.nvidia.com/cuda/wsl](https://developer.nvidia.com/cuda/wsl)
2. **Inside WSL2**, verify GPU: `nvidia-smi`
3. **Install nvidia-cuda-toolkit** (optional, only if `nvidia-smi` missing): `sudo apt install nvidia-cuda-toolkit`
4. **Keep repo on WSL2 filesystem** (`~/autoresearch`), not `/mnt/c/...` — NTFS cross-mounts cause I/O overhead and PyTorch memory-mapping issues.

## PEP 668 / uv workflow

Ubuntu 24.04 blocks system pip. Use `uv sync` instead — it creates its own venv automatically:

```bash
uv sync
uv run prepare.py
uv run train.py
```

Do not use `pip install` directly. `uv run` handles the venv transparently.

## Data source

Training data is `karpathy/climbmix-400b-shuffle` from HuggingFace (public, no API keys). Downloads parquet shards, trains a BPE tokenizer (vocab size 8,192). No external API calls.

## Metric

`val_bpb` (validation bits per byte) — lower is better, vocab-size-independent, comparable across architectural changes. Fixed 5-minute wall-clock time budget.