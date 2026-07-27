# Python Authorization Boundary Review

Use this when a candidate claims an “atomic” fail-closed Python API: one public function verifies a contract and computes a guarded result. The reviewer must assume a direct-Python caller can import and compose every module-level symbol, including names beginning with `_`.

## Core rule

A correct public entrypoint is not sufficient if any importable helper can compute the guarded outcome from caller-supplied or previously verified data. The outcome computation must be closure-local to the authorized entrypoint, or otherwise non-importable.

## Probe matrix

| Probe | Expected result |
|---|---|
| Public happy path with exact contract/database/evaluator bindings | Computes only the contract-declared blocks for the caller phase. |
| Caller phase differs from contract phase | Reject before outcome computation. |
| Contract omits the caller phase partition | Reject before outcome computation. |
| Substitute database with its own valid hash | Reject as contract provenance mismatch. |
| Contract mutation after verification but before return | Reject; caller receives no partial outcome. |
| Database mutation after verification but before return | Reject; caller receives no partial outcome. |
| Final/sealed phase without separately governed approval | Reject before invoking any outcome evaluator. |
| Final CLI / integrity-only surface | May verify integrity, but must not compute or expose final outcomes. |
| Direct import/introspection inventory | No importable symbol may mint authority or compute guarded outcomes. |
| Helper composition: rows from database A + evaluator for database B | Must be impossible or reject; success is a blocker. |
| Helper composition: final rows from an integrity verifier + outcome evaluator | Must be impossible; success is a blocker. |
| Helper composition: rows captured before database mutation + outcome evaluator | Must be impossible; success is a blocker. |

## Minimal direct-Python recipe

1. Freeze and report the exact candidate identity before testing: branch/base SHA, staged tree or exact file hashes, and binary diff hash.
2. Put probe scratch outside the repository in the authorized temporary area. Use the project interpreter, `PYTHONDONTWRITEBYTECODE=1`, and native OS temp paths.
3. Load the exact candidate module with `importlib.util.spec_from_file_location`; do not rely on an installed package copy.
4. Build two minimal but valid fixtures (for example two SQLite databases) plus a contract/manifest bound only to fixture A.
5. First prove the public path: happy path, wrong phase, missing partition, cross-database substitution, contract TOCTOU, database TOCTOU, and final-outcome refusal.
6. Instrument the outcome evaluator (for example monkeypatch it to record invocation) to prove the final refusal happens before evaluation, not after an outcome was already computed.
7. Inventory module attributes that verify, load, build, mint, or evaluate. Attempt direct composition with every available helper. Treat any successful guarded outcome as a fail-closed rejection.
8. Remove scratch, verify absence, and re-check the frozen identity before delivering the verdict.

## Session evidence pattern

In the SPY phase-authorization review, the public `evaluate_phase_outcomes` path correctly rejected cross-database substitution, contract/database TOCTOU, and final evaluation before calling the evaluator. The candidate still failed closed because module-level helpers remained importable:

- `_verify_phase_integrity(...)` returned final rows/partitions.
- `_evaluate_blocks(...)` computed final outcomes from those rows.
- `_evaluate_blocks(...)` also computed outcomes for an uncontracted substitute database and for stale rows captured before a database mutation.

That combination demonstrates the durable lesson: underscore naming is not a boundary, and “no reusable context object” is not enough when the verifier and evaluator can be composed directly.