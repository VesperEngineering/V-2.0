# Vesper Quant Research Patterns

Concrete techniques for moving from governance-only to
evidence-producing quant research in Vesper.

## Factor IC Analysis (Rank IC / Spearman)

**Purpose:** Measure which features actually predict returns.
Replaces hardcoded `rank_ic_floor: 0.02` in governance receipts
with measured values from real data.

**Module:** `app/services/factor_ic_analysis.py`
**CLI:** `scripts/run_factor_ic_analysis.py --date YYYYMMDD [--massive --sp500]`

### Pipeline

1. Load OHLCV per ticker (SQLite `sqlite-analyst.db` or Massive coverage DBs)
2. Compute 20 features via `deploy/src/na/features.py::calculate_features()`
3. Compute forward returns at horizons 5/10/21 days
4. Rank IC = Spearman(feature_values, forward_returns) per feature-horizon pair
5. Skip NaN ICs (constant features like macro overlays)
6. Decay curves: is IC positive or decaying across horizons?

### Findings (S&P 500, 2018-2026, 97 tickers)

| Feature | Best Horizon | Best IC | Pattern |
|---------|-------------|---------|---------|
| vwap_dist | 10d | 0.840 | Peaks mid |
| macd | 21d | 0.818 | Builds steadily |
| rsi_proxy | 10d | 0.759 | Peaks mid |
| returns | 5d | 0.361 | Sharp decay (momentum) |
| volatility | 21d | -0.240 | Building negative |

### Pitfalls

- **Macro features (vix, tnx, oil, usd) are constant per day across tickers.**
  They produce NaN ICs in per-ticker analysis — expected, not a bug.
  For cross-sectional ICs, compute IC per date (ranking features across tickers
  each day) instead of pooling across time.
- **`calculate_features()` loads macro data from global cache** — first call
  prints "Loaded macro data from cache (506 rows)"; duplicate-label errors
  are harmless for the 16 non-macro features.
- **Forward returns need index alignment.** `_compute_forward_returns`
  creates a Series with RangeIndex; assigning to a DatetimeIndex DataFrame
  silently drops all values. Use `.values` assignment.
- **numpy bools aren't JSON-serializable.** Use a custom `default=` function
  in `json.dumps` that converts `np.bool_`, `np.floating`, and `np.integer`.
- **`datetime64[s, UTC]` can't compare with `pd.Timestamp`.** The SQLite loader
  returns UTC-timestamped data; strip timezone with `df.index.tz_convert(None)`
  before any `pd.Timestamp` comparison when filtering date ranges.

## Cross-Sectional vs Pooled IC (CRITICAL DISTINCTION)

**The most important finding in any factor IC analysis.** Pooled ICs
(concatenating all ticker data then computing correlation) are inflated
by autocorrelation. Cross-sectional ICs (per-day ranking across tickers)
measure true predictive power.

**Pooled IC** (what `factor_ic_analysis.py` computes by default):
- vwap_dist: 0.70-0.84 — appears dominant
- macd: 0.34-0.82
- rsi_proxy: 0.50-0.76

**Cross-sectional IC** (per-date ranking, honest alpha):
- entropy: 0.051 at 21d — real signal
- hurst: 0.030 at 21d
- realized_vol_z60_lag1: 0.030 at 10d
- vwap_dist: 0.023 — mostly autocorrelation, not alpha
- macd: 0.014 — nearly zero after removing autocorrelation
- rsi_proxy: 0.019

**Implication:** Cross-sectional ICs of 0.02-0.05 are competitive for
equity factors. The `rank_ic_floor: 0.02` hardcoded in every governance
receipt was accidentally correct. Features that appear dominant in pooled
analysis may be pure autocorrelation play.

**How to compute:** `panel.groupby(panel.index)` — for each date, get
features + forward returns for all available tickers, compute Spearman
per date, then average the per-date ICs. Use non-overlapping periods
for backtesting (step by `horizon` days, not daily).

## Factor Portfolio Backtest

**Purpose:** Combine weak cross-sectional features into a daily rank-based
portfolio and backtest against equal-weight benchmark.

**Module:** `app/services/factor_portfolio_backtest.py`

### Pipeline

1. Build daily signal scores as average of top-3 cross-sectional features
   (entropy + hurst + realized_vol_z60_lag1 for Vesper)
2. Each day: rank tickers by signal, select top quintile
3. Forward return = portfolio average over horizon (10d recommended)
4. Compare vs equal-weight: Sharpe, total return, max drawdown, hit rate
5. Use **non-overlapping** periods (step by horizon days) — compounding
   overlapping forward returns produces absurd numbers

### Findings (30 tickers, 49 non-overlapping 10d periods)

| Metric | 3-Factor | 4-Factor (+sentiment) | Equal-Weight |
|--------|----------|----------------------|-------------|
| Sharpe | 3.62 | 3.57 | 3.43 |
| Total Return | 55.2% | **60.4%** | 38.3% |
| Max Drawdown | -18.8% | -18.8% | -15.9% |

Sentiment adds ~5.2% absolute return but marginally reduces Sharpe
(3.57 vs 3.62) — adds signal but also noise. With daily backfill
(20+ dates of unique non-replayed sentiment), both IC and Sharpe
should improve as the signal becomes genuinely time-varying.

## News Sentiment Feature

**Purpose:** Add news sentiment as a features with measurable cross-sectional IC.

**Module:** `app/services/news_sentiment.py`

### Pipeline

1. Load headlines from WebZ JSON archive (`data/webz/news/raw/<date>/<ticker>.json`)
   or scrape FinViz live via `deploy/src/na/data/news.py`
2. Score sentiment via dictionary fallback (positive/negative word lists) —
   no deps, works immediately. Upgrade path: FinBERT (`deploy/src/na/sentiment.py`)
   requires `transformers` library and model download
3. Average sentiment per ticker per day
4. Compute cross-sectional IC vs forward returns

### Findings (single date, dictionary sentiment, 30 tickers)

| Horizon | Sentiment IC |
|---------|-------------|
| 5d | 0.028 |
| 10d | 0.031 |
| 21d | 0.049 |

Comparable to top technical features. Single-date limitation: IC replayed
across the full panel, not true time-series. For reliable measurement,
backfill 30+ days of news headlines.

### FinViz news backfill (free, no API key)

**Module:** `app/services/news_backfill.py`
**CLI:** `scripts/backfill_news_sentiment.py [--tickers ...] [--date YYYYMMDD]`

- Scrapes FinViz HTML per ticker (~0.2s each, 100 headlines)
- Scores via dictionary sentiment, stores to `data/news_sentiment/<date>.json`
- 30 tickers in ~6 seconds, zero API cost, no rate limits
- For cron: run daily after close, scores become rolling sentiment feature

### WebZ data structure

- Path: `data/webz/news/raw/<YYYYMMDD>/<ticker>.json`
- Posts per ticker: 10 (lite API — headlines only, no full text)
- Extraction: `data["posts"][i]["title"]` for headlines
- Ticker parsing: `os.path.basename(f).replace(".json", "").upper()`
  (Windows path handling requires `os.path.basename()` not string split)

## Massive Data Loading

**Purpose:** Load OHLCV from Massive coverage-expanded SQLite DBs
(8,091+ tickers, 2003-2026) for factor research.

**Module:** `app/services/massive_loader.py`

### Performance: batch-per-DB beats per-ticker-per-DB

- **Do:** one `SELECT ... WHERE ticker IN (?,?,...)` per DB, then `df.groupby("ticker")`
  → 48 tickers from 1 DB in 1.3s
- **Don't:** per-ticker `SELECT` loop per DB → 48 tickers from 1 DB in 17.6s
- **37x speedup** from batching

### DB structure

- Schema: `(ticker TEXT PK, as_of_date TEXT, open/close/high/low/volume REAL, ...)`
- Coverage-expanded DBs: `day_aggs_coverage_expanded_YYYY.sqlite` (year chunks)
- Latest refresh: `day_aggs_adapter_refresh_<iso>.sqlite` (~33 tickers, full history)
- Reference DB: `massive_reference_corporate_actions_active_universe_<date>.sqlite`

### S&P 500 loading

- Parse Wikipedia constituent list: regex `\|\s*\[([A-Z0-9.]+)\]`
- Cross-reference against Massive DBs: 502 of 503 constituents have data
- Use `--massive --sp500` CLI flags for automated pipeline
- **Practical limit:** 97 of top 100 load from 2 coverage DBs in ~45s.
  Full 503 tickers × 24 DBs is too slow for interactive use; use
  top-100 or most recent DBs only.

## Paper Evidence Loop

**Purpose:** Verify the model is alive and producing real decisions.
Runs a full daily cycle: data refresh → candidate generation → pretrade
readiness → (no-submit preview). Produces the first real evidence receipt
for a session.

**Command (preview only, no orders):**
```
python scripts/run_daily_paper_evidence_loop.py --date YYYYMMDD \
  --symbol AAPL --side buy --notional 5.00 --no-submit
```

### What it reveals

- Actual OHLCV freshness (may differ from board state — board said 06-18, real was 07-02)
- Current selected basket from the `working_nova` model alias
- Ensemble agreement (4 models, hold-12 support)
- Risk gate status (concentration, turnover, limits)
- Drift observables (SPY/QQQ returns, VIX level, stress score)
- Turnover history (20 lookback days, above-limit flags)

### Board drift detection

The board's "Current State" section can be stale. Cross-check:
- Board OHLCV date vs no-order report freshness check
- Board selected basket vs actual model output
- Board last-completed task vs actual pipeline receipts

When updating the board after a paper evidence loop:
- Update OHLCV/macro dates from the no-order report's data checks
- Update selected basket from the report's "Candidate Selection" table
- Update last-completed task to the loop's task ID
- Set next task to the next trading day's loop

## Test Environment Repair (Vesper)

When `python -m pytest --co -q` shows 99 `ModuleNotFoundError` collection
errors in a governed repo, the fix has three layers:

1. **Install core deps:** Read `deploy/requirements.txt`, install the
   minimal set (`pip install torch pandas numpy scipy scikit-learn`).
   Match versions when available.
2. **Install secondary deps:** Check remaining errors from `yahooquery`,
   `pandera`, `beautifulsoup4` — install if the project depends on them.
3. **Fix cross-test imports:** If any test file does `from tests.test_foo
   import DATE` and fails with `ModuleNotFoundError`, add empty
   `tests/__init__.py` (zero bytes, zero test changes, immediately
   unblocks collection). Only 1 file in Vesper used this pattern
   (`test_backtest_matrix_operator_review_briefing_runtime_validator.py`).

Verify with `python -m pytest --co -q | tail -3` — target zero collection
errors. Full-suite pass rate above 97% is healthy; flaky failures that
pass in isolation can be noted but not chased.

## Data Dimensions (Vesper as of 2026-07)

| Source | Tickers | Features | Date Range |
|--------|---------|----------|------------|
| SQLite (active) | 30 | 20 OHLCV | 2018-2026 |
| Massive coverage | 25,690 | 20 OHLCV | 2003-2019 |
| S&P 500 in Massive | 500 | 20 OHLCV | 2003-2019 |
| SEC companyfacts | ~5,000 | ~200 | Filing-based |
| Macro overlay | 1 (global) | 4 (VIX,TNX,oil,USD) | Per-day |
| WebZ news | 30 | 1 (sentiment) | 1 date |
| FinViz news | Unlimited | 1 (sentiment) | Live scrape |

**Total features available:** ~225 (20 OHLCV + ~200 SEC + 4 macro + 1 news).
**Cross-sectional ICs measured:** 13 features with valid ICs.

### Scale gap vs Rentec/HRT

Tick count is competitive (25,690 vs 5,000-10,000). Feature depth is the
bottleneck (13 measured vs 100-500). No tick/order-book/microstructure data.
SEC companyfacts are available but not wired into the factor IC pipeline —\nwiring them would 10x the feature set immediately. See\n`references/vesper-sec-features.md` for the integration guide and\n`references/vesper-factor-redundancy.md` for post-wiring feature pruning.
