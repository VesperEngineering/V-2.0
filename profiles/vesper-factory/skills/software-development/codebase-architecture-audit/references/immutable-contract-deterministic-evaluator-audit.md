# Immutable Contract and Deterministic Evaluator Audits

Use this reference when a proposed autonomous/research loop depends on an immutable task contract, a bounded machine-produced candidate, a frozen fixture/baseline, and a deterministic evaluator.

## 1. Freeze the authority and source boundary

Before judging implementation details:

1. Read the canonical board/tracker and governance hierarchy. A draft goal is not dispatch authority; goal creation, task creation, and dispatch are separate facts.
2. Record full `HEAD`, source tree ID, branch, worktrees, and the blob IDs of the contract/design files being audited.
3. Snapshot tracked diff, index diff, and untracked paths separately. Save the exact sorted untracked path list in an approved external temp location as well as its digest; a digest alone cannot attribute a concurrent change.
4. Recheck all four surfaces at the end. If only untracked state changed concurrently, bind source findings to the frozen commit and report the untracked delta separately; do not claim whole-worktree equality.
5. Treat implausible search misses as unverified. Confirm tracked-file existence/absence with `git ls-files`, `git grep`, `git show <sha>:<path>`, or direct reads.

## 2. Audit byte-level contract immutability

A field list is not an immutable contract. Require all of the following:

- exact top-level and nested key sets; unknown and missing keys fail;
- a bounded read before parsing (byte limit and nesting/item limits);
- strict JSON parsing that rejects duplicate keys, BOM/trailing content, and `NaN`/infinities;
- exact booleans and integers (never accept Python's bool-as-int coercion);
- canonical text, timestamp, digest, identifier, and path formats;
- canonical JSON rules (`sort_keys`, compact separators, ASCII/UTF-8 choice, `allow_nan=False`);
- a semantic ID derived from canonical content excluding only the self-ID field;
- a separate raw-byte SHA-256 recorded by the controller/receipt;
- full source revision and source-tree identity;
- exact input and output paths with schema IDs, hashes, and size bounds;
- contained paths with explicit rejection of absolute paths, `..`, symlinks, junctions, and reparse points;
- expiry, retry, review, stop-condition, and closed-authority fields with exact semantics.

Never let a worker's self-asserted authority block prove enforcement. The launcher/controller must observe and bind the actual tools, provider request, workspace, output, and terminal state.

## 3. Prefer a data DSL over generated code

The smallest safe candidate is data, not source code. A good first-loop DSL has:

- one allowlisted family;
- a fixed, exact feature key set;
- bounded integer parameters (for example basis-point weights);
- a normalization invariant such as `sum(abs(weights)) == 10000`;
- no paths, imports, commands, expressions, classes, plugins, URLs, or arbitrary feature names;
- no timestamps or runtime-generated IDs in evaluator semantics;
- a candidate ID derived from canonical semantic content;
- bounded explanatory strings that are ignored by the evaluator.

Using integers avoids non-finite values and cross-platform float drift. Keep protocol controls such as universe, `top_k`, cost model, tie-breaker, and thresholds in the immutable contract/fixture, not under candidate control.

## 4. Freeze fixture and baseline as one suite

A fixture is frozen only when a manifest binds every file and semantic dependency:

- fixture path, byte size, SHA-256, schema version, and semantic ID;
- baseline candidate path/hash/ID;
- golden baseline metrics path/hash;
- evaluator protocol ID and evaluator source hash;
- explicit non-production/non-promotable scope;
- canonical row order, unique primary key, train/test semantics, and label horizon;
- fixed cost, turnover, allocation, tie-break, drawdown, coverage, and concentration rules.

The evaluator must recompute the baseline from the fixture and compare it exactly with the golden baseline before evaluating a candidate. A golden file alone is not a baseline proof.

For a lifecycle canary, use a small but adversarial fixture: multiple sessions, instruments, and groups/sectors; score ties; turnover changes; a drawdown; and a concentration hazard. State explicitly that a visible synthetic fixture proves plumbing and evaluator behavior, not empirical predictive skill. Blind holdout claims require an enforced filesystem/tool boundary.

## 5. Make the evaluator pure and exact

Separate the pure semantic evaluator from the timestamped lifecycle receipt.

The pure evaluator should:

1. accept already strict-parsed contract, candidate, fixture, and baseline objects;
2. verify every ID/hash/schema relation again;
3. recompute scores and portfolios rather than trusting producer metrics;
4. use integer arithmetic or `fractions.Fraction` for averages, turnover, costs, and threshold comparisons;
5. define a total tie order, e.g. `(-score, ticker)`;
6. define initial turnover and missing-data behavior explicitly;
7. serialize reduced rational values or fixed-point integers using canonical JSON;
8. contain no clock reads, UUIDs, absolute paths, environment values, locale dependence, filesystem enumeration order, or unordered-set output.

Determinism proof should run fresh subprocesses with different `PYTHONHASHSEED` values and permuted input row order, then require byte-identical semantic output. Evaluator exceptions, timeouts, non-finite values, or byte drift are integrity failures, not candidate underperformance.

## 6. Use a closed verdict taxonomy

Keep verdict meanings narrow:

- `ACCEPTED`: all identity, authority, fixture, baseline, evaluator, and determinism checks pass, and the valid candidate clears every frozen metric and guardrail.
- `REJECTED`: the candidate is structurally valid and fully bound, evaluation completed deterministically, but measured thresholds or guardrails fail.
- `HELD`: any contract, provenance, authority, parser, fixture, baseline, evaluator, runtime, publication, recovery, or determinism ambiguity exists.

Malformed output should normally be `HELD` and routed through the bounded repair policy; do not misuse `REJECTED` to hide an unevaluable artifact.

## 7. Bind runtime evidence end to end

Require one immutable chain:

`goal/task -> contract ID + raw hash -> attempt ID -> worker/lane/workspace -> provider request ID -> candidate ID + raw hash -> evaluator ID -> verdict artifact -> independent review -> terminal receipt`

Audit ledgers by their fields, not their names. A provider ledger without `task_id` and `contract_id` is supporting telemetry, not task-authority proof. A task ledger that suppresses duplicates by task ID alone can incorrectly accept changed task content. An artifact validator that checks only non-empty bytes is not schema validation.

For restart recovery:

- identical `(task_id, contract_id)` replay is idempotent and must not launch a second worker;
- the same task ID with different contract content is `HELD`;
- if provider completion and candidate bytes exist but the final receipt is missing, revalidate existing bytes instead of rerunning the worker;
- overlapping lease, broken hash chain, or uncertain terminal state is `HELD`;
- forbidden authority attempts are terminal and never retried.

## 8. Publish only after validation

Use write-once/atomic publication for candidate, verdict, and final receipt. Before calling a publisher, independently enforce trusted root containment and reject symlink/reparse substitution; many atomic publishers intentionally assume a trusted destination path.

Kanban/task completion occurs only after durable artifact publication and successful readback. If the board mutation or readback fails, leave the run `HELD` or pending synchronization; never infer completion from local bytes alone.

## 9. Reuse classification

For every adjacent component, classify it as:

- **reuse directly** — its exact security and determinism properties satisfy the new boundary;
- **adapt narrowly** — useful pure logic or hashing exists, but schema/authority/provenance is insufficient;
- **supporting evidence only** — telemetry is useful but not bound strongly enough;
- **do not place on authority path** — permissive, mutable, timestamp-driven, side-effectful, or domain-inappropriate.

Cite the exact functions and limiting lines. Passing legacy tests prove current behavior, not suitability for a stronger contract.

## 10. Read-only verification discipline

If the user requires literal no-file mutation, do not execute tests; inspect test source and prior receipts. If repository mutation is forbidden but isolated verification is explicitly allowed, disable bytecode/cache output, use an approved external basetemp, and record pre/post Git snapshots. Disclose any external scratch paths and any concurrent untracked delta. Never claim an audit induced no change solely because tracked diff is clean.
