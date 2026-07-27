# Ollama Throughput and Queue-Saturation Debugging

Use this when a real-time signal pipeline journals bars successfully but reports queue overflow, skipped analysis, empty LLM output, or confidence `0` bursts.

## Diagnostic sequence

1. **Quantify by signature**, not by eyeballing logs:
   - queue-full / dropped-analysis lines
   - HTTP failures by status
   - empty or unparsable responses
   - LLM completion latency and throughput
2. **Verify durability separately from analysis coverage.** A journaled raw bar does not mean live signal/LLM processing completed.
3. **Probe Ollama read-only endpoints:** `/api/tags`, `/api/version`, then the exact production `/api/generate` payload.
4. **Inspect the returned shape**, especially `thinking`, `response`, `done_reason`, and `eval_count`. Empty `response` plus populated `thinking` indicates the token budget was consumed by reasoning.
5. **Compare corrected payload timing** before changing queue sizes or adding workers.
6. **Restart only the owning collector process** after a code fix; identify the exact process tree first and leave dashboards/Ollama alone.
7. **Verify against live burst conditions**, not only a unit test: observe several complete universe bursts and then one exact production analyzer call.

## Qwen3 + current Ollama payload

Disable reasoning with top-level `think`, not an option nested under `options`:

```python
payload = {
    "model": model,
    "prompt": prompt,
    "stream": False,
    "think": False,
    "options": {
        "num_predict": max_tokens,
        "temperature": temperature,
    },
}
```

`options.enable_thinking = False` may be ignored. The symptom can be long inference, populated hidden reasoning, empty visible output, parse failure, and queue saturation.

## Architecture warning

Do not immediately add concurrent workers. If bar evaluation and LLM inference share mutable signal-engine state, worker fan-out introduces races; a single GPU may also serialize or degrade under concurrent generations. First correct inference mode and measure sustained throughput. If demand still exceeds capacity, separate fast signal evaluation from bounded LLM work and define explicit prioritization/cooldown semantics with tests rather than silently dropping arbitrary FIFO items.

## Safety and evidence

- Keep execution disabled during diagnosis.
- Do not treat expected fail-closed rejection as a defect.
- Record confirmed operational failures in the project issue registry.
- A code test is not operational closure: rerun the original live failure condition.
