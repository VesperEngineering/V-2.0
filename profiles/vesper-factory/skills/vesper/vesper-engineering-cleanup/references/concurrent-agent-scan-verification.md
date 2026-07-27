# Concurrent Agent Scan Verification

Use this when another Hermes/Codex session is already inspecting or editing Vesper.

## Observe safely

- Search Hermes logs for the exact session ID.
- Read the latest matching entries from `agent.log`, `errors.log`, and `gui.log`.
- Record the active model/provider, last tool actions, delegated-agent completion, and final termination reason.
- A session may have ended its main turn while a background review/curator is still running; distinguish those phases.
- Avoid repository edits until all writers have stopped.

## Determine what actually changed

- Use task scope and file modification times to identify likely new artifacts.
- Treat a large pre-existing dirty tree as unrelated unless the session log directly ties a file to a tool action.
- Read new tests and every imported production module. A test file can be present while its target module is absent.

## Verify completion

Run narrow checks first:

1. Import/collection check for newly added tests.
2. Focused unit tests for the new module.
3. Focused integration/backtest tests.
4. Full suite only after focused checks pass.

Completion requires all of the following:

- Every promised production artifact exists.
- Tests collect successfully.
- Focused tests pass from a fresh run.
- Historical/backtest evidence exists when the task is empirical.
- No claim relies solely on the agent's prose summary.

## Common incomplete-state pattern

An autonomous turn can hit `max_iterations_reached` after repairing unit tests but before writing an integration module. Delegated agents may then return design advice without applying code because their workspaces are isolated. The result can look complete in the transcript while a fresh test run fails during collection.

## Control subscription usage

Subscription-backed Codex OAuth removes per-token billing but not provider usage limits. Broad autonomous scans can generate dozens of model calls and very large cached contexts. Give future agents:

- A bounded deliverable list
- Explicit non-goals
- Focused verification commands
- A maximum iteration/call budget
- A stop condition requiring a user handoff when evidence is incomplete
