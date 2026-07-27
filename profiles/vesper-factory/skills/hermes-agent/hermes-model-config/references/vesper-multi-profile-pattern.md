# Vesper Multi-Profile Model Configuration Pattern

Current Vesper worker-fleet model assignments (July 2026). Treat this reference as the user's configured policy, not a universal cost rule.

## Profile Fleet Overview

| Profile | Role | Model | Provider | Reasoning | Fallback |
|---------|------|-------|----------|-----------|----------|
| `vesper-thomas` | Strategy / architecture | `gpt-5.6-sol` | **OpenAI Codex** | high | Gemini Flash, local Ollama |
| `vesper-engineer` | Engineering / coding | `gpt-5.6-sol` | **OpenAI Codex** | medium | Gemini Flash, local Ollama |
| `vesper-clarke` | Coordination / routing | `gpt-5.6-luna` | **OpenAI Codex** | low | DeepSeek Flash |
| `vesper-steward` | Continuity monitoring | `gpt-5.6-luna` | **OpenAI Codex** | medium | Gemini Flash, local Ollama |
| `vesper-morgan` | Factor research | `gpt-5.6-luna` | **OpenAI Codex** | medium | Gemini Flash, local Ollama |
| `vesper-rez` | Risk / portfolio | `gpt-5.6-luna` | **OpenAI Codex** | medium | DeepSeek Pro |
| `vesper-riley` | Execution / operations | `gpt-5.6-luna` | **OpenAI Codex** | medium | Gemini Flash |
| `vesper-local` | Local advisory worker | `qwen35-9b-hermes-64k` | **Ollama custom endpoint** | high | none |
| `default` | General orchestration | `kimi-k3` | **Kimi for Coding** | high | Gemini Flash, local Ollama |

## Key Patterns

### 1. Codex worker primary

```yaml
model:
  default: gpt-5.6-sol
  provider: openai-codex
  fallback: google/gemini-2.5-flash,custom:ollama-local/qwen3:14b-ctx
```

Codex model names omit the `openai/` prefix.

### 2. Reasoning matched to configured role

- **high**: Thomas; dedicated local advisory profile.
- **medium**: Engineer, Morgan, Rez, Riley, Steward.
- **low**: Clarke.

Do not infer reasoning from model tier. Store and verify `agent.reasoning_effort` independently.

### 3. Frequent workers still follow explicit fleet policy

Do not automatically route monitors to a free model. Steward intentionally uses Luna with medium reasoning. Cost optimization never overrides the user's selected capability policy.

### 4. Fallback chains are profile-specific

Provider and fallback are separate configuration facts. Inspect each profile rather than applying one shared chain. The local advisory profile deliberately has no fallback so it fails closed instead of silently using cloud.

### 5. Per-profile config location

```text
~/.hermes/profiles/vesper-<name>/config.yaml
```

Changes apply to new sessions. Restart the profile or use `/reset` after configuration changes.

## Quick Commands

```powershell
hermes profile list
hermes --profile vesper-thomas config
hermes --profile vesper-engineer config set model.default gpt-5.6-sol
hermes --profile vesper-engineer config set model.provider openai-codex
hermes --profile vesper-engineer config set agent.reasoning_effort medium
```

Verify the actual YAML/model/provider/reasoning values after every change; the display's `Reasoning: off` refers to visible reasoning display, not necessarily `agent.reasoning_effort`.

## Local advisory profile

The local profile is intentionally separate from production authority. It may inspect, explain, draft, test, and report, but does not gain trading, risk, scheduler, broker, promotion, or deployment authority. See `references/local-ollama-hermes-64k.md` for its context and tool-call admission checks.
