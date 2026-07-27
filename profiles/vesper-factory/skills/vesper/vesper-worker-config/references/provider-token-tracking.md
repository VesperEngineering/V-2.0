# Provider Token Tracking in Operator Terminal

When switching workers from OpenRouter to openai-codex, the provider accounting panel showed `$0.00` because Codex is a subscription (not per-token billing). The fix was to add token aggregation to the existing `provider_request_ledger` infrastructure.

## Files Changed

### `app/services/provider_request_ledger.py`
- Added token fields to `ProviderReconciliation` dataclass: `total_prompt_tokens`, `total_completion_tokens`, `total_tokens`, `codex_prompt_tokens`, `codex_completion_tokens`, `codex_tokens`, `openrouter_prompt_tokens`, `openrouter_completion_tokens`, `openrouter_tokens`
- Updated `reconciliation()` to sum tokens per provider from completed events

### `app/services/operator_terminal_status.py`
- Updated `load_provider_accounting()` to render token counts in the reconciliation string
- Added `_compact_number()` helper for formatting large token counts (e.g. 4200 → "4.2K")

## Display

The PROVIDER ACCOUNTING card now shows tokens alongside dollar amounts:
```
Codex 4.2K tok  OR 691 tok  total 4.9K tok  receipts 6
```

## How Events Flow

1. Workers make LLM requests through the kanban dispatcher
2. Each request is logged as a `started`/`completed` event in `.hermes/provider_request_events.jsonl`
3. Events contain: `provider` (openrouter|openai-codex), `model`, `prompt_tokens`, `completion_tokens`, `cost_usd`
4. Both providers feed into the same hash-chained ledger
5. The dashboard reads the ledger on every refresh cycle

## Valid Providers

Defined in `VALID_PROVIDERS`: `openrouter`, `openai-codex`, `unknown`