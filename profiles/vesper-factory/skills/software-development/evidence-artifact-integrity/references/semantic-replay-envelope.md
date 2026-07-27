# Pure Semantic Replay Envelope

## Goal

Establish deterministic replay before any persistence, ledger, checkpoint, or external anchor exists. This is an in-memory verification boundary, not a file format and not an append-only-history claim.

## Capture only builder inputs

For a forecast → target → delta → evidence chain, capture:

- complete typed forecast records;
- target-builder inputs: timestamps, canonical holdings, portfolio value, classification identity, generation version, `top_n`, threshold, and transaction-cost assumption;
- delta-builder inputs: typed position, price, and pending-order observations; completeness, observation time, externally carried identity claims; and typed planner constraints;
- an immutable enum-derived current-signal snapshot, excluding mutable incidental fields such as metadata;
- expected plan and evidence SHA-256 values from the source computation.

Do **not** capture derived target lines, target metrics, delta lines, blocked/diagnostic outputs, snapshot digests, or an object reference to the source plan/target. Those are outputs that replay must derive.

## Replay contract

1. Clone retained leaf records through their validating constructors.
2. Rebuild the target through its production builder.
3. Rebuild the plan through its production builder.
4. Rebuild the typed signal snapshot and evidence through production adapters.
5. Reject unless replayed plan and evidence identities equal the commitments captured at step 0.

The envelope itself must explicitly retain research-only/shadow state and deny execution, broker, order-submission, and persistence authority.

## Adversarial checks

- Mutate nested source-plan forecast/price/constraint objects after capture: replay must remain unchanged.
- Mutate a nested envelope input: builder validation or committed identity comparison must reject it.
- Exercise all announced classifications: increase/BUY, reduce/SELL, close/CLOSE, aligned, divergent, shadow-only, suppressed, blocked, and inactive.
- Reject raw/non-enum actions, duplicate/unknown symbols, timestamp drift, booleans, non-finite strengths, and strengths outside the allowed range.
- Confirm capture/replay creates no filesystem artifacts and imports no operational authority.

## Deferred work

Persistence later needs a strict versioned wire schema, bounded parser, duplicate-key rejection, Windows handle-bound containment, durable transition recovery, and independently administered anchoring. Do not smuggle any of those concerns into the pure replay slice.
