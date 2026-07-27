# colibrì (JustVugg/colibri) — Worked Rig Verification

**Repo:** Pure-C GLM-5.2 (744B MoE) runtime. Streams experts from disk, int4 quant, zero deps at runtime.
**Stars:** ~15.7k | **Language:** C | **License:** Apache 2.0

## User Rig Summary

| Component | Detail |
|---|---|
| CPU | AMD Ryzen 7 7700X (8 cores, 1 thread/core) |
| GPU | RTX 5070 Ti, 16 GB VRAM, sm_120 (Blackwell) |
| RAM | 32 GB DDR5 (desktop) → 19 GB allocated to WSL2 VM |
| Motherboard | ASUS ProArt B650-Creator (AM5, 4× DDR5, PCIe 5.0 M.2) |
| OS | Windows 10 + WSL2 (Ubuntu 24.04, kernel 6.18.33.2) |
| WSL2 Disk | 1007 GB ext4, 885 GB free |
| Windows Disk (D:) | 931 GB, 455 GB free |
| CPU Features | AVX2, **AVX-512F, AVX-512 VNNI** |
| Windows GCC | MinGW-W64 16.1.0 (ucrt-mcf-seh) |
| WSL2 GCC | gcc 13.3.0, OpenMP ✓ |
| WSL2 CUDA | nvcc 12.0 (max arch: compute_90 — **too old for sm_120**) |
| WSL2 PyTorch | Not in system python; `vesper-ranker/.venv` has torch 2.11.0+cu128 (CUDA 12.8) |
| WSL2 RAM | 19 Gi total, 16 Gi avail, swap maxed (5 Gi/5 Gi) |

## PASS / WARN / FAIL

| Requirement | Status | Notes |
|---|---|---|
| AVX2 CPU | ✅ PASS | AVX-512 VNNI exceeds minimum |
| gcc + OpenMP | ✅ PASS | Both WSL2 and MinGW paths |
| make | ✅ PASS | GNU Make 4.3 in WSL2 |
| ≥ 16 GB RAM | ⚠️ WARN | 19 GB total, swap saturated — tight |
| ~370 GB disk | ✅ PASS | 885 GB free on ext4 |
| ext4/NTFS (not 9p) | ✅ PASS | WSL2 root is ext4 |
| GPU detected | ✅ PASS | RTX 5070 Ti visible in WSL2 |

## Key Blockers

1. **CUDA 12.0 can't target sm_120 (Blackwell).** CUDA 12.8+ required for GPU expert tier. CPU-only is unaffected.
2. **19 GB RAM with swap maxed.** At this capacity the expert cache auto-caps to ~2 slots/layer, keeping decode cold. Community benchmarks confirm RAM cap is the binding constraint.
3. **8 threads only.** SMT off in WSL2. Matmul scales with core count.

## Community Benchmark Reference

User's closest analog in the repo's community table:
- **Intel Core Ultra 7 270K (24 threads), 24 GB RAM, WSL2 VHDX**: 0.07 tok/s cold, 0.11 tok/s with `--topp 0.7`
- **i5-12600K (16 threads), 32 GB RAM, native Windows MinGW**: 0.08 tok/s cold, MTP 57% acceptance
- User's rig with 8 threads + 19 GB RAM + AVX-512 VNNI will likely land in the **0.05–0.1 tok/s cold** range, improving to **~0.3–0.5 tok/s warm** with cache + MTP

## Upgrade Effect Tiers

| Tier | Change | Expected Effect |
|---|---|---|
| **Software ($0)** | Configure .wslconfig memory=32GB; install CUDA 12.8+ | Removes swap thrash; enables GPU tier |
| **RAM (~market)** | 2×48 GB or 2×64 GB DDR5 (AM5) | Expert cache expansion — biggest perf lever |
| **CPU (~market)** | Drop-in Ryzen 9 7950X (16 cores) | ~2× matmul throughput |
| **Cloud (per-hr)** | RunPod/Vast.ai multi-GPU box | Instant 4-6+ tok/s |

## Pricing Note (July 2026)

DDR5 prices were significantly higher than historical lows at time of verification. Always check current market pricing before quoting — do not estimate from memory.