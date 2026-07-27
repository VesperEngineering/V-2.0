# Desktop GUI Runtime Audit — Probe Patterns

Use this reference for read-only audits of long-lived desktop/operator UIs. Keep all mutation-capable dependencies mocked and keep temporary fixtures outside the audited repository.

## 1. Freeze and defend the audit boundary

Capture at the start:

```text
git root
full HEAD SHA
branch
status --short
worktree inventory
```

Recheck status before reporting. If a tracked file becomes dirty during the audit:

- Do not assume your probe caused it.
- Compare initial and final status.
- Bind findings to the frozen SHA and verify baseline source with `git show <sha>:<path>`.
- Describe the new dirty diff separately as concurrent/unverified mitigation.
- Never quote working-tree line numbers as if they came from the frozen commit.

## 2. Poll/timer state table

Build one row for each transition:

| Trigger | Producer state | Queue write | UI apply | Next timer | Failure behavior |
|---|---|---|---|---|---|
| startup | idle → running | expected payload | initial render | scheduled where? | retry or stop? |
| scheduled poll | guard? | bounded? | signature redraw? | before/after work? | timeout? |
| manual refresh | cancels which timer? | can overlap? | stale result guard? | duplicate chains? | visible error? |
| close | cancellation token? | late writes? | widget destroyed? | timers cancelled? | threads joined? |

Red flags:

- Next poll is scheduled only on successful apply.
- No in-flight flag or generation number.
- Unbounded `Queue()` plus unlimited drain loop.
- Fresh tracker/supervisor objects are reconstructed each poll even though they own baselines, last-good pointers, sessions, or background tasks.
- A worker invokes UI methods directly instead of queueing an immutable result.

## 3. Deterministic stale-response race probe

Patch detail fetches so request A sleeps and request B returns immediately:

```python
rendered = []
select("A")  # delayed
select("B")  # immediate
wait_for_both()
assert current_selection == "B"
assert rendered[-1] == "B"  # failure proves missing generation/identity guard
```

A safe design queues `(request_generation, selected_id, payload)` and discards any result that does not match current state.

## 4. Error-retry probe

Use a fake root whose `after(delay, callback)` records calls. Push one error result through the real queue-drain method. Verify both:

1. the error is visible, and
2. a bounded refresh retry is scheduled.

A drain-only callback is not a poll retry. Also test an indefinitely blocked producer: completion-coupled scheduling cannot recover from a hang without an outer timeout/cancellation path.

## 5. Redraw/signature probe

Create two payloads with the same ID/status but different visible fields such as title, assignee, detail, timestamp, priority, or ordering. If signatures compare equal while pixels/text would differ, the cache is incorrect.

For each rebuild, inspect:

- selected item reconciliation when an item disappears or becomes inactive;
- canvas/text `yview` capture and restoration;
- manual-follow state;
- mouse-wheel bindings on actual child widgets under the pointer;
- whether no-op polls avoid widget destruction.

## 6. Action safety probe

Patch the command wrapper; never invoke a live action. Exercise success, nonzero result, timeout, and first-step-success/second-step-failure.

Audit two independent layers:

- **Command construction:** argv list, no shell interpolation, bounded timeout, console suppression, sanitized output.
- **Authority/lifecycle:** authenticated identity, immutable target/scope, current-state precondition, confirmation, idempotency, transaction/compensation, surfaced result, and no synchronous UI-thread wait.

A shell-safe command can still be a critical authority bypass.

## 7. Log-follow probe

Create a temporary log with a distinct marker only at the tail. Verify the reader:

- seeks/reads a bounded tail rather than loading the whole file;
- returns the newest bytes/lines;
- strips unsafe terminal control sequences if rendered;
- changes its signature when new tail data arrives;
- preserves scroll only when follow is off.

## 8. Deployment reproducibility triad

Compare three evidence classes separately:

1. **Live:** shortcut target, arguments, working directory, icon, currently running executable.
2. **Tracked:** installer/launcher, expected asset path, supported entry point.
3. **Gated:** CI compile list, focused tests, packaging/release checks.

A live shortcut that points at untracked assets or an entry point absent from installers/CI is deployment drift, even when it launches successfully on the auditor's machine.

## 9. Read-only verification discipline

Preferred checks:

- AST parse/import without bytecode writes.
- Lint with cache disabled.
- Focused tests with cache provider disabled and external temporary roots.
- Fake Tk roots/widgets and patched command/data providers.
- Temporary SQLite fixtures opened outside the live board path.
- CLI `--help` for argument-shape verification only.

Do not launch the mutation-capable UI, click live controls, or call production write wrappers merely to prove they exist.
