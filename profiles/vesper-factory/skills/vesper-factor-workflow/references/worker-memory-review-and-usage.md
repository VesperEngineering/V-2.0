# Vesper Worker Memory, Review, and Usage Reference

## Persistence hierarchy

- Hermes memory: stable user/project context.
- `AGENTS.md`: static project constitution and authority boundaries.
- `.hermes/team_memory.json`: curated cross-worker discoveries, blockers, and decisions.
- `.hermes/workers/<worker>.md`: role-specific accepted knowledge, proposed knowledge, and superseded entries.
- `.hermes/learnings.jsonl`: append-only cycle journal; append, never overwrite.
- `.hermes/activity.jsonl`: operational event stream; delegation is not proof of execution.

## Completion review

Emit a worker completion only with an in-repository artifact or receipt plus explicit passing verification. If evidence is absent, emit `needs_review`; do not blind-retry. A JSON receipt must itself have a passing `status` or `state`.

Recommended event command:

```bash
python scripts/emit_worker_activity.py \
  --worker NAME --lane LANE --state completed \
  --activity "short result" \
  --artifact artifacts/evals/result.md \
  --receipt artifacts/evals/receipt.json \
  --verification "PASS: exact check"
```

## Truthful worker status

Render current status separately from recent events:

- `started` / `working` → `RUNNING`
- `delegated` → `PENDING`
- `completed` → `COMPLETE`
- `needs_review` → `REVIEW`
- `blocked` / `skipped` → `IDLE`
- old running/pending event → `IDLE` with last-event age

Lane owner attribution must never be presented as active work.

## OpenRouter usage

Use the management key only through a gitignored environment variable such as `OPENROUTER_MANAGEMENT_API_KEY`. Query:

```text
GET https://openrouter.ai/api/v1/activity
```

The endpoint provides daily aggregate rows by model/provider with usage, requests, prompt tokens, completion tokens, and reasoning tokens. Cache reads to avoid polling every UI refresh. Daily totals are authoritative; hourly spend is an observed local delta between snapshots, not historical hourly data. Never log or render the key.

If the key was pasted into chat or another potentially exposed channel, rotate it after confirming the integration and replace the environment value.

## Factor-worker handoff

For FM mortality findings, distinguish:

1. Research memo recommendation
2. Code/configuration change
3. Fresh regenerated factor artifact
4. Paper/shadow evidence
5. Manager acceptance
6. Promotion authorization

Verify the actual registry, `FACTOR_WEIGHTS`, and `GOVERNED_FACTOR_WEIGHTS` against worker claims. A team-memory entry alone does not prove that a change was applied, and applied weights do not authorize live execution.
