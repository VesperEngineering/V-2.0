# Vesper Factor Registry (v1.5 — 2026-07-09)

15 factors in registry from 6 data sources. 3 FM-validated factors drive the basket; 7 unvalidated factors are informational; 5 FM-failed duds at weight 0.0 (kept for research, not in blend).

## FM-Validated (|t| > 2.0, clean regression)

| Factor | Source | FM t-stat | Weight | Notes |
|---|---|---|---|---|
| `intraday_range` | Massive OHLCV | **+3.84** | 1.0 | Best single factor. High-low range / close, 21d avg. |
| `size` | Massive OHLCV | **-2.24** | 0.5 | Small-cap premium. Negated log dollar volume. Restored 2026-07-09. |
| `mean_reversion` | Massive OHLCV | **+2.27** | 0.4 | Composite: streak, 10d reversal, BB(20,2), RSI(14). |

## FM-Failed (Weight 0.0, kept in registry for research)

| Factor | Source | Solo IC IR | FM t-stat | Notes |
|---|---|---|---|---|
| `range_vol_ratio` | Massive OHLCV | +0.294 (best solo ever) | +1.04 | Price impact per unit volume. FM failed. |
| `max_return` | Massive OHLCV | Bali 2011 t=-6.22 | -1.07 | MAX lottery signal. Academic backing but FM failed. |
| `channel_breakout` | Massive OHLCV | -0.151 | +0.02 | Proximity to 20d high. Pure noise. |
| `gap_vol_20d` | Massive OHLCV | +0.098 | -0.04 | Overnight gap std. Pure noise. |
| `gv_cb_interaction` | Massive OHLCV | +0.144 | +1.07 | Gap x channel product. Failed. |

## Informational (Unvalidated, Weight 0.1)

| Factor | Source | Coverage | Notes |
|---|---|---|---|
| `sec_fundamentals` | SEC EDGAR | ~500 | Company facts from SEC. |
| `sec_insider_v2` | SEC Form 4 | 886 | Real-time only, no historical backfill. Live IC tracker. |
| `market_micro` | Massive normalized DB | 7,994 | Amihud + turnover approx + VWAP deviation. Rank-based z-score. |
| `macro_fred` | FRED | 502 sector | Yields, spreads, CPI, unemployment. FM t=-1.90 borderline. |
| `wiki_attention` | Wikipedia | ~500 | Page view data. |
| `massive_intraday` | Massive OHLCV | ~500 | Intraday bars. |
| `massive_sector_strength` | Massive OHLCV + Wikipedia | ~500 | Sector-level strength. |

## Removed (Deleted from disk 2026-07-09)

| Factor | FM t-stat | Why |
|---|---|---|
| `sp500_technical` | +0.58 | Not significant. Was anchor at 1.0. |
| `massive` | -0.52 | Noise. |
| `amihud` | -1.75 | Solo IC looked great, FM killed it. |
| `beta` | — | Diluted blend in optimizer. |
| `insider` (v1) | — | Superseded by sec_insider_v2. |
| `sentiment` | — | 38 tickers only, unvalidated. |
| `technical` | — | Dead. |
| `trends` | — | Dead. |
| `whale` | — | Dead. |
| `massive_fund` | — | Dead. |

## Key Rules

- **FM regression with Newey-West is gold standard.** |t| > 2.0 = keep, |t| < 1.5 = kill. Overrides solo IC, optimizer Sharpe, intuition, published academic t-stats.
- **Kill dilutive factors.** Remove from registry, don't leave at weight 0.0.
- **3 of 20+ factors survive FM.** Solo IC misleads. Published academic t-stats mislead. FM controls for correlated factors.
- **No factors work at 1d horizon.** Edge is 10-21d cross-sectional ranking.
- **Rank-based z-score for microstructure factors** (Amihud, turnover, VWAP).
- **Always run clean FM** (only validated factors) after demotions to avoid SE dilution.
- **Interaction terms don't work.** Tested ir x size, ir x mr, size x mr — all noise.

## Building a New Factor (Pattern)

1. **Signal mine** — prove edge exists (IC IR, horizon, direction). Use `scripts/signal_mine_v5.py` for comprehensive IC scan.
2. **Use `app/factors/db.py` helpers** — `open_ohlcv_db()`, `fetch_recent_dates()`, `fetch_ohlcv_rows()`, `build_ohlcv_panel()`. Never write raw SQLite in factors.
3. **Inherit `BaseFactor`** — set `name`, `required_data`, implement `_compute(self, *, root, date_stamp, universe, **kwargs) -> FactorResult`.
4. **Register** — add import + `_default.register_all(...)` in `registry.py`. Add timeout + weight in `scripts/run_all_factors.py`.
5. **Verify** — should return ~500 tickers from sp500_ohlcv.sqlite.
6. **FM-validate** — add to `scripts/fama_macbeth.py`, run `python scripts/fama_macbeth.py`. Promote weight only after |t| > 2.0.
7. **Run clean FM** — after demotions, run a 3-factor-only regression to get undiluted t-stats for the survivors.

## Pipeline (Vesper Scheduler)

8 jobs in `scheduler/jobs.json`, 500ms tick:
- OHLCV Ingest -> 7:00 AM Tue-Sat
- Factor Scores -> 8:00 AM daily
- Factor Basket -> 8:15 AM daily (sector-neutral)
- Alpaca Rebalance -> 9:35 AM M-F
- Portfolio Snapshot -> every 5s market hours
- Dashboard Refresh -> every 5s
- News Backfill -> 9:00 AM daily
- Live News -> hourly 8-5 M-F

Hermes cron: 9 pipeline jobs paused 2026-07-09. 3 remaining. Scheduler is sole pipeline authority.
