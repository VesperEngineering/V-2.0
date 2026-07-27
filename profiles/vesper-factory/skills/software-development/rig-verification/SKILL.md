---
name: rig-verification
description: Verify whether a user's hardware/software rig can run a given open-source project from GitHub. Cross-check requirements, identify bottlenecks, map upgrade paths.
category: software-development
triggers:
  - "can my rig run X"
  - "verify our rig to this repo"
  - "hardware compatibility check"
  - "will this work on my machine"
  - "system requirements assessment"
---

# Rig Verification Workflow

## 1. Fetch the Project Requirements

- Extract the repo's README from `raw.githubusercontent.com` via curl
- Also check `api.github.com/repos/<owner>/<repo>` for metadata (language, topics, size)
- If available, check any `requirements.txt`, `setup.py`, `Dockerfile`, or `docs/` for hardware specs

## 2. Identify Exact Hardware for Purchase Evaluations

When assessing a listing, establish the **CPU/APU, iGPU or GPU, RAM topology, and upgradeability** before issuing a buy/pass verdict. A seller's short model string, internal SKU, or sticker/component identifier does not by itself identify the silicon.

1. Prefer the manufacturer's product page or the listing's complete CPU line (for example, `Ryzen 7 7840HS`) and full SKU.
2. For a local-LLM mini PC, name the iGPU generation explicitly: Radeon 680M/780M-class graphics differ materially from older vague `Radeon Graphics`/Vega listings.
3. Verify whether RAM is replaceable and whether the system has two SODIMM slots; installed capacity alone does not prove a viable upgrade path.
4. If an identifier does not resolve authoritatively, say it is unmapped and request the listing link or full specifications. **Do not classify an unfamiliar identifier as a fan or other component without a source.**
5. Treat a seller who cannot provide the CPU as a pass for performance-sensitive purchases.

## 3. Profile the User's Rig

This user runs **Windows 10/11 with WSL2** (git-bash for terminal, WSL2 Ubuntu for Linux workloads). Check **both sides**:

### Windows side (via git-bash terminal)
```
nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap --format=csv
python --version
gcc --version              # MinGW available?
```

### WSL2 side (via `wsl.exe -- bash -lc '...'`)
```
nvidia-smi ...              # GPU visible in WSL?
uname -r
python3 --version
nvcc --version              # CUDA toolkit version
python3 -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.version.cuda)"
free -h                     # RAM available
df -h /                     # Disk space
lscpu | grep -E "Model name|CPU|Core|Thread"
gcc --version && make --version
grep -o "avx2\|avx512f\|avx512_vnni" /proc/cpuinfo | sort -u   # CPU feature check
mount | grep -E "ext4|drvfs|9p"                               # Filesystem type check
nvcc --list-gpu-arch 2>/dev/null | tail -5                    # What GPU arch CUDA supports
```

### Why both sides matter
- The WSL2 VM has its own RAM allocation (configured via `%USERPROFILE%\.wslconfig`)
- CUDA toolkit versions can differ between Windows and WSL2
- PyTorch may only be in a specific venv/conda, not the system Python
- Disk filesystem type matters: ext4 (good), VHDX (variable), 9p/drvfs/NTFS-cross-mount (bad for model I/O)

## 3. Compare Against Repo Requirements

Build a PASS / WARN / FAIL table:

| Requirement | User's Rig | Status |
|---|---|---|
| CPU with AVX2 | (check) | |
| gcc + OpenMP | (check) | |
| ≥ N GB RAM | (check) | |
| Disk space | (check) | |
| GPU compute cap | (check) | |
| CUDA toolkit version | (check) — critical for GPU arch compat | |

### Key mismatch patterns
- **CUDA toolkit vs prebuilt wheels — don't conflate them.** `nvcc --version` (toolkit) only matters for COMPILING CUDA code. Prebuilt PyTorch wheels ship their own CUDA runtime + kernels; what matters is (a) the driver (`nvidia-smi`) and (b) the wheel's CUDA build tag. Verified 2026-07-19 on this rig: WSL2 toolkit 12.0 looked "too old for sm_120 (RTX 50-series)" and was recorded as a blocker for months — the actual problem was a CPU-only torch wheel (`2.12.1+cpu`). One install fixed it, no toolkit upgrade: `uv venv .venv-gpu && uv pip install --python .venv-gpu/Scripts/python.exe torch --index-url https://download.pytorch.org/whl/cu128` → `torch 2.11.0+cu128`, `torch.cuda.is_available()=True`, `get_device_capability(0)=(12,0)`. sm_120/Blackwell needs `cu128`+ wheels; driver 610.x was always sufficient. A stale "toolkit too old" note in memory/docs is not evidence — check `torch.version.cuda` and run a real on-device op (e.g. a small matmul) before declaring the GPU blocked.
- **RAM tight**: The repo's stated minimum vs 19 GB WSL2 allocation vs swap saturation. Community benchmarks on similar configs are the best indicator.
- **CPU features**: AVX-512 VNNI is a positive signal — it enables the repo's fastest int8 matmul path.

## 4. Deliver Real-World Expectations

The repo's stated requirements and community benchmarks differ. Be honest:

- **"It runs"** vs **"it's usable"** are different answers
- Reference the repo's own community benchmark table for comparable hardware
- Explain bottleneck physics: e.g., "cold token requires ~11 GB disk reads; at N GB/s that's X seconds"
- Default policy: CPU-only path works, GPU tier is optional acceleration, not required

## 5. Upgrade Paths (Tiers)

When asked for upgrade options, present in terms of the bottleneck hierarchy:

| Tier | What | Effect | Cost class |
|---|---|---|---|
| **Software** | Configure WSL2 RAM, install correct CUDA toolkit | Removes artificial constraints | $0 |
| **RAM** | More DDR5 on AM5 board | Biggest perf lever per dollar — expert cache expansion | Medium |
| **CPU** | Drop-in Ryzen 9 upgrade (same socket) | Linear matmul scaling with core count | High |
| **Cloud** | Rent GPU box, run it remotely, hit API locally | No hardware changes, pay per hour | Variable |

### Budget Mini-PC Purchase Guidance

For budget local-AI mini-PC requests, establish the target spend *before* suggesting premium appliances. State the role accurately: an iGPU mini PC is usually an always-on sidecar for small local models, embeddings, retrieval, summaries, and low-risk triage—not a substitute for a discrete CUDA GPU or frontier-model reasoning.

- In a sub-$600 tier, prioritize **32 GB minimum / 64 GB preferred**, a named 8-core Ryzen APU, upgradeable dual-SODIMM memory, and an NVMe path over NPU marketing.
- Radeon 680M/780M uses shared system memory. Explain the distinction from a discrete GPU; do not imply it will match the user's existing NVIDIA GPU.
- For llama.cpp/Ollama-style workloads, a costly NPU generation bump alone is rarely a decisive upgrade. Compare CPU/APU, iGPU tier, RAM, and memory bandwidth first.
- Treat OCuLink as optional future eGPU expansion, not value already included in the listing. Note its shutdown-before-connect/disconnect requirement when visible on the chassis.
- Give a concise **Buy / Negotiate / Pass** verdict plus a pickup test: boot, confirm CPU/RAM/SSD, inspect thermals and fan noise, then test display, Wi-Fi/Ethernet, and ports. “Used for gaming” does not verify hardware or condition.

### Runtime model-capacity verification

For a user who already has Ollama or another local server installed, measure a representative model on the existing rig before turning a hardware recommendation into a purchase plan. Model-file storage is not runtime memory: loaded weights, CPU offload, backend overhead, and the KV cache can make the resident footprint substantially larger.

1. First establish the execution constraint. If the user requires Windows/CUDA compatibility, rule out macOS and AMD/Intel iGPU paths even when their unified-memory capacity looks attractive.
2. With the GPU idle, capture the baseline and loaded state:
   ```bash
   ollama list
   ollama ps
   nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu --format=csv,noheader
   ```
   Run a short prompt against the exact candidate model, then repeat `ollama ps` and `nvidia-smi`. Use a system-memory probe too, such as Python `psutil.virtual_memory()` and `swap_memory()`.
3. `ollama ps` exposes the live processor split and context length. A very large default context can consume most remaining VRAM through the KV cache. Explain that lowering `PARAMETER num_ctx` can reduce KV-cache pressure, but cannot make base weights fit in unavailable VRAM.
4. Stop the temporary model immediately after the measurement with `ollama stop <model>`. Never run the probe while the user has an active research/training job using the GPU.
5. Use conservative CUDA planning tiers: 8 GB is for 4B–8B models; 12 GB can support 14B Q4 models with restricted context; 16 GB is a practical 14B lane after context is verified; 20–24 GB makes 30B/32B Q4-class models realistic. Quantization, context length, and backend determine the actual fit.
6. Be explicit that a cheap 8 GB CUDA mini PC may offer compatibility but not enough model capacity for a meaningful 30B reasoning worker. If the user already owns a stronger CUDA GPU, a cheaper second machine adds concurrency/isolation—not better model quality.

### ⚠️ Pricing Pitfall
**Never guess hardware prices.** Check current market pricing via retailer searches before quoting. DDR5 prices fluctuate significantly — what was $150 six months ago may be $300+ now. If web tools are unavailable, say so rather than estimating.

## 6. Check Community Benchmarks

The repo's issue tracker + README often have a community benchmark table. Use this to calibrate:
- Find closest hardware match
- Note warm-vs-cold speed, expert hit rate, MTP acceptance
- Explain that the "learning cache" improves performance over time

## Pre-Flight: Should You Bother?

Before checking if the user's rig can run a project, assess whether the project is worth installing at all. See `references/oss-adoption-trust-evaluation.md` for the evaluation framework (community health, dependency burden, risk heuristics, and decision criteria).

## Verification Scripts

See `references/colibri-verification.md` for a worked example.

## Pitfalls

- **WSL2 RAM != desktop RAM**: The VM has its own allocation. Desktop may have 32 GB but WSL2 only sees 19 GB. Check `free -h` inside WSL, not just the physical DIMMs.
- **CUDA toolkit version mismatch**: nvidia-smi reports the driver version. nvcc reports the toolkit version. They are independent. The toolkit must support the GPU's compute capability.
- **PyTorch hiding in a venv**: Don't assume system python has torch. Check the active project's venv.
- **Swap saturation**: WSL2's swap file can fill up silently. `free -h` shows used swap. Maxed swap + tight RAM = thrashing.
- **9p/DrvFS mounts**: Repos often warn against running the model on a 9p mount (cross-WSL/Windows filesystem). Ext4 is preferred. Check with `mount`.
