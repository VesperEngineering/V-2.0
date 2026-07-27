# Kanban Triage And Transitive Side-Effect Audit

Use this checklist when a governed integration claims to publish a card for human review without provider calls, dispatch, scheduling, or execution.

## Do not infer semantics from the status name

A status named `triage` is not automatically a durable human hold. Inspect the exact installed CLI and gateway implementation:

1. Read `kanban create --help` and the installed create handler.
2. Trace every gateway/daemon sweep that selects `status='triage'`.
3. Read the effective runtime configuration, especially auto-specification/decomposition, child auto-promotion, dispatch interval, and gateway dispatch enablement.
4. Trace the complete transition: triage card -> auxiliary LLM/provider -> specification or decomposition -> `todo`/`ready` -> worker claim.
5. If any automatic path exists, `--triage` alone does not prove human review. Require a durable per-card exclusion understood by every sweeper, or fail publication when that guarantee cannot be established.

A short observation window proves almost nothing when the dispatcher interval is longer. Prefer invoking the exact sweep deterministically in an isolated temporary board. If a real-time probe is needed, observe for longer than the configured interval and verify task rows, child rows, runs, events, and provider-call traps—not merely that only a `created` event exists after a few seconds.

## Idempotency and read-back

- Lock lookup -> create -> read-back across cooperating publisher processes.
- Check whether the underlying CLI idempotency key is transactionally unique; a non-unique index plus pre-insert lookup is not independently race-safe.
- After create, read the authoritative persisted row and verify task ID, status, assignee, creator, workspace, and any dispatch-relevant fields.
- On replay, do not accept an arbitrary nonempty status while reporting `dispatch_authorized=false`. Either require the safe hold status or return truthful lifecycle/authority state and fail closed when the card has moved unexpectedly.
- Test crash-after-create recovery and ambiguous/multiple bindings.

## Trace default loaders transitively

A parameter such as `provider_telemetry=None` does not prove that a shared dashboard loader is provider-free. Trace every function called by the real default loader. Provider-accounting helpers may conditionally:

- read opt-in or credential settings;
- call management/account APIs;
- update local usage caches;
- fall back to stale cached observations.

For a no-provider/no-mutation command, use a structurally local-only loader rather than relying on the current environment having an opt-in disabled. Tests should execute the real default loader with network functions and filesystem writes trapped; replacing the entire loader with a mock only proves dependency injection.

## Failure semantics and bounds

- For bounded multi-card publication, report prior successful card IDs if a later card fails; a generic failure response must not hide committed mutations.
- `capture_output=True` followed by a length check does not bound subprocess memory use because buffering already occurred. Stream into a bounded reader or otherwise enforce the limit during collection.
- Keep subprocess calls as fixed argv with `shell=False`, a timeout, bounded fields, and sanitized errors.
