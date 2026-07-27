# Local LLM Hardware Benchmarks

## User's Current Machine (July 2026)

| Component | Spec |
|---|---|
| CPU | AMD Ryzen 7 7700X (8-core, 8-thread) |
| RAM | 32GB DDR5-5600 (2×16GB) |
| GPU | NVIDIA RTX 5070 Ti — 16GB VRAM |
| Driver | 610.52 |
| OS | Windows 11 |

### What fits on 16GB VRAM (Q4_K_M, fully on GPU)

| Model | Size | Est. Speed | Notes |
|---|---|---|---|
| **Qwen3 14B** | ~9 GB | 25-35 tok/s | **Recommended for trading analysis.** Native JSON mode, toggle-able thinking mode, 83% MMLU. Best structured-output model in this size class. Pull: `ollama pull qwen3:14b` |
| Qwen 2.5 14B | ~9 GB | 25-35 tok/s | Solid all-rounder, currently running on Vesper Swing |
| Qwen 2.5 7B | ~5 GB | 50-70 tok/s | Quick, general purpose |
| Phi-4 14B | ~9 GB | 25-35 tok/s | Strong reasoning |
| Gemma 2 9B | ~6 GB | 35-45 tok/s | Solid all-rounder |
| DeepSeek-R1 14B | ~9 GB | 25-35 tok/s | Chain-of-thought reasoning, slower due to thinking tokens |
| Llama 3.1 8B | ~5 GB | 40-60 tok/s | Fast, decent quality |
| Embedding models (nomic-embed, bge-large) | ~0.5-1 GB | Very fast | RAG / vector search |

### Model recommendation for trading context analysis

For the Vesper Swing LLM context layer (structured JSON output: thesis + confidence + risk factors), **qwen3:14b is the best choice on 16GB VRAM**. Native JSON mode eliminates the need for fallback parsing (markdown code block extraction, regex object find). Thinking mode can be enabled for ambiguous setups and disabled for routine scoring. Same 9GB footprint as qwen2.5:14b, no RAM penalty. Pull with `ollama pull qwen3:14b`, then update `config.yaml` → `ollama.model: qwen3:14b`.

### Partial offload (exceeds 16GB VRAM, spills to system RAM)

| Model | Size | Est. Speed | Notes |
|---|---|---|---|
| Qwen 2.5 32B | ~20 GB | 10-15 tok/s | Splits across GPU+CPU |
| Llama 3.3 70B | ~40 GB | 3-5 tok/s | Uses all 32GB RAM + 16GB VRAM, very slow |

## AMD Ryzen AI Halo Developer Platform ($3,999)

| Spec | Value |
|---|---|
| CPU | AMD Ryzen AI Max+ 395 — 16-core Zen 5, 32 threads |
| GPU | AMD Radeon 8060S iGPU (40 RDNA 3.5 CUs) |
| Memory | 128GB LPDDR5x-8000 unified — up to 112GB GPU-accessible |
| Bandwidth | 256 GB/s |
| NPU | AMD XDNA 2 |
| Storage | 2TB NVMe |
| Network | 10GbE, WiFi 7, BT 5.4 |
| OS | Custom Debian 13.4-based AMD Linux |
| Size | 6" × 6" × 2", 1.2 kg, 240W power brick |
| Purchase | In-store only at Micro Center |

### AMD ROCm Benchmarks (from AMD blog, Q4_K_M, Ollama)

| Model | Size | Speed | GPU Offload |
|---|---|---|---|
| Qwen3.5 9B (dense) | 6.2 GB | ~30 tok/s | 100% GPU |
| Qwen3.5 35B-A3B (MoE) | 20.5 GB | ~42 tok/s | 100% GPU |
| Qwen3.5 122B-A10B (MoE) | 76 GB | ~8.6 tok/s | 61% GPU / 39% CPU |

### Halo vs Alternatives

| Spec | Halo | NVIDIA DGX Spark | Mac Studio (M3 Ultra) | Framework Desktop |
|---|---|---|---|---|
| CPU | 16c Zen 5 | 20c ARM GB10 | Up to 32c M3 Ultra | 16c Zen 5 |
| GPU | 40 CU RDNA 3.5 | 6144 CUDA | Up to 80 GPU cores | 40 CU RDNA 3.5 |
| Memory | 128GB unified | 128GB unified | Up to 512GB unified | 128GB unified |
| Bandwidth | 256 GB/s | 273 GB/s | Up to 819 GB/s | 256 GB/s |
| Storage | 2TB | 4TB | Up to 16TB | Up to 16TB |

## Bandwidth Comparison (Why It Matters for Token Speed)

| Platform | Bandwidth | Token speed context |
|---|---|---|
| RTX 5070 Ti (user) | ~448 GB/s | Fast for 14B, limited by 16GB VRAM |
| AMD Halo | 256 GB/s | Large memory pool but lower bandwidth per byte |
| RTX 4090 | 1,008 GB/s | 2-4x faster for same model size |
| H100 | 3,350 GB/s | Datacenter class |
| Mac Studio M3 Ultra | 819 GB/s | Best bandwidth for local inference |

## Key Takeaway

User's current RTX 5070 Ti (16GB) is sufficient for 14B models fully on GPU — enough for financial text classification, sentiment, and embeddings. The Halo's advantage is running 70B-122B models via 128GB unified memory, but at lower bandwidth (slower per-token). For Vesper's needs (classification, summarization, embeddings), 14B is plenty.
