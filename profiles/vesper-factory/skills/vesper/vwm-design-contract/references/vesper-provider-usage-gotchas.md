# Vesper Provider Usage Gotchas

## OpenRouter usage shows "unavailable"

**Symptom:** Appbar shows `OR usage unavailable` instead of real usage data.

**Root cause:** The `fetch_usage()` function in
`app/services/openrouter_usage.py` has a **two-gate opt-in**:

1. `VESPER_OPENROUTER_USAGE_ENABLED=true` must be set in `.env`
   (line 166). If not set, returns `management_account_access_not_enabled`.
2. `OPENROUTER_MANAGEMENT_API_KEY=***` must be configured (line 174).
   This is a **separate management key** from the regular
   `OPENROUTER_API_KEY` used for model calls.

The error message "management account access not enabled" is misleading —
it really means "you haven't opted in to usage tracking."

**Fix:** Add both env vars to `D:\vesper\.env`:
```
VESPER_OPENROUTER_USAGE_ENABLED=true
OPENROUTER_MANAGEMENT_API_KEY=sk-or-v1-...   # from OpenRouter dashboard → Keys → Create Management Key
```

**If you can't get a management key:** The appbar should show the usage
*string* fields (`openai_usage`, `openrouter_usage`) which always have a
readable summary, NOT the numeric fields (`openai_remaining_percent`,
`openrouter_remaining_budget_usd`) which are `None` when access isn't
enabled. See `vot_tk.py::_apply_snapshot` for the correct string-based
appbar usage rendering.

## OpenAI usage shows "0 tokens"

**Symptom:** Appbar shows `OAI 0 tokens` even when Codex is active.

**Root cause:** The `CodexActivityTracker` reads from local Codex
activity logs, not the OpenAI API. If Codex hasn't been used recently
or the activity log is empty, it reports 0 tokens.

This is the honest state — not a bug. The `openai_remaining_percent`
field is `None` because the Codex OAuth flow doesn't expose quota
information through the same path as the API key flow.
