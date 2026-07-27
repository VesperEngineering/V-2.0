---
name: vesper-tkinter-ui-engineering
description: Use when designing, prototyping, building, reviewing, or repairing Vesper Tkinter operator interfaces, especially VOT/VWM layouts, card workspaces, workflow views, evidence surfaces, Windows-native behavior, responsive geometry, polling, and visual customization. Applies a minimalist systems-engineering process grounded in official Tkinter/ttk documentation, source-backed dashboard truth, reusable ecosystem evaluation, actual-window visual QA, and Vesper's fail-closed authority boundaries.
version: 1.1.0
author: Hermes Agent
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [vesper, tkinter, ttk, ui, layout, windows, vot, vwm, dashboard]
    related_skills: [desktop-gui, vwm-design-contract, operator-dashboard-assurance, test-driven-development]
---

# Vesper Tkinter UI Engineering

## Overview

Use this skill as the professional Tkinter/layout specialty for Vesper's existing Engineer. It supplies reusable engineering procedure; it does **not** create a new worker, authority role, approval path, or review exemption.

The goal is a small, truthful, Windows-native interface whose structure makes operational meaning obvious. Prefer a few strong surfaces over a dense collection of panels. Every displayed claim must remain traceable to an authoritative source, freshness marker, receipt, or explicit unavailable state.

Official Python `tkinter` and `tkinter.ttk` documentation are the implementation source of truth. TkDocs and ecosystem projects are secondary pattern libraries. Load `references/resources.md` when choosing widgets, themes, GUI builders, charts, tables, or third-party packages.

## When to Use

Use for:

- VOT/VWM Tkinter layout redesigns and card workspaces.
- Agentic workflow, learned-information, action-ledger, provenance, and history views.
- Responsive geometry, typography, navigation, polling, lifecycle, and Windows behavior.
- Converting a visual mockup into production Tkinter code.
- Evaluating whether prebuilt Tkinter technology should replace custom code.
- Visual defects: crowding, clipping, flicker, imbalance, stale state, lost selection, or unreadable density.

Do not use for:

- Prompt Toolkit terminal rendering; use the terminal/TUI skills.
- Rich document editing or PDF-centric apps; evaluate PySide6/Qt.
- Approval, trading, broker, scheduler, risk, or promotion policy changes.
- Inventing dashboard data because a desired panel has no authoritative source.

## Non-Negotiable Boundaries

1. **Display is not authority.** A card, button, status, event, or log line never grants permission. Preserve Vesper's separate human gates and receipt-backed actions.
2. **Evidence before presentation.** Trace each value to its reader, timestamp/freshness field, and failure state before styling it.
3. **Unknown stays unknown.** Render `UNAVAILABLE`, `MISSING`, `STALE`, or `NOT ACTED`; never fill visual gaps with plausible sample content in production.
4. **Mockups are labeled.** Standalone concepts must say `DESIGN MOCKUP / SAMPLE DATA` and must not read or mutate live systems unless explicitly requested.
5. **No self-approval.** Engineer may implement; another governed reviewer validates the change.

## Minimalist Design Contract

Minimalism means fewer concepts, not smaller text.

### Information hierarchy

Use five levels only:

1. Global state: app identity, paper/live boundary, authority, evidence, version.
2. Workspace navigation: Overview, Workflow, Knowledge, Actions, Evidence, Kanban/Research as justified.
3. Primary object: selected workflow, task, claim, action, or receipt.
4. Supporting cards: facts, transitions, tests, sources, timestamps.
5. Diagnostics: raw logs, developer provenance, and verbose metadata behind a detail surface.

If two panels answer the same operator question, merge them. If a panel cannot state its operator question in one sentence, split or remove it.

### Layout rules

- Use major horizontal bands for appbar, workspace navigation, body, and decision boundary.
- Use a balanced page grid for primary work. Avoid a permanent left rail that owns most content.
- Use `grid` for aligned, responsive page/card layouts; configure row/column weights and uniform groups.
- Use `pack` for simple one-dimensional bands. Never mix `pack` and `grid` among children of the same parent.
- Use `PanedWindow` only when the operator benefits from resizing a genuine split.
- Avoid `place` for application layout; reserve it for bounded overlays or canvas-local positioning.
- Keep card nesting shallow: section → card → content. Avoid cards inside cards inside cards.
- Prefer whitespace, 1px rules, and typography over ornamental frames and gradients.
- Use an 8pt operational-text floor. Density may not be purchased with unreadable microtype.
- Test minimum, default, and wide window sizes. A default screenshot alone is insufficient.

### Vesper visual system

Unless the user explicitly approves a new identity:

- Preserve the VWM near-black/warm-white palette and 3px orange appbar rail.
- Use Segoe UI for headings/body and Cascadia Mono for states, IDs, timestamps, and receipts.
- Show one semantic version (`VOT vX.Y.Z`) in the native title and visible appbar.
- Keep `LIVE` static. Do not animate wall-clock sync timestamps or flash transient `SYNCING` labels.
- Use status color as a secondary cue; the text state remains mandatory.
- Use real Tk buttons for operator actions. Do not hide primary actions behind keyboard-only shortcuts.
- Keep confirmations inline; do not use detached `messagebox` or `simpledialog` windows for integrated operator flows.
- Follow the current VOT/VWM no-visible-scrollbar contract; mouse-wheel scroll must work throughout the scrollable region.

## Card Semantics

Cards must represent durable operator concepts, not arbitrary rectangles.

### Workflow card

Show:

- worker/agent
- current bounded task
- state and age
- scope class
- previous and next handoff
- blocker or missing contract

A workflow row is not an authority hierarchy. Capacity and assignment never imply approval power.

### Learned-information card

Show:

- claim type: established fact, changed belief, inference, or unknown
- concise claim
- source count and exact source links/paths
- observed/freshness time
- confidence only when a governed producer supplies it
- operational scope: what the claim can and cannot affect

Do not label a generated summary as learned evidence unless a source and receipt support it.

### Action/receipt card

Use an explicit action vocabulary:

- `OBSERVED`
- `LEARNED`
- `PROPOSED`
- `DRAFTED`
- `TESTED`
- `EXECUTED`
- `REJECTED`
- `BLOCKED`
- `NOT ACTED`

Each row resolves to a receipt, diff, test result, approval event, or explicit not-acted state. Logs alone are not execution proof.

### Human decision boundary

Keep gated classes visible without making them visually dominant. State whether promotion, scheduler, risk, broker/order, or deployment authority was requested, granted, rejected, or absent. VOT and Telegram may both surface approvals; neither becomes exclusive.

## Tkinter Architecture

### Main-thread rule

Tk owns an event loop. Keep callbacks short and never block it with file scans, SQLite polling, subprocesses, network calls, or test runs.

Use:

```python
# worker thread: fetch immutable data
snapshot = load_snapshot()
pending.put(("snapshot", snapshot))

# Tk thread: drain and mutate widgets
root.after(150, drain_queue)
```

Only the Tk thread creates, configures, destroys, or reads mutable widget state. Background workers return plain data.

### Scheduling

- Use `after(ms, callback)` for bounded UI scheduling.
- Separate fast arithmetic/animation ticks from slow I/O refreshes.
- Track every callback ID that must be canceled during shutdown.
- Prevent overlap with an in-flight flag; timers must not spawn unbounded worker threads.
- Use direct read-only SQLite access for high-frequency Kanban observation; use audited CLI commands for mutations.

### Change-only rendering

Compute stable signatures for source data. Re-render only when the signature changes.

Preserve:

- selected card/task key
- scroll position
- active workspace/tab
- text auto-follow state
- last-good data during refresh or transient failure

Do not destroy and rebuild large widget trees on every poll. Prefer `Treeview` for large row sets and stable card pools for small bounded sets.

### Lifecycle

- Route `WM_DELETE_WINDOW` through one `close()` method.
- Mark closing before canceling callbacks.
- Cancel tracked `after()` callbacks.
- Stop accepting queue results.
- Join only short bounded workers; never freeze shutdown waiting indefinitely.
- Destroy the root once.
- On Windows `pythonw.exe`, suppress subprocess console flashes with the established `CREATE_NO_WINDOW` pattern.

## Widget Selection

Default to the standard library.

| Need | First choice | Notes |
|---|---|---|
| responsive layout | `Frame` + `grid` | weights, uniform columns, `sticky="nsew"` |
| simple bands | `Frame` + `pack` | appbar, termbar, footer |
| navigation | real `Button` or styled `ttk.Button` | visible, clickable, testable |
| large tabular data | `ttk.Treeview` | preserve selection by stable key |
| bounded cards | `Frame`/`Label` composition | shallow widget tree |
| logs/evidence text | `Text` | tags, read-only state, scroll preservation |
| custom diagrams/sparklines | `Canvas` | redraw on `<Configure>` with measured size |
| page workspaces | frame view-toggle or `ttk.Notebook` | choose one navigation model |
| resizable split | `ttk.PanedWindow` | only when operator resizing is useful |
| images/icons | `PhotoImage` or Pillow `ImageTk` | retain Python reference |

Use `ttk` when native theming and widget state machinery help. Use classic `tk` widgets where Vesper's exact dark palette or text behavior requires direct color control. Do not wrap every widget in a third-party abstraction by default.

## Prebuilt Technology Gate

Before installing or introducing a library:

1. Define the missing capability in one sentence.
2. Confirm stdlib Tk/ttk cannot meet it cleanly.
3. Check documentation, license, release recency, Windows behavior, and maintenance activity.
4. Build a throwaway spike with the exact Vesper palette, font scale, and expected row count.
5. Measure startup, resize behavior, memory stability, and packaging impact.
6. Keep the dependency only if it deletes more complexity than it adds.

Shortlist and cautions live in `references/resources.md`. Typical candidates include CustomTkinter, ttkbootstrap, pygubu, tksheet, Matplotlib's Tk canvas, Pillow ImageTk, and focused ttk themes. Treat them as options, never default requirements.

## Design-to-Production Workflow

### 1. Inspect

- Inspect the actual shortcut target, working directory, imported module, and data root.
- Read current VOT/VWM source and capture the actual running window.
- Map each panel to its authoritative source and operator question.

**Complete when:** current layout, source lineage, authority boundaries, and concrete pain points are recorded.

### 2. Reduce

Write a one-page information architecture:

- primary operator question
- page/workspace map
- cards retained, merged, moved, or removed
- gated actions and unavailable data
- minimum/default/wide geometry

**Complete when:** every proposed surface has one owner, one purpose, and one source.

### 3. Sketch

**Match the requested artifact before building anything.** If the user asks for a picture, layout draft, or visual idea "for now," deliver a rendered image only. Do not add a Tkinter prototype, README, tests, or repository files unless the user explicitly asks for an interactive prototype or implementation. Rendering source may be disposable scratch outside the repository and should not be presented as product code.

For unresolved visual direction, create 2–3 image variants with different layout stances—not cosmetic recolors. For an already clear direction, create one strong image. Label sample data. If the user explicitly requests an interactive Tkinter prototype, keep it outside production modules, compile it, launch it, capture it, and visually inspect it.

During this creative phase, defer pytest/linters until the user approves the direction or implementation is about to be committed. Picture-only work needs image inspection, not project test execution.

**Complete when:** the user received exactly the requested visual artifact and no implementation scope was added implicitly.

### Approved direction means implementation authorization

When the user explicitly approves a VOT layout or design direction, treat that approval as authorization to implement it through the intended live desktop path. Do **not** introduce a second visual-approval, freeze, or independent-review gate before beginning implementation unless a real authority-changing action requires it.

Use precise progress labels:

- **implemented** — source exists in an isolated worktree;
- **test-green** — automated checks pass;
- **integrated** — committed/reconciled into the intended branch;
- **operator-ready** — the actual desktop window was launched from its intended launcher, the approved workflow is visibly connected and usable, and the operator has not reported a live defect.

A passing test suite, shortcut target, source inspection, or headless Tk probe is not proof of operator readiness. Once the user reports a live layout as glitchy, disconnected, or unreadable, retract any readiness claim and inspect the running window before discussing release status. Do not add redundant review/freeze gates to ordinary approved UI iteration; reserve them for an integration boundary or an authority/evidence-integrity/scheduler/broker-order/risk/promotion/deployment/provider-spend/secret boundary.

### 4. Implement

Translate the approved concept into small modules: palette, fonts, appbar/navigation, workspace/card components, data adapters, and lifecycle. Reuse existing source readers. Do not create a parallel truth model merely to satisfy the layout.

**Complete when:** the production app launches with real data and no authority/source regression.

### 5. Verify

Run the verification matrix below. Repair failures before claiming completion.

**Complete when:** source-level tests, actual-window launch, screenshots, and interaction probes pass.

### 6. Handoff

Report changed files, screenshots, tests, actual command results, unresolved visual tradeoffs, and rollback version. Engineer hands off for independent review; it does not approve its own work.

When the operator asks whether a redesigned VOT is **up and running**, apply `references/native-vot-release-closure.md`. It distinguishes mockups, view-model foundations, isolated branch implementation, canonical integration, and a verified Desktop-shortcut runtime; only the final level supports an operational claim. It also provides the bounded-slice workflow and clean-commit recovery procedure for stalled coding-agent coordinators.

## Live-runtime acceptance rule

**Passing source tests, compilation, and a launcher-path check do not prove VOT is usable.** Before calling a native VOT slice ready, inspect the actual running window at the user’s current geometry and obtain explicit operator acceptance of the layout and workflow. Treat an operator report that the layout is glitchy, disconnected, or unreadable as the primary product evidence; immediately retract any readiness claim and investigate the live UI rather than defending test results.

For workflow surfaces, verify the click path end-to-end: a selected card must visibly acquire selected state, show a readable objective title/state/provenance (not a bare ID), and route the same bounded task identity into the intended detail/work surface. A static stage ribbon, a card handler that only stores local selection, or a separate detail surface that never receives that selection is a release-blocking disconnected-layout defect.

When checking a live process on Windows, distinguish a visible app window from interpreter parent/child processes before calling it a duplicate runtime. Do not kill a running VOT merely to simplify inspection.

## Visual QA Matrix

Capture and inspect at minimum:

- minimum supported window
- default window
- 1920×1080 or target desktop size
- maximum text scale
- long titles/status/source paths
- zero, one, and many cards/rows
- missing/stale/error states
- selected and unselected cards
- Workflow, Knowledge, Actions, Evidence, and Kanban/Research workspaces that changed

Check:

- no overlap, clipping, right-edge loss, or hidden action
- balanced visual weight
- primary state readable in three seconds
- no 5–7pt operational text
- wheel scroll works without visible native white scrollbars
- selection and scroll survive refresh
- no flicker when data is unchanged
- no fabricated values
- no visual cue implies authority that does not exist

## Verification Commands

Use the project interpreter and repository-local Windows pytest temp path.

```bash
python -m py_compile app/vot_tk*.py
python -c "import tkinter as tk; r=tk.Tk(); r.withdraw(); r.update(); r.destroy(); print('TK_OK')"
ruff check app/vot_tk*.py tests/test_vot*.py
pytest <targeted-vot-tests> -v --tb=short --basetemp=.pytest_tmp/vot-ui
```

Also launch the actual GUI under a bounded external timeout and capture the real HWND/window. A withdrawn-root probe cannot detect construction-time NameErrors, clipping, incorrect geometry, or launcher failures. On Windows, do not rely only on desktop screenshots when the VOT window may be occluded by another operator surface: capture the HWND with `PrintWindow` (or equivalent off-screen window capture) so visual evidence shows the VOT itself rather than overlapping desktop content.

For a mockup outside production, minimum evidence is: compile, actual launch, screenshot capture, and visual inspection. Run project tests once the direction is approved or the change is being committed.

### Isolated VOT launch probe when desktop automation is unavailable

For a narrow VOT candidate in an isolated worktree, create a temporary script
**outside the repository** that imports the candidate `VotTkApp` and creates
the actual `tk.Tk` application. The probe should install a
`report_callback_exception` collector; assert the visible title and normal
geometry; shrink below the declared minimum and assert enforcement; call
`page_shell.show()` for every `PAGE_IDS` page; select `system`; recursively
collect rendered `Label` text; assert literal boundary labels such as
`execution_authority=false`, `safe_for_planning=false`, and
`planning_safety=unavailable`; then call the application's real `close()` path.

This proves construction, navigation, minimum geometry, literal visible
fail-closed posture, zero captured Tk callback exceptions, and lifecycle while
leaving no candidate artifacts. It does not replace visible desktop-shortcut
verification when the task specifically requires the canonical launcher.

## Common Pitfalls

1. **Panel multiplication.** Adding cards without deleting or merging old surfaces recreates crowding. Set a page budget before implementation.
2. **Left-rail gravity.** Evidence, tasks, tools, and research accumulate in one rail. Move concepts to full-width workspaces and keep only true navigation/status in persistent chrome.
3. **Fake responsiveness.** A large default screenshot passes while minimum width clips. Configure weights and test all target geometries.
4. **Blocking callbacks.** Direct I/O in Tk callbacks freezes paint and input. Fetch in a worker; render in Tk.
5. **Poll rebuilds.** Destroying every widget on every tick causes flicker, lost state, and memory growth. Use signatures and stable widgets.
6. **Third-party-first design.** Installing a theme or widget suite before defining the operator problem adds dependency without reducing complexity.
7. **Mockup leakage.** Sample claims enter production. Production adapters must replace every sample value before integration.
8. **Logs mistaken for receipts.** An activity line is not proof of action. Link the actual receipt/diff/test/gate event.
9. **Detached dialogs.** Native popups break the integrated operator flow. Use inline confirmation and dedicated action surfaces.
10. **Testing the wrong layer.** When moving from Prompt Toolkit to Tkinter, do not extend old renderer tests. Test the approved Tkinter path.
11. **Unversioned UI.** Operator cannot identify the running build. Bump semantic version for coherent user-visible changes.
12. **Unreviewed dependencies.** A package demo works but packaging, license, maintenance, or Windows behavior is unknown. Apply the prebuilt technology gate.

## Verification Checklist

- [ ] Official Tkinter/ttk docs governed widget, event-loop, and geometry decisions.
- [ ] Existing VOT/VWM sources and actual running window were inspected.
- [ ] Every panel has one operator question and authoritative source.
- [ ] Layout is minimalist, balanced, responsive, and legible at 8pt or larger.
- [ ] Learned claims and acted-on events are semantically distinct.
- [ ] Gated authority remains explicit and unchanged.
- [ ] Tk callbacks do not block; widget mutation stays on the Tk thread.
- [ ] Polling uses in-flight guards, stable signatures, and state preservation.
- [ ] Any third-party dependency passed the technology gate.
- [ ] Mockup or production app compiled and launched as appropriate.
- Actual-window screenshots passed visual QA at target geometries.
- A real Tk construction regression creates representative changed-page cards and calls `root.update_idletasks()`; import/withdraw probes alone miss widget-option and geometry errors.
- Targeted tests passed before commit.
- Independent review remains pending after Engineer handoff.

## Tk Geometry and Refresh Regression Lessons

When a visual page is added or materially changed, add at least one focused test that constructs the real page with `tk.Tk()`, renders a representative non-empty projection, calls `update_idletasks()`, and always destroys the root in `finally`. This catches runtime-only Tcl validation failures that pure projections and imports cannot see. When a literal authority or evidence boundary must be operator-visible, test both the exact rendered label text and that each label's requested width fits its owning card at the default supported geometry. Split dense provenance, authority, and planning-safety metadata into separate bounded rows rather than preserving a single clipped line.

**Pitfall:** tuple spacing such as `pady=(3, 8)` belongs on the geometry manager (`widget.pack(..., pady=(3, 8))`), not on classic widget constructors such as `tk.Label(...)`. Classic Tk option parsing receives the tuple as the invalid screen-distance string `"3 8"`. Use scalar widget padding only when uniform internal padding is intended.

For refresh failures, preserve last-good evidence only behind one visible global `STALE` boundary that includes the source/reason and covers appbar values plus every page. Do not let a later success from a different source clear an unresolved stale source.

**Authority-label geometry regressions:** When an exact display-only authority contract must remain visibly legible, test the real Tk widget geometry at every declared supported size—not string presence alone. Build and pack the actual page, resize the live root for each supported geometry, call `root.update()`, locate each exact authority label, and assert both `requested_width <= actual_width` and `x + width <= containing_card_width`. Write this minimum-geometry regression before changing production layout. If the current layout passes, retain the regression and do not add a speculative UI change; if it fails, split only the clipped label row into compact bounded labels.
