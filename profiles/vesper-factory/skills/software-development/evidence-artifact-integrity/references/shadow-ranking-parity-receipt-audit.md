# Shadow Ranking/Parity Receipt Audit

Use this recipe when independently accepting or rejecting a staged receipt claiming parity between an inert forecast path and an active ranking/signal path.

## Required identity freeze

Record before execution and repeat after cleanup:

- exact `HEAD`;
- staged tree (`git write-tree`);
- SHA-256 of `git diff --cached --binary --no-ext-diff`;
- staged path list and worktree status;
- staged blob ID and raw SHA-256 of the receipt.

Extract or stream the staged blob into external scratch and use those exact bytes for parsing and hashing. Do not parse the checkout copy merely because `git status` reports no unstaged change: on Windows, clean checkout bytes may be CRLF while the staged blob is LF. If the two raw hashes differ, record the representation difference without treating it as candidate drift; the verdict remains bound to the staged blob unless the contract explicitly names checkout bytes.

A verdict is bound to this exact candidate. Any drift invalidates it.

## Read-only evidence handling

- Copy large SQLite evidence to unique external scratch before opening it. Hash-compare the copy to the declared source hash.
- Open the copy read-only; do not instantiate production stores against the source.
- Copy and hash any adjustment artifact used by the calculation.
- Set `PYTHONDONTWRITEBYTECODE=1` and keep scripts/results outside the repository.
- Remove external scratch and verify absence before finalizing.
- Verify the source database has no new WAL/SHM sidecars and source hashes are unchanged.

## One-shot recomputation

Perform one independent scoring-workflow invocation against the exact model, compatibility manifest, feature implementation, universe, adjusted dataset, and common as-of session. “One-shot” governs this public computation boundary; it does not imply exactly one low-level `predict()` call, because a valid implementation may predict once per symbol or per batch. Before any downstream assertion—including call-count assertions—persist the complete raw score map to unique external scratch and hash the capture. Separately derive the ranking from those captured raw scores and compare:

1. forecast count and rank sequence;
2. full symbol ordering, including deterministic tie-breaking;
3. positive-threshold/top-N entry symbols and order;
4. active signal symbols and order;
5. provenance fields on every forecast;
6. research-only/shadow state and literal authority denials.

Do not spend a second scoring-workflow invocation to repair a checker mistake. Repair the harness against the captured scores, then exercise forecast/signal formatting or provenance paths with the captured score map injected or replayed and assert that no further predictor calls occurred.

## Hash reproducibility gate

Ranking parity alone does not validate the receipt. Every bound digest must be independently recomputable from information inside the receipt or from an exact contained path named by it.

A dataset digest contract must state at least:

- source artifact/path and source SHA;
- row window and common-as-of rule;
- universe and symbol ordering;
- row and column ordering;
- exact scalar types and nonfinite handling;
- date/time representation and timezone projection;
- float/volume serialization;
- framing or canonical JSON profile;
- hash algorithm and canonicalization scope.

A run-manifest digest must bind either the complete manifest object or an exact contained path plus raw hash. A bare digest with no object/path is not independently verifiable.

If exact forecasts, rankings, and signals reproduce but a dataset or run-manifest digest cannot be reproduced because its serialization contract or preimage is absent, return `HOLD_EVIDENCE_UNREPRODUCIBLE`. Do not call the hash dishonest without proof; state that the behavioral parity claim reproduced while the exact receipt remains inadmissible.

## Verdict shape

Report:

- exact candidate identity;
- bindings that reproduced;
- one-shot parity result;
- any digest that did not reproduce and the missing contract/preimage;
- authority denials;
- opening/closing no-drift and scratch cleanup;
- `PASS` only if every material receipt claim is reproducible, otherwise a precise `HOLD`;
- next safe action, normally regeneration with the missing hash profile or manifest content—not editing the audited receipt in place.
