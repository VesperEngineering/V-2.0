# Named-Worker Flow Audit

Use this checklist when a system claims durable named workers, specialist skills, escalation, or autonomous wake-up behavior.

## Distinguish configuration from activity

Verify each layer independently:

1. **Profile exists** — a named profile is configured.
2. **Profile runtime state** — running, stopped, or only invoked by a scheduler.
3. **Skill inventory** — skills are installed and enabled for that profile.
4. **Role specialization** — the profile's skills, prompt, and authority differ meaningfully from peers. Identical broad skill inventories prove capacity, not specialization.
5. **Durable worker knowledge** — accepted/proposed/superseded entries exist with evidence and validation dates. Empty files mean the learning loop has not accumulated knowledge.
6. **Lane eligibility** — the lane is enabled, has an explicit work packet, and completed packets become ineligible.
7. **Escalation state** — stuck counters actually advance. A configured threshold is inert if the counter remains zero.
8. **Dispatch evidence** — require a real spawn/delegation/provider receipt or named-profile session. A heartbeat, local cycle, memory update, or briefing is not a worker wake-up.
9. **Completion evidence** — match the worker's output to the exact packet and lane before marking work complete.

## Source-first inspection order

Inspect live sources rather than relying on dashboard labels:

- profile list and runtime states;
- scheduler/cron definitions and last runs;
- latest named-worker and steward sessions;
- lane manifest and steward state;
- worker knowledge files;
- dispatch/provider receipts;
- output artifact and review receipt.

## Common false positives

- A named profile exists but is stopped and has never run.
- Every specialist has the same large skill inventory, so role boundaries exist only in prose.
- A briefing job reviews outputs but has no dispatch authority or work-packet routing.
- A steward increments cycle counts and updates memory without spawning a worker.
- A completed lane remains eligible and is selected repeatedly.
- `stuck_cycles` never increments, so escalation to strategy leadership never fires.
- A job reports `ok` because it wrote a state file, despite producing no actionable state change.

## Scheduler-authority audit

Inventory all schedulers before adding or evaluating worker flow: Windows Task Scheduler, Hermes cron, gateway dispatchers, repository daemons, and manual recovery jobs. Same-time jobs may be redundant checks, or they may be competing production authorities. Prefer one primary, one conditional recovery path, and read-only review/briefing jobs. A briefing should not silently become a mutation lane.

## Healthy flow contract

A healthy named-worker flow is:

`eligible work packet → atomic claim → named worker dispatch → evidence artifact → independent review → durable knowledge proposal → Steward/strategy acceptance`

Waiting for fresh data should be silent or explicitly `waiting`; it should not manufacture cycle counts or worker activity. Skills grant capability only—never authority.