---
name: operator-terminal-tui
description: Build, debug, verify, and improve full-screen operator dashboards running in Windows Terminal pseudoconsole environments.
---

# Operator Terminal TUI

Use this skill when a Windows terminal dashboard has redraw corruption, launcher failures, layout/readability problems, worker activity display requirements, or state/color rendering changes.

## Core workflow

1. **Inspect before editing**
   - Read the launcher, TUI entry point, layout/render module, status snapshot loader, and focused tests.
   - Identify the actual runtime interpreter used by the user-facing launcher; do not assume the shell's `python` is the same interpreter.
   - Check the current window/process and launcher log when the user reports a terminal failure.
   - Record canonical `HEAD`, branch, porcelain status, and the explicit paths owned by the slice. Recheck them after long verification runs; disappearing edits or rewritten equivalent commits indicate concurrent repository ownership.
   - When a read-only review is bound to an expected `git write-tree`, assert that exact tree as the first repository operation, bracket each substantive batch, and recheck immediately after any command/tool failure before retrying. Any drift invalidates the review; stop and report expected/observed IDs plus changed paths. See `references/read-only-diff-drift-gate.md` for the immutable staged-candidate recipe.

1a. **Isolate concurrent repository work instead of racing it**
   - If a steward or another agent repeatedly commits/resets the canonical tree, stop patching that tree and create a named temporary worktree from the newest canonical commit.
   - Do not pause or mutate scheduling merely to win the race unless scheduler authority was separately granted.
   - Run focused source-backed tests in the worktree with the canonical interpreter, but remember that ignored `.env`, `.venv`, databases, receipts, and generated artifacts are absent there. Asset-dependent full-suite failures are inconclusive until rerun in canonical.
   - An isolated-worktree review is useful early assurance, but it is not the final release verdict when rebase, cherry-pick, or three-way conflict resolution can change the tree. Reconcile onto the newest canonical history without rewriting concurrent commits or discarding unknown local edits.
   - After reconciliation, stage only the final owned paths and run the requirement audit plus added-line lint/static checks. If any rebase or conflict resolution remains, do **not** commission the release review against a moving uncommitted diff: create a local candidate commit (not yet published), rebase it onto the newest canonical commit, rerun focused verification, and freeze `HEAD`, `HEAD^`, `HEAD^{tree}`, and clean porcelain status. The final reviewer must assert those exact identities at both the start and end and review `git diff HEAD^ HEAD`. Any edit, amend, conflict resolution, or overlapping rebase invalidates the verdict and requires a new focused run, identity tuple, and review. A canonical-head advance alone does not invalidate a patch-level verdict when the intervening paths are disjoint and a clean rebase preserves the stable `git patch-id`; in that case, reassert the new commit/parent/tree, rerun focused tests, and record the unchanged patch ID. If paths overlap, the patch ID changes, or the review depended on whole-tree behavior, commission a fresh review. A staged `git write-tree` review is acceptable only when no integration step remains; verify the eventual commit tree equals that reviewed tree.
   - After the final edit, run at least one direct, standalone `pytest` invocation in the changed worktree—not only a chained shell pipeline—so verification evidence is unambiguously associated with the edited path; then run the broader focused/full gates. When an automation layer records canonical verification evidence by command name, make one invocation start with the literal `pytest` executable and prepend the intended virtualenv's Scripts/bin directory to `PATH`; this selects the right interpreter while keeping the command recognizable.
   - Before release verification, test the committed candidate with all unrelated tracked edits stashed or in a clean temporary worktree. A green suite in a mixed worktree may be borrowing unstaged production code; a stash may contain the implementation required by already-committed tests. Compare committed test and source inventories before pushing, and rerun the full suite after reconciliation.
   - Treat candidate commit, canonical integration, and remote publication as three separate states. Never say work is on GitHub because it is locally committed or because `vesper` is ahead of `origin/vesper`; verify the live remote ref (`git ls-remote` or a fetched `origin/*` ref), confirm it contains the intended commit, and explicitly report excluded untracked/unrelated paths.
   - Live terminal acceptance begins only after reconciliation and final review: canonical tests, one authoritative project-venv child, and a fresh render/screenshot.

1b. **Fail closed when a read-only review candidate drifts**
   - When asked to independently review an uncommitted diff without editing, disable all auto-fix, staging, stash, reset, formatting, and commit steps.
   - Before inspection, capture `HEAD`, porcelain status, changed-file stats, a SHA-256 of `git diff --no-ext-diff --binary HEAD`, and a separate path+content manifest hash for untracked files. Require two back-to-back fingerprints to agree before proceeding.
   - For a frozen committed candidate, also assert the exact base SHA, candidate SHA, merge-base, candidate tree, and SHA-256 of `git diff --no-ext-diff --binary <base>..<candidate>`. A clean `git diff HEAD` proves only that the worktree matches `HEAD`; the base-to-candidate digest is the reviewed patch identity.
   - Recompute the same fingerprint after source inspection, after every long test phase, and immediately before the verdict. `git diff --check` is a separate whitespace gate and does not prove candidate stability.
   - If `HEAD`, the tracked-diff hash, the untracked manifest, or the committed base-to-candidate digest changes, stop immediately. Do not silently rebaseline or continue tests against the new candidate. Return a fail-closed verdict with initial/current fingerprints and changed stats; restart only if explicitly asked to review the new stable candidate.
   - Keep verification artifacts outside the repository where possible (`PYTHONDONTWRITEBYTECODE=1`, pytest cache disabled, external `--basetemp`) so the reviewer does not create its own drift. Remember that `py_compile` can still create ignored bytecode; report verification scratch separately from tracked candidate state.
   - For pure VOT state/view models, adversarially probe exact-type grammar with hostile `__eq__`, falsey impostors, scalar subclasses, hostile `tzinfo`, state-conditioned source completeness, recursive hashability, duplicate-objective behavior, and every public consumer of the validator. Common malformed containers alone are not enough. See `references/vot-view-model-adversarial-review.md`.
   - See `references/read-only-diff-drift-gate.md` for the deterministic fingerprint and reporting recipe.

2. **Preserve pseudoconsole ownership**
   - Windows Terminal owns pseudoconsole dimensions and Prompt Toolkit owns full-screen painting.
   - Do not force `PROMPT_TOOLKIT_OUTPUT=ansi` or run `mode con` resizing inside the application; these can fight native redraw and produce scattered numeric/PID-looking fragments.
   - A launcher may size the outer native window once, but the TUI must not repeatedly force console dimensions.

3. **Separate wrapper and child failures**
   - Verify the launcher wrapper's exit code and the child TUI process independently.
   - A successful `wt.exe`/launcher result does not prove the child stayed alive.
   - If the user sees a generic `FAILED: ValueError`, reproduce with the exact launcher interpreter and capture the child traceback; test startup, snapshot refresh, app construction, and one render callback separately.
   - Do not declare success from a launcher log alone. Confirm a visible titled window, expected size, and a live child process or stable rendered frame.

4. **Design operator layouts by scan order**
   - Prefer three columns ordered left-to-right as:
     - **System health:** portfolio/account, market/data, authority, engineering.
     - **Evidence and blockers:** pipeline, blockers/receipts, continuity, timers.
     - **Autonomous work:** worker/lane status, bounded live activity, learnings.
   - Place blockers directly beneath or beside pipeline evidence so the operator can see what ran and why it is blocked without searching another column.
   - Keep the autonomous column dedicated to current work; do not mix it with engineering diagnostics and blockers.
   - At narrower widths, preserve critical state and footer shortcuts rather than forcing a clipped three-column layout.

5. **Implement live activity safely**
   - Use a bounded append-only event/log source and display only the newest small number of events.
   - Each row should identify age, state, lane, and accountable worker, e.g. `5m54s started pipeline — Clarke`.
   - Distinguish coordinator events (`cycle — Steward`) from worker events (`started/completed portfolio — Morgan`). A lane owner is not necessarily an actively working worker: render blocked prerequisite checks as gate events, not as evidence that the owner is stuck.
   - Prefer a structured append-only activity stream with bounded, redacted fields: timestamp, worker, lane, state, and short activity. Keep the legacy coordinator log only as a migration fallback.
   - Worker lifecycle states should include `delegated`, `started`, `working`, `completed`, `blocked`, `failed`, and `skipped`; do not invent completion or in-progress events when only a delegation signal exists.
   - Display operational summaries only: never expose hidden reasoning, credentials, prompts, or unfiltered tool output.
   - Treat missing activity data as a visible unavailable/stale state, not an exception that kills the TUI.
   - When a prerequisite block is unchanged, the scheduler should suppress repeated block events and must not dispatch a worker to retry it. Retry only after the gate/state changes or an authorized escalation.
   - Keep manager acceptance separate from worker self-report: a `completed` event is not proof of accepted work unless an authoritative receipt/artifact check exists; represent review or clarification as distinct states when available.

6. **Use semantic color, not decoration**
   - Apply restrained colors by meaning: green/pass, red/blocked or failed, amber/stale/waiting, blue/running, purple/delegated.
   - Give worker names stable, distinguishable accents, but preserve a readable near-black background and white/default body text.
   - Preserve existing style-token contracts when extending a renderer; add new styles without breaking tests that expect existing `class:state-*` tokens.

### Compact research HUDs: evidence over dashboard chrome

For a user watching model experiments, prefer a **boring engineering terminal** over card-heavy dashboard chrome unless they explicitly ask for a visual dashboard. Treat a request for "a normal terminal with a small neural-network chart or grid and some bars" literally: use plain aligned text, a one-line ASCII network, and small metric bars—not panels/cards, a mission-control composition, or visual flourish. Keep the default viewport compact:

```text
STATUS / script / phase / elapsed / GPU
MODEL  [input] -> [layers] -> [latent] -> [predictor]
EVIDENCE  small fixed bars with signed baseline deltas
ACTIVITY  newest 5-7 structured lines
```

- The network diagram must use actual layer widths and parameter counts calculated from the running architecture; do not reuse values from a different prototype.
- Separate architecture facts (e.g. non-collapse) from economic evidence (direction, ranking, risk). A technically validated representation must not look economically validated.
- Evidence bars must name the metric and signed direction (`IC delta`, `AUC delta`, `RMSE change`). Do not invent interpretable latent-space maps where semantic dimensions have not been established.
- Preserve a visible sandbox boundary (for example, `Vesper: CLOSED`) for research work.
- Hand-clearing a Windows terminal every refresh visibly flashes. Also avoid rendering more rows than the viewport, which scrolls/jumps even with cursor-home. Use a stable live renderer/alternate screen when needed, but keep its presentation plain-text/grid-first rather than decorative panels.
- Verify the actual batch/shortcut launch path stays alive after launch. A static import or captured output does not prove a live HUD is readable.

7. **Verify with the real project constraints**
   - Compile the changed modules.
   - When changed legacy files have baseline Ruff debt, run `python scripts/ruff_added_lines.py --cached --ruff <path-to-ruff>` from this skill directory (or invoke the linked script by absolute path) to gate only diagnostics on added staged lines. This is not a waiver for new lint and must not trigger drive-by cleanup of untouched lines.
   - Run focused layout, controller, hardening, and launcher tests in a fresh process; then run the complete suite; then rerun the focused slice independently. A complete-suite pass can mask test-order leakage, process-global state, or an implementation borrowed from unrelated worktree edits.
   - Make time/session tests hermetic at the actual admission boundary. Patching one module's `datetime` is insufficient when a calendar/session service owns a separate clock. Inject one canonical aware clock through every guard, and assert the intended rejection reason so an earlier unrelated gate cannot make a negative test pass accidentally.
   - On Windows, if the default pytest temp directory is inaccessible, use a repository-local writable `--basetemp` (or redirect `TMPDIR`/`TEMP`/`TMP`) and record that workaround; do not mistake the temp-permission failure for a product assertion failure. For a full read-only "verify everything runs" battery on a Tk VOT surface (dirty-tree check, lint/syntax/import, live SQLite/provider data validation, real Tk instantiation + refresh-drain), see the `operator-console-auditing` skill's `references/tk-operator-app-verification.md`.
   - Run the exact launcher interpreter's noninteractive status command and startup/refresh/render probes.
   - Verify the desktop shortcut/direct launcher opens a visible window at the intended size. Close temporary verification windows. Do not assume the installer’s default shortcut filename is the active one: enumerate the user Desktop and inspect the real `.lnk` target, arguments, working directory, description, and `IconLocation` before claiming the icon was replaced. Distinguish keyboard quit bindings from the Windows close button; when validating the latter, identify every child `python.exe`/`pythonw.exe` command containing the dashboard module, send a real `WM_CLOSE` to the titled window, and poll until the Vesper child PIDs disappear. If multiple Vesper tabs share one Windows Terminal host, close each tab and then the empty host, recording child counts before and after.

## Incremental worker-display iterations and baselines

When the operator asks for ongoing display improvement, make exactly one new
information-architecture or rendering idea per pass. Preserve the latest
accepted version as the comparison baseline; replace it only when the candidate
is better on code quality, data accuracy, and real execution/readability. Keep a
versioned improvement ledger in the repository with the baseline commit,
change, accuracy contract, verification evidence, and decision.

Use this sequence for each pass:

1. Inspect the current renderer, snapshot model, focused tests, branch/porcelain
   state, and any supplied visual reference. If the reference is absent, use
   the current visual contract and mark image-level acceptance as unverified
   rather than inventing a target.
2. Choose one bounded display idea. Prefer a pure renderer change when the
   existing snapshot already contains the authoritative fields; do not add
   telemetry or authority paths just to make a visual concept work.
3. Add one focused failing test first. Run it with the exact project interpreter
   exposed as the literal `pytest` command, using an external `--basetemp` and
   disabled pytest cache. Implement the smallest truthful change, then rerun the
   test and the focused layout/controller/provider slice.
4. Run a fresh pure-render probe at the supported target grids, checking row
   count, maximum line width, footer retention, and breakpoint visibility. A
   passing text test is not visual acceptance, but it catches geometry and
   clipping defects before a real relaunch/screenshot.
5. Run added-lines Ruff/static checks for legacy files instead of treating
   unrelated pre-existing lint debt as a new defect. Also run strict syntax/error
   checks and compile the changed modules. Record full-suite failures by exact
   test path; do not repair unrelated dirty-worktree failures under this slice.
6. Before release, test the committed candidate in a clean temporary worktree
   so mixed unstaged production edits cannot lend false green evidence. Verify
   the pushed remote ref and leave unrelated local edits unstaged.

Do not silently map delegated work to running, owner assignment to worker
activity, or missing data to zero. A kanban/status idea must preserve the
underlying state vocabulary and show blocker reasons when available. See
`references/incremental-display-iteration.md` for the reusable ledger and
verification recipe.

### Provider capacity, provenance, and freshness displays

When improving provider usage displays, preserve authoritative numeric fields
through the immutable snapshot instead of parsing display strings in the
renderer. Render a percentage gauge only from a source-reported percentage (for
example, an OpenAI weekly remaining percentage). If a provider exposes only a
remaining-dollar value and no total-budget denominator, render a dollar badge,
not a fabricated percentage or ratio. Missing, stale, negative, non-finite, or
malformed values must remain visibly unavailable rather than becoming zero.

Keep three contracts visible and separate:

1. **Numeric source fields:** carry provider numerics through the snapshot with
   backward-compatible defaults for older fixtures and unavailable payloads.
   Add a loader propagation assertion as well as a pure-render assertion.
2. **Provenance scope:** label workspace/session telemetry, account/key/credits
   telemetry, and local receipt attribution separately; never imply that a
   receipt total is the provider account total.
3. **Freshness:** show `READY`, `STALE`, or `UNAVAILABLE` plus the source
   observation time. Normalize timestamps only for display. Never replace a
   malformed timestamp with current time or silently turn stale last-good
   account data into fresh attribution.

Treat provenance rows, budget capacity, and feed freshness as separate bounded
iterations in the version ledger even when they occupy one provider card. Probe
the supported grids for clipping and footer retention. When a targeted patch
 touches a nested conditional or mixed-line-ending Python file, immediately
re-read the edited region and run a syntax check; fuzzy replacement can drop a
neighboring `if`/`else` branch while still looking visually plausible. See
`references/provider-budget-gauges.md` for the reusable provider display
contract.

### Multiple VOT surfaces: verify the live owner before changing provider UI

Vesper can expose provider facts through both the Prompt Toolkit operator
terminal and a separate Tk VOT worktree. Do not assume a correct canonical
terminal renderer explains what is visible on screen. Before editing:

1. Identify the titled window's process command line and its `--root`/working
tree. A live `pythonw -m app.vot_tk --root <worktree>` can render code unrelated
to canonical `app.operator_terminal`.
2. Trace the display boundary in that exact surface. For Tk appbars, keep
capacity formatting in a pure helper fed by typed snapshot numerics, then let
the refresh method set its `StringVar` from that helper.
3. Test the helper first. Assert exact visible text: valid values read
`OAI <N>% left` and `OR $<N.NN> left`; never escape `$` in a Python f-string.
Preserve unavailable fallbacks and never manufacture an OpenAI percentage from
token totals.
4. Compile touched Tk modules and run focused VOT formatter/workflow tests with
the project interpreter. Recheck `HEAD` afterward: shared worktrees may advance
or absorb edits concurrently. Report the actual commit and any uncommitted test
plainly; do not attribute an external concurrent commit to yourself.

### Native Tk VOT launch and all-page review

When asked whether a native Tk VOT is genuinely ready, verify the **actual desktop shortcut path** and every navigation page; imports and focused tests alone are insufficient.

1. Inspect the Desktop `.lnk` target, arguments, and working directory. Launch that shortcut once and identify the visible titled VOT window plus every `pythonw.exe -m app.vot_tk` process.
2. Do not call a parent launcher plus its child runtime a duplicate instance merely because they use different Python executable paths. Check PID parentage and visible window ownership first. A `.venv\\Scripts\\pythonw.exe` launcher may legitimately spawn a uv-managed interpreter child; one parent/child chain with one titled VOT window is one instance. Independent processes or multiple titled windows are the duplicate case.
3. Capture a settled screenshot of each navigation page (Workflow, System, Pipeline, Work, Research, Knowledge, Decisions, History) after a real user-equivalent navigation action. Background `PostMessage` clicks against a Tk top-level may not dispatch through its widget tree; verify the selected rail item and page heading before treating a capture as evidence.
4. On every page, look for false-green state, text clipping, blank/white repaint artifacts after settling, accidental native scrollbars, console/error dialogs, and any control that exceeds the declared authority boundary. Leave the requested surface open on its primary overview after the walkthrough.
5. Treat the appbar's global freshness/status label as an evidence claim, not merely a process-liveness indicator. If material displayed sources are `STALE`, `UNAVAILABLE`, `MISSING`, or contradictory, it must read `PARTIAL`, `STALE`, or `ERROR` as appropriate—not `LIVE`—even if the Tk process and a local Kanban read are alive. Provider/account-specific stale badges do not repair a contradictory global `LIVE` claim.

### Tk VOT polling flicker: preserve widgets when snapshot state is unchanged

For a report that VOT cards periodically flash—especially the left evidence,
readiness, or candidate rail—trace the normal polling path before blaming Tk,
the GPU, or volatile source data:

1. Inspect the desktop shortcut to identify the actual worktree and module, then
trace `refresh` → background snapshot fetch → queue drain → snapshot apply.
2. Look for renderer loops that call `destroy()` on every child before rebuilding
cards. This guarantees a transient empty frame, geometry/scrollregion recompute,
and visible flicker even when the snapshot is semantically identical.
3. Derive a stable, display-relevant signature from card identity, state, label,
detail, timestamp, and selection. Retain the prior signature and skip the render
when it is unchanged. Preserve canvas scroll position as part of the contract.
4. On selection changes, update only the prior and new selected card when
practical; otherwise permit one deliberate rebuild. Do not couple card rebuilds
to a timestamp-only refresh.
5. Add a focused regression test: two equal snapshots must perform zero child
destruction/recreation on the second apply; a state change must update the
necessary card; selection and scrollbar position must survive an unchanged poll.
6. **Keep observation time out of structural render signatures.** A
   `SourcePosture.observed_at` rebuilt at each 250 ms poll makes otherwise
   identical Workflow projections unequal, forcing `destroy()`/rebuild cycles
   that create visible blank-white card bars and make scrolling appear broken.
   Exclude timestamp-only fields from the structural signature while retaining
   every operator-visible state, reason, provenance, and card field. Test two
   equal snapshots at different poll times and require the second render to be
   a no-op.
7. If multiple canvas card hosts use `bind_all("<MouseWheel>", ...)`, each
   handler must first verify `event.widget` is a descendant of *its own* canvas
   and return `"break"` only for that owner. Otherwise an inactive page can
   swallow wheel input before the hovered canvas handles it. Test foreign-widget
   rejection and verify a real Windows wheel event moves the active page.

A signature-gated renderer may coexist with live `StringVar` counter/freshness
updates. The latter do not require replacing the card tree.

**Poll-interval floor depends on the data source, not the UI.** Direct read-only SQLite polls (e.g. VOT kanban via `app/vot_kanban_data.py`) are ~1 ms queries — with a signature-gated render, unchanged polls are free, so 250 ms is safe and feels live (shipped 2026-07-19: `KANBAN_POLL_MS = 250`). The operator's 2 s minimum applies only to polls that spawn subprocesses (snapshot refresh); do not apply that floor to in-process SQLite reads, and do not lower subprocess polls below it chasing "real-time." Below ~150 ms even SQLite polls hit Tkinter's event-loop floor for no perceptible gain.

**Tk implementation contract:** maintain independent pipeline and candidate/Kanban
signatures. Route the periodic snapshot apply, the separately queued Kanban-payload
apply, and each selection handler through the cache-aware render methods. A changed
Kanban payload must update candidate cards immediately without redrawing pipeline
cards; a pipeline selection change must not redraw candidates. For headless tests,
construct `VotTkApp` through `object.__new__`, supply minimal root/StringVar
stand-ins, monkeypatch both rail render functions into counters, and assert these
three cases directly. On Windows, run them with a repository-local `--basetemp`
when the default pytest temp directory has an ACL failure.

**Adding a new status panel to the Tk rail (proven 2026-07-19, RESEARCH section):**
keep four pieces separate and the panel can never take the app down:

1. **Pure data module** (e.g. `app/vot_research_data.py`): file reads only, no
   subprocess, no Tk import; returns a plain dict; every reader degrades to a
   "—" state when files are missing/malformed. Test it standalone with tmp-path
   fixtures — empty state, counts, malformed JSON, newest-file-wins selection.
2. **`build_x_section(rail, font_fn)` in `vot_tk_rail.py`**: mirrors the KANBAN
   section chrome (warm 1px separator, mono 8pt bold header, MUTED body rows),
   creates and returns a dict of `StringVar`s; a `render_x_status(vars, status)`
   pure function maps the data dict onto them. No polling logic in the builder.
3. **Own `after()` loop in the app**: `_refresh_x()` guards on `self._closing`,
   wraps the whole read+render in `try/except: pass` (a status panel must never
   crash the operator surface), and reschedules itself. Poll at the data-source
   floor: file-read panels at 5 s are plenty when the underlying state changes
   on batch boundaries, not milliseconds.
4. **Lifecycle hygiene**: initialize `self._x_after_id = None` in `__init__` and
   add it to the cancel tuple in `close()` — every new `after()` loop without a
   close-path entry is a post-destroy `TclError` waiting to happen.

## Approval overlays and governed action buttons

When adding approval workflows to a full-screen operator terminal, implement the complete path rather than only a ledger or command:

1. Add an immutable snapshot field for bounded approval rows; keep the renderer pure and have the snapshot loader replay the append-only approval source fail-closed.
2. Expose approvals through an explicit detail overlay, optionally paired with an always-visible governed summary card. The card is a queue/selection surface, **not a decision surface**: Enter opens exact-scope review. Keep an explicit overlay shortcut whenever responsive layouts can hide or truncate the card.
3. For embedded Issues/Approvals cards, keep independent stable selection IDs and controller-owned focus state. Use `Tab` or left/right to move focus, up/down to select, and Enter to open the corresponding detail overlay. Issue start and approval/reject/execute mutations occur only from the visible detail overlay. Hidden, vertically truncated, or compacted cards must retain no direct mutation path. Enforce this in both key dispatch and controller/domain methods so bypassing the dispatcher still fails closed. The pure renderer only reflects controller state; it never owns selection or mutates ledgers. Require the complete action, scope, reason, authority warning, status, and controls to be visible before a decision is accepted. Individual field caps are insufficient: calculate a **combined wrapped-row budget with the renderer's actual wrapping policy at the minimum supported overlay geometry**, validate it both before append and during replay, and reject before writing when it cannot fit. Validation and rendering must call the same terminal-column-aware wrapper; `len()`/code-point counts are unsafe for wide Unicode. Reject tabs, CR/LF, escape/control, and other unsupported terminal characters on the raw value **before** trimming ordinary spaces, or boundary controls disappear before inspection. If scrolling is used instead, keep decision controls locked until the complete request has been traversed. Test exact geometry, wide Unicode, embedded and boundary controls, and byte-for-byte no-write/no-change behavior.
4. Route every approval control through the existing approval service; do not duplicate validation in the renderer. Record the exact-scope decision separately from execution authority. Bind the complete serialized event—not only immutable request fields—into an append-only hash chain carrying a unique event ID and previous-event hash; validate the chain before replay or append. A request hash alone cannot detect changes to event kind, status, decision actor/time/reason, or authority flags. A valid hash-chain prefix also cannot detect deletion of the final event: persist a separate durable event-count/head-hash checkpoint, atomically replace it only after the event append is flushed, and require replay to match both checkpoint values. Test field changes, head/tail deletion, and reordering. An environment/CLI identity string is an actor label, not authentication: set `approval_granted=true` only when the project's schema explicitly defines that field as the recorded decision result and every consumer still treats authentication and execution as separate closed gates. If `approval_granted` is authority-bearing, keep it false until a trusted principal binding exists.
5. Require an explicitly configured operator identity label (for example `VESPER_VOT_IDENTITY`) before a button can write a decision attestation. Ensure the real Desktop launcher loads that allowlisted non-secret setting from the same ignored local configuration source used by the application. Missing identity must leave the UI usable but return a visible fail-closed message; presence alone must never authenticate or authorize execution.
6. Preserve two-person separation of duties, expiry, exact-scope binding, supported-handler checks, one-shot execution, and append-only receipts. Name the recorded state truthfully: when principal identity is only a local label, `approve` records a review attestation and grants no authority; operator help and controls should say `record attestation` and `check closed gate`, not `grant` or `run approved action`. Only call an approval a grant when authenticated authority actually exists; execution always remains a separately verified consumer step.
7. Add controller tests for embedded focus/selection, embedded Enter opening review without mutation, overlay-only issue start, overlay-only approve/reject/execute, direct controller-call denial without the overlay, approve→execute separation, replay rejection, missing-identity refusal, explicit review-shortcut wiring, and viewport cases where cards are hidden or truncated. Run focused TUI/VOT suites in a fresh process with an external basetemp before considering the change verified.

Do not ship an approval UI that only displays intent while claiming to provide an approval button. If the UI cannot collect or configure the required identity/reason safely, show the control and fail closed rather than inventing an actor or silently using a default authority.

## Second-opinion verification parallel to another agent's repair session

When the user asks you to verify a surface (e.g. "confirm all VOT components work") **while another agent session is mid-repair on the same tree**, your battery is a build/smoke signal, not the release verdict. The user corrected an over-strong "up-to-date and runs" bottom line here — embed this:

1. **Scope the tree first.** Run `git status --short` and name which files are modified/deleted/untracked before testing. Say explicitly "results reflect the uncommitted working tree, not the last commit." A deleted module (e.g. `app/vot_kanban.py`) means the other session is mid-refactor; check for dangling imports, but a grep hit on a similarly-named module (`vot_kanban_data`) is a false positive — read the actual import line.
2. **Read the other session's findings before issuing your verdict.** If the repair session published an audit or release gate (trust/authority defects, a "still required" list, failure counts), your summary MUST be scoped against it. Never write "up-to-date and runs" as a standalone bottom line when the owning session has an open "not yet release-verified" gate — that overstates assurance and the user will call it out.
3. **Label your run honestly:** "green build/smoke" = lint + syntax + imports + focused tests + one live data/refresh cycle. It is NOT full-repo pytest, NOT the actual `.lnk` desktop launch, NOT visual acceptance (no-console-flash, scrollbar rendering, appbar fit can't be checked headlessly).
4. **When replicating another agent's reported test counts,** reproduce their exact commands before widening the net. If widening surfaces MORE failures than they reported, report the higher count with exact failing test paths — do not anchor on their lower number.
5. **Distinguish failure origin:** a failing test adjacent to the edited slice may be introduced-by-repair (docs/governance the other session touched) or pre-existing at HEAD. Offer to classify per-test (checkout-and-diff) rather than asserting.

## Mission-control visual redesign and geometry

For a fullscreen Windows Terminal dashboard, separate native window pixels from the pseudoconsole cell grid. `--size` controls character cells; resizing the outer HWND alone leaves the TUI in a short grid and produces a large black region below the rendered frame. Set both together (for a 2500×1015 px target, approximately 312×63 cells at the current monospace metrics), then verify the real launcher exit code and rendered row count.
Use a Mission Control scan order for the default overview:

```text
status strip
    ↓
main operations canvas ── workforce rail
    ↓
health cards → primary blocker → evidence chain → provider accounting
    ↓
worker phases → next safe events → bounded recent activity
```

Do not mistake a wider three-column text composition for a redesign. If the user says the result still looks like the old panes, change the information architecture: use bordered cards, one dominant main canvas, and one dedicated workforce rail. Make cards consume their allocated width, wrap long details, and compute nested widths from the same separator-aware allocator as the outer compositor; otherwise one-cell rounding errors create visible ellipses at pane boundaries.

Keep raw detail behind overlays; the default frame should prioritize what is blocked, what is safe next, and whether a worker is actually provider-active. Preserve established semantic labels and high-value timer/task phrases in compact headers so shorter terminal geometries do not silently hide governance-critical state.

When changing the visual hierarchy, first write down the intended information architecture in terms of actual regions and scan order, then implement that structure—not merely shorter titles or different column weights. If the stated design is `status band → primary blocker → horizontal evidence spine → supporting cards + workforce rail`, the rendered regions must visibly match those parts; do not call a vertically stacked legacy pane layout a new design. Run a live pure-render probe before pytest to catch type mismatches and confirm exact viewport height/footer placement, then inspect a fresh screenshot of the relaunched real TUI. Check for dead space, unexpected nested panes, left-edge spill from wrapped rows, one-cell border clipping, and prose that should be a labeled field or compact human-readable label. A passing text renderer is not visual acceptance. Only after the user accepts the direction run the focused layout/controller/hardening suite and the telemetry/provider-receipt suite.

When a terminal must inherit an accepted native monitor palette, translate structural roles separately from semantic state colors and keep the first pass at the immutable-snapshot/pure-renderer boundary. Freeze protected truths before removing default-frame prose, give zoom levels semantic information roles, and validate the authoritative pixel and cell geometry through the real shortcut. See `references/cross-surface-command-deck.md` for the VWM-to-Prompt-Toolkit palette map, Command Deck scan order, renderer-first TDD matrix, and visual acceptance gates.

## Visual iteration lessons from operator-dashboard redesigns

- Do not call a wider three-column text composition a redesign. If the operator says it still looks like panes, change the information architecture: use a dominant main canvas, a dedicated workforce rail, and bounded cards with a clear scan order.
- Establish the visual hierarchy before adding metrics. Recommended Command Deck order: status band → primary blocker → evidence spine → account/data → authority/provider details → workforce rail → next safe action.
- Treat fullscreen whitespace as a design problem, not an invitation to print more diagnostics. Cards should consume their allocated width with borders or aligned fields; avoid left-aligned prose floating in a giant empty canvas.
- Long internal identifiers need two representations: preserve the exact ID in headers, overlays, or receipts, but render compact cards with human labels such as `Paper evidence loop · approval gates`.
- Next-safe actions should be fixed labeled fields, not paragraph-shaped prose. Prefer `TASK`, `MODE`, `GATE`, and `DETAIL` rows with bounded humanized text.
- Worker cards require fixed columns and bounded detail rows. Normalize known verbose states (for example, `WAITING_FOR_NEW_OHLCV` → `fresh OHLCV · last admitted YYYY-MM-DD`) and ensure continuation text starts under `PHASE`, never under the worker-name column.
- Nested card widths must use the same separator-aware allocation as the outer compositor. Compute available width after dividers, reproduce the allocator's remainder distribution, then probe the exact target grid for row count, footer position, maximum width, and zero unintended ellipsis markers.
- A pure renderer probe is necessary but not visual acceptance. Relaunch the real Windows TUI and obtain a fresh screenshot after each substantial layout pass; stale windows commonly make a correct code change appear absent.
- When repairing Windows-scheduled Vesper work, inspect the task action, referenced file existence, exact scheduled interpreter, historical log timeout, and child receipt before editing. A `Ready` task is not proof that the child ran. Use a bounded no-submit preview entry point for scheduled paper checks; normalize an expected blocked preview to task success only when its fail-closed receipt exists, never by weakening the receipt or submitting an order.

## Research HUDs: agent-driven runs with passive operator observation

For experimental or research sandboxes, separate **execution** from **observation**:

1. The agent starts tests through one canonical runner; the operator only watches the HUD and does not need to type test commands.
2. The runner writes a small current-state JSON plus append-only JSONL events: status, script, phase, timestamp, elapsed seconds, and concise stdout-derived activity. The HUD is read-only and can also read safe local telemetry such as GPU state.
3. Render both current run status and a durable evidence map from saved results. Clearly distinguish validated architectural mechanics from rejected downstream hypotheses; never turn a completed experiment into a generic green operational claim.
4. Test the exact desktop `.bat`/shortcut path, not only imports. Confirm its child stays alive and capture an actionable traceback/log when it does not.
5. Do not invoke `cls`/`clear` in a sub-second Windows-terminal refresh loop: it flashes and obscures transitions. Clear once, redraw in place with ANSI cursor-home or use Prompt Toolkit's native full-screen renderer, and smoke-test every redraw-path import before launch.
6. When the user asks to watch, label a run as a replication, new preregistered test, or invalid measurement. Do not silently reuse a failed holdout for tuning.

Recommended research HUD scan order:

```text
run status + GPU state
    ↓
research map: architecture → temporal dynamics → downstream evidence
    ↓
metric deltas / centered evidence bars
    ↓
bounded recent activity
```

Use `✓` only for the exact validated claim and `×` for the exact rejected hypothesis. A non-collapsed latent encoder and a failed alpha probe can coexist; show both.

## Wiring external data sources into the existing dashboard

When the user asks to consolidate multiple tools/windows into the operator terminal, do NOT build a new application. The VOT is already a full-screen Prompt Toolkit dashboard with mission-control layout, overlays, zoom levels, and key bindings. Wire data into the existing panels instead.

### Worktree venv symlink for the real launcher

The VOT launcher (`scripts/launch_operator_terminal.py`) hardcodes
`ROOT / ".venv" / "Scripts" / "python.exe"` — it expects a venv inside
the worktree root. An isolated worktree created via `git worktree add`
does NOT have its own `.venv`. Rather than duplicating or reinstalling
the venv, symlink the canonical one:

```bash
cd "D:/vesper-wt-<branch>" && cmd.exe /c "mklink /D .venv D:\\vesper\\.venv"
```

This is the only step needed to run the real desktop launcher from a
feature worktree. The venv is portable (same Python, same packages).
Verify with `ls -la .venv/Scripts/python.exe` before launching.

### Pattern: extend TerminalSnapshot + add a row function

1. Add new fields to `TerminalSnapshot` in `app/services/operator_terminal_status.py`
2. Load them in `load_terminal_snapshot()` from the relevant data source (cron artifacts, Alpaca API, OpenRouter API)
3. Add a row function (e.g., `_cron_status_rows()`) in `app/operator_terminal_layout.py`
4. Wire it into `_mission_control_body()` as a new card or extend an existing card
5. Do NOT create a separate command or a separate application — the dashboard IS the surface

### Key insight: cron data should be a panel, not a line command

The `cross-system` command was initially built as a line-oriented Rich command (`render_cross_system()` in `operator_terminal_render.py`). This works but forces the user to type a command. The better approach is to wire `CrossSystemStatus` into `_status_rows()` or add a `CRON STATUS` card to `_mission_control_body()` so it's always visible in the dashboard.

### What the existing dashboard already has vs what it needs

Already rendered: PRIMARY BLOCKER, EVIDENCE SPINE, PORTFOLIO/ACCOUNT, MARKET/DATA, STATUS/AUTHORITY, PROVIDER ACCOUNTING, WORKFORCE, KANBAN/WORKFLOW, NEXT SAFE, RECENT ACTIVITY, ISSUES, APPROVALS.

Missing (wiring needed):
- Cron job status (7 active jobs, last_status, health) → add `CRON STATUS` card
- Cross-system health (Pipeline + Research aggregated) → merge into `STATUS/AUTHORITY`
- Live Alpaca paper telemetry → extend `_portfolio_rows()` with API read (governance already approves read-only)
- Live OpenRouter/Codex token usage → extend `_provider_accounting_rows()` with API call
- Alert count + "Needs Brennan" items → extend `STATUS/AUTHORITY` or `RECENT ACTIVITY`

### Do NOT run the visual redesign plan before wiring data

A separate VOT redesign plan exists (`2026-07-17_135557-vot-command-deck-redesign.md`) for visual reskin (new palette, new card layout, screenshot acceptance). Do NOT run it before wiring data. There's no point reskinning a dashboard that doesn't yet show the data the operator needs. Data wiring first, visual polish second.

## Passive progress checks for a shared terminal session

When a user asks whether a long-running command in their visible terminal is finished, inspect it without typing, focusing, or interrupting the session:

1. Capture the specific terminal window first and report only what is visibly grounded: active command, progress indicator, and whether an interrupt affordance is present.
2. For a process-level confirmation on Windows under Git Bash/MSYS, use `ps -W -f` and search for the **full distinctive command fragment** (for example, `python scripts/train_model.py`). `tasklist` identifies processes but generally does not preserve enough command-line context to distinguish the user's run from other Python/Hermes children.
3. Do not infer completion just from a changed percentage or an idle-looking TUI. Recheck the exact command before reporting it completed.
4. If the user wants a completion notification, recheck immediately before creating a watcher. A short training run can finish in the gap; if it has already ended, report the result at once and do not leave a permanent polling cron job or stale watcher behind.
5. A completion monitor should be stateful and silent while the command is running: emit exactly one user-facing message only after it has observed the target running and subsequently absent. Remove one-off watchers after their purpose is fulfilled.

## Common pitfalls

- **MSYS bash eats backslashes in cron-launched scripts (CRITICAL)**: When Hermes cron launches a `.sh` wrapper script, MSYS bash (git-bash) interprets Windows backslash paths like `C:\Users\...` as escape sequences. This produces garbled paths like `C:UsersbgonnAppDataLocalhermesscripts...` and the script exits with code 127 (file not found). **The fix:** use thin Python wrapper scripts (`.py`) instead of `.sh` scripts. The Python wrapper does `os.chdir("D:/vesper")` then `subprocess.run([sys.executable, "D:/vesper/scripts/real_script.py"])`. No shell, no backslashes, no MSYS. This is the only reliable pattern for cron-launched scripts that need to import from a repo's `app/` package.
- **Cron wrapper needs `os.chdir` for `app` imports**: Copying a real script directly to `~/.hermes/scripts/` fails with `ModuleNotFoundError: No module named 'app'` because the script runs from the wrong working directory. The wrapper must `os.chdir` to the repo root before `subprocess.run` so the child inherits the correct cwd.
- **Verify cron jobs after wiring, not after scheduling**: A cron job that hasn't run yet has `last_status: null` — that is NOT proof it works. After creating cron jobs, trigger each one manually with `cronjob action=run` and verify `last_status: "ok"` before considering the wiring complete.
- Repeatedly reapplying edits in a canonical worktree whose `HEAD` and owned files are being replaced by another agent; detect drift, isolate once, and reconcile deliberately.
- Calling an isolated-worktree full suite red or green without accounting for absent ignored databases, artifacts, `.env`, and `.venv`; run focused tests there and canonical asset-dependent verification after reconciliation.
- Treat redraw fragments as real Vesper data or PIDs.
- **Observer HUD workflow:** when the user asks to watch agent-run tests, launch the HUD as a separate visible terminal, then have the agent start the experiment through a runner that writes structured state/events. Do not hand the user the test command or require them to drive the second terminal. Before claiming it is live, read back the state file and verify it says `RUNNING` with the expected script; a stale smoke-test `FAILED` state is not evidence that the new run failed.
- **Avoid flashing terminal HUDs:** do not call `cls`/`clear` in a sub-second refresh loop. In Windows Terminal, clear once at startup and redraw in place using ANSI cursor-home, or use Prompt Toolkit's native full-screen renderer. Verify a live frame while an actual long-running child is producing events; a static smoke test cannot demonstrate legibility.
- Testing only global `python` when the desktop launcher uses `D:/vesper/.venv/Scripts/python.exe`.
- Leaving multiple titled TUI children alive under different interpreters and then inspecting a stale window; enumerate exact command lines, retire stale copies, and relaunch one authoritative child before screenshot acceptance.
- Reading a provider management key from an ignored env file while checking its opt-in flag only in `os.environ`; configuration gates and credentials must resolve through a consistent, test-covered source path.
- Accepting a list-shaped provider payload while silently coercing malformed, negative, non-finite, or fractional count fields to zero. Validate the envelope and every aggregate field before replacing last-good evidence; cache only sanitized aggregates and expose static error types, never raw provider values.
- Feeding a stale last-good provider account total into a fresh attribution reconciliation. Preserve the stale total for display, but pass `unknown` into derived attribution, label the reconciliation stale, and never manufacture current unattributed spend from an old account aggregate.
- Showing only today's provider spend while calling the telemetry "cost totals." Render today's spend, the API-returned account total, receipt-attributed usage, and unattributed usage as distinct labels; verify those labels survive compact and wide layouts without implying that account aggregate is Vesper-attributed spend.
- Summing rollout files without deduplicating stable session IDs, or baselining a genuinely new post-launch session at its first observed total; both corrupt launch and cumulative token accounting.
- Coupling provider-account telemetry to Steward/worker state so missing autonomous evidence hides real spend.
- Calling a job or wrapper successful without verifying the child TUI.
- Putting blockers at the bottom of a long middle column where they are clipped from the normal viewport.
- Calling a steward log a fully live worker feed when it only contains coordinator/delegation events; label the feed accurately and add worker instrumentation when true in-progress visibility is required.
- Replacing existing style class names during a color refactor and causing compatibility-test failures.
- Emitting a Prompt Toolkit fragment style like `class:dashboard activity-meta` makes `activity-meta` parse as a color and raises `ValueError: Wrong color format`; every class after the first must retain its `class:` prefix, e.g. `class:dashboard class:activity-meta`.

## Supporting reference

See `references/concurrent-repo-reconciliation.md` for detecting canonical-head drift, isolating tracked work without copying secrets, distinguishing worktree environment failures, and safely reconciling a verified UI commit.
See `references/prompt-toolkit-color-classes.md` for the Prompt Toolkit class-prefix pitfall and a safe semantic-color extension pattern.
See `references/windows-tui-debugging.md` for durable Windows pseudoconsole, launcher, test, and verification patterns.
See `references/scheduler-recovery-and-preview.md` for logout-safe Windows task deployment, immutable-runtime ACLs, password-backed registration, non-secret diagnostics, and receipt-backed cutover.
See `references/worker-activity-and-no-retry.md` for structured lifecycle events, unchanged blocked-gate suppression, and the worker-versus-manager review boundary.
See `references/approval-overlays-and-telemetry.md` for immutable approval snapshots, embedded governed queue focus/selection, source-backed issue progress, Codex session accounting, OpenRouter last-good telemetry, and the focused verification matrix.
See `references/provider-receipts-and-worker-phases.md` for provider-request evidence, worker-phase derivation, spend reconciliation, and fresh-verification requirements.
See `references/provider-accounting-display-iterations.md` for the typed-field truth contract, compact provider-budget/token patterns, CRLF patch recovery, and the per-pass verification recipe.
See `references/fresh-verification-and-clock-hermeticity.md` for the focused→full→focused release gate, canonical clock injection, and detecting negative tests that pass at the wrong fail-closed gate.
See `references/mission-control-card-layout.md` for the fullscreen card composition, separator-aware width math, and visual-acceptance workflow.
See `references/baseline-classification.md` for classifying pre-existing vs. newly-introduced test failures (stash → test at baseline → restore → per-test verdict), distinguishing a broken test from broken behavior (live-state vs. brittle-string vs. real regression), and the Windows cross-mount pytest false positive.
