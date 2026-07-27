---
name: native-operator-console-release
description: Release a trustworthy native operator console with bounded refresh lifecycles, fail-closed evidence posture, independent review, and real launcher proof.
version: 1.0.0
---

# Native Operator Console Release

Use for Tkinter/native local operational desks that read evidence asynchronously and may expose tightly bounded administrative controls. Optimize for trustworthy posture and recovery, not feature breadth.

## Release contract

1. Work in an isolated worktree from a recorded canonical HEAD. Capture canonical dirty paths first; never absorb them.
2. Define the full page/surface contract and authority matrix before editing. Read-only evidence must never inherit authority from status color or freshness.
3. Every unavailable/malformed/read failure is visible as `STALE`, `ERROR`, `UNAVAILABLE`, or `UNKNOWN`. Last-good content may remain only behind a visible stale attribution.
4. `LIVE` is a static posture, never a changing clock presented as freshness proof.
5. Administrative mutations must remain exact-scope, canonical-root guarded, explicitly confirmed, and separate from authority-bearing operations.
6. Broker/order, spend/provider, scheduler, risk, promotion, deployment, credential, and permission authority stays closed unless an explicit separate approval says otherwise.

## Async lifecycle closure audit

Audit the whole application, including legacy callbacks, not just new code.

- Each background source has one ownership model: bounded/coalescing coordinator or a fixed-budget compatibility queue.
- Carry source and request identity through both success and error results.
- Rapid A→B→C selection must coalesce to the latest requested item. “One in flight” alone is insufficient if the latest request is discarded.
- A stale result—success or error—must not overwrite or falsely stale the current selection.
- Never evict a terminal result if application state relies on handling it to clear an in-flight flag or schedule the next poll.
- Apply a total fixed drain budget across every queue in a UI tick.
- Close must cancel timers, reject late completions, and suppress queued follow-up work.

## Test-first release slices

For each lifecycle behavior:

1. Write a focused regression test and run it red.
2. Implement the smallest change.
3. Run the focused test green.
4. Run the full console suite using an isolated pytest temporary base when needed.

Mandatory regressions for selection-driven readers:

- repeated request for the same item does not overlap;
- A→B→C starts A and then exactly one follow-up for C;
- stale A success does not overwrite C;
- stale A error does not mark C’s retained data stale;
- close before A finishes prevents the queued C follow-up;
- queue pressure cannot strand snapshot/poll flags.

## Verification and independent review

Before commit:

```bash
git diff --cached --check
python -m pytest --basetemp=.tmp-pytest-console <console tests> -q
python -m ruff check <changed source/tests>
python -m compileall -q <changed source/tests>
```

Use a fresh reviewer. In its brief require inspection of all async producers, stale success/error attribution, authority boundaries, and legacy queues. If review finds a defect: repair in the same worktree, rerun the focused test, refreeze, and obtain a fresh review.

## Integration and real operator-path proof

1. Commit only curated console source/tests/docs.
2. Reconcile with canonical via a fast-forward or conflict-aware operation that preserves recorded unrelated dirt.
3. Inspect the actual Desktop shortcut target, arguments, and working directory.
4. Launch via the shortcut—not merely a module invocation.
5. Verify a visible titled native window, normal/minimum geometry, readable appbar/navigation, explicit unavailable/stale posture, and clean close lifecycle.
6. Push only after local gates and independent review pass.

## Pitfalls

- Reviewing only a new refresh coordinator misses older detail/action threads.
- A bounded coordinator paired with an unbounded legacy queue still leaves the UI unbounded.
- Error paths require the same request identity as success paths.
- “Report-only” labels do not prove non-authority: inspect imports, CLI arguments, transports, schedulers, and mutation paths.
