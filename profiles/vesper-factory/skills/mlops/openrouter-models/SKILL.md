---
name: openrouter-models
description: "Discover, evaluate, and select AI models and providers for coding, reasoning, quant research, and agentic tasks — pricing, caching economics, cross-provider comparison, and testing patterns."
version: 1.2.0
author: Hermes Agent
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [openrouter, models, pricing, model-selection, llm, providers, caching, quant]
---

# AI Model & Provider Selection

How to discover, evaluate, select, and test models **and providers** for any task class (coding, reasoning, quant research, agentic work). Covers OpenRouter plus direct providers (DeepSeek, DeepInfra, Together, Blackbox, Groq, etc.) with a focus on caching economics for repetitive pipelines.

## Strategy Selection: Interactive vs Automated

Model selection strategy depends on *how* you're working. The two patterns are opposite — pick the right one.

### Interactive Sessions (default)

**One cheap model. That's it.**

For conversational, turn-by-turn work (you type → agent responds → you correct → agent fixes), use a single cheap capable model (e.g. `deepseek/deepseek-v4-flash` at $0.27/M). Do not switch models mid-session for different task types.

**Why:** For any single query, all modern models produce roughly equivalent results. The 2–5% benchmark gaps between DeepSeek V4 Flash, Gemini 2.5 Flash, Qwen3 Coder, and Claude Sonnet are *statistical averages over thousands of runs* — they don't predict which model will succeed or fail on one specific question. When a cheap model makes a mistake, the correction turn costs pennies. A premium model would need to save 100+ correction turns to break even on cost.

**When to upgrade:** Only when the agent explicitly says "I'm stuck on this reasoning path, this needs a stronger model." Use the desktop app's composer model picker (left of the microphone) or the TUI's `/model` command for a single-turn upgrade, then switch back.

**Desktop note:** The model picker lives in the composer just left of the microphone. It's sticky UI state — follows across new chats and restarts, never touches the profile default.

### Automated Pipelines (cron jobs, batch processing, unattended runs)

Use the tiered approach below. At scale (1,000+ tasks/day), even a 2% accuracy delta saves real money on re-runs and manual intervention.

### Primary Model (80% of tasks): Google Gemini 2.5 Flash
- Extremely fast (84 tok/s), good for validation tasks, checking receipts, quick analysis
- Best for: Backtest validation checks, JSON receipt validation, quick data verification
- Cost: ~$0.000154 per typical task (220 input + 380 output tokens)

### Code Generation/Refactoring: Qwen3 Coder
- Purpose-built for coding tasks, excellent at repository-level understanding
- Best for: Framework migration work, code generation for new modules, complex refactoring tasks
- Cost: ~$0.000892 per typical task (300 input + 800 output tokens)

### Complex Research/Analysis: DeepSeek V4 Pro
- Strong reasoning capabilities, good for deep quantitative analysis
- Best for: Model skill diagnostic analysis, complex remediation planning, research synthesis
- Cost: ~$0.001384 per typical task (150 input + 650 output tokens)

## Trigger

Use this skill whenever you need to:
- Find a model for a specific task class (coding, reasoning, agentic, cheap, fast)
- Check or compare OpenRouter model pricing
- Troubleshoot rate limits or availability
- Evaluate whether a `:free` or paid-tier model fits the use case
- Save a model as the Hermes default
- Configure a newly chosen provider in Hermes (API key, config values, verification)
- Work around provider-specific payment/regional constraints (e.g. China-based billing)

## Discovering Models

### Via the OpenRouter API (most reliable)

```python
import urllib.request, json
req = urllib.request.Request("https://openrouter.ai/api/v1/models",
    headers={"User-Agent": "Hermes/1.0"})
resp = urllib.request.urlopen(req, timeout=10)
data = json.loads(resp.read())
models = data.get('data', [])
```

Each model entry has:
- `id` — the model slug (e.g. `qwen/qwen3-coder`)
- `name` — human-readable name
- `context_length` — max tokens
- `pricing.prompt` — cost per token for input (NOT per million — multiply by 1,000,000)
- `pricing.completion` — cost per token for output

### Filter by pricing

```python
# Free models (prompt + completion == 0)
free = [m for m in models
        if float(m['pricing']['prompt']) == 0 and float(m['pricing']['completion']) == 0]

# Cheap models (under $X/M tokens)
cheap = [m for m in models
         if m.get('pricing') and
         float(m['pricing']['prompt']) + float(m['pricing']['completion']) < 0.00001]
```

### Filter by capabilities

Check the model ID for keywords: `coder`, `instruct`, `thinking`, `reasoning`, `flash`, `plus`, `pro`, `mini`, `nano`.

| Suffix | Meaning |
|--------|---------|
| `:free` | Free tier, routed through provider (Venice, etc.) — heaviest rate limits |
| (no suffix) | Paid tier, may still be very cheap ($0.00000x/M) |
| `-flash` | Fast, cheap, lower latency |
| `-plus` | Mid-tier, better reasoning |
| `-pro` / `-max` | Top-tier, most capable, most expensive |
| `-thinking` | Extra reasoning tokens before answering (chain-of-thought) |

## Model Selection Guide

### Coding & Agentic Work

| Model | Context | Cost/M tokens | Notes |
|-------|---------|---------------|-------|
| `qwen/qwen3-coder` | 1,048,576 | ~$0.000002 | **Best value coder** — 480B MoE, purpose-built for code |
| `qwen/qwen3-coder-flash` | 1,000,000 | ~$0.000001 | Faster, slightly cheaper variant |
| `qwen/qwen3-coder-plus` | 1,000,000 | ~$0.000004 | Better throughput, less rate-limited |
| `qwen/qwen3-coder:free` | 1,048,576 | Free | Heavily rate-limited (Venice) |
| `deepseek/deepseek-v4-flash` | 1,048,576 | Free/cheap | Fast, strong agentic behavior |

### Reasoning & Multi-variant Tasks

| Model | Context | Cost/M tokens | Notes |
|-------|---------|---------------|-------|
| `qwen/qwen3.6-plus` | 1,000,000 | ~$0.000002 | Strong instruction following, chain-of-thought |
| `qwen/qwen3-next-80b-a3b-thinking` | 262,144 | Free | Reasoning-tuned variant |
| `google/gemini-2.5-flash` | 1,048,576 | Free | Fast, solid reasoning |

### General Purpose

| Model | Context | Cost/M tokens | Notes |
|-------|---------|---------------|-------|
| `google/gemini-2.5-flash` | 1,048,576 | Free | Good all-rounder, survives rate limit tests |
| `google/gemma-4-31b-it:free` | 262,144 | Free | Latest Google open model |
| `nvidia/nemotron-3-super-120b-a12b:free` | 1,000,000 | Free | Large context, good for long docs |

## Provider Comparison Beyond OpenRouter

OpenRouter is one option. For coding-focused or quant research pipelines, evaluate these other providers using the framework below. The right provider depends on your **workload pattern** — repetitive pipelines benefit enormously from provider-specific caching; broad experimentation benefits from broad model catalogs.

### Provider Evaluation Framework

| Criterion | What to Check | Why It Matters |
|-----------|---------------|----------------|
| **Per-token pricing** | Input + output $/M tokens | Direct cost for single-use queries |
| **Cache hit pricing** | Discounted rate for repeated prefix/context | **Dominant factor for repetitive quant pipelines** — can be 50x cheaper than cache-miss rate |
| **Model selection** | Which models available through one API | More models = less provider lock-in |
| **Subscription vs pay-as-you-go** | Monthly credits vs per-token billing | Predictable daily usage benefits from subscriptions |
| **Encryption** | E2E / zero-knowledge / data retention | Critical for proprietary quant strategies |
| **Concurrency** | Requests per second limits | High-throughput pipelines (batch scoring) need headroom |
| **Auto-failover** | Fallback routing on provider outage | Production reliability without manual intervention |

### Provider Landscape (July 2026)

| Provider | Best For | Key Strength | Weakness |
|----------|----------|--------------|----------|
| **DeepSeek API (direct)** | Repetitive quant pipelines | **$0.0028/M cache-hit** on V4 Flash — transformative for repeated-context workloads | Only DeepSeek models |
| **Blackbox AI** | Unified multi-model coding | 48 models, E2E encryption, auto-failover, multi-agent orchestration | No cache-hit pricing; credits-based subscription |
| **Together AI** | Open-model experimentation | 100+ open models, fine-tuning available | Higher per-token pricing than DeepInfra |
| **DeepInfra** | Cost-efficient open-model pass-through | Lowest pass-through rates (e.g. V4 Pro $1.30/$2.60) | Smaller model catalog |
| **Fireworks AI** | Coding model inference | Good Qwen/DeepSeek/Llama coverage, consistent pricing | Less differentiation |
| **Groq** | Ultra-low-latency inference | LPU hardware: 2-3x faster TTFT than competitors | Limited model selection |
| **AI/ML API** | Multimodal + LLM in one API | 400+ models, image/video/audio support, crypto payments | Curated catalog misses niche models |

### Caching Economics — The Biggest Cost Lever for Quant Work

For repetitive workloads (daily factor scoring on the same ticker universe, same OHLCV context windows, same scoring templates), **provider caching is the single dominant cost factor**:

- **DeepSeek V4 Flash**: $0.14/M (miss) → **$0.0028/M (hit)** = 50x discount
- **DeepSeek V4 Pro**: $0.435/M (miss) → **$0.003625/M (hit)** = 120x discount
- Most other providers (Blackbox, Together, DeepInfra) do not advertise cache-hit pricing — you pay full rate every time

**Rule of thumb**: If your pipeline sends 80%+ identical prefix context (ticker list, date range, OHLCV schema) across calls, DeepSeek direct is dramatically cheaper. If your work is diverse/exploratory (each call has different context), a multi-model aggregator like Blackbox or Together gives you better flexibility for similar cost.

### When Each Provider Wins for Quant/Code Workloads

| Workload Type | Best Provider | Why |
|---------------|---------------|-----|
| **Daily factor scoring** (repetitive) | **DeepSeek API direct** | 85-98% cache hit on repeated ticker + OHLCV context → pennies per run |
| **Strategy research / architecture planning** (one-off) | **DeepSeek API direct** (V4 Pro) or **Blackbox** | V4 Pro cache-hit for revisits; Blackbox for multi-model comparison |
| **Multi-step agentic coding** | **Blackbox** or **OpenRouter** | Auto-failover, broad model selection, agent orchestration |
| **Data-sensitive pipeline** | **Blackbox** (E2E encrypted) or DeepSeek direct | Blackbox's zero-knowledge proxy beats alternatives for confidentiality |
| **Low-latency interactive coding** | **Groq** | Fastest TTFT for quick iteration on individual prompts |
| **Experimenting across many open models** | **Together AI** or **DeepInfra** | Largest open-model catalogs |

### Common Pitfalls in Provider Selection

- **Ignoring cache-hit pricing** — a $0.14/M model with 90% cache hit ($0.0028/M effective) beats a $0.089/M model with no cache pricing by 30x for repetitive work
- **Assuming all providers charge the same for the same model** — DeepSeek V4 Pro ranges from $1.30/$2.60 (DeepInfra) to $2.10/$4.40 (Together). Always compare the specific model+provider pair.
- **Paying retail for predictable volume** — if you run the same pipeline daily, a subscription (Blackbox $10-40/mo) or direct-provider pay-as-you-go (DeepSeek) beats per-call markup aggregators.
- **Overlooking provider lock-in** — DeepSeek direct only gives you DeepSeek models. If you need Claude, Gemini, or Grok for a specific task, you need a second API key (Blackbox, OpenRouter, or direct).

## Rate Limits & Availability

### `:free` models
- Routed through **upstream free-tier providers** (Venice, etc.)
- **Heavy rate limits** — expect 429s on rapid-fire requests
- Single query at human pace usually works
- After 3 consecutive rate-limit retries, the model is effectively unavailable for that session

### Non-free but very cheap models ($0.00000x/M)
- Better throughput but still soft rate-limited
- Survive moderate-paced usage throughout a work session
- The second rapid call in a loop will likely time out

### Paid tier models (non-zero pricing)
- No free-tier rate limits
- Use when sustained heavy throughput is needed
- `deepseek/deepseek-v4-pro`, `qwen/qwen3.6-plus`, `google/gemini-2.5-flash`

### Testing availability

A public provider catalog proves that a model exists; it does **not** prove that the user's account, route, or named Hermes profile can invoke it. Before recommending a model change, run one minimal profile-scoped probe through the exact route that the worker will use:

```bash
hermes -p <profile> chat -Q -q "Reply exactly: READY" \
  --provider openrouter -m "model-name"
```

Treat a concise expected reply as the availability receipt. Do not expose credentials. A provider policy refusal or streamed-response error may be a successful API response rather than a transport outage, so it may **not** activate Hermes fallbacks; validate the alternate route directly instead of assuming the fallback chain will rescue the task.

After a successful probe, make any model change only in the specific worker profile that needs it. Re-run the real bounded task in a fresh worker process, not in an already-blocked worker session.

For rapid testing across models, use `execute_code` with the `terminal` tool in a loop with `sleep 2` between calls.

## Setting as Hermes Default

### Via CLI (always works, no model is hidden)

```bash
# Set model
hermes config set model.default "model-name"
hermes config set model.provider openrouter

# Verify
hermes config
hermes chat -Q -q "test" -m "model-name" --provider openrouter

# Restart desktop app or use /reset to pick up new default in a fresh session
```

### Dashboard Model Picker Limitations

The Hermes Desktop Dashboard's **Select Model** dialog (under Models → model settings) only shows a **limited subset** of OpenRouter models — approximately 36 models from a catalog of 200+. Models like `google/gemini-2.5-flash`, `google/gemini-2.5-pro`, and many others are **not in the picker's list** even though they're fully available on OpenRouter and work fine when set via CLI.

**The picker is a curated view, not an exhaustive catalog.** If a model doesn't appear in the picker, set it directly via CLI — it will work.

**To get the full model list:**

```bash
curl -s -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  "https://openrouter.ai/api/v1/models" | python -c "
import json, sys
d = json.load(sys.stdin)
for m in sorted(d.get('data', []), key=lambda x: x['id'].lower()):
    print(m['id'])
" | less
```

## Per-Profile (Worker) Model Configuration

When you have multiple Hermes profiles (e.g. Vesper workers: `vesper-thomas`, `vesper-clarke`, `vesper-riley`, etc.), each profile has its own `model.default` setting. Set models per-profile independently of the default profile:

```bash
# Set a worker profile's model
hermes --profile <profile-name> config set model.default <model-id>

# Verify
hermes --profile vesper-riley config set model.default google/gemini-2.5-flash
hermes -p vesper-riley chat -Q -q "Reply: READY" --provider openrouter -m google/gemini-2.5-flash
```

**List all profiles and their current models:**

```bash
hermes profile list
```

Example output:
```
Profile          Model
───────────────  ───────────────────────────
◆default         deepseek/deepseek-v4-flash
 vesper-clarke   deepseek/deepseek-v4-flash
 vesper-riley    google/gemini-2.5-flash
 vesper-thomas   gpt-5.6-sol
```

**How it works:** Each profile has its own `config.yaml` under `~/.hermes/profiles/<name>/`. Setting the model via `hermes --profile <name> config set` writes to that profile's config, not the default. The dashboard's model picker only edits the **active profile** — and only shows its limited subset of models. Use the CLI to set any model on any profile.

**When to use per-profile models:**
- Different workers need different capability tiers (cheap flash for routine, pro for reasoning)
- A worker needs a specific model for tool compatibility
- Isolating model changes to one worker without affecting others

## Config Diagnosis & Fallback Chains

### Provider/Base URL Contradictions

A common config trap: the `provider` field says one thing but `base_url` points elsewhere. For example, `provider: custom:ollama-local` with `base_url: https://api.deepseek.com/v1` — the provider tells Hermes to use Ollama's custom provider handler, but the URL directs it to DeepSeek's API. This causes silent failures or wrong-model behavior.

**Symptoms:**
- The session header shows a different model than expected
- `hermes config list` shows a base_url that doesn't match the provider
- Requests hang or return auth errors despite valid API keys

**Fix procedure:**

```bash
# 1. Identify the contradiction
grep -A5 '^model:' ~/AppData/Local/hermes/config.yaml

# 2. Set the correct native provider (removes the need for base_url)
hermes config set model.provider deepseek
hermes config set model.default deepseek/deepseek-chat

# 3. Remove stale base_url (hermes config has no 'unset' — use sed)
sed -i '/^  base_url: https:\/\/api.deepseek.com\/v1$/d' ~/AppData/Local/hermes/config.yaml

# 4. Set fallback for resilience
hermes config set model.fallback "google/gemini-2.5-flash,custom:ollama-local/qwen3:14b-ctx"
```

**Native providers** (deepseek, openrouter, anthropic, google, xai) handle their own base URLs internally — setting `model.base_url` is only needed for `custom:...` providers.

### Fallback Chain Configuration

Fallbacks let Hermes automatically try alternative models when the primary provider is down, rate-limited, or returns errors. Configured via a single config key:

```bash
hermes config set model.fallback "provider1/model1,provider2/model2"
```

**Syntax:** comma-separated list of `provider/model` pairs. The provider can be a native name (`deepseek`, `openrouter`, `google`) or a custom provider (`custom:ollama-local`).

**Fallback order:** each entry is tried in sequence. If all fail, the agent reports the error.

**Real example for DeepSeek primary + Gemini + local:**

```yaml
model:
  default: deepseek/deepseek-chat
  provider: deepseek
  fallback: google/gemini-2.5-flash,custom:ollama-local/qwen3:14b-ctx
```

**When each fallback fires:**
- Primary → DeepSeek API (cheap, fast)
- Fallback 1 → Gemini Flash via OpenRouter (free tier, good backup)
- Fallback 2 → Local qwen3:14b via Ollama (free, always available)

**Verification:**

```bash
# Test primary
hermes chat -Q -q "ping" -m "deepseek/deepseek-chat" --provider deepseek

# Simulate fallback by temporarily setting an invalid primary model
# then confirming the agent falls through to secondary
```

### Checking What's Actually Running

```bash
# What Hermes thinks it's using
hermes config list | head -10

# What's actually running locally
curl -s http://localhost:11434/api/tags | python -c "import sys,json; d=json.load(sys.stdin); [print(m['name']) for m in d.get('models',[])]"

# What API keys are configured (shows partial keys for safety)
grep -o 'sk-[a-zA-Z0-9]\{4\}' ~/AppData/Local/hermes/.env | head -5
```

## Configuring a Direct Provider in Hermes

When you've chosen a direct provider (DeepSeek, Together, DeepInfra, etc.) instead of an aggregator, Hermes needs three things: the **API key** in `.env`, the **provider name** and **model** in `config.yaml`, and optionally the **base URL**.

### Universal Template

```bash
# 1. Set API key in .env
echo "PROVIDER_API_KEY=sk-..." >> ~/AppData/Local/hermes/.env

# 2. Set provider, model, and base URL
hermes config set model.provider <provider-name>
hermes config set model.default <model-id>
hermes config set model.base_url <api-endpoint>

# 3. Verify the connection
curl -s <api-endpoint>/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $PROVIDER_API_KEY" \
  -d '{"model":"<model-id>","messages":[{"role":"user","content":"ping"}]}'

# 4. Apply to your Hermes session with /reset
```

### Canonical Example: DeepSeek Direct

DeepSeek uses the OpenAI-compatible format and is natively supported by Hermes (env var `DEEPSEEK_API_KEY`):

```bash
# 1. Add the API key
echo "DEEPSEEK_API_KEY=sk-..." >> /c/Users/bgonn/AppData/Local/hermes/.env

# 2. Configure Hermes
hermes config set model.provider deepseek
hermes config set model.default deepseek-v4-flash
hermes config set model.base_url https://api.deepseek.com

# 3. Test the connection
curl -s https://api.deepseek.com/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $DEEPSEEK_API_KEY" \
  -d '{"model":"deepseek-v4-flash","messages":[{"role":"user","content":"ping"}]}'

# 4. /reset in the session to pick up the new provider
```

**Switching models at runtime**: Once DeepSeek is configured as default, use `/model deepseek-v4-pro` (or `/model deepseek-v4-flash`) to toggle between the cheap workhorse and the reasoning model without changing config.

**Checking your balance**: Visit [platform.deepseek.com](https://platform.deepseek.com) — new accounts get 5M free tokens (~$8-10) with no credit card required.

### China-Based Provider Concerns

DeepSeek is operated by a Chinese AI lab. Key considerations:

- **API usage**: Prompts and completions pass through DeepSeek's servers — don't send proprietary quant strategies or sensitive data as raw prompt text. The API key itself is used for authorization, not data collection.
- **Payment**: Topping up after the initial free credits requires entering a card on a Chinese site. Two alternatives:
  - **DeepInfra** (Palo Alto, US-based) — runs DeepSeek V4 Flash at $0.09/$0.18/M with caching at $0.018/M. Standard US payments. Same model, same quality.
  - **Blackbox AI** — subscription-based ($10-40/mo), US payments, includes DeepSeek models plus 47 others, E2E encrypted.
- **Pragmatic approach**: Use the free 5M token grant first (covers ~1-2 months of light quant dev). If additional balance is needed, DeepSeek direct's cache-hit pricing ($0.0028/M) is unmatched — evaluate the risk tolerance vs cost savings.

### Supported Providers Quick Reference

| Provider | Env Var | Config provider name | Base URL |
|----------|---------|---------------------|----------|
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek` | `https://api.deepseek.com` |
| DeepInfra | `DEEPINFRA_API_KEY` | `deepinfra` | `https://api.deepinfra.com/v1` |
| Together AI | `TOGETHER_API_KEY` | `together` | `https://api.together.xyz/v1` |
| Fireworks AI | `FIREWORKS_API_KEY` | `fireworks` | `https://api.fireworks.ai/inference/v1` |
| Groq | `GROQ_API_KEY` | `groq` | `https://api.groq.com/openai/v1` |
| xAI/Grok | `XAI_API_KEY` | `xai` | `https://api.x.ai` |
| Google Gemini | `GOOGLE_API_KEY` | `google` | `https://generativelanguage.googleapis.com/v1beta` |

## Local / Ollama Models

When running models locally via Ollama, the selection calculus is different — no token pricing, no rate limits, but constrained by hardware (VRAM, RAM, inference speed). These models are relevant for quant work (Vesper Swing real-time signal analysis, Vesper factor research) where data sensitivity or latency needs favor local inference.

### Ollama Setup in Hermes

Configure local models via `custom_providers.yaml` at `~/.hermes/custom_providers.yaml`:

```yaml
ollama-local:
  base_url: http://localhost:11434/v1
  api_key: ollama
  models:
    qwen3:14b:
      model: qwen3:14b
      context_length: 131072
    qwen2.5:14b:
      model: qwen2.5:14b
      context_length: 32768
```

Then switch Hermes to use it:

```bash
hermes config set model.provider custom:ollama-local
hermes config set model.default qwen3:14b
```

Or use per-invocation without changing the default:

```bash
hermes chat -q "analyze this signal" --provider custom:ollama-local
```

### Systematic Local Model Comparison

When evaluating two local models for coding vs reasoning, run the **same** prompts at the **same** temperature (0.1 for coding, ~0.3 for reasoning) and evaluate on these axes:

| Axis | How to Test | Signal |
|------|-------------|--------|
| **Code correctness** | Same coding task, check for side-effects (mutating input, unwanted `.dropna()`), edge-case handling | qwen3:14b respects immutability; qwen2.5:14b tends to mutate input and drop data |
| **Reasoning depth** | Quant-specific question (Sharpe assumptions, market regimes, signal improvements) — check for depth and accuracy, not just token count | qwen3:14b engages deeper reasoning; qwen2.5:14b is more terse and sometimes misses nuance |
| **JSON output** | Prompt for structured output without specifying JSON mode | Both produce valid JSON naturally at low temperature |
| **Speed** | Time identical prompts with `time curl ...` | qwen2.5:14b ~20% faster (~5.3s vs ~6.6s for simple) but generates less content — gap narrows for equivalent output depth |
| **Reasoning token overhead** | Check if `choices[0].message.reasoning` is populated | qwen3:14b emits explicit reasoning tokens that can eat the token budget if max_tokens is tight — raise max_tokens to 1500+ and use system prompt "Output ONLY the code, no reasoning" when you want terse output |

### Local Model Recommendations (RTX 5070 Ti 16GB)

| Model | VRAM | Coding | Reasoning | Speed | Verdict |
|-------|------|--------|-----------|-------|---------|
| **qwen3:14b** | ~10GB | Excellent — production-quality code, respects immutability | Deep — works through quant/statistical assumptions correctly | ~6.6s simple, ~12s reasoning | **Best for both Swing and quant Vesper** |
| **qwen2.5:14b** | ~9GB | Good but mutates input, drops first window rows | Adequate but shallow — misses nuance on statistical questions | ~5.3s simple | Acceptable fallback, not recommended primary |

**Key insight**: The 1.3s speed penalty on qwen3:14b is negligible for quant work. The extra reasoning tokens (which generate the overhead) are actually *useful* for signal analysis and factor research — you want the model to reason through statistical assumptions. The deep reasoning can be controlled with prompt engineering when you need terse output.

### Qwen3 Specific Quirks

- **Reasoning tokens consume the `max_tokens` budget** — qwen3 emits a `reasoning` field inside `choices[0].message` that counts toward `max_tokens`. A prompt asking for code with `max_tokens: 1000` may produce 800 tokens of reasoning + 200 tokens of code (truncated). Bump `max_tokens` to 1500-2000 when you want full code output, or use a system prompt suppressing reasoning.
- **Reasoning is still visible even with `"output ONLY code"`** — qwen3 includes reasoning inside the message object (returned as `reasoning` by the Ollama API). The final `content` field is just the code, but the `reasoning` field consumes generation time and token allocation. Set a high `max_tokens` and let it run — the extra reasoning doesn't degrade the final output quality.
- **JSON mode works naturally** — at temperatures ≤0.3, qwen3 reliably emits valid JSON without needing a format constraint. Just describe the schema in the prompt.

### Testing Script Pattern

For quick head-to-head comparisons:

```bash
#!/bin/bash
MODELS=("qwen3:14b" "qwen2.5:14b")
PROMPT='Write a Python function that...'

for model in "${MODELS[@]}"; do
  echo "=== $model ==="
  time curl -s http://localhost:11434/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$model\",\"messages\":[{\"role\":\"user\",\"content\":\"$PROMPT\"}],\"temperature\":0.1,\"max_tokens\":1500}"
  echo ""
done
```

## Reference Files

- `references/pricing-snapshot-2026-07.md` — concrete pricing data from July 2026. Useful as a baseline comparison but always re-check the live API before depending on stale numbers.
- `references/cost-optimized-strategy.md` — tiered approach for quant research workflows with cost projections and implementation recommendations.
- `references/provider-comparison-2026-07.md` — cross-provider comparison (DeepSeek direct, Blackbox AI, Together AI, DeepInfra, Fireworks, Groq) with concrete pricing, caching economics, and quant pipeline cost projections.
- `references/local-models-quant.md` — local model comparison for quant work (qwen3:14b vs qwen2.5:14b on an RTX 5070 Ti), with session-derived recommendations, testing methodology, and Ollama integration notes.
- `references/config-troubleshooting.md` — diagnosing and fixing provider/base_url contradictions, fallback chain syntax, and the sed fix for stale config keys when `hermes config unset` is unavailable.

## Free and preview reasoning-model benchmark guardrails

When evaluating a free or preview model for automated routing, test the exact production task class with identical prompts and a sufficient generation budget. A successful HTTP 200 is not enough: inspect final `message.content`, `finish_reason`, latency, completion tokens, and reasoning-token usage. Reasoning-heavy models can consume a small `max_tokens` budget without producing final content.

Use at least three task types (for example: domain reasoning, code transformation, and strict JSON classification), add 1–2 seconds between calls to avoid free-tier throttling, and compare against the incumbent model at the same token budget. Treat `:free` availability and rate limits as operational constraints, not pricing facts. Keep a free reasoning model for low-risk coordination only until it has demonstrated reliable final output and acceptable latency.

## Pitfalls

- **Don't over-engineer model selection for interactive work** — benchmark differences are statistical averages, not predictions for a single query. One cheap model + iteration beats multi-model orchestration for turn-by-turn work.
- **Don't overwhelm users with options** — when someone asks "should I use X or stick with what I have?" they often don't know the basic categories (agent vs model vs provider vs API middleman). First inventory what they have, explain in plain terms what each piece does, then give one clear recommendation. Multi-column comparison tables with pricing and scenarios before the basics are established cause confusion, not clarity.
- **`:free` models are deprecated without notice** — always test before committing to one as default. If you get a 404 with "The free model has been deprecated", switch to the non-free variant.
- **Pricing from the API is per-token, not per-million** — multiply by 1,000,000 for the per-M cost that providers advertise.
- **Context lengths in API responses are the model's architectural limit**, not what OpenRouter guarantees — actual usable context may be lower depending on the provider backend.
- **Rapid-fire testing in a for-loop will trigger 429s** — always add `sleep 1-2` between sequential test calls.
- **Model availability changes frequently** — what's free today may be deprecated tomorrow. Re-check before relying on a specific model for critical workflows.