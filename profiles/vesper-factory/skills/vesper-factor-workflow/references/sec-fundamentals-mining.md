# SEC Fundamentals Mining — Data Quality & Techniques

Tested session: 2026-07-08 against `artifacts/db/sqlite-analyst.db` (4.3M `sec_facts` rows, 1.8M `sec_filings` rows, 85K `ohlcv_data` rows, 473 tickers).

## Schema Recap

- **sec_facts** (4.3M rows): `ticker`, `tag`, `fiscal_year`, `fiscal_period`, `period_end`, `value`, `unit`, `accession_no`. Key fiscal_period: `'FY'` (annual).
- **sec_filings** (1.8M rows): `ticker`, `form`, `filing_date`, `accession_no`, `source_url`. **NO text/body column** — metadata only. Forms: 8-K (1.2M), 10-Q (466K), 10-K (146K). **Zero Form 4 filings** (insider transactions not in this table).
- **security_master** (4,603 tickers): `ticker`, `cik`, `company_name`, `sector`, `industry`.
- **ohlcv_data** (85K rows, 473 tickers): `ticker`, `timestamp` (mixed int epoch + text), `close`, `high`, `low`, `open`, `volume`. Dates 2018-02-05 to 2026-07-02.

## Available Fundamental Tags (FY, USD, in OHLCV ticker overlap)

| Tag | Rows | Tickers | Notes |
|---|---|---|---|
| `NetIncomeLoss` | 717K | 3,205 | Broadest coverage |
| `StockholdersEquity` | 683K | 3,152 | |
| `Assets` | 475K | 3,237 | |
| `OperatingIncomeLoss` | 517K | 2,681 | |
| `Liabilities` | 365K | 2,864 | |
| `Revenues` (plural) | 284K | 2,045 | **Sparse in OHLCV tickers** |
| `RevenueFromContractWithCustomerExcludingAssessedTax` | 150K | 1,821 | Alternate revenue tag |
| `GrossProfit` | 5 | 1 | Useless |
| `EarningsPerShareBasic` | 258 | 4 | Useless |
| `CommonStockSharesOutstanding` | 128 | 3 | Useless |

## Critical Pitfalls

### 1. `period_end_dt` Varies Across Tags for Same (ticker, FY)

XBRL data for the same fiscal year can have different `period_end` values per tag (prior-year comparison rows, restatements). Pivoting with `period_end_dt` in the index creates duplicate rows per (ticker, FY).

**Fix — two-step dedup + pivot:**
```python
# Step 1: For each (ticker, FY, tag), keep row with MAX period_end
facts_dedup = (
    facts.sort_values('pe_dt')
    .groupby(['ticker', 'fiscal_year', 'tag'], as_index=False)
    .last()
)

# Step 2: Pivot WITHOUT period_end in index
fund = facts_dedup.pivot_table(
    index=['ticker', 'fiscal_year'],
    columns='tag', values='value', aggfunc='first'
).reset_index()

# Step 3: Reattach max period_end per (ticker, FY)
max_pe = facts_dedup.groupby(['ticker', 'fiscal_year'])['pe_dt'].max().reset_index()
fund = fund.merge(max_pe, on=['ticker', 'fiscal_year'])
```

### 2. Revenue Tag Fragmentation

`Revenues` (plural, 2,045 tickers) and `RevenueFromContractWithCustomerExcludingAssessedTax` (1,821 tickers) are DIFFERENT tags. OHLCV tickers (e.g., AAPL) often have the latter but not the former. Using only `Revenues` drops most tickers from margin/asset_turnover computation.

**Fix — unify before dedup:**
```python
revenue_tags = ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax']
facts.loc[facts['tag'].isin(revenue_tags), 'tag'] = 'Revenue'
```

### 3. Negative StockholdersEquity

Companies with aggressive buybacks (HPQ, MCD, BA, MAR, KMB, DVA, NFG, CAH) have negative equity. This makes `roe` (NetIncome / negative equity = negative roe) and `leverage` (Assets / negative equity = negative leverage) nonsensical.

**Fix — filter positive equity AND assets:**
```python
fund = fund[(fund['StockholdersEquity'] > 0) & (fund['Assets'] > 0)]
```

### 4. Shares Outstanding Data Is Missing

Tags like `CommonStockSharesOutstanding`, `WeightedAverageNumberOfSharesOutstandingBasic` etc. have only 3-4 tickers with data (AMZN, BAC, COST). **Market-cap-based ratios (earnings yield, book-to-market, P/E) cannot be computed** from this DB. Stick to ratios that don't need shares outstanding.

### 5. OHLCV Coverage Is Heavily Concentrated

The `ohlcv_data` table has 473 tickers but coverage is very uneven:
- Pre-April 2026: ~15-16 stocks per date (sparse)
- 2026-04-08 onward: ~296 stocks per date (broad)
- Total panel: only ~75 dates with ≥15 stocks, almost all in 2024-2026

**Always check coverage distribution before trusting IC IR:**
```python
date_counts = panel.groupby('date').size()
print(date_counts.describe())
dates_ok = date_counts[date_counts >= 15]
print(f"Dates with ≥15 stocks: {len(dates_ok)} / {len(date_counts)}")
```

## Standard Ratio Pipeline

### Ratios That Work (no market cap needed)

| Ratio | Formula | Required Tags |
|---|---|---|
| ROE | NetIncomeLoss / StockholdersEquity | NI, Equity |
| ROA | NetIncomeLoss / Assets | NI, Assets |
| Leverage | Assets / StockholdersEquity | Assets, Equity |
| Asset Turnover | Revenue / Assets | Revenue, Assets |
| Net Margin | NetIncomeLoss / Revenue | NI, Revenue |
| Operating Margin | OperatingIncomeLoss / Revenue | OpInc, Revenue |

### Full Pipeline
```python
# 1. Compute ratio
fund[ratio_name] = fund[numerator] / fund[denominator]
fund[ratio_name] = fund[ratio_name].replace([np.inf, -np.inf], np.nan)

# 2. Winsorize GLOBALLY at 1st/99th percentile
lo = fund[ratio_name].quantile(0.01)
hi = fund[ratio_name].quantile(0.99)
fund[ratio_name + '_w'] = fund[ratio_name].clip(lo, hi)

# 3. Cross-sectional z-score per fiscal year (min 10 stocks)
def zscore_grp(x):
    if x.count() < 10:
        return pd.Series(np.nan, index=x.index)
    return (x - x.mean()) / x.std()

fund[ratio_name + '_sig'] = fund.groupby('fiscal_year')[ratio_name + '_w'].transform(zscore_grp)
```

### Compute Ratios Independently for Max Coverage

Don't require all 6 columns non-null. Each ratio only needs its numerator + denominator tags. Dropping NaN across all ratios cuts coverage dramatically. Instead, compute each ratio in isolation:

```python
# BAD — loses tickers that are missing Revenue but have NI+Assets
fund = fund.dropna(subset=['Revenues', 'NetIncomeLoss', 'Assets', ...])  # 79 tickers

# GOOD — independent ratio computation
for name, (num, den) in [('roe', ['NI','Equity']), ('roa', ['NI','Assets']), ...]:
    sub = fund.dropna(subset=[num, den])  # per-ratio, much wider
```

### Temporal Alignment (Panel Construction)

Fundamentals are "known" at `period_end + 45 days` (filing lag) and "stale" at `period_end + 410 days` (~13.5 months, next FY filing). For each (ticker, FY) row, apply the signal to all trading dates in `[known_date, stale_date]`:

```python
fund['known_date'] = fund['pe_dt'] + pd.Timedelta(days=45)
fund['stale_date'] = fund['pe_dt'] + pd.Timedelta(days=410)

# For each ticker, for each FY row, find OHLCV dates in window
for ticker in tickers:
    tf = fund[fund['ticker'] == ticker]
    tp = ohlcv[ohlcv['ticker'] == ticker]
    for _, fr in tf.iterrows():
        mask = (tp['date'] >= fr['known_date']) & (tp['date'] <= fr['stale_date'])
        matches = tp.loc[mask]
        # attach signal values to dates
```

## Results from 2026-07-08 Session

### Factor IC (21d forward, Spearman rank)

| Factor | Mean IC | IC IR | t-stat | N dates | Tickers |
|---|---|---|---|---|---|
| ROE | -0.159 | -2.15 | -5.38 | 75 | 296 |
| ROA | -0.146 | -1.87 | -4.68 | 75 | 296 |
| Operating Margin | -0.045 | -3.14 | -4.96 | 30 | 225 |
| Net Margin | -0.016 | -0.94 | -1.51 | 31 | 280 |
| Asset Turnover | -0.004 | -0.22 | -0.35 | 31 | 300 |
| Leverage | -0.003 | -0.03 | -0.07 | 75 | 318 |

**All profitability factors are NEGATIVE** — high-margin/high-ROE/high-ROA companies underperform short-term. This is a value/mean-reversion effect: expensive quality stocks reverse, cheap distressed stocks bounce.

### Caveat
IC IR annualization is unreliable because almost all cross-sectional dates are in 2024-2026 (heavily concentrated in 2026). Longer OHLCV history is needed for robust IC IR.

### sec_filings Sentiment
**Cannot be done.** The `sec_filings` table has no text/body column — only metadata (form type, filing_date, accession_no). Sentiment mining from filings requires downloading the actual filing documents from SEC EDGAR, which is a separate data pipeline not in this DB.
