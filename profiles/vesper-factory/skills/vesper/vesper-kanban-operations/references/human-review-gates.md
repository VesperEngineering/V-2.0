# Hermes Kanban Human-Review Gate Evidence

Use this note when designing proposal-to-Kanban bridges. Re-verify against the installed `hermes kanban create --help`, current official Kanban docs, live config, and installed source before relying on any status semantics.

## Current findings (2026-07-20)

1. `--initial-status blocked` creates a blocked task without a manual `block_kind`. An isolated real-board probe observed the task later receive a `promoted` event and become `ready`.
2. The current CLI uses `--triage`; `--initial-status triage` is not accepted.
3. Triage is not a human-only hold by default. Official docs state `kanban.auto_decompose: true` by default. The gateway re-reads that toggle every dispatcher tick and can call the decomposer for triage tasks.
4. Successful auto-decomposition can rewrite the root, create child tasks, move the root to `todo`, auto-promote children, and allow normal dispatch.
5. A two-command workaround—create blocked, then `block --kind needs_input`—is not atomic. The gateway may act between commands.

Relevant installed-source surfaces:

- `hermes_cli/kanban.py`: `create --triage`, `--initial-status`, and typed `block --kind` CLI contracts.
- `hermes_cli/kanban_db.py`: task creation, initial status, `block_kind`, and ready recomputation.
- `gateway/kanban_watchers.py`: per-tick auto-decompose configuration and triage sweep.
- Official docs: `https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban`.

## Safe architecture

- Persist bounded, idempotent proposals in a non-runnable proposal ledger.
- Render that ledger in VOT and Telegram.
- Record authenticated exact-scope approval separately.
- Only after approval, create/promote a runnable Kanban card through audited CLI writes.
- Keep broker/order, risk, scheduler, provider, model-promotion, and secret authority separately gated.

## Isolated verification recipe

1. Create a temporary `HERMES_HOME` and temporary board.
2. Exercise the exact installed `hermes.exe`/`hermes` CLI—not a mock.
3. Publish the same idempotency key twice and require one task ID.
4. Read the temporary SQLite task row and `task_events` stream.
5. Wait longer than the relevant dispatcher interval or run the real gateway against the temporary home when testing automatic transitions; a five-second no-gateway observation proves only creation/read-back, not durable production behavior.
6. Confirm the production board has no matching `created_by` or idempotency key.
7. Treat any unexpected `promoted`, `decomposed`, child creation, status drift, malformed output, or ambiguous read-back as unknown/fail-closed.

## Reporting rule

Do not claim a review gate from a unit test or immediate read-back alone. State separately:

- atomic create result;
- idempotent replay result;
- observed event stream;
- live orchestration configuration;
- gateway-duration observation;
- production-board non-mutation proof.
