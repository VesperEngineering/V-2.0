# Frozen-input data admission audit (read-only, fail-closed)

Session detail from a "Slice N data admission" audit of a frozen derived SQLite
adapter (SPY total-return snapshot) in a research program with ordered
remediation slices. Class pattern: an independent reviewer must emit a
fail-closed `ADMIT_<PHASE>` / `NO-GO` receipt for a frozen data input, for a
named phase only, with zero writes and zero outcome computation.

## Non-negotiables

- Open every SQLite database with `mode=ro&immutable=1` URI parameters, e.g.
  `sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro&immutable=1", uri=True)`.
  `mode=ro` alone still permits journal/WAL side effects on some states;
  `immutable=1` guarantees none. Check for stray `-wal`/`-shm`/`-journal` files.
- SHA-256 every touched file **before and after** inspection and assert identity.
  Hash again at the very end (all snapshots + backing DBs) as the no-write proof.
- `git status --porcelain` must be clean at start and end; delete any temp
  inspection script when done; keep scratch OUTSIDE the repo.
- Never compute outcome/selection/final metrics during a data-admission slice.
  The receipt must state the admitted phase explicitly (e.g. development and
  selection only, NOT final holdout).

## Gate checklist (adapt names to the local contract)

1. **Identity** — file SHA-256 matches the frozen hash recorded in the approved
   provenance/scope receipt; size/mtime noted but hash is the binding.
2. **Approved scope** — the human authority decision exists, is dated, and names
   the exact claim, adapter path, hash, and authorized next stage.
3. **Basis metadata** — declared price basis (e.g. `total_return_adjusted`),
   timeframe, and generation timestamp present in an in-DB metadata table.
4. **Row integrity** — target-instrument row count and date range match plan
   facts; timestamps unique, strictly monotonic; no null/non-positive prices;
   no duplicate `(ticker, timestamp, timeframe)` groups table-wide.
5. **Source-map completeness** — every data row left-joins to a source-map row
   with non-null, non-empty source key and 64-hex source SHA-256; do this for
   the target instrument AND count unmapped rows across all tickers.
6. **Backing-store reconciliation** — if a V20-local backing DB exists, verify
   its hash against plan facts and reconcile every mapped row on
   (key, hash, value): 0 missing, 0 hash mismatches, 0 value mismatches
   (compare with tolerance ~1e-9 for REAL columns).
7. **Historical-row stability** — compare against ALL older local snapshots of
   the same artifact: zero mismatched rows on shared timestamps. Append-only
   truncation (earlier snapshots have fewer rows) is expected; classify this as
   truncation-stability evidence, NOT proof of the external vendor build.
8. **Implementation/repair published** — the code the contract will bind is at
   the canonical commit. See provenance-drift pitfall below.
9. **No writes** — post-inspection hashes identical; repo clean.

## Provenance-hash drift pitfall (real, encountered)

An "after" hash recorded in a remediation/provenance receipt can be superseded
when a LATER commit further hardens the same file. `git log --oneline -- <file>`
shows which commits touched it. Do not fail the gate on the mismatch alone:
verify the on-disk file at the canonical commit IS the published repair, record
both hashes and the explanation, and direct the NEXT slice's contract to bind
the current on-disk hash at the canonical commit — not the stale receipt hash.

## Limitations to state explicitly (do not silently cure)

- External raw-to-derived reconstruction not locally reproducible when build
  inputs live outside the repo (e.g. an audit table naming `D:\...` paths).
  Distinguish EXPERIMENT reproducibility (contract+code+frozen input recompute)
  from RAW-DATA reconstruction; the former can be admitted, the latter not.
- Cross-snapshot stability is local evidence only; a silent vendor-side
  revision between external build and local snapshotting is undetectable.
- Data cutoff sufficiency: state which phases the frozen range can serve and
  which require a genuinely future sealed snapshot.
- Adjusted/total-return prices are research accounting values, not executable
  market prices.

## Receipt shape

Fail-closed JSON: decision + explicit phase scope, repo path/commit/tree state,
input path + observed vs expected hash, per-gate `pass`/`fail` with one-line
evidence, a `limitations` array, and a single `required_next_action` naming the
next slice/artifact and the exact values it must bind.
