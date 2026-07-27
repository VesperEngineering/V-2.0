---
name: external-side-effect-safety
description: "Design and adversarially verify fail-closed integrations that combine remote mutations with local persistence."
version: 1.9.1
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [safety, idempotency, reconciliation, transactions, concurrency, external-api]
    related_skills: [requesting-code-review, systematic-debugging, test-driven-development]
---

# External Side-Effect Safety

Use for brokers, payments, production control APIs, smart devices, deployment systems, or any workflow where a remote mutation must agree with durable local state.

## Principles

- Fail closed at every mutation boundary, including cleanup, cancellation, liquidation, and shutdown.
- Persist a unique intent before remote mutation; treat ambiguous outcomes as unknown.
- Atomically reserve every scarce limit consumed by pending effects (cash, slots, inventory, quota) in the same transaction that creates the intent.
- Keep reservations through pending, unknown, partial, and locally-open states until authoritative remote reconciliation or verified-flat cleanup releases them; remote balance/position snapshots may lag.
- Reconcile only responses whose remote identity and idempotency key match exactly.
- Run reconciliation at startup and periodically; unresolved intents gate new mutations without disabling monitoring and recovery workers.
- Close the mutation gate before reconciliation starts and keep one shared lock across its remote snapshot, local updates, and result publication; this serializes reconciliation with submissions, compensation, verified-flat cleanup, and EOD latches. Exceptions leave the gate closed. In asyncio systems, run the entire lock-held synchronous critical section in a worker thread—never acquire a `threading.Lock` on the event-loop thread and then await.
- Validate untrusted cache/API/config data by exact type and domain grammar rather than coercing values into plausible shapes. Numeric parsing must classify `TypeError`, `ValueError`, and `OverflowError` as malformed input; exercise booleans, fractions, NaN/infinity, negatives, and integers too large for `float()`. A malformed live observation must retain the exact last-good stale cache rather than escape the source boundary or overwrite it with zero.
- Model partial effects explicitly; cancellation does not imply zero exposure.
- Require exact local row effects and non-masking resource cleanup.
- Serialize shared state transitions and supervise critical workers.
- Make additive migrations repeat-safe and concurrency-safe.
- Keep external execution disabled throughout tests and review unless the user explicitly authorizes a controlled smoke test.
- Protect singleton ingress and mutation authority with a process-lifetime OS file lock; acquire it before recovery or network startup and release it in `finally`.
- Verify exact remote account identity before every cleanup mutation, then cancel and liquidate only assets attributable to durable local ownership; account-wide cleanup is unsafe even on a nominally dedicated account.

## Workflow

1. Enumerate every remote-mutating path and its local-state transition.
2. Define invariants for identity, idempotency, uncertainty, partial effects, and compensation.
3. For POST/submit calls, treat timeout, connection reset, malformed response, and read-after-write failure as `unknown`; the remote mutation may already have succeeded.
4. Derive a deterministic client/idempotency key from the immutable mutation envelope. Reconcile by that exact key before allowing any retry; never relabel uncertain outcome as confirmed no-effect.
5. Classify reconciliation as confirmed effect, provider-proven safe absence, or unresolved unknown. Unknown must block duplicate mutation and remain visible in durable evidence.
6. Write adversarial tests before fixes: post-acceptance timeout, reconciliation success, reconciliation failure, malformed reconciliation payload, and exactly-one-POST behavior.
7. Implement the smallest invariant-preserving change.
8. Exercise connect/insert/commit/update/close failures and malformed remote states.
9. Run the project suite and a focused direct probe.
10. Send the exact unified diff—not a prose summary—to a fresh independent fail-closed reviewer. Pin and report the reviewed commit SHA; any subsequent edit, fixup, or rebase invalidates that verdict and requires a new review of the new SHA.
11. For safety-critical changes, continue focused fix/review cycles until security and logic errors are empty; escalate only on churn, conflicting requirements, or a concrete blocker.
12. Treat a pending asynchronous safety review as a barrier for every source-bound descendant proof. If a late HOLD arrives after a canary, receipt, one-shot schedule, or dashboard projection was produced, preserve those artifacts as historical but mark them held/superseded, withdraw positive projections, disable stale schedules/wrappers, repair with TDD, and rerun the complete descendant chain from the approved successor SHA. See [references/late-review-proof-invalidation.md](references/late-review-proof-invalidation.md).

## Evidence Receipt Pipelines and Source Reconciliation

For guarded workflows, treat evidence production as part of the control boundary—not as reporting after the fact.

1. Map every consumer-required receipt to an explicit upstream producer and schedule it in dependency order.
2. Require each receipt to prove its source artifact, source date, freshness, universe, and execution scope; do not accept a bare `STATUS: PASS` as sufficient evidence.
3. Reconcile candidate evidence to the model and portfolio-selection path that actually runs in production. Do not let a legacy model/report generator satisfy a live pipeline's candidate gate merely because its schema validates.
4. Add source-date and artifact-identity checks between factor scores, baskets, candidate reports, and pretrade envelopes.
5. Keep evidence validity separate from execution authorization: a candidate receipt may be `PASS` while its internal decision remains `hold for review` or `no action`; those states must not reach preflight or any remote GET/POST. A generic scheduler must not transform evidence into mutation authority. Require a separately governed, exact mutation intent and route non-preview execution through the authoritative intent loop.
6. After repairing a missing producer, run the full consumer loop in no-submit mode and verify `First failed step: none`, not just the individual producer scripts.
7. Schedule read-only broker/account observations and their validators as first-class pipeline stages so a green state is reproducible on the next run.
8. For Windows Scheduler mutation lanes, prove the unattended path with the exact task action, a guarded dry run, one explicitly authorized real smoke trigger, the wrapper log, the resulting receipt, and immediate read-only broker reconciliation. `Status: Ready` and `schtasks /run` success are scheduler-level facts, not execution proof. Keep scheduled surfaces preview/reconciliation-only unless exact scheduler mutation authority is separately granted.
9. Ensure candidate selection, low-level execution guards, and post-order evidence readers derive scope from the same current admitted receipt, but do not let candidate membership widen the board-approved mutation envelope. Preserve any explicitly approved symbol/side/notional restriction until a dated authority artifact changes it; test an otherwise-valid out-of-envelope candidate and prove zero remote calls.
10. Intraday redundancy must be reconciliation-first, not repeated independent mutation. Use a deterministic daily intent plus an immutable one-effect-per-day envelope latch. Hold one process-level lock across prior-receipt inspection, exact-key reconciliation, optional POST, semantic response validation, and durable receipt publication; deterministic IDs alone do not prevent concurrent different-envelope effects.
11. Bind scheduled mutation dates to the current trading date in the market timezone before selecting receipt paths or idempotency keys. Caller-controlled historical/future dates must not create a parallel daily namespace.
12. A prior `ORDER_STATUS_UNKNOWN` may trigger exact-key GET reconciliation in later windows, but an absent or still-ambiguous result must never fall through to POST. Only exact remote identity matching may reopen the accepted/reconciled path. Likewise, HTTP 200 is not semantic acceptance: require valid JSON plus exact idempotency key and immutable envelope fields.
13. Schedule GET-only post-effect monitors shortly after mutation/recovery windows. Before any remote read, validate same-day scope, accepted submission truth, and exact preflight/submission envelope equality. Enforce those checks inside every network-capable helper itself, not only in its scheduler or caller: direct CLI/library invocation must reject stale dates and out-of-envelope symbol/side/notional before the first account, order, or position GET. Query fills by the deterministic remote identity—not "latest item for symbol"—and require exact key/date/symbol/side/amount matching before position or portfolio reads. Put all accepted lifecycle statuses in one shared predicate used by loops, monitors, evidence producers, and validators. Bare `STATUS: PASS` or an expected-but-missing receipt is an integrity failure and must propagate a nonzero scheduler result.
14. On Windows batch wrappers, use delayed expansion (`setlocal EnableDelayedExpansion` and `!ERRORLEVEL!`/`!EXIT_CODE!`) when reading exit codes inside parenthesized blocks; otherwise logs can record a blank or stale value even while Task Scheduler correctly reports failure.

See [references/evidence-pipeline-reconciliation.md](references/evidence-pipeline-reconciliation.md) for the receipt map, source-alignment checks, and verification sequence. See [references/windows-paper-submit-verification.md](references/windows-paper-submit-verification.md) for Windows task smoke tests, network-capable logon selection, immutable-runtime ACL gates, and production-only failure patterns.

## Guarded Market-Data Refresh and Recheck

Use this sequence when an explicitly approved refresh may make remote market-data GETs and write a local operational cache:

1. **Bind the approved source before network access.** Record the configured active provider identity, database/cache destination, expected latest completed market session, symbol/universe count, and exact missing-session window. Do not let a newer non-active store or a differently named evidence source substitute for the active source.
2. **Run a read-only plan and credential-presence preflight first.** Require `refresh_required`, a bounded request range, and required credential *names* only. Never print values, headers, URLs containing secrets, or environment-file contents.
3. **Use the narrow provider entrypoint only.** It must be fixed to market-data endpoints and the approved local cache; reject broker/account/order endpoints, source switching, scheduler mutation, and broad catch-up helpers that can exceed the approved scope.
4. **Treat the refresh result as uncertain unless it proves validation and commit.** Capture requested versus inserted rows, date range, symbol count, provider identity, validation result, transaction result, and post-write coverage. On timeout, malformed response, failed validation, failed commit, or an incomplete post-write readback, stop and reconcile the local cache before any retry.
5. **Replan read-only after the write.** Require `fresh`, zero missing rows, and the expected latest session across the full active universe. Then run the project’s no-network actionability receipt and structural validator from the canonical checkout.
6. **Keep freshness domains distinct in the final evidence.** Report active OHLCV/cache freshness, macro-cache freshness, and any legacy/non-active operator-data source separately. A fresh active source does not make a distinct macro or legacy evidence gate green; a stale non-active source does not authorize switching the active source.
7. **Persist bounded, redacted evidence.** Store the standard post-refresh/actionability receipts when available; otherwise record a bounded task receipt. Include checksums for the final evidence artifacts and commit only the narrow tracker/source-of-truth update. Do not push unless separately authorized.

### Pitfalls

- A successful no-network structural validator can validate receipt shape while the underlying data decision remains fail-closed; read both the validator and the actionability decision.
- Do not describe a stale macro cache as a stale active OHLCV source, or vice versa. Verify each receipt’s declared provider and admission surface before summarizing.
- A `fresh` active-refresh plan means a second refresh is not actionable. It is not authority to proceed to paper-order or live execution.
- A descriptive tracker pointer must not be made parseable by weakening task-date/scope gates. Preserve a canonical, date-valid task identifier separately from explanatory prose.

For the Vesper active-OHLCV/macro/Massive source-identity map, approved command boundaries, and receipt sequence, see [references/vesper-data-freshness-refresh.md](references/vesper-data-freshness-refresh.md).

## Paper-Order Crash Recovery and Exact Identity

For durable staged order lifecycles (`PREPARED` → `POSTING` → `ACCEPTED` / `UNKNOWN` → `RECONCILED`):

1. On restart, load and validate the durable intent before trusting any receipt. A local Markdown/JSON receipt is evidence, not broker authority.
2. Matching `POSTING`, `UNKNOWN`, or receipt-incomplete intents must enter exact-key broker reconciliation under the same daily mutation lock; do not return early merely because the receipt is absent or non-accepted.
3. Reconciliation may publish accepted state only after exact account, client key, provider order ID, symbol, side, amount, order type, TIF, provider status, and market-timezone trading date all match.
4. Never overwrite a remote identity field with an expected local value before validation. If an account-scoped endpoint omits `account_id`, prove account scope separately; if it supplies `account_id`, require exact agreement.
5. Require every broker identity field to be a non-empty string **before** comparison or hashing, including the account endpoint's account ID, an order object's account ID, provider order ID, and client/idempotency key. Never use `str(value)` as presence validation: JSON `null` becomes `"None"`, which can match a misconfigured expected value or a correspondingly corrupted durable hash.
6. Parse provider timestamps as real timezone-aware datetimes and compare after conversion to the market timezone. Prefix checks accept malformed timestamps and can misclassify UTC dates around midnight.
7. Recovery tests must inject crashes after each durable transition and after remote acceptance but before local receipt publication. Assert zero duplicate POSTs and eventual exact reconciliation of an accepted effect.
7a. Treat accepted-state persistence as part of acceptance, not cleanup after it. Assign or publish an accepted/reconciled local status only after the corresponding intent transition is durably written. Fault-inject that write for every path—direct POST success, pre-POST exact-key discovery, and post-error reconciliation. If persistence fails after a remotely proven effect, return `unknown`, mark submission truth unknown, retain the last durable `POSTING`/uncertain state for recovery, and never let a broad outer exception handler preserve a previously assigned PASS.
8. Keep mocked time deterministic across module boundaries. If a caller imports a guard whose implementation reads its own `datetime`, patching only the caller's clock is insufficient; preferably pass one explicit timezone-aware `now` through the public entrypoint into every guard, or patch the guard module too. First run the committed command unchanged, then use an external clock shim only to distinguish a flaky harness from an implementation defect—never report the shimmed pass as if the committed command was green.
9. Audit every wrapper, facade, loop helper, and duplicate-suppression shortcut that can return an accepted lifecycle status—not only the low-level submitter. A receipt-only fast path must never emit `accepted`/`already exists` or bypass durable-intent loading and exact-key reconciliation, even when a later downstream step would probably fail closed. Test public helpers directly with an accepted-looking receipt and no intent; require no accepted result.
10. Represent authorized money as a validated canonical decimal string or `Decimal`, not a binary float rounded with `:.2f`. Reject over-precision, exponent notation (unless explicitly allowed), booleans, NaN, and infinity before deriving the idempotency key, writing intent, comparing receipts, or building the POST. Prove that distinct invalid inputs such as `4.999` cannot collapse onto the same durable key and payload as `5.00`; normalization is safe only after explicit grammar/quantum validation.
11. For an **exact-current-HEAD** read-only verdict, capture the commit SHA before inspection and again after focused tests. Concurrent rebases/fixups can replace the commit lineage while preserving a similar-looking tree. If HEAD moved, inspect the new lifecycle diff, re-read any changed safety files, and rerun the focused suite against a fresh basetemp; finalize only when the before/after SHA of the final run is identical.
12. Keep read-only test evidence outside the repository: use a unique **native OS** pytest basetemp (for example, a `C:/Users/.../Temp/<uuid>` path on Windows), disable bytecode and pytest's cache provider, and compare repository status before and after. Distinguish pre-existing unrelated dirt from files created by the audit; do not claim a clean worktree when unrelated untracked files already exist.

See [references/paper-order-crash-identity-review.md](references/paper-order-crash-identity-review.md) for a compact review matrix and deterministic adversarial probes.

## Agent and Provider Runtime Boundaries

Treat autonomous worker dispatch and model-provider calls as external side effects even when the requested output is “report only.”

1. Declarative lane/work-packet JSON is untrusted data, not authority. Allow-list runtime type, worker, provider, model, prompt source, input roots, output roots, and receipt paths in immutable code or a separately approved capability ledger.
2. A repository-relative path check alone is insufficient. Restrict reads to explicit input roots, writes to task-owned output roots, reject reparse/symlink escapes, and use exclusive creation where overwriting another task’s artifact would alter evidence.
3. Do not reuse a broad shared agent/provider credential merely because it is available in the environment. Bind the worker to a dedicated least-privilege key or separately approved provider capability.
4. If the provider-authority boundary is not ready, remove or disable executable callers and make runtime-bearing packets fail closed. Labels such as `report_only`, `research`, or `no execution authority` do not neutralize network, token-spend, prompt-exfiltration, or artifact-write effects.
5. Serialize state-machine transitions across processes. Protect steward cycles with a process-lifetime lock, write state via flush/fsync plus atomic replace, and lock JSONL read-hash-append-fsync sequences so concurrent writers cannot fork or corrupt the chain.
6. Test concurrent dispatch/append behavior and prove that a blocked runtime creates no provider call, no claim, and no misleading activity receipt.

## OS-Level Outer Sandboxes for Device-Bearing Agent Workloads

When an agent runtime's built-in sandbox cannot project a required GPU/device without filesystem-policy failures, use one verified outer OS sandbox as the authority boundary rather than broadening the inner sandbox around device paths.

1. Start from a read-only root and rebind only the workspace writable.
2. Create a minimal device tree, then rebind each required device with the sandbox primitive intended for device access; do not classify device nodes as ordinary writable directories.
3. Mask forbidden data roots and host IPC/socket locations. Redirect temp directories and package caches into the writable workspace.
4. Preserve networking deliberately. Before masking broad mount trees, resolve DNS/config symlinks and reproduce only the minimal resolver data needed inside the sandbox.
5. Disable nested namespace creation when the inner agent must run unsandboxed relative to the outer namespace. Test that nested sandbox creation fails.
6. Run the inner agent in no-native-sandbox/full-access mode only after the outer probe passes. “Full access” then means full access inside the outer namespace.
7. Verify the exact runtime binary and version before launch, especially when host-mounted toolchains would disappear after mount masking.
8. Probe the boundary without the agent first: workspace write, outside-write denial, secret-tree denial, device operation, nested-sandbox denial, DNS, package endpoint, and model endpoint.

Keep credential handling separate from filesystem containment. A mount namespace cannot generally make credentials readable to the parent agent process but unreadable to model-generated child commands. Read-only credentials may also block token refresh. Report this limitation explicitly rather than implying that a read-only root provides credential confidentiality when outbound network is enabled.

See [references/wsl2-gpu-agent-outer-bwrap.md](references/wsl2-gpu-agent-outer-bwrap.md) for a concrete WSL2/Bubblewrap pattern and the Codex 0.144.5 device-mount failure mode.

## Approval and Authorization Ledgers

Treat approval decisions and authorization flags as security-sensitive state transitions, not display metadata.

1. Environment variables, config values, CLI arguments, and actor-name strings are labels—not authenticated principals. Until identity is bound to trustworthy OS/session or cryptographic evidence, record decisions only as attestations and keep both `approval_granted` and `execution_authorized` hard-false.
2. Hashing only the original request envelope does not protect later decision fields. Every appended event must be independently hash-bound (preferably chained to the prior event), or replay must reject any authority-bearing field that is not derivable from authenticated, validated evidence.
3. Adversarially edit `approval_granted`, `execution_authorized`, status, decision actor/reason/time, and event type while leaving the original request hash unchanged. Replay must fail closed; a UI hardcoded to say “closed” and an execute function that currently rejects are not substitutes for truthful durable state.
4. Keep visible approval, runtime authorization, and execution outcome as separate fields. No generic consumer may infer execution permission from an `APPROVED` label, a configured actor name, or a passing receipt.
5. Require the review overlay to be visibly redrawn before a second input can mutate. Test controller state, selected identity, zero first-input side effects, and an explicit application invalidation—not state alone.
6. If the contract says event deletion must fail replay, test removal of the first, middle, final, and only event plus whole-log absence. A normal previous-hash chain cannot detect suffix truncation when no successor remains; bind replay to a separately durable trusted tail hash, count/checkpoint, or authenticated signature before claiming deletion resistance.
7. Enforce review-surface fit **before** appending. Validation must use the renderer's exact prefixes, wrapping rules, and terminal-cell widths (for example `wcwidth`), not raw `len()` or a separate `textwrap` approximation. Reject or canonicalize tabs/control whitespace before hashing. If rejection is the contract, inspect the raw value before `.strip()`/`.trim()`—otherwise leading or trailing controls disappear and forbidden input can be persisted. Probe embedded, leading, and trailing `\t`, `\r`, `\n`, C0/C1 controls, and Unicode category `C`, plus wide Unicode. For every rejection, assert zero event-ledger, durable checkpoint, and temporary-file writes. Audit command help and docs too: operator-visible “grant” or “run” claims are authority bugs when decisions are attestations and execution is closed.
8. Treat pure operator view models as a safety boundary even when they have no I/O. Use one shared canonical grammar across gate, receipt, source, and objective evidence; reject Unicode category `C` controls in authority-signaling text; require every `FRESH` source to carry a nonempty parseable in-window observation; validate complete parent/task collection shapes before lookup or truthiness; preserve duplicate identities as ambiguity instead of last-write-wins; require exact built-in Boolean authority/completion fields; make timestamp and state resolution exception-total for hostile subclasses, mappings, and `tzinfo`; and prove recursive immutability/hashability on cards, decisions, pages, and the complete rendered object rather than only one signature tuple. Freeze a local candidate SHA for review, keep failed SHAs rejected, and review each successor over the full base-to-candidate range.
9. For append-only lifecycle ledgers, validate the complete pre-existing history before any exact-replay early return. Group rows by immutable identity, reject duplicate identity/state pairs globally, compare every non-state field by canonical JSON bytes so Boolean/number type changes cannot collapse, and enforce chronological monotonicity. A corrupt historical pair must block unrelated appends. On Windows, pair a per-path thread mutex with the OS byte-range lock to prevent same-process `EDEADLK`, then prove locking with both a high-contention thread race and spawned processes; assert one physical row for an exact concurrent append race.

See [references/operator-view-model-adversarial-review.md](references/operator-view-model-adversarial-review.md) for the decision-gate, duplicate-identity, hashability, parser-exception, and frozen-candidate probe matrix. See [references/append-only-lifecycle-ledger-review.md](references/append-only-lifecycle-ledger-review.md) for the full-history validation order, spawned-process race, reverse-transition, and moving-candidate review probes.

### Non-runnable proposal ledgers before identity is ready

When agents may draft work but actor authentication or atomic task creation is unavailable, remove the approval/task-creation surface entirely rather than storing an `approved` label with hard-false authority. Persist only bounded local proposals and repeat observations. Keep immutable proposal identity separate from changing `observed_at` values; validate the exact complete schema and every hard-false authority field on append and replay; use read-only SQLite connections for list/UI reads; never initialize or repair malformed state from a read path; enforce bounds before commit; return transaction-derived state without a post-commit reread; close connections explicitly; bind production writes to the canonical non-reparse path; and render malformed state as `UNAVAILABLE`, never an empty queue. Exact replay includes relational integrity: bind table/JSON/observation identities, reject orphan or hidden historical rows, run foreign-key checks, and reject unexpected triggers/views or partial indexes. Path containment must inspect the unresolved root as well as the resolved destination and account for the validation-to-open reparse race. Do not claim deletion resistance from an unkeyed hash chain stored in the same writable database.

Decide the local-attacker/path-containment threat model **before** implementing persistence. If a direct SQLite pathname cannot structurally close symlink/junction/reparse check-open races, do not accumulate application-level `resolve`/`lstat` checks and call the boundary fail-closed. Use a trusted backend/handle-based primitive, or remove persistence and retain a provider-free, zero-write shadow generator. Treat repeated independent review rejections that expose new integrity or containment defect classes as architectural evidence: delete/defer the unsafe ledger, review, approval, and queue UI together; restage, reverify, and independently review the reduced shadow slice as a new candidate.

For a command claiming **zero writes**, do not infer safety from SQLite `mode=ro` or `PRAGMA query_only`: a WAL-mode reader can still create or modify `-wal` and `-shm` sidecars. Resolve every real production state root, including environment-derived user application-data paths; run a passive control interval; then compare database and sidecar existence, size, modification time, and hashes around both the smallest read helper and the complete default CLI. Disable or explicitly account for bytecode and tool caches. Validate every input authority field before applying an output cardinality cap, and reject or deterministically deduplicate repeated normalized proposal identities. See [references/read-only-sqlite-side-effects.md](references/read-only-sqlite-side-effects.md) for the reproduction protocol and safer design options.

See [references/local-proposal-ledger.md](references/local-proposal-ledger.md) for the schema pattern, shadow fallback, staged-review protocol, adversarial probes, and regression matrix. For Windows receipt/artifact writers where pathname-based reparse containment cannot be proven, see [references/windows-zero-write-artifact-serialization.md](references/windows-zero-write-artifact-serialization.md): reduce the component to deterministic zero-write serialization rather than claim a safe local writer. When evaluating whether a real writer can instead be built on pinned native handles, use [references/windows-handle-bound-journal-probe.md](references/windows-handle-bound-journal-probe.md) for the disposable `NtCreateFile`/`NtSetInformationFile` proof, ctypes ABI pitfalls, adversarial checks, and evidence-cleanup protocol.

## Python Authorization Boundary Reviews

For an “atomic” Python authorization repair, do not stop at the public entrypoint or a passing focused suite. Treat every importable symbol as part of the attack surface.

1. Inventory every function/class that can mint context, verify inputs, load rows, build blocks, or compute outcomes. A leading underscore is not an authorization boundary.
2. Compose helpers adversarially: verified rows from one database with an evaluator for another; final rows returned by an integrity verifier with an outcome evaluator; stale rows retained before a database mutation; and uncontracted rows passed directly to the evaluator.
3. Require the authorized path to reject caller phase/contract mismatches, missing phase partitions, cross-database provenance, contract/database mutation during evaluation, and final outcomes without separately governed approval — before any outcome is computed.
4. Require outcome computation itself to be unavailable outside the atomic entrypoint. Move it into a closure-local inner function or otherwise make it non-importable; an importable `_evaluate_blocks` remains a direct bypass even when the public API is correct.
5. Run direct-Python probes from external scratch with the project interpreter, then remove scratch and re-verify the frozen candidate identity.

See [references/python-authorization-boundary-review.md](references/python-authorization-boundary-review.md) for the probe matrix and minimal recipe.

## Atomic Multi-Write Handoffs

When a workflow performs multiple durable writes such as `create downstream task → append upstream receipt`, treat it as one state transition only if the backend actually provides that atomicity.

1. Enumerate crash and retry cut points before and after **every** write.
2. Verify an idempotency claim from the authoritative implementation/schema. A preflight lookup followed by a later insert is race-prone; a process-local lock cannot repair crash windows, other hosts, or independent backend transactions.
3. Use a stateful harness that returns distinct IDs for repeated creates and persists every object/receipt. Assert exact cardinality, not merely that an expected ID appears in a set.
4. A retry after downstream creation but before receipt publication must recover the same durable object or fail closed; it must not simply issue `create` again.
5. If exact-once requires a cross-write atomic primitive that the backend lacks, stop patching the caller. Keep the workflow shadow-only and escalate to a backend transaction, transactional outbox, or durable compare-and-set transition.
6. If the backend owns both records, make the handoff key a database-enforced binding and create the downstream task, upstream receipt, ordinary audit events, and binding row inside that one transaction. Identical replay returns the stored pair; any changed binding fails closed.
7. Treat CLI process status as part of the safety contract: structured success must be the only success output, and a rejected transition must reach the actual console/module process as nonzero. A handler that returns `1` is not sufficient if the top-level entrypoint discards handler return values.
8. Treat the **committed backend response schema** as an immutable part of the handoff contract. Before any authorized live shadow, exercise the real command against an isolated board and verify every returned field by exact type/domain—not a mock-derived schema. Numeric receipt fields need backend storage bounds as well as JSON type checks (for SQLite `INTEGER`, reject booleans, non-positive values, floats, and values above signed 64-bit maximum). A local parser rejection after a successful backend commit is an **unknown locally-observed outcome**, not permission to retry blindly.
9. On that post-commit local rejection, reconcile the backend by immutable handoff key before any other mutation. If one binding/card/receipt exists, quarantine its downstream task before review or dispatch, preserve the source receipt and recovery record, and never reuse that source/key/workflow for a repaired attempt. Fix and independently review the client, then create a fresh immutable envelope and source task for the next bounded shadow. Do not claim end-to-end success from a backend commit the caller failed to validate.

See [references/atomic-multiwrite-handoffs.md](references/atomic-multiwrite-handoffs.md) for the cut-point matrix, contract-verification questions, adversarial harness pattern, and safe architecture choices. See [references/sqlite-task-handoff-primitive.md](references/sqlite-task-handoff-primitive.md) for the concrete SQLite schema/CLI pattern, subprocess exit-code regression, and isolated verification sequence. See [references/response-schema-after-commit.md](references/response-schema-after-commit.md) for the backend-response probe and quarantine/retry sequence.

## Detailed Checklist

See [references/adversarial-checklist.md](references/adversarial-checklist.md) for transaction, API-state, cancellation, migration, and concurrency probes. See [references/async-reconciliation-locking.md](references/async-reconciliation-locking.md) for the non-blocking gate/lock pattern and race probes. See [references/runtime-ownership-and-scoped-cleanup.md](references/runtime-ownership-and-scoped-cleanup.md) for cross-process singleton locks, account identity gates, and strategy-owned cleanup.

## Pitfalls

- A disabled submit path does not protect an ungated cleanup path.
- HTTP success does not prove semantic acceptance.
- Timeout or malformed response may occur after acceptance.
- `404` after cancellation does not necessarily prove zero effect.
- JSON booleans are numbers in several languages; reject them explicitly where numeric quantities are required.
- A successful commit can be masked by a failing close unless cleanup is non-throwing; in journal/queue pipelines this can permanently lose downstream processing because replay sees a durable duplicate.
- Checking a latch under a lock but setting it outside the lock preserves a race.
- `IF NOT EXISTS` alone does not make discovery-plus-migration atomic.
- Serializing POST calls does not enforce risk limits: accepted-but-unfinished effects must consume capacity before the remote call.
- Checking only current remote state (positions, balance, inventory) ignores locally durable pending/unknown intents; enforce limits against both under one transaction.
- Recover an existing idempotency key before testing new capacity, or duplicate retries can be blocked instead of reconciled.
- A migrated active intent with unknown reservation size must block conservatively until reconciled; never assume its reservation is zero.
- Setting a reconciliation gate false but releasing the shared lock during the remote call still permits stale-snapshot races: verified-flat cleanup can mark an intent closed, then late reconciliation can resurrect it to pending/open after the cleanup latch is set. Serialize the complete snapshot-to-local-update interval.
- Publishing the reconciliation result only after the call is insufficient if the previous `true` gate remains visible while the call is in progress; close it before invoking the remote API and leave it closed on exceptions.
- Deterministic idempotency keys must have a bounded, validated grammar. Validate date/tenant/symbol components before constructing the key, and never treat an arbitrary parseable HTTP 200 payload as proof of the intended effect: require exact remote identity matching.
- In asyncio code, acquiring `threading.Lock` on the event-loop thread before `await asyncio.to_thread(...)` can starve pings, ingress, supervision, and shutdown for the full network timeout. Close the gate immediately, then offload one synchronous helper that acquires the lock and performs snapshot → local updates → result publication without releasing it.
