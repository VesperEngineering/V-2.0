# V20 minimum viable admission remediation plan v1

**Plan date:** 2026-07-23 UTC  
**Current decision:** **NO-GO now; admissible only after the ordered gates below pass**  
**Recommended minimum path:** a narrow, research-only SPY time-series experiment on the existing V20-local total-return adapter, followed by a genuinely future sealed holdout. This is the smallest path because it avoids the unevidenced historical constituent-membership requirement of the fixed 502-name cross-section without pretending that the 31-name validation subset cures that defect.

## 1. Decision and scope

Do not repair or retune the current XGBoost ranker first. Thirty parameter runs already reused the same post-2021 period, the broad source is survivorship-limited, its local adjustment contract is incomplete, and its five-session split is unpurged. More tree, depth, regularization, feature, threshold, or portfolio-rule tuning on those receipts would be exhausted micro-tuning, not new confirmatory evidence.

The minimum viable route is instead to test one predeclared effect on one named instrument, SPY. A single named instrument removes dynamic S&P 500 constituent membership from the claim. It does not rehabilitate the broad 502-name model, establish deployability, or authorize promotion.

Brennan remains the final authority. Before implementation or execution, Brennan must either:

1. approve the narrow SPY-only claim and the use of a frozen derived total-return snapshot as the experiment input; or
2. reject the narrow scope, in which case the plan stops at the broad-data gate in Section 8.

## 2. Facts, assumptions, and hypothesis

### 2.1 Observed facts

1. `reports/research/data_evaluation_admission_v1.md` found the current broad path NO-GO because adjustment, point-in-time universe, availability, purge/embargo, and independent-holdout gates were not met.
2. `reports/research/data_evaluation_admission_review_v1.md` independently retained the NO-GO but corrected the adjustment account: all 30 run receipts say that `D:\vesper\vesper_data\split_adjustments.json` was loaded and applied to 502 tickers. Those receipts are runtime claims, not a V20-local checksummed adjustment contract.
3. `vesper/data/massive/sp500/sp500_ohlcv.sqlite` is a raw fixed 502-ticker table with 2,482,807 rows from 2003-09-10 through 2026-07-21. It has no row receipt time, revision identifier, source key, or source hash. Its observed SHA-256 is `6ad6bc7ced7781b9f94dea030b06b71ed55a1f889a7e925cbb428398cecc1bb0`.
4. `scripts/train_model.py:44-76,208-225` permits an external adjustment file, falls back to raw prices if no map is found, and splits only on feature date. It does not fail closed on a local adjustment checksum and does not purge the five-session label interval.
5. `reports/model_iteration_state.json` records 30 rejected parameter runs and no accepted candidate. The receipts repeatedly evaluate the same post-2021 period. `reports/portfolio_ablation_2026-07-22.md` explicitly says its period is not a fresh promotion holdout.
6. V20 already contains `vesper/data/massive/adapters/total_return_ohlcv_adapter_20260717T153500Z.sqlite`. Read-only inspection found:
   - 169,556 daily rows for 31 alias-normalized tickers;
   - SPY is present with 5,737 rows;
   - date coverage is 2003-09-10 through 2026-06-30;
   - metadata declares `price_basis=total_return_adjusted`, `timeframe=1day`, and generation at `2026-07-17T15:39:01.593969+00:00`;
   - every adapter row has a source-map row and no source hash is null or empty;
   - the adapter SHA-256 is `825252f94efb228df37683d58a1199cbc101828bbe7f53079e9d066c28e5a70c`.
7. The backing local total-return database contains 169,951 rows for 33 source tickers and row-level source hashes. Its SHA-256 is `a6db6de1f3be73bcebb5adf539bb92108f2f47dbdeea1a88f85d133bfc4d635d`.
8. Exact read-only comparison of SPY rows across the local 2026-06-22, 2026-07-01, and 2026-07-17 adapter snapshots found zero mismatched OHLCV rows on their shared timestamps. This is useful truncation-stability evidence, not proof of the external build inputs.
9. The local governance database has only six alias/lifecycle membership records. It is useful for FB/META, QQQQ/QQQ, and GOOG/GOOGL identity handling, but it is not broad point-in-time constituent history.
10. `scripts/intermediate_momentum_research.py` already demonstrates read-only adapter loading, monthly formation, next-session-open labels, costs, and a matched control. It is not admissible evidence because it is cross-sectional, labels the broad source survivorship-limited, censors future discontinuities after seeing outcomes, and defines an already examined 2021-2026 `final_oos` period.
11. `requirements.txt` already includes NumPy, pandas, SciPy, scikit-learn, and pytest. The minimum path needs no new package or provider.

### 2.2 Assumptions requiring explicit approval or verification

1. The minimum objective is to demonstrate a scientifically admissible V20 CPU research cycle, not to validate or promote the configured 502-name `ml_model`.
2. SPY is the named instrument in the hypothesis, not a proxy for a historically reconstructed S&P 500 constituent universe. The conclusion will be conditional on SPY only.
3. A content-addressed V20-local derived snapshot with row source hashes, adjustment metadata, and revision-stability checks may be admitted as the experiment input even though the external raw build inputs named in its audit table are not all present under V20. An independent reviewer must approve this assumption before any selection result is treated as admitted. If full raw-to-derived reconstruction is required, this assumption fails and Section 8 applies.
4. Same-session adjusted close is available only after the session closes and the row is received. Therefore the signal may form after close T but may not execute at close T.
5. The future final holdout starts only after the experiment contract, code hash, and data policy are frozen. Data through the freeze timestamp is development or selection material, regardless of whether a particular metric was previously printed.
6. Total-return adjusted OHLCV is research accounting evidence, not proof that an order was executable at an adjusted price. Any later trading or deployment claim requires separate unadjusted executable-price and corporate-action reconciliation.

### 2.3 One falsifiable economic hypothesis

**Mechanism:** aggregate equity risk is adjusted gradually, so a positive medium-term SPY trend should persist over the next week; a non-positive trend should identify periods when holding cash avoids enough downside to overcome turnover costs.

**Predeclared hypothesis:** when SPY's total-return adjusted close after session T is above its adjusted close 20 eligible sessions earlier, a long-SPY/cash rule executed at the next eligible session's open and held for five eligible sessions will exceed a matched always-long SPY baseline by at least 5 basis points per non-overlapping five-session block after 10 basis points per traded side on a future sealed holdout.

**Candidate rule:** long SPY when the 20-session total-return is strictly positive; otherwise hold cash. The lookback is 20 sessions, threshold is zero, horizon is five sessions, and no parameter is fit.

**Equal-information simple baseline:** always long SPY on the exact same eligible blocks. The baseline receives the same frozen database, cutoff, eligible rows, formation dates, next-session-open execution convention, five-session exit, missing-row policy, and 10-basis-point per-side cost accounting. It ignores the momentum value but has no data or timing advantage.

**Primary metric:** the paired arithmetic mean of `candidate net block return - baseline net block return` on final-holdout blocks.

**Minimum useful effect and acceptance threshold:** at least +0.0005 per block, with the lower endpoint of a predeclared 95% moving-block bootstrap interval above zero. Use block length four, 10,000 resamples, and seed 42. Candidate cumulative net return must also be positive; this guardrail cannot rescue a failed primary metric.

**Secondary diagnostics, never rescue criteria:** candidate and baseline cumulative return, maximum drawdown, fraction of blocks invested, turnover, gross paired difference, and the same returns at 5 and 25 basis points per side.

**Falsification:** reject the hypothesis if the selection direction is non-positive, the final primary effect is below +0.0005, its lower confidence endpoint is not above zero, or the candidate cumulative net return is non-positive. Call an underpowered or mixed result inconclusive; do not relabel it successful.

## 3. Frozen chronological evaluation

The later experiment contract must resolve and record exact eligible session dates from the admitted adapter before any outcome is calculated.

1. **Development window:** 2003-09-10 through 2018-12-31. Use it only to implement and test timestamp, return, cost, and receipt invariants. Do not optimize lookback, threshold, horizon, cost, or bootstrap settings.
2. **Selection window:** 2019-01-01 through the last admitted pre-contract row. The first selection formation date must occur only after a five-session purge following the development boundary. Evaluate the single frozen candidate and baseline once.
3. **Final holdout:** the first eligible formation session after contract approval, code freeze, and a five-session embargo from all pre-freeze outcome intervals. Keep results sealed until at least 52 completed, non-overlapping five-session labels exist.
4. **Formation schedule:** anchor on the first eligible session in each partition and advance in five-session increments. The label for formation T is next-session open to the open five eligible sessions later. No label interval may cross a partition boundary.
5. **Purging:** exclude every formation row whose `[feature_time, label_exit_time]` interval intersects another partition. An automated interval-overlap assertion is required; a calendar-day approximation is not acceptable.
6. **Final-holdout access:** no intermediate final metrics, charts, logs, or partial verdicts may be opened. Operational checks may verify file arrival, schema, hashes, and row counts without computing candidate or baseline outcomes.
7. **One-shot rule:** after selection passes and the final contract is sealed, run the final comparison once. A rerun is allowed only for a documented deterministic software failure with identical contract, code, and input hashes; both receipts must be retained.

## 4. Finite search budget

The complete family is fixed at:

- one instrument: SPY;
- one economic hypothesis;
- one feature: 20-session total-return momentum;
- one threshold: zero;
- one holding horizon: five eligible sessions;
- one formation cadence: non-overlapping five-session blocks;
- one candidate rule;
- one equal-information baseline;
- one primary cost: 10 basis points per traded side;
- one primary metric and one confidence procedure;
- no model class, hyperparameter, feature, universe, threshold, horizon, or execution search.

The 5- and 25-basis-point cases are sensitivity diagnostics only. No result from them may select a new primary cost. The existing 30 XGBoost runs and portfolio ablations remain in the research ledger as exhausted, contaminated selection evidence and are not part of this search budget.

## 5. Ordered remediation slices

### Slice 0 — Brennan scope and provenance decision

**Action:** approve or reject the SPY-only claim and decide whether the frozen local derived adapter is an admissible research input without a V20-local raw rebuild.

**Acceptance evidence:** a dated decision record identifies the exact allowed claim, exact adapter path and SHA-256, the known external-build limitation, and the authorized next stage as research-only CPU evaluation.

**Stop condition:** if Brennan requires a broad 502-name claim or raw-to-derived V20 reconstruction, do not implement or run the narrow experiment. Continue only after Section 8's missing-data gate passes.

### Slice 1 — Freeze a standalone experiment contract before outcomes

**Code-side work:** none.

**Research artifact proposed:** `reports/research/spy_momentum_cpu_contract_v1.md`.

The contract must bind the hypothesis, source and adapter hashes, metadata rows, exact SPY row count and date range, session/calendar convention, feature time, next-open execution, label interval, partition dates, purge/embargo rule, costs, metrics, bootstrap settings, search budget, and stop rule. It must state that all pre-contract dates are development or selection material.

**Acceptance evidence:** an independent reviewer can recompute the contract hash and match every bound path and value to read-only V20 evidence. The contract is approved before selection outcomes are computed.

**Stop condition:** any unresolved timestamp, adjustment, source-hash, partition, or execution convention keeps admission at NO-GO.

### Slice 2 — Implement only the research evaluator and integrity tests

**Code-side work proposed:**

- create `scripts/spy_momentum_cpu_experiment.py` as a research-only, read-only evaluator;
- create `tests/test_spy_momentum_cpu_experiment.py`;
- do not modify `scripts/train_model.py`, `vesper/data/features.py`, the engine, strategies, configuration, model artifacts, or data.

The evaluator must use SQLite read-only mode, select only SPY one-day rows, reject duplicate or non-monotonic timestamps, require the declared total-return basis, require non-empty source hashes for every selected row, verify the input and contract hashes, and fail closed on any mismatch. It must not import broker, execution, live strategy, or scheduler code.

Required tests must prove:

1. the feature uses only rows at or before T;
2. the label uses T+1 open through the open five eligible sessions later;
3. no post-outcome discontinuity, missingness, or availability filter can remove a row after observing its label;
4. candidate and baseline use identical dates, prices, and costs;
5. formation blocks and chronological partitions do not overlap;
6. five-session purge and embargo interval assertions fail on boundary leakage;
7. selection and final phases are separate and the final phase refuses to run without the sealed manifest;
8. output is deterministic for fixed contract, data, code, and bootstrap seed;
9. the source database is never opened writable.

**Acceptance evidence:** focused pytest output, Python compile output, a clean scope diff, and a dry integrity receipt that contains no selection or final outcome metrics.

**Stop condition:** any leakage, writable data access, hash bypass, phase bypass, or nondeterminism is a hard NO-GO. Fix the class of defect before proceeding; do not compensate with statistical thresholds.

### Slice 3 — Independent data admission for development and selection

**Missing-data work:** none if Slice 0 admits the current frozen derived adapter. Otherwise this slice is blocked pending a V20-local raw/source package.

**Read-only checks:** verify adapter SHA-256, SPY schema, unique timestamp keys, complete source-map coverage, adjustment metadata, date coverage, and exact historical-row stability against older local adapter snapshots. Record the external build paths as a limitation; do not silently claim they are locally reproducible.

**Acceptance evidence:** a reviewer-signed admission receipt states `ADMIT_SELECTION` or the exact failed gate. The receipt distinguishes experiment reproducibility from raw-data reconstruction.

**Stop condition:** a changed historical SPY row without a source revision receipt, missing row hash, missing adjustment metadata, or reviewer rejection stops the experiment.

### Slice 4 — One selection run and freeze

**Action:** after Slices 0-3 pass, run the candidate and baseline once on the frozen selection partition using CPU only.

**Proposed receipt:** `reports/research/spy_momentum_cpu_selection_v1.json`, containing contract, data, code, environment, and output hashes plus the predeclared metrics.

**Acceptance evidence to proceed:** primary paired mean difference is positive, candidate cumulative net return is positive at the primary cost, every integrity check passes, and no contract deviation occurred. This is a direction/plumbing gate, not confirmatory evidence.

**Stop condition:** any non-positive selection direction, non-positive candidate net return, integrity failure, or unplanned manual intervention rejects the hypothesis before final holdout. Do not alter the lookback, threshold, horizon, cost, universe, or metric and retry on the same selection period.

### Slice 5 — Acquire and seal genuinely future holdout data

**Missing-data requirement:** an authorized data steward, not this quant-research agent, must place or identify a new V20-local, immutable, total-return SPY adapter snapshot after the contract freeze. It must preserve source keys/hashes, generated/receipt timestamps, revision policy, and prior-row history. The sacred `vesper/data/massive/` paths remain read-only to agents.

At least 52 completed non-overlapping final blocks are required. Earlier partial data may be admitted structurally but must not be scored. Final rows must begin after the approved contract and code freeze, not merely after the 2026-06-30 current adapter cutoff.

**Acceptance evidence:** final snapshot SHA-256, source/receipt manifest, adjustment-basis receipt, zero unexplained historical revisions, complete SPY source-map hashes, exact eligible final dates, and an independent `ADMIT_FINAL` decision.

**Stop condition:** no future sealed snapshot, no receipt lineage, an unexplained historical revision, or early outcome inspection leaves the task blocked. Historical post-2021 data may not substitute.

### Slice 6 — One final CPU evaluation and decision

**Action:** open the sealed final phase once, produce the paired primary metric and predeclared diagnostics, and retain the immutable receipt.

**Proposed receipt:** `reports/research/spy_momentum_cpu_final_v1.json`.

**Acceptance evidence:** all hashes match the sealed manifest; the primary paired mean difference is at least +0.0005; the predeclared 95% lower confidence endpoint is above zero; candidate cumulative net return is positive; and no integrity or contract deviation occurred.

**Decision:**

- **Advance only to a separately authorized replication gate** if every acceptance condition passes.
- **Reject** if direction or economic threshold fails.
- **Inconclusive** if the point estimate passes but uncertainty or sample integrity does not.

**Stop condition:** do not rescue a failed or inconclusive result by changing the lookback, horizon, threshold, cost, bootstrap, universe, or start date against the same holdout. A materially new hypothesis requires a new future holdout and new authority.

## 6. Code-side fixes versus missing-data requirements

### 6.1 Code-side fixes required for the minimum SPY path

1. A small read-only evaluator with explicit information and execution clocks.
2. Interval-based purge/embargo and non-overlap assertions.
3. Equal-information candidate/baseline accounting with fixed costs.
4. Contract/data/code hash verification and fail-closed phase separation.
5. Deterministic statistical output and immutable receipts.
6. Tests for leakage, outcome-conditioned filtering, data mutability, and holdout access.

These fixes need no new dependency and do not require changing the active trainer or live engine.

### 6.2 Missing-data or human-decision requirements for the minimum SPY path

1. Brennan's approval of the narrow claim and derived-snapshot provenance assumption.
2. Independent admission of the current adapter for development/selection.
3. A genuinely future, sealed SPY total-return snapshot with receipt and revision lineage.
4. Enough future observations to complete 52 non-overlapping final blocks without interim scoring.
5. A separate data-steward action for any write under `vesper/data/massive/`.

## 7. Explicit exclusions

This plan does not:

- admit, repair, rerun, or promote the current 502-name XGBoost ranker;
- treat the 31-name adapter as a broad historical equity universe;
- use the six-record governance database as S&P 500 membership history;
- reopen the post-2021 period as a final holdout;
- tune another tree, depth, regularization, feature, threshold, horizon, portfolio rule, or cost using the existing receipts;
- edit code, data, configuration, models, schedules, broker state, risk limits, or trading parameters in this task;
- train a model, use GPU, use a paid provider, access `D:/vesper`, or access broker/execution systems;
- claim adjusted OHLC values are executable market prices;
- authorize paper trading, live trading, deployment, capital allocation, or promotion;
- create a new generalized research framework, data abstraction, or dependency.

## 8. Exact broad-502 gate if Brennan rejects the narrow scope

If the intended claim must remain a historical 502-name cross-sectional `ml_model`, the minimum SPY path is not a substitute. Stop until all of the following are present together under an approved V20-local contract:

1. an immutable checksummed broad source snapshot with source, receipt, revision, calendar, and freshness metadata;
2. a checksummed V20-local split/dividend or total-return adjustment artifact, with factor validation and no raw fallback;
3. point-in-time membership covering additions, removals, ticker changes, inactive names, and effective dates for the full evaluation range;
4. explicit signal formation and next-action timestamps aligned to row availability;
5. five-session interval purging at every chronological boundary;
6. disjoint development, model-selection, and genuinely untouched final-holdout periods;
7. a frozen simple equal-information baseline and finite model-search ledger;
8. run receipts binding code, data, adjustment, universe, configuration, seed, environment, and output hashes.

The existing raw 502-name database, external-adjustment run logs, six alias records, 31-name validation adapter, 30 reused OOS runs, and retrospective portfolio ablations do not collectively satisfy this gate.

## 9. Final recommendation

Approve Slices 0-3 only if Brennan accepts a SPY-only research claim and an independent reviewer admits the frozen derived adapter. Then permit one CPU selection run. If it passes, freeze everything and wait for a genuinely future sealed holdout; there is no scientifically valid historical shortcut.

Until those gates pass, the admission state remains **NO-GO**. If Brennan requires the broad `ml_model`, stop rather than micro-tune and obtain the exact missing data package in Section 8 first.
