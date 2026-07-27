# Capacity Probe and Source-Grounded Review Prompt

## Capacity probe

Run this sequence for each candidate model, while the actual background workload is representative:

```bash
# Idle baseline
ollama ps
nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu --format=csv,noheader
python -c "import psutil; m=psutil.virtual_memory(); print(f'RAM available={m.available/2**30:.1f} GiB used={m.used/2**30:.1f} GiB ({m.percent:.0f}%)')"

# Inspect model and perform a tiny functional load
ollama show <model>
ollama run <model> "Reply with exactly: OK"

# While resident
ollama ps
nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader

# Cleanup
ollama stop <model>
```

Read `ollama ps` as the primary runtime report: it shows loaded size, GPU/CPU split, and context. Preserve enough host RAM and VRAM for the intended concurrent workload; do not call a nearly-full-GPU result an always-on worker.

## Prompt for reviewing an unfamiliar codebase

A local chat model has no filesystem access unless the caller provides one. Prevent architecture hallucinations by making the supplied excerpts the complete authority:

```text
Use only the supplied source excerpts. Do not invent file paths, functions,
classes, tables, or existing behavior.

Task: [one concrete task]

Return only:
1. What the excerpts prove and do not prove
2. The smallest safe change using exact file paths/names present in the excerpts
3. Tests using exact existing test conventions present in the excerpts
4. Open questions that cannot be answered from the excerpts

Constraints: [state consequential boundaries, if any]

[Paste the relevant implementation and tests]
```

## Interpretation

A response that is structurally sensible but cites generic paths such as `utils/`, `pipelines/`, or invented exception names is an **unverified draft**, not evidence about the codebase. Verify against the live source and run the real tests before acting.
