# SPY Slice 2 admission-gated CPU experiment cycle

Session-derived workflow for the bounded SPY momentum CPU research track in V20.
Captures the patterns that survived independent fail-closed review; reuse for any
admission-gated research evaluator slice.

## 1. Reviewer findings → acceptance matrix first

Convert every independent-review finding into an explicit matrix against the prior
review document (`spy_momentum_cpu_slice2_review_v1.md`) BEFORE editing. Each gate
needs a failing-first regression test; do not start production edits from the review
narrative alone.

## 2. Contract-bound outcome authorization for every API surface

A leading underscore is not an authorization boundary in Python. A module-level
`_VerifiedPhase` type and `_PHASE_CAPABILITY` sentinel remain importable and can be
used to forge an accepted context. Likewise, `require_phase_access("selection")`
without verified inputs bypasses provenance even when the CLI verifies it first.

The durable pattern is:

- Prefer **no reusable authority context at all**. A context that is minted after
  verification can be reused with rows from another database or after inputs
  change. Expose one atomic outcome entrypoint instead.
- The outcome entrypoint must verify the exact raw contract hash, declared phase,
  database path/hash/metadata, evaluator code hash, and frozen bindings; load the
  bound rows itself; select only the contract-declared phase blocks; compute
  outcomes locally; then re-hash contract and database before returning. If drift
  is detected, raise before any outcome escapes.
- Do not accept caller-supplied rows, blocks, or a phase-only grant. Do not return
  rows, blocks, or reusable authority.
- Keep net-return/outcome arithmetic local to the authorized entrypoint. An
  importable `_evaluate_blocks`, `_net_return`, integrity verifier returning rows,
  or module-level/closure minting capability is still a bypass. A leading
  underscore is naming, not access control.
- Keep the CLI integrity-only. Its verification path may return a bounded row
  count, but must not return verified rows/blocks or expose an outcome helper.
- For final outcomes, complete sealed-manifest self-consistency is necessary but
  not an external approval root. If no independently governed approval root
  exists, reject final outcome computation unconditionally even when a caller can
  create a self-consistent contract and manifest.

Regression tests must first reproduce the old bypass, then prove that: the old
context/evaluator/helper names are absent; the public outcome function has no
closure capability; caller-supplied rows are rejected; cross-database substitution
fails; contract and database mutation between verification and return are caught;
caller phase and contract partition mismatches fail; final outcomes fail before
any row/block evaluation; and the integrity-only CLI cannot leak rows or outcomes.
For TOCTOU tests, wrap a non-outcome seam such as partition construction, mutate the
contract/database after the initial verification, and assert that the post-hash
check prevents a result from returning.

Python source and local market data are not a cryptographic sandbox: a caller with
filesystem access can always reimplement arithmetic. The enforceable module
boundary is that no importable or ordinarily introspectable helper/API supplied by
this evaluator bypasses its atomic admission checks. State this threat model
explicitly so reviewers test the real contract rather than an impossible claim.

## 3. Source-map validation must be complete, not representative

Validating only `source_sha256` accepts rows with NULL `source_ticker` /
`source_as_of_date` / `source_key`. Validate EVERY declared provenance column for
every loaded row: non-null AND non-empty-string. The regression probe inserts a row
with only the hash populated and must be rejected.

## 4. Environment-bound verification gates

- Full-suite gates run only under the explicit project interpreter
  (`C:\Users\bgonn\Desktop\v20\.venv\Scripts\python.exe`) with `PYTHONPATH=.` and
  `PYTHONDONTWRITEBYTECODE=1`.
- A reviewer HOLD whose failures are missing-dependency imports under system
  Python (e.g. `yfinance` absent) is an environment defect, not a candidate
  defect: verify interpreter + dependency, confirm frozen identity, re-dispatch one
  environment-bound re-verification. See `python-testing-windows` for the general rule.

## 5. Worktree → freeze → review → ff-only integration

1. Do repairs in `git worktree add -b agent/<slice> .worktrees/<slice> main`.
2. RED run, GREEN run, focused suite, then full suite with external basetemp and
   verified cleanup (`rm -rf` + `test ! -e` before exiting).
3. Stage exactly the allowlisted paths; record `git write-tree` + binary
   `git diff --cached` SHA-256 as the frozen identity.
4. Independent review verifies frozen identity before AND after its tests.
5. On PASS: commit in the worktree, verify main is at the candidate's parent, then
   `git merge --ff-only <sha>` and post-merge re-verify.

## 6. Do not ship unstable environment workarounds

The embedded uv-Python Tcl/Tk root intermittently failed to read its own script
files during full-suite runs while a focused GUI file passed alone. Attempted
path-stabilization patches could not be independently reproduced as stable; they
were discarded (`git restore --staged --worktree`) rather than integrated. Rule:
a runtime flake that neither blocks the canonical suite nor reproduces under
focused re-run gets diagnosed, reported as a residual environment note, and the
workaround is reverted — never commit an unverified stabilization.

## 7. SQLite admission inspection recipe

Read-only adapter checks that reviewers accepted as evidence:

- Connect with `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`.
- Schema differs from intuition: `ohlcv_source_map` is keyed by exact
  `(ticker, timestamp, timeframe)` — there is no `start_timestamp`/`end_timestamp`
  range column. Read the schema from `sqlite_master` before writing coverage SQL.
- Required zero-count checks: duplicate timestamps, non-monotonic transitions,
  NULL/non-positive OHLC, missing/malformed source-map rows.
- Historical stability: `ATTACH` prior adapter snapshots read-only and count
  shared-timestamp OHLC mismatches; zero mismatches is admission evidence, not
  proof of external build inputs.
