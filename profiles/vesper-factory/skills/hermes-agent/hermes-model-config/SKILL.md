---
name: hermes-model-config
description: Configure and manage models in Hermes — dashboard picker, model catalog, per-profile models, and OpenRouter model IDs
version: 1.1.0
author: Hermes Agent
tags: [hermes, models, openrouter, configuration, profiles, dashboard]
---

# Hermes Model Configuration

How to set, browse, and curate models across Hermes profiles — covering the dashboard picker, the curated model catalog, and CLI overrides.

## Key Insight: The Dashboard Picker Is Curated, Not Live

The Hermes Desktop dashboard model picker does NOT query the live OpenRouter API. It reads a **curated JSON manifest** hosted at:

```
https://hermes-agent.nousresearch.com/docs/api/model-catalog.json
```

This file is cached locally at:
```
~/.hermes/cache/model_catalog.json
```

Only models listed in this manifest appear in the picker. A model that exists on OpenRouter (`google/gemini-2.5-flash`, `openai/o4-mini`, etc.) WILL NOT show up in the picker unless it's in the catalog.

**But the model still works.** You can set any model ID via CLI regardless of what the picker shows.

## How the Catalog Works

- Fetched from `model_catalog.url` (default: the Hermes docs site) with 1-hour TTL
- Falls back to a raw GitHub URL if the primary URL is bot-gated
- Cached at `~/.hermes/cache/model_catalog.json`
- Falls back to stale cache or empty dict if fetch fails
- Each provider block contains a `models` array of `{id, description, default?}` entries
- The entry with `"default": true` is the model Hermes silently lands on when no model is chosen

## Setting a Model Per Profile

Each Hermes profile has its own `config.yaml` with an independent `model.default`.

```bash
# Set via CLI (bypasses the picker entirely)
hermes --profile <name> config set model.default <openrouter-model-id>
hermes --profile <name> config set model.provider openrouter

# Examples
hermes --profile vesper-clarke config set model.default google/gemini-2.5-flash
hermes --profile vesper-engineer config set model.default deepseek/deepseek-v4-pro
```

To check current models across all profiles:
```bash
hermes profile list
```

## Adding Models to the Dashboard Picker

Three approaches, in order of durability:

### 1. Edit the local cache (fastest, temporary)
Edit `~/.hermes/cache/model_catalog.json` and add entries to the `openrouter.models` array:
```json
{"id": "google/gemini-2.5-flash", "description": ""}
```
**Caveat:** Overwritten on next catalog refresh (1-hour TTL).

### 2. Host your own catalog (durable)
Serve your own `model-catalog.json` and point Hermes at it:
```bash
hermes config set model_catalog.url https://your-url/model-catalog.json
```
Or disable the catalog entirely:
```bash
hermes config set model_catalog.enabled false
```

### 3. OpenRouter fallback models
Set fallback models in any profile's config under `model.fallback`:
```yaml
model:
  default: deepseek/deepseek-v4-flash
  fallback: google/gemini-2.5-flash,custom:ollama-local/qwen3:14b-ctx
```

## OpenRouter Model ID Format

All OpenRouter models use the slug format:
```
<provider>/<model-name>
```

Examples: `google/gemini-2.5-flash`, `deepseek/deepseek-v4-pro`, `anthropic/claude-sonnet-5`

The `references/openrouter-models.md` reference file contains the full catalog with pricing, organized by provider with ⭐ annotations for value picks.

## Codex Subscription as Primary Provider

When you have a ChatGPT subscription (OpenAI Codex OAuth), you can set any profile to use it as the primary provider with OpenRouter as fallback:

```yaml
model:
  default: gpt-5.6-sol          # Codex model name (no 'openai/' prefix)
  provider: openai-codex        # Uses OAuth subscription
  fallback: google/gemini-2.5-flash,custom:ollama-local/qwen3:14b-ctx
  base_url: https://chatgpt.com/backend-api/codex
```

The `openai-codex` provider uses OAuth (configured via `hermes auth`) — no API key needed. Models are named without the `openai/` prefix (e.g. `gpt-5.6-terra`, not `openai/gpt-5.6-terra`).

### Available Codex Models

Defined in `hermes_cli/codex_models.py`. Default list:

| Model | Tier | Use Case |
|---|---|---|
| `gpt-5.6-sol` | Top | Heavy reasoning, strategy, architecture |
| `gpt-5.6-sol-pro` | Top+ | Sol with extra reasoning tokens |
| `gpt-5.6-terra` | Mid | Engineering, coding, general work |
| `gpt-5.6-terra-pro` | Mid+ | Terra with extra reasoning |
| `gpt-5.6-luna` | Entry | Specialist analysis, light work |
| `gpt-5.6-luna-pro` | Entry+ | Luna with extra reasoning |
| `gpt-5.5` | Legacy | Fallback |
| `gpt-5.4-mini` | Budget | Lightweight |
| `gpt-5.3-codex-spark` | Preview | Research preview (ChatGPT Pro only) |

Live discovery hits `chatgpt.com/backend-api/codex/models`; the hardcoded list above is the fallback when offline.

## Reasoning Effort Per Role

The `reasoning_effort` config setting (`none` | `low` | `medium` | `high`) controls how much the model deliberates. Set it independently per profile — don't waste high-effort tokens on simple routing work.

| Reasoning | When | Example Profiles |
|---|---|---|
| `high` | Strategy, architecture, deep analysis | Thomas |
| `medium` (default) | Coding, specialist analysis, research, continuity review | Engineer, Morgan, Riley, Rez, Steward |
| `low` | Lightweight orchestration and routing | Clarke |

```bash
# Set per profile
hermes --profile vesper-thomas config set agent.reasoning_effort high
hermes --profile vesper-clarke config set agent.reasoning_effort low
```

Thomas (strategy) uses `high`; Clarke's lightweight coordination uses `low`; Engineer, Morgan, Riley, Rez, and Steward use `medium`.

## Per-Profile Model Strategy (Vesper Pattern)

For multi-worker setups, match model capability to role. Use Codex subscription as primary when available, OpenRouter as fallback:

**Reference:** `references/vesper-multi-profile-pattern.md` — documented production fleet configuration with 7 worker profiles + default, cost/performance rationale, and setup commands.

```yaml
# Strategy / architecture lead (Thomas) — top tier + high reasoning
model:
  default: gpt-5.6-sol
  provider: openai-codex
  fallback: google/gemini-2.5-flash
  base_url: https://chatgpt.com/backend-api/codex

# Engineering (Engineer) — top tier, medium reasoning
model:
  default: gpt-5.6-sol
  provider: openai-codex
  fallback: google/gemini-2.5-flash
  base_url: https://chatgpt.com/backend-api/codex

# Specialists (Morgan, Riley, Rez) — entry tier, focused analysis
model:
  default: gpt-5.6-luna
  provider: openai-codex
  fallback: google/gemini-2.5-flash    # or deepseek/deepseek-v4-pro
  base_url: https://chatgpt.com/backend-api/codex

# Coordinator (Clarke) — entry tier + low reasoning
model:
  default: gpt-5.6-luna
  provider: openai-codex
  fallback: deepseek/deepseek-v4-flash
  base_url: https://chatgpt.com/backend-api/codex

# Continuity monitor (Steward) — entry tier + medium reasoning
model:
  default: gpt-5.6-luna
  provider: openai-codex
  fallback: google/gemini-2.5-flash
  base_url: https://chatgpt.com/backend-api/codex
```

### Quick setup commands

```bash
# Set primary model and provider
hermes --profile <name> config set model.default <model-id>
hermes --profile <name> config set model.provider openai-codex  # or openrouter
hermes --profile <name> config set model.base_url https://chatgpt.com/backend-api/codex  # only for codex
hermes --profile <name> config set model.fallback "google/gemini-2.5-flash,deepseek/deepseek-v4-flash"

# Set reasoning effort
hermes --profile <name> config set agent.reasoning_effort high  # or low/medium
```

To check current config across all profiles:
```bash
hermes profile list
```

## Local Ollama Preflight

A working `ollama run` chat model is not automatically ready for a tool-using Hermes session. Before altering a cloud default or fallback, preserve the current profile and run a one-shot custom-provider probe against the local endpoint.

1. Confirm the endpoint and model are visible with Ollama.
2. Invoke Hermes with the custom provider and a minimal `--toolsets safe` prompt.
3. Treat the returned context requirement as a hard admission constraint. A model configured for an 8K interactive context may be rejected for Hermes tool use; increasing `num_ctx` materially raises KV-cache VRAM consumption and must be benchmarked before making it a persistent worker.
4. Verify both metadata and runtime. `PARAMETER num_ctx 65536` does not override a lower architectural context limit; Ollama can accept the Modelfile yet clamp the live model below 64K. Require `ollama show` to report a true context capability of at least 64K and `ollama ps` to show a live `CONTEXT` of at least `65536`.
5. Use a dedicated local profile or explicit fallback only after both a text-only Hermes probe and a real tool-call probe succeed. Never replace a functioning cloud default during this experiment.

See `references/local-ollama-hermes-64k.md` for the complete Modelfile, runtime checks, profile pattern, and cleanup recipe.

### Comparing local candidates

Use one common, repository-grounded prompt across candidates; run candidates sequentially with automatic unload; compare factual adherence rather than fluent prose or raw tokens/sec. Reject responses that invent repository paths, policy values, fallback behavior, or relaxed fail-closed boundaries.

### Interactive guidance

For a user running these tests themselves, give only the next exact command(s), say which shell to use, and state exactly what output to bring back. Avoid front-loading optional architectures or API integration details unless requested.

## Pitfalls

- **The picker is not authoritative.** A model not showing in the dashboard picker does not mean it's unavailable. Set it via CLI and it works.
- **Cache auto-refreshes.** Edits to `model_catalog.json` get overwritten within 1 hour. Host your own catalog for permanent changes.
- **Provider matters per profile.** Some profiles use `openrouter`, others use `openai-codex` — the provider is separate from the model default.
- **Codex model names omit the `openai/` prefix.** `gpt-5.6-sol` not `openai/gpt-5.6-sol`. OpenRouter models use the full `provider/model` format.
- **Frequent workers need an explicit cost choice.** Do not assume every monitor belongs on a free model. Match the configured capability to the user's current fleet policy; for Vesper, Steward currently uses `gpt-5.6-luna` with medium reasoning.
- **`model.default` vs `model.fallback`.** The default is the primary model used. The fallback is a comma-separated list tried when the primary fails. Each is tied to its own provider.
- **`reasoning_effort` is per-profile, per-session.** Changes only take effect on new sessions — `/reset` or restart.