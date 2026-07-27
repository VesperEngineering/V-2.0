# Provider Comparison Data — July 2026

Concrete pricing and capability data gathered during a session comparing providers for a quant/coding pipeline (Vesper project). Always re-check live pricing before depending on these numbers.

## DeepSeek API (direct — platform.deepseek.com)

**Signup**: platform.deepseek.com/sign_up — email only, no credit card required.
**Base URL**: `https://api.deepseek.com` (OpenAI-compatible) or `https://api.deepseek.com/anthropic` (Anthropic format)
**API key**: Generate at platform.deepseek.com/api_keys

### Pricing (per 1M tokens)

| Model | Cache Hit (input) | Cache Miss (input) | Output | Concurrency |
|-------|:-----------------:|:------------------:|:------:|:-----------:|
| **deepseek-v4-flash** | **$0.0028** | $0.14 | $0.28 | 2,500 |
| **deepseek-v4-pro** | **$0.003625** | $0.435 | $0.87 | 500 |

Context: 1M tokens. Max output: 384K. Thinking mode enabled by default; pass `"thinking": {"type": "enabled"}` for V4 Pro reasoning, or use non-thinking mode for fast code tasks.

### Key Features
- 1M context length, 384K max output tokens
- Thinking mode (chain-of-thought) on by default
- OpenAI-compatible SDK — drop-in with just `base_url` change
- Tool calls, JSON output, FIM completion (non-thinking mode only)
- 2500 concurrent requests for V4 Flash
- **No subscription tier** — pure pay-as-you-go with top-up balance
- Cache hit requires the prefix to be "persisted" (written to disk cache) — not guaranteed 100% on first cold call

### Caching Mechanics
- Cache key is the prompt prefix — the first N tokens that are identical across calls
- Adding or changing even one token in the prefix (e.g. a different date string) invalidates the cache for that prefix
- For quant pipelines: keep the constant prefix (ticker list, schema, instructions) in system prompt and only vary the per-ticker portion in the user message

---

## Blackbox AI (blackbox.ai)

**Signup**: blackbox.ai/signup — email or OAuth.
**API base URL**: `https://api.blackbox.ai` (OpenAI-compatible)
**API key**: Generate at app.blackbox.ai/dashboard

### Pricing Model
Subscription-based with credits:

| Tier | Monthly | Credits Included | Key Features |
|------|---------|-----------------|--------------|
| Pro | $10 | $20 in credits | 48 models, unlimited free agent requests |
| Pro Plus | $20 | $40 in credits | + Multi-agent execution, app builder, Slack integration |
| Pro Max | $40 | $80 in credits | + Team collab, SAML SSO, advanced security |
| Enterprise | Custom | Custom | On-prem, training opt-out, custom SLA |

### Model Pricing (selected, per 1M tokens)

| Model | Input $/M | Output $/M |
|-------|:---------:|:----------:|
| DeepSeek V4 Flash | $0.089 | $0.18 |
| DeepSeek V4 Pro | $0.435 | $0.87 |
| Nemotron 3 Ultra 550B | $0.50 | $2.20 |
| Kimi K2.7 Code | $0.74 | $3.50 |
| GLM 5.2 | $0.93 | $3.00 |
| Gemma 4 31B | $0.12 | $0.35 |
| MiniMax M2.7 | $0.30 | $1.20 |
| Nemotron Nano 30B | $0.05 | $0.20 |
| Codestral | $0.30 | $0.90 |
| Mistral Small | $0.075 | $0.20 |
| Mistral Nemo | $0.02 | $0.03 |
| Llama 3.1 8B | $0.02 | $0.03 |
| Ministral 8B | $0.15 | $0.15 |

### Key Features
- 48 models available through one API key — Claude, GPT, Gemini, Grok, DeepSeek, Qwen, Llama, Mistral, Nemotron
- **E2E encrypted inference** — zero-knowledge proxy, Blackbox cannot read prompts/completions
- **Auto-fallback routing** — if primary provider down, routes to next available
- **Smart load balancing** — routes to lowest-latency endpoint
- **Multi-agent orchestration** — "Chairman LLM" dispatches tasks to parallel agents, evaluates, picks best result
- Integrated IDE, VS Code extension, CLI agent
- **No cache-hit pricing** advertised — you pay full rate on every call
- 99.9% uptime SLA, sub-200ms median latency
- Faster/cheaper than competitors on same open models (Artificial Analysis benchmark: ranked #1 on Nemotron 3 Ultra for speed, TTFT, and blended price)

---

## Together AI (together.ai)

**Focus**: Open-source model experimentation and fine-tuning
**Model count**: 100+ open models
**Pricing example** (DeepSeek V4 Pro): $2.10/$4.40 per 1M tokens
**Key advantage**: Largest open-model catalog, fine-tuning available
**Key disadvantage**: Higher per-token pricing than competitors for the same models

---

## DeepInfra (deepinfra.com)

**Focus**: Cost-efficient open-model inference
**Pricing example** (DeepSeek V4 Pro): $1.30/$2.60 per 1M tokens — cheapest pass-through
**Key advantage**: Lowest rates for open-weight models
**Key disadvantage**: Smaller catalog, fewer extras

---

## Fireworks AI (fireworks.ai)

**Focus**: Fast open-model inference for coding
**Pricing example** (DeepSeek V4 Pro): $1.74/$3.48 per 1M tokens
**Key advantage**: Good coding model coverage, consistent pricing

---

## Groq (groq.com)

**Focus**: Ultra-low-latency inference via LPU hardware
**Key advantage**: 2-3x faster time-to-first-token than GPU-based providers
**Key disadvantage**: Limited model selection; free tier has rate limits (30 rpm)

## Blackbox API Details

### API Format
OpenAI-compatible:
```
POST https://api.blackbox.ai/v1/chat/completions
Authorization: Bearer <api_key>
```

### Model IDs
Use format `blackboxai/<provider>/<model>`:
- `blackboxai/deepseek/deepseek-v4-flash`
- `blackboxai/deepseek/deepseek-v4-pro`
- `blackboxai/openai/gpt-5.5`
- `blackboxai/anthropic/claude-sonnet-4.5`

### Routing Feature
The API accepts a `models` array parameter and `provider` object for routing preferences:
```python
data = {
    "model": "blackboxai/deepseek/deepseek-v4-flash",
    "models": ["blackboxai/deepseek/deepseek-v4-flash", "blackboxai/google/gemini-2.5-flash"],
    "provider": {"require_parameters": True},
    "messages": [...]
}
```

---

## DeepSeek API Quick Start

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-...",
    base_url="https://api.deepseek.com"
)

# V4 Flash (non-thinking, fast)
response = client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=[{"role": "user", "content": "Hello"}],
    stream=False
)

# V4 Pro (thinking mode, deep reasoning)
response = client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=[{"role": "user", "content": "Analyze this factor... "}],
    stream=False,
    reasoning_effort="high",
    extra_body={"thinking": {"type": "enabled"}}
)
```

### Cost Projection for a Quant Pipeline

For a daily pipeline that makes 500 calls on the same ticker universe:

| Scenario | Model | Per-Call Cost | Daily Cost | Monthly |
|----------|-------|:------------:|:----------:|:-------:|
| Full rate (no cache) | V4 Flash | $0.00028/M input | ~$0.56 | ~$17 |
| 85% cache hit | V4 Flash | **$0.000011/M input** | **~$0.15** | **~$4.50** |
| 95% cache hit | V4 Flash | **$0.000003/M input** | **~$0.06** | **~$1.80** |
| Blackbox (same volume) | V4 Flash | $0.089/M input | ~$1.07 | ~$32 |