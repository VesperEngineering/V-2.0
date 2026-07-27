# Model Catalog Cache Format

The dashboard picker reads from `~/.hermes/cache/model_catalog.json`. Each model entry is:

```json
{
  "id": "provider/model-slug",
  "description": "optional badge text"
}
```

The `description` field drives picker badges (e.g. "free", "recommended", "default"). One entry can be marked `"default": true` — that's the model Hermes silently lands on when the user never picked one.

## OpenRouter Section Shape

```json
{
  "version": 1,
  "updated_at": "2026-07-16T19:45:30Z",
  "providers": {
    "openrouter": {
      "metadata": {
        "display_name": "OpenRouter"
      },
      "models": [
        {"id": "openai/gpt-5.6-sol", "description": ""},
        {"id": "google/gemini-2.5-flash", "description": ""},
        {"id": "deepseek/deepseek-v4-flash", "description": ""}
      ]
    },
    "nous": {
      "metadata": {
        "display_name": "Nous Portal"
      },
      "models": [
        {"id": "anthropic/claude-sonnet-5"}
      ]
    }
  }
}
```

## How Refresh Works

- TTL: 1 hour (configurable via `model_catalog.ttl_hours`)
- Fetch: `model_catalog.url` → fallback: raw GitHub copy
- If fetch fails, stale cache is kept
- `hermes update` seeds the cache from the local checkout (no network needed)

## Models Added to Cache (2026-07-16)

The following were manually added to the local cache for the Vesper OpenRouter picker:

- `openai/o4-mini`
- `openai/gpt-5.4-nano`
- `google/gemini-2.5-flash`
- `google/gemini-2.5-flash-lite`
- `google/gemini-2.5-pro`
- `google/gemma-4-26b-a4b-it` (free)
- `google/gemma-4-31b-it` (free)
- `mistralai/codestral-2508` (coding)
- `mistralai/mistral-large-2512`
- `mistralai/mistral-small-3.2-24b-instruct`