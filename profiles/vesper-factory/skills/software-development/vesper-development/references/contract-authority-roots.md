# Contract authority roots and atomic evidence APIs

Use this when a V20 research API gates forecasts, outcomes, phase access, provenance, or protected evidence.

## Authority-root rule

Checking `actual == expected` is not authorization when the same caller supplies both values. The same defect appears when a caller supplies an “approved” universe together with the symbols, or a feature hash together with its expected hash.

Compatibility and approval must originate outside the per-call request, for example:

- a frozen model-companion manifest independently reviewed with the model;
- a detached signature verified by a pinned public key;
- an immutable reviewed registry or receipt;
- a code-pinned compatibility identity where circular hashes are avoided.

The authority root should bind the model bytes, ordered feature schema, admitted universe, horizon/target semantics, and any other compatibility claims. Per-run calls may supply changing dataset/run identities, but they may not self-approve model compatibility.

## Atomic outcome boundary

For outcome-producing research APIs:

1. Accept paths and independently rooted expected identities, not preloaded rows or caller-minted phase objects.
2. Verify contract, phase, database, evaluator, freeze, and sealed-manifest bindings before computation.
3. Load exact inputs inside the authorized entrypoint.
4. Evaluate only contract-declared partitions.
5. Re-hash mutable inputs before returning to reject TOCTOU drift.
6. Return outcomes only—never rows or reusable authority.
7. Avoid module-exposed helper APIs that directly turn verified rows/blocks into outcomes.
8. Keep final outcomes unconditionally disabled until a real external final-approval root exists.

Python source and local data are not a sandbox against a caller who manually reimplements arithmetic. The enforceable boundary is that the governed module exposes no bypass outcome API/helper and makes all supported outcome paths fail closed.

## Forecast compatibility pattern

For inert shadow forecasts, use a frozen model-companion compatibility manifest established separately from each forecast call. Bind at minimum:

- model artifact SHA-256;
- ordered feature columns and deterministic feature identity;
- approved universe and deterministic universe identity;
- forecast horizon and target definition;
- schema version.

At generation time, load and validate the companion manifest against current model bytes and imported feature schema. Reject symbols outside the manifest universe. Do not accept per-call `approved_universe`, `expected_feature_hash`, or equivalent self-authorization.

## Review regressions

Add RED tests for:

- caller supplies matching arbitrary expected/actual hashes;
- caller self-approves an arbitrary symbol;
- cross-database context reuse;
- contract/database mutation after verification;
- final self-sealing without an external approval root;
- importable helper bypasses;
- manifest/model/feature/universe mismatch.
