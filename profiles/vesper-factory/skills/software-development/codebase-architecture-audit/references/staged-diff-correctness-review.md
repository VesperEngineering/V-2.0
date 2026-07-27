# Staged-Diff Correctness Review Checklist

Use this when a large staged change crosses data, portfolio, execution, scheduler, worker-runtime, and operator surfaces.

## Index discipline

- Record the repository root, full HEAD, branch, `git status --short`, staged name/status, and staged stat first.
- Hash the exact staged patch bytes at entry and exit, including binary content: `git diff --cached --binary --no-ext-diff | sha256sum`. If the requester supplied a digest, require an exact match before using any evidence.
- Review the index, not an accidentally newer working-tree copy. Use `git show :path` and index blob IDs when staged and unstaged content may differ; never silently mix `AM` working files with staged source.
- When executable probes must run against the exact index, export only the required indexed paths to an external scratch tree with `git checkout-index --prefix=<external-root>/ -- <paths>` (or archive the base and overlay index blobs). Run with bytecode/cache disabled and an external temp/basetemp. Do not stash, reset, checkout, or otherwise rewrite a live worktree merely to manufacture a clean test boundary.
- Recheck patch digest, HEAD, status, per-file index/working blob IDs, and untracked files at the end. If concurrent working-tree changes appeared, report them separately; they do not change the reviewed index but can invalidate any probe accidentally run from the live tree.

## Contract tracing

For every new status, decision, receipt field, or state transition:

1. Find its producer.
2. Find every consumer and validator.
3. Check that accepted-state sets are shared and complete.
4. Check that negative states cannot pass through substring matching.
5. Check immutable identity fields across the chain (task/order ID, symbol, side, amount, date, artifact hash).

Typical decisive defects:

- A `PASS` receipt whose semantic decision says `no action` reaches a mutating path.
- A newly introduced success state is rejected by older downstream validators.
- Reconciliation matches “latest by symbol” instead of the exact idempotency key.
- A calendar gate checks weekday/fixed hours instead of exchange holidays and early closes.
- A historical portfolio path silently reads the latest available observations (lookahead).
- Per-asset arrays have equal lengths but represent different dates (calendar misalignment).
- Append-only ledgers perform read/check/append without a process lock or transaction.
- Terminal events are accepted without a valid predecessor transition.

## Test-integrity checks

- Inspect changed assertions and skips separately from implementation changes.
- Treat changing the input so the old invariant is no longer exercised as expectation laundering.
- Reject autouse skips based on untracked/generated local artifacts; construct deterministic fixtures under `tmp_path`.
- Exercise tests with an external writable pytest basetemp when the repository must remain read-only. On a Windows host where the shell is MSYS/Git Bash but `python` is native Windows, pass `--basetemp` as a native absolute path such as `C:/Users/<user>/AppData/Local/Temp/<unique-id>`; `/c/...` may be interpreted by `pathlib` as a path relative to the repository drive. Use a fresh UUID path, disable bytecode/cache output, and recheck repository status afterward.
- **Environment-dependent tests assert live state, not a fixture.** A test that calls a builder/loader with `root=None` (or no `tmp_path`) resolves against the LIVE repo/board and will break when that live state advances — even though nothing in the code regressed. When classifying "did this change introduce the failure," check whether the test reads live state; if so, the correct repair is usually to update the stale assertion to the current correct value or pin a hermetic fixture, NOT to change production code. Preserve every guard/redaction/fail-closed assertion when updating; only the environment-derived expectation (e.g. the current routing decision) should move.
- **Classify before fixing: pre-existing vs introduced without mutating the live worktree.** Export the committed baseline to an external scratch tree, overlay only the candidate tests when needed, and run the same focused command there. An identical baseline failure is pre-existing; a meaningful RED must fail at the intended behavioral assertion, not because the scratch tree lacks a new fixture, import, or artifact. Never use stash/reset in a strict read-only review or in a worktree another agent may be editing.
- Add deterministic probes for uncovered indexing, alignment, and transition bugs; retain the actual exception/output as evidence.

## Authority and concurrency boundary reviews

When the staged slice changes a steward, coordinator, worker runtime, provider adapter, or append-only ledger:

1. **Prove reachability, not just declarations.** Search the staged index for concrete model/provider call primitives, process launchers, and every caller. A lane's model name, quota allocation, prompt, or provider field is declarative until reachable from the entrypoint.
2. **Prove removed authority is really absent.** Check both the staged file list and filesystem for retired runtime/provider modules, then scan for stale imports and alternate call paths. A disabled lane alone is insufficient if another entrypoint can invoke the runtime.
3. **Exercise the hostile packet.** In an external temporary root, pass a packet containing runtime, model, prompt, and path fields. Verify zero dispatch, zero provider receipt, and zero artifact write. This probe must not use credentials or touch repository runtime state.
4. **Inspect lock scope.** For state machines, acquire the singleton/process lock before lane and state reads and hold it through claim, external action, logging, and durable state publication. For hash-chained JSONL, hold one writer lock across load → validate → previous-hash selection → append → flush/fsync.
5. **Test process concurrency, not only threads.** Thread tests can pass while separate schedulers or cron processes still race. Run a bounded multi-process append probe against an external temp directory and reload the complete chain afterward.
6. **Distinguish corruption safety from observability.** An unlocked best-effort activity stream may tolerate skipped malformed rows; authoritative state, dispatch claims, approvals, and provider receipts may not. Rate defects according to which evidence class is affected.
7. **Keep verification read-only.** Disable bytecode/cache output, use an external pytest `--basetemp`, never run a side-effecting production entrypoint, and recheck staged/unstaged status afterward.
8. **Bind every authorization grant to its use.** When a repair introduces a private capability/context, probe no-public-minting, missing/foreign/public context rejection, context minted for input A consumed against input B, mutation after grant, repeated context use, and caller-generated self-sealed manifests. A grant that checks only closure/type identity at consumption is reusable authority; require single-use semantics or immediate reload/reverification of contract/data/evaluator/manifest at outcome time. Treat caller-supplied hash manifests as self-consistency evidence, not approval, unless bound to an external frozen approval root.

## Windows no-agent scheduler boundary probes

For a fixed-path, no-agent Windows scheduler, test the *complete operational boundary*, not just the direct child command:

1. **Bind executable behavior, not launcher stubs.** Verify fixed absolute paths and hashes, but determine whether a small console launcher merely imports mutable Python source/site-packages. The release identity must bind the wrapper, manifest, runtime modules, dependency environment, and every enforcement executable used on timeout; a clean Git worktree is not a substitute for an expected release commit or complete artifact manifest.
2. **Probe child startup for credential/search-path reopening.** An allowlist-built parent `env` is insufficient if the invoked CLI reloads `.env`, `.op.env`, machine-managed scope, vault providers, plugins, or project fallbacks before dispatch. Inspect the actual pinned child implementation and use a child-process-only synthetic sentinel to prove whether fake credential names or `PATH` can reappear. Never print real values.
3. **Audit the exact command grammar and semantic gate separately.** Enumerate every CLI call site and require argument vectors with `shell=False`; then verify board/task/root identity, permitted activation statuses, canonical/real path comparison, claim/lease liveness, and stale-owner behavior. A path match alone is not a live-owner proof, and a blocked/review/cancelled activation card should not silently become runnable unless policy explicitly says so.
4. **Place the kernel singleton around the whole tick.** Cross-process-test the Windows lock, then inspect scope. Queue selection, materialization, publication, and external-comment reconciliation done before or after the lock can still overlap even when the core evaluator is serialized.
5. **Require pre-allocation output bounds and process-tree containment.** `capture_output=True` followed by a length check is not a hard bound. Stream with a cap, use a hard deadline, and test termination failures. Prefer a Windows Job Object with kill-on-close for descendant containment; if an enforcement tool is used, pin it and provide a verified direct-kill/final-wait fallback.
6. **Inject crash cutpoints after every durable boundary.** Cover staging publication, terminal receipt, ledger append, champion/summary publication, active-marker cleanup, and external Kanban update. Replay must complete missing downstream effects before queue advancement. Exercise the baseline-rejected/no-champion path explicitly.
7. **Verify exact external evidence, not marker presence.** Read back and hash the complete comment/body or remote object. A matching idempotency marker inside altered content must not be recorded as verified. Ensure a successful local experiment with a failed external update remains reconcilable on the next tick.
8. **Treat schedule and rollback evidence as release artifacts.** A schedule definition should be mandatory and bind job identity, command/args, wrapper and manifest digests, worktree, cadence/window, no-agent mode, overlap policy, prior-job disposition, and rollback steps. Read-only verification must fail closed when the definition is absent or only asserts `job_id` plus `max_per_tick`.

A credible `PASS` requires both static absence/reachability evidence and focused executable probes against the exact index export. Passing unit tests alone do not establish credential closure, release identity, provider authority closure, or cross-process serialization.

## Reporting

Return `PASS` or `BLOCK`. Rank findings by execution/safety impact, then silent evidence corruption, then research/test reliability. Every finding needs staged `file:line`, mechanism, consequence, and the smallest precise fix. Separate verification evidence from findings and state any limitations. For a clean review, keep the final concise: verdict, boundary proved, verification results, and confirmation that no files were changed.