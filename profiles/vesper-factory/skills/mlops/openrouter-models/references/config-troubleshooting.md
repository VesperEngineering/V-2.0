# Hermes Config Troubleshooting

## Provider/Base URL Mismatch

**Problem:** `provider: custom:ollama-local` with `base_url: https://api.deepseek.com/v1`

The provider tells Hermes which handler to use; the base_url tells it where to send requests. When they point to different services, requests either go to the wrong API or fail with auth errors.

### Fix (no `hermes config unset`)

Hermes CLI has no `unset` subcommand. To remove a stale key:

```bash
# 1. Switch to a native provider that handles its own URL
hermes config set model.provider deepseek
hermes config set model.default deepseek/deepseek-chat

# 2. Remove the stale base_url from config.yaml with sed
sed -i '/^  base_url: https:\/\/api.deepseek.com\/v1$/d' ~/AppData/Local/hermes/config.yaml

# 3. Set fallback chain for resilience
hermes config set model.fallback "google/gemini-2.5-flash,custom:ollama-local/qwen3:14b-ctx"
```

Native providers (deepseek, openrouter, anthropic, google, xai) know their own API endpoints — `base_url` is only needed for `custom:...` providers.

## Fallback Chain Syntax

```bash
hermes config set model.fallback "provider1/model1,provider2/model2"
```

Comma-separated `provider/model` pairs. Tried in order when the primary fails.

## Full Provider Stack Example

```yaml
model:
  default: deepseek/deepseek-chat
  provider: deepseek
  fallback: google/gemini-2.5-flash,custom:ollama-local/qwen3:14b-ctx
```

Primary → DeepSeek API (paid, cheap, fast)
Fallback 1 → Gemini Flash via OpenRouter (often free tier)
Fallback 2 → Local qwen3:14b via Ollama (free, always available)
