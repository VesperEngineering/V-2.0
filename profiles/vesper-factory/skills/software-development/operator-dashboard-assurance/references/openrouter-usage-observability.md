# OpenRouter usage observability

## Read-only endpoint

For OpenRouter management/provisioning keys, use:

```text
GET https://openrouter.ai/api/v1/activity
Authorization: Bearer $OPENROUTER_MANAGEMENT_API_KEY
```

`/api/v1/key` can confirm key metadata and `/api/v1/credits` can expose account credit information, but `/api/v1/activity` is the useful usage source. Do not log the key, raw Authorization header, or unfiltered account response.

For a provider-accounting card, keep these scopes separate:

- `/activity` is account activity and is useful for daily spend, requests, and tokens.
- `/key` can expose a finite key limit and cumulative key usage. When both `data.limit` and `data.usage` are finite nonnegative numbers, remaining dollars are `max(0, limit - usage)`.
- `/credits` is a useful fallback for credit-based accounts. When `/key` has no finite limit, use `data.total_credits` and `data.total_usage` and compute `max(0, total_credits - total_usage)`.

If neither endpoint reports a finite budget, render `$ left unavailable`; do not infer a budget from today's spend, cached buying power, or a local receipt ledger. Use the API key only for these read-only calls, keep management-key activity access separate, and never print credentials or raw authorization headers.

## Activity row fields

Activity rows are aggregate records with fields such as:

- `date`
- `model`, `model_permaslug`, `provider_name`
- `requests`
- `prompt_tokens`, `completion_tokens`, `reasoning_tokens`
- `usage`
- `byok_requests`, `byok_usage_inference`

Aggregate by date and model/provider for daily spend, request count, and token volume. Treat the endpoint's daily values as authoritative for daily totals.

## Hourly-rate limitation

The activity endpoint may not provide historical hourly buckets. Estimate current hourly burn from successive snapshots:

```text
hourly_rate = max(0, current_cumulative_usage - prior_cumulative_usage) / elapsed_hours
```

Persist only sanitized snapshot metadata locally: observation time, cumulative usage, current-day totals, request count, token count, and derived rate. On the first snapshot, report `hourly rate unavailable` rather than inventing a rate. Use a bounded in-process/cache TTL (about one minute for a refreshing TUI) to avoid making a management request every render tick.

## Schema and cache integrity

Validate the response envelope before aggregating or saving it. A successful HTTP status with a missing `data` key, top-level list, mapping-valued `data`, `null`, or non-object rows is not a valid zero-usage observation. Route every invalid shape through the unavailable/stale path and preserve the last-good cache. Prefer one explicit envelope/row-type gate that raises the service's existing typed schema failure before aggregation; do not add a broad `TypeError` catch that can conceal unrelated programming defects.

Treat cache contents as untrusted local data: require parseable observation time, finite nonnegative totals, and the expected field types before using them. Do not let a malformed response or cache overwrite a valid nonzero snapshot with fresh zeroes. Keep the source observation timestamp when serving stale data, and consider an explicit maximum stale age for operator decisions.

A derived reconciliation inherits source freshness. A stale last-good account total may remain displayable with its source timestamp, but it is not eligible for a current reconciliation: pass `None`/unknown into the reconciler, render attributed/unattributed output with an explicit `STALE` qualifier, and do not expose a stale-derived dollar value as current merely because the account line carries a warning. The regression should capture the exact downstream reconciliation argument as well as checking presentation; an outer stale label is insufficient if stale numbers still crossed the calculation boundary.

## Secret handling

Store the management key in a gitignored environment file under a dedicated name such as `OPENROUTER_MANAGEMENT_API_KEY`. Read it from the environment first, then the local env file. Never put it in source, generated dashboard payloads, logs, tests, screenshots, or activity text. If a user pastes a live key into chat, recommend rotation after confirming the integration.

## Display contract

Show concise operator values such as:

```text
OpenRouter $12.52 today  $0.00/hr est  1187 requests
```

Label the hourly value as an estimate. Keep daily authoritative usage separate from local-rate estimation. On API failure, show `usage unavailable` and preserve the last good dashboard snapshot; do not render zero as if it means no spend.

## Verification

Use a live read-only probe that reports only HTTP status/response shape and aggregate totals. Add fixture tests for date aggregation, token counting, cache persistence, missing-key behavior, redacted errors, malformed response envelopes, stale-cache retention, stale reconciliation labeling, and future/too-short elapsed intervals. Confirm the focused dashboard suite still passes after integrating the usage line, then run a minimal adversarial probe proving that invalid JSON shapes cannot become a fresh zero or overwrite last-good cost data.