# Worker activity, blocked gates, and review boundaries

## Source-of-truth pattern

A coordinator log is not a live worker feed. Use a separate bounded JSONL stream with redacted fields:

```json
{"ts":"...","worker":"Clarke","lane":"pipeline","state":"blocked","activity":"ALREADY_SCORED: 20260713"}
```

Use `cycle` for Steward markers, `delegated` for dispatch signals, and `started`/`working`/`completed`/`failed` only when a worker actually emits those lifecycle events. Lane ownership alone does not prove current work.

## No-retry gate

Before dispatching a worker, compare the current prerequisite failure signature with the last recorded signature for that lane. If unchanged:

- do not dispatch or spend model tokens on investigation;
- suppress duplicate blocked events or mark them as unchanged;
- rotate to the next actionable lane;
- retry only after the input/state changes or an authorized escalation occurs.

Local shell prerequisite checks may still run; they are not equivalent to a worker retry.

## Review boundary

Worker `completed` is self-report, not acceptance. A manager/reviewer layer must validate the claimed artifact, receipt, tests, and lane acceptance criteria before marking work accepted. Use separate states such as `needs_review`, `clarification_requested`, `accepted`, and `rejected`; do not silently convert an unverified completion into progress.

## Operator presentation

Render blocked checks as `blocked gate — OWNER` (or equivalent), not as `OWNER working`. Include a short reason and timestamp. This prevents a Clarke-owned blocked prerequisite from falsely appearing as Clarke being stuck.
