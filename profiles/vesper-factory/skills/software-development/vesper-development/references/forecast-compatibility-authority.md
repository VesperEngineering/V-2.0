# Forecast compatibility authority

Use this checklist when adding research-only or shadow forecast records around an existing model.

## Authority root

A forecast call must not receive both an asserted identity and the value that supposedly authorizes it. Comparing `feature_hash == expected_feature_hash` or `symbol in approved_universe` is meaningless when the same caller supplies both sides.

Establish compatibility before individual forecast calls with an independently reviewable model-companion manifest. Bind at least:

- exact model artifact SHA-256;
- ordered feature schema and its canonical digest;
- ordered approved universe and its canonical digest;
- forecast horizon and target definition;
- manifest schema version.

The model adapter should derive the companion-manifest location from the selected model artifact rather than accepting per-call universe/feature overrides. Validate the manifest against loaded model bytes and imported feature definitions before scoring. Reject unknown symbols, malformed/tampered manifests, model/hash drift, feature-order drift, horizon drift, and target drift.

## Forecast record

A closed research/shadow forecast record should include:

- symbol, exact `datetime` as-of timestamp, and explicit valid-until timestamp;
- horizon, target definition, standardized score, units, direction, and deterministic rank;
- expert/model identity and artifact hash;
- feature, dataset, adjustment, and run-manifest identities;
- data-freshness status;
- explicit `research_only`, `execution_authority=False`, and `authority_state="shadow"` invariants.

Reject non-finite values, stale/mismatched timestamps, invalid validity ordering, missing provenance, unknown symbols, and incompatible feature identity before model scoring or record return.

## Inertness and parity

- Keep shadow generation in memory for the first slice; no writers, engine wiring, orders, broker calls, risk changes, or promotion paths.
- Prove it does not mutate strategy rebalance state or construct `Signal` objects.
- Factor scoring only when an exact regression preserves existing signal symbol/action/strength/reason/timestamp/metadata.
- Use deterministic tie-breaking (for example score descending, symbol ascending) and explicitly test z-score behavior.

## Independent acceptance matrix

Do not accept a manifest-bound candidate from ordinary happy-path tests alone. An external verifier should recompute the champion companion from current sources and exercise all of these classes:

- model bytes, ordered feature list/digest, ordered universe/digest, horizon, target, and schema match independently recomputed values;
- the adapter derives the companion path from the selected model path and rejects constructor/per-call compatibility overrides;
- arbitrary caller-approved symbols and matching caller-supplied expected/actual hashes cannot reach scoring;
- each manifest field fails closed when tampered, including reordered features, duplicate/empty universe entries, and model-hash drift;
- lazy loading does not hide a manifest mutation made after strategy construction but before the first forecast call;
- ranking is score-descending with deterministic symbol tie-breaking, and forecast z-scores use the intended sample-standard-deviation convention;
- shadow generation constructs no `Signal`, performs no writes, and leaves rebalance state unchanged;
- active signal payload parity covers symbol, action, strength, reason, timestamp, and metadata—not merely signal count.

Temporary models and manifests used by tests are valid only when the companion is established before the forecast call; never pass compatibility authority through the call under test. Put verifier scripts and pytest temp roots outside the repository, disable repository cache/bytecode writes, and remove all scratch before the final identity check.

## Review sequence

1. Capture strict RED evidence for every authority failure.
2. Run focused and explicit `tests/` suites with the project interpreter and external temp paths.
3. If worker-monitor/dashboard tests are excluded to avoid GUI or concurrent-session interference, name the exact collected path (for example `tests/test_dashboard_worker_monitor.py`) and report the result as scoped—not as a full-suite pass. Do not guess an exclusion filename from a component nickname.
4. Stage only the declared contract/source/test/manifest paths.
5. Freeze tree and binary-diff identities using the handoff's exact canonical hash command.
6. Obtain adversarial independent review, remove external scratch, then recheck branch, HEAD, tree, paths, and diff hash before integration.
