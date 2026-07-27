# Scientific-Integrity Repair Pattern for Cross-Sectional Ranking

Use this pattern when review finds target leakage, invalid execution timing, compressed session horizons, PIT membership drift, mutable criteria, comparator dead-ends, or a verifier that only checks hashes.

## Non-negotiable invariants

### 1. Separate the score-time universe from future outcome availability

Construct features using information available at the signal cutoff only. Never include `target_return`, `target_rank`, future prices, or future-presence flags in the `dropna`/admission mask for score-time rows.

A security that is feature-complete at close `t` remains in the scoring universe even when its later exit price is missing. Preserve that row with an unavailable label and fail the affected evaluation date explicitly; do not silently shrink the universe. Test this by deleting one selected name's future price and proving:

1. the name still exists in the feature frame at `t`; and
2. evaluation raises a future-outcome completeness error.

### 2. Bind signal, entry, and exit to executable prices

For an after-close five-session ranking contract:

- signal cutoff: close `t`;
- entry: split-adjusted open `t+1`;
- exit/rebalance: split-adjusted open `t+6`;
- held horizon: five exchange sessions.

The label is `open[t+6] / open[t+1] - 1`, not close-to-close and never a same-close fill. Store signal, label-start, and target-end dates in the feature artifact so tests can assert exact offsets.

### 3. Index on a frozen exchange calendar, not retained panel rows

A partial or missing cross-section must not turn five sessions into six calendar sessions. Materialization should:

1. obtain an authoritative, versioned XNYS session sequence for the frozen date range;
2. reject non-session dates;
3. detect a wholly absent session inside the observed range;
4. retain partial sessions with a monotonic `session_index` while marking them `eligible_rebalance=false`;
5. use the full session index for rolling features, rebalance cadence, and label offsets.

If an internal calendar implementation is unavoidable, freeze its supported range, include special closures and non-federal market holidays, and regression-test it against an authoritative schedule. At minimum cover Good Friday, observed Juneteenth, New Year edge cases, and known one-off closures. An unverified homemade calendar is not a completed repair.

### 4. Reconstruct PIT membership using the source's actual semantics

Do not infer effective-date behavior from snapshot filenames. If same-day snapshots are pre-change:

1. normalize and validate each ticker;
2. group additions/removals by effective date;
3. require a same-day pre-change snapshot;
4. require every removal to exist and every addition to be absent;
5. apply all changes atomically to produce the post-change membership used on that date;
6. test adjacent days around both an addition and a removal.

Ticker strings are path input as well as financial identifiers. Constrain their grammar before constructing file paths; then separately enforce approved-root containment and reparse/junction safety.

### 5. Freeze the complete scientific protocol

Validate exact nested keys and exact values for target construction, walk-forward windows, holdout, features, portfolio rules, costs, model queue/configuration, evaluator metrics, acceptance criteria, runtime bounds, authority, and external evidence bindings. Unknown nested fields fail closed.

Production entry points should accept only the canonical protocol path and a compiled semantic hash. Isolated materialization tests may vary physical fixture paths, but executable runs must not accept an alternate protocol with moved dates, zero costs, or relaxed thresholds.

**Hash-ordering pitfall:** compute and pin the canonical protocol hash only after all protocol edits are final. Any later field addition invalidates the pin. Add a test that mutates a data boundary in an alternate file and proves the executable rejects it.

### 6. Account for costs over the full position lifecycle

For a one-way cost `c`:

- initial deployment: subtract `c` once;
- later rebalance: subtract `2*c*turnover` for sells plus buys;
- terminal liquidation: subtract `c` once.

Do not charge the initial book two-way merely because turnover is represented as `1.0`, and do not omit the final exit. Test a no-turnover two-period portfolio where the expected net returns expose both boundary costs.

### 7. Treat the baseline as a comparator, not a promotion winner

A well-formed factor-composite baseline must be established even when its return, drawdown, turnover, or concentration is poor. Rejecting the comparator can strand the queue before trained candidates run. Record it as the immutable baseline while preserving research-only/no-promotion authority.

Trained candidates have separate gates and must include positive aggregate after-cost return; "loses less than baseline" is insufficient for `KEEP`.

### 8. Verification must recompute science and enforce completion

A final verifier must require:

- the exact canonical experiment queue in order, once each;
- receipt/model/experiment identity agreement;
- at least one trained-model `KEEP`;
- a trained current champion;
- a candidate-bound final-holdout `PASS`;
- byte-equivalent recomputation of every pre-holdout evaluation and sequential decision;
- recomputation of baseline/candidate holdout evaluations and the holdout decision.

Optional `--require-holdout` flags are inappropriate for a completion verifier. If a pre-holdout audit mode is needed, give it a separate command/status that cannot emit `VERIFIED` completion.

## RED-GREEN workflow

Repair one invariant at a time:

1. Write the smallest adversarial regression and run it to observe the intended failure.
2. Implement the narrow production change.
3. Run syntax checks and only that regression.
4. Move to the next invariant.
5. Run the complete focused suite after all slices.

Lifecycle tests should use the exact frozen protocol. Stub scientific evaluation deterministically at the module boundary rather than weakening production thresholds in test fixtures; evaluator correctness belongs in evaluator tests, while receipt/recovery tests should remain fast and hash-valid.

Keep the real experiment queue, final holdout, Kanban, and scheduler untouched throughout repair. Synthetic probes use disposable external directories only.

### 9. Make raw corporate-action repair prefix-invariant

For point-in-time research artifacts, a split discovered later must not rewrite the feature inputs that existed before its event date. A conventional retrospectively back-adjusted series may be useful for charting, but it is not automatically a valid PIT source.

For a causally normalized raw fallback:

1. detect a split from the event-day close/previous-close and open/previous-close ratios;
2. leave every pre-event row byte-for-byte unchanged;
3. normalize prices from the event row forward (for a raw ratio `r`, divide the suffix prices by `r`) and normalize suffix volume in the inverse economic direction;
4. if a residual jump remains unexplained, return its first date and quarantine only that suffix;
5. retain the safe prefix instead of deleting the ticker's entire history.

Use a prefix-invariance regression: run the adjustment on a prefix alone and on the same prefix plus a future split, then require exact equality of the two adjusted prefixes. Add a second probe where a future non-split jump truncates only the suffix. If using a provider-adjusted source instead, require dated adjustment provenance showing that future corporate-action knowledge cannot alter earlier admitted features.

### 10. Retire contaminated holdouts prospectively

If a proposed final holdout was materialized, feature-engineered, inspected, or used in diagnostics, mark it `RETIRED_NON_VIRGIN`; renaming it does not restore untouched status. Select a replacement that begins after a recorded selection timestamp—preferably a complete future exchange year—and keep it unavailable until the period and its PIT source data are complete.

Persist a hash-bound selection manifest containing:

- the retired period, reason, and historical artifact hashes;
- replacement dates and authoritative exchange-calendar source;
- selection timestamp plus source-data and membership cutoffs at selection;
- `source_materialized=false`, `features_materialized=false`, `opened=false`, `evaluated=false`, and `opening_authorized=false`;
- an explicit execution state such as `UNARMED_PROPOSAL`.

The evaluator, lifecycle runner, and CLI must refuse an unarmed proposal before loading replacement-period data or writing a receipt. A later source extension and one-shot opening require a separately reviewed protocol. Prospective selection is evidence of non-contamination; it is not a holdout `PASS` and does not satisfy lifecycle-completion gates.

### 11. Treat authority extracts and replay reports as protocol dependencies

When an internal exchange calendar is necessary, preserve a bounded authoritative extract (URL, capture time, heading, exact closure table, and observance footnotes) and hash-bind it. Do not apply generic federal-holiday observance rules blindly: NYSE's Saturday New Year's Day rule can leave the preceding Friday open. Test exact published dates, Good Friday, Juneteenth, early-close-as-session behavior, and supported one-off closures. If the live authoritative page only covers future years, recover archived captures of the official NYSE origin page for each historical table and record the archive only as transport. Legacy captures may be JavaScript shells; inspect named partial/data endpoints or select a later rendered official capture rather than inferring dates. Discover exceptional closures separately through the archived official ICE/NYSE press-release prefix instead of guessing a release slug. For the 2014–2025 C1 range, this method established recurring dates from official annual tables, Juneteenth beginning in 2022, and separate official releases for 2018-12-05 and 2025-01-09. Exact-set testing then exposed the omitted Carter closure. Observed OHLCV agreement, a federal proclamation, or a third-party calendar does not by itself prove historical exchange authority. Bump the calendar/evidence version whenever one date changes, because every session-indexed descendant becomes stale. Use the generic recovery and manifest procedure in the `evidence-artifact-integrity` skill's `references/authoritative-calendar-evidence.md`.

For PIT membership, freeze expected snapshot/change counts and produce a deterministic replay report that proves every declared row transforms its same-day pre-change snapshot into the exact post-change set. Report both total change rows and unique effective dates; a snapshot-count check alone is insufficient.

Bind these evidence hashes before computing the canonical protocol hash. The identity dependency order is: authority/selection/replay evidence -> protocol -> dataset manifest -> feature-builder/helper identity and feature manifest -> release manifest -> staged-diff digest -> independent review. Adding any child binding after its parent was pinned makes the parent stale and requires regeneration, never hand-rebinding.

## Final closure checklist

Before calling the repair complete:

- verify the exchange calendar against an authoritative source;
- replay the real membership artifact through strict change validation;
- include helper dependencies or the whole module in feature-builder identity;
- ensure holdout-period anomalies cannot influence pre-holdout source admission/quarantine;
- regenerate protocol, dataset, feature, evaluator, and release identities in dependency order;
- run focused adversarial tests, full relevant tests, formatting/lint, compile, and diff checks;
- stage one exact slice and obtain independent scientific review against its immutable diff hash.

If tooling or turn limits interrupt before this checklist, report the repair as partial and preserve the HOLD. Passing unit slices are evidence of progress, not authorization to execute the real queue or open the holdout.
