# Local Ollama Model Admission for Hermes

Use this recipe when a local Ollama model works in direct chat but Hermes rejects it or the model is absent from `/model`.

## Hard context admission rule

Hermes tool sessions require at least 64K context. Validate the model's **architectural context metadata**, not only a Modelfile parameter.

```powershell
ollama show <model>
```

A Modelfile containing `PARAMETER num_ctx 65536` does not enlarge a model whose metadata reports a smaller maximum. Ollama may clamp the runtime silently. Verify the real allocation:

```powershell
ollama run <variant> "Reply with exactly: OK" --think=false --keepalive 5m
ollama ps
```

The `CONTEXT` column must show at least `65536`. If it still shows `40960`, Hermes will correctly reject it even when the Modelfile says `num_ctx 65536`.

## Known pattern

A Qwen3 8B build reported a 40,960-token architectural context. A 65,536 Modelfile parameter was accepted at creation time but the runtime remained clamped to 40,960, so it was not a valid Hermes model.

A Qwen3.5 9B base reported 262,144 architectural context. This variant worked:

```text
FROM qwen35-9b-q6-hf:latest
PARAMETER num_ctx 65536
```

Create and verify:

```powershell
ollama create qwen35-9b-hermes-64k -f .\qwen35_9b_hermes_64k.Modelfile
ollama show qwen35-9b-hermes-64k
ollama run qwen35-9b-hermes-64k "Reply with exactly: OK" --think=false --keepalive 5m
ollama ps
```

On a 16 GB RTX 5070 Ti, the verified 64K runtime used roughly 10.1 GB VRAM and remained 100% GPU-offloaded. Treat that number as a measured example, not a guarantee on another machine.

## Hermes smoke tests

Do not trust a direct Ollama response alone. Test Hermes first without changing the default profile:

```powershell
hermes chat -q "Reply with exactly: HERMES_LOCAL_OK" --provider custom:ollama-local -m qwen35-9b-hermes-64k --toolsets safe --quiet
```

Then prove tool calling:

```powershell
hermes --profile <local-profile> chat -q "Use the terminal tool to run pwd. Then reply with only the directory path returned." --toolsets terminal --quiet
```

A text-only pass does not prove agent/tool readiness; require both.

## Dedicated profile

Create a separate profile rather than replacing the working cloud profile. Set:

```yaml
model:
  default: qwen35-9b-hermes-64k
  provider: custom:ollama-local
  context_length: 65536
custom_providers:
  - name: ollama-local
    base_url: http://localhost:11434/v1
    api_key: no-key
```

Remove `model.fallback` when the local profile must fail closed instead of silently routing to cloud.

A custom local model may not appear in the default profile's `/model` picker. Launch the dedicated profile directly:

```powershell
hermes --profile <local-profile>
```

or use its generated profile wrapper. Confirm with `/config`.

## Cleanup

After benchmarking or finishing a session:

```powershell
ollama stop qwen35-9b-hermes-64k
ollama ps
```

An empty `ollama ps` confirms the model is no longer reserving VRAM.
