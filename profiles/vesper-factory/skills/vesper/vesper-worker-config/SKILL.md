---
name: vesper-worker-config
description: "Configure Hermes profiles and models for Vesper workers — provider choice, model tiers, reasoning effort, and dashboard picker overrides."
version: 1.0.0
author: Hermes Agent
tags: [vesper, profiles, models, openai-codex, openrouter, configuration]
---

# Vesper Worker Model Configuration

Class-level skill for assigning models to Vesper worker profiles. Each worker runs as a separate Hermes profile with its own `config.yaml` under `~/.hermes/profiles/vesper-<name>/`.

## Provider Hierarchy

Vesper uses a **primary + fallback** model strategy:

1. **Primary**: `openai-codex` (ChatGPT subscription — OAuth, no per-token cost). Model IDs are bare slugs like `gpt-5.6-sol`, NOT `openai/gpt-5.6-sol`.
2. **Fallback**: `openrouter` (API-key-backed). Model IDs are `provider/model-slug` like `google/gemini-2.5-flash`.

## Model Tiers

The GPT-5.6 Codex lineup has three tiers:

| Model | Tier | Best For | Reasoning |
|---|---|---|---|
| `gpt-5.6-sol` | Top | Strategy, architecture, deep reasoning | `high` |
| `gpt-5.6-terra` | Mid | Engineering, coding | `medium` |
| `gpt-5.6-luna` | Entry | Specialist analysis, orchestration, routing | `medium` or `low` |

## Legacy Named Worker Role Mapping

| Worker | Role | Model | Provider | Reasoning |
|---|---|---|---|---|
| Thomas | Strategy/Architecture | `gpt-5.6-sol` | openai-codex | high |
| Engineer | Engineering/Coding | `gpt-5.6-terra` | openai-codex | medium |
| Clarke | Orchestrator/Routing | `gpt-5.6-luna` | openai-codex | low |
| Morgan | Specialist | `gpt-5.6-luna` | openai-codex | medium |
| Riley | Specialist | `gpt-5.6-luna` | openai-codex | medium |
| Rez | Specialist | `gpt-5.6-luna` | openai-codex | medium |
| Steward | 24/7 Monitor | `deepseek/deepseek-v4-flash` | openrouter | low |

Steward stays on OpenRouter (free/cheap) since it runs every 15min — don't burn Codex quota on monitor ticks.

The named Thomas/Engineer/Clarke/Morgan/Riley/Rez/Steward mapping is a separate legacy profile family. Do not copy those generic identities into the V20 role profiles. V20 uses seven project-specific workers: Product, Data Engineering, Quant Research, ML Systems, Portfolio Research, Risk Review, and Development.

For the V20 SOUL contract, role boundaries, controlled project/runtime synchronization, fresh-session authority probes, and independent review gate, read `references/v20-soul-coordination.md`.

## Development Worker Group Prompt

When creating a Vesper group whose role is implementation, give it a coding-only contract rather than a strategy or research charter. Require a brief pre-change statement of outcome, assumptions, expected files, and verification; minimal diffs matching established patterns; focused tests with actual command output; and a concise completion report listing outcome, changed files, verification, risks, and one suggested next task.

Keep explicit stop-and-escalate boundaries for broker/execution/risk changes, credentials, paid compute, schedules, production configuration, and data-integrity decisions. The worker may implement approved tasks but must not invent product direction, broaden scope through refactors, or treat a green test as authorization to deploy or promote a model.

## Setting a Model Per-Profile

```bash
hermes --profile vesper-<name> config set model.default <model-id>
hermes --profile vesper-<name> config set model.provider openai-codex
hermes --profile vesper-<name> config set model.base_url https://chatgpt.com/backend-api/codex
hermes --profile vesper-<name> config set agent.reasoning_effort medium
```

For OpenRouter fallback:
```bash
hermes --profile vesper-<name> config set model.fallback google/gemini-2.5-flash
```

The `model.default` + `model.provider` + `model.base_url` must all be set together to switch providers.

## Dashboard Model Picker

The Hermes Desktop dashboard model picker uses a **curated catalog** at `https://hermes-agent.nousresearch.com/docs/api/model-catalog.json`, NOT the live OpenRouter API. Only models in that JSON appear in the picker.

To add models not in the curated list:

**Option A — Edit local cache (temporary, 1hr TTL):**
```bash
# Edit ~/.hermes/cache/model_catalog.json
# Add entries to providers.openrouter.models array
```

**Option B — CLI bypass (recommended):**
Set models via `hermes --profile <name> config set` directly — they work regardless of what the picker shows.

**Option C — Custom catalog URL (durable):**
```bash
hermes config set model_catalog.url https://your-url/model-catalog.json
```

## Pitfalls

- **Codex model IDs are bare slugs**: `gpt-5.6-terra` not `openai/gpt-5.6-terra`. The `openai/` prefix is only for OpenRouter.
- **Codex base_url is required**: Without `base_url: https://chatgpt.com/backend-api/codex`, Codex OAuth won't route correctly.
- **Fallback chain format**: Comma-separated, no spaces. `google/gemini-2.5-flash,custom:ollama-local/qwen3:14b-ctx`
- **Reasoning effort on Steward/Clarke**: Set to `low` — they route/monitor, not reason. Saves tokens.
- **Profile configs are independent**: Changing the default profile doesn't affect worker profiles. Each `vesper-*` profile has its own `config.yaml`.
- **Dashboard refresh**: After editing model_catalog.json, the dashboard shows changes immediately — no restart needed. But the cache auto-refreshes from the remote URL every hour.