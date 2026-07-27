# Real-Worker Canary Admissibility

Use this gate when a Vesper milestone claims that a real Hermes/Kanban task and worker proved an end-to-end report-only lifecycle. A `done` card, plausible artifact, or zero exit code is necessary evidence, not acceptance by itself.

## 1. Freeze the execution contract before publication

Bind and hash all fields that can change the result or authority:

- task and idempotency IDs;
- exact source revision;
- frozen input/config/baseline/evaluator paths and SHA-256 values;
- exact worker role and lane;
- workspace kind, project, branch, and expected HEAD when a worktree is required;
- allowed tools and output/edit roots;
- complete denied-capability set;
- metric, threshold, guardrail, runtime, turn, retry, and cost limits;
- required artifacts, stop conditions, and reviewer identity.

Reject weakened positive thresholds just as firmly as invalid negative values. Range validation is not identity binding. Prove every output lies beneath an editable root and every input is from an allowlisted root.

A contract that embeds its own Git source SHA cannot be committed into the source revision it names without a self-reference problem. For a dynamic canary contract, generate the canonical JSON outside the candidate tree, embed its exact bytes/hash in the audited Kanban body, and have the finalizer parse and revalidate that body. The worker worktree should still resolve `HEAD` to the named source revision; do not weaken source binding merely to make a committed contract file convenient.

### Cross-worktree content hashing on Windows

Do not hash bytes from the coordinator checkout and assume another Git worktree will materialize identical bytes. Git line-ending filters can produce LF in one existing worktree and CRLF in a freshly created one even when both resolve to the same blob and SHA. Choose and document one binding semantics before dispatch:

- Prefer a repository `.gitattributes` policy that materializes the frozen evidence identically; or
- for explicitly declared UTF-8 text inputs only, hash canonical text bytes (for example, CRLF normalized to LF) in both the preparer and finalizer, with LF/CRLF parity and non-line-ending mutation regressions; or
- materialize the target worktree before freezing the contract and hash those exact worker-visible bytes.

Never silently weaken binary artifacts to normalized-text hashing. Candidate/output bytes and other binary evidence remain raw-byte bound. The contract **and** receipt must carry an exact hashing-profile object (algorithm, text canonicalization, and scope), and both validators must reject profile drift. A reviewer must recompute the declared canonical bytes—not compare a canonical-content digest with raw CRLF checkout bytes and call that proof. Add regressions showing LF/CRLF parity under the declared profile and rejection of every non-line-ending mutation.

## 2. Read back the real control-plane identity

After creation and again after dispatch/completion, query one coherent read-only Kanban transaction for:

- task row and idempotency key;
- assignee and creator;
- status;
- workspace kind/path, project, branch, and HEAD;
- exact retry/runtime limits;
- events;
- run row, run ID, worker profile/session, start/end, and terminal outcome;
- changed-file/artifact metadata.

If the contract requires an isolated worktree, `workspace_kind=dir` is not an equivalent proof. If the task reports a different retry limit than the contract, classify the attempt `HELD` even when it used only one attempt. Never widen a contract retry value to account for the initial attempt unless the Kanban field is explicitly proven to use that different semantic.

Bind both the human project selector and the authoritative task-row project identity. Hermes may accept `--project <name-or-slug>` but persist an opaque `project_id` such as `p_...`; comparing the stored value with the selector string creates either a false rejection or a tempting fail-open exception. Resolve or pre-read the expected project ID and require exact read-back. Likewise, a branch already checked out in the coordinator worktree cannot safely back a second worktree; create a dedicated canary branch at the frozen SHA and require exact branch and `HEAD` read-back.

## 3. Audit worker telemetry, not just outputs

Read the task log and run metadata. Build an observed-action inventory and compare it with the allowlist.

A task-body instruction such as “do not use terminal” is policy text, not tool enforcement. Verify the installed Hermes worker launcher before the canary: dispatcher-spawned workers may resolve CLI tools from the assignee profile's `platform_toolsets.cli` and append task-scoped Kanban tools. They may also continue with automatic verification after `kanban_complete`, so audit the log through the session footer—not merely through the completion event. When the user has explicitly authorized strict canary configuration, back up the assignee profile, change only its CLI toolset to the smallest reversible set (do not alter provider/model/credentials), launch a fresh task/session, and restore the profile after evidence capture. Even a minimal `file` toolset exposes more than read/write, so observed telemetry remains mandatory.

Fail closed when telemetry contains a non-allowlisted action, including unsuccessful calls: a denied path probe or failed tool invocation still demonstrates behavior outside the frozen contract. Audit exact arguments and resolved paths, not only tool names or successful outputs. Examples include:

- terminal or generic shell use;
- dependency installation or `uv run --with ...` acquisition;
- network/browser/provider activity;
- writes outside output roots;
- scheduler, broker/order, risk, promotion, deployment, or credential activity.

Injected Kanban completion/read-back bookkeeping is admissible only when the contract explicitly identifies it as control-plane bookkeeping and the evidence shows no wider authority. Skill loading is not proof of compliance; inspect the actual tool calls the skill caused.

Do not use a human log footer's total `Messages` count as the contract's model-turn consumption. It usually includes user and tool-result rows. Bind `worker_session_id` from the authoritative task-run metadata, open the assignee profile's session store read-only, count persisted assistant/model rows, and decode each assistant `tool_calls` record. Classify candidate-plane file actions separately from injected Kanban control-plane actions; validate every read/write path against the frozen input/output sets and retain a bounded sanitized inventory in the receipt packet. Continue through post-`kanban_complete` rows because dispatcher/system follow-up may add comments or attempt verification after terminal task completion.

When temporarily narrowing a worker profile's CLI toolset, preserve the original config outside the profile, record its digest, verify the diff changes only the intended toolset, and restore it byte-for-byte immediately after the run reaches a terminal state. Re-read the restored digest. This is reversible execution confinement, not permission to alter model/provider/credential policy.

Preserve inadmissible attempts as immutable evidence. Do not rewrite their cards, artifacts, or logs into a pass. Use a new idempotency identity for a corrected canary.

## 4. Keep identities separate throughout the lifecycle

Do not overload one `external_id` field for unrelated identities. Preserve separate immutable bindings for at least:

- contract/loop ID and hash;
- Kanban task ID;
- run ID;
- worktree/branch/HEAD/assignee;
- candidate hash;
- evaluation/evaluator hash;
- receipt hash;
- reviewer task/verdict.

A candidate transition must never overwrite the task identity. Validate these bindings again on restart and in the read-only operator projection.

## 5. Validate deterministic evaluation independently

The worker may propose a candidate and bounded notes; it may not decide acceptance. The evaluator must:

- consume exact frozen bytes, not worker narrative;
- validate strict config/baseline/fixture schemas;
- reject duplicate date/symbol rows, non-finite values, leakage, ambiguous ties, and unsupported transforms;
- reproduce the baseline at least three times;
- emit only `ACCEPTED`, `REJECTED`, or `HELD`;
- bind its version/hash and exact output bytes.

On restart, recompute or independently validate an existing evaluation artifact. Do not trust `evaluation.json` merely because it exists.

## 6. Receipt and event-chain gate

Before accepting a receipt:

- bound raw size before JSON decoding;
- require exact top-level and nested schemas;
- recompute every lifecycle event hash, previous-hash link, sequence, contract hash, and monotonic timestamp;
- require the lifecycle state to agree with the decision and review state;
- require exact Kanban/run/worktree/evaluator/baseline/input/candidate bindings;
- require finite numeric consumed runtime/turn/retry/cost values and compare them with contract maxima;
- require the complete denied-authority set.

`UNVERIFIED` may describe missing provider identity only when the contract explicitly permits that state. For a supervised Hermes worker, prefer the persisted session model/provider identity from the authoritative session row and hold when policy requires it but it is absent; do not discard known telemetry and then label it unverified. `UNVERIFIED` must never substitute for consumed limits, task/run/worktree identity, evaluator identity, or review authority.

Type the control plane honestly in the receipt. A supervised worker run is `hermes_kanban`; a natural deterministic schedule run is `hermes_cron`. Do not fabricate a Kanban task/creator/event count for a cron tick merely to reuse one receipt schema. Validate the exact nested schema for each kind, and on exactly-once replay require the stored receipt to match the requested source revision, schedule/task ID, run ID, root/worktree, and branch before returning it as a pass.

## 7. Review ordering is part of correctness

The safe order is:

`... -> decision -> REVIEW_READY -> exact independent review -> CLOSED`

The owner may create a review packet at `REVIEW_READY`, but may not self-close. Bind the independent reviewer task, exact candidate/source/receipt identities, verdict, reviewer run/session, and review receipt before `CLOSED` and before completing the governing Kanban goal. A packet marked “not approved” alongside lifecycle `CLOSED` is a false-green state. VOT must fail closed on that mismatch rather than displaying `CLOSED` with a pending-review label.

### Preallocate reviewer identity without making it runnable

A receipt needs the real reviewer task ID, while the reviewer needs the completed receipt. Do not solve this chicken-and-egg problem by creating an **assigned** `--initial-status blocked` reviewer card: current Hermes may promote blocked cards, so the reviewer can run before the packet exists.

Use this ordering instead:

1. create the reviewer card without an assignee (and with an idempotency key, exact source branch/worktree, candidate hash, and future packet path); an unassigned card is nonspawnable even if its status changes;
2. read back that exact task ID and prove it has no claim, run, or worker PID;
3. bind the real reviewer task ID into the pending receipt and review packet;
4. only after immutable packet creation, assign `vesper-riley` and promote/unblock the exact card;
5. require one terminal reviewer run on the exact source SHA and parse one structured verdict binding source, receipt, and candidate hashes;
6. persist a separate immutable `review_result.json`, bind its reviewer task/run/session and summary hash into the lifecycle store, then append `CLOSED` exactly once.

A `HOLD` is terminal evidence for that review attempt. Do not unblock/reuse the same reviewer card as a later approval and do not rewrite its pending receipt: create a fresh reviewer task and a fresh immutable pending-review receipt bound to that new task. Preserve every held receipt, comment, run, and worktree write as historical evidence. The closure finalizer should require exactly one successful terminal run for the approving reviewer identity.

Make the review command profile explicit in the card rather than saying only “run tests” or “run critical Ruff.” Bind the exact existing interpreter/venv, focused test list, external `--basetemp`, compile command, JSON checks, and the precise critical Ruff selector (for example `--select E9,F63,F7,F82`) reviewed by the owner. Otherwise a reviewer may use system Python or unintentionally substitute repository-wide style debt for the agreed safety gate. Missing or failed checks remain `HOLD`; do not install dependencies from a review task.

“Read-only reviewer” is an observed property, not merely task prose. Audit reviewer telemetry and the filesystem after the run, including ignored paths such as `.hermes/` that ordinary `git status` can hide. A reviewer-created learning log, cache, fixture output, or test artifact is still a write. Preserve it externally if needed, classify the attempt honestly, and use a clean successor worktree/task rather than deleting evidence and retroactively approving.

A later read-only projection should accept `CLOSED` only when the lifecycle row, closed event, pending receipt, and independent review result all agree. Approval remains report/planning evidence; `execution_authority` and `promotion_allowed` stay false.

## 8. Schedule installation gate

Install or enable an unattended report-only schedule only after the supervised canary passes every gate above. Recheck immediately before installation:

- all order-capable tasks remain disabled;
- wrapper/action hashes match reviewed canonical source;
- one schedule only;
- timeout, overlap, retry, working directory, principal, and no-order boundaries are exact;
- rollback is documented and tested;
- the natural scheduled run produces a separately validated receipt.

Never treat `task status=done`, evaluator `ACCEPTED`, or artifact existence alone as authorization to schedule.

### Dispatcher and singleton recovery details

If a freshly created card remains `ready`, check gateway/dispatcher status before changing the task. When the gateway is stopped, first query all spawnable ready cards and use a dry run. A one-pass `hermes kanban --board vesper dispatch --max 1 --json` is admissible only when the intended exact task is the sole candidate (or the returned `spawned.task_id` is verified before proceeding); otherwise a board-wide pass can start unrelated work. Keep any temporary worker-profile confinement in place until that exact run is terminal, then restore the profile byte-for-byte and verify its digest.

For unattended PID locks on Windows, `os.kill(pid, 0)` is not a reliable dead-process test: a nonexistent high PID can surface as `OSError(errno=22, winerror=87)`. Use a Windows process-handle probe such as `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)`; treat `ERROR_INVALID_PARAMETER (87)` as proven dead, a valid handle as alive, and access-denied/unknown errors as ambiguous-alive. Reclaim only a proven-dead owner, write the new PID under exclusive-create semantics, and test active, malformed, dead, and replay cases. On POSIX, retain the usual `ProcessLookupError`/`PermissionError` distinction.

## 9. Turn-budget and handoff discipline

A multi-phase coordinator can exhaust its turn budget after committing useful slices and leave uncommitted work. A terminal board run still does not prove the worker process tree exited. When this happens:

1. pause automatic redispatch and task supervisors that could race the handoff;
2. read task/run status, then inspect host processes for the exact `work kanban task <TASK_ID>` command line, executable, PID, parentage, and start time;
3. preserve a binary tracked patch and archive the intended untracked implementation files outside the repository;
4. terminate only a proven stale task process tree—never the gateway parent or an ambiguous process—and verify the PIDs are gone;
5. sample relevant file hashes twice across a short interval; any continued change means ownership is still unresolved;
6. inspect commits plus uncommitted paths and run a fresh focused acceptance suite;
7. continue from the same isolated worktree or create a reviewed successor card with explicit single-writer ownership;
8. never discard useful uncommitted work merely because the run timed out.

Prefer milestone-internal slices with independent commits and explicit acceptance checkpoints so a single coordinator run does not spend its entire turn budget before canary/review/closure.