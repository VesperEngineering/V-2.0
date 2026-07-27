# Native Tauri sidecar and Mission Control patterns

Use these patterns when a native Rust shell supervises a local authenticated service and a React UI renders authoritative operational state.

## Sidecar trust boundary

- Resolve one exact executable path and spawn it directly, never through a shell.
- Generate a fresh session token for every launch. Keep the token in the native layer; do not serialize it into frontend state, errors, logs, debug output, readiness objects, or persisted settings.
- Bound readiness-line collection. Validate loopback address, protocol/schema, reported PID against the spawned child, and an authenticated health response before publishing `HEALTHY`.
- Retain the exact child handle. Stop or kill only that recorded child, wait with a timeout, and reject late results after shutdown.
- Add a process-level Cargo integration target, not only fake-spawner unit tests. Launch the canonical PID-stable sidecar executable against an external temporary home, verify readiness plus authenticated health/snapshot/events, call supervisor shutdown, and assert the recorded PID disappears and public status becomes stopped. Keep the supervisor boundary publicly testable rather than duplicating private launch logic in the test.
- When the sidecar is Python on Windows, a virtual-environment launcher may redirect to a different base-interpreter PID. Preserve strict readiness PID matching: resolve the canonical base interpreter, pass the environment's import paths explicitly, and use an in-process `-c`/`runpy` bootstrap when necessary so dependency loading does not introduce a launcher child. Never relax the PID check to make the test pass.
- Use a documented rolling restart budget and backoff. Exhaustion transitions to explicit read-only recovery rather than an unbounded restart loop.

## Generation-safe proxying

- Increment a native generation whenever a new sidecar instance becomes authoritative.
- Stamp snapshot, event, and command responses with that generation.
- Capture generation before I/O and verify it again before returning data; reject a late response from a superseded sidecar.
- Cache only validated snapshots. If the sidecar is unavailable, show cached data solely under a global read-only/stale marker and reject all mutations.

## Frontend synchronization

- Load an authoritative snapshot before event polling.
- Require contiguous event sequence, matching protocol/schema, matching sidecar generation, and a non-regressing server cursor. Before comparing the returned events to `last_event_sequence`, inspect the transport contract: some APIs return a limit-bounded page plus the **journal-global** tail. Under that contract, a non-empty consecutive prefix ending before the global tail is valid pagination and must advance the cursor so the next page can be fetched. Resynchronize for an internal gap, cursor regression, generation/protocol mismatch, or an impossible **empty** page claiming a global tail ahead of the current cursor. Require a non-empty page to end exactly at `last_event_sequence` only when the protocol explicitly defines that field as the page-local tail. Add deterministic empty-ahead and valid-truncated-pagination regressions.
- On any gap or mismatch, replace state from a fresh snapshot. Never invent missing events or repair workflow state in the UI.
- Submit typed commands with UUID4 idempotency keys. Refresh from the authoritative snapshot after acceptance.
- Treat Tauri `invoke` rejection values as `unknown`: native commands can reject with a serialized `DesktopErrorV1` object rather than a JavaScript `Error`. Surface a non-empty string `message` only after shape/type validation, otherwise use a generic rejection. Add a frontend regression using the real serialized object shape, then exercise a stale-version native command: rejection must leave the item authoritative and append no event; refresh from a fresh snapshot before retrying.
- Keep drag/drop and keyboard movement on one command path. Show a pending request without moving a card optimistically; rejection must leave it in its prior authoritative column and be announced accessibly.
- For `dnd-kit`, configure pointer activation deliberately (for example an 8-pixel distance), use `KeyboardSensor` with `sortableKeyboardCoordinates`, attach the product's exact screen-reader instructions to `DndContext`, and publish accepted/rejected/canceled copy in an `aria-live="assertive"` region. A nominal sensor import is not evidence: test the rendered instructions, keyboard parity/cancellation, pointer target mapping, and the actual live-region politeness.
- Do not replace the sortable listener's `onKeyDown` with a manual keyboard state machine. Spreading `{...listeners}` and then assigning `onKeyDown` silently disables `KeyboardSensor` activation and leaves `sortableKeyboardCoordinates` unused. Prefer the sensor lifecycle directly; if supplemental behavior is unavoidable, compose rather than replace the listener and prove one controller request per completed drop.
- Exercise the actual keyboard sensor in tests: send a native-code `Space` keydown to the focused activator, wait for dnd-kit's own `role="status"` pickup announcement (the sensor installs its document listener asynchronously), then send arrow/drop/cancel keydowns to `document`. Compact synthetic key sequences can outrun listener installation and accidentally test only custom code.
- `sortableKeyboardCoordinates` depends on measured droppable rectangles. JSDOM reports zero geometry, so movement tests must supply deterministic `getBoundingClientRect` values for cards and `column:<STATE>` droppables; otherwise activation/cancellation may pass while adjacent-column movement is never exercised. Restore geometry spies after every test.
- Pointer tests must respect the configured activation constraint. With a distance constraint, the first `pointermove` beyond the threshold can activate the sensor without yet updating collision state; send a second movement event, wait for dnd-kit's live region to announce the intended droppable, and only then release. Dropping immediately after the activation move can falsely report a drop over the active card and never exercise controller target mapping.
- Read-only recovery must disable every drag handle and short-circuit both pointer and keyboard transition handlers. Test the disabled controls and zero controller calls; a disabled-looking button without a handler guard is insufficient.
- Treat transition rejection as `unknown` just like other Tauri invokes. Shape-check a serialized native error object's non-empty `message` before falling back, and test with an object rather than only `new Error(...)`.

## Native lifecycle authority

- Keep ordinary frontend workflow commands and native process lifecycle commands on different allowlists. React may request a typed lifecycle action, but Rust constructs the sidecar command envelope.
- Pause/resume/stop must read the current authoritative Factory version immediately before submission and use a fresh UUID4 idempotency key. Resume is valid only after an authoritative paused snapshot.
- Stop records the Factory stop command first, asks each registered runtime boundary to stop within a fixed deadline, then terminates only the reported remainder. A Plan-2-style placeholder should be an explicit no-op participant returning zero counts, not an unimplemented process adapter.
- Quit follows stop sequencing, shuts down only the recorded sidecar child, marks an atomic explicit-quit flag, and then exits. If the sidecar is degraded, report that no Factory command was recorded; never fabricate a receipt, but still perform bounded local cleanup.
- Prevent ordinary window-close and run-loop exit requests while explicit quit is false. Close hides the main window; tray open or double-click shows and focuses it. Register managed lifecycle state before constructing tray handlers.
- Derive tray priority from live native status and authoritative snapshot data, with deterministic precedence such as degraded, attention, paused, running. Do not initialize a state-specific label from an assumed startup mode.

## Notification privacy and deduplication

- React forwards only newly significant unacknowledged HIGH/CRITICAL attention identities. Keep **in-flight** and **delivered** state separate: an in-flight marker prevents duplicate calls during rerenders, but it is not delivery evidence. Advance delivered state only after the native Promise resolves to `SENT` or `DEDUPLICATED`. Clearing an in-flight ref after rejection or `PERMISSION_DENIED` is not enough when `items` and `notify` identities remain stable—the effect will not rerun. Schedule an explicit rate-bounded, finite retry/re-evaluation keyed by attention identity, severity, and occurrence count; cancel its timer on unmount and clear its retry marker after success. Test with stable item/notifier identities, make the retry fail, advance beyond the retry window, and prove there is no third attempt.
- A single `(max severity, max occurrence count)` pair is insufficient even when both fields use `max`. It loses per-severity progress: `HIGH(5) → CRITICAL(1) → CRITICAL(2)` must deliver all three, while `HIGH(5) → CRITICAL(1) → HIGH(5)` must suppress the final duplicate. Retain the highest delivered severity plus the highest successfully delivered occurrence count **for each severity rank** (or an equivalent Pareto frontier). Deduplicate only when the request neither escalates severity nor advances the delivered count at its current severity. Keep both sequences as deterministic Rust and frontend regressions.
- Rust remains the final policy authority even if React calls incorrectly: skip routine severities, deduplicate by attention identity plus count/severity, and return an explicit outcome.
- Native notification bodies contain only a stable attention kind and product name. Never include causal reason, receipt, path, token, raw payload, or diagnostic details.
- Record deduplication state only after the operating-system notification sink succeeds; permission denial must not masquerade as delivery.
- Verify native delivery with a disposable canonical attention record, not a frontend mock. On Windows, Do Not Disturb can suppress the transient banner while still accepting the notification into Notification Center; use the taskbar's current notification-button accessible name (which may include a changing new-notification count), capture only the notification-center region, and confirm the safe product title/body. Keep unrelated notification contents out of retained evidence.
- Hold the app through several unchanged polling cycles and prove only one product card remains. A higher occurrence count or severity escalation is expected to notify again; unchanged identity/count/severity is not. If notification-card text is absent from UIA, treat UIA counting as inconclusive and use two bounded before/after panel captures rather than claiming deduplication from an empty accessibility query.

## Contract-driven operator surfaces

- Correct tests and implementations to the frozen transport/schema types before adding UI-only fields. If a requested preference is absent from the contract, display controller ownership rather than inventing a payload field.
- Render proposal hashes, stages, dependencies, reservations, dossier entries, collision facts, and recovery status directly from authoritative responses. Local wizard state is only a draft until the controller returns a proposal.
- Do not equate an audit-retained array length with an active/open count. For attention and similar records, derive visibility/counts from the authoritative acknowledgement/status field; successful acknowledgement may retain the record with timestamp/version while removing it from the operator's unacknowledged view.
- Numeric fields that permit `clear → type` must preserve an empty editing string while deriving a separately clamped schema value. Immediately coercing empty input to the minimum causes typed digits to append to the reinserted minimum.

## Deterministic React tests

- If the host may export `NODE_ENV=production`, set `process.env.NODE_ENV = "test"` in the Vitest `setupFiles` entry before importing React Testing Library. This avoids loading React's production build without `act` while keeping the repository test command deterministic.
- Await async controller completion or a visible live-region result so React state updates remain inside the test's `act` boundary.
- Test gaps, generation changes, protocol mismatches, server regression, read-only mutation denial, rejected transitions, and absence of optimistic movement.

## Development-shell preflight and isolation

Before treating `tauri dev` as a smoke test:

- Compare the configured `build.devUrl` with the Vite/dev-server host and port. Start the frontend once and verify its actual reported URL matches exactly. If Tauri waits for one port while Vite selected another, stop immediately and repair the configuration; do not mistake the wait loop for native startup evidence.
- Make the frontend port explicit and fail closed (`strictPort` or the equivalent) so a busy port cannot silently move the server away from the URL Tauri is polling.
- On Windows, exclude the Rust build tree (for example `**/src-tauri/target/**`) from Vite's watcher. Native DLLs can remain locked while Cargo/Tauri is running; watching them can terminate an otherwise valid development shell with `EBUSY`.
- Before each retry, inventory the exact dev-server port owner and command line. A terminated Tauri parent can leave a Vite/Node child behind. Kill only a confirmed child from the current worktree, then prove the configured IPv4/IPv6 loopback port can be rebound; never blanket-kill all Node, Python, or desktop processes.
- Redirect platform-local application data to a disposable worktree-owned root for the smoke process. Derive the exact sidecar home from the application code rather than assuming the framework always appends the application identifier: code that reads `LOCALAPPDATA` directly may append only its own product suffix, while a native Known Folder resolver may behave differently. Initialize and inspect that exact derived home before launch. Never point a development smoke test at the operator's real local Factory/database state.
- Resolve the real sidecar interpreter/executable and inspect the supervisor's child-environment policy. If the child inherits environment, pass only the import/runtime paths needed by the fixture; if it clears environment, explicitly whitelist those paths. Do not assume either behavior.
- When readiness binds the reported PID to the spawned child, probe the candidate executable independently and compare `spawn_pid` with `ready_pid`. On Windows, a virtual-environment `python.exe` may be a redirector that launches the real interpreter under another PID. UV may also expose an unversioned interpreter directory as a reparse alias to the concrete patch-version directory; canonicalize through to the final versioned executable when launch policy rejects reparse components. Use a PID-stable underlying interpreter/executable only if it also passes the product's canonical-path, regular-file, and reparse-point policy; never weaken readiness PID validation to accommodate a launcher shim.
- Adding a venv's `Lib/site-packages` directory to `PYTHONPATH` does **not** reproduce venv startup: Python does not process that directory's `.pth` files merely because it appears on `PYTHONPATH`. Packages such as pywin32 can then fail before readiness because their auxiliary `win32`, `win32/lib`, `pythonwin`, or `pywin32_system32` paths/bootstrap were never activated. Probe the canonical interpreter with the real sidecar command and visible stderr first. Then either include every required auxiliary directory explicitly or launch one PID-stable Python process with an in-process bootstrap that calls `site.addsitedir(venv_site_packages)` before `runpy.run_path(...)`; do not add a shell/venv wrapper that changes the readiness PID.
- If a development override is needed, scope it to development mode and fail closed: require the sidecar override, absolute existing canonical paths, the correct file/directory type, and reparse-point policy. Reject orphaned home/argument overrides. If resolution still fails, identify the exact failed predicate before changing policy.
- Start the development shell as a managed long-lived process. Require separate evidence for frontend readiness, native compilation, visible window creation, sidecar readiness/authenticated health, and eventual child cleanup; one signal does not prove the others.
- Keep disposable homes, budgets, databases, and logs outside the candidate diff and remove them after verification.

## Live-fixture verification without startup side effects

- Treat application-kernel construction as potentially mutating even when the immediate caller only intends to call `snapshot()`. Constructors/openers may migrate schema, reconcile abandoned attempts, revoke leases, or reset a formerly running system to a fail-closed mode.
- While a sidecar owns the live fixture, prefer its authenticated health/snapshot/events interfaces. Keep authentication inside the native boundary: do not scrape the token from process environments or expose it to React merely to simplify verification.
- If an external probe cannot authenticate by design, use a storage interface that is structurally read-only—for SQLite, a read-only URI/connection and direct bounded projections—or add a dedicated token-free native diagnostic command returning already-sanitized status. Never call the production kernel opener from the probe.
- A suspicious signature is `mode/state changed` while the event cursor did not advance. Before filing a product defect, determine whether a second process ran startup reconciliation. Restore state only through the real native authority and then verify through that same authority.
- Accessibility automation proves only delivery mechanics. `SetFocus`, `Invoke`, or a key-sender returning success does not prove that a WebView sensor activated or that a controller accepted a mutation. Require a visible live-region/destination result and an authoritative post-command snapshot or event. If platform security blocks low-level input synthesis, do not bypass it; use a supported automation rung or report that sub-gate separately.

## Native acceptance evidence

Frontend tests and `cargo test` are necessary but not sufficient. Before release, run the actual development Tauri shell against a real local sidecar and capture evidence for launch, readiness, authenticated health, snapshot/event rendering, command rejection/acceptance, restart, recovery, close-to-tray, stop, quit, and child-process cleanup.

After a sidecar restart, verify every operator-facing native status surface—not only the Factory snapshot—updates to the new generation, child PID, restart count, health timestamp, and error state. A board that resynchronized while Settings still displays a dead PID is a release-blocking stale-authority defect. Refresh native status on both generation changes and same-generation authority transitions such as `read_only: false → true` or a host-state transition into recovery. Add separate regressions for generation replacement and same-generation recovery.

## Restart and recovery smoke

- A rolling restart budget is time-based, not an all-session counter. Record the current-window attempt count and timestamps before the test, then force all intended failures inside one budget window. A later successful restart can be correct when an older attempt has aged out; do not label it an off-by-one failure from total historical kills.
- A failed relaunch must consume an attempt and continue through the same bounded delay/budget state machine. Leaving the host indefinitely in `RESTARTING` because the next health probe runs only in `HEALTHY` is a release blocker. Add a fake-spawner regression that fails every launch, proves exactly the allowed attempts occur, then observes `READ_ONLY_RECOVERY` and mutation denial.
- On budget exhaustion, atomically enter read-only recovery, clear client/readiness, take the recorded process handle out of supervisor state, and terminate/wait it with a bound before returning. Public recovery status must not expose the PID of a dead or unreaped child.
- Verify both cached and no-cache recovery: cached authoritative data remains visible only under a global stale/read-only marker; no-cache recovery renders an explicit unavailable panel. Disable every workflow/lifecycle mutation in read-only recovery—including task transitions and Factory Stop—in both visible controls and execution handlers. Keep only explicit Quit available for bounded local process cleanup, without claiming or recording a sidecar mutation.

## Authority-derived lifecycle controls

- Derive frontend and tray dispatch controls from the same authoritative mode and availability rule. A safe mapping is `RUNNING → Pause`, `PAUSED → Resume`, `STOPPED → disabled “Dispatch stopped”`, and `degraded/read-only/no-snapshot → disabled “Dispatch unavailable”`.
- Do not implement tray dispatch as “paused means resume, otherwise pause”; STOPPED and unavailable states would incorrectly fall through to Pause. Use one pure mapping for both the displayed label/enabled state and the action callback, and return without dispatch when the mapping has no action.
- Distinguish Stop from Quit in process evidence. Stop can leave the observation sidecar healthy so the stopped state remains inspectable; only explicit Quit must stop the sidecar and prove no desktop or sidecar orphan remains.

## Windows notification-area verification

A native tray implementation is not accepted from Rust unit tests or main-window visibility alone. Exercise the real Windows notification-area icon and retain evidence for every state-changing menu action.

- Enumerate the taskbar UIA tree and invoke the notification overflow through the button whose name starts with `Show Hidden Icons`; Windows may expose the open state as `Show Hidden Icons Hide`, so do not require one exact name. When the open-state element and product icon already exist, do not invoke the collapsed-state control again.
- Notification Center/Calendar and the hidden-icons overflow can overlap while UIA still reports stale underlying icon bounds. Before any coordinate-backed tray action, capture the scoped taskbar/notification quadrant and prove the product icon is visibly unobstructed. If another shell panel is intercepting input, dismiss it with one bounded click in a known inert application region, then freshly enumerate the overflow/icon and require the context menu to be visibly open before selecting an item.
- Locate the product icon by `AutomationId=NotifyItemIcon` plus a stable product/state suffix. Windows can prefix its accessible name with a decorative glyph, so do not anchor matching to a presumed leading space.
- Read tooltip state and menu labels from UIA when available. If a native context menu is not exposed, capture only the notification-area quadrant and verify the visible labels and disabled styling from pixels.
- Prefer background computer-use delivery. If that transport is unavailable and a bounded native smoke must use coordinates, first derive the icon/menu coordinates from UIA or a scoped taskbar capture and preserve the physical cursor position. For tray right-click, allow a bounded 300–500 ms dwell over the icon after mouse-up before restoring the cursor: some native popup handlers anchor asynchronously, and immediate restoration can produce a verified no-op. Perform only the required click/double-click/right-click, restore the cursor after that bounded dwell, and verify the result from fresh UIA/pixels. Retry at most once after a visually confirmed no-op; never use guessed coordinates or broad desktop capture.
- For close-to-tray, issue a real native close request, prove the window becomes hidden while the exact desktop and sidecar PIDs remain alive, then double-click the real icon and prove the same HWND becomes visible again.
- Exercise menu Resume, Pause, and Stop against authoritative UI state. Verify both tooltip and dispatch menu relabeling. A four-level alert priority (`degraded → attention → paused → running`) does not justify labeling a terminal Factory mode as Running: preserve alert priority, but derive a truthful `Stopped` tooltip when no higher alert overrides it.
- Before Quit, prove STOPPED/degraded dispatch is disabled while Quit remains enabled. Invoke the real Quit menu item, then boundedly poll exact command-line-scoped desktop, supervised sidecar, and development-server processes until absent. Also confirm the managed development wrapper exits; never infer cleanup from a missing window or blanket-kill unrelated processes.

## Hot-reload attribution

During `tauri dev`, a Rust source edit can make the native watcher rebuild and replace the desktop and sidecar while Vite remains on the same port. Before attributing a click, screenshot, PID query, tray action, or cleanup result after any edit/build, recapture the desktop PID, exact child PID/parent relation, window handle, and visible mode. Treat old process/window identities as stale evidence rather than assuming the original session survived.

Generated `target/` output is build evidence, not authored source.
