# Model Comparison: 8-Way Stop-Loss Design Benchmark (2026-07-09)

## Context

Blind A/B comparison: same stop-loss design prompt sent to 8 models. Each model independently designed a per-position stop-loss system for Vesper's $113K paper portfolio. No model saw the others' output.

## Models Tested

| Model | Provider | Cost/call | Response time | Output length |
|---|---|---|---|---|
| GLM-5.2 | OpenRouter | ~$0.01 | N/A (inline) | ~2000 chars |
| DeepSeek | Direct API | ~$0.01 | 33s | 7701 chars |
| gpt-5.6-luna | OpenRouter | ~$0.015 | 28s | 9750 chars |
| gpt-5.6-luna-pro | OpenRouter | $0.09 | ~100s | ~12000 chars |
| gpt-5.6-terra | OpenRouter | ~$0.015 | 43s | 3700 chars |
| gpt-5.6-terra-pro | OpenRouter | ~$0.038 | 71s | 6018 chars |
| gpt-5.6-sol | OpenRouter | ~$0.075 | 108s | 5803 chars |
| gpt-5.6-sol-pro | OpenRouter | ~$0.075 | 96s | 7639 chars |

## Feature Matrix

| Feature | GLM-5.2 | DeepSeek | 5.6-luna | 5.6-luna-pro | 5.6-terra | 5.6-terra-pro | 5.6-sol | 5.6-sol-pro |
|---|---|---|---|---|---|---|---|---|
| Time stop | · | ✓ | · | · | · | · | · | · |
| Partial fills | · | ✓ | · | ✓ | · | ✓ | ✓ | · |
| Broker outage | · | · | ✓ | ✓ | · | · | · | · |
| Corp actions | · | ✓ | · | ✓ | · | · | · | · |
| Stale stops | · | · | ✓ | ✓ | · | ✓ | · | ✓ |
| Multi-stop | ✓ | ✓ | ✓ | · | · | · | · | · |
| Cooldown | ✓ | · | · | ✓ | · | · | ✓ | ✓ |
| Override | ✓ | ✓ | ✓ | ✓ | · | · | ✓ | ✓ |
| Gap handling | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Alpaca native | · | · | ✓ | ✓ | ✓ | · | ✓ | ✓ |
| What NOT to do | ✓ | ✓ | ✓ | ✓ | · | ✓ | ✓ | ✓ |
| **Score** | **5/11** | **7/11** | **7/11** | **9/11** | **2/11** | **4/11** | **6/11** | **6/11** |

## Key Differentiators

### gpt-5.6-luna-pro (WINNER — 9/11)
- Only model with partial fill reconciliation (6-step: STOPPING → cancel conflicting → query actual fills → sell remainder → retry → STOPPED)
- Broker-native stop + local watchdog dual layer (if Python dies, Alpaca's server-side stop still fires)
- Stop quantity staleness (adding to a position invalidates old stop coverage)
- Corporate actions handling (splits/reverse splits invalidate stop levels)
- "Disaster stop, not trading signal" framing — explicitly says this stop should NOT exit every losing position
- Portfolio impact math: $3,240-$5,400 per stop, 2.9-4.8% of equity
- Named actual tickers (SMCI, VRT, HOOD, ALB) and reasoned about their specific volatility

### DeepSeek (TIED 2nd — 7/11, best value)
- Only model with time stops (15 flat/negative days → exit at next rebalance)
- 3-tier architecture (hard stop, time stop, gap breaker)
- Corporate actions handling
- Multi-stop awareness
- $0.01/call — best dollar-for-dollar

### gpt-5.6-luna (TIED 2nd — 7/11, best GPT value)
- Broker outage awareness
- Stale stop detection
- Alpaca native stop orders
- Multi-stop awareness
- $0.015/call — 6× cheaper than luna-pro

### GLM-5.2 (5th — 5/11)
- Multi-stop pause (3 of 4 trigger = market event, pause system)
- Day-1 exemption (don't apply stops on entry day)
- Trim 50% (arguable — leaves recovery potential)
- Missed the operational layer entirely

### gpt-5.6-terra (WORST — 2/11)
- Shortest answer (3700 chars)
- Missing most edge cases
- No "what not to do" section
- Avoid for design tasks

## "Pro" Tax Analysis

The "pro" label doesn't guarantee better reasoning:
- luna → luna-pro: +2 features (partial fills, corp actions) for 6× cost
- terra → terra-pro: +2 features (partial fills, stale stops) for 2.5× cost
- sol → sol-pro: +0 features for same cost

## Recommendations

| Use case | Model | Why |
|---|---|---|
| Architecture/design decisions | gpt-5.6-luna-pro | Best reasoning, operational edge cases |
| Daily driver (if budget allows) | gpt-5.6-luna | 7/11 at $0.015, best value |
| Budget daily driver | DeepSeek | 7/11 at $0.01, time stops |
| Fallback | qwen3:14b local | Free, zero dependency |

## How to Run Your Own Comparison

### Via OpenRouter (pay per token)

```python
import requests
# Get OpenRouter key from ~/.hermes/.env (OPENROUTER_API_KEY)
resp = requests.post(
    'https://openrouter.ai/api/v1/chat/completions',
    headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
    json={
        'model': 'openai/gpt-5.6-luna-pro',
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 4000,
    },
    timeout=180,
)
```

### Via ChatGPT Pro OAuth (zero per-token cost)

After `hermes auth add openai-codex` (device code flow):
```bash
hermes config set model.provider openai-codex
hermes config set model.default gpt-5.6-luna-pro
```
Then /reset to activate. All calls go through the Pro subscription — no per-token billing. Watch usage limits though.

### Parallel multi-model testing

Use `execute_code` with `ThreadPoolExecutor` to fire all models simultaneously. Full example in the session transcript — 6 models in ~108s wall time.

### Available GPT-5.6 variants on OpenRouter (as of 2026-07-09)

- `gpt-5.6-luna` / `gpt-5.6-luna-pro`: $1/$6 per M tokens (cheapest)
- `gpt-5.6-terra` / `gpt-5.6-terra-pro`: $2.50/$15 per M tokens
- `gpt-5.6-sol` / `gpt-5.6-sol-pro`: $5/$30 per M tokens

Also available via ChatGPT Pro OAuth at zero per-token cost after `hermes auth add openai-codex`.

## ChatGPT Pro OAuth Setup (2026-07-09)

The user has a ChatGPT Pro subscription (won a year, not paid). Connected to Hermes via:

1. `hermes auth add openai-codex` — starts device code flow
2. Open https://auth.openai.com/codex/device in browser
3. Enter the displayed code (e.g., `XZD6-8DQ69`)
4. Sign in with ChatGPT Pro account
5. `hermes config set model.provider openai-codex`
6. `hermes config set model.default gpt-5.6-luna-pro`
7. `/reset` to activate

Zero per-token cost. Usage tracked by OpenAI's rate limits, not billing. Fallback chain still goes to Gemini Flash → local qwen3:14b if Pro limits are hit.

Full response outputs saved at `D:/vesper/tmp/model_comparison/` for reference.
