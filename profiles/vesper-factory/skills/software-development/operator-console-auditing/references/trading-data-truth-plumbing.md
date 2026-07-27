# Trading dashboard data-truth plumbing

Use this reference when a dashboard displays factor ranks, target baskets, broker portfolios, or execution state.

## Authority ladder

Keep these separate in both payloads and widgets:

1. Raw factor scores and leaders
2. Universe/tradability-admitted candidates
3. Portfolio-construction output (for example sector-neutral selection)
4. Risk-approved execution target
5. Last execution receipt and submitted/filled orders
6. Current broker positions

Never derive a widget called **Selected Basket** directly from raw top-N scores when execution consumes a constructed basket artifact. Never overwrite a target-basket widget with current holdings. Show target, last executed target, and actual positions as separate objects with independent timestamps.

## Prove which duplicate copy produced a payload

When repository and serving directories coexist:

- Trace the scheduler/wrapper command to its exact script path and working directory.
- Compare files/hashes, but do not stop there: use behavioral fingerprints in the payload (for example top-4 versus top-10 selection) to identify the producer that actually ran.
- Check which frontend bundle the HTML references and whether that bundle differs from the repository copy.
- Report when an aggregator writes to both trees, since identical output files do not imply identical source code.

## Freshness fields

Model at least:

- `payload_generated_at`: aggregation time
- `source_as_of`: authoritative source timestamp/session
- `source_age_seconds`: age of that source
- `fetched_at`: browser/API fetch time
- `source_kind`: snapshot, broker-live, receipt, target artifact, etc.
- `status`: fresh, stale, error, unavailable

A browser reread or aggregator rewrite must not reset `source_age_seconds`. Do not use a successful fetch or recent file mtime as the sole meaning of `live`.

## Factor contribution truth

- Read current factor keys and deployed weights from the scoring producer, not legacy dashboard aliases.
- Distinguish raw factor value from weighted contribution to the combined score.
- Compute top contributor from deployed weighted contribution and the producer's denominator rules.
- Mark zero-weight factors as diagnostic/non-deployed rather than contributors.
- Add a fixture using at least one current factor key that no legacy mapping recognizes.

## Universe and tradability

Ticker syntax is not universe admission. Test all applicable gates independently:

- membership in the approved universe artifact
- required metadata/sector coverage
- score artifact source session and status
- broker asset existence
- broker `tradable`
- support for the intended order type (for example fractionable/notional)

An edited markdown target should not bypass universe admission merely because all symbols are valid at the broker.

## Production-path regression test

Helper tests are insufficient if the CLI entry point bypasses them. Add a test that patches the lower-level unsafe/direct function to fail, then asserts `main()` enters the lock/idempotency boundary and invokes the durable execution orchestrator. Verify the production receipt carries target provenance, basket digest, before/after positions, and terminal order states.

## Tight regression suite

Prefer small fixture-driven contract tests covering:

1. health fails closed when a critical job/source is stale or errored;
2. payload age and source age remain distinct across repeated aggregation;
3. selected target equals the canonical execution artifact, not raw leaders;
4. target, last executed target, and holdings never overwrite one another;
5. current factor keys map to truthful weighted contributions;
6. snapshot and broker-live portfolio states are visibly distinct;
7. approved-universe and broker tradability gates both run;
8. the real entry point uses the tested durable side-effect boundary.
