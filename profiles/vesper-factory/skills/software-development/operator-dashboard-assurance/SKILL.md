---
name: operator-dashboard-assurance
description: Audit and repair the trust plumbing behind operational dashboards before changing presentation or layout.
version: 1.9.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [dashboard, observability, data-lineage, scheduler, deployment, qa]
    related_skills: [dogfood, systematic-debugging, test-driven-development]
---

# Operator Dashboard Assurance

## Trigger

Use for dashboards that supervise autonomous systems, trading systems, scheduled pipelines, broker accounts, infrastructure, or other operations where stale or mislabeled data can create false confidence.

Use this skill when the user asks whether a dashboard is accurate, refreshing correctly, hiding background failures, or providing enough information to supervise automation.

## Core principle

**Plumbing before presentation.** If the user likes the layout, preserve it while validating and repairing source authority, freshness, health derivation, scheduler truth, and deployment consistency. Do not mix a visual redesign into a data-truth repair.

## Workflow

1. Identify the live process, command line, working directory, static root, API root, and launcher serving the inspected URL.
2. Enumerate **every runtime authority path**, not just the web server: login/startup launchers, tray/service wrappers, scheduled tasks, refresh scripts, generated-payload destinations, and any shadow writes. A repository can be authoritative in source control while a stale copy remains authoritative at runtime.
3. Prove exclusive listener ownership, not merely successful reachability. On Windows, combine `netstat -ano` with per-PID command line, working directory, and socket inspection (for example via `psutil.Process(pid).cmdline()`, `.cwd()`, and `.net_connections(kind="tcp")`). Two unrelated processes can appear to own the same loopback port; repeated successful identity responses from the intended server do not eliminate the competing-runtime risk.
4. Compare the live deployment with repository source. Treat shadow copies and duplicate frontends as P0 risks. Disable or redirect competing launchers; do not merely copy patched files into both trees.
5. Discover the actual scheduler authority from launch configuration and task state before deriving health. Do not assume an in-repository scheduler is production authority merely because its code or logs exist.
6. Trace each displayed value through source → transformation → payload → frontend, including fallbacks.
7. Distinguish raw candidates, approved execution artifacts, and actual holdings/state. Require artifact-internal provenance (for example source-session metadata), not only a plausible filename and row count.
8. Challenge reassurance labels such as `HEALTHY`, `Connected`, and `live`; require derived evidence and fail-closed behavior.
9. Separate browser-fetch age, payload age, artifact age, feed age, broker observation age, and persisted-snapshot age.
10. Identify the authoritative scheduler; verify expected versus actual runs, last result, missed runs, duration, retries, dependencies, and outputs. A failed prerequisite should remain visible even if downstream artifacts still exist.
11. Validate timezone and schedule semantics with deterministic tests, including DST and scheduler-specific weekday numbering.
12. Write focused failing regression tests before production fixes. Isolate browser formatting/cadence logic into a small pure module that can be exercised with Node when no browser unit-test harness exists.
13. Verify at three layers: unit tests, concurrent real API/HTTP output, and browser-visible state. Confirm the browser loaded the intended cache-busted bundle and inspect runtime timer/source state, not just the HTML response.
14. Only after plumbing is verified should visual/layout changes be considered.
15. If the worktree is broadly dirty, recover validation authority before repair: preserve staged/unstaged patches, restore only tracked deletions, verify workflow-required test paths exist, and distinguish a reduced surviving suite from the established baseline.
16. Time-box recovery. Once the trust gate is restored, continue with the system's highest-value bounded engineering or research lane rather than treating cleanup as the end product.

## Required trust contracts

- Every major value exposes or carries source and observation time.
- Dashboard health is derived, never hardcoded.
- Missing required evidence cannot resolve to green.
- The displayed execution artifact is the same artifact consumed by execution.
- Live and snapshot data are explicitly distinguished.
- The inspected URL is served from the exact code version tested.
- Scheduler liveness and job success are separate concepts.
- A successful HTTP response proves reachability only, not system health.

## Browser refresh and source arbitration

- Track payload polling, backend aggregation, and external live-data polling as separate timers. Clear **all** timer handles before restart; guard each request against overlap.
- Recompute cadence at session-boundary transitions, after tab visibility changes, and after sleep/resume. An initialization-only `isOpen` decision becomes stale.
- Never let a frequent persisted-snapshot render overwrite a newer live observation. Keep a recent-live watermark or explicit source priority, and label the visible value with source plus observation time.
- Do not let a live holdings response replace the approved target-basket table. Target, actual, and drift are separate widgets even if they contain the same ticker fields.
- Dynamic contribution tables should render the factors actually present in the payload. Fixed legacy columns full of zeroes are misinformation; label raw/research rankings explicitly when they have not passed universe, tradability, portfolio, and risk gates.

## Security and action-authority boundary

- Treat bind address, CORS, authentication, HTTP method, and exposed actions as part of dashboard correctness. A truthful dashboard is still unsafe if it listens on every interface, permits wildcard origins, or exposes account/order controls without an explicit authority design.
- Default operator-only dashboards to loopback. If remote access is required, require an intentional authentication, origin/CSRF, and network-exposure design rather than relying on obscurity.
- Never expose broker/order actions merely because the backend already has a callable function. Remove or disable the route and its GUI handler; return an explicit denial. Keep bounded local refresh/report actions separate from execution actions.
- API health must independently enforce payload age. An embedded historical `HEALTHY` value cannot remain healthy after aggregation stops; stale payload age overrides the embedded state and adds a reason.

## Governed TUI replay and immutable review

- Treat identities loaded from `.env`, process configuration, CLI flags, or preferences as unauthenticated attribution labels unless a separate mechanism proves identity. They may record an approve/reject attestation, but they must not set `approval_granted` or `execution_authorized` true.
- During append-only replay, derive sensitive authority rather than trusting serialized booleans. When authenticated authority is unavailable, require both flags to be exactly false, reject missing/non-boolean/true claims as malformed evidence, and construct the projection with literal false values.
- A two-stage governed action needs a real render boundary: the first key opens and normalizes the exact review overlay, explicitly invalidates/redraws the application, and performs zero mutation; only a later key while that visible overlay is active may mutate. Test invalidation count as well as state ordering.
- Review-size admission and rendering must call one shared terminal-column-aware wrapper. Do not validate with `len()` or one `textwrap` policy and render with another. Reject tabs/control characters before hashing or writing, exercise wide Unicode with `wcwidth`/Prompt Toolkit column widths, and prove the simultaneous maximum accepted fields plus warning/status/action footer fit the minimum supported viewport. If complete review cannot fit, mutation controls remain unavailable.
- A request hash does not bind decision metadata, and an event hash chain alone cannot detect deletion of a valid suffix. Hash complete events, link each previous hash, and persist a separately verified event-count/head-hash checkpoint after the event append is flushed. Replay must reject missing/stale/mismatched checkpoints, field changes, head or tail deletion, and reordering. State clearly that a local checkpoint is truncation evidence, not authenticated identity or protection against coordinated deletion of both files.
- Treat help text, shortcut footers, and protocol copy as part of the authority boundary. When decisions are unauthenticated attestations and execution is closed, every operator-visible surface must say “record attestation” and “check closed gate,” never “grant” or “run approved action”; add a repository-wide wording scan and focused help regression.
- Provider numeric validation must catch `OverflowError` as well as malformed strings, booleans, negatives, fractions in count fields, and non-finite values. A malformed live response must preserve the exact last-good cache as stale and must not overwrite it.
- Freeze independent reviews with exact HEAD, parent, tree, clean status, and stable patch ID. If canonical advances, do not alter the reviewed tree mid-review. Finish the behavioral review, rebase afterward, require the patch ID to remain stable for unrelated base movement, rerun verification, and attest the exact final rebased tree before merge or push.

See `references/governed-tui-authority-replay.md` for minimum-viewport/Unicode review fixtures, complete-event and truncation probes, redraw tests, huge-number provider probes, and moving-canonical closure.

### Pure operator view-model boundary hardening

Before wiring an operator view model into production pages, adversarially verify the pure derivation boundary rather than trusting dataclass annotations or happy-path tests:

- Require verified, noncontradictory evidence for `COMPLETE` and action receipts; keep unsafe closed roots visible.
- Group duplicate identities before resolution so last-write-wins cannot hide contradictions or fabricate a current objective.
- Bind `HUMAN GATE` to exact built-in, nonempty, unpadded task/action/scope/principal/request evidence, fresh source posture, future expiry, and literal Boolean-false authority. Malformed evidence must return `BLOCKED`, never raise.
- For frozen/cacheable page models, validate recursive exact built-in immutability and hash the complete object contract; hostile subclasses and malformed source metadata must be rejected.
- Make timestamp parsing total over huge, non-finite, type-confused, and hostile-subclass inputs.
- Freeze each candidate SHA for independent adversarial review. Every failed review keeps integration blocked, adds RED regressions, and is recorded as a rejection/remediation—not rewritten as success.
- Keep engineering documents descriptive: label unwired behavior as a target contract and never create governance authority by documentation assertion.

See `references/pure-view-model-fail-closed-review.md` for the exact boundary rules, adversarial fixture matrix, and immutable review loop.

## Shared execution contracts

Do not approximate an execution loader in dashboard code. Reuse the same parser/validator, or extract a shared pure contract, so exact date selection, trading-calendar rules, heading/provenance, age/future skew, cardinality, uniqueness, and ticker syntax cannot drift. If a shared loader needs an alternate artifact root for tests, resolve the default path at **call time** (`None` then current constant), not as a default argument bound at function definition; otherwise monkeypatching the runtime authority will silently fail.

## Scheduler correctness gates

- A successful last result is insufficient: also require a recent successful run. Use schedule-aware or task-specific staleness bounds that tolerate weekends/holidays but detect stopped automation.
- For cron jobs, reserve the exact matched `(year, month, day, hour, minute)` before execution. A short elapsed-time debounce can admit a second run in the same matching minute.
- Use an IANA timezone such as `ZoneInfo("America/New_York")` or browser `Intl.DateTimeFormat` with an explicit zone. Never encode permanent EDT/EST offsets or hand-maintain DST transition calculations.
- Live endpoint fields and frontend rendering contracts must match. A live refresh must not blank snapshot-derived P/L fields; either provide live equivalents or retain and explicitly label snapshot values.

## Blocked-state acknowledgment versus override

When an operator asks to “override blocked,” do not translate that into forced `HEALTHY` or bypassed execution admission. First separate three concepts:

1. **Acknowledge:** record who/when/why, suppress repetitive alerting for a bounded period, and render `BLOCKED — ACKNOWLEDGED`; all underlying blockers and execution gates remain active.
2. **Temporary observation mode:** permit read-only dashboard use while blocked, with an expiry and visible banner; no broker/order, promotion, scheduler, target/risk, or artifact-admission authority is granted.
3. **True override:** changes an execution or safety gate and therefore requires the project’s explicit approval lane, scope, expiry, audit receipt, and rollback path. Never infer this authority from a casual request to clear a dashboard warning.

Prefer acknowledgment when the user wants relief from alert noise. Never rewrite source evidence, task results, artifact timestamps, or health inputs to manufacture green. An acknowledgment must automatically clear when the blocker changes or the bounded expiry passes, and the unacknowledged status must remain available through the API and audit log.

## Scheduler mutation safety

When changing scheduled-task commands or wrappers, read back the task action, enabled state, next run, account/logon mode, and last result. On systems that require stored credentials or a specific unattended logon type, a successful task-definition update does **not** prove the next unattended run will execute. Preserve the old failure result until a new successful receipt exists.

## Testing discipline

Follow strict RED → GREEN cycles for provenance, health, freshness, schedule semantics, and API contracts. Do not claim completion after unit tests alone. Deployment and browser verification are mandatory for an end-to-end trust claim.

When parallel reviewers run pytest, give each process a unique `--basetemp` outside shared canonical artifacts. If a full run reports that its pytest base directory disappeared, rerun the affected test alone and inspect concurrent test processes before classifying it as an application defect; shared temporary-directory deletion can create a false failure.

Treat independent review as a new verification boundary, not a reporting appendix. Fix high-confidence findings, then rerun the affected tests and full suite. Any production patch after the last server start or browser check invalidates that runtime evidence: restart the deployed process, verify bind address and denied/allowed routes, regenerate the payload, and repeat browser/API checks before upgrading the verdict to trustworthy. If tool or time limits interrupt this closure loop, report the exact last-green test set and explicitly keep the verdict at not yet trustworthy.

## Read-only uncommitted-diff assurance

When the user requests an independent review and forbids edits, switch from repair mode to evidence-preserving audit mode. Inspect staged, unstaged, and untracked scope explicitly; hash the staged candidate with one canonical command; and repeat that exact command immediately before tests, after tests, and before reporting. On Windows/Git Bash, standardize the packet on `git diff --cached | sha256sum | cut -d' ' -f1` and record that output verbatim. The author handoff, prompt, and reviewer must use this exact pipeline; do not accept a hash from a differently rendered or copied diff as equivalent. If the contract says fail closed on movement, one observed staged-hash change is terminal for that review—do not silently re-freeze and treat later passing tests as release evidence. Read porcelain XY status before testing: `MM path` means normal imports/builds exercise a worktree that differs from the staged blob. Do not stage, stash, format, auto-fix, or commit. Run probes with bytecode/cache writes disabled and use temporary directories outside the repository. See `references/read-only-interactive-dashboard-diff-review.md` for the concurrent-staging sentinel and mixed-index/worktree procedure.

For interactive dashboards and TUIs, test focus and action authority across a viewport matrix—not only the largest happy-path render. A panel title is insufficient evidence that its selected row is visible. Hidden, vertically truncated, or hard-clipped panels must not retain active mutation or approval shortcuts. Require untruncated exact-scope review before recording a reason that claims such review occurred. If a wrapped selected action/scope cannot fit in the current overlay, approval/rejection/execute controls must remain disabled until scrolling or another explicit view has exposed the complete entry; selecting the row alone is not proof of review.

Treat passing tests as supporting evidence, not a veto over a minimal reproduction. Probe malformed provider envelopes **and semantically malformed object rows**: invalid numeric strings, booleans, mappings, `NaN`/infinities, and negative values must not be coerced into a fresh zero or overwrite last-good cache evidence. Also probe stale-derived reconciliation, repeated state transitions, duplicate/reappearing session counters, and breakpoint-specific visibility. Lead the report with PASS/FAIL, separate blockers from suggestions, name sensitive authority that remained closed, and state whether the reviewer modified any worktree file.

Before treating a full suite as release evidence, prove it ran against the committed candidate rather than a mixed worktree. Unstaged production edits can make committed tests pass while the actual commit remains broken; stashed production edits can leave committed tests ahead of their implementations. Record `HEAD`, stash tracked concurrent edits or use an isolated worktree, rerun the suite there, and recheck status immediately afterward. If a review or test run inspected a moving diff, its verdict is stale unless the final patch hash or `HEAD` matches the reviewed snapshot.

See `references/read-only-interactive-dashboard-diff-review.md` for the command sequence, no-write safeguards, adversarial fixture matrix, and verdict contract.

## Operator readability and desktop discoverability

After data truth is established, verify presentation as an operator workflow rather than a static screenshot:

- Prefer readable type and vertical scrolling over a global “fit everything without scrolling” mode. At a normal 1280×625 viewport, summary tables should fit their panels and detailed sections should remain reachable by scrolling.
- Remove fake window chrome and controls that do not perform their labels. Browser dashboards should use browser behavior; native desktop controls require a real host integration.
- Summary panels should show only decision-relevant columns. Put full factor detail, scheduler history, and diagnostics in their dedicated views instead of shrinking every column into the overview.
- Do not display persisted P/L beside newer live P/L without explicit labels. Use a recent-live watermark so periodic snapshot rendering cannot overwrite the fresher observation; verify agreement across every repeated value.
- Replace raw technical diagnostics in the primary header with concise operator language, preserving the exact reason in details or hover text. A preview artifact aging out is a warning when order submission is disabled, not an execution blocker.
- Resolve the actual Windows Desktop through the Known Folder API (`[Environment]::GetFolderPath("Desktop")`); do not assume OneDrive Desktop is the visible desktop.
- For a browser/tray application without a standalone executable, create a standard `.lnk` on the resolved Desktop. Point it to a hidden launcher that starts one authoritative runtime and opens the loopback URL. Give the shortcut a recognizable icon and description.
- Verify the shortcut by launching it, reading back its target/arguments, checking the server identity contract, and confirming the listener PID did not duplicate.

## Model-governance and promotion-control audit

For model-governance/operator-control audits, treat promotion status, artifact identity, and operator reassurance as separate trust contracts:

1. Inspect every champion/challenger evaluator and registry consumer, including duplicate app/backend implementations. Run the same incomplete proposal through each evaluator; divergent HOLD/REJECT/APPROVE semantics are a governance defect even when both paths are fail-closed.
2. Do not accept a top-level receipt `PASS` when nested proposals are `HOLD` or `REJECT`. A receipt's execution-safety boundary can be false while its decision/readiness status is still blocked; these dimensions must be represented separately.
3. Require one canonical model identity across registry, runtime resolver, checkpoint set, per-checkpoint SHA-256, model/config/schema hashes, code SHA, current picks, model history, and outcome ledger. Compare registry-declared path/hash to the exact inferred runtime path, not a global hash set.
4. Treat artifact existence as inventory only. “Healthy” requires parseability, schema validity, source/observation time, freshness SLA, validation status, and provenance binding. Exercise the operator status builder with missing/unknown inputs; unknown must not render `clear`, `armed`, or green by default.
5. Audit rollback as a runtime control, not a documentation promise. A registry-only backup cannot roll back a changed checkpoint, pointer, schema, or consumer configuration; require an immutable pre-change manifest and a tested restore path for any runtime-affecting promotion.
6. Record contradictions explicitly with exact paths, lines, computed hashes/statuses, and a non-mutating reproduction. Do not run broad tests or receipt generators when the audit is required to remain artifact-free; source probes and pure evaluator calls are sufficient evidence for these control defects.

See `references/model-governance-audit.md` for the reusable read-only probes and reporting template.

## Holistic execution, risk, and operations audit

For trading systems, do not stop at the dashboard or the nominal paper submitter. Inventory every mutation-capable path in source and wrappers before judging the execution boundary:

1. Search all `submit`, `create_order`, `cancel`, `replace`, `close_position`, SDK mutation, and credentialed private-client construction sites across scripts, legacy deploy code, CLI subcommands, crypto/exchange adapters, scheduler jobs, and Windows wrappers.
2. Trace each path to its actual entrypoint. A guard in `main()` or a high-level runner is insufficient if a public lower-level function, legacy script, SDK adapter, or alternate provider path can mutate independently.
3. Compare executable policy definitions with usage. A validated policy/config object that is only covered by tests but never loaded by the real mutation path is dead safety plumbing; report the exact callers that bypass it.
4. For each mutation, verify endpoint/account mode, market/session gate, symbol/asset scope, sizing and aggregate exposure limits, stale/unknown open-order handling, deterministic client idempotency, retry behavior after uncertain responses, and durable per-order receipts.
5. Treat order/position/fill/P&L evidence as a separate authority audit. Require exact order identity, terminal fill semantics, source timestamps/freshness, and reconciliation between broker state and local artifacts. Never infer a fill from requested `qty`, a successful GET, or a plausible local CSV.
6. Audit scheduler truth independently from scheduler intent: enumerate Windows Task Scheduler/service/startup wrappers, internal schedulers, job registries, working directories, logon context, last/next run, timeout/process-tree behavior, overlap policy, and durable receipts. A missing registry or stale dashboard snapshot is an operational finding, not a harmless configuration detail.
7. Exercise only read-only/static probes during a read-only audit. For mutation defects, provide a fake-transport or AST-based reproduction command and explicitly state that real/fake order-path tests were not run if the requested boundary forbids invoking them.

Prioritize findings where a broad legacy path, alternate broker/provider, or dead policy can bypass a narrow guarded path. Minimal repairs should centralize admission at the mutation boundary, remove or deny unsupported alternate entrypoints, bind evidence to deterministic order identity, and use process-tree supervision for scheduled workers. See `references/holistic-execution-risk-audit.md` for the reusable checklist and concrete failure patterns. For exactly-once broker mutation and recovery semantics, use `references/crash-safe-paper-order-reconciliation.md`.

## Autonomous worker status versus activity ledger

For autonomous worker panels, never treat recent event history as current concurrency. Maintain two separate views:

- **Worker status:** one current row per known worker, derived from the latest structured lifecycle event. Map `started`/`working` to `RUNNING`, `delegated` to `PENDING`, `completed` to `COMPLETE`, `needs_review` to `REVIEW`, `blocked`/`skipped` to `IDLE`, and `failed` to `FAILED`.
- **Recent activity:** a bounded append-only history of cycle markers, gate checks, delegation signals, and retry-suppression decisions.

A lane owner is not necessarily an active worker. A successful delegation means the coordinator recorded a request, not that the worker started or completed. A blocked gate attributed to an owner means the prerequisite check rejected execution; it does not mean the owner is working on the blocker.

Apply an age cutoff to `started`, `working`, and `delegated` events. Stale events must become `IDLE — last event Xm ago`, not remain `RUNNING`. Keep `blocked` and duplicate-dispatch suppression visible in the activity ledger while showing the worker as idle in the status view.

For fail-closed worker completion, require an in-repository artifact or receipt plus explicit passing verification. If evidence is absent or a receipt status is not passing, render `REVIEW`/`needs_review` and do not automatically retry. Suppress unchanged blocked signatures and allow retry only after prerequisite state changes or explicit escalation.

## Usage and cost observability

When an operational dashboard needs provider spend or token usage, use each authority only for the scope it actually proves:

- **Provider management/activity API:** account-level provider usage; label the provider, observation time, freshness, and whether the result is daily, historical, or estimated.
- **Local provider receipt ledger:** Vesper-attributed requests only; an empty `openai-codex` or `openrouter` ledger is **not** evidence that the provider account has zero usage.
- **Workspace/session telemetry:** local model-session counters, often workspace-scoped and potentially including cached tokens; do not present them as provider billing totals without an explicit reconciliation contract.
- **Quota telemetry:** remaining allowance is not usage and must be displayed separately.

For a dual-provider operator card, use explicit lines rather than one blended total: OpenAI/Codex workspace/session tokens plus source-reported weekly percent remaining; OpenRouter account activity tokens plus remaining dollars; and a separate local receipt-reconciliation line. An empty `openai-codex` or `openrouter` receipt ledger must never render as provider-account zero. Label workspace/session totals as local scope, not provider billing totals. If a provider reports no finite limit, render `$ left unavailable` rather than deriving or guessing a budget.

Keep authoritative daily aggregates distinct from locally estimated hourly burn. Cache management reads, persist sanitized snapshots only, label estimated rates explicitly, preserve the last good value on API failure, and never render an API failure or an out-of-scope empty ledger as zero spend. Every usage line should expose source/scope, provider, observation time, and stale/estimated status. If two authorities disagree, show both with their scopes and mark reconciliation degraded; do not silently merge them.

When a code-editing turn is followed by an external verification gate that says the workspace is unverified, run the relevant `pytest` command again in the canonical worktree even if an earlier result exists in conversation history. Treat the new process output as the only fresh verification evidence; repair any failure before claiming the slice is verified.

For process-linked usage checks, distinguish dedicated display/runtime processes, browser hosts for static files, worker runtimes, and supervisor parents. A missing dedicated display PID does not imply that workers are stopped, and a browser PID loading a static HTML file does not prove a live dashboard backend. Inspect command line, working directory, parent/child relationships, and listener ownership.

For OpenRouter endpoint fields, secret handling, aggregation, hourly-rate estimation, and verification, see `references/openrouter-usage-observability.md`. For the reusable process-identity and multi-authority usage checklist, see `references/runtime-identity-and-usage-scope.md`.

## Native Tk / multi-source display lineage

For Tkinter and other native operator consoles, audit the final UI writer rather than stopping at the snapshot model. Inventory every `StringVar`/widget update, asynchronous queue ordering, repeated writers, state-vocabulary conversion, and renderer fallback. Reconstruct the exact live labels, final counter scope, selected blocker fields, and semantic colors with a pure probe against the loader output.

Treat virtual-environment launchers and interpreter children as one logical runtime unless window/listener evidence proves competing instances. Bind shortcut target, process tree, visible window PID/title, process start time, and source mtime; a running Python GUI does not reload files that change during review. When source moves, separate runtime-loaded evidence from final-worktree evidence and apply the audit's immutable-versus-current-state contract explicitly.

Cross-check file-existence health against successful authorized producer receipts and task/review state. For SQLite freshness, inspect mixed timestamp storage classes and normalize them before taking a maximum. Never let a UI-sync timestamp, receipt filename date, or silent empty fallback masquerade as source freshness.

### Current-cycle evidence and bounded local administration

- When governance Markdown repeats a corrected field, parse the last canonical declaration and regression-test duplicate-field precedence.
- A daily receipt is current-green only when its receipt date matches the latest completed market session under the trading calendar. An older `PASS` is `stale`. Prefer the concrete selected artifact for `sourcePath`, and derive `asOf` from artifact/receipt metadata rather than UI sync time.
- A nonempty candidate CSV is inventory, not admission. Keep it waiting until producer identity, source session, decision date, validator result, and required review are bound.
- Name authority by domain. `TRADING AUTH CLOSED` may coexist with a separate bounded `KANBAN ADMIN`; a generic closed-authority label is misleading when any mutation control exists. Scope compact counters and provider values explicitly, and suppress typed provider capacity when its source is stale.
- Do not expose raw worker logs or task bodies. Display only bounded summaries/comments/events after credential redaction. Use neutral attribution for unauthenticated clicks.
- For local task administration, require canonical-root scope, selected-task existence, current-status gates, a reason for rejection, and a matching second click inside a short visible confirmation window. Route writes through the authoritative task CLI/service. If a task is already blocked, record rejection as an audited comment rather than a redundant transition.
- Construct since-launch activity trackers once per app lifetime. Recreating Codex/workspace/Git trackers each refresh resets semantics and repeats expensive scans.

See `references/native-vot-hardening-closure.md` for the condensed current-cycle, provider-scope, safe-Kanban, persistent-tracker, and release-closure checklist.

### Native polling and failure recovery

- Give each independent poll one in-flight guard and one timer handle. A completion message belongs in `finally`, and the Tk thread—not the worker—must clear the guard and schedule the next attempt. A success-only reschedule silently kills refresh after one transient exception.
- Preserve the last-good payload on read failure and render an explicit error/stale marker. A missing SQLite database, malformed query, or failed provider call must never become `0 tasks`, `all workers idle`, or `unavailable = zero`.
- Prove recovery by forcing the first loader call to fail, then running the real Tk event loop long enough for a second call to finish. Record loader call count, recovered snapshot presence, poll count, and callback exceptions. Distinguish nominal timer delay from end-to-end cadence when aggregation itself takes seconds.
- Route all background results through a queue carrying the source/task identity. Apply selected-task detail only if its captured ID still matches current selection; otherwise a slow older fetch can overwrite a newer selection.

### Native interaction harness

After source edits, run a finite programmatic Tk harness in addition to unit tests. Install `root.report_callback_exception`, let real polling complete, then exercise view toggles, tab changes, task selection, detail/log rendering, manual wheel scrolling, FOLLOW restoration, and close. Recursively count `winfo_class() == "Scrollbar"` when the design forbids visible scrollbars. Bind wheel handlers to card descendants and return `"break"` where a widget class also has a default wheel binding, or scrolling can fail over child labels or execute twice.

For task mutation controls, first verify exact CLI construction with mocks, then run the real lifecycle against a temporary Hermes home and disposable board (`create → comment → unblock → block → unblock → complete`). Read the isolated SQLite events/result back and delete the fixture. Never exercise production-board mutations merely to prove a button works.

A direct `python -m ...` runtime probe does not prove the desktop shortcut. After the final source change, separately launch the `.lnk`, read back target/arguments/working directory/icon, identify the visible process/window, and confirm no console or duplicate runtime. Any edit after that launch invalidates the launcher/runtime evidence.

See `references/native-tk-data-lineage-audit.md` for the reusable native-runtime, final-writer, state-vocabulary, mixed-SQLite, Kanban, provider-scope, failure-recovery, isolated-mutation, and shortcut-closure checklist.

When an approved native redesign exists as mockups or image layouts, also use `references/native-redesign-lineage-gap-audit.md`: inventory every dynamic mockup field, trace from final writer backward, distinguish loaded-but-unrendered fields from implemented UI, audit startup/cache mutations before launching, and report adapter/view-model gaps by operator domain. Before production edits, run a sanitized live-data reality check that reconciles task rows with current runs/heartbeats/task-bound events, separates declared assignment from activity, splits pending requests from non-authorizing decision history, and writes the source→view-model→writer matrix plus a read-only connectivity smoke contract. Implement data/view models first, one end-to-end workflow tracer second, and remaining pages only after that path is truthful.

## Second-opinion verification of another session's work

When asked to verify or reproduce a prior agent/session's verification claims, do NOT issue a verdict from your own battery alone. First read the prior session's report, audit notes, and claimed test counts (its "still required" list is the real gate). Then:

1. **Replicate their exact runs before widening.** Match their reported pass/fail counts first (e.g. their "73 passed, 2 failed"). If your boundary yields different counts (e.g. "150 passed, 0 failed"), their `-k`/selection boundary differed — bisect the test-selection boundary until you reproduce their number, or report that their count is not reproducible and show the widest-net result.
2. **Scope your verdict to what you actually ran.** A headless build + one refresh + focused tests is a *build/smoke signal*, never a release verification. Do not say "up-to-date" or "release-ready" without their full gate. When your checks pass but theirs is broader, say "green on my checks; their release gate stands."
3. **Classify every failure as pre-existing vs. introduced before attributing it.** Never report "N failures" as if the working tree caused them without a baseline comparison (see below).
4. **Windows pytest temp-dir:** if a run errors with `PermissionError: [WinError 5] ... Temp\pytest-of-<user>`, redirect `TMPDIR=TEMP=TMP` to a fresh dir (e.g. `/tmp/votpytest`) and add `-p no:cacheprovider`. This is environmental, not a code failure.

## Baseline-classify test failures (stash-verify-restore)

To determine whether a failing test was introduced by uncommitted working-tree changes or is pre-existing, run the identical test at the committed baseline:

```bash
git stash push -u -m "classify-baseline"   # -u includes untracked
git log --oneline -1                        # confirm you're at baseline HEAD
pytest <the failing tests> -q               # same command as against the tree
git stash pop                               # restore; verify no conflicts
git stash drop stash@{0}                    # ONLY after pop applies cleanly
```

- If the test fails **identically at baseline**, it is **pre-existing** — the working tree did not cause it. Report this; do not let the tree's owner take the blame.
- After `stash pop`, **verify the restore**: `git diff stash@{0} --stat` should be empty, re-run a fast focused test to confirm the tree still works, and only then `stash drop`. A "kept stash" message after pop usually means a harmless untracked-dir warning, not a conflict — confirm with `git diff --name-only --diff-filter=U` (empty = no conflicts).
- To classify **which change** introduced a string/behavior drift, compare token presence: `git show HEAD:<file> | grep -c "<token>"` vs `grep -c "<token>" <file>`. A token present at HEAD but absent now = the working tree removed it; absent at both = pre-existing.
- **Distinguish failure kinds before recommending a fix:** strict-literal-string assertions (test demands exact doc wording) and retired/legacy-path tests (e.g. a `deploy/` copy of a superseded module) are usually *test-needs-update* or *pre-existing drift*, not runtime bugs. A clean file failing a test is almost never the current slice's fault. A structural governance check that is fail-closed (e.g. mutations hard-closed) with a test expecting board-only enablement is a **design decision**, not a live security bug — say so explicitly and route the authority question to the user.

See `references/verification-and-baseline-classification.md` for the full recipes and the doc-contract/provider-policy failure taxonomy.

## Reporting

Lead with one trust verdict: **trustworthy**, **degraded**, or **not yet trustworthy**. Separate verified facts, repaired behavior, and remaining unverified work. If interrupted, state precisely which tests passed and which deployment checks remain.

### User-designated review and delivery pace

When the user explicitly states that they are the designated human reviewer and gives a verdict on the frozen candidate, treat that verdict as the human-review gate. Verify objective anchors available in the workspace (candidate identity/SHA and relevant checks) once, but do **not** delay integration merely because chat formatting damaged an otherwise clear review receipt or because a strict JSON response was wrapped/corrupted in transit. Do not spawn or request a redundant reviewer after the user has supplied the binding review; distinguish a materially missing verdict from a presentation defect. State the resulting next action immediately—repair, integrate, or stop—rather than creating another ceremonial freeze/review cycle.

## References

- See `references/verification-and-baseline-classification.md` for second-opinion verification of another session's claims, stash-based pre-existing-vs-introduced failure classification, and the doc-contract/provider-policy failure taxonomy.

- See `references/governed-tui-authority-replay.md` for unauthenticated approval attestations, terminal-column-safe minimum reviews, complete-event/checkpoint replay integrity, redraw-before-mutation tests, provider numeric overflow handling, and immutable review closure on moving canonical branches.
- See `references/pure-view-model-fail-closed-review.md` for exact evidence typing, duplicate-identity handling, total timestamp parsing, whole-page hashability, adversarial RED fixtures, and immutable candidate review loops.
- See `references/dirty-worktree-recovery.md` for preserving mixed rough-patch work, restoring tracked deletions without overwriting active edits, recovering the real validation baseline, and resuming productive bounded work after the trust gate.
- See `references/plumbing-audit.md` for the detailed audit checklist, regression targets, and common failure patterns.
- See `references/runtime-truth-patterns.md` for deployment-authority inventory, freshness vocabulary, timer/source arbitration, artifact provenance, deterministic browser tests, and scheduled-task readback.
- See `references/read-only-interactive-dashboard-diff-review.md` for stable patch capture, no-write verification, viewport/key-dispatch probes, provider-cache adversarial fixtures, and fail-closed review reporting.
- See `references/security-scheduler-closure.md` for loopback/action-authority probes, stale-health tests, shared execution-validator fixtures, once-per-minute scheduler checks, and the post-review verification closure loop.
- See `references/native-vot-hardening-closure.md` for current-cycle evidence admission, scoped authority/provider labels, sanitized Kanban administration, persistent native trackers, and exact final-tree release closure.
- See `references/windows-desktop-launcher.md` for Known Folder shortcut creation, identity-aware launchers, typography closure, and live-versus-snapshot UI consistency checks.
