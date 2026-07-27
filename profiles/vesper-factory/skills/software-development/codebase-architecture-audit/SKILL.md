---
name: codebase-architecture-audit
description: Read-only architecture audit of a complex subsystem — map signal paths, trace caller chains with exact line numbers, cross-reference policy declarations against actual code consumption, identify duplicate/dead implementations, rate severity, and deliver the smallest trustworthy architecture with minimal safe next actions.
---

# Codebase Architecture Audit

Trigger when the user asks for a read-only audit of a subsystem (portfolio, risk, data pipeline, execution, etc.) and wants exact paths, line ranges, caller evidence, severity ratings, and minimal safe next actions. Also trigger for phrases like "map the X layer," "trace the Y path," "identify dead/duplicate Z," or "find the smallest trustworthy architecture above factors."

## Prerequisites

Before starting any audit:

1. **Read project governance docs first.** Every repo with formal governance has an AGENTS.md, a policy hierarchy doc, and a board/tracker. Read them ALL before touching code — they tell you what's active, what's retired, what's gated, and what naming is legacy vs. current. Skipping this step produces an audit that contradicts the project's own source of truth.

2. **Identify the active policy hierarchy.** Read the repository's current authority chain from its canonical governance documents and machine-readable manifests. Treat retired documents, historical plans, archived receipts, and compatibility names as non-authoritative unless the active hierarchy explicitly incorporates them. The audit must evaluate code against current policy, not stale naming or former frameworks.

3. **Distinguish "registered without a current lane" from "dead."** A domain that appears in the program registry but has no active lane is a gap — not dead code. Dead code has no caller, no import, or an explicit runtime guard blocking execution.

## Audit Methodology

### Phase 1: Surface Mapping (broad, fast)

1. **Read the project board/tracker** for the subsystem's registered status, active lanes, approved scope, and current execution authority.
2. **File-name discovery** — `search_files` with broad patterns (`*portfolio*`, `*risk*`, `*alloc*`, `*sizing*`, `*covariance*`, `*turnover*`, `*sector*`, `*concentration*`, `*drawdown*`) across the entire repo. Do all patterns in one parallel call.
3. **Directory enumeration** — `find` or `ls -la` on `app/services/`, `scripts/`, `deploy/`, and any factor/signal directories. Get the full file list before drilling into individual files.
4. **TODO list** — create a todo list with the major audit dimensions (signal paths, sizing, covariance, turnover, costs, sector/beta/concentration, drawdown, execution handoff, duplicates, architecture). Mark them off as each is validated.

### Phase 2: Deep Trace (one dimension at a time)

For each dimension in the audit:

1. **Read the primary file** (e.g., `intent_portfolio.py` for portfolio construction). Read in chunks if >200 lines — use `offset` and `limit` to page through.
2. **Follow every import** — for each `from app.services.X import Y`, verify X exists. If it doesn't appear in `search_files` results, broaden the search (worktrees, different naming).
3. **Cross-reference policy declarations vs. code consumption.** For every config knob declared in a policy dataclass, search for where it's actually read and consumed. Mark "declared, never consumed" as an orphaned configuration — this is a HIGH severity finding.
4. **Record exact line ranges** for:
   - The function/method that implements the behavior
   - The caller that invokes it
   - The policy/config that governs it
   - The gate/validator that enforces it
5. **Run parallel reads** — when you need to inspect multiple independent files, batch them in one turn. Serialize only when a later read depends on an earlier read's content.

### Phase 3: Duplicate and Dead Identification

For each file in the subsystem:

1. **Caller search** — `search_files` with `target='content'` for the file's module name or key function names. If no callers outside its own test file, mark as "no external callers."
2. **Runtime guard check** — read the entry point (`main()`, `if __name__` block, or key function). If it raises `RuntimeError`, calls `SystemExit`, or has an early return with a disabled message, it's definitively dead.
3. **Duplicate detection** — when two files implement the same algorithm (e.g., sector-neutral selection, factor z-scoring), flag both with the exact line ranges and note any parameter differences (ddof, window length, ticker filtering).
4. **Version chaining** — when files are named v1, v2, v3, determine which is current and which are superseded. Superseded versions that share no callers with the active path are legacy.

### Phase 4: Architecture Synthesis

1. **Draw the active path** as a linear chain from data source to execution handoff, with each node labeled by file and primary function.
2. **Identify the smallest trustworthy subgraph** — the minimal set of files that, if everything else were deleted, would still constitute a working, fail-closed system.
3. **List what to remove** (dead code, orphaned config, superseded versions) and **what to add** (missing wiring, missing controls) with explicit preconditions.
4. **Severity ratings:**
   - **CRITICAL:** Would cause incorrect execution, silent data loss, or authority bypass if triggered.
   - **HIGH:** Currently safe (guarded or single-symbol) but would become critical at the next scale-up.
   - **MEDIUM:** Creates operator confusion, technical debt, or maintenance risk.
   - **LOW:** Cosmetic, well-contained, or accepting current constraints by design.

### Phase 5: Report Format

Deliver the audit as a structured markdown report with:

1. Header: auditor role, date, scope, constraints
2. Numbered sections for each major dimension
3. Tables with columns: Implementation | Location | Lines | Mechanism/Status
4. Severity callouts in **bold** with rationale
5. ASCII architecture diagram for the active path
6. "Minimal Safe Next Actions" table with Priority | Action | Risk | Precondition
7. Explicit conclusion paragraph

## Whole-Stack / Stackflow Inventories

When the user asks for the current stack, stackflow, APIs, AI sources, agents, technology, workflow, or “everything,” use `references/whole-stack-current-state-inventory.md`.

Key rules:

1. Classify every component as **declared**, **configured**, **installed**, **active**, **evidence-producing**, or **historical/retired**. Do not collapse these states.
2. Inspect external runtime authority in addition to repository intent: provider ledgers, Hermes profiles, live cron/OS scheduler state, service status, latest receipts, and scheduled-target existence.
3. Enumerate credential and environment-variable **names only**; never print values.
4. Build a contradiction matrix across board policy, guards, candidate producers, submitters, reconcilers, scheduler targets, operator-surface declarations, model profiles, and provider-call receipts.
5. Present one end-to-end flow and one clear recommendation. Avoid turning the report into a raw file inventory.

## Workforce and Autonomous-Loop Audit

When auditing a worker workforce, autonomous loop, or steward/coordinator, use `references/vesper-agentic-workflow-comparison.md` when a diagram or version claim must be compared against Vesper's split Hermes-Kanban and resident-agentd architecture. When the user supplies an aspirational architecture brief and asks for a path to a fully functional project, also use `references/brief-to-runtime-roadmap.md`: prove the live Git/board/process/artifact/scheduler baseline, choose one canonical orchestration owner, define “fully functional” across runtime and operations, and prefer a selective spine rebuild plus one bounded real-worker/evaluator loop over a wholesale rewrite or more unproven automation.

When the loop depends on an immutable task contract, bounded candidate DSL, frozen fixture/baseline, or closed deterministic verdict, use `references/immutable-contract-deterministic-evaluator-audit.md`. It covers byte-level identity, strict JSON, integer/rational evaluation, end-to-end runtime binding, write-once publication, `ACCEPTED`/`REJECTED`/`HELD` semantics, and Git evidence under concurrent untracked changes.

When a milestone claims a complete autonomous loop is proven across a classifier, task/Kanban bridge, real worker, lifecycle store, receipt, review, and restart/idempotency, also use `references/durable-agentic-loop-proof-audit.md`. It distinguishes canonical capability from branch/live evidence, tests declared authority against actual worker tools, rejects synthetic/manual task completion as worker proof, audits cross-store outboxes and fenced leases, and supplies the crash/replay matrix required for a `PROVEN` verdict.

When a later milestone must adapt that accepted lifecycle to a new research domain, also use `references/accepted-lifecycle-extension-audit.md`. It covers frozen Git/evidence digests in dirty roots, governance drift, core-vs-profile classification, additive v2 profiles, worker/holdout separation, PIT ranking semantics, exact state meanings, and separately approved one-shot scheduling.

1. Treat **role files, lane manifests, model-allocation tables, activity events, and provider ledgers as separate evidence classes**. A declared owner or model allocation is not a worker invocation; a delegation event is not worker start; a successful receipt is not proof of an AI call unless it carries provider/request identity.
2. Trace each lane action to a concrete handler. For `delegate_to_*` or equivalent signals, require an actual process/session launcher, prompt/input construction, provider request, worker artifact, and terminal receipt. If the coordinator only persists a claim and emits activity, classify dispatch as **signal-only**.
3. Search for real model-call primitives and their callers (`responses.create`, `chat.completions`, provider SDK calls, Codex/Claude process launches, HTTP inference clients). Model names in a quota router or manifest are declarative until one is reachable from the lane entrypoint.
4. Separate lifecycle evidence: `delegated` → `started/active` → `working` → `completed/failed`. Require fresh timestamps or leases for active state, and require an artifact/receipt plus passing verification before accepting completion.
5. Audit retries explicitly: identify retry count, backoff, idempotency key, timeout lease, completion transition, and retry suppression. A permanent `claimed` bit without timeout or reconciliation is not a reliable retry system.
6. Inspect the live scheduler authority separately from repository intent: Windows Task Scheduler definitions, user-level automation directories, service/startup wrappers, working directories, and last-result evidence. For every installed task, compare its actual command, arguments, and working directory with the checked-in runner; verify that the exact target exists and report a nonzero Last Result separately from configured `Ready` status. A registry document or checked-in task XML that says an automation exists is descriptive, not proof it is installed or runnable.
7. When task/worker JSONL state exists, trace its in-repo writers and readers separately. Require a binding among steward packet ID, durable task ID, worker identity, provider request ID, artifact, validator, and review outcome. A task ledger or provider receipt with no reachable repository writer is externally produced evidence, not a verified coordinator execution path.
8. For real-LLM viability, require one harmless end-to-end proof through the exact chain `coordinator → launcher → model → artifact → validator → receipt`, preferably with a fake transport for timeout/malformed-response tests before any credentialed run.
9. **Check who owns escalation when the agent layer is paused.** Paused steward/coordinator cron jobs leave blocked/needs-input board cards with no escalation even when escalation rules exist in lane manifests, and deterministic watchdogs typically only watch files and receipts — not board age. Look for a deterministic fallback (blocked-age check) or report the escalation gap explicitly.

## Git Worktree, Integration, And Shipping Audits

When the requested subsystem includes Git worktrees, branches, merge controls, CI, approvals, or deployment/shipping, add this evidence matrix before drawing conclusions:

1. **Snapshot Git state without mutation.** Capture `git status --short`, current branch/root, `git worktree list --porcelain`, local branch/upstream topology, and recent merge commits. Treat a worktree plan or contributor guidance as **declared process** unless an executable runner or current Git state proves it is active.
2. **Separate isolation from integration.** Multiple linked worktrees prove concurrent isolation, not a merge queue, integration branch, conflict resolver, or post-merge gate. Search executable non-document files for Git mutation/conflict primitives; report a policy-only process as manual rather than automated.
3. **Trace CI coverage from workflow commands, not test-file existence.** Extract the exact test paths and validators invoked by each workflow, then compare them with the relevant integration, scheduler, safety-guard, and deployment tests present in the repository. A green narrow CI lane is not evidence that absent critical suites ran.
4. **Trace approval end-to-end.** A manifest field such as `requires_operator_approval` is descriptive until the execution-capable function consumes a bound, authenticated approval record. Follow the action from CLI/UI entrypoint through approval consumer, scope/freshness checks, and final side effect. If a decision ledger always fails execution or is never called by the submitter, classify approval as recorded-but-non-authorizing.
5. **Inspect live scheduler/deployment state separately, read-only.** Compare tracked templates/installers with the installed task/service action path, working directory, enabled state, next/last run, and last result. A task targeting a runtime snapshot rather than the audited checkout is deployment drift. Do not infer the cause of an exit code without the corresponding logs.
6. **State external-control uncertainty precisely.** If branch protection, environment approvals, or release controls cannot be read through the available API/account, say **unverified**, not absent. Likewise distinguish no tracked release workflow from a possible external release process.
7. **For Windows scheduled pipelines, prove the installed task’s exact target before calling it active.** Read-only query each relevant task for enabled state, next/last run, last result, action, and working directory; then prove the exact executable/script/batch target exists in the audited checkout. Record runtime-snapshot drift explicitly when a task targets a copied deployment directory rather than the repository. Treat an enabled task with a missing target or nonzero last result as **installed but non-runnable/unverified**, not active. Distinguish a PASS dry-run receipt from evidence of a successful scheduled production run.

## Gated Multi-Agent Software-Delivery Audits

When auditing a proposed Planner → Build → gates → independent review → ship workflow, audit the execution graph rather than role names or design documents.

1. **Freeze the audit boundary first.** Capture branch, `git status --short`, worktree inventory, board/task state, active profiles, and existing untracked artifacts. Do not run tests or commands that write artifacts when the user requires a no-modification audit; inspect prior receipts and CI definitions instead.
2. **Trace one real task chain.** Start from a planner card, then inspect builder workspace/branch, gate commands and their recorded exits, reviewer task, rejection/rework linkage, and final authority. A manually completed chain proves primitives only; it does not prove a reusable state machine.
3. **Classify each required gate separately.** For every stage—planning, build, format, lint, type check, test, review, integration merge, post-merge test, approval, ship—state PRESENT, PARTIAL, MISSING, or PRESENT BUT UNSAFE. Cite the exact file/function/command/task event and the limiting condition.
4. **Bind every approval to immutable source identity.** Verify base SHA, candidate full SHA, diff/receipt hash, and reviewer identity. A short SHA prefix, branch name, mutable worktree, or task `done` status is not sufficient approval evidence.
5. **Separate isolation from orchestration.** A Git worktree proves only workspace separation. It does not prove component decomposition, safe parallel scheduling, conflict handling, staging merge control, or post-merge validation.
6. **Treat task budgets and retries as safety controls.** Inspect effective iteration budget, retry limit, lease/heartbeat, stale-run handling, idempotency, and escalation. A card that can start with a zero or invalid budget is a workflow reliability defect, not a harmless runtime detail.
7. **Trace failure routing, not just failure logging.** Exact formatter/linter/test output must reach the responsible builder; review rejection must select Planner only for an invalid approach and Builder for an implementation defect. If humans manually recreate cards or copy comments, classify routing as partial or unsafe.
8. **Trace Ship to a real side effect.** An approval ledger is only recorded intent until an execution-capable handler consumes a scope-bound, authenticated approval and produces an idempotent receipt. If execution intentionally fails closed, classify controlled ship as missing—not as active deployment support.
9. **Keep prototypes distinct from canonical capability.** Code present only on an unmerged branch or isolated worktree is a candidate/prototype. Do not count it as a canonical repository capability until the review and integration gates accept it.

## Desktop GUI Runtime Architecture Audits

When the audited subsystem is a Tkinter, Prompt Toolkit, Qt, Electron, or similar long-lived operator UI, add a runtime-lifecycle pass rather than treating it as a static renderer:

1. **Freeze an immutable baseline before probing.** Record HEAD and initial dirty status. If another process changes the worktree during the audit, do not silently mix revisions or line numbers: keep findings bound to the frozen commit, use `git show <sha>:<path>` for baseline verification, and report the concurrent delta separately as an unverified working-tree mitigation.
2. **Trace every poll outcome.** Follow success, error, timeout/hang, manual-refresh, and shutdown paths. Verify where the next timer is scheduled, whether an in-flight guard exists, whether queues are bounded, and whether queue draining has an item/time budget.
3. **Enforce UI-thread ownership.** Background workers may do I/O, but UI calls must return through one main-thread queue. Look for worker-thread `after`/widget calls, stale-response races, missing request-generation tokens, daemon threads that outlive close, and callbacks that are not cancelled or joined.
4. **Audit redraw signatures against visible state.** A signature must include every field rendered by the widget. Check selection reconciliation, scroll/yview preservation, event binding on child widgets (mouse-wheel events do not automatically bubble to a parent canvas), and follow-mode behavior when the user scrolls manually.
5. **Treat command safety and authority safety separately.** An argv list with `shell=False` can be injection-safe while still being an authority bypass. Trace confirmation, identity, immutable scope, task/status preconditions, result checking, partial-success behavior, timeout handling, and whether synchronous commands block the UI thread.
6. **Verify deployment reproducibility.** Compare the live shortcut/launcher target with tracked installers, icons/assets, CI compile/test lists, and the declared supported entry point. A manually working shortcut is not a reproducible product path.
7. **Use mock-only action probes.** Never exercise live mutation buttons during a read-only audit. Patch command wrappers, use temporary SQLite fixtures, and test queue ordering/race behavior with fake roots and deterministic delays.

Reusable probe patterns and reporting guidance are in `references/desktop-gui-runtime-audit.md`.

## Dead-FILE Audits (orphan / superseded / retired files)

When the user wants dead **FILES** (not in-function dead code) — orphaned scripts, retired
launchers, duplicate/superseded modules, stale bulk artifacts, empty files — use
`references/dead-file-audit.md`. It covers the reference-count scan (code vs. doc refs), the
CONFIRMED-DEAD / LIKELY-DEAD / UNCERTAIN confidence ladder, an O(N)-single-pass scanning pattern
that avoids timeouts on large repos, and the false-positive traps that look dead but are live:
sibling-imported helper modules, retirement shims gated by CI tests, externally-scheduled entry
points (cron / `.hermes` lanes), and "duplicate" dirs that are actually the live core.

## Greenfield Trading System Scoping (IC, Universe, Data Sources)

When the user asks whether to pay for premium market data, what IC level to target, or how large a stock universe to use, use `references/greenfield-trading-system-scoping.md`.

Key rules:
1. **Don't spend money on data until the system runs.** A $200/month Massive subscription is premature when the codebase has broken startup paths (empty dashboard, missing strategy wiring, invalid provider config). Fix the skeleton first, prove the strategy on free data, then upgrade.
2. **Free data is sufficient for validation.** yfinance (daily bars, backtesting) + Alpaca Data API (paper trading) cover 90% of early-stage needs. Save premium data for when you have a proven edge that needs better execution.
3. **Target IC = 0.03–0.06.** Anything above 0.10 is likely overfitting or look-ahead bias. The real constraint is turnover cost, not raw IC.
4. **Universe size: 100–200 stocks.** 20 is too concentrated (one earnings miss kills you), 1000 is overkill for a $50k account (data cost, API limits, slippage dilute alpha). 100–200 gives enough cross-sectional spread for meaningful ranking without operational complexity.
5. **The bottleneck is always portfolio construction, not more factors.** Before building factor #N+1, ask whether risk management, position sizing, and execution are wired. The alpha ceiling is in the layers above raw signals.

## Strict Read-Only Audits of Non-Git Source Bundles

When the target is a copied folder, extracted archive, prototype bundle, or release snapshot rather than a Git worktree, use `references/non-git-read-only-source-bundle-audit.md` and the read-only `scripts/source_manifest.py` helper. For compact broker/equities systems, also use `references/small-python-trading-system-static-audit.md` for the configured-path-vs-backtest split, startup-blocker ladder, broker-effect safety trace, declaration-to-consumer config matrix, credential-safe reporting, Windows persistence checks, and static test-gap matrix. Keep currently unreachable hazards labeled **latent** so a blocked application is not misreported as active.

1. Capture the deterministic content **and metadata** baseline before any other probe; a hash first captured mid-audit proves only the later verification window.
2. Never import target modules or run tests, linters, formatters, installers, entrypoints, or constructors under a strict no-modification boundary. Use direct reads and `ast.parse`/in-memory `compile` for Python syntax and symbol inspection.
3. Inventory volatile artifacts (`__pycache__`, `data`, `logs`, coverage, receipts) separately rather than silently excluding them from the no-touch proof.
4. Build a documentation/config/runtime contradiction matrix and trace each advertised entrypoint as a blocker ladder: import → construction → configuration → artifact → side-effect boundary.
5. For side-effecting systems, compare the displayed mode with the effective client and endpoint, represent unavailable external state as unknown rather than empty, and trace rollback/flatten/close actions through terminal confirmation before state clearing.
6. Report credential-shaped material only by path, line, and key/variable name; never reproduce values.
7. Repeat the exact manifest command at the end and state precisely whether the proof covers the whole session or only the measured window.

## Read-Only Worktree Reviews With Concurrent Changes

When reviewing an isolated worktree that may be active in another session or agent:

1. **Freeze the baseline before analysis:** capture branch, full HEAD SHA, `git status --short`, and worktree path. Bind findings to that SHA.
2. **Separate baseline from concurrent delta:** if new tracked/untracked files appear during the audit, report them as a separately observed working-tree delta, not as evidence of the frozen commit. Use `git cat-file -e HEAD:<path>` or `git show <sha>:<path>` to establish whether a path belonged to baseline.
3. **Do not run tests in a strict no-modification audit.** Test runners can create caches, temp roots, receipts, or coverage artifacts. Inspect test source and prior receipts/CI definitions instead; say explicitly that tests were not executed because the requested boundary forbade mutation.
4. **Trace snapshot entry points separately from pure projections.** A pure display/projection function may be harmless when given a snapshot, while its normal UI/CLI snapshot producer can instantiate provider supervisors, load environments, start background polling, access accounts, or otherwise traverse authority-sensitive paths. Recommend proposal/report CLIs accept a narrow reviewed local evidence adapter or perform inspection only; do not have them construct broad dashboard/terminal snapshots.
5. **For a proposed ledger, test the integrity contract—not merely denial fields.** Require bounded-before-parse reads, writer serialization, replay-before-write, idempotency, interrupted-write preservation, tamper/truncation detection, and immutable provenance/receipt binding. A full-file atomic replacement without a lock is not append-only and can lose concurrent updates.
6. **Re-freeze after every long probe and immediately before verdict.** Capture full HEAD plus per-file blob hashes for the reviewed slice. If another worker commits during the audit, compare blob identities before reusing evidence: unchanged implementation blobs may retain implementation-probe evidence, but a test-only delta still requires the affected suite and test-quality review to rerun. Any implementation-blob change invalidates earlier runtime probes and line references. Never silently issue a verdict for the SHA that happened to be current at audit start.
7. **Prove new regressions RED without stashing or resetting the live worktree.** Export the immutable base revision to an external scratch tree (for example with `git archive`), overlay only the candidate tests, and run them with an external temp/basetemp. Count a test as meaningful only when old behavior fails at the intended behavioral assertion. A RED caused by a newly required fixture/artifact being absent, import/setup drift, or unrelated old-suite failure does not prove the remediation test.

## Governance / Status Truth Reconciliation Audits

When the user asks whether a milestone, board, tracker, issue registry, fact base, health page, runtime, data cache, receipt chain, and roadmap all tell the same truth, use `references/governance-status-truth-reconciliation.md`.

1. Build an **evidence dependency graph**, not a flat document comparison: authority policy → current tracker/board schema → live task store, issue registry, and manifests → physical runtime/scheduler/data evidence → fact base → status/health documents → roadmap claims.
2. Classify at the **field or claim level**. A policy-designated canonical document can still contain stale operational values; a current runtime receipt can be authoritative for one run but non-canonical for program policy. Use the independent dimensions `role` (canonical/derived/historical) and `condition` (current/stale/missing/contradictory/unverified).
3. Freeze both the Git baseline and the observation window. Record initial and final HEAD/status. If another worker changes files or refs mid-audit, bind baseline findings to `git show <frozen-sha>:<path>` and describe the working-tree delta separately; never silently mix revisions, mtimes, or line numbers.
4. Validate parsers and field vocabulary before trusting a green/red consistency validator. A tracker rename such as `Next ready task` → `Next ready operating task` can make the validator report `None` while the human-readable field is present.
5. Preserve nested receipt semantics. A wrapper `PASS` may mean “the fail-closed child outcome was recorded,” not readiness, submission, fill, or operational success. Trace parent → child → validation → side effect and name the first failed dependency.
6. Treat a mutable latest-receipt path as an observation cache, not a run-history proof. Correlate receipt timestamps and run IDs with scheduler history; a later manual rerun can overwrite a failed scheduled receipt without repairing the installed schedule.
7. Reconcile dates through the actual consumer path and market/session calendar. Resolve the canonical database/cache path from source code, then compare physical data dates, board mirrors, pretrade inputs, and expected completed sessions. File mtime alone is not data freshness.
8. Order repairs upstream-first: schema/authority vocabulary → task and issue provenance → runtime/data prerequisites → receipt consumers → fact-base regeneration → status/health regeneration → roadmap acceptance. Do not “fix” downstream prose first.

## Comparator Identity In Architecture Audits

When a user asks for a comparison with a named external product, framework, or project:

1. Establish the comparator before claiming equivalence: search the audited repository for the exact name, then obtain an authoritative external source (official documentation, canonical repository, or user-provided specification).
2. If the name is ambiguous, absent locally, or external searches yield only unrelated projects, do **not** silently substitute a similarly named product or a generic best-practice model.
3. Still deliver the local inventory. Add a clearly labeled **Comparator boundary: unverified** entry and classify the comparator specification itself as `MISSING`.
4. If a generic durable-agent rubric is useful, label it as such rather than presenting it as feature-for-feature parity with the requested comparator.
5. Request a URL, repository, or architecture diagram only as the follow-up needed to complete literal parity analysis; do not block the read-only local audit on it.

## Point-in-Time Event-Factor Feasibility Audits (SUE / PEAD / Earnings)

When assessing whether an event-driven fundamental feature is feasible under a strict read-only and no-leakage boundary:

1. **Prove the configured runtime path first.** Trace configuration → feed/loader → feature schema → trainer/strategy. A nearby cache, research note, sibling repository, or canonical-store artifact is not an available source unless the audited runtime is configured to read it.
2. **Separate the necessary inputs.** For standardized unexpected earnings, require actual EPS with a declared basis; consensus EPS plus an immutable pre-release estimate vintage/as-of timestamp; fiscal-period identity; and a stable issuer identifier. SEC/company-fact data alone may supply reported facts but cannot supply the consensus surprise.
3. **Require event availability timestamps, not dates.** Preserve issuer release/published time, filing acceptance time where applicable, source first-observed time, time zone, and revision lineage. A filing date, cache mtime, or period end is insufficient evidence of when a feature became tradable.
4. **Define the cutoff against the actual execution model.** For a daily-bar, next-open strategy, accept an event for session D only when its `available_at` is before the previous market close; disallow same-session BMO/AMC signals until intraday bars and an explicit execution policy exist. Require each estimate vintage and actual observation to be available no later than the feature snapshot.
5. **Use read-only metadata probes.** Inspect SQLite schemas with `mode=ro`, Parquet schema/metadata when an installed reader permits it, source manifests, and artifact metadata. Do not download, materialize, train, or run backtests in a feasibility audit. Classify unreadable or ambiguous artifacts as unverified rather than inferring fields from filenames.
6. **Verdict logic.** Recommend NO-GO if any indispensable field or cutoff provenance is absent; a prospective source catalog or unintegrated schema is only a conditional future path. State the smallest data-acquisition and validation gate required before re-review.

## Reproducible Model Candidate / Paid-Compute Gate Audits

When the user asks whether durable transformer, sequence-model, or other ML artifacts support a reproducible paid run, use `references/reproducible-sequence-model-paid-test-audit.md`.

1. Exclude `.tmp`, test fixtures, pytest basetemps, virtual environments, and scratch worktrees before candidate inventory.
2. Distinguish a checkpoint that exists and loads from an historically reproducible candidate. Require source/data/config/split identities, not just a checkpoint hash and a current database path.
3. Treat only model-unseen evaluation as a holdout. A rolling portfolio backtest from a fixed model is not a valid holdout if its dates overlap the model's training panel; require refit-per-window proof or a truly later untouched period.
4. Reconcile economic claims with shuffled-label, equal-weight, and simple-model controls. If shuffled controls retain substantial benchmark outperformance, report model-specific skill as unproven.
5. Read receipt authority fields separately from receipt `PASS`; report-only, hold, and promotion-not-ready status cannot authorize external paid compute.
6. Return an explicit GO/NO-GO, gate-by-gate evidence matrix, and the smallest frozen replay bundle required for re-review.

## Portable Agent-Asset Migration Audits

When reviewing a project-owned skill/profile migration into runtime profile homes, audit the copier as a security boundary rather than treating successful hash output as sufficient.

1. **Probe native path semantics.** A POSIX parser followed by a Windows `Path` conversion can reject `../x` while accepting `..\\x`, drive-absolute paths, drive-relative paths, or alternate separators. Test the exact validation function with native separators and prove resolved source and destination paths remain under approved roots.
2. **Require exact managed-tree parity.** Comparing only expected source files is subset equality, not synchronization. Detect extra destination files as drift. Distinguish unrelated sibling skill directories from stale or unreviewed files inside a managed skill directory.
3. **Preflight before writes.** Validate every required `SKILL.md`, profile identity, source directory, target, symlink/reparse point, and manifest relationship before the first copy. A late missing source must not leave a partial runtime or canonical update.
4. **Treat recursive import as a secret boundary.** A directory allowlist is not a file allowlist. Check for credential-shaped files/content, caches, runtime state, symlinks, junctions, and unexpected extensions before importing a live tree. Documentation claiming credentials are excluded must be enforced by code, not inferred from currently clean contents.
5. **Validate target relationships.** Named skill targets should belong to the declared portable-profile set unless a separately reviewed exception exists. Reject absolute/traversal targets and avoid profile-name substring expansion.
6. **Separate historical receipt from current state.** A receipt saying “synchronized” proves only its observation window. Rerun a read-only checker immediately before verdict and report concurrent runtime drift separately from immutable project-source findings.
7. **Verify rollback artifacts structurally.** Confirm backup hash, member allowlist, embedded-manifest coverage, per-member hashes, and zero credential-pattern findings without extracting into the audited tree.
8. **Inspect semantic profile identity.** Byte parity can faithfully preserve the wrong role. Compare each profile name and intended lane with its `SOUL.md`; duplicate generic identities under distinct product/research/risk names remain a correctness concern even when hashes match.

For the concrete Windows probe matrix, exact-parity rules, backup checks, and regression-test inventory, see `references/hermes-asset-portability-audit.md`.

## Capability / Provenance Authorization Repair Audits

When independently verifying a frozen authorization/provenance repair — especially one that replaces public minting symbols with closure-private capabilities, hash-bound contracts, or sealed manifests — use `references/capability-authorization-audit.md`. Do not stop at “the old public bypass is gone.” Probe grant-to-use binding: context minted for input A consumed against input B, mutation after grant, repeated context use, and caller-generated self-sealed manifests. A caller-supplied hash manifest proves internal consistency only; it is not approval unless bound to an external frozen approval root.

## Windows Handle-Bound File-Operation Feasibility Audits

When a Windows Python subsystem claims it can prevent path/reparse races with a directory-handle-relative create or publish path, do not accept `Path.exists`, `Path.glob`, `os.replace`, or a pre-check of file attributes as proof. Audit the claimed authority boundary as follows:

1. Freeze the target worktree and classify all current pathname operations separately from handle-bound operations.
2. Inspect installed Python/pywin32 capability, `ntdll` exports, and the locally installed Windows SDK declarations. Record whether native calls need `ctypes` and define their ABI rather than relying on an assumed layout.
3. Probe only in a disposable temporary directory: direct-child `CREATE_NEW`, a directory-reparse traversal with and without `OBJ_DONT_REPARSE`, no-replace rename collision, successful absent-target rename, and an existing reparse target.
4. Require a pinned root handle, grammar-restricted one-component child names, `OBJ_DONT_REPARSE` on `NtCreateFile`, `DELETE` access on the source being renamed, and no pre-rename existence check.
5. State the boundary precisely: `NtSetInformationFile(FileRenameInformation)` accepts a destination root handle but has no `OBJ_DONT_REPARSE` field; a handle-relative no-replace direct-child publish is narrower than a general recursive no-reparse guarantee. Pathname-based recovery/enumeration remains outside it until converted as well.
6. Treat native-API supportability as a material risk: `winternl.h` labels these APIs internal and version-variable. A successful local probe proves current feasibility, not durable public-API compatibility.

See `references/windows-handle-bound-file-operations.md` for verified x64 layouts, constant distinctions, probe expectations, and the minimal call sequence.

## Pitfalls

- **Do not trust file-name search alone, and do not fall back to an unbounded repository crawl.** Files like `paper_application_policy.py` may live in `app/services/` but `search_files` with `path=D:/vesper/app` can fail due to Windows drive-path resolution. If `search_files` returns an implausible zero-file result, verify with a read-only native-drive probe. For tracked source, prefer `git ls-files` and scan only that bounded list. When untracked/runtime artifacts are in scope, use top-down `os.walk('D:/vesper')` and prune `.git`, `.worktrees`, `.tmp`, `tmp`, `node_modules`, caches, generated test roots, and large `data`/`artifacts` trees unless the audit explicitly needs them; filter and cap output before printing. Never run unconstrained `Path('D:/vesper').rglob('*')` over a repo with generated test trees. Do not substitute `/d/vesper` blindly: on some Windows shells the native `D:/vesper` path exists while `/d/vesper` does not.
- **Do not assume an imported module exists just because it's imported.** Python files in governed repos may import from modules that only exist in worktrees or were renamed. Verify every import with a file search.
- **Do not conflate "registered without a current lane" with "dead."** The project board may register a domain as a placeholder for future work — that's a gap, not dead code to be removed.
- **Do not treat research scripts as production.** Scripts like `factor_optimizer.py`, `signal_mine.py`, `dd_circuit_breaker.py` are research artifacts. Flag them as "research only, not integrated" — don't recommend deletion unless they're explicitly rejected in a design doc.
- **Do not skip the governance docs.** An audit that doesn't account for the project's own policy hierarchy will flag false positives and miss real gaps.
- **Do not run a broad suite as the only proof of an autonomous worker.** Use focused coordinator/ledger/receipt tests first; report unrelated stale-contract failures separately rather than treating them as worker-runtime evidence.
- **A cron job firing green every tick proves the schedule works, not that the lane produces.** Verify the job's *target* exists and has produced real output, and read each health check's comparison logic — a check that reads a value without comparing it, ignores receipt status, or counts dry-run/no-op receipts as evidence structurally cannot fail. Green-no-op (`PASS {action: no_queue}` forever) is a distinct state from productive and must be labeled as such.

## Staged-Diff Reviews

For large read-only staged-diff correctness reviews, also consult `references/staged-diff-correctness-review.md`. It covers exact-index hashing/export under concurrent working-tree changes, producer-to-consumer status tracing, calendar/portfolio assumptions, state-machine races, test expectation laundering, and adversarial Windows no-agent scheduler probes for release identity, credential closure, live-owner gates, process containment, crash recovery, and rollback evidence.

## Versioned Autonomy Roadmap Documentation

When an architecture/current-state audit is being turned into a V2→V3 (or similar) roadmap, preserve the evidence boundary instead of presenting the roadmap as a product-status claim:

1. **Label the version model honestly.** If the repository has no formal release/version contract, call the V2/V3 labels a proposed architecture direction. Define what each label means operationally.
2. **Separate evidence classes.** For every claimed capability, distinguish declared, configured, installed, active, evidence-producing, and historical/retired. A successful runtime artifact proves that an execution happened; it does not prove that the canonical repository contains the producer or that the path is reproducible.
3. **Trace artifact provenance.** For any autonomous-worker proof, require the binding `task → worker → provider request → artifact → validator → receipt`, and separately verify that a tracked source path can produce it. If the event/artifact exists only in runtime state, report it as real evidence but non-canonical until the producer is recovered or recreated.
4. **Make the roadmap actionable.** End with one smallest safe first slice, its exact acceptance chain, explicit non-goals, and a staged path to resident/event-driven autonomy. Do not jump directly from cron inventory to a broad planner.
5. **Anchor the document.** Cite exact repository paths, live runtime surfaces, and current operational evidence. Treat older architecture documents as historical when live scheduler/runtime state contradicts them.
6. **Keep authority separate from autonomy.** Every V3 step must state which authority classes remain closed; autonomous worker capacity must never be presented as broker, order, risk, promotion, scheduler, provider, or secret authority.

## Complete Workflow-Diagram Artifacts

When the user requests a **complete current-repository workflow diagram**, produce a standalone HTML/SVG artifact in addition to the audit material.

1. Use a two-layer completeness design: a readable diagram of active and retained workflow nodes, then an exhaustive backing inventory generated from actual tracked plus nonignored-untracked file paths. Do not falsely put every file into the SVG just to claim completeness.
2. Place a linked table of contents directly below the diagram when requested. Include sections for board-first current state, authority gates, entrypoints, live operational state, coverage matrix, complete inventory, review findings, and source limitations.
3. Treat the current board as authoritative over older architecture/readme/runbook prose. Explicitly identify conflicting UI/topology claims and classify non-current surfaces as retained compatibility, historical, or aspirational.
4. Inspect live scheduling and runtime state separately from repository source: cron inventory, Windows Task Scheduler definitions/results/targets, worker/ledger existence, worktrees, and CI configuration. Classify each item as declared, configured, installed, active, evidence-producing, failed/drifted, or unverified.
5. Verify the artifact after writing: HTML parses; TOC follows the SVG; each inventoried repository path occurs in the output; and the reported file counts match the source enumeration. Never include credential values, account identifiers, or raw provider payloads.

## Verification

After delivering the audit:
1. Confirm every severity rating has a rationale tied to specific code evidence.
2. Confirm the "smallest trustworthy architecture" can be traced end-to-end with no missing links.
3. Confirm dead-code identifications include caller evidence (or the absence of callers).
4. Confirm next actions are minimal, reversible, and gated by explicit preconditions.