---
name: local-llm-operations
description: Operate and capacity-plan local Ollama/llama.cpp coding and reasoning workers on Windows CUDA machines.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [ollama, llama.cpp, local-llm, CUDA, Windows, VRAM, capacity-planning]
---

# Local LLM Operations

Use this skill when a user wants to select, run, benchmark, or operationally integrate a local model for coding/reasoning, especially under constrained RAM/VRAM.

## Core rule

**Disk size is not runtime size.** Measure the loaded model rather than estimating from GGUF/Ollama download size. Resident demand depends on quantization, context/KV cache, GPU offload, and concurrent workloads.

## Windows CUDA capacity workflow

1. Record idle headroom before loading a model:
   ```bash
   ollama ps
   nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu --format=csv,noheader
   python -c "import psutil; m=psutil.virtual_memory(); print(f'RAM available={m.available/2**30:.1f} GiB used={m.used/2**30:.1f} GiB ({m.percent:.0f}%)')"
   ```
2. Inspect model metadata before testing:
   ```bash
   ollama show <model>
   ```
   Check architecture, parameter count, quantization, tool/thinking support, and `num_ctx`.
3. Run a trivial completion, then measure while the model remains resident:
   ```bash
   ollama run <model> "Reply with exactly: OK"
   ollama ps
   nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader
   ```
4. Classify the result:
   - **Always-on worker:** substantial system RAM and VRAM remain free.
   - **On-demand lane:** fits but monopolizes GPU or puts RAM under pressure.
   - **Reject:** meaningful CPU spill or swapping makes it unsuitable for the workload.
5. Unload immediately after testing or a deliberate high-capability session:
   ```bash
   ollama stop <model>
   ```

## Context discipline

- Prefer **8K context** for routine implementation, tests, log triage, and focused code review.
- A large default context can consume enough KV cache to turn a model that should fit into an on-demand-only model.
- Increase context only when the user is explicitly pasting/reviewing a larger code window.

## WSL2 and background workload check

- On Windows, account for `vmmemWSL` separately. It can retain many GiB after research or agent runs.
- Only after all WSL work is safely finished, `wsl --shutdown` releases that memory but terminates every WSL process.
- Never recommend shutting down WSL while the user has an active research, build, or agent process.

## Using a local model without code integration

For a non-programmer or a first test, run:

```bash
ollama run <model>
```

Then paste a **concrete** task plus the relevant code, traceback, log, or configuration. A direct Ollama chat cannot inspect a local repository by itself.

Good prompt shape:

```text
Use only the supplied excerpts; do not invent files, classes, or architecture.
Return: (1) observations, (2) smallest safe change, (3) tests, and
(4) unanswered questions.

[Paste the relevant code or traceback]
```

For governed systems, state explicit boundaries (e.g. no trading, risk, promotion, scheduler, or deployment decision) and keep the local model in an advisory/drafting role.

## Quality policy

- Small local models are valuable for first-pass implementation, tests, code review, log triage, and constrained analysis.
- They can confidently hallucinate repository paths and architecture when no source is provided.
- Treat output as a draft. Verify it against the actual repository and test suite before acting.
- Do not substitute a local model for human approvals or consequential-system authority.

## Reference

- **[capacity-probe-and-review-prompt.md](references/capacity-probe-and-review-prompt.md)** — compact measurement checklist and source-grounded review prompt.
