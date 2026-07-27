# No-helper atomic authorization audit

Use this for an independently frozen Python candidate whose security claim is: one atomic authorization-and-outcome entrypoint, no reusable capability token, no row/block outcome helper, and no final-phase outcome path.

## Boundary to state first

Treat ordinary imports, signatures, module attributes, closures, tracebacks produced by normal calls, and direct calls to exposed functions as the review surface. Python is not a sandbox: constructing functions from code objects, rewriting globals, tracing frames, or manually reimplementing arithmetic is outside this contract unless the requester explicitly includes it. Do not reject a candidate merely because it exposes data-loading or block-position primitives from which a caller could manually rewrite the outcome formula. Reject when an exposed callable performs that formula or an integrity helper returns the protected rows/blocks.

## Freeze the exact staged candidate without writing Git objects

Use `GIT_OPTIONAL_LOCKS=0`. Record base/HEAD, branch, status, staged paths, unstaged paths, and the complete staged binary-diff SHA-256. If the expected candidate tree object already exists, avoid `git write-tree` in a strict read-only audit:

```bash
git cat-file -t <candidate-tree>                 # must be tree
git diff --cached --quiet <candidate-tree> --   # index must match exactly
git diff --cached --binary | sha256sum
git diff --cached --check
```

Require the staged allowlist and no unstaged tracked delta before importing the worktree source. Re-run the same identity checks immediately before the verdict.

## Static inventory

Parse the staged blob with `ast` and inventory every top-level class/function. Locate all outcome arithmetic and all return statements carrying protected outcome fields. The intended shape is:

- one public atomic entrypoint validates phase, contract hash/content, provenance, database hash, partition contract, and final policy;
- outcome arithmetic exists only inside that entrypoint (a nested function created during the admitted call is acceptable under this boundary);
- reusable helpers such as `evaluate_blocks`, `_net_return`, `require_phase_access`, phase capability objects, and row-returning phase-integrity helpers are absent;
- block values omit the realized label/outcome;
- CLI final integrity output is a fixed non-outcome schema.

Search the complete repository for callers and stale aliases, not only the changed module.

## Import/introspection probe

Import the exact candidate module with bytecode writes disabled. Inspect `vars(module)` and classify every module-local callable. Verify:

1. forbidden helper/capability names are absent;
2. the atomic entrypoint has no `rows`, `blocks`, or reusable authority-context input;
3. `entrypoint.__closure__ is None` and no module-local function unexpectedly retains a closure;
4. the block type has no realized-label field;
5. outcome-bearing source occurs only in the atomic entrypoint;
6. nested code objects are not themselves exposed as callable module attributes;
7. contract/final-integrity helpers return `None` (or a bounded non-row result), never protected rows or blocks.

Name and print the callable inventory in the probe result so a later reviewer can see what was actually inspected.

## Runtime adversarial matrix

Use self-created external fixtures and assert exact errors/results:

- **Cross-database substitution:** a contract bound to database A rejects database B even when B has a caller-supplied matching hash.
- **Phase partition isolation:** a multi-partition contract returns outcomes only for the requested admitted phase.
- **Contract TOCTOU:** mutate the contract after rows/blocks are built; the pre-return rehash rejects it.
- **Database TOCTOU:** mutate the database after loading/building; the pre-return rehash rejects it.
- **Final fail-closed ordering:** provide a structurally valid self-sealed final contract/manifest, replace row loader and block builder with sentinels, and require the outcome call to reject for missing external approval with both sentinel counts still zero.
- **Final CLI integrity-only behavior:** the same valid final inputs may pass integrity verification, but stdout must equal the exact allowed summary shape and contain no rows, blocks, returns, labels, or outcome payload.

Do not treat monkeypatching a verifier to force success as a product bypass test; Python module globals are mutable and the review boundary is not a hostile in-process sandbox. Sentinel monkeypatches are appropriate only to prove control-flow ordering.

## Windows-safe probe execution

Set `PYTHONDONTWRITEBYTECODE=1`, route `TEMP`, `TMP`, `TMPDIR`, pytest `--basetemp`, and `PYTHONPYCACHEPREFIX` to native external paths, and disable pytest's cache provider. SQLite readers may retain handles until interpreter exit even when assertions pass. Run the adversarial probe as a child process, then remove its fixture root from the parent after the child exits. Report an initial same-process cleanup lock as harness evidence, rerun with parent cleanup, and do not patch candidate source for it.

## Acceptance

PASS only when all of the following are true:

- exact candidate identity is unchanged;
- no exposed callable is an outcome bypass or final-row leak;
- cross-database, partition, TOCTOU, and final-ordering probes pass;
- focused tests, the declared broad non-GUI/non-flaky suite, syntax checks, diff checks, and added-line security scan pass;
- external probe artifacts are removed and the worktree has no new unstaged/untracked changes.

Return HOLD for any exposed bypass, final-phase outcome path, identity drift, incomplete required gate, or cleanup/worktree mutation that cannot be attributed and removed. Keep the final verdict strict and distinguish a harness-only retry from a candidate defect.
