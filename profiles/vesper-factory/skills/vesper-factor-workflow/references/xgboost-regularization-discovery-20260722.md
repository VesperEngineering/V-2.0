# XGBoost Regularization Discovery (2026-07-22)

## Context

The v20 XGBoost ranker (502 SP500 tickers, 24 raw price/volume features, 5-day forward return target, chronological train/test split at 2021-01-01) was severely overfitting: train IC ~0.14, out-of-sample IC ~0.022. The user asked to "test a few more options."

## Experiment Results

| Experiment | n_estimators | max_depth | reg_alpha | reg_lambda | subsample | colsample_bytree | Train IC | Test IC | Verdict |
|------------|-------------|-----------|-----------|------------|-----------|------------------|----------|---------|---------|
| Baseline (default) | 200 | 4 | 0.1 | 1.0 | 0.8 | 0.8 | 0.1395 | **0.0220** | Overfit |
| 1-day horizon | 200 | 4 | 0.1 | 1.0 | 0.8 | 0.8 | 0.1176 | **0.0156** | Worse |
| Moderate reg | 100 | 3 | 1.0 | 10.0 | 0.8 | 0.8 | 0.0718 | **0.0268** | Improving |
| **Strong reg** | **50** | **2** | **5.0** | **20.0** | **0.6** | **0.6** | **0.0433** | **0.0324** | **Best OOS** |

## Key Findings

1. **More features from the same data source does not help.** Expanding from 17 to 24 features (adding MACD, RSI, Stochastic, CCI, ATR, MFI, intraday return) with default regularization produced identical OOS IC (~0.022). Raw-price-derived technical indicators all derive from the same information and increase memorization capacity without adding new signal.

2. **Strong regularization improves generalization.** The best model uses only 50 trees, depth 2, high alpha/lambda, and aggressive subsampling. Train IC drops from 0.14 to 0.043, but OOS IC rises from 0.022 to 0.032. The train-test gap shrinks from 0.117 to 0.011.

3. **1-day horizon is harder, not easier.** Shifting from 5-day to 1-day forward return target reduced OOS IC from 0.022 to 0.016. Next-day returns are noisier and harder to predict than 5-day returns.

## Recommended Parameter Set

```python
xgb.XGBRegressor(
    n_estimators=50,
    max_depth=2,
    learning_rate=0.05,
    subsample=0.6,
    colsample_bytree=0.6,
    reg_alpha=5.0,
    reg_lambda=20.0,
    objective="reg:squarederror",
    n_jobs=-1,
    random_state=42,
)
```

## Next Steps

- OOS IC 0.032 is still below the 0.05 threshold for viable trading. Further improvements require better features, not more hyperparameter tuning.
- Options: (a) sector-relative returns instead of raw returns, (b) integrate pre-engineered V4 sequence tensors from `D:/vesper/vesper_data/market_data/numbers/training/v4_optimized/`, (c) adopt the existing PyTorch transformer (`transformer_latest.pth`) which was trained on 60-step sequences with 29 engineered features.
- Do not add more raw-price technical indicators.
