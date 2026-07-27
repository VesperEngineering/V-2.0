# Historical Stop-Backtest Data Source Audit — 2026-07-10

Use this as a dated evidence snapshot; re-query SQLite and inspect the current worktree before relying on it.

## Most defensible reconstruction path

No local dataset alone supports an unbiased primary S&P 500 stop-loss backtest. Build a new point-in-time, split-adjusted panel from the broad Massive normalized store, historical membership, historical sectors, expanded corporate actions, and alias/delisting governance. Until then, the existing adjusted 31-name surface supports only a fixed-cohort diagnostic.

### Broad raw foundation

`vesper_data/massive/normalized/day_aggs_coverage_expanded_2026.sqlite`

- Table: `day_aggs`
- Columns: `ticker, ticker_upper, as_of_date, volume, open, close, high, low, window_start, transactions, source_key, source_sha256`
- Observed coverage: 48,998,285 rows; 35,690 symbols; 2003-09-10 through 2026-06-18.
- Raw/unadjusted. It is broad enough to source historical and delisted names but must be joined to expanded corporate-action, membership, sector, and alias data.

Current corporate-action reference is only an active-universe pilot:

`vesper_data/massive/reference/massive_reference_corporate_actions_active_universe_20260622.sqlite`

- `splits`: 35 rows
- `dividends`: 2,024 rows
- `ticker_reference`: 33 rows
- `ticker_overview`: 32 rows
- Must be expanded to every point-in-time constituent and alias before a primary run.

### Best existing adjusted diagnostic surface

Canonical-selection adapter:

`vesper_data/massive/adapters/total_return_ohlcv_adapter_20260701T182524Z.sqlite`

- `ohlcv_data(ticker, timestamp, open, high, low, close, volume, timeframe)`
- `ohlcv_source_map(ticker, timestamp, timeframe, source_ticker, source_as_of_date, source_key, source_sha256, alias_policy)`
- Observed coverage: 169,556 rows; 31 canonical symbols; 2003-09-10 through 2026-06-30; zero duplicate ticker/date keys.
- Adapter prices are total-return-adjusted and should not directly drive stop touches or gap tests.

Underlying source:

`vesper_data/massive/total_return/day_aggs_total_return_adjusted_active_universe_20260701T182524Z.sqlite`

Table `total_return_adjusted_day_aggs` carries raw OHLCV, `adjusted_*`, `total_return_adjusted_*`, split/dividend factors, and source provenance. Observed coverage: 169,951 rows; 33 source/alias symbols; 2003-09-10 through 2026-06-30.

For a stop diagnostic, use `ohlcv_source_map` for canonical row selection, join on `source_ticker + source_as_of_date`, and consume `adjusted_open/high/low/close/volume`. The adjusted builder currently applies the future split factor while its dividend factor is 1.0, so `adjusted_*` is the split-adjusted executable-price basis. Reserve `total_return_adjusted_close` for return accounting, not stop levels.

### Reject as primary sources

`vesper_data/massive/sp500/sp500_ohlcv.sqlite`

- `sp500_ohlcv(ticker,date,close,volume,open,high,low)`
- Observed: 2,478,289 rows; 502 July-2026 names; 2003-09-10 through 2026-07-08.
- Raw split jumps are present: NVDA 1208.88 to 121.79 in June 2024; AAPL 499.23 to 129.04 in August 2020.
- It backfills the current constituent cohort and is survivorship-biased.

`artifacts/db/sp500_ohlcv.sqlite` and `artifacts/db/sp500_ohlcv_v2.sqlite` had malformed column alignment in this snapshot (price-like text in date/timestamp and nanosecond timestamps in price fields); do not treat similarly named files as interchangeable without sampling rows and verifying types.

The small `day_aggs_coverage_expanded.sqlite` was previously rejected as history-incomplete even when its max date looked fresh. Check both cutoff and full-history row coverage.

## Membership and sector blockers

- `data/sp500_tickers.json` was a 2026-07-07 current Wikipedia snapshot, not point-in-time membership.
- `data/sp500_sectors.json` contained 502 current ticker mappings across 11 sectors and no effective dates.
- `scripts/build_sector_map.py` builds that map from current Wikipedia constituents.
- Repository status said MIT-licensed historical S&P membership exists externally, but the exact source was not recorded locally.
- Exact historical company-level GICS sectors were unavailable locally; SIC inference had been rejected as an approved substitute.
- `total_return_universe_membership_*.sqlite` contained only six alias/lifecycle rows around FB/META, QQQQ/QQQ, and GOOG/GOOGL. Its scope label is not proof of historical benchmark membership.

## Frozen reconstruction inputs

Compute complete-case cross-sectional signals at close `t`:

1. `intraday_range`: mean of `(high-low)/close` over 21 sessions.
2. `size`: `-log10(mean(close*volume, 20 sessions))`, requiring at least 15 valid observations.
3. `mean_reversion`: `-longest_up_streak_20/10 - 0.7*ret_10d - 0.5*(2*(BB_position_20-0.5)) - 0.3*((RSI14-50)/25)`.
4. Composite: `(1.0*z_range + 0.5*z_size + 0.4*z_mean_reversion) / 1.9`, with population-standard-deviation z-scores.

Select the highest scorer in each PIT sector, then choose winners from the four highest-scoring sectors. Use unrounded scores and ticker ascending for ties. Compute at close `t`, execute at next-session open, and preserve 5% cash (23.75% in each of four names).

Run matched no-stop, ATR-only, gap/intraday-only, time-only, and combined variants. Canonical stop: ATR(14), `clamp(3*ATR/entry, 12%, 20%)`, 15% fallback; gap-through-stop at open; otherwise low-touch at stop plus declared slippage; -8% opening-gap breaker; -10% intraday breaker; day-15 return <= 0 exits next open; five-session cooldown; no trailing or portfolio drawdown stop. Pre-register costs and report sensitivities.

## Historical-code pitfalls confirmed

- Live factor classes accepted `date_stamp` but fetched the globally latest dates; historical replay needs explicit `date <= as_of_date` queries.
- Shared OHLCV row fetches lacked `ORDER BY ticker,date`; rolling panels must order explicitly.
- The live blend used ticker-specific available-weight denominators; historical replay should require complete cases for the frozen kernel.
- The FM script did not match all live formulas/signs, omitted a cross-sectional intercept, and zero-filled missing exposures.
- Existing `vesper_backtest_v1/v2/v3`, factor-portfolio, and FM artifacts used incompatible factors, fixed/current universes, static sectors, and/or raw prices. They are diagnostics, not a matched live-strategy baseline.

## Audit discipline

Record HEAD plus staged, unstaged, and untracked state. This snapshot was taken at HEAD `9ed2d437821f5874df82cd953709dfd4d2999c09` with a very dirty worktree. Never infer current strategy truth from one generated artifact without reconciling it against current source and provenance.