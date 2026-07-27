# Read-only market-data audit

Use this before proposing a model-training, backtest, or data-integration change.

## Scope and safety

1. Resolve the requested data path and its link/junction target. A project-local `data/` directory may be absent while the intended corpus is external.
2. Treat database files as immutable: open SQLite using `mode=ro`; do not run migrations, VACUUM, checkpointing, or any code path that creates sidecar files.
3. Inventory formats, file counts, total bytes, and the largest artifacts before querying large stores.

## Minimum evidence for a canonical OHLCV table

For the exact candidate table, report:

- schema and the intended key (normally ticker + session date);
- total rows, distinct tickers, distinct sessions, min/max session;
- duplicate key groups;
- basic OHLCV invariants: non-null values, positive prices, non-negative volume, and low <= open/close <= high;
- latest-session ticker coverage and per-ticker history range.

Do not infer point-in-time index membership, split adjustment, dividend treatment, or symbol-identity safety from a clean OHLCV table alone. Inspect the associated membership, corporate-action, adjustment, and alias-provenance layers separately.

## Large-corpus discipline

A full duplicate or integrity scan over tens of millions of rows can be expensive. Run the canonical/smaller store first. For larger stores, inspect schema/indexes and use bounded, indexed, or staged checks; if a read-only query times out, report that its full integrity is unverified rather than retrying the same table scan.

## Integration conclusion

Data presence is not integration. Trace the active application feed and model paths. Explicitly distinguish:

- source data exists;
- training matrices/features exist;
- a deployable model artifact exists;
- the runtime is configured and wired to use the data and artifact.
