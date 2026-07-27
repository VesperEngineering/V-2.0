# Reversible least-privilege toolsets for Kanban workers

## Purpose

Use this when a profile must temporarily expose only the tools admitted by a worker or reviewer contract. Tool restriction must be in place before the dispatcher starts a new session; tool changes do not retroactively change an existing session.

## Transaction

1. Identify the exact profile `config.yaml` selected by the assignee.
2. Copy it byte-for-byte to an external evidence directory and record SHA-256 for source and backup.
3. Change only `platform_toolsets.cli`:
   - artifact producer: `[file]`;
   - test-running read-only reviewer: `[file, terminal]`.
4. Parse the whole YAML after editing. Assert:
   - `platform_toolsets.cli` is a list, not a quoted scalar containing JSON-like text;
   - its members exactly equal the approved set;
   - sibling platform toolsets retain their original values;
   - model/provider/reasoning, credentials, gateway, and memory settings are unchanged.
5. Create or release the task only after the restricted config and exact-source branch are both verified.
6. Wait for the spawned worker process/session to become terminal, not merely the task row to become `done`.
7. Restore the original config bytes from the backup, hash both paths, and require equality before continuing acceptance.

## Editing lists safely

`hermes config set` is convenient for scalar values. For list-valued keys, inspect the saved YAML rather than trusting command output: a shell-quoted value can be persisted as one string such as `'["file"]'` instead of a YAML list.

For a temporary list edit, use a deterministic method with all of these properties:

- assert the old byte/text block occurs exactly once;
- replace only that block;
- parse the full result;
- compare sibling keys to the pre-edit parse;
- retain the original byte backup for unconditional restoration.

Do not accept a visually plausible diff as sufficient; indentation-sensitive YAML can silently attach a platform's toolset to the wrong key.

## Dispatcher interaction

The Kanban dispatcher resolves the assignee profile's effective CLI toolsets when it spawns the worker. Task-scoped Kanban lifecycle controls are then added for the claimed task. Therefore a worker profile does not need broad `hermes-cli`, skills, web, memory, or terminal toolsets merely to call task show/complete/heartbeat controls.

Precreate the task's named branch at the exact source commit. A blocked task can still be promoted by automation, so configuration and branch admission must be safe before task creation or before any promotion path can run.

## Verification evidence

Persist:

- pre-edit and restored profile hashes;
- parsed temporary CLI toolset;
- task/run/session IDs;
- exact source SHA and worktree branch;
- complete ordered session tool-call names;
- confirmation that original profile bytes were restored.

If restoration or full-session capability audit fails, stop and classify the run as HOLD.
