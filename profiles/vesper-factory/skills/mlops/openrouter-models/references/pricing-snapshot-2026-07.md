# OpenRouter Pricing Snapshot — July 2026

Captured from the OpenRouter API on 2026-07-04. Pricing changes frequently; re-check before relying on stale data.

## Top Coding Models

| Model | Prompt $/token | Completion $/token | ~$/M tokens | Context |
|-------|----------------|--------------------|-------------|---------|
| `qwen/qwen3-coder` | 0.000000 | 0.000002 | 0.000002 | 1,048,576 |
| `qwen/qwen3-coder-flash` | 0.000000 | 0.000001 | 0.000001 | 1,000,000 |
| `qwen/qwen3-coder-plus` | 0.000001 | 0.000003 | 0.000004 | 1,000,000 |
| `qwen/qwen3-coder-next` | 0.000000 | 0.000001 | 0.000001 | 262,144 |
| `qwen/qwen3-coder-30b-a3b-instruct` | 0.000000 | 0.000000 | 0.000000 | 160,000 |
| `qwen/qwen3-coder:free` | 0.000000 | 0.000000 | 0.000000 | 1,048,576 |
| `deepseek/deepseek-v4-flash` | 0.000000 | 0.000000 | 0.000000 | 1,048,576 |

## Top Reasoning Models

| Model | Prompt $/token | Completion $/token | ~$/M tokens | Context |
|-------|----------------|--------------------|-------------|---------|
| `qwen/qwen3.6-plus` | 0.000000 | 0.000002 | 0.000002 | 1,000,000 |
| `deepseek/deepseek-v4-pro` | 0.000000 | 0.000000 | 0.000000 | 1,048,576 |
| `qwen/qwen3-next-80b-a3b-thinking` | 0.000000 | 0.000000 | 0.000000 | 262,144 |
| `google/gemini-2.5-flash` | 0.000000 | 0.000000 | 0.000000 | 1,048,576 |

## Free Models (good quality)

| Model | Context | Notes |
|-------|---------|-------|
| `deepseek/deepseek-v4-flash` | 1,048,576 | Fast, agentic, excellent value |
| `qwen/qwen3-coder:free` | 1,048,576 | Heavily rate-limited through Venice |
| `qwen/qwen3-next-80b-a3b-instruct:free` | 262,144 | Next-gen Qwen |
| `google/gemma-4-31b-it:free` | 262,144 | Latest Google open model |
| `google/gemma-4-26b-a4b-it:free` | 262,144 | Smaller Gemma variant |
| `nvidia/nemotron-3-super-120b-a12b:free` | 1,000,000 | Large context free model |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | 1,000,000 | Ultra-large, good for long docs |
| `meta-llama/llama-3.3-70b-instruct:free` | 131,072 | Classic Llama |
| `openai/gpt-oss-120b:free` | 131,072 | OpenAI open model |

## Rate Limit Observations

- **`:free` models** (routed through Venice, etc.): first call works, second rapid call (within 1-2s) gets 429. After 3 retries, model is dead for that session.
- **Non-free cheap models** (e.g. `qwen/qwen3-coder` at $0.000002/M): survive first call, second rapid call may timeout. Human-paced usage across a work session is fine.
- **`google/gemini-2.5-flash`** survived rapid-fire testing best among free models.

## Model:free Deprecations

- `qwen/qwen3.6-plus:free` — deprecated (404: "The free model has been deprecated. Transition to qwen/qwen3.6-plus for continued paid access.")
- Model `:free` suffixes are a moving target — re-verify before recommending as a daily driver.