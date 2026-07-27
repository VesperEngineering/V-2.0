# Low-volatility evaluator worked example

## Existing behavior preserved

The evaluator already reported `net_returns` by subtracting a full entry-and-exit cost from every independent holding label. That field was deliberately retained unchanged.

## Added cost-adjusted field

`turnover_cost_returns` was added separately. It uses actual equal-weight target-basket one-way turnover and applies a stated per-side bps rate:

- first period: cost for buying the initial target basket;
- later periods: cost for selling and buying the changed target weights (`2 × one-way turnover`);
- last period: cost for selling the final basket.

A partial-overlap fixture—`[A, B]` then `[B, C]`—proved the calculation. At 5 bps with 10% returns in both periods, the expected result was:

```text
(1.10 - 0.0005) × (1.10 - 0.0010) - 1
```

The first cost is the initial buy. The second is a 0.5 one-way rebalance (buy and sell = 0.0005 total) plus a 0.0005 terminal sale.

## Matched control

The equal-weight control consisted of all tickers that were:

1. feature-eligible at the formation date;
2. in the top 80% by liquidity; and
3. retained by the same future open-to-open holding-label discontinuity screen.

It used the exact same formation dates and holding windows as low-vol. It differed only by not applying the low-risk selection rule.

## Decision boundary

The output contained a `RESEARCH_ONLY_NO_GO` field explicitly saying it was not a paid-GPU approval and could not override raw-price/survivorship limitations.

## Execution sequence

The change was validated with focused RED/GREEN tests, the affected test file, and the full suite using `PYTHONPATH=.` plus an external pytest basetemp that was deleted afterward. The evaluator was then run once against its read-only SQLite source and only stdout was used—no report file was created.