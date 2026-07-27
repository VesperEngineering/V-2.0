# Local-only candidate-pipeline boundary

## Problem

The scheduler-oriented factor path can combine three distinct authority classes:

```text
provider-capable factor collection
→ persisted factor-score/history materialization
→ sector basket / candidate strategy decision
```

Do not invoke this whole path merely because a no-submit daily preview lacks a dated candidate receipt. A no-submit preview removes order submission, not provider, source, strategy-decision, or persistent-history side effects.

## Safe shadow seam

Create and test a pure candidate-construction seam with explicit inputs:

```text
frozen score mapping + frozen ticker→sector mapping + as-of date
→ deterministic sector basket
→ dated no-order candidate representation
```

The seam must:

- use in-memory or frozen test fixtures only;
- make no provider, registry, subprocess, HTTP, socket, SQLite, cache, scheduler, broker, or order call;
- avoid factor-history writes, promotion, and production scheduler rewiring;
- have no production caller and no artifact writer for a real dated candidate.

## Review-grade fail-closed contract

Test the actual boundary adversarially. Do not accept a generic `PASS` result merely because a happy-path fixture works.

1. **Date:** validate a real `YYYYMMDD` calendar date. Reject regex-looking but impossible values such as `20261399`, `00000000`, and invalid leap dates.
2. **Identity:** reject empty, whitespace-only, or malformed ticker and sector values.
3. **Scores:** reject empty evidence plus missing, `None`, boolean, string, NaN, and infinite scores.
4. **Ambiguity:** reject equal highest scores within a sector; never select a winner based on input/source order.
5. **Replay:** verify all permutations of a non-tied frozen fixture emit exactly the same ordered representation.
6. **Isolation:** statically inspect imports and calls. A pure service should depend on stdlib-only validation/ordering primitives, not on the factor registry or a storage/provider adapter.

Use vertical strict TDD: each behavior gets an observed RED failure before minimal GREEN code. Freeze the candidate diff before independent review. A broad suite failure caused by unrelated fixture/environment contracts does not replace scoped behavior, lint, compilation, import-isolation, and diff-check evidence; record it honestly without treating it as candidate approval.

## Production boundary

A passing shadow seam proves only that candidate construction can be isolated. It does **not** create a production candidate, establish source freshness, admit a new factor, authorize a basket, or authorize paper/live orders.

A dated production factor-score/basket run needs separate exact authorization naming:

- allowed providers and source identities;
- permitted persistent writes, including factor-history state;
- exact date and output paths;
- whether a fresh strategy/basket decision is allowed;
- explicit denials of broker/account/order, promotion, scheduler, risk, dependency, and secret actions.

Keep any Massive scope behind its repository-defined exact approval contract. After a future production run, independently validate source provenance, score date, basket date, candidate/no-order decision, and the no-submit boundary before attempting a preview.
