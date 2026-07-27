---
name: hermes-profile-configuration
description: "Configure per-profile models, providers, reasoning effort, and fallback chains in Hermes profiles — bypassing dashboard picker limitations."
version: 1.1.0
author: Hermes Agent (learned)
tags: [hermes, configuration, profiles, models, providers]
---

# Hermes Profile Configuration

How to set models, providers, reasoning effort, and fallback chains per Hermes profile when the dashboard model picker is limited or missing models.

## When to use

- The user wants a specific model that doesn't appear in the dashboard `Select Model` picker
- The dashboard shows a curated subset (e.g. 36 OpenRouter models) but the full API has many more
- Configuring per-worker/role model assignments across multiple profiles
- Switching providers (e.g. openai-codex ↔ openrouter) per profile
- Setting `reasoning_effort` differently per role (Thomas=high, Steward=low, etc.)

## The dashboard picker limitation

The Hermes Desktop dashboard fetches models from a **curated manifest** at:
`https://hermes-agent.nousresearch.com/docs/api/model-catalog.json`

This manifest is maintained by Lie Hermes Team and only lists ~36 OpenRouter models. The full OpenRouter catalog has hundreds. Models like `google/gemini-2.5-flash` may be available via the OpenRouter API but absent from the picker.

**The fix: set models via CLI — the model works even if the picker doesn't show it.**

## Commands

### List all profiles with their current models

```bash
hermes profile list
```

### Set model per profile

```bash
hermes --profile <name> config set model.default <model-slug>
```

Example:
```bash
hermes --profile vesper-clarke config set model.default google/gemini-2.5-flash
```

### Switch provider per profile

```bash
hermes --profile <name> config set model.provider <provider-name>
```

Example (switch to OpenAI Codex):
```bash
hermes --profile vesper-engineer config set model.default gpt-5.6-terra
hermes --profile vesper-engineer config set model.provider openai-codex
hermes --profile vesper-engineer config set model.base_url https://chatgpt.com/backend-api/codex
```

### Set reasoning effort

```bash
hermes --profile <name> config set agent.reasoning_effort low|medium|high
```

Current Hermes builds may print an `unrecognized config key` warning for `agent.reasoning_effort` even though runtime model routing still reads it (the source-level `agent.reasoning_overrides` comments explicitly describe it as the fallback). Treat the warning as a CLI-schema mismatch: read the value back with `config get`, then verify the next spawned session's runtime metadata. For per-model control, edit `agent.reasoning_overrides` directly in YAML as a map from model slug to effort; dotted model names make generic `config set` unsafe for that map.

## Common providers

| Provider | model.default prefix | Required auth |
|----------|---------------------|---------------|
| OpenRouter | `google/gemini-2.5-flash` | `OPENROUTER_API_KEY` |
| OpenAI Codex (OAuth) | `gpt-5.6-sol` | `hermes auth` (OAuth) |

### Codex model tiers

| Model | Tier | Use case |
|-------|------|----------|
| `gpt-5.6-sol` | Top | Complex reasoning, strategy (Thomas) |
| `gpt-5.6-sol-pro` | Top+ | Extra reasoning tokens |
| `gpt-5.6-terra` | Mid | Engineering, coding (Engineer) |
| `gpt-5.6-terra-pro` | Mid+ | Extra reasoning tokens |
| `gpt-5.6-luna` | Entry | Specialist work, analysis (Morgan, Riley, Rez, Clarke) |

### Codex provider config

When using openai-codex provider, you MUST set both:

```yaml
model:
  default: gpt-5.6-<tier>
  provider: openai-codex
  base_url: https://chatgpt.com/backend-api/codex
```

## Reasoning effort recommendations by role

| Role | Reasoning | Why |
|------|-----------|-----|
| Strategy/architecture | `high` | Deepest thinking, complex decisions |
| Engineering/coding | `medium` | Well-served at medium; bump per task |
| Specialist analysis | `medium` | Solid default for focused work |
| Orchestrator/routing | `low` | Fast coordination, no deep reasoning |
| Monitoring (24/7, frequent) | `low` | Cheap and fast, just check/report |

## Editing the local model catalog cache

For quick visual fix in the dashboard picker, edit the local cache:

```
~/.hermes/cache/model_catalog.json
```

Add entries to `providers.openrouter.models` array:
```json
{
  "id": "google/gemini-2.5-flash",
  "description": ""
}
```

**Caveat:** Cache auto-refreshes from the remote URL every hour. For permanent changes, either:
1. Host your own catalog and set `hermes config set model_catalog.url <your-url>`
2. Or just use CLI config (models work regardless of what the picker shows)

## Temporary least-privilege profiles for Kanban workers

When a Kanban worker run is evidence—not merely a coding convenience—pin the assigned profile's `platform_toolsets.cli` before the task is claimable. The dispatcher resolves that profile-specific CLI list and appends task-scoped Kanban lifecycle tools separately.

Typical temporary surfaces:

```yaml
platform_toolsets:
  cli:
    - file                 # artifact-only worker
```

```yaml
platform_toolsets:
  cli:
    - file
    - terminal             # reviewer that must run fixed test commands
```

Treat this as a reversible configuration transaction:

1. Copy the complete profile config to an evidence/backup path and hash both copies.
2. Apply a minimal, uniquely preconditioned edit; parse the resulting YAML and assert `platform_toolsets.cli` is a list with the exact expected values.
3. Verify adjacent platform entries such as Telegram, Discord, and WhatsApp were not altered.
4. Precreate the task branch at the exact source SHA before the task can be claimed. A board `blocked` label may be promoted by automation and is not by itself a safe hold.
5. After the worker process is terminal, restore the original config bytes immediately and compare the restored digest with the backup.
6. Audit the entire persisted worker session: a model can invoke Kanban completion and then continue calling tools. Task `done` and changed-file metadata do not prove capability compliance.

For the complete admission, verification, and restoration recipe, see `references/temporary-worker-toolsets.md`.

## Durable role identity across sessions

Profile configuration is not only model routing. When a profile must remain a stable main coordinator or specialist worker across new conversations, bind the role through all three layers:

1. Put the durable organizational identity and responsibilities in that profile's `SOUL.md`.
2. Store a compact canonical identity record in the active memory provider for recall and correction.
3. Explicitly route each CLI, gateway channel/topic, cron job, delegation, and Kanban assignment to the intended profile.

A new conversation title, Telegram group name, or ordinary semantic-memory hit is not an authoritative profile selector. `AGENTS.md` defines project policy, not organizational identity. Verify a fresh session's runtime profile after changing identity or routing.

See `references/profile-identity-routing.md` for the coordinator/worker pattern, verification matrix, and routing pitfalls.

## Fallback chains

Set per-profile fallbacks so if the primary provider fails, OpenRouter models kick in:

```bash
hermes --profile <name> config set model.fallback google/gemini-2.5-flash,model2,model3
```

The fallback is a comma-separated list. Each entry can be a model ID (automatic same provider) or `provider:model`.

## Pitfalls

- **Dashboard picker reads curated catalog, not live API.** A model that works fine via CLI may not appear in the picker. This is by design — do not treat picker absence as "model unavailable."
- **openai-codex requires `base_url`** to `https://chatgpt.com/backend-api/codex`. Missing this causes silent fallback to OpenRouter.
- **Config changes take effect on next session** (profile restart), not mid-conversation.
- **Codex model IDs are bare slugs** (`gpt-5.6-sol`), not `openai/gpt-5.6-sol`. The `openai/` prefix is only used on OpenRouter.
- **Windows Ctrl+D ≠ EOF.** In the operator terminal, press `Q` to quit the dashboard, or type `quit` at the `vesper>` prompt.