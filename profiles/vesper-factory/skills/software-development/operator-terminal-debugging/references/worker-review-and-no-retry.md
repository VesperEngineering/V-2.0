# Worker review and no-retry pattern

## Structured event contract

Persist bounded JSONL events with:

```json
{
  "ts": "2026-07-15T03:02:18Z",
  "worker": "Rez",
  "lane": "research",
  "state": "started|working|completed|needs_review|blocked|failed",
  "activity": "short operator-safe description",
  "artifact": "optional in-repository path",
  "receipt": "optional in-repository receipt path",
  "verification": "optional explicit passing check"
}
```

Never persist prompts, hidden reasoning, credentials, or raw tool output.

## Completion gate

A `completed` event is accepted only when:

1. An in-repository artifact or receipt exists.
2. Verification explicitly passes.
3. A supplied JSON receipt has a passing status.

Otherwise downgrade it to `needs_review`; do not automatically dispatch the worker again.

## Unchanged-block handling

Store a per-lane blocked signature such as:

```text
pipeline: WAITING_FOR_NEW_OHLCV: latest admitted date 20260713 already scored
```

Run the cheap local prerequisite check as needed, but suppress duplicate blocked events and do not spend model tokens retrying the lane. Re-open the lane only when its signature changes, the upstream input changes, or an authorized escalation occurs.

## UI semantics

- `Steward` identifies coordinator cycle markers.
- A lane owner on a blocked event identifies accountability for the lane, not active execution.
- Use `WAITING` or `BLOCKED GATE` language to avoid implying the owner is repeatedly working.
- Show `needs_review` as unresolved; it is not success and is not permission to retry.
