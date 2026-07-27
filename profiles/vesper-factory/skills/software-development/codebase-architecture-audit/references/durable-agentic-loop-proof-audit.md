# Durable Agentic Loop Proof Audits

Use this reference when a milestone claims one autonomous loop is proven across authority classification, task dispatch, a real worker, deterministic evaluation, durable lifecycle state, receipts, review, and restart/idempotency.

## Freeze four evidence planes

Bind each conclusion to its own immutable identity:

1. **Canonical product SHA** — what is accepted on the main/canonical branch.
2. **Candidate SHA** — the exact implementation under review. If it advances during the audit, finish the frozen SHA first and classify later commits as a separate delta.
3. **Control-plane/backend SHA and schema** — task/Kanban/dispatcher behavior can differ from the product repository.
4. **Live observation window** — timestamped task, run, event, artifact, and process evidence.

Never promote a branch prototype, dirty worktree, draft milestone document, historical receipt, or live artifact into canonical capability by implication.

## Authority classifier: declaration is not enforcement

Require all of these before calling a contract authorized:

- exact schema and a policy version/hash owned by trusted code, not only a caller-selected `authority_class`;
- exact frozen thresholds/guardrails, approved worker and reviewer identities, allowlisted input roots, and outputs contained under task-owned writable roots;
- actual launcher/runtime toolsets and sandbox matching the declared allowlist;
- complete closed-authority set, including account/broker/order, paper/live, provider/source/paid data, scheduler, training/promotion, target/risk/capital, deployment/dependency, secrets, destructive actions, shell/subagents, and network where relevant;
- contract bytes, source tree, input bytes, evaluator, baseline, and runtime profile verified against their claimed hashes.

A prompt, denial list, profile name, or `read_file`/`write_file` declaration does not remove broader tools the worker process actually receives. Resolve the live profile before approval: require that it exists, bind its exact configuration/toolset hash, and compare effective tools—not merely configured labels—with the contract. Generate the worker prompt/body from trusted code; a bridge that appends arbitrary caller-supplied instructions to a valid contract reopens every denied capability. Post-execution log-marker scanning is evidence triage, not preventive enforcement, and a receipt must never hardcode the declared tool list as though it were observed runtime evidence.

## Prove a real worker, not merely a done card

A terminal task is insufficient when operators can manually complete it or the backend can synthesize a run. Require one consistent chain:

`created -> claimed -> spawned -> heartbeat/activity -> completed|blocked`

Bind the same task ID and run/attempt ID across those events, and require expected assignee/profile, non-synthetic worker PID or service launch identity, isolated workspace/branch/HEAD, candidate artifact hash, terminal run outcome, and bounded log/transcript evidence. Record provider/model/request identity when authoritative instrumentation exposes it; otherwise mark that field unavailable without upgrading the proof.

Worker-authored summaries and metadata are claims, not independent evidence. The controller must independently hash and validate the output. A second task with a new idempotency key is another run, not restart/idempotency proof.

For Hermes project-linked worktree tasks, inspect the **installed** worktree materializer before dispatch. Some versions create a missing branch from the project checkout's current `HEAD`; embedding a candidate `source_revision` in the card or checking worker `HEAD` only in a post-run finalizer does not pin admission. Require an existing unambiguous ref at the exact candidate SHA or an exact-source creation primitive, and prove no other worktree owns that branch. Also inspect task readiness ordering: if `create` publishes directly to `ready`, an active gateway dispatcher can spawn the worker before bridge readback rejects a project/branch/source mismatch. Preflight every immutable binding or create blocked, verify, then explicitly release.

Treat worker text logs as secondary evidence only. Verify whether rotation causes the normal log reader to omit earlier generations; parse structured action records when available; enumerate every action rather than scanning a short forbidden-marker list; and validate both read and write paths. A content worker can violate a frozen-input contract using only `read_file` when absolute or out-of-worktree reads are accepted. Lifecycle-only Kanban actions must be explicitly classified as such, not silently omitted while the receipt claims the complete tool action list.

## Durable lifecycle/store review

Require:

- explicit `BEGIN IMMEDIATE` or equivalent serialized transaction plus versioned compare-and-set transitions;
- separate immutable fields for contract, task, run/attempt, workspace/branch/HEAD, candidate, evaluation, receipt, and review identities—never one overloaded `external_id`;
- lease owner, heartbeat, expiry, attempt ID, and fencing token; every write checks the current fence;
- lease renewal and safe reclaim semantics;
- contract-specific retry budget with reason and attempt events;
- exact event schema with legal from/to state, reason, timestamp, prior hash, and recomputed event hash;
- replay-time verification that row state equals the verified chain tail;
- no automatic `REVIEW_READY -> CLOSED`: closure requires a bound independent review verdict and final task-system readback.

For Python `sqlite3`, `connect(..., isolation_level="IMMEDIATE")` is **not** proof that an authoritative `SELECT` is serialized: under legacy transaction control, the implicit `BEGIN IMMEDIATE` starts at the first DML statement, so a preceding read can occur outside the transaction. Require an explicit `BEGIN IMMEDIATE` before the read, then a version/fence compare-and-set in the `UPDATE`. Apply the same rule to retry increments, lease sweeps, and create-if-absent logic. Replay must validate every adjacent state edge and timestamp, not only hash continuity and final-row equality. A stale-lease sweep must respect the declared state graph—do not silently move decision states through an edge the model forbids—and retry counters must use the contract-specific maximum, carry reason/attempt events, and be reachable from the real recovery controller rather than tests alone.

Contract expiry should block new admission, not make an already admitted run impossible to reconcile after restart.

## Cross-store handoff

If lifecycle and task state live in different databases, there is no cross-database atomicity. Use a transactional outbox or backend-owned atomic handoff primitive:

1. commit immutable handoff intent locally;
2. invoke the remote/backend mutation with a database-enforced key;
3. on timeout or crash, reconcile by that key before retry;
4. require exactly one matching backend binding—zero is absent, more than one is ambiguity/HELD;
5. bind exact readback in a local transaction.

A preflight lookup, process-local lock, non-unique idempotency index, or fixed argv does not prove exactly once. Crash-sticky lock files need owner/fence/expiry recovery.

Audit the **live backend schema**, not only the bridge's test double. For SQLite-backed control planes, inspect `PRAGMA table_info(...)`, `PRAGMA index_list(...)`, and `PRAGMA index_info(...)`. Tests can accidentally invent a source-revision column, a unique idempotency constraint, or a slug-shaped project field that production does not have. Treat `row.get("binding") in {None, expected}` as a missing-binding bypass, not compatibility. A `fetchone()` query over a non-unique idempotency index hides ambiguity. Also distinguish human project slug from backend project ID: if the remote mutation commits and strict readback then rejects that representation mismatch, the task is already orphaned unless an outbox/reconciliation path records and rebinds it.

## Full receipt validation

A receipt self-hash proves only internal byte consistency. Validation must independently require and recompute:

- exact nested schemas and contract/task/run/workspace bindings;
- candidate bytes and candidate schema;
- input, config, baseline, evaluator, source-tree, log/transcript, evaluation, and review hashes;
- the entire lifecycle hash chain and legal state sequence;
- decision consistency (`ACCEPTED`, `REJECTED`, `HELD`) with evaluator output and final state;
- exact consumed-limit keys and numeric values within immutable maxima;
- complete denied-authority set;
- independent review status and final task-system state.

`UNVERIFIED` may be honest telemetry, but it cannot satisfy a required limit or real-worker acceptance field while the receipt reports an overall pass.

Adversarially inspect the validator's own supposedly-valid test fixture. If that fixture contains a schema-invalid candidate, arbitrary evaluator/input hashes, caller-invented Kanban facts, or fake review hash and still validates, the test proves a false-green validator. Require equality across top-level task ID, Kanban task ID, lifecycle loop ID, run/attempt ID, event bindings, and review identity; compare consumed limits with maxima reconstructed from the validated contract, never a second caller-supplied `limits_contract` object. Review closure must load and validate an actual independently produced review receipt and task/run readback—a reviewer label, `t_` prefix, and 64-hex string are not review evidence.

Bind the **executed** evaluator, not merely a similarly named file. Hashing the evaluator path in a worker checkout while importing and executing the module from the controller's checkout is a cross-binding defect; verify the loaded module's `__file__` bytes/source tree or execute through the exact frozen artifact. Likewise, a self-consistent existing receipt is not replay proof until it is rebound to the requested run ID, schedule/task identity, source revision, current frozen inputs, lifecycle row, companion artifacts, and ledger entry.

## Restart and idempotency matrix

Inject or reason through crashes at minimum:

- before/after contract commit;
- before/after backend task creation;
- after remote commit but before response/readback;
- after task binding but before spawn observation;
- worker crash, stale lease, and stale prior-attempt completion;
- after candidate bytes but before candidate-state commit;
- before/after evaluation publication;
- before/after receipt, ledger, review packet, and final task closure;
- concurrent same-key callers;
- replay after terminal closure.

For each cut point state whether restart creates, reconciles, revalidates, retries, quarantines, or holds. Assert cardinality—one task, one accepted candidate, one evaluation, one receipt, one review binding—not merely presence of an expected ID. Trace production reachability too: a bridge, registry, stale-lease handler, retry API, or close-review method called only by tests is a prototype primitive, not an end-to-end loop. An unattended local function may honestly produce local deterministic evidence, but it must not populate a receipt's Kanban task/run/worktree/status/tool fields from constants when no authoritative task exists; use a distinct control-plane schema or classify the evidence as synthetic.

When live proof appears after the review starts, bind it to its own exact source revision. A canary produced by a successor commit cannot prove the earlier candidate, even if the earlier SHA is its ancestor. Finish the frozen-SHA verdict and report the successor evidence separately.

## Verdict language

- **PROVEN:** canonical implementation plus one fully bound real-worker run and passing restart/concurrency evidence.
- **SUPERVISED EVIDENCE:** a real worker ran, but authority enforcement, lifecycle integration, review, or restart proof is incomplete.
- **PROTOTYPE:** source/tests exist only on a candidate branch or are not reachable from a production entrypoint.
- **HOLD:** any authority, identity, cross-store, receipt, review, lease, or ambiguity condition remains.
