# Split Adjustment + Scoring Universe Gate (2026-07-14)

Session remediation after Vesper Quant worker audits (Thomas / Research / Riley).

## Problem 1 — split jumps (CRITICAL)

- Source: `vesper_data/massive/sp500/sp500_ohlcv.sqlite` stores raw Massive day bars.
- Example: NVDA 2024-06-07 close ≈ 1208.88 → 2024-06-10 close ≈ 121.79.
- Effect: every raw-close factor saw false returns / ATR / gap / channel events.
- Massive adjusted DB at `vesper_data/massive/adjusted/` covers **~33 tickers only** — useful for validation, not production S&P.

## Fix — cumulative forward factors

1. Detect candidate splits as consecutive-session close ratios matching standard n:1 ratios (2,3,4,5,7,10,20) within ±2%.
2. Iterate **backward** so most recent bars keep factor 1.0; pre-split history multiplies by 1/n at each split.
3. Write `vesper_data/split_adjustments.json` → `{ticker: {date: factor}}`.
4. Shared API in `app/factors/db.py`:
   - `fetch_adjusted_ohlcv_rows(...)` — drop-in; multiplies open/high/low/close.
   - `get_split_adjustment(ticker, date, root=...)` — raw SQL factors.
5. Wired into core price factors: mean_reversion, intraday_range, channel_breakout, gap_volatility / gap_vol_20d, max_return, range_vol_ratio, size, sp500_technical.

### Validation anchors

| Name | Event | Check |
|------|-------|-------|
| NVDA | 10:1 2024-06-10 | pre-split adj_close ≈ 122.x continuous with post |
| AAPL | 4:1 2020-08-31 | pre ≈ 124.81 continuous |
| AMZN | 20:1 2022-06-06 | pre ≈ 122.35 continuous |

Matches the 33-ticker Massive adjusted active-universe artifact within ~0.5 on close.

### Remaining orphans

- Residual raw-SQL consumers (e.g. parts of `massive_intraday` / legacy `massive.py`) still need audit.
- Adjustment is **split-only**, not full total-return (dividends omitted) unless a later total-return path is admitted.

## Problem 2 — universe leakage (CRITICAL)

- `market_micro` (and similar) score ~19k Massive names.
- Combiner used union of all factor tickers → dry artifact rows like IAUX / ALIT dominated z-rank tips.
- Current-constituent splits vs full panel are incomparable cross-sectionally.

## Fix — admitted scoring universe at combine time

In `scripts/run_all_factors.py`:

```text
raw_tickers = union(factor scores)
admitted = raw_tickers ∩ load_scoring_universe()  # data/sp500_tickers.json
rank only admitted; count excluded
```

Artifact keys:

- `universe: "sp500_current"`
- `universe_size`
- `external_factor_tickers_excluded`

Regression: `tests/test_run_all_factors.py`
(`test_run_excludes_non_universe_factor_tickers`, universe load helper).

## Explicit non-fixes (do not claim)

- Point-in-time historical membership still missing → historical backtests remain survivor-cohort diagnostics.
- Data freshness (`resolve_signal_date` / XNYS prev session) independent of these gates.
- Governance false-green issues (Riley) are board-language problems, not solved by price/universe plumbing.

## Operator language

Prefer: “live factors consume **split-adjusted prices** on the **current S&P admitted universe**; historical claims still need PIT membership.”
