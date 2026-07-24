# SPY Momentum CPU Slice 2 Independent Review v1

**Review date:** 2026-07-23  
**Verdict:** **HOLD — NOT ACCEPTED**  
**Scope:** `scripts/spy_momentum_cpu_experiment.py`, its focused tests, provenance manifest, and the minimum admission plan.

## Supersession notice

The earlier local verification established that the existing tests passed, hashes matched, SQLite was opened read-only, and the broader project suite was green in the project `.venv`. It did **not** establish that the tests covered all required fail-closed behavior. This independent review supersedes any earlier acceptance wording. Selection and final evaluation remain prohibited.

## Blocking findings

1. **Final-phase authorization is bypassable.** `evaluate_blocks()` can compute outcomes without a verified phase context. The accepted sealed-manifest shape is not bound to the approved contract, database, evaluator code, or freeze hashes.
2. **Contract and source provenance are not bound together.** Caller-supplied contract and database hashes are verified separately, but the contract does not have to declare the supplied database path/hash, evaluator hash, adapter metadata, or sealed-manifest hash.
3. **Purge and embargo are incomplete and not integrated into the executable path.** The helper is a one-sided position check rather than a complete validation of actual `[feature_time, label_exit_time]` intervals across partitions; the CLI path does not invoke the partition/purge/embargo gates.
4. **Missing and non-finite price data can fail open.** Null, NaN, and infinite required prices are not rejected before features/labels are built. NaN bypasses the existing `<= 0` checks.
5. **The focused tests do not prove the complete Slice 2 contract.** Missing cases include CLI-level provenance/phase binding, final-outcome bypass, malformed metadata, absent/duplicate source mapping, non-monotonic timestamps, non-finite OHLC, missingness/availability filtering, and complete deterministic output binding.

## Positive evidence retained

- Focused suite: `9 passed` on the reviewed candidate.
- Syntax check passed.
- Implementation SHA-256: `e03e15c8f229fdfa2143c4dec8af44895ec7d75e6cde8c9a8ba7b6754f1994f1`.
- Test SHA-256: `0d8706bacb50315a67447457f6f80d63f91592c461c25632c6fccfa98d091cae`.
- Provenance and frozen adapter hashes matched.
- SQLite uses `mode=ro` with `uri=True`.
- SQL scope is limited to `SPY` / `1day`.
- Focused feature and next-open label indexing are temporally correct.
- No protected-data writes, credentials, broker imports, or execution-system access were found.

## Required corrective acceptance gate

A successor may be accepted only after tests first demonstrate and implementation then enforces all of the following:

- Outcome evaluation requires an authenticated/verified phase context.
- Final manifest is cryptographically bound to the approved contract, database, evaluator code, and freeze hashes.
- The contract-declared provenance exactly matches CLI inputs.
- Partition, purge, and embargo checks operate on actual block intervals and run in the executable evaluation path.
- Null, missing, NaN, infinite, and non-positive required prices fail closed.
- Adversarial CLI tests prove phase mismatch, hash mismatch, provenance mismatch, malformed metadata/source mapping, non-monotonic timestamps, non-finite OHLC, outcome-bypass prevention, and deterministic output binding.
- Focused tests, full project suite, external compile, current hashes, protected-data immutability, and cleanup all pass.
- A fresh independent reviewer reports no security concerns or logic errors.

No selection, final holdout access, model promotion, data mutation, broker/risk/execution action, provider spend, or scheduler change is authorized by this review.
