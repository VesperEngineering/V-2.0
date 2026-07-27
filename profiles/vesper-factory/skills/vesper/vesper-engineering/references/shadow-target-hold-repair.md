# Step 3 shadow-target HOLD repair pattern

Use this after an independent review rejects an inert portfolio-target candidate for unbound inputs, incomplete liquidation economics, caller-minted authority, weak public invariants, or representation-dependent hashing.

## Repair contract

Keep the candidate research-only and disconnected from signals, orders, risk, brokers, persistence, and runtime wiring. Preserve active scoring and signal methods byte-for-byte.

### Upstream authority root

- Add the reviewed compatibility-manifest universe identity to every forecast record.
- Populate it only from the accepted compatibility manifest; do not accept a per-call universe override.
- Require one common universe identity across the forecast set.
- Remove caller-supplied approved-universe values and matching hashes from the target builder. A caller-provided value plus its caller-provided hash proves only self-consistency.

### Holdings, cash, costs, and constraints

- Accept actual current holdings weights; normalize them into an immutable symbol-sorted tuple.
- Derive current cash exactly as `1 - sum(holdings)` and embed both holdings and cash in the target.
- Compute domain-separated holdings and cash hashes internally from the embedded content.
- Emit target lines for the union of forecast symbols and current holdings.
- For a holding with no forecast, emit `liquidation_no_forecast`, zero target weight/notional, unavailable forecast contributions, and the full liquidation cost when a rate exists.
- Bind transaction-cost assumptions internally to their explicit numeric rate. Changing the rate must change the assumption hash.
- Represent fixed constraints as actual fields (`top_n`, threshold, long-only, equal-weight) and compute their identity internally.

### Canonical hashing

- Domain-separate every canonical payload with a schema/version string.
- Do **not** cast generic integers through binary64. Encode integers as exact, type-tagged canonical decimal strings so values beyond `2**53` cannot collide; preserve booleans separately from integers.
- Normalize only fields whose domain is semantically floating-point (forecast scores, weights, rates, thresholds, notionals) and encode them with `float.hex()` semantics. This retains intentional `1`/`1.0` equivalence without collapsing integer identities such as `top_n`, rank, or count.
- Normalize signed zero to positive zero.
- Sort forecast records by symbol before hashing and serialize timestamps in one stable ISO form.
- Reject duplicate, skipped, or score-incoherent ranks. Required rank order is raw score descending, then symbol ascending.
- Embed the full validated forecast tuple in the aggregate target. Recompute the forecast-set digest from that immutable projection in `__post_init__`, require each line's raw/standardized contributions to match its embedded forecast, and permit `liquidation_no_forecast` only when the symbol is absent from the embedded tuple.

### Public-schema fail-closed checks

`frozen=True` is not enough. Both exported line and aggregate dataclasses need substantive `__post_init__` validation, including direct construction and `dataclasses.replace`:

- finite/nonnegative weights, notionals, costs, turnover, exposure, concentration, and portfolio value;
- positive integer `top_n`, nonnegative integer selected count, and exact selected-line count;
- deterministic unique line ordering;
- exact equal weights and target notionals;
- recomputed gross/net/concentration/turnover and complete per-line costs;
- holdings/cash, cost-assumption, and constraint hashes recomputed from embedded content;
- consistent selected/threshold/outside/liquidation reasons and contribution availability;
- blocked/infeasible/diagnostic consistency;
- closed research/shadow/no-authority fields.

Reconstruct nested frozen line records at the aggregate boundary. This catches `object.__setattr__` tampering that aggregate arithmetic alone may miss (for example, a mutated confidence field).

## TDD sequence

1. Add REDs for each independent reviewer exploit before changing production code.
2. Add the forecast universe identity and prove forecast tests green.
3. Run the target exploit tests and preserve their expected RED output.
4. Implement the smallest closed-schema repair and make target tests green.
5. Add mutation-bypass and signed-zero REDs if not already covered; then repair and rerun.
6. Run forecast, target, and legacy model/signal tests together, then the practical suite.

## Freeze and verification

- Stage exactly the authorized paths; require no unstaged or untracked repository files.
- Record HEAD, staged tree, and staged binary-diff SHA-256.
- Prove active scoring and signal method source blocks are byte-identical to base.
- Run in-memory compilation, `git diff --cached --check`, and an added-line security scan.
- Create a fresh external verifier with `tempfile.mkstemp(prefix="hermes-verify-", suffix=".py")`.
- The verifier should exercise liquidation cost coverage, content-bound identities, rank rejection, canonical numeric hashing, public-schema contradiction rejection, and exact staged identity.
- Generate the tempfile first, then execute that exact `.py` path directly in a separate terminal invocation. Do not hide the verifier behind a wrapper process that merely launches it as a child: verification-aware runtimes may otherwise report that no verification command was detected even when the child passed.
- Preserve the direct invocation's structured verification evidence when available. Label the result **ad-hoc evidence**, never canonical-suite green; a focused pytest command is separate **canonical suite evidence** only when it was actually run.
- Delete the verifier after execution, confirm both the generated tempfile and any seed/template are absent, and recheck staged/unstaged/untracked identity after cleanup.
- Any source, test, or staging change invalidates both identities and the prior ad-hoc receipt.

## Final independent re-review gate

A repaired candidate receives **PASS** only when the fresh reviewer independently confirms all of the following against one unchanged staged identity:

1. exact branch, base/HEAD, staged tree, staged binary-diff SHA-256, expected staged-path set, and zero unstaged/untracked paths before testing;
2. focused forecast/target/legacy-model tests and the declared practical suite in the project interpreter with external Windows temp roots;
3. syntax/diff checks, added-line security scan, byte/AST preservation of active scoring and signal behavior, and no runtime caller or operational/persistence wiring;
4. fresh adversarial probes covering every prior HOLD family: holdings/cash binding, complete liquidation economics, cost and constraint identities, rank coherence, large-integer canonical identity, semantic float equivalence, domain/type/framing separation, embedded forecast digest, line/forecast linkage, public `dataclasses.replace` contradictions, mutation-bypass revalidation, closed authority fields, and no writes;
5. identical staged identity after probes and cleanup, plus verified absence of every reviewer scratch path.

Keep externally supplied classification, dataset, adjustment, and run-manifest hashes classified honestly as carried provenance claims. Their replaceability is not a self-consistency defect when the contract does not claim they are content-derived; do not blur them with internally derived holdings, cash, cost, constraint, or forecast-set identities.

### Reviewer-probe defects are not candidate defects

The independent verifier is review code and can itself contain a bad expected value or target a nonexistent test filename. Fail closed, but classify precisely:

- If a probe assertion is wrong, recompute the expected value from the declared formula (for turnover, include both asset changes and cash change), correct only the external scratch verifier, and rerun it from the beginning against the unchanged staged identity.
- If a test target does not exist, clean the failed attempt's external temp root, discover the actual tracked test filenames, and rerun with a fresh root.
- Never edit product or candidate tests to satisfy reviewer-owned mistakes.
- Preserve the setup/probe-error attempt in the report, but base PASS/HOLD only on a subsequently completed admissible run with unchanged candidate identity.
- Shell cleanup must execute even when pytest/probes fail; do not let `set -e` skip cleanup before status capture.
