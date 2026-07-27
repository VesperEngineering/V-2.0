---
name: operator-terminal-debugging
description: "Debug and evolve a Windows Prompt Toolkit/Vesper operator terminal safely: reproduce launcher failures, capture redacted runtime tracebacks, preserve fail-closed state, implement readable layout/color/activity changes, and verify with the exact desktop interpreter and launcher."
---

# Operator Terminal Debugging

Use for Windows terminal-TUI failures, dashboard layout changes, Prompt Toolkit styling, activity feeds, launcher regressions, and opaque `FAILED: ValueError` exits.

**Note:** If the user wants the VOT rebuilt as a Tkinter desktop app (mirroring VWM), this skill covers the *old* Prompt Toolkit terminal. For the Tkinter rebuild, use the `desktop-gui` skill's "Rebuilding a Prompt Toolkit terminal app as a Tkinter desktop app" section and the `vwm-design-contract` skill. Signal: "mirror the design", "tinker/Tkinter loader", "not in the terminal".

## Operating principles

- Treat a generic TUI error as a real regression; do not infer success from a passing pure-render test alone.
- Reproduce through the user-facing desktop launcher and the interpreter it actually uses, not only the global `python`.
- Keep the TUI fail-closed: refresh failures retain the last good snapshot, never expose credentials, and never turn diagnostics into a second crash.
- Prefer one clear operational recommendation and concise evidence. Distinguish coordinator/Steward activity from worker activity.
- For visual work, preserve scan order: system/engineering health left, workflow blockers/evidence middle, live autonomous activity right.

## Reproduction and evidence

1. Read the launcher and identify its Python executable, working directory, Windows Terminal arguments, and title/window-size behavior.
2. Run the exact interpreter used by the launcher for compilation, batch status, controller refresh, and application construction.
3. Do not treat direct `python -m ...` from the Hermes shell as a full TUI test: without a pseudoconsole it can produce `NoConsoleScreenBufferError` even when Windows Terminal works.
4. When the UI only says `FAILED: <Type>`, add or use a redacted append-only error log under `.hermes/` and capture phase plus traceback. Never put raw exception text into the visible snapshot if it may contain secrets.
5. Verify a fresh launcher instance by checking the titled window exists and has the intended physical size.
6. For a PID question, classify the target before searching: dedicated display/TUI process, browser host for a static `file://` visual, live web server, worker runtime, or supervisor parent. Report exact command line, cwd, and parent/child identity. “No dedicated display PID” and “no workers running” are different claims.
7. For a token/usage question, state the telemetry boundary before quoting a number. A local provider receipt ledger proves only receipt-attributed worker activity; a Codex session scanner proves only discovered local sessions (often workspace-scoped); a provider management API proves account activity. Never convert an empty local ledger into an account-wide provider zero. Preserve provider name, scope, observed time, stale state, and cached-token semantics in the visible result.

See `references/runtime-identity-and-usage-scope.md` for the compact process and usage-authority probe.

## Prompt Toolkit styling

- In `Style.from_dict`, define semantic classes such as `activity-meta`, `activity-running`, and `worker-morgan` with valid color values.
- In `FormattedText` fragments, reference classes as `class:dashboard class:activity-meta`; `class:dashboard activity-meta` is parsed as a color and raises `ValueError: Wrong color format`.
- Preserve legacy state-style contracts if tests expect `class:state-pass` etc.; add new classes without changing the old fragment shape.
- Test actual `build_dashboard_application(...)` construction, not just plain text rendering, because style parsing occurs only during application construction.

## Safe live activity feed

- Use a bounded stream (latest 6–10 entries) with timestamp, state, lane, and accountable worker.
- Keep raw model reasoning, credentials, prompts, and unfiltered tool output out of the feed.
- Show `Steward` for coordinator cycle markers; show the lane owner for delegated/started/completed worker events.
- If no event source is available, render an explicit unavailable/empty state rather than inventing activity.
- Render activity as a fixed three-column table, not free-form prose:
  `TIME` right-aligned, `ACTIVITY` fixed-width/truncated, `WORKER` left-aligned at one stable x-position. Never allow activity rows or worker names to wrap.
- Format elapsed time with a fixed width (for example ` 2m35s`) so updates do not shift neighboring columns. Keep the header static.
- Use restrained semantic color: slate-gray for ordinary text, brighter colors only for pass/fail/waiting/running/delegated states and worker attribution.
- Narrative learnings may wrap responsively to the actual Autonomous column width; indent continuation lines and preserve the fixed activity table above them.

## Worker activity truth and no-retry control

- Treat lane ownership as accountability, not proof that a worker is currently working. Render blocked prerequisite checks as `WAITING`/`BLOCKED GATE — <owner>` rather than implying the owner is retrying the task.
- Keep a structured append-only activity stream with `worker`, `lane`, `state`, `activity`, and timestamp. Prefer it over legacy coordinator logs; retain a compatibility fallback during migration.
- Emit worker lifecycle states only around real dispatches: `started`, concrete `working`, `completed`, `needs_review`, `blocked`, and `failed`. Never invent progress from a delegation signal.
- Enforce no-retry for unchanged blocked signatures. Local prerequisite checks may run, but do not spend model tokens dispatching a worker until the underlying state changes or an explicit escalation authorizes it. Record `no_work` and idle when no actionable lane exists.
- A `completed` event is not accepted without an in-repository artifact or receipt plus explicit passing verification. Missing, unreadable, or non-passing evidence becomes `needs_review`; do not auto-retry unverified work.
- For recurring pipelines, distinguish `already scored`/`already recorded` from stale data. A repeated output for the same input date is an intentional wait condition, not a worker defect. Label the wait reason and wait for a changed upstream input.

## Read-only authority and static audits

When the request is an audit rather than a repair, verify the terminal's claimed posture end to end instead of trusting labels such as `READ ONLY` or `AUTHORITY CLOSED`:

1. Freeze branch, HEAD, full dirty status, and a scoped diff for every audited path before running checks. Repeat the scoped diff after each major gate batch. If a target changes concurrently, never revert it: partition results into the HEAD-equivalent audit and the post-drift candidate, rerun non-mutating gates on the candidate, and cite revision-qualified locations such as `path@HEAD:line` versus current `path:line`.
2. Trace every button, key binding, callback, and secondary data-layer helper to its terminal side effect. Search specifically for subprocess/CLI writes, database writes, file appends, scheduler calls, hard-coded boards/scopes/principals, status-independent actions, ignored return values, and mutation performed on the Tk/UI thread.
3. Compare the *complete set of reachable side-effect classes* with the flags used to compute the visible authority state. A closed broker/order flag set does not prove the UI is read-only if task, approval, scheduler, provider, or filesystem mutation remains reachable.
4. Treat an authenticated/fail-closed approval service as irrelevant to a GUI action unless the callback actually consumes it. Tests of the safe service do not protect a parallel callback that invokes a lower-level mutator directly.
5. Probe log disclosure with synthetic sentinel markers through the real loader. ANSI stripping, tail bounding, and truncation are not redaction; prompts, tool output, tokens, and credential-like values must be filtered before display.
6. Probe missing or malformed data sources. `[]`/`{}` converted into `No active tasks`, zero counters, or an idle roster is false-green evidence; render an explicit unavailable/error state and retain the last good snapshot.
7. Inventory test importers, not just test filenames. Require direct regressions for every mutation callback, denied authority path, identity/scope binding, CLI failure, source failure, and redaction path.
8. Keep `py_compile`, imports, Ruff, and pytest scratch outside the repository (`PYTHONPYCACHEPREFIX`, `-p no:cacheprovider`, external `--basetemp`) and remove only scratch created by the audit.

See `references/read-only-terminal-authority-audit.md` for safe no-side-effect probes, caller/test inventory recipes, concurrent-drift handling, and report structure.

## Verification gates

Run using the launcher’s interpreter, with pytest and bytecode scratch directed outside the repository from the Hermes/Git-Bash shell:

```bash
export PYTHONPYCACHEPREFIX="${TEMP:-/tmp}/vesper-tui-pycache"
D:/vesper/.venv/Scripts/python.exe -m py_compile app/operator_terminal.py app/operator_terminal_layout.py
D:/vesper/.venv/Scripts/python.exe -m pytest \
  tests/test_operator_terminal_layout.py \
  tests/test_operator_terminal_controller.py \
  tests/test_operator_terminal_hardening.py \
  -q --tb=short -p no:cacheprovider \
  --basetemp="${TEMP:-/tmp}/vesper-pytest-tui-verify"
```

Then perform all of:

- forced refresh-failure probe: last good snapshot retained; visible message contains only exception type;
- redaction probe: error log contains `[REDACTED]`, not credential values;
- actual `build_dashboard_application` construction with `DummyOutput`;
- desktop launcher test; confirm titled window and expected dimensions;
- inspect `.hermes/operator_terminal_error.log` after any failure.

Do not report “fixed” until the current file state has fresh passing tests and the exact launcher path has been exercised.

## References

## Windows scheduled pipeline reliability

When the operator terminal depends on a Windows scheduled ingest/factor chain, verify the Task Scheduler boundary separately from TUI behavior. Pin the scheduled wrapper to the project interpreter, invoke the batch file through explicit `cmd.exe`, guarantee append-only logging, and diagnose the first failing stage before touching approval or readiness gates. A configured task is not evidence that it fired; require a native wrapper run, `COMPLETED OK`, fresh artifacts, and receipts. See `references/windows-scheduled-pipeline.md` for the reusable investigation and repair pattern.

### Active-source evidence versus documentation reconciliation

For VOT daily paper evidence, do not make current local active-source freshness contingent on every board/status-document date being synchronized. Parse board dates for reconciliation and reject malformed values, but gate source freshness on configured local OHLCV/cache values meeting or exceeding the expected completed session. Preserve the receipt's preflight status, result class, and actionability-decision checks. After a repair, run the exact **no-submit** loop plus its cron wrapper and watchdog; a separately fail-closed pretrade receipt remains a correct `EVIDENCE BLOCKED` result, not a reason to fabricate remediation evidence. See `references/vesper-active-source-evidence-gating.md`.

See `references/windows-tui-debugging.md` for the durable failure modes, commands, and evidence checklist from the Vesper operator-terminal debugging session. See `references/worker-review-and-no-retry.md` for the structured worker-event, completion-review, and unchanged-block pattern. For read-only review of a fixed or rebased terminal commit—including pre/post Git drift assertions, fail-closed pure view-model probes, completion/timestamp/objective/immutability checks, authority-model binding, master-document truth, approval-ledger tampering, exact viewport matrices, and tool-budget discipline—use `references/immutable-terminal-commit-review.md`.
