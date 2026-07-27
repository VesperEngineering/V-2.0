# Hermes + Ollama Local-Agent Profile (Windows)

## When this applies

Use when an existing Windows/CUDA workstation has Ollama and the user wants a local model to run as a **Hermes tool-using agent**, rather than only using `ollama run` as a pasted-text reviewer.

## Critical compatibility gate

Hermes rejects models whose **advertised context window** is below 64K for reliable tool use. A model that loads in Ollama at 8K or 40K is not automatically usable in Hermes.

Verify both the model metadata and runtime context:

```bash
ollama show <model>
ollama ps
```

A `PARAMETER num_ctx 65536` overlay does not increase a model's true advertised maximum. On the tested Windows setup:

- `qwen3:8b` advertised 40,960 tokens and remained clamped to 40,960 at runtime even with a 65,536 Modelfile parameter. Hermes correctly refused it.
- `qwen35-9b-q6-hf` advertised 262,144 tokens. A 65,536-context derivative was accepted by Hermes and successfully completed a real terminal-tool call.

## Safe profile pattern

1. Keep the normal cloud profile untouched.
2. Create a separate local profile; do not silently replace the user's default model.
3. Configure the profile to use the existing Ollama OpenAI-compatible custom provider and local model.
4. Remove cloud fallback from the local profile if the intent is a genuinely local/fail-closed worker.
5. Verify with both a text-only prompt and a harmless read-only tool call (`pwd`).
6. Stop the loaded model after benchmarking or when the user is done.

Example Modelfile:

```text
FROM qwen35-9b-q6-hf:latest
PARAMETER num_ctx 65536
```

## Verified resource envelope (RTX 5070 Ti 16 GB)

`qwen35-9b-hermes-64k` (9B Q6, 65,536 context) was fully GPU-resident at about 9 GB according to `ollama ps`; total GPU use was about 10.1 GB, leaving about 5.9 GB VRAM. This is viable as a local Hermes worker when competing WSL/GPU workloads are stopped, but it is not a substitute for a larger reasoning model.

## User-facing style

For this user, give only the immediate numbered commands and the one decision needed next. Do not lead with integration/API architecture or long hardware matrices when they ask how to use a model.
