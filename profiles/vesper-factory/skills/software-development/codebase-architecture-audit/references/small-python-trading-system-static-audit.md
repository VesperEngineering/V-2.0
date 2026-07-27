# Small Python Trading-System Static Audit

Use this checklist for a strict read-only review of a compact equities/broker application when importing or running the application is outside scope.

## 1. Freeze the boundary

- Inventory source, configuration, documentation, requirements, entry points, tests, and generated-looking artifacts; prune virtual environments and caches.
- Do not import application modules, instantiate broker/data clients, run tests, or compile with a mode that writes bytecode.
- Prefer `ast.parse` for a write-free syntax/import/definition pass. If no repository code graph is available, do not create an index without permission; use a bounded file/AST scan instead.
- Recheck that the review created no logs, databases, state files, models, caches, or receipts.

## 2. Build the startup blocker ladder

Trace imports and constructor order before discussing the intended trading loop. Report the first failure, then each next failure that would become reachable if the previous one were fixed:

1. entry-point import failures or empty modules;
2. configuration values rejected by exact provider/strategy factories;
3. missing model artifacts or referenced setup/training scripts;
4. interface mismatches hidden behind currently unreachable code;
5. relative-path/CWD assumptions and optional dependencies.

Keep the runnable path separate from the aspirational path. A backtest that hardcodes a different feed or strategy does not prove the configured paper/live path.

## 3. Trace one effect end to end

For each order, cancel, close, flatten, or notification path, capture:

`signal -> current snapshots -> risk decision -> durable intent -> remote call -> semantic response -> local state -> tracker/reconciliation -> audit`

High-severity patterns include:

- **Batch reservation gap:** positions, cash, slots, or exposure are snapshotted once and reused for several submissions. Per-order checks can all pass while the batch exceeds limits. Require pending/unknown effects to reserve capacity.
- **Ambiguous-as-rejected:** a broad exception around `submit_order` maps timeout/reset/malformed response to rejection. The effect may have succeeded remotely; require a deterministic client key and exact-key reconciliation before retry.
- **Audit-after-effect:** the first durable record is written only after the remote mutation. A crash can leave an unowned, unrecoverable effect.
- **Fabricated fallback state:** account/position read failure returns zero or empty collections. This can create false P&L, false flatness, or unsafe sizing. Represent unavailability explicitly and close the mutation gate.
- **Account-wide cleanup:** circuit breakers or EOD handlers flatten the whole account without exact account identity and locally owned-position scope.
- **Repeated cleanup:** a latched breaker invokes cleanup every tick, or exits are not tracked as pending.
- **Premature recovery deletion:** local state is cleared when closes are submitted rather than after exact remote reconciliation proves flatness.
- **Mode-label drift:** a command named or displayed as `paper` does not enforce the SDK's paper endpoint/account selection.

## 4. Cross-reference every config key

Create a declaration-to-consumer matrix for:

- mode and broker endpoint/account identity;
- provider and strategy names;
- risk limits;
- market timezone/open/close/early-close calendar;
- dashboard enablement/refresh;
- audit enablement/format;
- notification settings;
- cache/model paths.

Classify each key as consumed, consumed indirectly, ignored, contradicted, or accepted only by documentation. Case-sensitive provider mismatches and configuration that names an implemented-but-unwired class are startup blockers, not mere documentation drift.

Also compare strategy data requirements with source windows. A rolling 50-observation feature is not guaranteed by a 60-calendar-day daily-bar request.

## 5. Verify persistence semantics on the target OS

- Inspect temp-write replacement semantics, locking, flush/fsync, malformed-state behavior, and concurrent writers.
- On Windows, `Path.rename(temp, existing_destination)` is not a replacement primitive; repeated saves can fail. Use this as a review check, not as permission to edit.
- Confirm reconciliation gates new mutation until unresolved pending/unknown effects are classified.
- Treat append-mode JSONL as an audit trail, not tamper evidence; inspect thread/process serialization and durability separately.

## 6. Credentials and reporting

- Enumerate credential variable/key names and whether values are empty, placeholders, or non-empty; never print the values.
- Check examples, comments, URLs, and exception logging as well as active configuration.
- Report potentially exposed material as `path:line — KEY_NAME` and recommend rotation if genuine.

## 7. Static test-gap matrix

Count actual test files/functions, then map missing tests to the effect chain:

- construction/configuration matrix;
- batch reservations and pending effects;
- post-acceptance timeout and exactly-one submission;
- account/position read failure;
- cleanup ownership, repetition, and flatness proof;
- crash cut points and repeated state saves on the target OS;
- scheduler callback failure and future-year calendars;
- stale/malformed market data and cache fallback;
- strategy/model artifact/interface compatibility;
- audit concurrency and config flags;
- entry-point imports and operator mode labeling.

Do not infer test coverage from filenames mentioned in architecture documents. Missing files and empty modules are evidence.

## 8. Concise report order

1. Current runnable verdict and a two-path diagram (configured app vs. backtest/research path).
2. P0 startup blockers in reachability order.
3. P0/P1 latent execution-safety defects, clearly labeled as unreachable until blockers are fixed.
4. Stale documentation/config contradictions.
5. Missing-test matrix.
6. Concrete strengths with exact code ranges.
7. Boundary record: what was inspected, what was not run, and files modified (normally none).

This ordering avoids overstating live danger in code that cannot currently start while still preventing unsafe piecemeal repairs.

## 9. Strategic scoping questions (data spend, IC, universe size)

When the user asks whether to buy premium data, what IC to target, or how many stocks to trade, see `references/greenfield-trading-system-scoping.md`. The audit findings above inform the answer — a system with P0 startup blockers should not be spending money on data subscriptions yet.