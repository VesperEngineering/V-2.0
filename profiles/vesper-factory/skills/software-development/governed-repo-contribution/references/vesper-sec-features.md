# SEC Companyfacts Features

**Modules:** `app/services/sec_features.py`, wired into `app/services/factor_ic_analysis.py`

The SEC companyfacts database (same `sqlite-analyst.db` as OHLCV) holds
quarterly fundamental data: total assets, revenue, net income, operating
cash flow per CIK/filing. These are forward-filled to daily resolution
and z-scored causally to avoid lookahead bias.

## Feature List (4 numeric)

| Feature | Definition | z-scored? |
|---------|-----------|-----------|
| `cf_assets_log_z` | log(1 + total assets) | Yes |
| `cf_revenue_log_z` | log(1 + quarterly revenue) | Yes |
| `cf_net_income_margin_z` | net income / revenue | Yes |
| `cf_operating_cf_to_assets_z` | operating CF / total assets | Yes |

Plus 3 mask/flag features (informational only, not used in IC computation):
`companyfacts_available_flag`, `companyfacts_missing_flag`,
`companyfacts_is_issuer_feature_applicable` (0 for ETFs: SPY, QQQ, IWM, etc.)

## Loading Pipeline

```python
from app.services.sec_features import load_sec_features
from app.services.factor_ic_analysis import _load_ohlcv, build_factor_ic_analysis

db = Path("artifacts/db/sqlite-analyst.db")
data = _load_ohlcv(tickers, db)
sec = load_sec_features(str(db), data)  # loads + forward-fills
p = build_factor_ic_analysis(..., sec_features=sec)
```

Key implementation detail: `load_sec_features()` forward-fills SEC data
(replace 0.0 → NaN → ffill → fillna(0.0)) because fundamental data
updates quarterly. Without forward-fill, 80% of values are zero and
Spearman produces NaN for most feature-horizon pairs.

The `_feature_matrix()` function in `factor_ic_analysis.py` now accepts
an optional `sec_features` dict and merges the 4 numeric columns into
the feature DataFrame per ticker via `pd.concat`.

`_compute_ics()` dynamically discovers all feature columns (excluding
`ticker`, `date`, and `fwd_ret_*` columns) — no need to add SEC feature
names to `FEATURE_NAMES`.

## IC Findings (30 tickers, pooled)

| Feature | 5d IC | 10d IC | 21d IC | Pattern |
|---------|-------|--------|--------|---------|
| `cf_operating_cf_to_assets_z` | -0.015 | -0.035 | **-0.060** | Building negative |
| `cf_revenue_log_z` | -0.011 | -0.023 | **-0.056** | Building negative |
| `cf_net_income_margin_z` | +0.015 | +0.020 | +0.025 | Weak positive |
| `cf_assets_log_z` | -0.008 | -0.021 | -0.019 | Weak negative |

All four SEC features show **negative ICs at long horizons** — classic
value factor: large companies with high assets/revenue/margins underperform
(Big = boring). `cf_operating_cf_to_assets_z` at -0.06 is comparable to
`hurst` (+0.063) and `dollar_volume_z20_lag1` (+0.058) in pooled rank.

Cross-sectional ICs will be lower (as with OHLCV features). Pooled ICs
overstate predictive power — see the Cross-Sectional vs Pooled section.

## Pitfalls

- **60-day windows show all zeros.** Use full date range (2113 days from
  2018-2026) — `_causal_zscore` needs a minimum window before values
  become non-zero. With the full date range, 1753-2026 of 2113 rows
  have valid values per feature.
- **ETFs (SPY, QQQ, IWM) return all zeros** — expected, they have
  `companyfacts_is_issuer_feature_applicable = 0.0`.
- **Last non-zero values may be months behind** — SEC filings have
  processing delays. AAPL's last non-zero `cf_assets_log_z` was 2023-11-18
  in the 2026-07 database, meaning the most recent fiscal data hasn't
  been ingested yet. This is normal — fundamentals lag prices.
