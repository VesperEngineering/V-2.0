# Point-in-Time Five-Session Ranking Audit Pattern

Use this reference for read-only audits of whether Vesper can support a leakage-safe cross-sectional S&P 500 ranking experiment. It records the reusable method plus the dated 2026-07-21 local snapshot; code and current receipts remain authoritative.

## Audit order

1. **Identify every physical data island.** Separate the static S&P database, broad Massive day aggregates, adjusted adapters, Qlib exports, analyst SQLite, Parquet stores, factor-history caches, and any research-only repository.
2. **Measure physical state, not documentation claims.** Open SQLite with `file:...?...mode=ro`; inspect `sqlite_master`, `PRAGMA table_info`, indexes, exact row/date counts where affordable, `MAX(rowid)` plus ingestion receipts for very large tables, duplicate key groups, and per-date symbol coverage. Use Parquet metadata/statistics before loading full files.
3. **Trace provenance.** Require source keys, hashes, adjustment policy, calendar policy, and immutable snapshot identifiers. Receipts are evidence about a build, not substitutes for querying the file that exists now.
4. **Audit universe semantics independently from bars.** Compare current constituents, every PIT snapshot, and broad-data availability on the actual rebalance dates. Test adjacent change dates, additions/removals, aliases, class shares, delistings, and ticker reuse.
5. **Audit features, labels, models, and portfolios as separate layers.** A usable price panel does not prove historical feature reconstruction; a valid label does not prove split isolation; a rank-IC report does not prove portfolio economics.

## Universe checks that must not be skipped

- Treat `data/sp500_tickers.json` and current sector maps as present-day snapshots; long backfills over them are survivor cohorts.
- Test PIT effective-date behavior around concrete changes. Snapshot count and date range alone do not establish correct as-of semantics.
- Never treat coverage on `ticker_upper` as execution-safe coverage. It is an upper bound until case collisions and permanent security identities are resolved.
- Measure coverage on each intended score date and separately require valid entry and terminal prices. Do not condition the score universe on future-label availability.
- Historical sector caps require effective-dated sectors. A current GICS map may be shown only as a non-PIT diagnostic.

## Feature and label checks

- Prove that `date_stamp` or `as_of_date` changes the SQL cutoff. A date used only in an artifact filename is not historical reconstruction.
- Confirm sorting by security and exchange session before rolling features or `shift(-h)` labels.
- Fit imputers, scalers, winsorization parameters, and model hyperparameters on training only. Same-date cross-sectional ranks are allowed only over the admitted PIT universe.
- Preserve `feature_cutoff_date`, `label_start_date`, `label_end_date`, `universe_member_flag`, `window_id`, and `data_source_snapshot` in the row schema.
- For a score formed after close on session `t`, use an executable five-full-session label such as `open[t+6] / open[t+1] - 1`, not a same-close fill.
- Purge every row whose `label_end_date` reaches the next split and embargo one full holding interval. Labels created before segment assignment commonly leak across boundaries.

## Model/evaluator audit

- Distinguish algorithmic CPU capability from a runnable local dependency and from a verified end-to-end runner.
- Compare a fixed factor composite, Ridge, and one CPU tree model on the identical rows, folds, labels, costs, and portfolio code.
- Verify that each displayed walk-forward window actually refits using only its training rows. A report that slices one precomputed signal file into yearly windows is a stability report, not walk-forward training.
- Normalize turnover terminology. For fully invested long-only weights, report one-way turnover as `0.5 * sum(abs(w_t - w_{t-1}))`; charge costs on traded notional `sum(abs(delta_weight))`.
- Require rank IC, gross/net returns, benchmark excess, turnover, cost drag, drawdown, concentration, fold/year stability, and contribution concentration. A turnover proxy or rank IC alone is insufficient.

## Frozen protocol template

- Rebalance every fifth XNYS session.
- Score after close `t`; enter at `open[t+1]`; exit/rebalance at `open[t+6]`.
- Base basket: equal-weight `top_k=25`, with incumbents retained through `hold_k=40`; freeze all tie-breaks.
- Outer expanding folds must have disjoint purged train/validation/test labels and true refits.
- Base friction should match the current project cost contract; pre-register higher-cost stress cases.
- If prior artifacts have already inspected the entire historical period, call any reused interval a **locked retrospective confirmation set**, not an untouched holdout. A strictly untouched holdout must be prospective and opened once.

## Dated local snapshot: 2026-07-21

- `vesper_data/massive/normalized/day_aggs_coverage_expanded_2026.sqlite`: 48,998,285 rows, 5,730 complete XNYS dates from 2003-09-10 through 2026-06-18, 35,823 case-sensitive and 35,690 uppercased ticker identities. Repository admission receipts explicitly defer identity, corporate actions, dividends, delistings, and survivorship review.
- `vesper_data/massive/sp500/sp500_ohlcv.sqlite`: 2,481,285 rows for 502 current constituents through 2026-07-20; PIT member intersection at year-end was about 49% in 2004, 74% in 2018, 90% in 2023, and 97% in 2025.
- `vesper_data/sp500_pit_membership.json`: 402 changes, 304 snapshots, 1976-07-01 through 2026-06-30, union 855 symbols. Adjacent-change inspection showed pre-change membership on the dated snapshot under the current lookup contract; see `references/pit-membership.md`.
- Uppercased-symbol weekly coverage on the broad table was an upper bound: every 2018 week exceeded 95%; every 2023 week exceeded 98%. This does not resolve permanent identity or total-return adjustment.
- No existing artifact combined PIT membership, five-session executable labels, true fold refits, buffered weekly portfolios, costs, drawdown, and concentration. Existing one-day tree, 30-symbol Qlib, and static-constituent backtests are controls or diagnostics only.

## Adversarial evaluator probes and completion-gate checks

Add these bounded probes before accepting a five-session evaluator, even when its focused tests pass:

1. **Future-label availability probe.** Give a security complete score-time features and prices, but remove only its terminal label price. It must remain in the score-time universe. Build the admitted universe from information available at `t`; join labels afterward for evaluation. A single `dropna()` over features plus `target_return` silently conditions selection, rank IC, and returns on future survival.
2. **Missing-session probe.** Remove one whole exchange session from an otherwise complete fixture. A five-session label must fail/skip or still resolve through an explicit XNYS calendar; it must not become the fifth retained row and span six real sessions while annualization still assumes five.
3. **Effective-date membership probe.** For every dated change, classify the stored snapshot as pre-change or post-change by checking whether the added name is present and the removed name absent. Pre-change snapshots combined with `bisect_right` delay each change until the next snapshot. Freeze and test one explicit convention: membership effective before open, after close, or next session.
4. **Execution-timing probe.** Perturb next-open prices while holding closes fixed. A score computed with close-`t` features must use `open[t+1] -> open[t+6]` (or another explicitly executable frozen convention), never `close[t] -> close[t+5]` unless a separately justified pre-close/MOC execution model exists.
5. **Cost-placement probe.** For equal-weight long-only portfolios, one-way turnover is `0.5 * sum(abs(delta_weight))`. Charge per-side costs on actual traded notional: initial deployment buys one side, while a fully funded rebalance can trade both sells and buys. Do not apply `2 * one_way_cost * turnover` to the initial portfolio or to every independently reset fold.
6. **Negative-aggregate gate probe.** Construct four positive windows and two modest negative windows such that aggregate after-cost return remains negative, drawdown stays within the frozen cap, and the candidate beats a worse baseline. Pre-holdout qualification must still reject unless the protocol explicitly allows a negative-return model to consume the holdout.
7. **Rejected-baseline recovery probe.** Force the simple baseline to fail one guardrail. The lifecycle must publish a terminal baseline-rejected state, clear its active marker, and either continue under an explicit policy or stop cleanly. Summary generation must not assume a champion exists after receipt/ledger publication.
8. **Completion-verifier probe.** Test empty, partial, all-rejected, holdout-Fail, and holdout-Held evidence. Distinguish artifact integrity (`VERIFIED`) from scientific completion. A completion gate must require the exact queue, a non-baseline pre-holdout KEEP, one candidate-bound holdout receipt, and holdout PASS; optional `--require-holdout` flags or mere receipt existence are loopholes.
9. **Holdout-access probe.** Perturb all holdout features and labels and require pre-holdout outputs to remain byte-identical, but also inspect the producer path. If the pre-holdout runner materializes, feature-engineers, or loads holdout outcomes, describe it as logically sliced—not sealed or untouched. A true seal needs a separate inaccessible artifact/process seam opened only after qualification.
10. **Fresh-process determinism probe.** Run Ridge/tree evaluation in fresh subprocesses with different `PYTHONHASHSEED` values and compare canonical output hashes. Also enforce, rather than merely record, Python/package versions, CPU device, thread caps, and model parameters. Include the environment lock/requirements identity in the release manifest; an interpreter hash does not bind installed packages.

When auditing a staged index, hash the exact `git diff --cached` bytes before and after probes. If concurrent unstaged fixes appear, keep the verdict bound to the unchanged staged hash and report the newer working-tree delta separately rather than crediting it to the reviewed candidate.

## Admission rule

Do not describe a study as a full PIT S&P 500 backtest until effective-date membership, permanent identity, split/dividend/delisting returns, entry/exit prices, and historical sector claims are all admitted. Before that point, label results `partial-PIT OHLCV research` and surface date-level coverage explicitly.
