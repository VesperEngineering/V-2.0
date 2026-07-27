# Position-Risk Provenance and Factor-Reconstruction Audit

Use this checklist when reviewing a historical position-risk or stop-loss diagnostic against the live Vesper factor path.

## Dual price-basis rule

- Use split-adjusted OHLC for factor inputs, ATR, gaps, stop touches, and executable fills.
- Do not use total-return-adjusted OHLC for executable levels.
- Separately credit dividends in portfolio return accounting, either as explicit cash flows or through a rigorously reconciled total-return valuation layer. A split-adjusted equity curve silently omits dividends.
- Do not infer “no dividend effect” from an intermediate `dividend_factor == 1.0`; compare `adjusted_close` with `total_return_adjusted_close` and inspect the builder’s actual factor columns.
- Artifacts should state both `execution_price_basis` and `return_accounting_basis`, with an explicit `dividends_credited` boolean.

## Formula-parity matrix

Compare the historical kernel with the actual live implementations on:

1. included factors and nonzero live weights;
2. sign and raw formula;
3. lookback and minimum warmup;
4. missing-value admission and complete-case behavior;
5. cross-sectional z-score `ddof`;
6. as-of cutoff and next-session execution;
7. universe and sector source.

A frozen three-factor core reconstruction can be defensible when sparse informational factors lack publication-lag-correct history, but label it `frozen core kernel`, not the complete live blend. Check warmup independently: a rolling formula may become numerically available after 21 rows even when the live factor intentionally requires 60.

## Membership, sectors, and identity

- Report both total cohort size and daily cross-sectional size range.
- Report represented sector count and distribution. Selecting one winner from each of four winning sectors is four-sector diversification, not benchmark sector neutrality.
- A current active-universe cohort plus current sectors remains survivor/static-classification evidence even if adjusted prices are clean.
- Hardcoded rename repair is acceptable only as a documented diagnostic patch. Promotion-grade identity requires effective-dated security IDs, canonical source-row selection, alias-policy versioning, uniqueness assertions, and fail-closed held-price checks.

## Artifact identity and moving worktrees

Record HEAD, staged/unstaged/untracked state, and source hashes before interpreting an artifact. If scoped files change during review, re-read them, rerun targeted tests, and state the final reviewed hashes.

A reproducible artifact should persist:

- git commit when meaningful;
- hashes of untracked/dirty source files that implement the run;
- database and sector hashes;
- design/specification version or hash;
- exact cost and risk configuration;
- execution and return-accounting bases;
- semantic definitions for counts such as `stop_events` versus administrative horizon exits.

Changing defaults, count semantics, or artifact fields without changing the schema/version makes older artifacts ambiguous even when their economic conclusion remains conservative.

## Gate honesty

A field named `passed_economic_gate` should not imply more than was tested. Verify:

- out-of-sample or walk-forward Sharpe evidence when the governing rule requires OOS;
- worst-position loss, stop frequency, re-entry churn, turnover, and estimated costs;
- declared cost/parameter sensitivities;
- finite values and valid metric domains;
- explicit zero-denominator behavior;
- thresholds documented before the observed result.

A historical artifact must always keep `deployment_approved = false`. Static/survivor evidence may reject a policy, but any positive result is capped at report-only shadow consideration and should say which gate dimensions remain untested.

## Verification sequence

1. Snapshot source/artifact identity.
2. Query the exact database schema and compare adjusted versus total-return columns.
3. Trace live and historical formulas side by side.
4. Quantify first eligible score date for IPOs/late entrants to expose warmup drift.
5. Quantify daily universe size and sector composition.
6. Inspect rename/reuse transitions and return tails.
7. Reconcile artifact configuration and count semantics against current source.
8. Run syntax checks and the focused simulator tests without editing the reviewed files.
