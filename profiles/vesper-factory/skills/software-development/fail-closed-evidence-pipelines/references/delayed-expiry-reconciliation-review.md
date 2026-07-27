# Delayed-Expiry Reconciliation Review

Use this recipe when a durable workflow must resume or replay **after its original contract expires** without turning expiry bypass into first-admission authority.

## Core invariant

Expiry has two distinct meanings:

- **First admission:** the contract must be live and unexpired.
- **Reconciliation:** an expired contract may be parsed only to recover immutable identity for a lifecycle that was already durably admitted.

Do not make the ordinary validator accept expired contracts. Add an explicit reconciliation validator that skips **only** the live-expiry comparison. It must retain exact schema/profile checks, bounded paths and tools, required denials, canonical hashing, issue/expiry window shape, and the future-issued check.

A persisted contract file, receipt, candidate, or evaluation artifact is not proof of prior admission. Reconciliation becomes available only after the durable lifecycle snapshot validates completely and its contract hash exactly equals the canonical contract hash.

## Controller pattern

```python
reconciliation = validate_contract_for_reconciliation(contract)
identity = reconciliation.payload["task_id"]
try:
    snapshot = store.snapshot(identity)  # validates state + full event chain
except LifecycleNotFound:
    validated = validate_contract_for_admission(contract)  # expiry enforced
except LifecycleCorruption:
    raise  # fail immediately
else:
    if snapshot["contract_hash"] != reconciliation.contract_hash:
        raise LifecycleError("persisted contract identity changed")
    validated = reconciliation
```

If the store exposes one broad lifecycle exception for both absence and corruption, corruption must still be unable to produce progress: either fail it immediately, or route through admission validation and ensure the very next durable operation revalidates the snapshot before any artifact, dispatch, evaluation, or receipt effect. Test both expired and still-live corrupt rows.

Persisted-contract loaders may use reconciliation validation to compare immutable bytes across a retry, but that loader must not decide admission. The controller/store boundary owns that decision.

## Required adversarial matrix

Exercise the real public entry point with one injected timezone-aware clock.

1. **Completed replay after expiry**
   - Complete the run at `t0`.
   - Save exact contract/candidate/evaluation/receipt bytes and receipt hash.
   - Advance past expiry.
   - Replay through the public scheduler/runner.
   - Require `PASS`, `replayed=true`, the original receipt hash, byte-identical immutable artifacts, one ledger row, and all authority flags false.

2. **Crash after evaluation, resume after expiry**
   - Crash after durable evaluation/decision but before review-ready/receipt publication.
   - Require durable decision state and no receipt before restart.
   - Advance past expiry and call the same public entry point.
   - Require only the legal lifecycle suffix, no duplicate candidate/evaluation/event, and a final review-gated receipt.

3. **No lifecycle means no first admission**
   - Persist the contract, then crash before lifecycle creation/admission.
   - Advance past expiry.
   - Retry and require expiry rejection, zero lifecycle/event rows, and no candidate/evaluation/receipt.

4. **Lifecycle activation gates**
   - Missing lifecycle row.
   - Malformed state.
   - Broken event hash/previous-hash chain.
   - Missing event suffix or state/event disagreement.
   - Structurally valid lifecycle carrying the wrong contract hash.
   - Each must reject reconciliation; wrong/corrupt state must remain unchanged.

5. **Future-issued contracts**
   - Test both admission and reconciliation validators.
   - Also precreate an exact-hash lifecycle row and prove the controller still rejects the future issue time.

6. **Cross-artifact bindings after expiry**
   - Raw receipt hash corruption.
   - Internally rehashed receipt whose candidate bytes/hash no longer match the durable candidate.
   - Valid-profile contract timestamp shift that changes the contract hash.
   - Corrupt lifecycle chain.
   - Internally consistent lifecycle chain under a different contract hash.
   - Raw candidate-byte mutation, including semantic-equivalent newline changes.
   - Raw evaluation-byte mutation that preserves parsed JSON semantics, such as an appended newline, harmless whitespace, or key-order change; also test one semantic result mutation separately.
   - Require explicit `HELD`/exceptional failure and false execution/promotion authority for every case.

7. **Authority closure**
   - Compare base and candidate AST imports/calls for changed production files.
   - Scan added lines using exact-word matches for broker, order, scheduler, promotion, deployment, risk, provider, and live authority terms.
   - Inspect actual receipt, review-packet, and ledger outputs; require all execution/operational/promotion fields false and the complete denial set retained.
   - A static false constant alone is not sufficient; assert the emitted artifacts.

## Bounded final-audit execution order

A final audit is binary only when every required gate actually ran. Under a bounded tool/session budget, front-load the gates that can independently invalidate the release:

1. Freeze source, evidence roots, live schedule/profile hashes, and the exact verdict scope.
2. Build and verify the external Git snapshot.
3. Run the focused test count, critical Ruff/compile/diff checks, and the public delayed-expiry probes—especially raw-byte-only candidate **and evaluation** mutations—before reconstructing a long happy-path narrative.
4. Run one schema-smoke check, then validate lifecycle/receipt/ledger/cross-copy evidence with restartable scratch scripts whose outputs are saved by phase.
5. Join supervised and natural scheduler provenance, including the exact pre-fire job definition and terminal execution record for auto-retiring one-shots.
6. Recompute closing source/evidence/schedule/profile manifests and compare them to opening state.

Reserve enough calls for steps 3 and 6. If a ceiling interrupts any required item, classify the result as an incomplete-audit `HOLD` and name the missing gates; do not infer them from prior reports or green artifacts.

## External exact snapshot for an uncommitted candidate

Do not test the shared dirty worktree when the review requires no source writes.

1. Record source `HEAD`, tree, `git status --short --untracked-files=all`, exact path allowlist, and:

   ```bash
   git diff --binary --full-index HEAD -- <paths...> | sha256sum
   ```

2. Export that exact patch outside the repository.
3. Create an independent external clone with Git metadata (not a plain archive when tests call Git):

   ```bash
   git -c core.autocrlf=false clone --no-local --no-hardlinks --no-checkout <repo> <scratch>/repo
   git -C <scratch>/repo config core.autocrlf false
   git -C <scratch>/repo checkout --detach <base-sha>
   git -C <scratch>/repo apply --binary <scratch>/candidate.patch
   ```

4. Require external `HEAD`/tree and binary-diff SHA to match the source freeze. Compare the reviewed files byte-for-byte.
5. Run pytest with the project interpreter, `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, and a unique native same-drive external `--basetemp`. Put Ruff cache and `PYTHONPYCACHEPREFIX` outside the clone as well.
6. After every gate, recompute source and snapshot identities. Bind the verdict to the exact binary-diff SHA and allowlist.

If a new unrelated untracked file appears during review, do not delete or absorb it. Record its path/metadata, prove the tracked diff and reviewed file bytes did not move, and state whether the verdict is scoped only to the frozen allowlist. If the user required whole-worktree identity rather than a scoped patch, treat any unexplained drift as `HOLD`.

## Minimum evidence to report

- Verdict: exactly `PASS` or `HOLD`.
- Base commit and exact binary-diff SHA-256.
- External snapshot path and identity match.
- Focused suite count/result plus adversarial probe count/result.
- Critical Ruff, compile, and `git diff --check` results.
- Concrete admission/reconciliation/binding/authority assertions.
- Final source/snapshot drift check and any unrelated untracked movement.
