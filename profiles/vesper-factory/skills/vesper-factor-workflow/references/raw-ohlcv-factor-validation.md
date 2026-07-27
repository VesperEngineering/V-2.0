# Raw OHLCV factor validation: bounded overnight pattern

## Purpose
Use when V20 research has only a broad raw-OHLCV panel plus a smaller adjusted/total-return validation surface.

## Evidence hierarchy
1. **Broad raw panel:** use only for screening a clearly predeclared economic hypothesis. Label results fixed-universe, raw-price, and survivorship-limited.
2. **Adjusted/total-return adapter:** use as a bounded robustness rerun, not as a substitute for broad point-in-time evidence.
3. **Paid GPU:** only after a candidate has incremental performance versus a matched control and survives declared cost assumptions; a more complex architecture cannot repair data provenance.

## Required protocol
- Monthly formation after close t; execute t+1 open; exit at a predeclared executable future open.
- Apply history and liquidity filters with data available at t.
- For unadjusted prices, predeclare a discontinuity rule. If future holding-window exclusions are used to remove apparent corporate-action corruption, label this **post-outcome censoring**, never deployable evidence.
- Compare signal basket with the same-date, same-liquidity, same-censoring equal-weight control.
- Report gross return, both a conservative independent-holding cost case and actual-turnover cost case, turnover, breadth, and all development/validation/final-OOS windows.
- Do not treat a signal as viable when it loses to its matched control, even if absolute return is positive.

## V20 adapter example
Canonical total-return validation adapter:
`D:/vesper/vesper_data/massive/adapters/total_return_ohlcv_adapter_20260717T153500Z.sqlite`

- Table: `ohlcv_data(ticker, timestamp, open, high, low, close, volume, timeframe)`
- Filter `timeframe='1day'`; normalize `timestamp` with `date(timestamp, 'unixepoch')`.
- Metadata expected: `price_basis=total_return_adjusted`.
- It is a 31-name alias-normalized validation subset through 2026-06-30, not broad confirmation.
- Retain the documented META/FB source-transition hazard as a disclosed diagnostic limitation.

## Overnight operating rule
When the user gives a deadline, budget, and conditional provider authorization, proceed autonomously through research, surgical local code, tests, and bounded local evaluation. Interrupt only for an actual blocker: failed authentication, an unbounded cost, safety boundary, or a failed model gate. Do not revive an exhausted hyperparameter family merely to consume available GPU credit.
