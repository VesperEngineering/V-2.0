# Capability / Provenance Authorization Repair Audits

Use this reference when a staged repair claims to close an authorization or provenance bypass by introducing a verified phase/context/capability, hash-bound contract, database/evaluator freeze, or sealed manifest.

## Core rule

Verify **grant-to-use binding**, not only grant construction. A repair can correctly hide a module-scope minting symbol and still fail closed if the granted object is reusable against different rows, mutable inputs, or caller-generated manifests.

## Review boundary

1. Freeze the exact index before probing: HEAD, staged name/status, index blob IDs, full index tree ID, staged binary patch SHA-256, unstaged/untracked state.
2. Export only the staged paths under review to an external scratch tree; hash exported files and run tests/probes against that export.
3. Use the project interpreter and external temp/basetemp. Keep review scratch outside the worktree and remove it afterward.
4. Re-freeze the same identities before verdict. Report only the frozen candidate, not concurrent working-tree drift.

## Adversarial probe matrix

For each new authorization API, exercise:

- **No public minting:** the old public context/capability symbols are absent and the authorizer requires complete proof.
- **Missing context:** outcome computation without a context fails closed.
- **Public/foreign context:** a same-shaped public value or context from another module/process fails closed.
- **Unknown phase:** unsupported phase names fail closed.
- **Hash mismatch:** wrong contract, database, evaluator, manifest, or freeze hash fails closed.
- **Phase mismatch:** a contract for phase A cannot authorize phase B.
- **Path/metadata mismatch:** declared database path and adapter metadata must match the actual bound database.
- **Cross-input context reuse:** mint a context for input A, then consume it against rows/blocks/input B. This must fail.
- **TOCTOU mutation:** mutate contract/database/manifest after grant but before evaluation. Evaluation must fail or re-verify.
- **Repeated use:** consume the same context twice if the contract implies one-shot admission. This must fail when single-use is required.
- **Self-sealed final manifest:** alter the contract, generate a fresh manifest binding the altered hash, and attempt final admission. Without an external approval root this is self-consistency, not approval.

## Fail-closed design expectations

A credible repair does at least one of the following:

- makes authorization single-use and binds it to immutable evaluated input;
- has the authorized evaluation path load and re-verify contract/data/evaluator/manifest immediately before computing outcomes;
- removes public outcome evaluators and exposes only one fail-closed evaluator entrypoint;
- binds final admission to an external frozen approval registry, signature, or reviewer receipt rather than caller-supplied manifest bytes alone.

A context object that carries only `phase` plus a private capability is a reusable bearer token if the consumer does not verify the exact rows/database/contract at use time.

## Reporting language

Classify demonstrated grant/use separation as a security finding, not a style concern. State the exact producer and consumer lines, the probe that crossed the boundary, and the smallest safe fix. Distinguish:

- **internal consistency:** all caller-supplied hashes match each other;
- **approval:** hashes match an external frozen authority;
- **evaluation binding:** the outcome computation uses the same verified bytes that authorized it.

A green focused or full suite does not clear the repair if these adversarial probes are absent or fail.