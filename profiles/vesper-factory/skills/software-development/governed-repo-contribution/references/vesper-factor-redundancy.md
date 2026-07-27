# Factor Redundancy Analysis

**Module:** `app/services/factor_redundancy.py`

Identifies redundant feature clusters via Spearman correlation (|r| > 0.70),
then selects the best feature per cluster by cross-sectional IC. Reduces
collinearity before portfolio construction or model training.

## Pipeline

1. Load OHLCV + SEC features via the standard factor IC pipeline
2. Compute Spearman correlation matrix across all feature columns
3. Greedy clustering: iterate features, group any with |r| > 0.70
4. Per cluster: compute cross-sectional 10d IC, keep feature with
   highest absolute IC, flag rest as removable
5. Report: cluster members, redundancy ratio, keep/remove decisions

## Findings (5 tickers: AAPL/MSFT/NVDA/GOOGL/AMZN, 24 features)

| Keep | Remove | Why |
|------|--------|-----|
| `realized_vol_z60_lag1` | `realized_vol_20` | Both volatility measures |
| `vwap_dist` | `macd`, `rsi_proxy` | All momentum/trend |
| `volume_z20_lag1` | `dollar_volume_z20_lag1` | Both volume |

**Redundancy ratio: 17%** (4 of 24 features removable).

**Independence confirmed:** `entropy` and `hurst` are NOT in any redundant
cluster — they measure distinct market properties (disorder, persistence)
that don't overlap with volatility/momentum/volume.

## Limitations

- 5-ticker sample means cross-sectional ICs are near-zero (not enough
  cross-sectional variation for stable IC measurement). Run on 30+ tickers
  for meaningful IC-per-cluster decisions.
- Spearman r detects monotonic relationships — a non-monotonic dependency
  (e.g., U-shaped) would be missed.
- Threshold of 0.70 is arbitrary but standard. Lower thresholds produce
  more clusters; higher thresholds miss real redundancy.
- Full 30-ticker run timed out due to `calculate_features()` per-ticker
  overhead. Until the feature-computation pipeline is optimized, use
  5-10 ticker samples for quick redundancy checks.

## Integration with Factor Portfolio

After redundancy analysis:
1. Drop removable features from the signal set
2. Re-run cross-sectional ICs on the reduced set
3. Re-run the factor portfolio backtest to measure impact
4. A cleaner feature set should produce comparable or better Sharpe
   (less noise from redundant signals pulling in same direction)
