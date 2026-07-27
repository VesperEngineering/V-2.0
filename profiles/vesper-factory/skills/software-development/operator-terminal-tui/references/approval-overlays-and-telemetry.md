# Approval overlays and telemetry verification

## Governed queue pattern

For a governed operator terminal, do not make Issues or Approvals controls a renderer-only mock. Load bounded rows into the immutable terminal snapshot and keep rendering pure: the renderer consumes snapshot plus controller-owned focus/selection state rather than reading or writing ledgers directly.

Two valid interaction shapes exist:

- **Overlay-first:** a stable shortcut opens a detail overlay.
- **Embedded-card-first:** equal always-visible Issues and Approvals cards sit in the main canvas. Use `Tab` or left/right for focus, up/down for selection, and Enter to open visible issue/approval detail. A second overlay action performs the issue start or approval decision. Do not retain a redundant shortcut such as `V` when the operator explicitly chose the visible card as the primary path.

Keep separate stable IDs for issue selection, approval selection, and any open overlay. Refreshes should retain each selection when its row still exists. In a single `FormattedTextControl` canvas, keyboard focus is logical controller state—not Prompt Toolkit widget focus—and every redraw must receive that state explicitly. Opening a governed overlay must normalize its selection, call the application invalidation/redraw hook, and return before any mutation; only a later input may act. Enforce the same boundary inside controller/domain mutation methods, not only key dispatch, and test direct method calls with no overlay to prove they remain no-ops.

Wire approval actions to the existing approval service, not a second UI-specific policy:

- `A/R/E` while the embedded Approvals card is focused opens the visible exact-scope review overlay and performs no mutation
- `A` inside the visible approval overlay → approve the selected request
- `R` inside the visible approval overlay → reject the selected request
- `E` inside the visible approval overlay → invoke the separately gated execution consumer, which may still fail closed
- record the exact-scope decision separately from execution authority
- an environment/CLI identity is an actor label, not authentication; `approval_granted=true` is valid only when the schema defines it as decision status and no consumer treats it as authenticated authority
- if `approval_granted` is authority-bearing, keep it false until a trusted principal binding exists
- treat authority booleans as serialization/replay invariants: while authenticated grants are unavailable, write both flags as false and reject ledger events that claim true, even when the immutable request hash still validates
- execution remains independently closed until authenticated identity and every current authority gate pass
- the identity label must be explicitly configured and loaded by the real launcher; absent identity fails closed
- service enforces principal allowlist, separation of duties, expiry, exact scope, and one-shot execution

The dashboard may show controls when identity is absent, but must not mutate the ledger. Use a clear message such as `VOT identity is not configured`.

### Minimum review geometry

Separate field-length caps do not prove that a request is reviewable. Compute the actual fixed-row cost (header, labels, identity/timestamps, authority warning, status, footer), subtract it from the **minimum supported overlay height**, then validate the combined action/scope/reason row count with the renderer's exact wrapping policy. For the VOT `80×19` detail surface, 10 rows are fixed and labeled values have 68 usable columns, leaving 9 combined wrapped rows. Recompute these constants whenever geometry or labels change; do not cargo-cult them into another layout.

Validate this invariant before the first ledger append and again during replay. Reject an oversized request before writing anything. The boundary test must render the complete action, scope, reason, authority warning, status message, and decision footer within the minimum width/height. Validation and rendering must use one shared wrapper that counts terminal display columns (for example Prompt Toolkit/wcwidth semantics), not Python code points; wide CJK/emoji can occupy two columns. Prefer deterministic column chunking when exact preservation matters. If word-aware wrapping is retained, invoke the identical routine on both paths and test whitespace patterns that leave rows partially filled. Validate the **raw** value before `.strip()` or other normalization: leading/trailing tabs, CR/LF, escape/control characters, and embedded controls must fail before any ledger/checkpoint write, while ordinary surrounding ASCII spaces may be normalized deliberately. For decisions, assert rejected raw controls leave existing evidence bytes unchanged. If a design chooses scrolling instead, decisions must remain unavailable until the complete review has been traversed; merely truncating `rows[:height]` is not an exact-scope gate.

### Complete-event integrity

A request hash protects only request fields. Decision metadata remains mutable unless every serialized event is bound. Store a unique event ID, the previous event hash (empty only for genesis), and a deterministic hash of the complete canonical event excluding its own hash. Before replay **or append**, validate every event hash and the entire previous-hash chain; fail closed on malformed data. Keep request-field hashing as a separate exact-scope invariant.

A hash chain alone accepts any valid prefix, so deleting the final decision event can silently return an approval to `requested`. Persist a separate durable checkpoint with the verified `event_count` and `head_hash` (optionally self-hashed for corruption detection). Append and flush/fsync the event first, then atomically replace the checkpoint; replay must require the checkpoint and match both values. A crash between append and checkpoint should leave evidence unavailable/fail-closed rather than self-healing silently. Regression fixtures should change event kind, status, decision actor/time/reason, and authority booleans without updating the hash; delete the head or tail while leaving the checkpoint; remove the checkpoint; and reorder events. Every case must reject replay. This is local evidence-integrity detection, not proof of authenticated identity: a local actor label and recomputable hashes still do not grant execution authority.

For Issues, Enter may atomically mark the exact registry section in progress. A progress bar must consume a bounded source field such as `Progress: N%`. Only initialize `0%` when the action actually transitions a not-started issue into progress; an already-active issue with no progress field remains `not reported` and must not be rewritten to a persuasive zero. Preserve subsequent producer updates and display the registry's authoritative `Owner` beside the bar. Never infer progress or ownership from prose, status labels, controller focus, lane ownership, or a delegation event.

## Telemetry source distinctions

Keep these metrics visibly distinct:

- **Launch delta**: new tokens observed since the terminal/controller started; can remain flat without new source events. The first discovery establishes baselines for existing sessions, but a genuinely new session first seen after launch must start from zero so a short-lived run is not discarded.
- **Cumulative total**: sum each unique stable session ID once across discovered rollout files. Deduplicate repeated/rolled-back files before both cumulative sums and launch-delta baselines; otherwise a brand-new tracker can report a large false launch delta.
- **Provider aggregate**: OpenRouter activity endpoint totals; this is not a streaming feed and should display today's spend, the API-returned account total, token count, request count, observation time, and a rate only when elapsed samples support it. Read the opt-in flag from the same ignored local configuration source as the management key. Validate the provider envelope before aggregating: `data` must be a list of mapping rows, not `null`, a mapping, or another iterable. Validate every usage/count field as finite and nonnegative, and reject fractional request/token counts rather than truncating or coercing malformed values to zero. Then validate aggregate sums and derived rates too: individually finite rows can overflow while summing, and a finite usage delta can overflow when scaled to an hourly rate. Malformed data at any stage is a failed observation—preserve the exact last good sanitized snapshot, label both usage and any derived reconciliation `STALE`, and never overwrite a nonzero cache with fresh-looking zero or infinity.
- **Provider reconciliation**: show the API-returned account aggregate, receipt-attributed Vesper usage, and unattributed usage as separate labels. Do not imply that an account total is all-time or Vesper-owned unless the provider contract and receipt lineage prove those claims. A stale account total may remain visible as last-good evidence, but pass `None`/unknown into current attribution arithmetic so old spend cannot manufacture a current unattributed value; render `unattributed unknown` and preserve the stale label. Verify the explicit account-total and reconciliation labels at compact, two-column, and wide viewport sizes.
- **Provider accounting lifecycle**: load account telemetry independently from Steward/autonomous-worker state. Missing worker coordination data must not hide provider spend.
- **Worker lifecycle**: `RUNNING`, `PENDING`, `IDLE`, etc. from structured activity events; a `delegated` event is pending work, not proof that the worker is active.

Do not display `$0.00/hr` when the sample interval is too short to estimate a rate. Say `rate unavailable` and show the observation timestamp instead. Label cumulative Codex totals as indexed/session totals so they are not confused with launch usage or billable provider spend.

## Verification loop

1. Add controller regressions with temporary issue and approval ledgers plus a snapshot containing both row types.
2. For embedded cards, verify logical focus moves with Tab/left/right, each queue retains its own stable selection across refresh, Enter starts the selected issue or opens exact approval detail, and no superseded `V` shortcut remains. Repeat at wide, three-column, compact, and short-height viewports. If the focused card or selected row is absent, truncated, or hard-clipped, mutation shortcuts must be inactive and exact-scope approval must require a full detail overlay.
3. Verify `A/R/E` route through the governed service only while Approvals is focused. Approval records the exact decision; if the schema exposes `approval_granted=true`, prove that no consumer interprets it as authenticated execution authority and that execution remains independently closed.
4. Verify missing identity-label and self-approval fail closed without writing a decision. Exercise the real launcher's ignored-local-config loading path for the allowlisted identity name, and separately prove that the label cannot authenticate an execute/apply path.
5. Verify issue progress parses only bounded `0..100%` evidence, initializes at `0%` on first start, preserves later updates, exposes the source-backed owner, and never fabricates a percentage or worker when absent.
6. Verify telemetry unit tests for initial launch baselines, sessions first appearing after launch, duplicate rollout/session IDs, cumulative totals, OpenRouter `.env` opt-in, strict envelope/row/numeric rejection, last-good cache preservation, stale reconciliation labeling, explicit today/account-total/attributed/unattributed formatting, and independence from Steward state. Probe provider labels at compact, two-column, and wide viewport sizes.
7. Run focused controller, action-registry, layout, hardening, approval, Codex, OpenRouter, and status suites with an external writable pytest basetemp.
8. Run `py_compile`, scoped lint, a pure render probe at the actual cell grid, and `git diff --check`.
9. Enumerate live TUI child processes before visual acceptance. Retire stale copies launched by the wrong interpreter, relaunch exactly one authoritative process, and inspect a fresh screenshot.
10. If a full-suite run times out or contains unrelated failures, report the focused green boundary separately; never claim the full suite or live UI is green.
