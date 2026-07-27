# One-shot selection evidence audit

Use this recipe when an independently accepted evaluator exposes an atomic, contract-bound selection API and the review must invoke it exactly once while verifying a staged admission/contract/result chain.

## 1. Freeze staged identity before execution

Record and later recheck:

- `HEAD`, branch, and upstream identity;
- expected index tree (compare with `git diff-index --cached --quiet <tree> --` when avoiding `git write-tree` side effects);
- SHA-256 of `git diff --cached --binary --no-ext-diff`;
- NUL-framed staged path list and count;
- unstaged/untracked status.

Read and hash staged artifacts from the index (`git show :path`), not merely from worktree paths. Require index/worktree byte equality when the result claims both.

## 2. Validate the chain leaves-first

1. Hash the frozen adapter and actual loaded evaluator bytes.
2. Validate the admission receipt's exact phase, input hash, row/date scope, source mapping, limitations, and required next action.
3. Validate historical contract/result raw hashes and source identities.
4. Normalize the successor contract by removing only its explicit supersession object and restoring the prior evaluator binding. Require exact equality with the predecessor; report recursive JSON-pointer differences.
5. Require successor contract/result supersession objects to bind the exact predecessor path/name and raw SHA-256.
6. Require result bindings to match contract, adapter, evaluator, and repository identities exactly.

On Windows, a Git blob's LF bytes may differ from executed CRLF checkout bytes. Before calling this a provenance defect, inspect `core.autocrlf` and attributes, distinguish blob identity from raw executed-worktree identity, and reproduce the declared checkout transformation explicitly. Do not silently treat LF and CRLF as equivalent.

## 3. Capture-first exact-once execution

The atomic API call is the scarce operation. Never put uncertain aggregation logic between the call and durable scratch capture.

1. Pre-validate the aggregation contract, especially bootstrap details: circular versus non-circular blocks, RNG family, seed, block length, number of samples, start-index range, truncation, and quantile function.
2. Create a unique external scratch leaf; set `PYTHONDONTWRITEBYTECODE=1` and the project interpreter/environment.
3. Snapshot protected input metadata, hashes, and sidecar inventory.
4. Invoke the public selection API exactly once with the exact contract and input bindings.
5. Immediately serialize the returned block outcomes canonically to external scratch and hash them **before** any aggregation assertions. This is ephemeral audit recovery material, not a repository report.
6. Aggregate only from that captured output. Compare floats exactly (including list elements; `float.hex()` is useful evidence) when exact reproduction is claimed.
7. If post-processing fails, do not call the API again. Repair the harness and rerun aggregation from the captured output. If no capture exists, classify the API-bound aggregate proof as incomplete; an independent reconstruction may diagnose the method but must be disclosed and must not be misrepresented as the captured API return.
8. Delete the entire external scratch leaf after all closing checks and verify absence.

A circular moving-block bootstrap samples starts over every observation and wraps each block modulo `n`; a non-circular variant samples starts only through `n - block_length`. These can produce materially different intervals under the same seed. The contract or receipt must make the variant unambiguous.

## 4. SQLite admission checks without source writes

Copy each proven frozen/checkpointed SQLite input to external scratch, verify copy/source hashes, and inspect the copy with `mode=ro&immutable=1`. Check integrity, exact metadata, target and table-wide duplicate groups, finite positive prices, complete source maps, and historical overlap stability. Hash source files before and after and check for `-wal`, `-shm`, and `-journal` sidecars.

When a receipt binds exchange **session dates**, compare `date(timestamp, 'unixepoch')`, not an assumed midnight `datetime(...)`. Historical rows can legitimately encode local midnight as `04:00:00` UTC. A datetime-offset mismatch is an audit-harness semantic error unless the contract actually binds UTC instants.

## 5. Final boundary and closing proof

- Require no final partition in a selection-only contract.
- Inspect that final rejection is unconditional and occurs before row loading/outcome arithmetic.
- Require contract and database post-hashes before API return.
- Verify non-confirmatory language reflects the numbers (for example, a bootstrap interval crossing zero must not be described as confirmatory).
- Run strict JSON finite-number parsing, staged mode/scope checks, `git diff --cached --check`, and credential/private-key scans.
- Recompute the complete opening Git/staged identity, protected-input hashes/sidecars, and temp-leaf absence before verdict.

## Harness-failure classification

Wrong bootstrap variants, session-date versus UTC-datetime comparisons, and line-ending identity confusion are harness mistakes until reproduced as target defects. Repair and rerun only the read-only checker phase. Never spend a second exactly-once outcome call to compensate for a post-processing bug.