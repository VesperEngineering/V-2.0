---
name: desktop-application-release
description: "Release native desktop applications safely: bounded async lifecycle, fail-closed evidence UI, independent review, canonical integration, and launcher proof."
version: 1.2.11
---

# Desktop Application Release Assurance

## Use when

Use for a native desktop/Tkinter application that reads background evidence, supervises a local sidecar, has a real operator launcher, or must be released from an isolated worktree into a dirty/shared canonical repository.

## Core rule

A passing unit test and a direct interpreter launch are not sufficient. Release requires an end-to-end proof of the real operator path plus an independent lifecycle review.

For Rust/Tauri sidecars and authoritative Mission Control UIs, also read [references/tauri-sidecar-mission-control.md](references/tauri-sidecar-mission-control.md).

For exact staged-candidate review in a dirty Windows worktree, also read [references/candidate-bound-windows-review.md](references/candidate-bound-windows-review.md).

## Native development-smoke identity rule

Treat every desktop PID, sidecar PID, window handle, and tray state as generation-scoped evidence. A native development watcher may rebuild and replace the desktop after a Rust edit while the frontend server stays alive. Re-inventory the native process, its exact sidecar child, the dev-server owner, and the visible window before attributing any later click or screenshot. Do not interpret a sidecar that remains after **Stop Factory** as an orphan when the contract reserves sidecar termination for explicit **Quit**; verify cleanup only after the completed quit sequence.

## Live-authority probe rule

Do not instantiate a second application kernel as a “read-only” verifier while the real desktop sidecar is running. Kernel construction can run migrations, startup reconciliation, lease recovery, or fail-closed mode transitions and thereby mutate the live fixture without an event the existing UI has observed. Verify through the running sidecar's authenticated snapshot/events API, or use a truly read-only storage connection that cannot execute application startup hooks. After every accessibility-driven command or keyboard sequence, prove the authoritative post-state; successful focus, invoke, or key-delivery calls are not acceptance evidence by themselves.

## Execution-budget rule

For a large desktop milestone, divide work into independently GREEN slices before editing. Do not open a new RED slice unless there is enough execution budget to implement it, run focused verification, and leave it GREEN. After each slice, record its exact files, focused test result, and next contract. Batch independent inspections and test commands. If the available execution window becomes tight, stabilize and verify the current slice instead of creating additional unimplemented tests or half-wired surfaces.

## Release flow

1. **Freeze scope first**
   - Capture worktree branch, HEAD, staged and unstaged paths.
   - Capture canonical branch/status separately.
   - Stage only the application-owned source, tests, and intentional docs; never absorb unrelated canonical dirt.

2. **Inventory every asynchronous path**
   - List all thread/task producers, timers, queues, result handlers, selection-triggered readers, action results, and close callbacks.
   - Include legacy/background detail readers, not only newly added coordination code.
   - Every worker result must either be handled or have an explicit drop transition that clears dependent in-flight state and safely schedules retry.

3. **Bound the lifecycle**
   - Enforce one in-flight operation per logical source.
   - Keep native lifecycle authority separate from the frontend command whitelist. Native pause/resume/stop/quit must use authoritative versions, fresh idempotency keys, bounded sequencing, and explicit quit state.
   - Close-to-tray must prevent ordinary close and exit requests; only the completed explicit-quit path may release the sidecar and allow process exit.
   - Bound/coalesce pending results and bound every main-thread drain, including compatibility queues.
   - Do not evict terminal results whose handler clears UI in-flight flags unless the eviction performs the equivalent state transition.
   - Selection-driven fetches must serialize the active read, retain only the latest requested selection, launch it after the active terminal result is handled, and ignore late success *and error* results for an obsolete selection.
   - Close must cancel timers, invalidate/close coordinators, reject late completion, and prevent queued follow-up work.

4. **Make evidence failures visibly fail closed**
   - Retain last-good display values only under a global, explicit `STALE`/`ERROR`/`UNAVAILABLE` overlay with bounded reason/provenance.
   - Never leave capacity, count, posture, or “LIVE” appearance current-looking after a source failure.
   - Static `LIVE` is a posture label, never a changing sync timestamp used as freshness proof.

5. **Test with TDD**
   - Add a red regression test before each lifecycle repair.
   - Minimum cases: background failure overlay; close before worker completion; bounded/coalesced queue behavior; queue saturation; `A → B → C` selection coalescing; stale A success/error after C selection; persistence of selected page/task and scroll/follow state.
   - On Windows, isolate pytest temp state using `--basetemp=<worktree-local-temp>` if the shared pytest temp root is unavailable or locked.

6. **Run release gates**
   - Focused tests, full application suite, compile, lint, and `git diff --cached --check`.
   - Treat test infrastructure failures distinctly from assertion failures; retry in an isolated test temp directory before classifying a code regression.
   - Freeze the exact staged candidate with a staged-tree identity and staged-diff digest before review. The reviewer must verify those identities from the repository rather than echoing prompt values.
   - Distinguish a reviewer setup HOLD (the reviewer could not read Git/files) from a candidate HOLD (the reviewer inspected the candidate and found defects). A setup HOLD never counts as review evidence; repair the review environment and retry without changing the candidate.
   - Obtain an independent reviewer after each repair. A reviewer must inspect actual staged code and all async paths, not only the reported defect.
   - Any post-freeze edit invalidates the candidate identity and prior verdict. Re-stage only the bounded allowlist, require no unstaged application-owned repair paths, rerun affected/full gates, recompute tree/diff identities, and obtain a fresh candidate-bound review before commit.

7. **Prove the real launcher**
   - Inspect the actual desktop shortcut target, arguments, and working directory.
   - Reconcile the reviewed candidate to canonical without overwriting unrelated dirt.
   - Launch through the shortcut, not just `python -m`.
   - Verify a visible titled window, normal and minimum geometry, readable appbar/navigation, explicit unavailable/stale behavior, and clean close lifecycle.

8. **Publish carefully**
   - Commit only the reviewed application slice.
   - Push only after canonical HEAD, remote HEAD, and intended commits are verified.
   - Report pre-existing unrelated canonical dirt explicitly; do not claim it was cleaned or included.

## Authority boundary checklist

For an operator desk, a UI refresh/release change must not silently add broker/order, provider spend, scheduler, risk, promotion, deployment, secret, or worker-dispatch authority. Mutation controls, if allowed at all, must remain exactly scoped, explicit, confirmed, and independently guarded.

## Pitfalls

- Reviewing only the new coordinator while an older detail-reader thread bypasses it.
- Draining a legacy queue unboundedly after a bounded coordinator drain.
- Coalescing a same-item selection but losing the latest distinct selection.
- Applying an error from a stale selection to the currently selected item.
- Treating configured keyboard sensors as operational while a later `onKeyDown` prop replaces their activator listener.
- Releasing a distance-constrained pointer drag on its activation move; send a post-activation move and prove the intended collision target first.
- Storing notification state as either the latest pair or one pair of global severity/count maxima; correct deduplication needs successful delivered count per severity (or an equivalent frontier), plus separate in-flight state that never masquerades as delivery. Ref cleanup alone does not retry a failed React effect with stable dependencies; require an explicit finite, rate-bounded retry and a stable-identity timer regression.
- Treating `last_event_sequence` as the returned page tail without inspecting the transport contract. If it is a journal-global tail while events are limit-bounded, a non-empty consecutive prefix is valid pagination and must advance the cursor; resynchronize on internal gaps, regression, or an impossible empty page claiming unseen progress. Require exact tail accounting only when the protocol explicitly defines a page-local tail.
- Restoring the physical cursor immediately after a coordinate-backed tray right-click when the native menu anchors asynchronously; use one bounded dwell and verify the visible menu before selecting an item.
- Treating `PYTHONPATH=<venv>/Lib/site-packages` as equivalent to venv startup; `.pth` bootstraps and auxiliary native-package paths are not processed automatically.
- Treating “window exists” as proof that the Desktop shortcut launches the integrated canonical build.
- Fast-forwarding a worktree branch without first proving canonical dirty files do not overlap the release slice.
