# Schema-first read-only audit harnesses

Use this recipe for exact-source, fail-closed audits that join receipts, JSONL ledgers, SQLite lifecycle history, scheduler records, and session telemetry without modifying the originals.

## Why this exists

A forensic checker is part of the proof chain. If it assumes a stale table or column name, a late `OperationalError` can consume the remaining audit budget and leave mandatory probes unexecuted. That is an **incomplete audit**, not evidence that the target is defective. Under a fail-closed gate it still yields `HOLD`, but the report must classify the hold accurately.

## Order of operations

1. **Freeze scope first.** Record exact source SHA/tree, clean status, admissible evidence roots, and byte manifests before opening structured stores.
2. **Create one external scratch root.** Put source snapshots, database copies, temporary test state, probe outputs, and audit scripts beneath it. Record the scratch path.
3. **Snapshot databases without touching originals.** For frozen evidence, copy the database to scratch before any SQLite connection. For an active WAL database, prefer an official read-only surface or an approved consistent snapshot of the main database plus WAL state. Do not instantiate a production store class against evidence: constructors may create directories, enable WAL, migrate schemas, or add sidecars.
4. **Discover the actual schema before writing joins.** On each scratch copy inspect:
   - `sqlite_master` tables and indexes;
   - `PRAGMA table_info(table)` or `table_xinfo(table)`;
   - `PRAGMA index_list(table)` and relevant index columns;
   - `PRAGMA foreign_key_list(table)` when used;
   - one bounded `SELECT * ... LIMIT 1` sample to confirm stored representations.
5. **Persist a schema fingerprint.** Canonically serialize table names, ordered columns, types, nullability, primary-key positions, and indexes; hash it into the scratch audit output. A schema mismatch should stop that audit phase with an explicit `AUDIT_INCOMPLETE_SCHEMA_MISMATCH` result rather than being mislabeled as target corruption.
6. **Smoke-test one record per evidence plane.** Recompute one receipt hash, one lifecycle event hash, one JSONL row, and one task/session join before launching the full-history checker. Only expand after these agree with physical bytes.
7. **Run acceptance-critical adversarial probes early.** Before broad inventory work, exercise the exact public replay route after raw-only candidate and evaluation mutations, binary multiline write behavior, producer/lifecycle byte comparison, strict JSONL framing, and the latest known HOLD reproductions. These decide the gate and are vulnerable to session/tool ceilings.
8. **Then perform exhaustive history joins.** Validate every sequence, previous hash, state edge, external identity, ledger row, receipt companion, scheduler execution, and worker/reviewer telemetry record.
9. **Run the focused test/lint gates from the exact clean scratch snapshot.** Redirect bytecode, pytest temp, and caches into scratch.
10. **Reserve the final calls for drift checks.** Rehash source/evidence/profile/scheduler inputs and compare them with the opening manifest. Never spend the final audit budget constructing a new un-smoke-tested monolithic checker.

## Minimal SQLite discovery pattern

Run only against a scratch copy:

```python
import json
import sqlite3

connection = sqlite3.connect("scratch/evidence.db")
connection.row_factory = sqlite3.Row
assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"

tables = [
    row[0]
    for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
]
schema = {}
for table in tables:
    schema[table] = {
        "columns": [tuple(row) for row in connection.execute(f"PRAGMA table_info({table})")],
        "indexes": [tuple(row) for row in connection.execute(f"PRAGMA index_list({table})")],
        "sample": [dict(row) for row in connection.execute(f'SELECT * FROM "{table}" LIMIT 1')],
    }
print(json.dumps(schema, indent=2, sort_keys=True, default=str))
```

Do not copy column lists from prose, an older migration, or another evidence generation. Build the validator from the discovered schema and separately compare that schema with the exact source revision's declared contract.

## Budgeted audit phases

Make the checker restartable and phase-oriented:

- `00-scope.json`: roots, source SHA/tree, opening manifests;
- `10-schema.json`: database integrity and schema fingerprints;
- `20-critical-probes.json`: raw-byte replay, O_BINARY, cross-copy, JSONL framing;
- `30-history.json`: receipts, events, ledgers, scheduler, sessions;
- `40-gates.json`: focused tests and lint;
- `90-drift.json`: closing manifests and clean status.

Each phase should write only beneath scratch and be independently rerunnable. Validate the output schema of each phase before moving on.

## Verdict classification

- **Target HOLD:** a reproducible target behavior violates the governing contract, such as accepting a raw-only artifact mutation or a broken event hash.
- **Audit HOLD:** a required proof could not be completed because the audit harness, access path, or execution budget failed. Do not present this as a product defect.
- **PASS:** every required proof completed and the opening/closing scope fingerprints match.

When the user permits only `PASS` or `HOLD`, use one of those words as the verdict and state the classification in the concrete evidence that follows.