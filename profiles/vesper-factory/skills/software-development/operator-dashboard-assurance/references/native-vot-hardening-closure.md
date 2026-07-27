# Native VOT hardening and closure pattern

Use this checklist when a native operator console mixes evidence telemetry, provider accounting, and local task administration.

## Reconcile review scope before accepting findings

- Record the reviewer's frozen `HEAD`/patch identity and the current worktree identity.
- Classify every finding as **still present**, **already repaired**, or **requires re-test**. A valid finding against an older commit is not proof that the current tree still has the defect; equally, passing tests against the old tree do not certify later repairs.
- Any production edit after a native-runtime probe, shortcut launch, or test run invalidates that evidence for release closure.

## Current-cycle evidence rules

- When governance Markdown repeats corrected fields, use the last canonical declaration and test duplicate-field precedence.
- A passing daily receipt is current only when its receipt date equals the latest completed market session computed with the trading calendar. Old `PASS` receipts become `stale`, not green.
- Prefer the concrete selected artifact as `sourcePath`; retain wildcard/required paths only as missing-source guidance.
- Populate `asOf` from artifact-internal dates or receipt metadata. UI sync time and file mtime are not substitutes for source date.
- A nonempty candidates CSV is inventory. Keep it waiting/unadmitted until producer identity, decision date, source session, validator result, and required review are bound.
- Unknown states and unknown provider values fail to waiting/unavailable, never success or zero.

## Compact label and provider scope

- Name authority by domain: `TRADING AUTH CLOSED` can coexist with separately bounded `KANBAN ADMIN`; a generic `AUTHORITY CLOSED` is misleading when any mutation control exists.
- Scope compact task counters (`TASK A/Q/B`) so they cannot be mistaken for process concurrency.
- Label OpenAI quota by period/scope (for example weekly) and OpenRouter credit as account-wide. If the provider snapshot is stale or unavailable, suppress typed remaining-credit numbers and preserve the stale/unavailable label.

## Bounded Kanban administration

- Do not render raw worker logs or task bodies in the operator UI. Prefer bounded run summaries, comments, and event kinds; redact common credential forms before display.
- Never attribute a local click to a named person without authentication. Use a neutral actor such as `vot-operator`.
- Restrict mutation controls to the canonical project root, validate the selected task still exists, gate each action by current status, require a reason for rejection, and require a matching second click within a short visible confirmation window.
- If a task is already blocked, rejection should append an audited rejection comment rather than issue a redundant block transition.
- Route writes through the authoritative task CLI/service so validation and history remain centralized. Exercise the real lifecycle only against a disposable board under a temporary home.

## Native refresh and state preservation

- Construct expensive since-launch trackers once per app lifetime and reuse them across snapshots; recreating Git/workspace/Codex trackers each poll resets semantics and repeats expensive scans.
- Keep one in-flight guard per source. Queue completion in `finally`, preserve the last-good payload, and schedule retry from the Tk thread.
- Measure retry delay plus real loader duration; timer interval alone is not end-to-end cadence.
- Clear selection when the task leaves the active set. Preserve card/list scroll during signature-gated redraws, preserve free-scroll/follow state, and return `"break"` from wheel handlers where class bindings would duplicate scrolling.

## Release closure

Release confidence requires all of the following against the exact final tree:

1. compile/import and Ruff;
2. focused VOT/data-lineage/action tests;
3. adjacent operator/dashboard tests;
4. full repository test suite, with exact unrelated failures disclosed;
5. CI coverage for the native modules/tests;
6. tracked icon assets and a reproducible shortcut installer;
7. actual `.lnk` launch after the last edit, with target/arguments/working directory/icon, visible process/window, no console flash, no duplicate runtime, repeated toggles, selection/scroll/follow, and callback-error capture;
8. scoped diff review, commit, and push.

If tool/time limits interrupt any closure step, report the last-green evidence and retain the verdict **not yet trustworthy** or **degraded**.
