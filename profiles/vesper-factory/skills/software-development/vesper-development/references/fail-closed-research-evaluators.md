# Fail-Closed Research Evaluators

Use this pattern when a research evaluator must enforce phase, provenance, and holdout boundaries through both CLI and direct Python APIs.

## Threat boundary

Python source and local data are not a sandbox against a caller who deliberately reimplements the arithmetic. The enforceable boundary is narrower and testable: the evaluator module must expose no API, helper, capability, row-bearing integrity result, or closure that bypasses the approved outcome path.

State that boundary explicitly during review. Do not claim that underscore names, dataclasses, or module globals are private authority.

## Architecture

1. **Use one atomic public outcome entrypoint.** It receives the requested phase plus exact contract/database identities. It must not accept caller-supplied rows, blocks, phase objects, or previously minted contexts.
2. **Verify before computation.** Verify the raw contract hash, declared phase, evaluator/code hash, database path and hash, data metadata, partition definition, purge/embargo rules, and any sealed-manifest bindings.
3. **Load internally.** Load the bound database and select only the contract-declared phase positions inside the authorized call. Never return rows or reusable authorization state.
4. **Keep outcome arithmetic local.** Create the arithmetic helper inside the authorized entrypoint at call time. Do not leave module-importable `_evaluate_*` or `_net_return` helpers that turn rows/blocks into outcomes. Avoid leaking labels/outcomes from public block records.
5. **Re-hash before return.** Recompute contract and database hashes after evaluation; discard results and raise if either changed. This closes the common verify-then-mutate TOCTOU path.
6. **Separate integrity-only CLI behavior.** Integrity verification may return counts and binding status, never rows, blocks, labels, or outcome metrics. Do not share a row-returning verifier with the outcome API.
7. **Block final outcomes until authority is real.** A self-consistent local manifest is not an external approval root. If no independently controlled approval/signature/registry exists, reject final outcome computation unconditionally while still allowing integrity-only checks.

## Required RED regressions

Capture each failure before production repair:

- old public phase/context grant works without complete contract proof;
- context from database A can be replayed against rows from database B;
- contract mutation between verification and result return escapes detection;
- database mutation between verification and result return escapes detection;
- a self-sealed or tampered final contract reaches outcome arithmetic;
- module inspection exposes an outcome helper, capability, label-bearing block, or row-bearing integrity helper;
- requested phase can evaluate positions from another partition.

Then require GREEN evidence for focused tests, the explicit project `tests/` suite, syntax, diff scope, secret scan, and an independent adversarial probe of the exact staged identity.

## Evidence rebinding after evaluator repair

An evaluator hash change invalidates old contract bindings even when the arithmetic is unchanged.

- Preserve the old contract and receipt as historical evidence; never silently overwrite them.
- Create a new versioned contract bound to the accepted evaluator hash and record why it supersedes the prior version.
- Re-run through the repaired atomic public API under the same frozen data, partitions, costs, seed, and hypothesis.
- Create a new receipt that cites the old receipt hash and reports whether all metrics reproduced exactly.
- Keep language selection-only/non-confirmatory unless a separately approved final gate exists.
- Freeze staged tree and binary diff hash, obtain independent read-only review, then commit and push only after PASS.

## Review pitfall

A reviewer can keep finding new bypasses if the threat model is left implicit. Before dispatch, define acceptance precisely: ordinary imports and normal function/closure inspection must expose no evaluator-provided bypass; manual reimplementation of arithmetic from readable local data is outside the module API boundary. If stronger protection is required, use a separately controlled service, signer, or approval root rather than Python naming conventions.
