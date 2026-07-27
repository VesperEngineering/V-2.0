# Duplicate Windows gateway restart from a one-time task

## Failure pattern

A temporary Windows task is created with a future `TimeTrigger`, then manually started with `schtasks /Run` to apply a Hermes configuration change immediately. The manual run succeeds, but it does not consume the future trigger. Windows executes the same gateway restart again at the original boundary.

Typical evidence:

- `gateway-exit-diag.log` records a clean planned stop rather than a crash.
- `schtasks /Query /TN <task> /XML` shows a future or already-fired `StartBoundary` and an action such as `hermes gateway restart`.
- The task's output log reports a clean stop/start.
- Hermes `agent.log` can correlate task creation with the originating session and approval.

## Correct procedure

1. Confirm a restart is actually required and obtain explicit approval.
2. Prefer an immediate external `hermes gateway restart` when no active work will be interrupted.
3. If a scheduled task is necessary, use a unique temporary name and record it before execution.
4. Never combine a future `TimeTrigger` with `schtasks /Run` unless a second restart is intentional.
5. After the approved immediate restart, delete the temporary task from an external process:

   ```text
   schtasks /Delete /TN <temporary-task-name> /F
   ```

6. Delete any temporary XML used to register it.
7. Verify `schtasks /Query /TN <temporary-task-name>` reports that the task does not exist.
8. Check `hermes gateway status` and active worker heartbeats.

## Reporting contract

Distinguish clearly between:

- a crash;
- a user-initiated restart;
- an agent-created scheduled restart;
- an unintended duplicate restart caused by stale scheduler state.

If the agent created the stale task, say so directly. Do not imply that the user manually shut down the gateway merely because the task ran under the user's Windows account.
