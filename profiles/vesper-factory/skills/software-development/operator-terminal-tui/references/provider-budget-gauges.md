# Provider Budget Gauges

Reusable pattern for provider-accounting display iterations.

## Truth contract

- Keep authoritative numeric capacity fields on the immutable provider snapshot.
- Preserve the existing human-readable usage strings; gauges are additive, not a replacement for token counts, receipts, or observed/stale labels.
- OpenAI/Codex weekly capacity may be rendered as a percentage bar only when the source reports a bounded `remaining_percent` value.
- OpenRouter may expose `remaining_budget_usd` without a total budget. Render the dollar amount as a badge; never manufacture a percentage denominator from daily spend, hourly rate, or account aggregate.
- `None`, stale, malformed, negative, non-finite, and unavailable values render an explicit unavailable state. Do not coerce them to zero.
- Keep provider account totals, workspace/session telemetry, and Vesper-local receipt attribution visibly separate.
- Add a compact freshness row from the provider snapshot's `state` and `observed_at`: `READY`, `STALE`, or `UNAVAILABLE` plus a normalized UTC observation time. A malformed timestamp must render as unavailable, never as the current time.

## Implementation pattern

1. Extend the immutable provider snapshot with optional numeric fields defaulting to `None`, preserving old positional callers and fixtures.
2. Populate those fields from the already-authoritative loader objects. Use `getattr(..., None)` for older test doubles or payloads that do not carry the optional field.
3. Put normalization in a small renderer helper: finite percentage → clamp to `0..100`; finite nonnegative dollars → fixed currency formatting; otherwise unavailable.
4. Use a bounded visual treatment. A 10-cell bar is sufficient for a percentage; a dollar badge is the honest treatment when no denominator exists.
5. Keep the visual rows short enough for the medium supported grid. Probe the exact target grids rather than trusting the wide layout.

## Test pattern

Add both layers:

```python
# loader propagation
assert result.openrouter_remaining_budget_usd == 7.48
assert result.openai_remaining_percent == 93.0

# pure render
assert "BUDGET / LEFT" in text
assert "OPENAI [█████████░] 86% left" in text
assert "OPENROUTER [$12.34 left]" in text
assert "FEED STALE · OpenAI/OpenRouter · 17:00Z" in text
```

Also retain existing assertions for token counts, weekly reset/percentage text,
receipt reconciliation, stale behavior, and provider scope. Run a fresh pure
render at `312×63`, `180×50`, and `120×35`, checking row count, maximum line
width, footer retention, and that the gauge rows remain visible.

## Pitfalls

- Parsing `"Weekly 86% left"` or `"$12.34 left"` back into numbers in the renderer couples presentation to telemetry formatting.
- Showing a percentage for OpenRouter from `$ left / today's spend` is an invented ratio.
- Moving the numeric fields only into a UI fixture proves the renderer but not the production loader.
- Rewriting a ternary expression with a targeted patch can accidentally drop its `if/else` branch; compile and run the focused status tests immediately after the edit.
