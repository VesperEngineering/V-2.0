# V20 data and evaluation admission audit v1

**Decision date:** 2026-07-23 UTC  
**Scope:** V20 local files and a read-only SQLite inspection only. No data, code, configuration, model artifact, provider, or `<legacy-vesper-root>` content was changed or read.

## Decision standard

A fresh CPU experiment contract needs a reproducible source path and freshness evidence, a valid adjusted return basis, a point-in-time universe, unambiguous feature/label clocks, purged five-session label boundaries, and independent train/model-selection/final-holdout periods. Each item below is classified from observed V20 evidence; historical report claims are not treated as proof when their required local input is absent.

## Observed local source state

| Item | Classification | Evidence | Admission implication |
|---|---|---|---|
| Exact primary OHLCV path | **EVIDENCED** | `config/settings.yaml:21-27` selects provider `massive` at `vesper/data/massive`; `vesper/data/feed.py:124-166` reads `vesper/data/massive/sp500/sp500_ohlcv.sqlite`, table `sp500_ohlcv`. Read-only inspection found 2,482,807 rows, 502 tickers, no duplicate `(ticker, date)` groups, and dates 2003-09-10 through 2026-07-21. | A local source location and basic coverage are reproducible for this checkout. |
| Freshness and receipt lineage | **MISSING** | The database file mtime is 2026-07-22T22:42:38Z and its latest market date is 2026-07-21; audit time is 2026-07-23T13:02:17Z. There is no observed delivery manifest, source/receipt timestamp, checksum, vendor revision policy, or immutable snapshot identifier. | The source is not admissible as a fresh point-in-time input. It is also missing the 2026-07-22 US market session as of this audit. |
| Raw versus split adjustment | **INVALID** | `MassiveFeed` selects raw OHLCV columns without adjustment (`vesper/data/feed.py:147-161`). The current trainer only applies split factors when `vesper/data/massive/split_adjustments.json` (or an alternate path) exists (`scripts/train_model.py:44-76,208-214`); that local file is absent, so the current path explicitly falls back to raw prices. | Split-sensitive price features and five-session returns are not admissible. |
| Total-return adjustment | **MISSING** | No total-return field, dividend adjustment, or verified local total-return adapter was observed in the primary source path. The research evaluator labels the default `sp500_ohlcv` source as `raw` (`scripts/intermediate_momentum_research.py:194-225`). A separate adapter code path can label an `ohlcv_data` table as total-return-adjusted, but no local primary adapter snapshot was evidenced. | Total-return research claims cannot be based on the primary source without an identified and versioned adapter. |
| Universe membership and survivorship | **INVALID** | The SQLite source is a fixed 502-ticker set; the research evaluator explicitly labels it `fixed-502-universe` and `survivorship-limited` (`scripts/intermediate_momentum_research.py:12-24,215-224`). `config/universe.yaml` is a static ticker list and carries no effective dates or constituent-history provenance. | Cross-sectional results may use present-day survivor membership and are not admissible for an unbiased historical experiment. |
| Feature timestamp discipline | **MISSING** | Feature formulas use rolling/current-or-past OHLCV values (`vesper/data/features.py:32-126`), which is code evidence against direct row-level future-price reads. However, the local daily bars have no source publication, receipt, or session-availability clock, and `intraday_ret` includes the same-row close (`vesper/data/features.py:101-102`). | The code establishes only a feature-date convention, not a deployable availability-time convention. A contract must state whether a date's close is known at signal formation and use only information available then. |
| Label timestamp discipline | **EVIDENCED** | `compute_label` and the trainer define the target as `close.pct_change(5).shift(-5)` (`vesper/data/features.py:129-136`; `scripts/train_model.py:101-114`): row T receives the T-to-T+5 close return. | The intended five-session forward-label convention is explicit, but it requires purge/embargo at every split boundary. |
| Five-session overlap and purging | **INVALID** | The trainer splits samples solely by feature date at 2021-01-01 (`scripts/train_model.py:219-225`). No purge or embargo implementation was found in V20 Python sources. Thus training feature dates immediately before 2021-01-01 have labels whose outcome window crosses into the test period. | The existing chronological evaluation is contaminated at the train/test boundary and cannot admit a fresh contract unchanged. |
| Train/model-selection/holdout separation | **INVALID** | The trainer has one chronological train/test split only (`scripts/train_model.py:219-239`), not separate train, selection, and final holdout periods. `reports/model_iteration_log.md` records repeated parameter experiments against the same OOS evaluation, so that OOS period has been used for model selection. The portfolio ablation likewise states it is not a fresh promotion holdout (`reports/portfolio_ablation_2026-07-22.md:1-16`). | No untouched final holdout exists in the inspected V20 evidence. Historical OOS metrics are research diagnostics, not admission evidence. |

## Evidence conflicts and limitations

- `reports/model_iteration_log.md` repeatedly describes prior runs as using “local split-adjusted Massive data,” but the current checkout has no local split-adjustment map and the current trainer warns then uses raw prices when none is found. This audit classifies the active local input as raw; the historical adjustment claim is **unverified** for a fresh run.
- The database is structurally usable (single table, complete latest-date coverage across 502 tickers, no duplicate ticker/date groups), but structural checks do not establish point-in-time availability, corporate-action correctness, or constituent history.
- This audit intentionally did not compare against `<legacy-vesper-root>`, because local V20 evidence already fails admission and no integrity comparison is required to identify the blockers.

## Conditions required before a new CPU experiment contract

1. Freeze a local, checksummed source snapshot with source, receipt, and revision timestamps; refresh it through the agreed cutoff.
2. Supply and validate a versioned split-adjustment and dividend/total-return policy, or explicitly limit the contract to a research question valid on raw prices.
3. Provide point-in-time constituent membership (including additions, removals, ticker changes, delistings, and effective dates) and bind it to the snapshot.
4. Define signal formation and execution timestamps, including whether same-session close values are permitted, and align features/labels to that availability rule.
5. Purge at least the five-session forward-label horizon (or use an equivalent embargo) at every chronological boundary.
6. Reserve disjoint chronological periods for training, model selection, and a final untouched holdout; do not tune against the holdout.

## Final admission decision

**NO-GO** for a new CPU experiment contract using the current local Massive-derived input and existing chronological evaluation. The decisive failures are raw/unverified adjusted prices, survivorship-limited static membership, absent five-session purging, and reuse of the only OOS period for selection. The source and evaluation may be reconsidered after all six conditions above have independently evidenced completion.
