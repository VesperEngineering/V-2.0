# Versioned Artifact Identity and Exact Replay

Use this procedure when generated datasets, features, reports, or model inputs must be reproducible from frozen inputs and tied to the code that actually produced their bytes.

## Identity graph

Build identities leaves-first:

1. Raw immutable sources and authoritative evidence bytes.
2. Canonical protocol identity, kept distinct from the raw formatted protocol-file hash.
3. Dataset semantic/materializer identity and actual producing runtime.
4. Dataset bytes and canonical dataset manifest.
5. Feature semantic-builder identity, feature serializer/materializer identity, and the exact dataset-manifest hash.
6. Feature bytes and canonical feature manifest.
7. Release manifest, staged diff, and independent review.

Any edit to a leaf invalidates every descendant. Preserve old artifacts as historical evidence; never overwrite their identity claims in place.

## Builder and materializer identities

Do not use one vague `builder_sha256` for everything.

- **Semantic builder:** hash every transitive helper affecting admission, calendar/session selection, point-in-time membership, pivots, normalization, labels, target availability, or row values.
- **Materializer/serializer:** separately hash the code that validates manifests, selects output paths, canonicalizes metadata, writes Parquet/JSON, fsyncs, and performs replay checks.
- Use explicit symbol labels and a domain/version prefix in the source-hash payload so concatenation is unambiguous.
- If source hashing normalizes CRLF/LF, declare that transform. Generated artifacts remain raw-byte-bound.
- Do not edit source while a materializer is running when its identity function calls `inspect.getsource`; the running process can otherwise bind a mixture of loaded code and later on-disk source.

A requirements lock is not proof of the runtime that executed. Record and replay-check actual relevant versions, for example:

```json
{
  "python": "...",
  "numpy": "...",
  "pandas": "...",
  "pyarrow": "...",
  "sqlite": "..."
}
```

Choose only libraries that can affect admission, calculations, source reads, or serialized bytes.

## Minimum manifest bindings

A dataset manifest should bind at least:

- protocol SHA-256;
- source/evidence SHA-256 values;
- dataset-builder/materializer SHA-256;
- actual runtime identity;
- calendar/session identity;
- materialization recipe/version;
- output SHA-256, shape, date range, and source counts;
- causal anomaly/quarantine boundaries needed to verify retained history.

A feature manifest should additionally bind:

- dataset artifact SHA-256;
- exact dataset-manifest SHA-256;
- dataset-builder SHA-256;
- feature semantic-builder SHA-256;
- feature materializer SHA-256;
- actual runtime identity;
- feature artifact SHA-256, shape, feature list, and target-date boundary.

Replay readers must check these fields, canonical manifest bytes, and the physical artifact hash before returning success.

## Recoverable two-pass physical replay

1. Verify that all four canonical files (dataset, dataset manifest, feature, feature manifest) are either present or absent; reject partial sets.
2. Produce or validate pass 1.
3. Copy every pass-1 file byte-for-byte into a new private replay directory and verify each copied hash.
4. Only after durable pass-1 copies exist, remove the canonical set.
5. Rebuild pass 2 from the same frozen inputs, protocol, source, and runtime.
6. Compare pass-1 and pass-2 raw hashes, raw bytes, parsed canonical manifests, and identity fields.
7. On build or comparison failure, restore pass-1 bytes exactly; never leave the canonical set missing or mixed.
8. Persist a canonical replay result containing both hash maps, identities, checks, and paths.

A second call that merely returns an existing valid manifest is idempotence, not regeneration proof. At least one pass must be a fresh physical rebuild after deleting the canonical outputs.

## Safe evidence tamper probes

Do not mutate canonical evidence just to test rejection.

1. Copy the canonical protocol and all relative evidence files into a temporary private root.
2. Redirect the loader's root/canonical-path constants to that copy in the test process.
3. Confirm the untampered copy loads.
4. Append or alter one evidence byte at a time.
5. Require rejection for the exact intended identity reason.
6. Restore the copied bytes and require the original protocol identity again.

This proves physical tamper closure without risking canonical evidence.

## Scientific integrity checks on rebuilt artifacts

For session-indexed research artifacts, verify from the physical outputs rather than trusting manifest booleans:

- one-to-one, contiguous exchange-session indexes;
- signal, executable entry, and exit dates all resolve through the frozen calendar;
- exact signal-to-entry and entry-to-exit session lags;
- target returns reconstruct from the bound executable prices;
- missing future outcomes remain missing without removing score-time rows;
- every recorded quarantine boundary excludes only that suffix;
- synthetic future split and unresolved-jump extensions preserve the earlier prefix exactly.

When probing a strict numerical rule, select a value clearly beyond the production threshold. If a probe expected `> 0.45` but generated `0.4423`, that is a harness defect, not a target defect. Read the exact predicate, repair the fixture, and rerun without changing production code.

## Release-manifest recursion

Avoid impossible self-reference. If a launcher or wrapper contains the expected release-manifest hash, the release manifest cannot also contain that wrapper's raw hash without a cycle. Either:

- exclude the wrapper from that manifest and bind its identity in an outer release/staged-diff review; or
- redesign with a non-self-referential external anchor.

A release verifier should enforce exact schema keys, canonical bytes, contained worktree-relative file paths, approved absolute artifact roots, source/evidence/build/runtime identities, and every artifact hash. Invoke the verifier directly for a focused check; do not execute a scheduler or experiment merely to test release identity.
